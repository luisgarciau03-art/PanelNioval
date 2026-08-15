import os
import time
import shutil
import tempfile
from time import sleep
from datetime import datetime
from typing import Optional

import gspread
from oauth2client.service_account import ServiceAccountCredentials
import requests

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import WebDriverException, TimeoutException

try:
    import pyperclip
except Exception:
    pyperclip = None

# ---------------------------
# Configuración
# ---------------------------
SPREADSHEET_ID_PEDIDOS = '1U_z1KNqCxSRZVi7wvO2FQH4zIdS_wxuafxj6YHdHEqg'
SHEET_NAME_PEDIDOS = 'Respuestas de formulario 1'
SPREADSHEET_ID_TELEFONOS = '1oEtAiYaYVdOnEum3tbp_BminBUdj06JzXqJhaOVQFlk'
SHEET_NAME_TELEFONOS = 'BD CONTACTOS'
SHEET_NAME_MENSAJE = 'Mensajes'

PDF_LOCAL_PATH = 'C:/Users/PC 1/Files mensajes'
IMAGENES = ['IMG1.jpg', 'Video1.mp4', 'CATÁLOGO NIOVAL.pdf', 'LPNIOVAL.pdf']

FALLBACK_PROFILE_DIR = 'C:/Users/PC 1/ChromeSeleniumProfile'
CHROME_BINARY = 'C:/Program Files/Google/Chrome/Application/chrome.exe'

T_CHAT_LOAD = 10
WAIT_TIMEOUT = 30
T_SHORT = 0.5
PREVIEW_TIMEOUT_IMAGE = 40
PREVIEW_TIMEOUT_VIDEO = 120
EXTRA_WAIT_VIDEO_SECS = 15
EXTRA_WAIT_AFTER_SEND_VIDEO = 15
KEEP_BROWSER_OPEN = False
WAIT_BEFORE_CLOSE_SECS: Optional[int] = 600

MEDIA_EXTS = [
    '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp',
    '.mp4', '.mov', '.avi', '.mkv', '.webm', '.3gp', '.quicktime'
]
DOC_EXTS = ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.zip']

# Telegram config — leídos desde variables de entorno (NUNCA hardcodear el token).
# El token histórico 8404009072 quedó expuesto en ~14 copias y DEBE rotarse (acción del owner).
# Definir antes de correr:  set TELEGRAM_TOKEN=...  y  set TELEGRAM_CHAT_ID=...
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

def enviar_reporte_telegram(token, chat_id, texto):
    # Fallo explícito y seguro: sin credenciales, no se intenta enviar (no crashea la corrida de WhatsApp).
    if not token or not chat_id:
        print("[TELEGRAM] TELEGRAM_TOKEN/TELEGRAM_CHAT_ID no configurados; se omite el reporte.")
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": texto,
        "parse_mode": "Markdown"
    }
    try:
        r = requests.post(url, data=payload)
        if r.status_code == 200:
            print("Reporte enviado a Telegram correctamente.")
        else:
            print(f"Error enviando reporte a Telegram: {r.text}")
    except Exception as e:
        print("Error en la comunicación con Telegram:", e)

def fecha_es_hoy(fecha_str: str) -> bool:
    try:
        fecha = datetime.strptime(fecha_str.split(' ')[0], "%d/%m/%Y")
        return fecha.date() == datetime.now().date()
    except Exception:
        return False

def buscar_telefono(nombre_tienda: str, tel_rows: list) -> Optional[str]:
    for tel_row in tel_rows[1:]:
        tienda_tel = tel_row[0].strip().lower() if len(tel_row) > 0 else ""
        telefono = tel_row[18].strip() if len(tel_row) > 18 else ""
        if tienda_tel == nombre_tienda.strip().lower():
            if telefono and not telefono.startswith('+'):
                telefono = '+' + telefono
            return telefono
    return None

def obtener_mensajes(sheet_mensajes) -> list:
    mensajes = sheet_mensajes.col_values(1)[2:]
    return [m for m in mensajes if m.strip()]

