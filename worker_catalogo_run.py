"""Runner del worker local de envío de catálogo (Plan 5, transporte B).

Se ejecuta en la PC del owner (donde vive la sesión de WhatsApp Web). Lee la cola
`ENVIOS_CATALOGO` desde Google Sheets, envía el catálogo por WhatsApp usando el
transporte Selenium existente (`envio_catalogo.py`), escribe el estado final y
reporta un heartbeat al panel en Railway.

Uso (PC del owner):
    set TELEGRAM_TOKEN=...        (opcional, para reportes)
    set TELEGRAM_CHAT_ID=...
    set PANEL_URL=https://<tu-app>.up.railway.app   (para heartbeat)
    set WORKER_TOKEN=...          (si el panel lo exige)
    python worker_catalogo_run.py

Instalar como Tarea Programada de Windows: ver `instalar-worker.ps1`.
"""
import os
import sys
import tempfile
import time
import traceback

import requests

import app                      # get_gs_client, SHEET_IDS, _abrir_ws_envios
import envio_catalogo as ec     # transporte Selenium (WhatsApp Web)
import nucleo_catalogo as nc
import worker_catalogo as wc

LOCK_PATH = os.path.join(tempfile.gettempdir(), "worker_catalogo.lock")
LOCK_TTL = 30 * 60  # 30 min: un lock más viejo se considera huérfano


def _adquirir_lock():
    """Evita dos corridas solapadas. Usa creación atómica ('x'); si el lock existe
    pero es más viejo que LOCK_TTL, se considera huérfano y se reemplaza."""
    if os.path.isfile(LOCK_PATH):
        try:
            edad = time.time() - os.path.getmtime(LOCK_PATH)
        except OSError:
            edad = 0
        if edad < LOCK_TTL:
            print("[worker] otra corrida en curso (lock activo); saliendo.")
            return False
        try:
            os.remove(LOCK_PATH)  # lock huérfano
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
        estado = ec.abrir_chat(driver, telefono)
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
                time.sleep(2)
        return wc.ResultadoEnvio(nc.ENVIADO, "mensajes y archivos enviados")
    return transporte


def _reportar_heartbeat(resumen):
    panel = os.environ.get("PANEL_URL")
    if not panel:
        return
    headers = {}
    wt = os.environ.get("WORKER_TOKEN")
    if wt:
        headers["X-Worker-Token"] = wt
    try:
        requests.post(f"{panel.rstrip('/')}/api/catalogo/heartbeat",
                      json={"resumen": resumen}, headers=headers, timeout=10)
    except Exception:
        print("[worker] no se pudo enviar heartbeat (¿panel caído?)")


def main():
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
        client = app.get_gs_client()
        # Mensajes y archivos del catálogo (misma fuente que envio_catalogo.py).
        sheet_msg = client.open_by_key(ec.SPREADSHEET_ID_TELEFONOS).worksheet(ec.SHEET_NAME_MENSAJE)
        mensajes = ec.obtener_mensajes(sheet_msg)
        archivos = ec.IMAGENES

        ws = app._abrir_ws_envios(crear=False)
        driver = ec.iniciar_driver(ec.FALLBACK_PROFILE_DIR, "Default")
        driver.get("https://web.whatsapp.com/")
        print("[worker] Abre WhatsApp Web y escanea el QR si corresponde.")
        time.sleep(ec.T_CHAT_LOAD + 3)

        transporte = construir_transporte_selenium(driver)
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
