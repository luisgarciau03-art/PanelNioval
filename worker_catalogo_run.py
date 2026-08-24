"""Runner del worker local de envío de catálogo (Plan 5, transporte B).

Se ejecuta en la PC del owner (donde vive la sesión de WhatsApp Web). Lee la cola
`ENVIOS_CATALOGO` desde Google Sheets, envía el catálogo por WhatsApp usando el
transporte Selenium existente (`envio_catalogo.py`), escribe el estado final y
reporta un heartbeat al panel en Railway.

Uso (PC del owner):
    set TELEGRAM_TOKEN=...        (opcional, para reportes)
    set TELEGRAM_CHAT_ID=...
    set PANEL_URL=https://<tu-app>.up.railway.app   (para heartbeat)
    set WORKER_TOKEN=...          (obligatorio: el heartbeat devuelve 401 sin el)
    python worker_catalogo_run.py

Instalar como Tarea Programada de Windows: ver `instalar-worker.ps1`.
"""
import json
import os
import sys
import subprocess
import tempfile
import time
import traceback

print("[worker] cargando dependencias (la primera vez puede tardar ~1-2 min; NO cierres)...", flush=True)

import gspread
from gspread.exceptions import WorksheetNotFound
from google.oauth2.service_account import Credentials
import requests

import envio_catalogo as ec     # transporte Selenium (WhatsApp Web)
import nucleo_catalogo as nc
import worker_catalogo as wc

# El worker es INDEPENDIENTE de la app Flask (no importa app.py → arranca en
# segundos en vez de ~2 min con pandas/googleapiclient). Solo necesita gspread.
_DIR = os.path.dirname(os.path.abspath(__file__))
RESPUESTAS_SHEET_ID = "1U_z1KNqCxSRZVi7wvO2FQH4zIdS_wxuafxj6YHdHEqg"  # = SHEET_IDS['respuestas']
ENVIOS_WS_NAME = "ENVIOS_CATALOGO"
CRED_FILE = os.path.join(_DIR, "bubbly-subject-412101-c969f4a975c5.json")

LOCK_PATH = os.path.join(tempfile.gettempdir(), "worker_catalogo.lock")
LOCK_TTL = 30 * 60  # 30 min: un lock más viejo se considera huérfano


def _get_client():
    """Cliente gspread desde GOOGLE_CREDENTIALS_JSON (env) o el .json local."""
    scopes = ["https://www.googleapis.com/auth/spreadsheets",
              "https://www.googleapis.com/auth/drive"]
    creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON")
    if creds_json:
        creds = Credentials.from_service_account_info(json.loads(creds_json), scopes=scopes)
    else:
        creds = Credentials.from_service_account_file(CRED_FILE, scopes=scopes)
    return gspread.authorize(creds)


def _abrir_ws_envios(client):
    """Worksheet ENVIOS_CATALOGO del spreadsheet de respuestas."""
    sp = client.open_by_key(RESPUESTAS_SHEET_ID)
    return sp.worksheet(ENVIOS_WS_NAME)


def _proceso_vivo(pid):
    """True si el PID sigue corriendo. Ante la duda, True: mejor no arrancar dos
    workers que arrancar sobre uno vivo y duplicar envios de WhatsApp."""
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            salida = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                capture_output=True, text=True, timeout=10,
            ).stdout
        except (OSError, subprocess.SubprocessError):
            return True
        return str(pid) in salida
    try:
        os.kill(pid, 0)          # senal 0: no envia nada, solo comprueba
    except ProcessLookupError:
        return False
    except PermissionError:      # existe, es de otro usuario
        return True
    except OSError:
        return True
    return True


def _pid_del_lock():
    """PID guardado en el lock, o 0 si no se puede leer."""
    try:
        with open(LOCK_PATH, encoding="utf-8") as f:
            return int(f.read().split()[0])
    except (OSError, ValueError, IndexError):
        return 0