def resolve_media_path(name: str) -> Optional[str]:
    if os.path.isabs(name):
        if os.path.isfile(name):
            return name
        base = name
        if not os.path.splitext(name)[1]:
            for ext in ['.mp4', '.MP4', '.mov', '.avi', '.mkv', '.webm',
                        '.jpg', '.jpeg', '.png', '.webp', '.gif', '.pdf', '.PDF']:
                candidate = base + ext
                if os.path.isfile(candidate):
                    return candidate
        return None

    base = os.path.join(PDF_LOCAL_PATH, name)
    if os.path.isfile(base):
        return base
    if os.path.splitext(name)[1]:
        return None
    for ext in ['.mp4', '.MP4', '.mov', '.avi', '.mkv', '.webm',
                '.jpg', '.jpeg', '.png', '.webp', '.gif', '.pdf', '.PDF']:
        candidate = base + ext
        if os.path.isfile(candidate):
            return candidate
    return None

def crear_opciones(user_data_dir=None, profile_dir=None) -> Options:
    opts = Options()
    if user_data_dir:
        opts.add_argument(f"--user-data-dir={user_data_dir}")
    if profile_dir:
        opts.add_argument(f"--profile-directory={profile_dir}")
    if CHROME_BINARY and os.path.isfile(CHROME_BINARY):
        opts.binary_location = CHROME_BINARY
    opts.add_argument('--no-sandbox')
    opts.add_argument('--disable-dev-shm-usage')
    opts.add_argument('--disable-gpu')
    opts.add_argument('--disable-extensions')
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option('useAutomationExtension', False)
    return opts

def iniciar_driver(user_data_dir, profile_dir) -> webdriver.Chrome:
    svc = Service(ChromeDriverManager().install())
    opts = crear_opciones(user_data_dir, profile_dir)
    return webdriver.Chrome(service=svc, options=opts)

# ---------------------------
# Detección robusta de popup "número no válido" y cierre
# ---------------------------
def detect_invalid_popup(driver) -> bool:
    """
    Detecta el popup "El número de teléfono compartido a través de la dirección URL no es válido."
    Retorna True si detecta el popup (por texto exacto, parcial, OK, o page_source).
    """
    try:
        # XPath exacto según el HTML proporcionado
        xp_exact = '//div[normalize-space(text())="El número de teléfono compartido a través de la dirección URL no es válido."]'
        if driver.find_elements(By.XPATH, xp_exact):
            return True

        # Texto parcial dentro de cualquier div (más tolerante)
        xp_contains = '//div[contains(normalize-space(.), "El número de teléfono compartido a través de la dirección URL no es válido")]'
        if driver.find_elements(By.XPATH, xp_contains):
            return True

        # Búsqueda más genérica por "no es válido" (case-insensitive)
        xp_generic = '//div[contains(translate(., "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "no es válido")]'
        if driver.find_elements(By.XPATH, xp_generic):
            return True

        # Buscar botón OK (puede indicar el modal)
        xp_ok = '//span[normalize-space(.)="OK" or normalize-space(.)="Ok" or normalize-space(.)="ok"]'
        if driver.find_elements(By.XPATH, xp_ok):
            src = driver.page_source or ""
            if "El número de teléfono compartido a través de la dirección URL no es válido" in src or ("número de teléfono" in src and "no es válido" in src):
                return True
            return True

        # Fallback: buscar la frase en page_source
        src = driver.page_source or ""
        if "El número de teléfono compartido a través de la dirección URL no es válido" in src:
            return True
        if "número de teléfono" in src and "no es válido" in src:
            return True

    except Exception:
        pass
    return False

def _close_invalid_modal_if_present(driver) -> bool:
    """
    Intenta cerrar el modal de 'número no válido' si está presente.
    Retorna True si encontró y cerró (o intentó cerrar) un modal; False si no detectó modal.
    """
    try:
        ok_xpaths = [
            # span OK dentro del dialogo que contiene el texto
            '//div[normalize-space(.)="El número de teléfono compartido a través de la dirección URL no es válido."]/ancestor::div[@role="dialog"]//span[normalize-space(.)="OK"]',
            '//span[normalize-space(.)="OK" or normalize-space(.)="Ok" or normalize-space(.)="ok"]',
            '//div[@role="button"]//span[normalize-space(.)="OK"]'
        ]
        for xp in ok_xpaths:
            elems = driver.find_elements(By.XPATH, xp)
            for el in elems:
                try:
                    if el.is_displayed():
                        try:
                            el.click()
                        except Exception:
                            driver.execute_script("arguments[0].click();", el)
                        sleep(0.6)
                        return True
                except Exception:
                    continue

        # intentar click en backdrop/modal container
        backdrop_xp = '//div[contains(@class,"popup") or contains(@class,"modal") or contains(@class,"x9f619")]'
        b = driver.find_elements(By.XPATH, backdrop_xp)
        for el in b:
            try:
                if el.is_displayed():
                    try:
                        el.click()
                    except Exception:
                        driver.execute_script("arguments[0].click();", el)
                    sleep(0.5)
                    return True
            except Exception:
                continue

        # último recurso: ESC
        try:
            ActionChains(driver).send_keys(Keys.ESCAPE).perform()
            sleep(0.5)
            # no garantizamos que haya cerrado, devolvemos False porque no confirmamos
            return False
        except Exception:
            pass

    except Exception:
        pass
    return False

# ---------------------------
# Persistencia: columna ENVIADO_WA en la hoja de pedidos
# ---------------------------
def ensure_sent_column(sheet) -> int:
    """
    Asegura que la hoja tenga una columna llamada 'ENVIADO_WA'.
    Retorna el índice (1-based) de la columna.
    Si no existe, la crea como última columna.
    """
    try:
        headers = sheet.row_values(1)
    except Exception:
        headers = []
    header_upper = [h.strip().upper() for h in headers]
    if 'ENVIADO_WA' in header_upper:
        return header_upper.index('ENVIADO_WA') + 1
    # crear columna al final
    col = len(headers) + 1
    try:
        sheet.update_cell(1, col, 'ENVIADO_WA')
        print(f"Columna 'ENVIADO_WA' creada en la posición {col}.")
    except Exception as e:
        print("No se pudo crear la columna ENVIADO_WA:", e)
    return col

def abrir_chat(driver: webdriver.Chrome, telefono: str, max_wait_override: Optional[int] = None) -> str:
    """
    Abre el chat mediante la URL y devuelve:
      - 'ok' si el chat está listo para enviar,
      - 'invalido' si detecta el popup de número no válido,
      - 'fail' si no carga nada en el tiempo máximo.
    Limpia modales residuales antes y después, y guarda debug (screenshot + page_source) si detecta el popup.
    """
    # Limpiar modal residual antes de navegar
    try:
        _close_invalid_modal_if_present(driver)
    except Exception:
        pass

    url = f"https://web.whatsapp.com/send?phone={telefono.replace('+','')}&text="
    driver.get(url)
    print(f"Abriendo chat {telefono} ...")

    chat_xpath = '//div[@contenteditable="true"]'
    try:
        default_wait = max(20, (globals().get('T_CHAT_LOAD', 10) or 10) + 10)
    except Exception:
        default_wait = 20
    max_wait = max_wait_override if max_wait_override is not None else default_wait

    t0 = time.time()
    while time.time() - t0 < max_wait:
        sleep(1)

        # 1) Detectar popup inválido
        try:
            if detect_invalid_popup(driver):
                # guardado debug
                try:
                    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                    safe_tel = telefono.replace('+','').replace('/','_')
                    png = f"debug_invalid_{safe_tel}_{ts}.png"
                    htmlf = f"debug_invalid_{safe_tel}_{ts}.html"
                    driver.save_screenshot(png)
                    with open(htmlf, "w", encoding="utf-8") as f:
                        f.write(driver.page_source or "")
                    print(f"[DEBUG] Guardado screenshot y page_source para {telefono}: {png}, {htmlf}")
                except Exception as ex_dbg:
                    print("No se pudo guardar debug:", ex_dbg)

                # Intentar cerrar el modal para dejar el driver en estado limpio
                try:
                    closed = _close_invalid_modal_if_present(driver)
                    if closed:
                        print("Modal inválido cerrado (OK/ESC).")
                    else:
                        print("Modal inválido detectado, intento de cierre por ESC realizado o no clicable.")
                except Exception:
                    pass

                print("Número de teléfono no válido (modal detectado).")
                return 'invalido'
        except Exception:
            pass

        # 2) Detectar área de chat (listo para enviar)
        try:
            chat_boxes = driver.find_elements(By.XPATH, chat_xpath)
            visible = False
            for el in chat_boxes:
                try:
                    if el.is_displayed():
                        visible = True
                        break
                except Exception:
                    continue
            if visible:
                sleep(0.5)
                return 'ok'
        except Exception:
            pass

    # Timeout: no detectó ni modal ni área de chat
    print("No se pudo cargar el chat (timeout).")
    try:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_tel = telefono.replace('+','').replace('/','_')
        fname = f"debug_timeout_{safe_tel}_{ts}.html"
        with open(fname, "w", encoding="utf-8") as f:
            f.write(driver.page_source or "")
        print(f"[DEBUG] Guardado page_source por timeout para {telefono}: {fname}")
    except Exception:
        pass
    return 'fail'