def _cerrar_chromes_huerfanos(perfil):
    """Cierra los Chrome que quedaron agarrados al perfil de Selenium.

    El bloque finally hace driver.quit(), pero no corre si el proceso muere de
    golpe: cerrar la consola con la X, un apagon o un kill. Entonces Chrome
    sobrevive sujetando el perfil, y la siguiente corrida falla con
    SessionNotCreatedException "Chrome instance exited", que no dice nada sobre
    la causa real. Medido en la maquina del owner: 12 procesos huerfanos de dos
    dias atras.

    Solo se tocan los que citan ESTE perfil en su linea de comandos; el Chrome
    normal del operador no se toca. Windows unicamente: el worker corre ahi.
    """
    if os.name != "nt":
        return 0
    marca = os.path.basename(os.path.normpath(perfil))
    try:
        salida = subprocess.run(
            ["wmic", "process", "where", "name='chrome.exe'", "get", "ProcessId,CommandLine", "/format:csv"],
            capture_output=True, text=True, timeout=30,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return 0

    pids = []
    for linea in salida.splitlines():
        if marca in linea:
            partes = linea.rsplit(",", 1)
            if len(partes) == 2 and partes[1].strip().isdigit():
                pids.append(partes[1].strip())
    if not pids:
        return 0

    print(f"[worker] {len(pids)} Chrome huerfanos del perfil; cerrandolos.")
    cerrados = 0
    for pid in pids:
        try:
            subprocess.run(["taskkill", "/PID", pid, "/F", "/T"],
                           capture_output=True, timeout=15)
            cerrados += 1
        except (OSError, subprocess.SubprocessError):
            pass
    return cerrados


def _adquirir_lock():
    """Evita dos corridas solapadas. Usa creación atómica ('x').

    Un lock se considera huérfano si el proceso que lo escribió ya no existe, o
    si supera LOCK_TTL. Antes solo se miraba la edad: un worker cerrado con
    Ctrl+C o caido por un apagon dejaba el archivo y bloqueaba los reintentos
    hasta 30 minutos, sin ninguna corrida real en curso. El PID es la senal
    directa; el TTL queda como respaldo para PIDs reciclados por el sistema.
    """
    if os.path.isfile(LOCK_PATH):
        try:
            edad = time.time() - os.path.getmtime(LOCK_PATH)
        except OSError:
            edad = 0
        pid = _pid_del_lock()
        if edad < LOCK_TTL and _proceso_vivo(pid):
            print(f"[worker] otra corrida en curso (PID {pid}); saliendo.")
            return False
        motivo = "proceso muerto" if edad < LOCK_TTL else f"mas de {LOCK_TTL // 60} min"
        print(f"[worker] lock huerfano ({motivo}); se reemplaza.")
        try:
            os.remove(LOCK_PATH)
        except OSError:
            pass
    try:
        with open(LOCK_PATH, "x", encoding="utf-8") as f:  # 'x' = fallo si ya existe (atómico)
            f.write(f"{os.getpid()} {time.time()}")
    except FileExistsError:
        print("[worker] carrera al adquirir el lock; saliendo.")
        return False
    return True


def _liberar_lock():
    try:
        os.remove(LOCK_PATH)
    except OSError:
        pass


def construir_transporte_selenium(driver):
    """Devuelve un transporte con la interfaz enviar(tel, mensajes, archivos)->ResultadoEnvio."""
    def transporte(telefono, mensajes, archivos):
        # WhatsApp Web puede tardar en abrir un chat nuevo; damos margen (configurable).
        espera = int(os.environ.get("WA_CHAT_WAIT_SECS", "45"))
        estado = ec.abrir_chat(driver, telefono, max_wait_override=espera)
        if estado == "invalido":
            return wc.ResultadoEnvio(nc.NUMERO_INVALIDO, "popup 'número no válido'")
        if estado != "ok":
            return wc.ResultadoEnvio(nc.FALLO, f"el chat no cargó (estado={estado})")
        for m in mensajes:
            ec.enviar_mensaje(driver, m)
            time.sleep(0.6)
        for nombre in archivos:
            ruta = ec.resolve_media_path(nombre)
            if ruta:
                ec.enviar_archivo(driver, ruta)
                time.sleep(4)  # dejar que la UI termine de enviar antes del siguiente adjunto
        return wc.ResultadoEnvio(nc.ENVIADO, "mensajes y archivos enviados")
    return transporte


def esperar_whatsapp_listo(driver, timeout):
    """Espera a que WhatsApp Web termine de cargar (lista de chats visible) antes
    de intentar abrir chats. Evita el 'spinner infinito' justo tras escanear el QR."""
    from selenium.webdriver.common.by import By
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            if driver.find_elements(By.CSS_SELECTOR, "#side, #pane-side, div[aria-label='Lista de chats']"):
                return True
        except Exception:
            pass
        time.sleep(2)
    return False


def _reportar_heartbeat(resumen):
    panel = os.environ.get("PANEL_URL")
    if not panel:
        print("[worker] heartbeat no enviado: falta PANEL_URL")
        return
    headers = {}
    wt = os.environ.get("WORKER_TOKEN")
    if wt:
        headers["X-Worker-Token"] = wt
    try:
        r = requests.post(f"{panel.rstrip('/')}/api/catalogo/heartbeat",
                          json={"resumen": resumen}, headers=headers, timeout=10)
        if r.status_code not in (200, 201, 202, 204):
            print(f"[worker] heartbeat devolvio HTTP {r.status_code} (auth fallida o panel rechaza)")
    except Exception as e:
        print(f"[worker] no se pudo enviar heartbeat (¿panel caído?): {e!r}")


def _modo_loop():
    """True si se pide modo continuo: arg --loop o env WORKER_LOOP=1."""
    return ("--loop" in sys.argv) or (os.environ.get("WORKER_LOOP") == "1")


def main():
    loop = _modo_loop()
    if not _adquirir_lock():
        return
    # GATE DE SEGURIDAD: exige y valida la contraseña de envío antes de tocar WhatsApp.
    autorizado, motivo = wc.autorizar_envio()
    print(f"[worker] autorización de envío: {motivo}")
    if not autorizado:
        _liberar_lock()
        return
    driver = None
    try:
        client = _get_client()
        # Mensajes y archivos del catálogo (misma fuente que envio_catalogo.py).
        sheet_msg = client.open_by_key(ec.SPREADSHEET_ID_TELEFONOS).worksheet(ec.SHEET_NAME_MENSAJE)
        mensajes = ec.obtener_mensajes(sheet_msg)
        archivos = ec.IMAGENES

        ws = _abrir_ws_envios(client)
        _cerrar_chromes_huerfanos(ec.FALLBACK_PROFILE_DIR)
        driver = ec.iniciar_driver(ec.FALLBACK_PROFILE_DIR, "Default")
        driver.get("https://web.whatsapp.com/")
        print("[worker] Abre WhatsApp Web y escanea el QR si corresponde.")
        sync_wait = int(os.environ.get("WA_SYNC_WAIT_SECS", "120"))
        print(f"[worker] Esperando a que WhatsApp cargue tus chats (hasta {sync_wait}s)...")
        if esperar_whatsapp_listo(driver, sync_wait):
            print("[worker] WhatsApp Web listo (lista de chats cargada).")
            time.sleep(3)
        else:
            print("[worker] AVISO: no se detectó la lista de chats (¿sigue sincronizando o falta QR?). "
                  "Se intentará de todos modos.")

        transporte = construir_transporte_selenium(driver)

        if loop:
            intervalo = int(os.environ.get("WORKER_LOOP_SECS", "15"))
            print(f"[worker] MODO CONTINUO: procesando la cola cada {intervalo}s (Ctrl+C para salir).")
            try:
                while True:
                    try:
                        resumen = wc.procesar_cola(ws, transporte, mensajes, archivos)
                        if resumen["procesados"]:
                            print(f"[worker] procesados: {resumen}")
                            _reportar_heartbeat(resumen)
                        else:
                            _reportar_heartbeat({"vivo": True, "procesados": 0})
                    except KeyboardInterrupt:
                        raise
                    except Exception:
                        # Resiliente: un error transitorio (red/cuota) NO mata el loop.
                        print("[worker] error transitorio (se continúa la próxima vuelta):")
                        traceback.print_exc()
                        _reportar_heartbeat({"error": True})
                    time.sleep(intervalo)
            except KeyboardInterrupt:
                print("[worker] detenido por el usuario (Ctrl+C).")
        else:
            resumen = wc.procesar_cola(ws, transporte, mensajes, archivos)
            print(f"[worker] corrida terminada: {resumen}")
            _reportar_heartbeat(resumen)
    except Exception:
        print("[worker] error en la corrida:")
        traceback.print_exc()
        _reportar_heartbeat({"error": True})
        sys.exit(1)
    finally:
        try:
            if driver:
                driver.quit()
        except Exception:
            pass
        _liberar_lock()


if __name__ == "__main__":
    main()