def find_message_box(driver: webdriver.Chrome, timeout=15):
    xpath = '//div[@contenteditable="true" and (@data-tab="10" or contains(@aria-placeholder,"Escribe"))]'
    try:
        elems = WebDriverWait(driver, timeout).until(EC.presence_of_all_elements_located((By.XPATH, xpath)))
        for e in elems:
            try:
                if e.is_displayed():
                    return e
            except Exception:
                continue
    except Exception:
        pass
    try:
        elems = driver.find_elements(By.XPATH, '//div[@contenteditable="true"]')
        for e in elems:
            try:
                if e.is_displayed():
                    return e
            except Exception:
                continue
    except Exception:
        pass
    return None

def focus_and_place_caret_at_end(driver: webdriver.Chrome, el):
    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
        try:
            rect = driver.execute_script("return arguments[0].getBoundingClientRect();", el)
            cx = rect.get('width', 0) / 2
            cy = rect.get('height', 0) / 2
            ActionChains(driver).move_to_element_with_offset(el, cx, cy).click().perform()
        except Exception:
            try:
                el.click()
            except Exception:
                driver.execute_script("arguments[0].click();", el)
        sleep(0.08)
        js = """
        const el = arguments[0];
        el.focus();
        const range = document.createRange();
        range.selectNodeContents(el);
        range.collapse(false);
        const sel = window.getSelection();
        sel.removeAllRanges();
        sel.addRange(range);
        """
        driver.execute_script(js, el)
        sleep(0.08)
        return True
    except Exception:
        try:
            driver.execute_script("arguments[0].focus();", el)
            sleep(0.05)
            return True
        except Exception:
            return False

def enviar_mensaje(driver: webdriver.Chrome, mensaje: str):
    try:
        msg_box = find_message_box(driver, timeout=8)
        if not msg_box:
            print("No se encontró el área de mensaje.")
            return
        focus_and_place_caret_at_end(driver, msg_box)
        try:
            msg_box.send_keys(mensaje)
            sleep(0.12)
            msg_box.send_keys(Keys.ENTER)
            print("Mensaje enviado (send_keys).")
            sleep(T_SHORT)
            return
        except WebDriverException as e_send:
            err = str(e_send).lower()
            if ('bmp' in err and 'only supports characters' in err) or 'invalid argument' in err or 'unknown error' in err:
                if pyperclip:
                    try:
                        pyperclip.copy(mensaje)
                        focus_and_place_caret_at_end(driver, msg_box)
                        ActionChains(driver).key_down(Keys.CONTROL).send_keys('v').key_up(Keys.CONTROL).perform()
                        sleep(0.12)
                        ActionChains(driver).send_keys(Keys.ENTER).perform()
                        print("Mensaje enviado (clipboard).")
                        sleep(T_SHORT)
                        return
                    except Exception as ex_clip:
                        print("Fallback clipboard falló:", ex_clip)
            try:
                safe = mensaje.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n")
                js = "arguments[0].focus(); arguments[0].innerText = arguments[1]; arguments[0].dispatchEvent(new InputEvent('input',{bubbles:true}));"
                driver.execute_script(js, msg_box, safe)
                sleep(0.12)
                msg_box.send_keys(Keys.ENTER)
                print("Mensaje enviado (JS injection).")
                sleep(T_SHORT)
                return
            except Exception as ex_js:
                print("Fallback JS falló:", ex_js)
                return
    except Exception as ex:
        print("Error general enviando mensaje:", ex)

def click_attach_button(driver):
    # Reintenta hasta 3 veces; si el click normal queda interceptado por un overlay
    # (típico al enviar varios archivos seguidos), cae a click por JavaScript.
    for intento in range(3):
        try:
            attach_btn = WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.XPATH, '//span[@data-icon="plus-rounded"]'))
            )
            try:
                attach_btn.click()
            except Exception:
                # click interceptado / no clickable → forzar por JS
                driver.execute_script("arguments[0].click();", attach_btn)
            sleep(0.9)
            return True
        except Exception as e:
            print(f"[adjuntar] intento {intento+1}/3 falló: {e}")
            sleep(1.5)  # dar tiempo a que el overlay del envío anterior desaparezca
    print("No se pudo hacer click en el botón Adjuntar tras 3 intentos.")
    try:
        driver.save_screenshot('adjuntar_fail.png')
    except Exception:
        pass
    return False

def click_documentos(driver):
    try:
        doc_btn = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, '//span[@data-icon="document-filled-refreshed"]'))
        )
        doc_btn.click()
        sleep(0.7)
        return True
    except Exception as e:
        print("No se encontró el botón Documentos:", e)
        return False

def click_media(driver):
    try:
        media_btn = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, '//span[@data-icon="media-filled-refreshed"]'))
        )
        media_btn.click()
        sleep(0.7)
        return True
    except Exception as e:
        print("No se encontró el botón Fotos y videos:", e)
        return False

def find_file_input_by_position(driver, tipo="documento", timeout=8):
    end_time = time.time() + timeout
    while time.time() < end_time:
        inputs = driver.find_elements(By.XPATH, '//input[@type="file"]')
        if tipo == "media" and len(inputs) >= 2:
            if inputs[1].is_enabled():
                return inputs[1]
        elif tipo == "documento" and len(inputs) >= 1:
            if inputs[0].is_enabled():
                return inputs[0]
        sleep(0.2)
    print(f"No se encontró input para cargar archivo: {tipo}")
    return None

def tipo_archivo(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in MEDIA_EXTS:
        return "media"
    if ext in DOC_EXTS:
        return "documento"
    return None

def find_file_input_by_accept(driver, tipo="documento", timeout=8):
    """Busca el <input type=file> correcto por su atributo `accept` (robusto ante
    cambios de los íconos del submenú de WhatsApp Web):
      - media: input cuyo accept incluye image/video.
      - documento: input que NO restringe a image/video (accept '*' o vacío).
    """
    end_time = time.time() + timeout
    while time.time() < end_time:
        inputs = driver.find_elements(By.XPATH, '//input[@type="file"]')
        for inp in inputs:
            try:
                accept = (inp.get_attribute("accept") or "").lower()
            except Exception:
                accept = ""
            es_media = ("image" in accept) or ("video" in accept)
            if tipo == "media" and es_media:
                return inp
            if tipo == "documento" and not es_media:
                return inp
        sleep(0.3)
    return None

def _click_menu_por_texto(driver, textos, timeout=6):
    """Hace clic en una opción del menú de adjuntar por su TEXTO visible (robusto a
    cambios de íconos). Usa click por JS para evitar intercepciones. True si clicó."""
    fin = time.time() + timeout
    while time.time() < fin:
        for t in textos:
            try:
                els = driver.find_elements(By.XPATH, f'//*[normalize-space(text())="{t}"]')
                for el in els:
                    try:
                        if el.is_displayed():
                            driver.execute_script("arguments[0].click();", el)
                            return True
                    except Exception:
                        continue
            except Exception:
                continue
        sleep(0.3)
    return False


def enviar_archivo(driver, archivo_path):
    tipo = tipo_archivo(archivo_path)
    if tipo not in ("media", "documento"):
        print("Tipo de archivo no soportado:", archivo_path)
        return
    print(f"Detectado {tipo}:", archivo_path)
    # Abrir el menú de adjuntar (botón '+').
    if not click_attach_button(driver):
        print("No se pudo abrir el menú de adjuntar.")
        return
    sleep(1.0)
    # WhatsApp Web solo expone el input correcto tras elegir la opción del menú por TEXTO
    # (los íconos data-icon del submenú cambian; el texto es estable). Para 'media' el input
    # image/* ya suele estar; para 'documento' hay que abrir "Documento" para que aparezca.
    if tipo == "documento":
        if _click_menu_por_texto(driver, ["Documento", "Documentos", "Document"]):
            sleep(1.0)
        else:
            print("[adjuntar] no se encontró la opción 'Documento' en el menú.")
    else:
        _click_menu_por_texto(driver, ["Fotos y videos", "Fotos y vídeos", "Photos & videos", "Fotos"])
        sleep(0.6)
    # DIAGNÓSTICO: listar los <input type=file> y su accept.
    try:
        _dbg = driver.find_elements(By.XPATH, '//input[@type="file"]')
        _accepts = [(i, (e.get_attribute("accept") or "")[:60]) for i, e in enumerate(_dbg)]
        print(f"[adjuntar][diag] {len(_dbg)} input(s) file: {_accepts}")
    except Exception:
        pass
    # Selección por `accept` (robusto); fallback por posición.
    inp = find_file_input_by_accept(driver, tipo=tipo)
    if not inp:
        inp = find_file_input_by_position(driver, tipo=tipo)
    if not inp:
        print("No se encontró input para cargar archivo.")
        return

    inp.send_keys(archivo_path)
    print("Archivo cargado:", archivo_path)
    sleep(3)

    actions = ActionChains(driver)
    actions.send_keys(Keys.ENTER)
    actions.perform()
    print("Simulación de tecla ENTER para enviar.")
    sleep(3)

def main():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
    client = gspread.authorize(creds)

    pedidos_ss = client.open_by_key(SPREADSHEET_ID_PEDIDOS)
    if SHEET_NAME_PEDIDOS not in [ws.title for ws in pedidos_ss.worksheets()]:
        print("Hoja de pedidos no encontrada.")
        return
    sheet_pedidos = pedidos_ss.worksheet(SHEET_NAME_PEDIDOS)
    pedidos_rows = sheet_pedidos.get_all_values()

    # Asegurar columna ENVIADO_WA y obtener su índice
    sent_col = ensure_sent_column(sheet_pedidos)

    sheet_tel = client.open_by_key(SPREADSHEET_ID_TELEFONOS).worksheet(SHEET_NAME_TELEFONOS)
    tel_rows = sheet_tel.get_all_values()

    sheet_msg = client.open_by_key(SPREADSHEET_ID_TELEFONOS).worksheet(SHEET_NAME_MENSAJE)
    mensajes = obtener_mensajes(sheet_msg)

    enviados_pedidos = []
    enviados_catalogo = []
    errores_telefono = []
    contactos_no_validos = []
    enviados_clientes = set()

    driver = None
    try:
        print("Iniciando Chrome con perfil fallback.")
        os.makedirs(FALLBACK_PROFILE_DIR, exist_ok=True)
        driver = iniciar_driver(FALLBACK_PROFILE_DIR, "Default")

        driver.get("https://web.whatsapp.com/")
        print("Abre WhatsApp Web y escanea QR si corresponde.")
        sleep(T_CHAT_LOAD + 3)

        # Recorremos con índice para poder escribir en la fila correcta
        for row_idx, row in enumerate(pedidos_rows[1:], start=2):
            fecha = row[0] if len(row) > 0 else ""
            tienda = row[1] if len(row) > 1 else ""
            estado = row[9].strip().lower() if len(row) > 9 else ""
            if not fecha or not tienda:
                continue

            # Comprobación persistente: si ya tiene valor en ENVIADO_WA saltar
            try:
                sent_val = sheet_pedidos.cell(row_idx, sent_col).value or ""
            except Exception:
                sent_val = ""
            if sent_val and sent_val.strip():
                print(f"Fila {row_idx}: {tienda} ya marcado como enviado ({sent_val}), saltando...")
                enviados_clientes.add(tienda)
                continue

            # No reenviar si ya en memoria (por seguridad)
            if tienda in enviados_clientes:
                print(f"Ya se envió mensaje a {tienda} en esta ejecución, saltando...")
                continue

            try:
                if datetime.strptime(fecha.split()[0], "%d/%m/%Y").date() != datetime.now().date():
                    continue
            except Exception:
                continue
            if estado not in ["pedido", "revisara el catalogo"]:
                continue
            telefono = buscar_telefono(tienda, tel_rows)
            if telefono:
                if telefono and not telefono.startswith('+'):
                    telefono = '+' + telefono
                print(f"\nEnviando a {tienda} -> {telefono}")

                chat_status = abrir_chat(driver, telefono)

                if chat_status == 'invalido':
                    print(f"Teléfono no válido para {tienda} ({telefono}), notificando por Telegram.")
                    contactos_no_validos.append(tienda)
                    errores_telefono.append((tienda, telefono))
                    enviar_reporte_telegram(
                        TELEGRAM_TOKEN, TELEGRAM_CHAT_ID,
                        f"*Contacto no válido*: {tienda} ({telefono})"
                    )
                    # ya intentamos cerrar el modal dentro de abrir_chat, continuar
                    continue  # Saltar al siguiente contacto

                elif chat_status != 'ok':
                    print(f"No se pudo cargar el chat para {tienda} ({telefono}), notificando por Telegram.")
                    errores_telefono.append((tienda, telefono))
                    enviar_reporte_telegram(
                        TELEGRAM_TOKEN, TELEGRAM_CHAT_ID,
                        f"*Error cargando chat*: {tienda} ({telefono})"
                    )
                    continue

                sleep(10)  # Espera antes de enviar el primer mensaje

                error_envio = False
                for m in mensajes:
                    try:
                        enviar_mensaje(driver, m)
                        sleep(0.6)
                    except Exception as e:
                        print(f"Error enviando mensaje a {tienda}: {e}")
                        error_envio = True
                for media_name in IMAGENES:
                    resolved = resolve_media_path(media_name)
                    if not resolved:
                        print("Archivo no encontrado para:", media_name)
                        continue
                    try:
                        enviar_archivo(driver, resolved)
                        sleep(2)
                    except Exception as e:
                        print(f"Error enviando archivo a {tienda}: {e}")
                        error_envio = True
                sleep(60)
                if estado == "pedido":
                    enviados_pedidos.append(tienda)
                elif estado == "revisara el catalogo":
                    enviados_catalogo.append(tienda)
                if error_envio:
                    errores_telefono.append((tienda, telefono))
                else:
                    # Marcamos como enviado en la hoja con timestamp
                    try:
                        ts = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                        sheet_pedidos.update_cell(row_idx, sent_col, ts)
                        print(f"Marcado ENVIADO_WA para fila {row_idx} ({tienda}) = {ts}")
                    except Exception as e_upd:
                        print(f"No se pudo marcar ENVIADO_WA para {tienda}: {e_upd}")
                enviados_clientes.add(tienda)
            else:
                print("No se encontró teléfono para:", tienda)
                errores_telefono.append((tienda, "No encontrado"))

        print("\nProceso completado. Preparando cierre/espera según configuración...")

        # Construir y enviar reporte por Telegram
        reporte = "*Resumen de Envío WhatsApp*\n\n"
        reporte += "*Pedidos:*\n"
        for nombre in enviados_pedidos:
            reporte += f"- {nombre}\n"
        reporte += f"Total Pedidos: {len(enviados_pedidos)}\n\n"
        reporte += "*Revisarán el Catálogo:*\n"
        for nombre in enviados_catalogo:
            reporte += f"- {nombre}\n"
        reporte += f"Total Catálogo: {len(enviados_catalogo)}\n\n"
        if errores_telefono:
            reporte += "*Errores de teléfono:*\n"
            for nombre, tel in errores_telefono:
                reporte += f"- {nombre}: {tel}\n"
        else:
            reporte += "Sin errores de teléfono.\n"
        if contactos_no_validos:
            reporte += "\n*Contactos no válidos:*\n"
            for nombre in contactos_no_validos:
                reporte += f"- {nombre}\n"
        enviar_reporte_telegram(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, reporte)

    except Exception as e:
        print("Error en ejecución principal:", e)
    finally:
        try:
            if driver:
                if KEEP_BROWSER_OPEN:
                    print("KEEP_BROWSER_OPEN=True -> manteniendo navegador abierto (Ctrl+C para cerrar).")
                    try:
                        while True:
                            sleep(60)
                    except KeyboardInterrupt:
                        print("Ctrl+C detectado. Cerrando driver...")
                        try:
                            driver.quit()
                        except Exception:
                            pass
                else:
                    secs = WAIT_BEFORE_CLOSE_SECS if isinstance(WAIT_BEFORE_CLOSE_SECS, int) else 0
                    if secs > 0:
                        print(f"Esperando {secs} segundos antes de cerrar Chrome...")
                        try:
                            interval = 60
                            remaining = secs
                            while remaining > 0:
                                m = remaining // 60
                                s = remaining % 60
                                print(f" - Cerrando en {m}m {s}s ... (Ctrl+C para cerrar antes)")
                                sleep(interval if remaining >= interval else remaining)
                                remaining -= interval
                        except KeyboardInterrupt:
                            print("Interrupción por usuario. Cerrando ahora.")
                    try:
                        driver.quit()
                        print("Chrome cerrado (driver.quit()).")
                    except Exception as e_q:
                        print("Error cerrando Chrome:", e_q)
        except Exception as e_quit:
            print("Error en rutina final:", e_quit)

if __name__ == "__main__":
    main()