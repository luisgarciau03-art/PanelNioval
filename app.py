"""
Panel Principal NIOVAL
Dashboard centralizado: Prospectos + Seguimiento
Deploy: Railway  |  Auth: GOOGLE_CREDENTIALS_JSON env var o archivo .json local
"""

from flask import Flask, jsonify, render_template_string, request, session
import secrets, threading
try:
    import googlemaps
    GMAPS_OK = True
except ImportError:
    GMAPS_OK = False
import gspread
import gspread.utils as gsu
from gspread.exceptions import WorksheetNotFound
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import os, json, time, io, base64, re, hmac, tempfile, subprocess, requests as req_lib
import unicodedata  # normalizar nombres de ciudad (Plan 1)
from datetime import datetime
from collections import Counter, defaultdict
import traceback

import nucleo_catalogo as nc  # lógica pura de la cola de envíos de catálogo (Plan 3)

app = Flask(__name__)
app.json.sort_keys = False

# ─── GUARDAS DE ARRANQUE (fail-closed) ───────────────────────────────────────
# Sin secretos la app NO arranca. Un despliegue mal configurado revienta aquí,
# ruidosamente, en vez de publicar el panel abierto. Bypass explícito para
# desarrollo local y tests: PANEL_AUTH_DESACTIVADA=1.
# Lectura directa (no vía _auth_desactivada()): esta guarda corre antes de que
# la función se defina más abajo; llamarla aquí sería un NameError. Es la
# única lectura directa de la variable en todo el archivo.
if os.environ.get('PANEL_AUTH_DESACTIVADA') != '1':
    if not os.environ.get('PANEL_DASHBOARD_TOKEN'):
        raise RuntimeError(
            'PANEL_DASHBOARD_TOKEN no está definida. El panel expone datos de '
            'clientes: no arranca sin token. Defínela en el entorno, o pon '
            'PANEL_AUTH_DESACTIVADA=1 si de verdad quieres el panel abierto.')
    if not os.environ.get('SECRET_KEY'):
        raise RuntimeError(
            'SECRET_KEY no está definida. Con varios workers de gunicorn una '
            'clave aleatoria por worker rompe las cookies de sesión de forma '
            'intermitente. Genera una fija y ponla en el entorno.')

app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(16))
# Cookie de sesión endurecida (el panel corre tras TLS).
app.config.update(SESSION_COOKIE_SECURE=True, SESSION_COOKIE_SAMESITE='Lax', SESSION_COOKIE_HTTPONLY=True)


# ─── AUTENTICACIÓN DEL PANEL (fail-closed) ───────────────────────────────────
# El panel exige PANEL_DASHBOARD_TOKEN en TODAS las rutas (header
# X-Dashboard-Token, ?token=, o cookie de sesión tras el primer acceso con
# ?token=). Si la variable falta, la app no arranca (ver guardas de arranque).
# Único bypass, explícito y ruidoso: PANEL_AUTH_DESACTIVADA=1 para desarrollo
# local y para la suite de tests. El default NUNCA abre.
# WORKER_TOKEN (a diferencia de sus dos hermanos, PANEL_DASHBOARD_TOKEN y
# SECRET_KEY) no tiene guarda de arranque a propósito: el heartbeat es
# telemetría, no un dato de cliente, y su ausencia falla cerrado en la propia
# ruta (401) en vez de bloquear el arranque de todo el panel.
_RUTAS_EXENTAS_AUTH = ('/api/catalogo/heartbeat',)  # el worker usa su propio WORKER_TOKEN


def _auth_desactivada() -> bool:
    """True solo si el operador desactivó la auth a propósito."""
    return os.environ.get('PANEL_AUTH_DESACTIVADA') == '1'


@app.before_request
def _requiere_token_panel():
    if _auth_desactivada():
        return
    path = request.path or ''
    if path in _RUTAS_EXENTAS_AUTH:
        return
    token = os.environ.get('PANEL_DASHBOARD_TOKEN')
    if not token:
        return jsonify({'ok': False, 'error': 'no autorizado'}), 401
    provisto = (request.headers.get('X-Dashboard-Token')
                or request.args.get('token')
                or session.get('dashboard_token'))
    if provisto and hmac.compare_digest(str(provisto), str(token)):
        if request.args.get('token') and hmac.compare_digest(str(request.args.get('token')), str(token)):
            session['dashboard_token'] = token  # recordar para la sesión del navegador
        return
    return jsonify({'ok': False, 'error': 'no autorizado'}), 401


# ─── CONFIG ─────────────────────────────────────────────────────────────────
SHEET_IDS = {
    'ventas':      '1Dlpm6swrNSPnt9L5tQhoi2OMln0bb8bqqgeLACNos98',
    'frecuentes':  '1wgEentS16hJrcf6YdEnSpEBcp4SCBJ9TkOCZY439jV4',  # hoja FRECUENTES dentro del mismo sheet de contactos
    'contactos':   '1wgEentS16hJrcf6YdEnSpEBcp4SCBJ9TkOCZY439jV4',
    'respuestas':  '1U_z1KNqCxSRZVi7wvO2FQH4zIdS_wxuafxj6YHdHEqg',
    'mensajes':    '1oEtAiYaYVdOnEum3tbp_BminBUdj06JzXqJhaOVQFlk',
    'seguimiento': '1i0bWYQG7d5GVvOjuklZRpsg1bQfsScdY0bg7lytMXKM',
    'bruce':       '1i0bWYQG7d5GVvOjuklZRpsg1bQfsScdY0bg7lytMXKM',  # worksheet PROSPECTOS BRUCE dentro del mismo sheet
}
# GIDs directos de cada hoja (más confiable que nombres)
SHEET_GIDS = {
    'ventas':      1268382090,  # Hoja "Ventas"
    'frecuentes':  1061706533,   # hoja FRECUENTES en spreadsheet contactos
    'contactos':   823047163,
    'respuestas':  1343998886,
    'mensajes':    0,
    'seguimiento': 258325319,
}

_cache: dict = {}
CACHE_TTL = 300

# La cache se muta desde el hilo daemon del importador (_exportar_a_sheets) a la
# vez que los hilos de peticion. Con --workers 2 cada proceso era monohilo para
# peticiones y la carrera era estrecha; con un worker y 4 hilos deja de serlo.
# `if key in _cache` seguido de `_cache[key]` es un check-then-act sin proteger.
# RLock y no Lock a proposito: los helpers no se anidan hoy, pero si alguno
# llegara a componer a otro, un Lock simple se autobloquearia en silencio.
_cache_lock = threading.RLock()

# Los clientes perezosos (_gs_client, _drive_service, _pago_folder_id) eran
# seguros por construccion cuando cada worker atendia una peticion a la vez. Con
# --threads 4 dos peticiones en frio pueden pasar la comprobacion de None a la
# vez y autenticarse dos veces contra Google.
_clientes_lock = threading.Lock()


def _cache_get(clave):
    """Valor cacheado o None. Devuelve la tupla (dato, ts) tal cual la guardo."""
    with _cache_lock:
        return _cache.get(clave)


def _cache_set(clave, valor):
    with _cache_lock:
        _cache[clave] = valor


def _cache_pop(clave):
    with _cache_lock:
        return _cache.pop(clave, None)


def _cache_clear():
    with _cache_lock:
        _cache.clear()
_gs_client = None
_drive_service = None
_pago_folder_id = None
PAGO_FOLDER_NAME = 'NIOVAL_PAGOS'

# ─── GOOGLE SHEETS ───────────────────────────────────────────────────────────
def get_gs_client():
    global _gs_client
    if _gs_client:
        return _gs_client
    with _clientes_lock:
        if _gs_client:          # otro hilo lo construyo mientras esperabamos
            return _gs_client
        return _construir_gs_client()


def _construir_gs_client():
    global _gs_client
    scopes = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive',
    ]
    creds_json = os.environ.get('GOOGLE_CREDENTIALS_JSON')
    if creds_json:
        info = json.loads(creds_json)
        creds = Credentials.from_service_account_info(info, scopes=scopes)
    else:
        creds_file = os.environ.get('GOOGLE_CREDENTIALS_FILE', 'bubbly-subject-412101-c969f4a975c5.json')
        creds = Credentials.from_service_account_file(creds_file, scopes=scopes)
    _gs_client = gspread.authorize(creds)
    return _gs_client


def get_drive_service():
    global _drive_service
    if _drive_service:
        return _drive_service
    with _clientes_lock:
        if _drive_service:
            return _drive_service
        return _construir_drive_service()


def _construir_drive_service():
    global _drive_service
    scopes = [
        'https://www.googleapis.com/auth/drive',
        'https://www.googleapis.com/auth/spreadsheets',
    ]
    creds_json = os.environ.get('GOOGLE_CREDENTIALS_JSON')
    if creds_json:
        info = json.loads(creds_json)
        creds = Credentials.from_service_account_info(info, scopes=scopes)
    else:
        creds_file = os.environ.get('GOOGLE_CREDENTIALS_FILE', 'bubbly-subject-412101-c969f4a975c5.json')
        creds = Credentials.from_service_account_file(creds_file, scopes=scopes)
    _drive_service = build('drive', 'v3', credentials=creds)
    return _drive_service


def get_pago_folder_id():
    """Obtiene la carpeta NIOVAL_PAGOS desde env var (carpeta compartida del usuario)."""
    global _pago_folder_id
    if _pago_folder_id:
        return _pago_folder_id
    with _clientes_lock:
        if _pago_folder_id:
            return _pago_folder_id
        return _construir_pago_folder_id()


def _construir_pago_folder_id():
    global _pago_folder_id
    # Leer desde variable de entorno (carpeta de Drive del usuario compartida con la cuenta de servicio)
    folder_id = os.environ.get('PAGO_FOLDER_ID', '').strip()
    if folder_id:
        _pago_folder_id = folder_id
        print(f'[Drive] Carpeta PAGO desde env: {_pago_folder_id}')
        return _pago_folder_id
    raise ValueError(
        'PAGO_FOLDER_ID no configurado. '
        'Crea una carpeta en tu Google Drive, compártela con '
        'maps-905@bubbly-subject-412101.iam.gserviceaccount.com (Editor) '
        'y agrega el ID de la carpeta como variable PAGO_FOLDER_ID en Railway.'
    )


def get_worksheet(key: str):
    """Obtiene el worksheet correcto por GID, con fallback a nombre y primera hoja."""
    client = get_gs_client()
    sp = client.open_by_key(SHEET_IDS[key])
    gid = SHEET_GIDS.get(key)
    # 1. Por GID
    if gid is not None:
        for ws in sp.worksheets():
            if ws.id == gid:
                return ws
    # 2. Por nombre
    NAMES = {
        'ventas': 'Ventas', 'frecuentes': 'FRECUENTES',
        'contactos': 'LISTA DE CONTACTOS',
        'respuestas': 'Respuestas de formulario 1',
        'mensajes': 'Mensajes', 'seguimiento': 'Seguimiento',
    }
    name = NAMES.get(key)
    if name:
        try:
            return sp.worksheet(name)
        except Exception:
            pass
    # 3. Primera hoja
    return sp.get_worksheet(0)


def values_to_records(rows: list) -> list:
    """Convierte lista de listas (get_all_values) en lista de dicts."""
    if not rows or len(rows) < 2:
        return []
    headers = [str(h).strip() for h in rows[0]]
    records = []
    for sheet_row, row in enumerate(rows[1:], start=2):  # row 1 = header
        if not any(str(c).strip() for c in row):
            continue
        padded = list(row) + [''] * (len(headers) - len(row))
        r = {headers[i]: str(padded[i]).strip() for i in range(len(headers))}
        r['_row'] = sheet_row  # número de fila real en la hoja (para updates)
        records.append(r)
    return records


def get_data(key: str, force: bool = False) -> list:
    now = time.time()
    entrada = None if force else _cache_get(key)
    if entrada is not None:
        data, ts = entrada
        if now - ts < CACHE_TTL:
            return data
    try:
        ws = get_worksheet(key)
        rows = ws.get_all_values()
        data = values_to_records(rows)
        _cache_set(key, (data, now))
        print(f"[OK] {key} -> {len(data)} filas desde '{ws.title}' (gid={ws.id})")
        return data
    except Exception as e:
        print(f"[ERROR] get_data({key}): {e}")
        traceback.print_exc()
        entrada = _cache_get(key)
        if entrada is not None:
            return entrada[0]
        return []


# GIDs de todas las hojas de respuestas a combinar
_RESPUESTAS_GIDS = [1343998886]  # Respuestas de formulario 1

def get_all_respuestas(force: bool = False) -> list:
    """Lee Respuestas de formulario 1 + Bruce FORMS y los combina en un dataset unificado."""
    cache_key = 'all_respuestas'
    now = time.time()
    entrada = None if force else _cache_get(cache_key)
    if entrada is not None:
        data, ts = entrada
        if now - ts < CACHE_TTL:
            return data
    try:
        client = get_gs_client()
        sp = client.open_by_key(SHEET_IDS['respuestas'])
        all_records = []
        gid_set = set(_RESPUESTAS_GIDS)
        for ws in sp.worksheets():
            if ws.id in gid_set:
                try:
                    rows = ws.get_all_values()
                    records = values_to_records(rows)
                    for r in records:
                        r['_sheet'] = ws.title
                    all_records.extend(records)
                    print(f"[respuestas] '{ws.title}' gid={ws.id}: {len(records)} filas")
                except Exception as e:
                    print(f"[respuestas] Error leyendo '{ws.title}': {e}")
        # Normalizar: asegurar que todas las filas tengan las mismas keys públicas
        all_keys: set = set()
        for r in all_records:
            all_keys.update(k for k in r.keys() if not k.startswith('_'))
        for r in all_records:
            for k in all_keys:
                if k not in r:
                    r[k] = ''
        _cache_set(cache_key, (all_records, now))
        print(f"[respuestas] TOTAL combinado: {len(all_records)} filas")
        return all_records
    except Exception as e:
        print(f"[ERROR] get_all_respuestas: {e}")
        traceback.print_exc()
        entrada = _cache_get(cache_key)
        if entrada is not None:
            return entrada[0]
        return []


@app.route('/api/debug')
def api_debug():
    """Lista todas las hojas disponibles en cada spreadsheet"""
    result = {}
    for key, sid in SHEET_IDS.items():
        try:
            client = get_gs_client()
            sp = client.open_by_key(sid)
            result[key] = [{'title': ws.title, 'id': ws.id, 'rows': ws.row_count} for ws in sp.worksheets()]
        except Exception as e:
            result[key] = {'error': str(e)}
    return jsonify(result)


@app.route('/api/debug/respuestas')
def api_debug_respuestas():
    """Muestra headers y conteo de cada hoja de respuestas incluida en el dataset."""
    try:
        client = get_gs_client()
        sp = client.open_by_key(SHEET_IDS['respuestas'])
        gid_set = set(_RESPUESTAS_GIDS)
        info = []
        for ws in sp.worksheets():
            if ws.id in gid_set:
                rows = ws.get_all_values()
                headers = rows[0] if rows else []
                info.append({
                    'title': ws.title, 'gid': ws.id,
                    'total_rows': len(rows) - 1,
                    'headers': headers[:30],
                })
        data = get_all_respuestas(force=True)
        return jsonify({'hojas': info, 'total_combinado': len(data)})
    except Exception as e:
        return jsonify({'error': str(e)})


@app.route('/api/test/<key>')
def api_test(key):
    """Test directo de una hoja: muestra primeras 3 filas y encabezados"""
    if key not in SHEET_IDS:
        return jsonify({'error': 'key no válido'}), 400
    try:
        ws = get_worksheet(key)
        rows = ws.get_all_values()
        headers = rows[0] if rows else []
        sample = rows[1:4] if len(rows) > 1 else []
        records = values_to_records(rows)
        return jsonify({
            'worksheet': ws.title,
            'gid': ws.id,
            'total_rows_raw': len(rows),
            'total_records': len(records),
            'headers': headers,
            'sample': sample,
        })
    except Exception as e:
        return jsonify({'error': str(e)})


def str_val(v) -> str:
    return str(v).strip() if v is not None else ''

# ─── API ENDPOINTS ───────────────────────────────────────────────────────────
@app.route('/api/refresh', methods=['POST'])
def api_refresh():
    key = request.json.get('key', 'all')
    if key == 'all':
        _cache_clear()
    else:
        _cache_pop(key)
        if key == 'respuestas':
            _cache_pop('all_respuestas')
    return jsonify({'ok': True})


@app.route('/api/ventas/buscar-imagen')
def buscar_imagen_drive():
    """Busca en Drive un archivo por nombre exacto y devuelve su URL."""
    nombre = request.args.get('nombre', '').strip()
    if not nombre:
        return jsonify({'encontrado': False})
    try:
        drive = get_drive_service()
        nombre_safe = nombre.replace("'", "\\'")
        q = f"name='{nombre_safe}' and trashed=false"
        results = drive.files().list(q=q, fields='files(id,name,mimeType)', pageSize=1).execute()
        files = results.get('files', [])
        if files:
            fid = files[0]['id']
            # Hacer público si no lo es
            try:
                drive.permissions().create(fileId=fid, body={'type': 'anyone', 'role': 'reader'}).execute()
            except Exception:
                pass
            url = f'https://drive.google.com/file/d/{fid}/view'
            thumb = f'https://drive.google.com/thumbnail?id={fid}&sz=w400'
            return jsonify({'encontrado': True, 'url': url, 'thumb': thumb, 'file_id': fid})
        return jsonify({'encontrado': False})
    except Exception as e:
        return jsonify({'encontrado': False, 'error': str(e)})


@app.route('/api/ventas/update-pago-url', methods=['POST'])
def update_pago_url():
    """Actualiza la celda PAGO con una URL ya existente en Drive."""
    try:
        num_factura = request.form.get('num_factura', '').strip()
        url = request.form.get('url_existente', '').strip()
        if not num_factura or not url:
            return jsonify({'ok': False})
        ws = get_worksheet('ventas')
        rows = ws.get_all_values()
        headers = rows[0] if rows else []
        try:
            col_factura = headers.index('Num Factura') + 1
            col_pago    = headers.index('PAGO') + 1
        except ValueError:
            return jsonify({'ok': False, 'error': 'columnas no encontradas'})
        for i, row in enumerate(rows[1:], start=2):
            if str(row[col_factura - 1]).strip() == num_factura:
                ws.update_cell(i, col_pago, url)
                _cache_pop('ventas')
                return jsonify({'ok': True})
        return jsonify({'ok': False, 'error': 'factura no encontrada'})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/api/ventas/upload-pago', methods=['POST'])
def upload_pago():
    """Sube imagen de comprobante a Drive y actualiza la celda PAGO en el sheet."""
    try:
        num_factura = request.form.get('num_factura', '').strip()
        if not num_factura:
            return jsonify({'ok': False, 'error': 'num_factura requerido'}), 400
        if 'imagen' not in request.files:
            return jsonify({'ok': False, 'error': 'imagen requerida'}), 400

        archivo = request.files['imagen']
        nombre_archivo = f"PAGO_{num_factura}_{archivo.filename}"
        contenido = archivo.read()
        mimetype = archivo.mimetype or 'image/jpeg'

        # 1. Subir a ImgBB (hosting gratuito, evita limite de cuota de Drive)
        imgbb_key = os.environ.get('IMGBB_API_KEY', '').strip()
        if not imgbb_key:
            return jsonify({'ok': False, 'error': 'IMGBB_API_KEY no configurado. Obtén una key gratuita en imgbb.com/api y agrégala en Railway.'}), 500

        img_b64 = base64.b64encode(contenido).decode('utf-8')
        imgbb_resp = req_lib.post(
            'https://api.imgbb.com/1/upload',
            data={'key': imgbb_key, 'image': img_b64, 'name': nombre_archivo},
            timeout=30
        )
        if imgbb_resp.status_code != 200:
            return jsonify({'ok': False, 'error': f'ImgBB error {imgbb_resp.status_code}: {imgbb_resp.text[:200]}'}), 500

        img_data   = imgbb_resp.json().get('data', {})
        url_drive  = img_data.get('url', '')
        url_thumb  = img_data.get('thumb', {}).get('url') or img_data.get('display_url', url_drive)

        # 2. Actualizar celda PAGO en el sheet Ventas
        ws = get_worksheet('ventas')
        rows = ws.get_all_values()
        headers = rows[0] if rows else []

        # Encontrar índices de columnas Num Factura y PAGO
        try:
            col_factura = headers.index('Num Factura') + 1  # 1-based
        except ValueError:
            col_factura = None
        try:
            col_pago = headers.index('PAGO') + 1
        except ValueError:
            col_pago = 13  # columna M por defecto

        fila_actualizada = None
        if col_factura:
            for i, row in enumerate(rows[1:], start=2):
                val = row[col_factura - 1] if len(row) >= col_factura else ''
                if str(val).strip() == num_factura:
                    ws.update_cell(i, col_pago, url_drive)
                    fila_actualizada = i
                    break

        # Invalidar cache
        _cache_pop('ventas')

        return jsonify({
            'ok': True,
            'url': url_drive,
            'thumb': url_thumb,
            'fila': fila_actualizada,
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/api/prospectos/stats')
def api_stats():
    contactos = get_data('contactos')
    respuestas = get_all_respuestas()

    total_contactos = len(contactos)

    # Columnas reales del sheet de respuestas:
    # "Compatible" = Resultado (col S): APROBADO, NEGADO, NO COMPATIBLE, MARCA UNICA
    # "Respondio"  = Estado llamada (col T): Respondio, Buzon, Telefono Incorrecto
    # "Conclusión" = cierre de llamada: Pedido, Revisara el Catalogo, Correo, etc.
    # "Marca temporal" = fecha
    resultados = Counter()
    estados_llamada = Counter()
    conclusiones = Counter()
    por_semana: dict = defaultdict(int)

    for r in respuestas:
        res = str_val(r.get('Compatible', r.get('Resultado', ''))).upper()
        if res:
            resultados[res] += 1

        estado = str_val(r.get('Respondio', r.get('Estado de llamada', ''))).strip()
        if estado:
            estados_llamada[estado] += 1

        conclusion = str_val(r.get('Conclusión', r.get('Conclusion', ''))).strip()
        if conclusion:
            conclusiones[conclusion] += 1

        fecha_str = str_val(r.get('Marca temporal', r.get('Fecha_Hora', '')))
        if fecha_str:
            for fmt in ('%m/%d/%Y', '%d/%m/%Y %H:%M:%S', '%d/%m/%Y', '%Y-%m-%d'):
                try:
                    dt = datetime.strptime(fecha_str[:10], fmt[:10])
                    semana = f"S{dt.isocalendar()[1]:02d}/{dt.year}"
                    por_semana[semana] += 1
                    break
                except:
                    pass

    semanas_sorted = sorted(por_semana.items())[-12:]

    # Ciudades en contactos
    ciudades_contactos = Counter()
    for c in contactos:
        ciudad = str_val(c.get('CIUDAD', c.get('Ciudad', c.get('ciudad', '')))).title()
        if ciudad:
            ciudades_contactos[ciudad] += 1

    return jsonify({
        'total_contactos': total_contactos,
        'total_respuestas': len(respuestas),
        'resultados': dict(resultados),
        'estados_llamada': dict(estados_llamada),
        'conclusiones': dict(conclusiones),
        'por_semana': [{'semana': s, 'total': n} for s, n in semanas_sorted],
        'top_ciudades': ciudades_contactos.most_common(10),
    })


@app.route('/api/prospectos/contactos')
def api_contactos():
    data = get_data('contactos')
    return jsonify(data)


@app.route('/api/prospectos/contactos-pendientes')
def api_contactos_pendientes():
    """Contactos donde la columna RESPUESTA en LISTA DE CONTACTOS está vacía."""
    contactos = get_data('contactos')
    pendientes = []
    for c in contactos:
        respuesta = str(c.get('RESPUESTA', '')).strip()
        if not respuesta:
            pendientes.append(c)
    return jsonify(pendientes)


@app.route('/api/prospectos/respuestas')
def api_respuestas():
    data = get_all_respuestas()
    return jsonify(data)


@app.route('/api/prospectos/ventas')
def api_ventas():
    data = get_data('ventas')
    return jsonify(filter_ventas_cols(data))


@app.route('/api/prospectos/mensajes')
def api_mensajes():
    """Mensajes: una entrada por columna (tipo de mensaje → contenido)."""
    try:
        ws = get_worksheet('mensajes')
        rows = ws.get_all_values()
        if not rows:
            return jsonify([])
        # Primera fila con ≥2 celdas no vacías = encabezados
        header_idx = 0
        for i, row in enumerate(rows):
            if sum(1 for c in row if str(c).strip()) >= 2:
                header_idx = i
                break
        headers = [str(h).strip() for h in rows[header_idx]]
        data_rows = rows[header_idx + 1:]
        # Una entrada por columna
        records = []
        for col_idx, col_name in enumerate(headers):
            if not col_name:
                continue
            # Tomar el primer valor no vacío de las filas de datos
            content = ''
            data_row_num = header_idx + 2  # default: primera fila de datos (1-based)
            for dr_idx, dr in enumerate(data_rows):
                cell = dr[col_idx].strip() if col_idx < len(dr) else ''
                if cell:
                    content = cell
                    data_row_num = header_idx + 2 + dr_idx
                    break
            records.append({
                'Tipo': col_name,
                'Contenido': content,
                '_col': col_idx + 1,
                '_row': data_row_num,
            })
        print(f"[mensajes] {len(records)} columnas desde header_idx={header_idx}")
        return jsonify(records)
    except Exception as e:
        print(f"[mensajes] error: {e}")
        traceback.print_exc()
        return jsonify([])


VENTAS_COLS = ['Fecha', 'Cliente', 'ESQUEMA', 'MES', 'Monto ', 'Monto', 'Envio Costo', 'Num Factura', 'Cotizacion PDF', 'PAGO']

def filter_ventas_cols(data: list) -> list:
    """Devuelve solo las columnas de ventas en el orden exacto definido."""
    result = []
    for row in data:
        clean = {k: row[k] for k in VENTAS_COLS if k in row}
        if any(str(v).strip() for v in clean.values()):
            result.append(clean)
    return result


@app.route('/api/prospectos/frecuentes')
def api_frecuentes():
    data = get_data('frecuentes')
    return jsonify(filter_ventas_cols(data))


@app.route('/api/prospectos/clientes-frecuentes')
def api_clientes_frecuentes():
    """Agrupa ventas por cliente: suma montos, cuenta pedidos, ordena mayor a menor."""
    ventas = get_data('ventas')

    def parse_monto(v):
        try:
            return float(str(v).replace(',', '').replace('$', '').strip() or 0)
        except:
            return 0.0

    clientes: dict = defaultdict(lambda: {
        'total_monto': 0.0,
        'num_pedidos': 0,
        'esquema': '',
        'facturas': [],
        'ultimo_pedido': '',
    })

    for row in ventas:
        cliente = str(row.get('Cliente', '')).strip()
        if not cliente:
            continue
        monto   = parse_monto(row.get('Monto', 0))
        factura = str(row.get('Num Factura', '')).strip()
        fecha   = str(row.get('Fecha', '')).strip()
        esquema = str(row.get('ESQUEMA', '')).strip()

        clientes[cliente]['total_monto']  += monto
        clientes[cliente]['num_pedidos']  += 1
        clientes[cliente]['esquema']       = esquema or clientes[cliente]['esquema']
        if factura:
            clientes[cliente]['facturas'].append(factura)
        if fecha and fecha > clientes[cliente]['ultimo_pedido']:
            clientes[cliente]['ultimo_pedido'] = fecha

    MESES_ES = {
        1:'Enero', 2:'Febrero', 3:'Marzo', 4:'Abril', 5:'Mayo', 6:'Junio',
        7:'Julio', 8:'Agosto', 9:'Septiembre', 10:'Octubre', 11:'Noviembre', 12:'Diciembre'
    }

    def fecha_a_mes(f):
        for fmt in ('%d/%m/%Y', '%m/%d/%Y', '%Y-%m-%d'):
            try:
                dt = datetime.strptime(f[:10], fmt)
                return f"{MESES_ES[dt.month]} {dt.year}"
            except:
                pass
        return f

    result = []
    for nombre, d in clientes.items():
        result.append({
            'Cliente':       nombre,
            'Esquema':       d['esquema'],
            'Pedidos':       d['num_pedidos'],
            'Total Monto':   round(d['total_monto'], 2),
            'Ultimo Pedido': fecha_a_mes(d['ultimo_pedido']) if d['ultimo_pedido'] else '—',
        })

    result.sort(key=lambda x: x['Total Monto'], reverse=True)
    return jsonify(result)


@app.route('/api/prospectos/ventas-dashboard')
def api_ventas_dashboard():
    """Métricas de ventas agrupadas por mes, con desglose por esquema y top clientes."""
    ventas = get_data('ventas')

    def parse_monto(v):
        try:
            return float(str(v).replace(',', '').replace('$', '').strip() or 0)
        except:
            return 0.0

    def parse_fecha(f):
        for fmt in ('%d/%m/%Y', '%m/%d/%Y', '%Y-%m-%d'):
            try:
                return datetime.strptime(str(f).strip()[:10], fmt)
            except:
                pass
        return None

    meses: dict = defaultdict(lambda: {
        'monto': 0.0, 'pedidos': 0,
        'clientes': set(), 'esquemas': defaultdict(float),
    })

    total_general = 0.0
    total_pedidos = 0

    for row in ventas:
        cliente = str(row.get('Cliente', '')).strip()
        monto   = parse_monto(row.get('Monto', 0))
        fecha   = parse_fecha(row.get('Fecha', ''))
        esquema = str(row.get('ESQUEMA', '')).strip() or 'Sin esquema'
        factura = str(row.get('Num Factura', '')).strip()

        if not fecha or not cliente:
            continue

        clave = fecha.strftime('%Y-%m')   # para ordenar
        label = fecha.strftime('%b %Y')    # para mostrar

        meses[clave]['label']    = label
        meses[clave]['monto']   += monto
        meses[clave]['pedidos'] += 1
        meses[clave]['clientes'].add(cliente)
        meses[clave]['esquemas'][esquema] += monto

        total_general += monto
        total_pedidos += 1

    # Convertir sets a listas para JSON
    resultado = []
    for clave in sorted(meses.keys()):
        d = meses[clave]
        resultado.append({
            'clave':         clave,
            'mes':           d['label'],
            'monto':         round(d['monto'], 2),
            'pedidos':       d['pedidos'],
            'clientes':      len(d['clientes']),
            'ticket_prom':   round(d['monto'] / d['pedidos'], 2) if d['pedidos'] else 0,
            'por_esquema':   dict(d['esquemas']),
        })

    mejor_mes = max(resultado, key=lambda x: x['monto']) if resultado else {}

    return jsonify({
        'por_mes':        resultado,
        'total_general':  round(total_general, 2),
        'total_pedidos':  total_pedidos,
        'promedio_mes':   round(total_general / len(resultado), 2) if resultado else 0,
        'mejor_mes':      mejor_mes.get('mes', '—'),
        'mejor_mes_monto': mejor_mes.get('monto', 0),
    })


def _agregar_por_ciudad(contactos, respuestas):
    """Agrega contactos y respuestas por ciudad. Devuelve una lista de dicts.

    Extraida de api_ciudades para que /api/importador/ciudades use exactamente
    la misma cuenta. Dos agregaciones paralelas sobre la misma hoja se separan
    en cuanto alguien toque una: el importador diria 37 contactos donde el
    dashboard dice 38, y nadie sabria cual de las dos miente.
    """

    # Agrupar TODAS las respuestas por tienda (puede haber varias por contacto)
    resp_por_tienda: dict = defaultdict(list)
    for r in respuestas:
        nombre = str_val(r.get('Nombre De la Tienda', r.get('TIENDA', r.get('Tienda', '')))).strip().upper()
        if nombre:
            resp_por_tienda[nombre].append(r)

    def blank_ciudad():
        return {
            'total': 0, 'llamados': 0,
            # Estado de llamada
            'respondio': 0, 'buzon': 0, 'tel_incorrecto': 0,
            # Resultado compatible
            'aprobados': 0, 'negados': 0, 'no_compatible': 0, 'marca_unica': 0,
            # Conclusión
            'pedido': 0, 'catalogo': 0, 'correo': 0,
            'avance': 0, 'continuacion': 0, 'nulo': 0, 'colgo': 0,
        }

    ciudades: dict = defaultdict(blank_ciudad)

    for c in contactos:
        ciudad = str_val(c.get('CIUDAD', c.get('Ciudad', c.get('ciudad', '')))).title().strip()
        if not ciudad:
            ciudad = 'Sin ciudad'
        nombre = str_val(c.get('TIENDA', c.get('Tienda', c.get('Nombre', '')))).strip().upper()
        ciudades[ciudad]['total'] += 1

        for r in resp_por_tienda.get(nombre, []):
            ciudades[ciudad]['llamados'] += 1

            res    = str_val(r.get('Compatible', '')).upper()
            estado = str_val(r.get('Respondio', '')).upper()
            concl  = str_val(r.get('Conclusión', r.get('Conclusion', ''))).lower()

            # Estado de llamada
            if 'BUZON' in estado or 'BUZÓN' in estado:
                ciudades[ciudad]['buzon'] += 1
            elif 'INCORRECTO' in estado:
                ciudades[ciudad]['tel_incorrecto'] += 1
            elif 'RESPONDIO' in estado or 'RESPONDIÓ' in estado:
                ciudades[ciudad]['respondio'] += 1

            # Resultado
            if res == 'APROBADO':      ciudades[ciudad]['aprobados'] += 1
            elif res == 'NEGADO':      ciudades[ciudad]['negados'] += 1
            elif res == 'NO COMPATIBLE': ciudades[ciudad]['no_compatible'] += 1
            elif res == 'MARCA UNICA': ciudades[ciudad]['marca_unica'] += 1

            # Conclusión
            if 'pedido' in concl:          ciudades[ciudad]['pedido'] += 1
            elif 'catalogo' in concl or 'catálogo' in concl: ciudades[ciudad]['catalogo'] += 1
            elif 'correo' in concl:        ciudades[ciudad]['correo'] += 1
            elif 'avance' in concl or 'fecha' in concl: ciudades[ciudad]['avance'] += 1
            elif 'continuacion' in concl or 'continuación' in concl: ciudades[ciudad]['continuacion'] += 1
            elif 'nulo' in concl:          ciudades[ciudad]['nulo'] += 1
            elif 'colgo' in concl or 'colgó' in concl: ciudades[ciudad]['colgo'] += 1

    result = []
    for ciudad, m in ciudades.items():
        interes = round(m['aprobados'] / m['llamados'] * 100, 1) if m['llamados'] > 0 else 0
        result.append({'ciudad': ciudad, **m, 'interes_pct': interes})

    return result


@app.route('/api/prospectos/ciudades')
def api_ciudades():
    result = _agregar_por_ciudad(get_data('contactos'), get_all_respuestas())

    max_total = max((r['total'] for r in result), default=1)
    for r in result:
        r['relevancia'] = round(
            r['interes_pct'] * 1.5 +
            (r['total'] / max_total) * 40 +
            min(r['llamados'] * 2, 20), 1
        )

    result.sort(key=lambda x: x['relevancia'], reverse=True)
    return jsonify(result)


@app.route('/api/seguimiento')
def api_seguimiento():
    data = get_data('seguimiento')
    return jsonify(data)


def _sheet_update_row(ws_key, row_num, fields, cache_key=None):
    """Actualiza celdas de una hoja por nombre de columna."""
    import gspread.utils as gsu
    ws = get_worksheet(ws_key)
    headers = ws.row_values(1)
    updates = []
    for col_name, value in fields.items():
        if col_name in headers:
            col_idx = headers.index(col_name) + 1
            a1 = gsu.rowcol_to_a1(int(row_num), col_idx)
            updates.append({'range': a1, 'values': [[str(value)]]})
    if updates:
        ws.batch_update(updates, value_input_option='USER_ENTERED')
    _cache_pop(cache_key or ws_key)
    return len(updates)


@app.route('/api/seguimiento/update', methods=['POST'])
def api_seguimiento_update():
    body = request.json or {}
    row_num = body.get('_row')
    if not row_num:
        return jsonify({'error': 'Falta _row'}), 400
    fields = {k: v for k, v in body.items() if not k.startswith('_')}
    try:
        n = _sheet_update_row('seguimiento', row_num, fields)
        print(f"[seguimiento] update row={row_num} fields={list(fields.keys())} updated={n}")
        return jsonify({'ok': True, 'updated': n})
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/mensajes/update', methods=['POST'])
def api_mensajes_update():
    body = request.json or {}
    col_num = body.get('_col')
    row_num = body.get('_row')
    contenido = body.get('Contenido', '')
    if not col_num or not row_num:
        return jsonify({'error': 'Falta _col o _row'}), 400
    try:
        import gspread.utils as gsu
        ws = get_worksheet('mensajes')
        a1 = gsu.rowcol_to_a1(int(row_num), int(col_num))
        ws.update(a1, [[str(contenido)]], value_input_option='USER_ENTERED')
        _cache_pop('mensajes')
        print(f"[mensajes] update col={col_num} row={row_num}")
        return jsonify({'ok': True})
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/ventas/stats')
def api_ventas_stats():
    ventas = get_data('ventas')
    if not ventas:
        return jsonify({'total_ventas': 0, 'clientes': 0, 'por_mes': [], 'top_clientes': []})

    claves = list(ventas[0].keys()) if ventas else []

    # Detectar columnas relevantes heurísticamente
    col_cliente = next((k for k in claves if 'cliente' in k.lower() or 'tienda' in k.lower() or 'nombre' in k.lower()), None)
    col_monto = next((k for k in claves if 'monto' in k.lower() or 'total' in k.lower() or 'venta' in k.lower() or 'importe' in k.lower()), None)
    col_fecha = next((k for k in claves if 'fecha' in k.lower() or 'date' in k.lower()), None)

    clientes = Counter()
    por_mes: dict = defaultdict(float)

    for v in ventas:
        if col_cliente:
            cli = str_val(v.get(col_cliente, '')).title()
            if cli:
                clientes[cli] += 1
        if col_fecha:
            fecha_str = str_val(v.get(col_fecha, ''))
            for fmt in ('%d/%m/%Y', '%Y-%m-%d', '%m/%d/%Y'):
                try:
                    dt = datetime.strptime(fecha_str[:10], fmt)
                    mes = dt.strftime('%b %Y')
                    monto = 0
                    if col_monto:
                        try:
                            monto = float(str_val(v.get(col_monto, '0')).replace(',', '').replace('$', ''))
                        except:
                            monto = 1
                    por_mes[mes] += monto or 1
                    break
                except:
                    pass

    return jsonify({
        'total_ventas': len(ventas),
        'clientes': len(clientes),
        'columnas': claves,
        'top_clientes': clientes.most_common(10),
        'por_mes': [{'mes': k, 'total': v} for k, v in sorted(por_mes.items())[-12:]],
    })


# ─── MAIN HTML ──────────────────────────────────────────────────────────────
HTML = r"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Panel NIOVAL</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{--blue:#0047CC;--blue2:#003399;--blue3:#e6f0ff;--green:#00CC47;--orange:#e67e22;--purple:#8e44ad;--red:#e74c3c;--gray:#6c757d}
body{font-family:'Segoe UI',sans-serif;background:#f0f4ff;display:flex;min-height:100vh;color:#222}

/* SIDEBAR */
#sidebar{width:230px;min-height:100vh;background:linear-gradient(180deg,var(--blue2) 0%,var(--blue) 100%);color:#fff;display:flex;flex-direction:column;flex-shrink:0;position:fixed;top:0;left:0;height:100vh;overflow-y:auto;z-index:100}
#sidebar .logo{padding:22px 18px 14px;border-bottom:1px solid rgba(255,255,255,.15);text-align:center}
#sidebar .logo img{height:48px;background:#fff;border-radius:10px;padding:5px}
#sidebar .logo h2{font-size:1.15em;margin-top:8px;font-weight:800;letter-spacing:.5px}
#sidebar .logo p{font-size:.72em;opacity:.75;margin-top:2px}
.nav-group{padding:14px 12px 4px}
.nav-label{font-size:.65em;text-transform:uppercase;letter-spacing:1.5px;opacity:.6;padding:0 8px;margin-bottom:6px}
.nav-item{display:flex;align-items:center;gap:10px;padding:9px 12px;border-radius:10px;cursor:pointer;font-size:.88em;font-weight:500;transition:all .2s;margin-bottom:2px;opacity:.85}
.nav-item:hover{background:rgba(255,255,255,.15);opacity:1}
.nav-item.active{background:rgba(255,255,255,.22);opacity:1;font-weight:700}
.nav-item .icon{font-size:1.1em;width:20px;text-align:center}

/* MAIN */
#main{margin-left:230px;flex:1;display:flex;flex-direction:column;min-height:100vh}
#topbar{background:#fff;padding:14px 28px;border-bottom:1px solid #dde6ff;display:flex;align-items:center;justify-content:space-between;position:sticky;top:0;z-index:50}
#topbar h1{font-size:1.25em;color:var(--blue);font-weight:700}
#topbar .actions{display:flex;gap:10px;align-items:center}
.btn-refresh{background:var(--blue3);border:1px solid var(--blue);color:var(--blue);padding:6px 16px;border-radius:8px;cursor:pointer;font-size:.82em;font-weight:600;transition:all .2s}
.btn-refresh:hover{background:var(--blue);color:#fff}
.badge-cache{font-size:.72em;color:#888;background:#f0f0f0;padding:3px 10px;border-radius:20px}
#content{padding:24px 28px;flex:1}

/* SECTION */
.section{display:none}
.section.active{display:block}

/* CARDS */
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:14px;margin-bottom:22px}
.card{background:#fff;border-radius:14px;padding:18px 16px;box-shadow:0 2px 10px rgba(0,71,204,.08);border-left:4px solid var(--blue);transition:transform .2s}
.card:hover{transform:translateY(-3px)}
.card .label{font-size:.7em;text-transform:uppercase;letter-spacing:.8px;color:#888;margin-bottom:6px}
.card .value{font-size:1.9em;font-weight:800;color:var(--blue)}
.card .sub{font-size:.72em;color:#aaa;margin-top:3px}
.card.green{border-color:var(--green)}.card.green .value{color:var(--green)}
.card.orange{border-color:var(--orange)}.card.orange .value{color:var(--orange)}
.card.red{border-color:var(--red)}.card.red .value{color:var(--red)}
.card.purple{border-color:var(--purple)}.card.purple .value{color:var(--purple)}
.card.gray{border-color:var(--gray)}.card.gray .value{color:var(--gray)}

/* CHARTS */
.charts{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:22px}
.chart-box{background:#fff;border-radius:14px;padding:20px;box-shadow:0 2px 10px rgba(0,71,204,.08)}
.chart-box h3{font-size:.88em;color:var(--blue);margin-bottom:14px;font-weight:700;text-transform:uppercase;letter-spacing:.5px}
.chart-box.full{grid-column:1/-1}
@media(max-width:900px){.charts{grid-template-columns:1fr}}

/* TABLES */
.table-box{background:#fff;border-radius:14px;padding:20px;box-shadow:0 2px 10px rgba(0,71,204,.08);margin-bottom:22px;overflow:hidden}
.table-box h3{font-size:.88em;color:var(--blue);margin-bottom:14px;font-weight:700;text-transform:uppercase;letter-spacing:.5px}
.table-controls{display:flex;gap:10px;margin-bottom:12px;flex-wrap:wrap}
.table-controls input,.table-controls select{padding:7px 12px;border:1px solid #dde;border-radius:8px;font-size:.83em;outline:none;transition:border .2s}
.table-controls input:focus,.table-controls select:focus{border-color:var(--blue)}
.seg-tabs{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:18px}
.seg-tab{padding:8px 18px;border-radius:20px;background:#f1f5f9;color:#475569;cursor:pointer;font-size:.83em;font-weight:600;border:2px solid transparent;transition:all .2s;white-space:nowrap}
.seg-tab:hover{background:#e2e8f0;color:#1e293b}
.seg-tab.active{background:var(--blue);color:#fff;border-color:var(--blue)}
.seg-tab .tab-count{font-size:.75em;opacity:.75;margin-left:3px}
.edit-field-group{display:flex;flex-direction:column;gap:5px}
.edit-field-group label{font-size:.68em;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:.6px;display:flex;align-items:center;gap:4px}
.edit-field-group input,.edit-field-group select,.edit-field-group textarea{padding:9px 12px;border:1.5px solid #e2e8f0;border-radius:10px;font-size:.87em;outline:none;transition:border .2s,box-shadow .2s;width:100%;background:#f8fafc;color:#1e293b}
.edit-field-group input:focus,.edit-field-group select:focus,.edit-field-group textarea:focus{border-color:#0047CC;box-shadow:0 0 0 3px rgba(0,71,204,.1);background:#fff}
.edit-field-group textarea{resize:vertical;min-height:72px;line-height:1.5}
.edit-field-group input[type=date]{color:#0f172a}
.btn-edit-row{padding:4px 11px;border:1.5px solid #0047CC;border-radius:7px;background:#eff6ff;color:#0047CC;cursor:pointer;font-size:.77em;font-weight:700;white-space:nowrap;transition:all .15s}
.btn-edit-row:hover{background:#0047CC;color:#fff;box-shadow:0 2px 8px rgba(0,71,204,.25)}
.color-opt{position:relative;width:30px;height:30px;border-radius:50%;cursor:pointer;transition:transform .15s,border .15s;flex-shrink:0}
.color-opt:hover{transform:scale(1.15)}
.color-opt.selected{transform:scale(1.1)}
.color-legend{font-size:.7em;color:#64748b;display:flex;align-items:center;gap:5px;white-space:nowrap}
#edit-color-picker{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.tbl-wrap{overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:.82em}
th{background:var(--blue);color:#fff;padding:9px 10px;text-align:left;font-weight:600;white-space:nowrap}
td{padding:8px 10px;border-bottom:1px solid #eef;white-space:nowrap;vertical-align:top}
tr:nth-child(even) td{background:#f8fbff}
tr:hover td{background:var(--blue3)}
.tag{display:inline-block;padding:2px 8px;border-radius:20px;font-size:.75em;font-weight:600}
.tag.aprobado{background:#d4edda;color:#155724}
.tag.negado{background:#f8d7da;color:#721c24}
.tag.buzon{background:#fff3cd;color:#856404}
.tag.no-compatible{background:#fde8d8;color:#7b3300}
.tag.marca-unica{background:#e8d5f5;color:#4a1a6e}
.tag.tel-inc{background:#f0f0f0;color:#555}
.tag.colgo{background:#dde;color:#333}
.tag.default{background:#e6f0ff;color:var(--blue)}

/* CIUDADES */
.interes-bar{display:inline-block;background:var(--green);height:8px;border-radius:4px;min-width:4px}

/* LOADING */
.loading{text-align:center;padding:40px;color:#aaa;font-size:.9em}
.spinner{display:inline-block;width:28px;height:28px;border:3px solid #dde;border-top-color:var(--blue);border-radius:50%;animation:spin .8s linear infinite;margin-bottom:10px}
@keyframes spin{to{transform:rotate(360deg)}}

/* EMPTY */
.empty{text-align:center;padding:30px;color:#bbb;font-size:.88em}

/* PAGINATION */
.pagination{display:flex;align-items:center;gap:6px;margin-top:12px;justify-content:flex-end;flex-wrap:wrap}
.pagination button{padding:4px 10px;border:1px solid #dde;border-radius:6px;background:#fff;cursor:pointer;font-size:.8em;color:var(--blue)}
.pagination button.active{background:var(--blue);color:#fff;border-color:var(--blue)}
.pagination button:hover:not(.active){background:var(--blue3)}
.pag-info{font-size:.78em;color:#aaa}

.section-header{font-size:1.05em;font-weight:700;color:var(--blue);margin-bottom:18px;padding-bottom:8px;border-bottom:2px solid var(--blue3)}
.btn-upload-pago{background:var(--blue3);border:1px solid var(--blue);color:var(--blue);padding:3px 9px;border-radius:6px;cursor:pointer;font-size:.75em;font-weight:600;white-space:nowrap;transition:all .2s}
.btn-upload-pago:hover{background:var(--blue);color:#fff}
.bruce-form{background:#f0f4ff;border-radius:12px;padding:18px;margin-bottom:20px;display:grid;grid-template-columns:1fr 1fr;gap:12px}
.bruce-form input,.bruce-form select,.bruce-form textarea{width:100%;padding:9px 12px;border:1.5px solid #c5d8ff;border-radius:8px;font-size:.86em;font-family:inherit;outline:none;transition:border .2s}
.bruce-form input:focus,.bruce-form select:focus,.bruce-form textarea:focus{border-color:var(--blue)}
.bruce-form label{font-size:.72em;font-weight:700;color:var(--blue);text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px;display:block}
.bruce-form .full{grid-column:1/-1}
.bruce-form textarea{resize:vertical;min-height:60px}
.bruce-casilla{cursor:pointer;font-size:1.2em;text-align:center;user-select:none;transition:transform .15s}
.bruce-casilla:hover{transform:scale(1.3)}
.men-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:16px;padding:4px 0}
.men-card{background:#fff;border-radius:12px;border:1px solid #e2e8f0;border-left:4px solid var(--blue);padding:16px 18px;display:flex;flex-direction:column;gap:10px;box-shadow:0 1px 6px rgba(0,71,204,.07)}
.men-card-header{display:flex;align-items:center;justify-content:space-between;gap:8px}
.men-card-tipo{font-size:.8em;font-weight:700;text-transform:uppercase;letter-spacing:.6px;color:var(--blue)}
.men-card-content{font-size:.82em;color:#334155;line-height:1.55;white-space:pre-wrap;max-height:130px;overflow-y:auto;border-top:1px solid #f1f5f9;padding-top:8px;word-break:break-word}
.men-card-empty{font-size:.8em;color:#aaa;font-style:italic;border-top:1px solid #f1f5f9;padding-top:8px}
</style>
</head>
<body>

<!-- SIDEBAR -->
<aside id="sidebar">
  <div class="logo">
    <img src="https://res.cloudinary.com/dipt3jq6r/image/upload/v1764307686/NIOVAL-05_xhfrrh.jpg" alt="NIOVAL" onerror="this.style.display='none'">
    <h2>NIOVAL</h2>
    <p>Panel de Gestión</p>
  </div>

  <div class="nav-group">
    <div class="nav-label">Ventas</div>
    <div class="nav-item" onclick="showSection('frecuentes')">
      <span class="icon">⭐</span> Clientes Frecuentes
    </div>
    <div class="nav-item" onclick="showSection('ventas-dash')">
      <span class="icon">📈</span> Dashboard Ventas
    </div>
    <div class="nav-item" onclick="showSection('ventas')">
      <span class="icon">💰</span> Ventas
    </div>
  </div>

  <div class="nav-group">
    <div class="nav-label">Clientes Prospectos</div>
    <div class="nav-item active" onclick="showSection('dashboard')">
      <span class="icon">📊</span> Dashboard
    </div>
    <div class="nav-item" onclick="showSection('contactos')">
      <span class="icon">📋</span> Lista de Contactos
    </div>
    <div class="nav-item" onclick="showSection('pendientes')">
      <span class="icon">📞</span> Por Llamar
    </div>
    <div class="nav-item" onclick="showSection('ciudades')">
      <span class="icon">🗺️</span> Ciudades por Interés
    </div>
    <div class="nav-item" onclick="showSection('respuestas')">
      <span class="icon">📝</span> Respuestas
    </div>
    <div class="nav-item" onclick="showSection('mensajes')">
      <span class="icon">💬</span> Mensajes
    </div>
    <div class="nav-item" onclick="showSection('catalogo')">
      <span class="icon">📖</span> Envíos Catálogo
      <span id="cat-badge" style="display:none;margin-left:auto;background:#e74c3c;color:#fff;border-radius:10px;padding:1px 7px;font-size:.72em;font-weight:700"></span>
    </div>
  </div>

  <div class="nav-group">
    <div class="nav-label">Seguimiento</div>
    <div class="nav-item" onclick="showSection('seguimiento')">
      <span class="icon">🔄</span> Seguimiento
    </div>
    <div class="nav-item" onclick="showSection('bruce')">
      <span class="icon">🤖</span> Prospectos Bruce
    </div>
  </div>

  <div class="nav-group">
    <div class="nav-label">Herramientas</div>
    <a href="/formulario" target="_blank" style="text-decoration:none">
      <div class="nav-item" style="background:rgba(0,204,71,.2);border:1px solid rgba(0,204,71,.4)">
        <span class="icon">📞</span> Iniciar Llamadas
      </div>
    </a>
    <a href="/importador" target="_blank" style="text-decoration:none">
      <div class="nav-item" style="background:rgba(230,126,34,.2);border:1px solid rgba(230,126,34,.4)">
        <span class="icon">📥</span> Importar Contactos
      </div>
    </a>
  </div>
</aside>

<!-- MAIN -->
<div id="main">
  <div id="topbar">
    <h1 id="topbar-title">📊 Dashboard Prospectos</h1>
    <div class="actions">
      <span class="badge-cache" id="cache-badge">—</span>
      <button class="btn-refresh" onclick="refreshData()">↻ Actualizar</button>
    </div>
  </div>

  <div id="content">

    <!-- ═══ DASHBOARD ═══ -->
    <div class="section active" id="sec-dashboard">
      <div class="cards" id="dash-cards">
        <div class="loading"><div class="spinner"></div><br>Cargando...</div>
      </div>
      <div class="charts">
        <div class="chart-box">
          <h3>📈 Resultados de Llamadas</h3>
          <canvas id="chartResultados" height="180"></canvas>
        </div>
        <div class="chart-box">
          <h3>📅 Contactos por Semana</h3>
          <canvas id="chartSemanas" height="180"></canvas>
        </div>
        <div class="chart-box full">
          <h3>🏙️ Top Ciudades en Lista</h3>
          <canvas id="chartCiudades" height="100"></canvas>
        </div>
      </div>
    </div>

    <!-- ═══ FRECUENTES ═══ -->
    <div class="section" id="sec-frecuentes">
      <div class="cards" id="frec-cards">
        <div class="loading"><div class="spinner"></div><br>Cargando...</div>
      </div>
      <div class="table-box">
        <h3>⭐ Clientes Frecuentes — Orden de Ingreso</h3>
        <div class="table-controls">
          <input type="text" id="frecuentes-search" placeholder="🔍 Buscar..." oninput="filterTable('frecuentes')">
        </div>
        <div class="tbl-wrap" id="frec-top-table"><div class="loading"><div class="spinner"></div></div></div>
        <div class="pagination" id="frec-pag"></div>
      </div>
    </div>

    <!-- ═══ DASHBOARD VENTAS ═══ -->
    <div class="section" id="sec-ventas-dash">
      <div class="cards" id="vdash-cards">
        <div class="loading"><div class="spinner"></div><br>Cargando...</div>
      </div>
      <div class="charts">
        <div class="chart-box full">
          <h3>💰 Facturación Mensual</h3>
          <canvas id="chartVentasMonto" height="90"></canvas>
        </div>
        <div class="chart-box">
          <h3>📦 Pedidos por Mes</h3>
          <canvas id="chartVentasPedidos" height="160"></canvas>
        </div>
        <div class="chart-box">
          <h3>🎯 Ticket Promedio por Mes</h3>
          <canvas id="chartVentasTicket" height="160"></canvas>
        </div>
      </div>
      <div class="table-box">
        <h3>📅 Desglose por Mes</h3>
        <div class="tbl-wrap" id="vdash-table"></div>
      </div>
    </div>

    <!-- ═══ VENTAS ═══ -->
    <div class="section" id="sec-ventas">
      <div class="table-box">
        <h3>💰 Ventas — Orden de Ingreso</h3>
        <div class="table-controls">
          <input type="text" id="ventas-search" placeholder="🔍 Buscar..." oninput="filterTable('ventas')">
          <span id="ventas-count" style="font-size:.8em;color:#888;align-self:center;margin-left:4px"></span>
        </div>
        <div class="tbl-wrap" id="ventas-table"><div class="loading"><div class="spinner"></div></div></div>
        <div class="pagination" id="ventas-pag"></div>
      </div>
    </div>

    <!-- ═══ CONTACTOS ═══ -->
    <div class="section" id="sec-contactos">
      <div class="table-box">
        <h3>📋 Lista de Contactos</h3>
        <div class="table-controls">
          <input type="text" id="contactos-search" placeholder="🔍 Buscar..." oninput="filterTable('contactos')">
          <select id="contactos-ciudad" onchange="filterTable('contactos')">
            <option value="">Todas las ciudades</option>
          </select>
          <select id="contactos-cat" onchange="filterTable('contactos')">
            <option value="">Todas las categorías</option>
          </select>
        </div>
        <div class="tbl-wrap" id="contactos-table"><div class="loading"><div class="spinner"></div></div></div>
        <div class="pagination" id="contactos-pag"></div>
      </div>
    </div>

    <!-- ═══ POR LLAMAR ═══ -->
    <div class="section" id="sec-pendientes">
      <div class="cards" id="pend-cards">
        <div class="loading"><div class="spinner"></div><br>Cargando...</div>
      </div>
      <div class="table-box">
        <h3>📞 Contactos Sin Respuesta — Por Llamar</h3>
        <div class="table-controls">
          <input type="text" id="pendientes-search" placeholder="🔍 Buscar..." oninput="filterTable('pendientes')">
          <select id="pendientes-ciudad" onchange="filterTable('pendientes')">
            <option value="">Todas las ciudades</option>
          </select>
        </div>
        <div class="tbl-wrap" id="pendientes-table"><div class="loading"><div class="spinner"></div></div></div>
        <div class="pagination" id="pendientes-pag"></div>
      </div>
    </div>

    <!-- ═══ CIUDADES ═══ -->
    <div class="section" id="sec-ciudades">
      <div class="table-box">
        <h3>🗺️ Ciudades Ordenadas por Interés</h3>
        <div class="table-controls">
          <input type="text" id="ciudades-search" placeholder="🔍 Buscar ciudad..." oninput="filterCiudades()">
        </div>
        <div class="tbl-wrap" id="ciudades-table"><div class="loading"><div class="spinner"></div></div></div>
      </div>
    </div>

    <!-- ═══ RESPUESTAS ═══ -->
    <div class="section" id="sec-respuestas">
      <div class="table-box">
        <h3>📝 Respuestas — Conclusión Final</h3>
        <div class="table-controls">
          <input type="text" id="resp-search" placeholder="🔍 Buscar..." oninput="filterTable('respuestas')">
          <select id="resp-conclusion" onchange="filterTable('respuestas')">
            <option value="">Todas las conclusiones</option>
          </select>
        </div>
        <div class="tbl-wrap" id="respuestas-table"><div class="loading"><div class="spinner"></div></div></div>
        <div class="pagination" id="respuestas-pag"></div>
      </div>
    </div>

    <!-- ═══ MENSAJES ═══ -->
    <div class="section" id="sec-mensajes">
      <div class="table-box">
        <h3>💬 Mensajes Iniciales</h3>
        <div class="table-controls">
          <input type="text" id="mensajes-search" placeholder="🔍 Buscar mensaje..." oninput="filterMensajes(this.value)">
        </div>
        <div class="tbl-wrap" id="mensajes-table"><div class="loading"><div class="spinner"></div></div></div>
        <div class="pagination" id="mensajes-pag"></div>
      </div>
    </div>

    <!-- ═══ ENVÍOS DE CATÁLOGO (números a corregir) ═══ -->
    <div class="section" id="sec-catalogo">
      <div class="table-box">
        <h3>📖 Envíos de Catálogo — números a corregir</h3>
        <p style="color:#777;font-size:.85em;margin:4px 0 10px">Cuando el envío falla por número inválido/erróneo, aquí lo corriges: se actualiza el teléfono en <b>LISTA DE CONTACTOS</b> y se reintenta.</p>
        <div class="table-controls">
          <select id="cat-filtro" onchange="loadCatalogo()" style="padding:6px 10px;border:1px solid #ccd;border-radius:8px;font-size:.85em">
            <option value="problema">⚠️ Con problema (corregir número)</option>
            <option value="">Todos</option>
            <option value="PENDIENTE">Pendientes</option>
            <option value="ENVIADO">Enviados</option>
          </select>
          <button class="btn-refresh" onclick="loadCatalogo()">↻ Actualizar</button>
        </div>
        <div class="tbl-wrap" id="catalogo-table"><div class="loading"><div class="spinner"></div></div></div>
      </div>
    </div>

    <!-- Modal corrección de número (dashboard) -->
    <div id="modal-corregir-cat" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,.55);z-index:100;align-items:center;justify-content:center;padding:16px">
      <div style="background:#fff;border-radius:16px;max-width:440px;width:100%;padding:22px;box-shadow:0 20px 60px rgba(0,0,0,.3)">
        <h3 style="margin-bottom:6px">✏️ Corregir número</h3>
        <p style="font-size:.88em;color:#777;margin-bottom:12px">Tienda: <b id="cat-corr-tienda"></b></p>
        <input id="cat-corr-input" type="tel" inputmode="numeric" placeholder="52 + 10 dígitos (ej. 526623534185)"
               style="width:100%;padding:11px;border:1px solid #ccd;border-radius:8px;font-size:1em" oninput="catValidarCorregir()">
        <p id="cat-corr-error" style="color:#e74c3c;font-size:.82em;min-height:16px;margin:4px 0"></p>
        <button id="cat-corr-btn" class="btn-refresh" style="width:100%;background:#00CC47;border-color:#00CC47;color:#fff;padding:10px" disabled onclick="catGuardarCorreccion()">Guardar y reintentar</button>
        <button class="btn-refresh" style="width:100%;margin-top:8px" onclick="catCerrarModal()">Cancelar</button>
      </div>
    </div>

    <!-- ═══ SEGUIMIENTO ═══ -->
    <div class="section" id="sec-seguimiento">
      <div class="cards" id="seg-cards">
        <div class="loading"><div class="spinner"></div><br>Cargando...</div>
      </div>
      <div class="seg-tabs" id="seg-tabs"></div>
      <div class="table-box">
        <h3 id="seg-tab-title">🔄 Seguimiento</h3>
        <div class="table-controls">
          <input type="text" id="seg-search" placeholder="🔍 Buscar en este panel..." oninput="filterSegTab()">
        </div>
        <div class="tbl-wrap" id="seguimiento-table"><div class="loading"><div class="spinner"></div></div></div>
        <div class="pagination" id="seguimiento-pag"></div>
      </div>
    </div>

    <!-- ═══ PROSPECTOS BRUCE ═══ -->
    <div class="section" id="sec-bruce">
      <div class="table-box">
        <h3>🤖 Prospectos Bruce — Agregar Nuevo</h3>
        <div class="bruce-form" id="bruce-form">
          <div>
            <label>Nombre *</label>
            <input id="bf-nombre" placeholder="Nombre de la tienda o contacto">
          </div>
          <div>
            <label>Número de Teléfono</label>
            <input id="bf-tel" placeholder="10 dígitos" type="tel">
          </div>
          <div>
            <label>Tipo de Interés</label>
            <input id="bf-tipo" placeholder="Ej: Abarrotes, Ferretería..." list="bruce-tipos-list">
            <datalist id="bruce-tipos-list">
              <option value="Abarrotes">
              <option value="Ferretería">
              <option value="Farmacia">
              <option value="Papelería">
              <option value="Ropa">
              <option value="Electrónica">
              <option value="Otro">
            </datalist>
          </div>
          <div>
            <label>Fecha</label>
            <input id="bf-fecha" disabled style="background:#e8edf5;color:#888">
          </div>
          <div class="full">
            <label>NOTA</label>
            <textarea id="bf-nota" placeholder="Observaciones, contexto, seguimiento..."></textarea>
          </div>
          <div class="full" style="display:flex;gap:10px;justify-content:flex-end">
            <button class="btn btn-blue" onclick="agregarBruce()" style="max-width:200px">➕ Agregar Prospecto</button>
          </div>
        </div>
      </div>
      <div class="table-box">
        <h3>📋 Lista de Prospectos</h3>
        <div class="table-controls">
          <input type="text" id="bruce-search" placeholder="🔍 Buscar..." oninput="filterBruce(this.value)">
        </div>
        <div class="tbl-wrap" id="bruce-table"><div class="loading"><div class="spinner"></div></div></div>
        <div class="pagination" id="bruce-pag"></div>
      </div>
    </div>

  </div><!-- /content -->
</div><!-- /main -->

<!-- ═══ MODAL EDICIÓN ═══ -->
<div id="edit-seg-modal" style="display:none;position:fixed;inset:0;background:rgba(15,23,42,.65);backdrop-filter:blur(5px);z-index:9999;overflow-y:auto;padding:20px">
  <div style="background:#fff;border-radius:22px;max-width:740px;margin:24px auto;position:relative;box-shadow:0 30px 90px rgba(0,0,0,.4);overflow:hidden">
    <!-- Header -->
    <div style="background:linear-gradient(135deg,#0047CC 0%,#0284c7 100%);padding:22px 28px 18px;position:relative">
      <button onclick="closeEditSeg()" style="position:absolute;top:14px;right:16px;background:rgba(255,255,255,.18);border:none;border-radius:50%;width:34px;height:34px;color:#fff;font-size:1.15em;cursor:pointer;line-height:34px;text-align:center;transition:background .15s" onmouseover="this.style.background='rgba(255,255,255,.32)'" onmouseout="this.style.background='rgba(255,255,255,.18)'">✕</button>
      <div id="edit-modal-title" style="color:#fff;font-size:1.05em;font-weight:800;letter-spacing:.3px">✏️ Editar Registro</div>
      <div id="edit-modal-subtitle" style="color:rgba(255,255,255,.65);font-size:.78em;margin-top:5px;max-width:560px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap"></div>
    </div>
    <!-- Color selector (solo Seguimiento) -->
    <div id="edit-color-section" style="padding:14px 28px;border-bottom:1px solid #f1f5f9;display:flex;align-items:center;gap:14px">
      <span style="font-size:.68em;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:.5px;white-space:nowrap">Estado visual</span>
      <div id="edit-color-picker"></div>
      <span id="edit-color-label" style="font-size:.78em;color:#475569;font-style:italic"></span>
    </div>
    <!-- Fields -->
    <div style="padding:22px 28px 10px">
      <div id="edit-seg-fields" style="display:grid;grid-template-columns:1fr 1fr;gap:15px 18px"></div>
    </div>
    <!-- Footer -->
    <div style="padding:16px 28px 20px;display:flex;gap:10px;justify-content:flex-end;background:#f8fafc;border-top:1px solid #e2e8f0;margin-top:10px">
      <button onclick="closeEditSeg()" style="padding:10px 26px;border-radius:10px;border:1.5px solid #cbd5e1;background:#fff;cursor:pointer;font-weight:600;color:#475569;font-size:.9em;transition:all .15s" onmouseover="this.style.background='#f1f5f9'" onmouseout="this.style.background='#fff'">Cancelar</button>
      <button id="edit-seg-save" onclick="saveEdit()" style="padding:10px 26px;border-radius:10px;border:none;background:linear-gradient(135deg,#0047CC,#0284c7);color:#fff;cursor:pointer;font-weight:700;font-size:.9em;box-shadow:0 4px 14px rgba(0,71,204,.35);transition:all .15s">💾 Guardar cambios</button>
    </div>
  </div>
</div>

<script>
// ─── STATE ──────────────────────────────────────────────────────────────────
const state = {
  currentSection: 'dashboard',
  loaded: {},
  data: {},
  filtered: {},
  page: {},
  pageSize: 50,
  sortCol: {},
  sortDir: {},  // true = asc, false = desc
};

const SECTION_TITLES = {
  dashboard:   '📊 Dashboard Prospectos',
  frecuentes:  '⭐ Dashboard Clientes Frecuentes',
  'ventas-dash': '📈 Dashboard de Ventas',
  ventas:      '💰 Ventas',
  contactos:   '📋 Lista de Contactos',
  pendientes:  '📞 Por Llamar — Sin Respuesta',
  ciudades:    '🗺️ Ciudades por Interés',
  respuestas:  '📝 Respuestas del Formulario',
  mensajes:    '💬 Mensajes Iniciales',
  catalogo:    '📖 Envíos de Catálogo',
  seguimiento: '🔄 Seguimiento',
  bruce:       '🤖 Prospectos Bruce',
};

let charts = {};

// ─── NAVIGATION ─────────────────────────────────────────────────────────────
function showSection(name) {
  document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  document.getElementById('sec-' + name).classList.add('active');
  document.querySelectorAll('.nav-item').forEach(n => {
    if (n.textContent.trim().toLowerCase().includes(SECTION_TITLES[name].slice(2,10).toLowerCase().trim()))
      n.classList.add('active');
  });
  // simpler: mark by onclick
  event.currentTarget.classList.add('active');
  state.currentSection = name;
  document.getElementById('topbar-title').textContent = SECTION_TITLES[name];
  if (!state.loaded[name]) loadSection(name);
}

// ─── LOAD SECTION ───────────────────────────────────────────────────────────
async function loadSection(name) {
  state.loaded[name] = true;
  try {
  switch(name) {
    case 'dashboard':   await loadDashboard(); break;
    case 'frecuentes':  await loadFrecuentes(); break;
    // filterTable('frecuentes') → frec-top-table / frec-pag manejado en loadFrecuentes
    case 'ventas-dash': await loadVentasDash(); break;
    case 'ventas':      await loadVentas(); break;
    case 'contactos':   await loadContactos(); break;
    case 'pendientes':  await loadPendientes(); break;
    case 'ciudades':    await loadCiudades(); break;
    case 'respuestas':
      await loadTableSection('respuestas', '/api/prospectos/respuestas', 'respuestas-table', 'respuestas-pag', ['resp-search','resp-conclusion']);
      // Poblar dropdown de Conclusión con valores únicos del dataset
      { const concSel = document.getElementById('resp-conclusion');
        if (concSel) {
          const vals = [...new Set((state.data['respuestas'] || [])
            .map(r => String(r['Conclusión'] || r['Conclusion'] || '').trim())
            .filter(Boolean))].sort();
          vals.forEach(v => { const o = document.createElement('option'); o.value = v; o.textContent = v; concSel.appendChild(o); });
        }
      }
      break;
    case 'mensajes':    await loadMensajes(); break;
    case 'catalogo':    await loadCatalogo(); break;
    case 'seguimiento': await loadSeguimiento(); break;
    case 'bruce':       await loadBruce(); break;
  }
  } catch(e) {
    console.error('loadSection error:', name, e);
    const tableEl = document.getElementById(name + '-table') || document.getElementById('sec-' + name)?.querySelector('.tbl-wrap');
    if (tableEl) tableEl.innerHTML = `<div class="empty" style="color:#e74c3c">⚠️ Error al cargar: ${e.message}</div>`;
    const cardsEl = document.getElementById(name.replace('-','') + '-cards') || document.getElementById('pend-cards');
    if (name === 'pendientes' && cardsEl) cardsEl.innerHTML = `<div class="empty" style="color:#e74c3c">⚠️ Error: ${e.message}</div>`;
    state.loaded[name] = false; // permitir reintento
  }
}

// ─── FETCH ──────────────────────────────────────────────────────────────────
async function fetchAPI(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

function showSectionError(sectionId, msg) {
  const el = document.getElementById(sectionId);
  if (el) el.innerHTML = `<div class="empty" style="color:#e74c3c">⚠️ ${msg}</div>`;
}

// ─── DASHBOARD ──────────────────────────────────────────────────────────────
async function loadDashboard() {
  const stats = await fetchAPI('/api/prospectos/stats');
  state.data.dashStats = stats;
  updateCacheBadge();

  const res = stats.resultados || {};
  const aprobados = res['APROBADO'] || 0;
  const negados   = res['NEGADO'] || 0;
  const nc        = res['NO COMPATIBLE'] || 0;
  const mu        = res['MARCA UNICA'] || 0;

  const estados = stats.estados_llamada || {};
  const buzon   = estados['BUZON'] || estados['BUZÓN'] || 0;
  const telInc  = estados['TELEFONO INCORRECTO'] || estados['TELÉFONO INCORRECTO'] || 0;

  const totalResp = stats.total_respuestas || 0;
  const tasaConv  = totalResp > 0 ? ((aprobados / totalResp) * 100).toFixed(1) : 0;

  document.getElementById('dash-cards').innerHTML = `
    <div class="card"><div class="label">Total Contactos</div><div class="value">${stats.total_contactos}</div><div class="sub">En lista</div></div>
    <div class="card"><div class="label">Llamadas Realizadas</div><div class="value">${totalResp}</div><div class="sub">Con respuesta</div></div>
    <div class="card green"><div class="label">Aprobados</div><div class="value">${aprobados}</div><div class="sub">Tasa: ${tasaConv}%</div></div>
    <div class="card red"><div class="label">Negados</div><div class="value">${negados}</div><div class="sub">Rechazaron</div></div>
    <div class="card orange"><div class="label">Buzón</div><div class="value">${buzon}</div><div class="sub">No contestó</div></div>
    <div class="card gray"><div class="label">Tel. Incorrecto</div><div class="value">${telInc}</div><div class="sub">Fuera de servicio</div></div>
    <div class="card orange"><div class="label">No Compatible</div><div class="value">${nc}</div><div class="sub">Sin fit</div></div>
    <div class="card purple"><div class="label">Marca Única</div><div class="value">${mu}</div><div class="sub">Competencia</div></div>
  `;

  // Chart: Resultados donut
  destroyChart('chartResultados');
  const ctxR = document.getElementById('chartResultados').getContext('2d');
  const labelsR = Object.keys(res);
  const dataR   = Object.values(res);
  charts['chartResultados'] = new Chart(ctxR, {
    type: 'doughnut',
    data: {
      labels: labelsR,
      datasets: [{ data: dataR, backgroundColor: ['#00CC47','#e74c3c','#e67e22','#8e44ad','#6c757d','#ffc107'] }]
    },
    options: { plugins: { legend: { position: 'right' } }, cutout: '65%' }
  });

  // Chart: Semanas
  destroyChart('chartSemanas');
  const semanas = stats.por_semana || [];
  const ctxS = document.getElementById('chartSemanas').getContext('2d');
  charts['chartSemanas'] = new Chart(ctxS, {
    type: 'line',
    data: {
      labels: semanas.map(s => s.semana),
      datasets: [{ label: 'Contactos', data: semanas.map(s => s.total), borderColor: '#0047CC', backgroundColor: 'rgba(0,71,204,.1)', fill: true, tension: .4 }]
    },
    options: { plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true } } }
  });

  // Chart: Ciudades
  destroyChart('chartCiudades');
  const ciudades = (stats.top_ciudades || []).slice(0,10);
  const ctxC = document.getElementById('chartCiudades').getContext('2d');
  charts['chartCiudades'] = new Chart(ctxC, {
    type: 'bar',
    data: {
      labels: ciudades.map(c => c[0]),
      datasets: [{ label: 'Contactos', data: ciudades.map(c => c[1]), backgroundColor: '#0047CC' }]
    },
    options: { plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true } } }
  });
}

// ─── FRECUENTES ─────────────────────────────────────────────────────────────
async function loadFrecuentes() {
  const data = await fetchAPI('/api/prospectos/clientes-frecuentes');

  // ── KPIs ──
  const totalClientes = data.length;
  const totalMonto    = data.reduce((s, r) => s + (r['Total Monto'] || 0), 0);
  const totalPedidos  = data.reduce((s, r) => s + (r['Pedidos'] || 0), 0);
  const top           = data[0] || {};

  document.getElementById('frec-cards').innerHTML = `
    <div class="card"><div class="label">Clientes</div><div class="value">${totalClientes}</div><div class="sub">Con al menos 1 pedido</div></div>
    <div class="card green"><div class="label">Facturación Total</div><div class="value">$${fmtMonto(totalMonto)}</div><div class="sub">Suma de todos</div></div>
    <div class="card"><div class="label">Total Pedidos</div><div class="value">${totalPedidos}</div><div class="sub">Facturas emitidas</div></div>
    <div class="card orange"><div class="label">Top Cliente</div><div class="value" style="font-size:1em">${top['Cliente'] || '—'}</div><div class="sub">$${fmtMonto(top['Total Monto'] || 0)}</div></div>
  `;

  // ── Tabla agrupada ──
  const pageSize = 50;
  const page     = state.page['frecuentes'] || 1;
  const slice    = data.slice((page-1)*pageSize, page*pageSize);

  let html = `<table><thead><tr>
    <th>#</th><th>Cliente</th><th>Esquema</th><th>Pedidos</th>
    <th style="text-align:right">Total Facturado</th><th>Último Pedido</th>
  </tr></thead><tbody>`;

  slice.forEach((r, i) => {
    const rank = (page-1)*pageSize + i + 1;
    const medal = rank === 1 ? '🥇' : rank === 2 ? '🥈' : rank === 3 ? '🥉' : `${rank}`;
    html += `<tr>
      <td style="font-weight:700;color:var(--blue)">${medal}</td>
      <td><strong>${r['Cliente']}</strong></td>
      <td><span class="tag default">${r['Esquema'] || '—'}</span></td>
      <td style="text-align:center;font-weight:700">${r['Pedidos']}</td>
      <td style="text-align:right;font-weight:800;color:var(--green)">$${fmtMonto(r['Total Monto'])}</td>
      <td style="color:#888;font-size:.85em">${r['Ultimo Pedido'] || '—'}</td>
    </tr>`;
  });
  html += '</tbody></table>';
  document.getElementById('frec-top-table').innerHTML = html;

  // Paginación
  const totalPages = Math.ceil(data.length / pageSize);
  let pag = `<span class="pag-info">${data.length} clientes</span>`;
  if (totalPages > 1) {
    if (page > 1) pag += `<button onclick="frecPage(${page-1})">‹</button>`;
    for (let p = Math.max(1,page-2); p <= Math.min(totalPages,page+2); p++) {
      pag += `<button class="${p===page?'active':''}" onclick="frecPage(${p})">${p}</button>`;
    }
    if (page < totalPages) pag += `<button onclick="frecPage(${page+1})">›</button>`;
  }
  document.getElementById('frec-pag').innerHTML = pag;

  // Guardar data para paginación
  state.data['frecuentes-raw'] = data;
}

function frecPage(p) {
  state.page['frecuentes'] = p;
  state.data['frecuentes'] = state.data['frecuentes-raw'];
  loadFrecuentes();
}

function fmtMonto(n) {
  return Number(n).toLocaleString('es-MX', {minimumFractionDigits:2, maximumFractionDigits:2});
}

// ─── DASHBOARD VENTAS ────────────────────────────────────────────────────────
async function loadVentasDash() {
  const d = await fetchAPI('/api/prospectos/ventas-dashboard');
  const meses = d.por_mes || [];

  // ── KPIs ──
  document.getElementById('vdash-cards').innerHTML = `
    <div class="card green">
      <div class="label">Facturación Total</div>
      <div class="value" style="font-size:1.4em">$${fmtMonto(d.total_general)}</div>
      <div class="sub">Todas las ventas</div>
    </div>
    <div class="card">
      <div class="label">Total Pedidos</div>
      <div class="value">${d.total_pedidos}</div>
      <div class="sub">Facturas emitidas</div>
    </div>
    <div class="card orange">
      <div class="label">Promedio Mensual</div>
      <div class="value" style="font-size:1.3em">$${fmtMonto(d.promedio_mes)}</div>
      <div class="sub">Por mes</div>
    </div>
    <div class="card purple">
      <div class="label">Mejor Mes</div>
      <div class="value" style="font-size:1.1em">${d.mejor_mes}</div>
      <div class="sub">$${fmtMonto(d.mejor_mes_monto)}</div>
    </div>
    <div class="card">
      <div class="label">Meses Activos</div>
      <div class="value">${meses.length}</div>
      <div class="sub">Con ventas</div>
    </div>
  `;

  const labels  = meses.map(m => m.mes);
  const montos  = meses.map(m => m.monto);
  const pedidos = meses.map(m => m.pedidos);
  const tickets = meses.map(m => m.ticket_prom);

  // ── Chart: Facturación mensual ──
  destroyChart('chartVentasMonto');
  charts['chartVentasMonto'] = new Chart(
    document.getElementById('chartVentasMonto').getContext('2d'), {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        label: 'Facturación $',
        data: montos,
        backgroundColor: montos.map((v,i) =>
          v === Math.max(...montos) ? '#00CC47' : 'rgba(0,71,204,0.7)'),
        borderRadius: 6,
      }]
    },
    options: {
      plugins: { legend: { display: false } },
      scales: {
        y: { beginAtZero: true, ticks: { callback: v => '$'+fmtMonto(v) } }
      }
    }
  });

  // ── Chart: Pedidos por mes ──
  destroyChart('chartVentasPedidos');
  charts['chartVentasPedidos'] = new Chart(
    document.getElementById('chartVentasPedidos').getContext('2d'), {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        label: 'Pedidos',
        data: pedidos,
        backgroundColor: 'rgba(0,71,204,0.75)',
        borderRadius: 6,
      }]
    },
    options: {
      plugins: { legend: { display: false } },
      scales: { y: { beginAtZero: true, ticks: { stepSize: 1 } } }
    }
  });

  // ── Chart: Ticket promedio ──
  destroyChart('chartVentasTicket');
  charts['chartVentasTicket'] = new Chart(
    document.getElementById('chartVentasTicket').getContext('2d'), {
    type: 'line',
    data: {
      labels,
      datasets: [{
        label: 'Ticket Promedio $',
        data: tickets,
        borderColor: '#e67e22',
        backgroundColor: 'rgba(230,126,34,.1)',
        fill: true, tension: .4, pointRadius: 4,
      }]
    },
    options: {
      plugins: { legend: { display: false } },
      scales: {
        y: { beginAtZero: true, ticks: { callback: v => '$'+fmtMonto(v) } }
      }
    }
  });

  // ── Tabla desglose por mes ──
  const maxMonto = Math.max(...montos, 1);
  let html = `<table><thead><tr>
    <th>Mes</th><th style="text-align:right">Facturación</th>
    <th style="text-align:center">Pedidos</th><th style="text-align:center">Clientes</th>
    <th style="text-align:right">Ticket Prom.</th><th>Distribución</th>
  </tr></thead><tbody>`;

  meses.forEach(m => {
    const barW = Math.round((m.monto / maxMonto) * 140);
    const esqs = Object.entries(m.por_esquema)
      .sort((a,b) => b[1]-a[1])
      .map(([k,v]) => `<span class="tag default" style="font-size:.7em">${k}: $${fmtMonto(v)}</span>`)
      .join(' ');
    const isMejor = m.mes === d.mejor_mes;
    html += `<tr ${isMejor ? 'style="background:#f0fff4"' : ''}>
      <td><strong ${isMejor ? 'style="color:var(--green)"' : ''}>${m.mes} ${isMejor ? '⭐' : ''}</strong></td>
      <td style="text-align:right;font-weight:800;color:var(--green)">$${fmtMonto(m.monto)}</td>
      <td style="text-align:center;font-weight:700">${m.pedidos}</td>
      <td style="text-align:center">${m.clientes}</td>
      <td style="text-align:right;color:#888">$${fmtMonto(m.ticket_prom)}</td>
      <td>
        <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap">
          <div style="background:var(--green);height:8px;border-radius:4px;width:${barW}px;min-width:2px"></div>
          ${esqs}
        </div>
      </td>
    </tr>`;
  });
  html += '</tbody></table>';
  document.getElementById('vdash-table').innerHTML = html;
}

// ─── VENTAS (orden cronológico de ingreso) ────────────────────────────────────
async function loadVentas() {
  const data = await fetchAPI('/api/prospectos/ventas');
  // Orden de ingreso: primeras entradas primero (como en la hoja)
  state.data['ventas'] = data;
  state.filtered['ventas'] = data;
  state.page['ventas'] = 1;
  const countEl = document.getElementById('ventas-count');
  if (countEl) countEl.textContent = `${data.length} registros`;
  renderTable('ventas', 'ventas-table', 'ventas-pag');
}

// ─── GENERIC TABLE ──────────────────────────────────────────────────────────
async function loadTableSection(key, url, tableId, pagId, filterIds) {
  const data = await fetchAPI(url);
  state.data[key] = data;
  state.filtered[key] = data;
  state.page[key] = 1;
  renderTable(key, tableId, pagId);
}

function filterTable(key) {
  const d = state.data[key] || [];
  let filtered = d;

  const searchId = key === 'respuestas' ? 'resp-search'
    : key === 'frecuentes' ? 'frecuentes-search'
    : key + '-search';
  const searchEl = document.getElementById(searchId);
  const q = searchEl ? searchEl.value.toLowerCase() : '';
  if (q) {
    filtered = filtered.filter(row =>
      Object.values(row).some(v => String(v).toLowerCase().includes(q))
    );
  }

  // Specific filters
  if (key === 'respuestas') {
    const concEl = document.getElementById('resp-conclusion');
    const conc = concEl ? concEl.value : '';
    if (conc) filtered = filtered.filter(r =>
      String(r['Conclusión'] || r['Conclusion'] || '').trim() === conc
    );
  }
  if (key === 'contactos' || key === 'pendientes') {
    const ciudadEl = document.getElementById(`${key}-ciudad`);
    const ciudad = ciudadEl ? ciudadEl.value.toLowerCase() : '';
    if (ciudad) filtered = filtered.filter(r => String(r.Ciudad || r.ciudad || r.CIUDAD || '').toLowerCase() === ciudad);
    if (key === 'contactos') {
      const catEl = document.getElementById('contactos-cat');
      const cat = catEl ? catEl.value.toLowerCase() : '';
      if (cat) filtered = filtered.filter(r => Object.values(r).some(v => String(v).toLowerCase() === cat));
    }
  }

  state.filtered[key] = filtered;
  state.page[key] = 1;
  // frecuentes usa IDs distintos
  const tableId = key === 'frecuentes' ? 'frec-top-table' : key + '-table';
  const pagId   = key === 'frecuentes' ? 'frec-pag'       : key + '-pag';
  renderTable(key, tableId, pagId);
}

function renderTable(key, tableId, pagId) {
  const data = state.filtered[key] || [];
  const page = state.page[key] || 1;
  const ps   = state.pageSize;
  const total = data.length;
  const totalPages = Math.ceil(total / ps);

  if (!total) {
    document.getElementById(tableId).innerHTML = '<div class="empty">No hay datos</div>';
    document.getElementById(pagId).innerHTML = '';
    return;
  }

  // Ordenar antes de paginar
  const sc = state.sortCol[key];
  const sd = state.sortDir[key]; // true=asc false=desc
  const sorted = sc ? [...data].sort((a, b) => {
    const va = String(a[sc] ?? '');
    const vb = String(b[sc] ?? '');
    const na = parseFloat(va.replace(/[,$\s]/g, ''));
    const nb = parseFloat(vb.replace(/[,$\s]/g, ''));
    const cmp = !isNaN(na) && !isNaN(nb) ? na - nb : va.localeCompare(vb, 'es-MX');
    return sd ? cmp : -cmp;
  }) : data;
  const slice = sorted.slice((page-1)*ps, page*ps);

  const allCols = Object.keys(slice[0]).filter(k => !k.startsWith('_'));

  // Columnas fijas para ventas/frecuentes (en orden exacto de la hoja)
  const VENTAS_COLS = ['Fecha','Cliente','ESQUEMA','MES','Monto ','Monto','Envio Costo','Num Factura','Cotizacion PDF','PAGO'];
  // Columnas clave para respuestas (Conclusión es el campo principal)
  const RESPUESTAS_COLS = ['Marca temporal','Nombre De la Tienda','Teléfono','Telefono','CIUDAD','Ciudad','Conclusión','Conclusion'];
  // Encabezados exactos del sheet de Mensajes Iniciales
  const MENSAJES_COLS = ['Mensaje inicial','Mensaje Seguimiento','Cotizacion','Cotizacion Seguimiento','Seguimiento Clientes','correo'];
  const isVentas     = key === 'ventas' || key === 'frecuentes';
  const isRespuestas = key === 'respuestas';
  const isSeguimiento = key === 'seguimiento';
  const isMensajes    = key === 'mensajes';

  let sortedCols;
  if (isVentas) {
    sortedCols = VENTAS_COLS.filter(c => allCols.includes(c));
    allCols.filter(c => !VENTAS_COLS.includes(c) && c.trim() !== '').forEach(c => sortedCols.push(c));
  } else if (isRespuestas) {
    sortedCols = RESPUESTAS_COLS.filter(c => allCols.includes(c));
  } else if (isMensajes) {
    // Preferir columnas definidas; si no coinciden (distinto header) usar las del dataset
    sortedCols = MENSAJES_COLS.filter(c => allCols.includes(c));
    if (!sortedCols.length) sortedCols = allCols.filter(c => c.trim() !== '').slice(0, 10);
  } else {
    sortedCols = allCols.filter(c => c.trim() !== '').slice(0, 20);
  }
  const isEditable    = isSeguimiento || isMensajes;
  const openFn        = isMensajes ? 'openEditMen' : 'openEditSeg';
  const arrow = c => c === sc ? (sd ? ' ▲' : ' ▼') : ' ⇅';
  const thStyle = 'cursor:pointer;white-space:nowrap;user-select:none';

  const editTh = isEditable ? '<th style="width:60px"></th>' : '';
  let html = `<table><thead><tr>${editTh}${sortedCols.map(c =>
    `<th style="${thStyle}" data-key="${key}" data-tableid="${tableId}" data-pagid="${pagId}" data-col="${c.replace(/"/g,'&quot;')}" onclick="sortTable(this)">${c}<span style="opacity:.4;font-size:.75em">${arrow(c)}</span></th>`
  ).join('')}</tr></thead><tbody>`;

  slice.forEach(row => {
    if (isSeguimiento && row._row) _segRowMap[row._row] = row;
    const editKey = row._row;
    const editTd = isEditable && editKey
      ? `<td><button class="btn-edit-row" onclick="${openFn}(${editKey})">✏️ Editar</button></td>`
      : '<td></td>';
    const colorCode = (isSeguimiento && row._row) ? (_segColorMap[row._row] || '') : '';
    const colorD    = colorCode ? SEG_COLORS[colorCode] : null;
    const rowStyle  = colorD ? `style="background:${colorD.bg};border-left:5px solid ${colorD.border}"` : '';
    html += `<tr ${rowStyle}>` + editTd + sortedCols.map(c => {
      const v = row[c] !== undefined ? row[c] : '';
      return `<td>${renderCell(c, String(v), row)}</td>`;
    }).join('') + '</tr>';
  });
  html += '</tbody></table>';
  document.getElementById(tableId).innerHTML = html;

  // Pagination
  let pag = `<span class="pag-info">${total} registros</span>`;
  if (totalPages > 1) {
    if (page > 1) pag += `<button onclick="goPage('${key}','${tableId}','${pagId}',${page-1})">‹</button>`;
    const start = Math.max(1, page-2), end = Math.min(totalPages, page+2);
    for (let p = start; p <= end; p++) {
      pag += `<button class="${p===page?'active':''}" onclick="goPage('${key}','${tableId}','${pagId}',${p})">${p}</button>`;
    }
    if (page < totalPages) pag += `<button onclick="goPage('${key}','${tableId}','${pagId}',${page+1})">›</button>`;
  }
  document.getElementById(pagId).innerHTML = pag;
}

function goPage(key, tableId, pagId, p) {
  state.page[key] = p;
  renderTable(key, tableId, pagId);
}

function sortTable(th) {
  const key     = th.dataset.key;
  const tableId = th.dataset.tableid;
  const pagId   = th.dataset.pagid;
  const col     = th.dataset.col;
  if (state.sortCol[key] === col) {
    state.sortDir[key] = !state.sortDir[key];
  } else {
    state.sortCol[key] = col;
    state.sortDir[key] = true;
  }
  state.page[key] = 1;
  renderTable(key, tableId, pagId);
}

function renderCell(col, val, row) {
  if (!val || val === 'undefined') {
    // Columna PAGO vacía → mostrar botón de upload
    if (col === 'PAGO' && row) {
      const factura = row['Num Factura'] || '';
      return `<button class="btn-upload-pago" onclick="abrirUpload('${factura}', this)" title="Subir comprobante">📎 Subir</button>`;
    }
    return '<span style="color:#ccc">—</span>';
  }
  const colLow = col.toLowerCase();
  const valUp  = val.toUpperCase();

  if (colLow.includes('resultado')) {
    if (valUp === 'APROBADO') return `<span class="tag aprobado">✓ Aprobado</span>`;
    if (valUp === 'NEGADO') return `<span class="tag negado">✗ Negado</span>`;
    if (valUp === 'NO COMPATIBLE') return `<span class="tag no-compatible">No Compatible</span>`;
    if (valUp === 'MARCA UNICA') return `<span class="tag marca-unica">Marca Única</span>`;
  }
  if (colLow.includes('estado') && (valUp.includes('BUZON') || valUp.includes('BUZÓN'))) return `<span class="tag buzon">Buzón</span>`;
  if (colLow.includes('estado') && valUp.includes('INCORRECTO')) return `<span class="tag tel-inc">Tel. Incorrecto</span>`;
  if (colLow.includes('estado') && valUp === 'RESPONDIO') return `<span class="tag aprobado">Respondió</span>`;

  // Columna PAGO
  if (col === 'PAGO') {
    if (val.startsWith('http')) {
      // Ya tiene URL (ImgBB o Drive) → solo ver, NO subir
      const fileId = val.match(/\/d\/([^/]+)\//)?.[1] || '';
      // Thumb: Drive usa thumbnail API, ImgBB devuelve URL directa de imagen
      const thumb = fileId
        ? `https://drive.google.com/thumbnail?id=${fileId}&sz=w120`
        : val;  // ImgBB: la URL ya es la imagen directa
      const full = fileId
        ? `https://drive.google.com/thumbnail?id=${fileId}&sz=w1200`
        : val;
      return `<span style="display:flex;align-items:center;gap:6px">
        <img src="${thumb}" class="pago-thumb" data-full="${full}" data-link="${val}"
             style="height:40px;border-radius:4px;cursor:pointer;border:2px solid #0047CC"
             title="Clic para ampliar"
             onerror="this.style.display='none'">
        <a href="${val}" target="_blank" style="color:var(--blue);font-size:.78em;font-weight:600">🔍 Abrir</a>
      </span>`;
    }
    // Tiene nombre de archivo pero no URL → solo subir
    const factura = row ? (row['Num Factura'] || '') : '';
    return `<span style="display:flex;align-items:center;gap:5px" id="pago-cell-${factura}">
      <span style="font-size:.72em;color:#999;max-width:90px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${val}">🖼 ${val.slice(0,14)}…</span>
      <button class="btn-upload-pago" onclick="abrirUpload('${factura}',this)" title="Subir comprobante a Drive">📤 Subir</button>
    </span>`;
  }

  // Escape HTML para columnas de texto plano (datos de hoja/importador Places): cierra XSS almacenado.
  const _esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c =>
    ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  if (val.startsWith('http')) return `<a href="${_esc(val)}" target="_blank" style="color:var(--blue);font-size:.8em">Ver →</a>`;
  if (val.length > 80) return `<span title="${_esc(val)}">${_esc(val.slice(0,78))}…</span>`;
  return _esc(val);
}

// ─── CONTACTOS ──────────────────────────────────────────────────────────────
async function loadContactos() {
  const data = await fetchAPI('/api/prospectos/contactos');
  state.data['contactos'] = data;
  state.filtered['contactos'] = data;
  state.page['contactos'] = 1;

  // Populate ciudad filter
  const ciudades = [...new Set(data.map(r => String(r.Ciudad || r.ciudad || r.CIUDAD || '').trim()).filter(Boolean))].sort();
  const ciudadSel = document.getElementById('contactos-ciudad');
  ciudades.forEach(c => { const o = document.createElement('option'); o.value = c.toLowerCase(); o.textContent = c; ciudadSel.appendChild(o); });

  // Populate categoria filter
  const catKey = Object.keys(data[0] || {}).find(k => k.toLowerCase().includes('categ')) || null;
  if (catKey) {
    const cats = [...new Set(data.map(r => String(r[catKey] || '').trim()).filter(Boolean))].sort();
    const catSel = document.getElementById('contactos-cat');
    catSel.parentElement.querySelector('option').textContent = `Todas las categorías`;
    cats.forEach(c => { const o = document.createElement('option'); o.value = c.toLowerCase(); o.textContent = c; catSel.appendChild(o); });
  }

  renderTable('contactos', 'contactos-table', 'contactos-pag');
}

// ─── POR LLAMAR ─────────────────────────────────────────────────────────────
async function loadPendientes() {
  const data = await fetchAPI('/api/prospectos/contactos-pendientes');
  state.data['pendientes']     = data;
  state.filtered['pendientes'] = data;
  state.page['pendientes']     = 1;

  // KPIs
  const totalPend = data.length;
  const ciudadesSet = [...new Set(data.map(r =>
    String(r.CIUDAD || r.Ciudad || r.ciudad || '').trim()).filter(Boolean))];

  document.getElementById('pend-cards').innerHTML = `
    <div class="card red">
      <div class="label">Sin Llamar</div>
      <div class="value">${totalPend}</div>
      <div class="sub">Sin respuesta aún</div>
    </div>
    <div class="card">
      <div class="label">Ciudades</div>
      <div class="value">${ciudadesSet.length}</div>
      <div class="sub">Diferentes</div>
    </div>
  `;

  // Populate ciudad filter
  const ciudadSel = document.getElementById('pendientes-ciudad');
  ciudadSel.innerHTML = '<option value="">Todas las ciudades</option>';
  ciudadesSet.sort().forEach(c => {
    const o = document.createElement('option');
    o.value = c.toLowerCase();
    o.textContent = c;
    ciudadSel.appendChild(o);
  });

  renderTable('pendientes', 'pendientes-table', 'pendientes-pag');
}

// ─── CIUDADES ───────────────────────────────────────────────────────────────
let ciudadesData = [];
let ciudadesSortCol = 'relevancia';
let ciudadesSortAsc = false;

async function loadCiudades() {
  ciudadesData = await fetchAPI('/api/prospectos/ciudades');
  renderCiudades(getSortedCiudades());
}

function filterCiudades() {
  const q = document.getElementById('ciudades-search').value.toLowerCase();
  const filtradas = q ? ciudadesData.filter(c => c.ciudad.toLowerCase().includes(q)) : ciudadesData;
  renderCiudades(getSortedCiudades(filtradas));
}

function getSortedCiudades(data) {
  const d = (data || ciudadesData).slice();
  d.sort((a, b) => {
    const va = a[ciudadesSortCol] ?? 0;
    const vb = b[ciudadesSortCol] ?? 0;
    return ciudadesSortAsc ? (va > vb ? 1 : -1) : (va < vb ? 1 : -1);
  });
  return d;
}

function sortCiudades(col) {
  if (ciudadesSortCol === col) ciudadesSortAsc = !ciudadesSortAsc;
  else { ciudadesSortCol = col; ciudadesSortAsc = false; }
  const q = document.getElementById('ciudades-search').value.toLowerCase();
  const filtradas = q ? ciudadesData.filter(c => c.ciudad.toLowerCase().includes(q)) : null;
  renderCiudades(getSortedCiudades(filtradas));
}

function renderCiudades(data) {
  if (!data || !data.length) {
    document.getElementById('ciudades-table').innerHTML = '<div class="empty">Sin datos</div>';
    return;
  }
  const maxAprob = Math.max(...data.map(c => c.aprobados), 1);

  const cols = [
    { key: 'ciudad',        label: 'Ciudad',        fmt: (v,c) => `<strong>${v}</strong>` },
    { key: 'total',         label: 'En Lista',       fmt: v => v },
    { key: 'llamados',      label: 'Llamados',       fmt: v => v },
    { key: 'respondio',     label: '📞 Respondió',   fmt: v => v || 0 },
    { key: 'buzon',         label: '📬 Buzón',       fmt: v => v || 0 },
    { key: 'tel_incorrecto',label: '✗ Tel. Inc.',    fmt: v => v || 0 },
    { key: 'aprobados',     label: '✓ Aprobados',    fmt: (v,c) => {
      const w = Math.round((v / maxAprob) * 80);
      return `${v} <span class="interes-bar" style="width:${w}px"></span>`;
    }},
    { key: 'interes_pct',   label: '% Interés',      fmt: v => `<strong style="color:var(--green)">${v}%</strong>` },
    { key: 'negados',       label: '✗ Negados',      fmt: v => v || 0 },
    { key: 'no_compatible', label: '⊘ No Compat.',   fmt: v => v || 0 },
    { key: 'marca_unica',   label: '◈ M.Única',      fmt: v => v || 0 },
    { key: 'pedido',        label: '📦 Pedido',      fmt: v => v ? `<strong style="color:var(--green)">${v}</strong>` : 0 },
    { key: 'catalogo',      label: '📖 Catálogo',    fmt: v => v || 0 },
    { key: 'correo',        label: '📧 Correo',      fmt: v => v || 0 },
    { key: 'avance',        label: '📅 Avance',      fmt: v => v || 0 },
    { key: 'continuacion',  label: '⏳ Continuación',fmt: v => v || 0 },
    { key: 'nulo',          label: '✗ Nulo',         fmt: v => v || 0 },
    { key: 'colgo',         label: '📵 Colgó',       fmt: v => v || 0 },
  ];

  const arrow = col => col === ciudadesSortCol ? (ciudadesSortAsc ? ' ▲' : ' ▼') : '';

  let html = `<table><thead><tr>
    <th style="cursor:default">#</th>
    ${cols.map(c =>
      `<th style="cursor:pointer;white-space:nowrap" onclick="sortCiudades('${c.key}')">${c.label}${arrow(c.key)}</th>`
    ).join('')}
  </tr></thead><tbody>`;

  data.forEach((c, i) => {
    html += `<tr>${[`<td>${i+1}</td>`,
      ...cols.map(col => `<td>${col.fmt(c[col.key], c)}</td>`)
    ].join('')}</tr>`;
  });

  html += '</tbody></table>';
  document.getElementById('ciudades-table').innerHTML = html;
}

// ─── SEGUIMIENTO ────────────────────────────────────────────────────────────
const SEG_ICONS = {
  callback:'📞', llamar:'📞', 'volver a llamar':'📞', rellamar:'📞',
  'buzón':'📬', buzon:'📬', voz:'📬',
  respondió:'✅', respondio:'✅', contestó:'✅', contesto:'✅',
  'no contesta':'❌', 'no contest':'❌', 'no respondió':'❌', 'no respondio':'❌',
  incorrecto:'⚠️', equivocado:'⚠️', inexistente:'⚠️',
  pedido:'🛒', interesado:'🌟', aprobado:'✅',
  negado:'🚫', rechazado:'🚫',
};
function segIcon(val) {
  const v = (val || '').toLowerCase();
  for (const [k, icon] of Object.entries(SEG_ICONS)) { if (v.includes(k)) return icon; }
  return '📋';
}

let _segGroups = {};
let _segActiveTab = 'todos';
let _segResultKey = null;

async function loadSeguimiento() {
  const data = await fetchAPI('/api/seguimiento');
  state.data['seguimiento'] = data;
  _segColumnOptions = buildColumnOptions(data);

  // Detectar columna "Resultado Llamada" o similar
  if (data.length) {
    const keys = Object.keys(data[0]);
    _segResultKey = keys.find(k => /resultado/i.test(k))
      || keys.find(k => /estado/i.test(k))
      || keys.find(k => /status/i.test(k))
      || null;
  }

  // Agrupar por valor de resultado
  _segGroups = { todos: data };
  if (_segResultKey) {
    data.forEach(r => {
      const v = String(r[_segResultKey] || '').trim() || 'Sin resultado';
      if (!_segGroups[v]) _segGroups[v] = [];
      _segGroups[v].push(r);
    });
  }

  // KPI cards
  const total = data.length;
  let cardsHtml = `<div class="card"><div class="label">Total</div><div class="value">${total}</div><div class="sub">Registros</div></div>`;
  Object.entries(_segGroups).filter(([k]) => k !== 'todos').forEach(([s, arr]) => {
    const pct = total > 0 ? ((arr.length / total) * 100).toFixed(0) : 0;
    cardsHtml += `<div class="card"><div class="label">${s}</div><div class="value">${arr.length}</div><div class="sub">${pct}%</div></div>`;
  });
  document.getElementById('seg-cards').innerHTML = cardsHtml;

  // Tabs
  const tabKeys = ['todos', ...Object.keys(_segGroups).filter(k => k !== 'todos')];
  document.getElementById('seg-tabs').innerHTML = tabKeys.map(k => {
    const count = (_segGroups[k] || []).length;
    const icon  = k === 'todos' ? '🔄' : segIcon(k);
    const label = k === 'todos' ? 'Todos' : k;
    return `<div class="seg-tab${k==='todos'?' active':''}" data-tab="${k.replace(/"/g,'&quot;')}" onclick="switchSegTab(this)">${icon} ${label} <span class="tab-count">(${count})</span></div>`;
  }).join('');

  _segActiveTab = 'todos';
  renderSegTab();
}

function switchSegTab(el) {
  _segActiveTab = el.dataset.tab;
  document.querySelectorAll('#seg-tabs .seg-tab').forEach(t => t.classList.remove('active'));
  el.classList.add('active');
  document.getElementById('seg-search').value = '';
  renderSegTab();
}

function filterSegTab() { renderSegTab(); }

function renderSegTab() {
  const raw = _segGroups[_segActiveTab] || [];
  const q = (document.getElementById('seg-search')?.value || '').toLowerCase();
  const filtered = q ? raw.filter(r => Object.values(r).some(v => String(v).toLowerCase().includes(q))) : raw;
  const label = _segActiveTab === 'todos' ? 'Todos' : _segActiveTab;
  document.getElementById('seg-tab-title').textContent = `🔄 Seguimiento — ${label} (${filtered.length})`;
  state.filtered['seguimiento'] = filtered;
  state.page['seguimiento'] = 1;
  renderTable('seguimiento', 'seguimiento-table', 'seguimiento-pag');
}

// ─── EDICIÓN GENÉRICA (Seguimiento + Mensajes) ───────────────────────────────
const _segRowMap = {};
const _menColMap = {};
let _segColumnOptions = {};
let _editCtx = { endpoint: '', rowMap: {}, reload: null, label: '' };

// Colores de estado visual — persisten en localStorage
const SEG_COLORS = {
  '':       { hex:'#cbd5e1', bg:'',        border:'',        label:'Sin estado' },
  'yellow': { hex:'#f59e0b', bg:'#fffbeb', border:'#f59e0b', label:'Pendiente envío' },
  'red':    { hex:'#ef4444', bg:'#fef2f2', border:'#ef4444', label:'Urgente' },
  'green':  { hex:'#22c55e', bg:'#f0fdf4', border:'#22c55e', label:'Completado' },
  'blue':   { hex:'#3b82f6', bg:'#eff6ff', border:'#3b82f6', label:'En seguimiento' },
  'orange': { hex:'#f97316', bg:'#fff7ed', border:'#f97316', label:'Esperando resp.' },
  'purple': { hex:'#a855f7', bg:'#faf5ff', border:'#a855f7', label:'Info enviada' },
};
let _segColorMap = {};
try { _segColorMap = JSON.parse(localStorage.getItem('seg_colors') || '{}'); } catch(e) {}
function _saveColorMap() {
  try { localStorage.setItem('seg_colors', JSON.stringify(_segColorMap)); } catch(e) {}
}

function buildColumnOptions(data) {
  const opts = {};
  if (!data.length) return opts;
  const keys = Object.keys(data[0]).filter(k => !k.startsWith('_'));
  keys.forEach(k => {
    const vals = [...new Set(data.map(r => String(r[k] || '').trim()).filter(Boolean))].sort();
    if (vals.length >= 2 && vals.length <= 20) opts[k] = vals;
  });
  return opts;
}

// Conversión de fechas DD/MM/YYYY ↔ YYYY-MM-DD
function toInputDate(val) {
  if (!val) return new Date().toISOString().slice(0, 10);
  const m = val.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})/);
  if (m) return `${m[3]}-${m[2].padStart(2,'0')}-${m[1].padStart(2,'0')}`;
  if (/^\d{4}-\d{2}-\d{2}/.test(val)) return val.slice(0, 10);
  return new Date().toISOString().slice(0, 10);
}
function fromInputDate(val) {
  const m = val.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  return m ? `${m[3]}/${m[2]}/${m[1]}` : val;
}

function _isDateField(k)  { return /fecha|date/i.test(k); }
function _isLongField(k,v){ return /nota|detalle|comentar|observ|descrip|info|mensaje/i.test(k) || String(v).length > 80; }

function openEdit(ctx, rowNum) {
  _editCtx = ctx;
  const row = ctx.rowMap[rowNum];
  if (!row) return;
  const opts = ctx.columnOptions || {};
  const isSeg = ctx.label === 'Seguimiento';
  const fields = Object.entries(row).filter(([k]) => !k.startsWith('_'));

  // ── Color picker ──
  const modal = document.getElementById('edit-seg-modal');
  const colorSection = document.getElementById('edit-color-section');
  if (isSeg) {
    const curColor = _segColorMap[row._row] || '';
    document.getElementById('edit-color-picker').innerHTML = Object.entries(SEG_COLORS).map(([code, c]) =>
      `<div class="color-opt${code===curColor?' selected':''}" data-color="${code}" onclick="selectEditColor(this)"
           title="${c.label}"
           style="background:${code?c.hex:'#e2e8f0'};border:3px solid ${code===curColor?'#1e293b':'transparent'}">
         ${code===curColor?'<span style="position:absolute;inset:0;display:flex;align-items:center;justify-content:center;color:#fff;font-size:.75em;font-weight:900">✓</span>':''}
       </div>`).join('');
    document.getElementById('edit-color-label').textContent = SEG_COLORS[curColor]?.label || '';
    colorSection.style.display = 'flex';
    modal._color = curColor;
  } else {
    colorSection.style.display = 'none';
    modal._color = undefined;
  }

  // ── Fields ──
  const html = fields.map(([k, v]) => {
    const safeK  = k.replace(/"/g,'&quot;');
    const safeV  = String(v).replace(/"/g,'&quot;').replace(/</g,'&lt;');
    const fullRow = _isLongField(k, v) ? 'grid-column:1/-1' : '';
    const icon   = _isDateField(k) ? '📅 ' : '';

    if (_isDateField(k)) {
      return `<div class="edit-field-group" style="${fullRow}">
        <label>${icon}${k}</label>
        <input type="date" data-field="${safeK}" data-type="date" value="${toInputDate(String(v))}">
      </div>`;
    }
    if (opts[k]) {
      const opts2 = opts[k].map(o=>
        `<option value="${o.replace(/"/g,'&quot;')}"${o===String(v).trim()?' selected':''}>${o}</option>`).join('');
      return `<div class="edit-field-group" style="${fullRow}">
        <label>${k}</label>
        <select data-field="${safeK}"><option value=""></option>${opts2}</select>
      </div>`;
    }
    if (_isLongField(k, v)) {
      return `<div class="edit-field-group" style="${fullRow}">
        <label>${k}</label>
        <textarea data-field="${safeK}" rows="3">${String(v).replace(/</g,'&lt;')}</textarea>
      </div>`;
    }
    return `<div class="edit-field-group">
      <label>${k}</label>
      <input data-field="${safeK}" value="${safeV}">
    </div>`;
  }).join('');

  // Subtitle = primer valor no vacío
  const subtitle = (fields.find(([,v]) => String(v).trim())?.[1] || '').slice(0, 55);
  document.getElementById('edit-modal-title').textContent = `✏️ Editar — ${ctx.label}`;
  document.getElementById('edit-modal-subtitle').textContent = subtitle;
  document.getElementById('edit-seg-fields').innerHTML = html;
  modal._rowNum = rowNum;
  modal.style.display = 'block';
}

function selectEditColor(el) {
  const code = el.dataset.color;
  document.querySelectorAll('#edit-color-picker .color-opt').forEach(d => {
    d.style.border = '3px solid transparent';
    d.innerHTML = '';
  });
  el.style.border = '3px solid #1e293b';
  el.innerHTML = '<span style="position:absolute;inset:0;display:flex;align-items:center;justify-content:center;color:#fff;font-size:.75em;font-weight:900">✓</span>';
  document.getElementById('edit-seg-modal')._color = code;
  document.getElementById('edit-color-label').textContent = SEG_COLORS[code]?.label || '';
}

function openEditSeg(rowNum) {
  openEdit({ endpoint: '/api/seguimiento/update', rowMap: _segRowMap,
    columnOptions: _segColumnOptions, label: 'Seguimiento',
    reload: async () => { delete state.loaded['seguimiento']; await loadSeguimiento(); }
  }, rowNum);
}

async function loadMensajes() {
  const data = await fetchAPI('/api/prospectos/mensajes');
  // Poblar mapa por columna
  Object.keys(_menColMap).forEach(k => delete _menColMap[k]);
  data.forEach(d => { _menColMap[d._col] = d; });

  const container = document.getElementById('mensajes-table');
  document.getElementById('mensajes-pag').innerHTML = '';
  if (!data.length) {
    container.innerHTML = '<div class="empty">No hay mensajes configurados</div>';
    return;
  }
  container.innerHTML = `<div class="men-grid">${data.map(d => `
    <div class="men-card">
      <div class="men-card-header">
        <span class="men-card-tipo">💬 ${d.Tipo}</span>
        <button class="btn-edit-row" onclick="openEditMen(${d._col})">✏️ Editar</button>
      </div>
      ${d.Contenido
        ? `<div class="men-card-content">${d.Contenido.replace(/</g,'&lt;').replace(/\n/g,'<br>')}</div>`
        : `<div class="men-card-empty">(Sin contenido)</div>`
      }
    </div>`).join('')}</div>`;
}

function filterMensajes(q) {
  const lq = q.toLowerCase();
  document.querySelectorAll('.men-card').forEach(card => {
    const text = card.textContent.toLowerCase();
    card.style.display = (!lq || text.includes(lq)) ? '' : 'none';
  });
}

function openEditMen(colKey) {
  const row = _menColMap[colKey];
  if (!row) return;
  _editCtx = {
    endpoint: '/api/mensajes/update',
    rowMap: _menColMap,
    label: 'Mensajes',
    reload: async () => { delete state.loaded['mensajes']; await loadMensajes(); }
  };
  const modal = document.getElementById('edit-seg-modal');
  document.getElementById('edit-color-section').style.display = 'none';
  modal._color = undefined;
  modal._rowNum = colKey;
  document.getElementById('edit-modal-title').textContent = `✏️ ${row.Tipo}`;
  document.getElementById('edit-modal-subtitle').textContent = '';
  document.getElementById('edit-seg-fields').innerHTML = `
    <div class="edit-field-group" style="grid-column:1/-1">
      <label>Contenido</label>
      <textarea data-field="Contenido" rows="10" style="min-height:180px">${(row.Contenido || '').replace(/</g,'&lt;')}</textarea>
    </div>`;
  modal.style.display = 'block';
}

function closeEditSeg() {
  document.getElementById('edit-seg-modal').style.display = 'none';
}

async function saveEdit() {
  const modal = document.getElementById('edit-seg-modal');
  const rowNum = modal._rowNum;
  const row = _editCtx.rowMap[rowNum];
  if (!row) return;
  const inputs = modal.querySelectorAll('[data-field]');
  const payload = {};
  if (row._row !== undefined) payload._row = row._row;
  if (row._col !== undefined) payload._col = row._col;
  inputs.forEach(el => {
    payload[el.dataset.field] = el.dataset.type === 'date' ? fromInputDate(el.value) : el.value;
  });
  // Guardar color en localStorage
  if (_editCtx.label === 'Seguimiento' && row._row !== undefined) {
    const color = modal._color !== undefined ? modal._color : '';
    if (color) _segColorMap[row._row] = color;
    else        delete _segColorMap[row._row];
    _saveColorMap();
  }
  const btn = document.getElementById('edit-seg-save');
  btn.textContent = '⏳ Guardando...'; btn.disabled = true;
  try {
    const res = await fetch(_editCtx.endpoint, {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (data.ok) {
      closeEditSeg();
      if (_editCtx.reload) await _editCtx.reload();
    } else {
      alert('Error: ' + (data.error || 'No se pudo guardar'));
    }
  } catch(e) { alert('Error de conexión'); }
  btn.textContent = '💾 Guardar cambios'; btn.disabled = false;
}

// ─── UTILS ──────────────────────────────────────────────────────────────────
function destroyChart(id) {
  if (charts[id]) { charts[id].destroy(); delete charts[id]; }
}

function updateCacheBadge() {
  document.getElementById('cache-badge').textContent = 'Actualizado ' + new Date().toLocaleTimeString('es-MX', {hour:'2-digit',minute:'2-digit'});
}

async function refreshData() {
  await fetch('/api/refresh', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({key:'all'}) });
  Object.keys(state.loaded).forEach(k => delete state.loaded[k]);
  ['chartResultados','chartSemanas','chartCiudades','chartVentasMes'].forEach(destroyChart);
  loadSection(state.currentSection);
}

// ─── BUSCAR IMAGEN EN DRIVE ──────────────────────────────────────────────────
async function buscarEnDrive(nombreEnc, factura) {
  const cell = document.getElementById(`pago-cell-${factura}`);
  if (cell) cell.innerHTML = '<span style="font-size:.78em;color:#888">🔍 Buscando...</span>';

  try {
    const res = await fetch(`/api/ventas/buscar-imagen?nombre=${nombreEnc}`);
    const data = await res.json();

    if (data.encontrado) {
      // Actualizar celda visualmente
      if (cell) {
        cell.innerHTML = `<span style="display:flex;align-items:center;gap:6px">
          <img src="${data.thumb}" style="height:40px;border-radius:4px;cursor:pointer;border:1px solid #dde" onclick="verImagen('${data.url}','${data.thumb}')">
          <a href="${data.url}" target="_blank" style="color:var(--blue);font-size:.78em">🔍 Abrir</a>
        </span>`;
      }
      // Actualizar el sheet con la URL encontrada
      const form = new FormData();
      form.append('num_factura', factura);
      form.append('url_existente', data.url);
      await fetch('/api/ventas/update-pago-url', { method: 'POST', body: form });
    } else {
      if (cell) cell.innerHTML = `<span style="display:flex;align-items:center;gap:5px">
        <span style="font-size:.72em;color:#888">No en Drive</span>
        <button class="btn-upload-pago" onclick="abrirUpload('${factura}',this)">📤 Subir</button>
      </span>`;
    }
  } catch(e) {
    if (cell) cell.innerHTML = `<button class="btn-upload-pago" onclick="abrirUpload('${factura}',this)">📤 Subir</button>`;
  }
}

// ─── UPLOAD PAGO ─────────────────────────────────────────────────────────────
function abrirUpload(numFactura, btn) {
  const modal = document.getElementById('modal-upload');
  document.getElementById('upload-factura').value = numFactura;
  document.getElementById('upload-preview').innerHTML = '';
  document.getElementById('upload-status').textContent = '';
  document.getElementById('upload-file').value = '';
  document.getElementById('upload-factura-display').textContent = numFactura || '(sin factura)';
  modal.style.display = 'flex';
  state._uploadBtn = btn;
}

function cerrarUpload() {
  document.getElementById('modal-upload').style.display = 'none';
}

function previewImagen(input) {
  const file = input.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = e => {
    document.getElementById('upload-preview').innerHTML =
      `<img src="${e.target.result}" style="max-height:160px;border-radius:8px;border:1px solid #dde;margin-top:8px">`;
  };
  reader.readAsDataURL(file);
}

async function subirComprobante() {
  const fileInput = document.getElementById('upload-file');
  const numFactura = document.getElementById('upload-factura').value;
  const statusEl = document.getElementById('upload-status');
  const btnSubir = document.getElementById('btn-subir');

  if (!fileInput.files[0]) {
    statusEl.textContent = '⚠️ Selecciona una imagen primero';
    statusEl.style.color = 'orange';
    return;
  }

  btnSubir.disabled = true;
  statusEl.textContent = '⏳ Subiendo...';
  statusEl.style.color = '#0047CC';

  const form = new FormData();
  form.append('imagen', fileInput.files[0]);
  form.append('num_factura', numFactura);

  try {
    const res = await fetch('/api/ventas/upload-pago', { method: 'POST', body: form });
    const data = await res.json();

    if (data.ok) {
      statusEl.textContent = '✅ Comprobante subido correctamente';
      statusEl.style.color = 'green';
      // Actualizar preview con la imagen de Drive
      if (data.thumb) {
        document.getElementById('upload-preview').innerHTML =
          `<img src="${data.thumb}" style="max-height:160px;border-radius:8px;border:1px solid #dde;margin-top:8px">
           <div style="margin-top:6px"><a href="${data.url}" target="_blank" style="color:var(--blue);font-size:.82em">Ver en Drive →</a></div>`;
      }
      // Actualizar celda en la tabla sin recargar todo
      if (state._uploadBtn) {
        const td = state._uploadBtn.closest('td');
        if (td && data.url) {
          const fileId = data.url.match(/\/d\/([^/]+)\//)?.[1] || '';
          const thumb = fileId ? `https://drive.google.com/thumbnail?id=${fileId}&sz=w120` : '';
          td.innerHTML = `<span style="display:flex;align-items:center;gap:6px">
            ${thumb ? `<img src="${thumb}" style="height:40px;border-radius:4px;cursor:pointer;border:1px solid #dde" onclick="verImagen('${data.url}','${thumb}')">` : ''}
            <a href="${data.url}" target="_blank" style="color:var(--blue);font-size:.78em">Ver →</a>
          </span>`;
        }
      }
      // Invalidar cache
      fetch('/api/refresh', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({key:'ventas'}) });
      setTimeout(cerrarUpload, 2000);
    } else {
      statusEl.textContent = '❌ Error: ' + (data.error || 'desconocido');
      statusEl.style.color = 'red';
      btnSubir.disabled = false;
    }
  } catch (e) {
    statusEl.textContent = '❌ Error de red: ' + e.message;
    statusEl.style.color = 'red';
    btnSubir.disabled = false;
  }
}

function verImagen(url, full) {
  const m   = document.getElementById('modal-imagen');
  const img = document.getElementById('img-full');
  img.src = '';
  img.style.opacity = '0';
  img.onload = () => { img.style.transition = 'opacity .3s'; img.style.opacity = '1'; };
  img.src = full || url;
  document.getElementById('img-link').href = url;
  m.style.display = 'flex';
}

function cerrarImagen() {
  document.getElementById('modal-imagen').style.display = 'none';
}

// ─── LISTENER GLOBAL THUMBNAILS PAGO ────────────────────────────────────────
document.addEventListener('click', function(e) {
  const img = e.target.closest('.pago-thumb');
  if (!img) return;
  const full = img.getAttribute('data-full');
  const link = img.getAttribute('data-link');
  if (full || link) verImagen(link, full);
});

// ─── ENVÍOS DE CATÁLOGO — números a corregir ─────────────────────────────────
const CAT_ESTADOS_PROBLEMA = ['NUMERO_INVALIDO', 'FALLO'];
let _catSel = null;
function _catEsc(s){ return String(s==null?'':s).replace(/[&<>"']/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }

async function _catFetchProblema(){
  const [inv, fall] = await Promise.all([
    fetch('/api/catalogo/envios?estado=NUMERO_INVALIDO').then(r=>r.json()),
    fetch('/api/catalogo/envios?estado=FALLO').then(r=>r.json()),
  ]);
  return [].concat(inv.envios||[], fall.envios||[]);
}

function _catTag(estado){
  const e = String(estado||'').toUpperCase();
  if (e==='ENVIADO') return '<span class="tag aprobado">Enviado</span>';
  if (e==='NUMERO_INVALIDO') return '<span class="tag negado">Número inválido</span>';
  if (e==='FALLO') return '<span class="tag no-compatible">Falló</span>';
  if (e==='PENDIENTE') return '<span class="tag buzon">Pendiente</span>';
  if (e==='EN_PROCESO') return '<span class="tag default">En proceso</span>';
  return '<span class="tag default">'+_catEsc(estado)+'</span>';
}

async function loadCatalogo(){
  const filtro = document.getElementById('cat-filtro').value;
  const cont = document.getElementById('catalogo-table');
  cont.innerHTML = '<div class="loading"><div class="spinner"></div></div>';
  let envios = [];
  try {
    if (filtro === 'problema') envios = await _catFetchProblema();
    else { const d = await fetch('/api/catalogo/envios'+(filtro?('?estado='+filtro):'')).then(r=>r.json()); envios = d.envios||[]; }
  } catch(e){ cont.innerHTML = '<div class="empty" style="color:#e74c3c">⚠️ Error al cargar los envíos.</div>'; return; }
  renderCatalogo(envios);
  actualizarBadgeCatalogo();
}

function renderCatalogo(envios){
  const cont = document.getElementById('catalogo-table');
  if (!envios.length){ cont.innerHTML = '<div class="empty">Sin envíos en este filtro. 🎉</div>'; return; }
  const rows = envios.map(e=>{
    const prob = CAT_ESTADOS_PROBLEMA.includes(String(e.estado).toUpperCase());
    const acc = prob
      ? `<button class="btn-refresh" style="padding:4px 10px;font-size:.76em" onclick='catAbrirCorregir(${JSON.stringify(e).replace(/'/g,"&#39;")})'>✏️ Corregir</button> `
        + `<button class="btn-refresh" style="padding:4px 10px;font-size:.76em" onclick="catReintentar(${e._row})">🔁 Reintentar</button>`
      : '—';
    return `<tr><td>${_catEsc(e.tienda)}</td><td>${_catEsc(e.telefono)}</td><td>${_catTag(e.estado)}</td>`
         + `<td style="text-align:center">${_catEsc(e.intentos)}</td><td style="font-size:.8em;color:#777">${_catEsc(e.timestamp_estado)}</td><td>${acc}</td></tr>`;
  }).join('');
  cont.innerHTML = `<table><thead><tr><th>Tienda</th><th>Teléfono</th><th>Estado</th><th>Intentos</th><th>Actualizado</th><th>Acción</th></tr></thead><tbody>${rows}</tbody></table>`;
}

async function actualizarBadgeCatalogo(){
  try {
    const envios = await _catFetchProblema();
    const badge = document.getElementById('cat-badge');
    if (!badge) return;
    if (envios.length){ badge.textContent = envios.length; badge.style.display='inline-block'; }
    else badge.style.display='none';
  } catch(e){ /* silencioso */ }
}

function catAbrirCorregir(e){
  _catSel = e;
  document.getElementById('modal-corregir-cat').style.display = 'flex';
  document.getElementById('cat-corr-tienda').textContent = e.tienda || '';
  const inp = document.getElementById('cat-corr-input'); inp.value = ''; inp.focus();
  document.getElementById('cat-corr-error').textContent = '';
  document.getElementById('cat-corr-btn').disabled = true;
}
function catValidarCorregir(){
  const v = document.getElementById('cat-corr-input').value;
  const dig = (v.match(/\d/g)||[]).length; const ok = dig>=10 && dig<=13;
  document.getElementById('cat-corr-btn').disabled = !ok;
  document.getElementById('cat-corr-error').textContent = (v && !ok) ? 'Deben ser 10 a 13 dígitos.' : '';
  return ok;
}
async function catGuardarCorreccion(){
  if (!catValidarCorregir() || !_catSel) return;
  const btn = document.getElementById('cat-corr-btn'); btn.disabled = true;
  try {
    const r = await fetch('/api/catalogo/corregir-numero', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ envio_row: _catSel._row, telefono: document.getElementById('cat-corr-input').value, contacto_row: _catSel.fila_respuesta })
    });
    const d = await r.json();
    if (d.ok) { catCerrarModal(); loadCatalogo(); }
    else { document.getElementById('cat-corr-error').textContent = d.error || 'No se pudo corregir.'; btn.disabled = false; }
  } catch(e){ document.getElementById('cat-corr-error').textContent = 'Error de conexión.'; btn.disabled = false; }
}
async function catReintentar(row){
  try {
    const r = await fetch('/api/catalogo/reintentar', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ envio_row: row }) });
    const d = await r.json();
    if (!d.ok) alert('⚠️ ' + (d.error || 'No se pudo reintentar.'));
    loadCatalogo();
  } catch(e){ alert('⚠️ Error de conexión.'); }
}
function catCerrarModal(){ document.getElementById('modal-corregir-cat').style.display = 'none'; }

// ─── INIT ────────────────────────────────────────────────────────────────────
loadSection('dashboard');
actualizarBadgeCatalogo();  // badge de "números a corregir" desde el arranque

// ─── PROSPECTOS BRUCE ────────────────────────────────────────────────────────
let _bruceData = [];

function _initBruceForm() {
  const now = new Date();
  const dd = String(now.getDate()).padStart(2,'0');
  const mm = String(now.getMonth()+1).padStart(2,'0');
  const yy = now.getFullYear();
  const hh = String(now.getHours()).padStart(2,'0');
  const mi = String(now.getMinutes()).padStart(2,'0');
  document.getElementById('bf-fecha').value = `${dd}/${mm}/${yy} ${hh}:${mi}`;
}

async function loadBruce() {
  _initBruceForm();
  const data = await fetchAPI('/api/bruce/prospectos');
  _bruceData = data;
  renderBruceTable(data);
}

function filterBruce(q) {
  const lq = q.toLowerCase();
  const filtered = lq ? _bruceData.filter(r =>
    Object.values(r).some(v => String(v).toLowerCase().includes(lq))
  ) : _bruceData;
  renderBruceTable(filtered);
}

function renderBruceTable(data) {
  const container = document.getElementById('bruce-table');
  document.getElementById('bruce-pag').innerHTML = '';
  if (!data.length) {
    container.innerHTML = '<div class="empty">Sin prospectos aún</div>';
    return;
  }
  let html = `<table><thead><tr>
    <th>Fecha</th><th>Nombre</th><th>Teléfono</th><th>Tipo de Interés</th>
    <th style="text-align:center">Contactado</th><th>NOTA</th><th style="width:60px"></th>
  </tr></thead><tbody>`;
  data.forEach(r => {
    const casilla = (r['Contactado'] || '').trim() === '✓';
    html += `<tr>
      <td style="white-space:nowrap;font-size:.8em">${r['Fecha'] || ''}</td>
      <td style="font-weight:600">${r['Nombre'] || ''}</td>
      <td>${r['Teléfono'] || ''}</td>
      <td>${r['Tipo de Interés'] || ''}</td>
      <td style="text-align:center">
        <span class="bruce-casilla" onclick="toggleContactadoBruce(${r._row}, this)" title="Marcar/desmarcar">
          ${casilla ? '✅' : '⬜'}
        </span>
      </td>
      <td style="font-size:.82em;max-width:220px;word-break:break-word">${(r['NOTA'] || '').replace(/</g,'&lt;').replace(/\n/g,'<br>')}</td>
      <td><button class="btn-edit-row" onclick="editNotaBruce(${r._row})">✏️</button></td>
    </tr>`;
  });
  html += '</tbody></table>';
  container.innerHTML = html;
}

async function agregarBruce() {
  const nombre = document.getElementById('bf-nombre').value.trim();
  if (!nombre) { alert('El Nombre es obligatorio'); return; }
  const payload = {
    'Nombre':         nombre,
    'Teléfono':       document.getElementById('bf-tel').value.trim(),
    'Tipo de Interés':document.getElementById('bf-tipo').value.trim(),
    'NOTA':           document.getElementById('bf-nota').value.trim(),
  };
  const btn = document.querySelector('#bruce-form .btn-blue');
  btn.textContent = '⏳ Guardando...'; btn.disabled = true;
  try {
    const res = await fetch('/api/bruce/agregar', {
      method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)
    });
    const d = await res.json();
    if (d.ok) {
      ['bf-nombre','bf-tel','bf-tipo','bf-nota'].forEach(id => document.getElementById(id).value = '');
      delete state.loaded['bruce'];
      await loadBruce();
    } else { alert('Error: ' + (d.error || 'No se pudo guardar')); }
  } catch(e) { alert('Error de conexión'); }
  btn.textContent = '➕ Agregar Prospecto'; btn.disabled = false;
}

async function toggleContactadoBruce(rowNum, el) {
  const actual = el.textContent.trim() === '✅';
  const nuevo  = actual ? '' : '✓';
  el.textContent = nuevo ? '✅' : '⬜';
  await fetch('/api/bruce/actualizar', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({ _row: rowNum, 'Contactado': nuevo })
  });
  const rec = _bruceData.find(r => r._row === rowNum);
  if (rec) rec['Contactado'] = nuevo;
}

function editNotaBruce(rowNum) {
  const rec = _bruceData.find(r => r._row === rowNum);
  if (!rec) return;
  _editCtx = {
    endpoint: '/api/bruce/actualizar',
    rowMap: Object.fromEntries(_bruceData.map(r => [r._row, r])),
    label: 'Bruce',
    reload: async () => { delete state.loaded['bruce']; await loadBruce(); }
  };
  const modal = document.getElementById('edit-seg-modal');
  document.getElementById('edit-color-section').style.display = 'none';
  modal._color = undefined;
  modal._rowNum = rowNum;
  document.getElementById('edit-modal-title').textContent = `✏️ ${rec['Nombre'] || 'Prospecto'}`;
  document.getElementById('edit-modal-subtitle').textContent = rec['Tipo de Interés'] || '';
  document.getElementById('edit-seg-fields').innerHTML = `
    <div class="edit-field-group" style="grid-column:1/-1">
      <label>NOTA</label>
      <textarea data-field="NOTA" rows="8" style="min-height:160px">${(rec['NOTA'] || '').replace(/</g,'&lt;')}</textarea>
    </div>`;
  modal.style.display = 'block';
}
</script>

<!-- MODAL UPLOAD COMPROBANTE -->
<div id="modal-upload" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:999;align-items:center;justify-content:center">
  <div style="background:#fff;border-radius:18px;padding:32px;width:420px;max-width:95vw;box-shadow:0 20px 60px rgba(0,0,0,.3)">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px">
      <h2 style="color:var(--blue);font-size:1.1em;font-weight:700">📎 Subir Comprobante de Pago</h2>
      <button onclick="cerrarUpload()" style="background:none;border:none;font-size:1.4em;cursor:pointer;color:#aaa">✕</button>
    </div>
    <div style="background:var(--blue3);border-radius:10px;padding:10px 14px;margin-bottom:18px;font-size:.85em;color:var(--blue)">
      Factura: <strong id="upload-factura-display"></strong>
    </div>
    <input type="hidden" id="upload-factura">
    <label style="display:block;border:2px dashed #bcd;border-radius:12px;padding:24px;text-align:center;cursor:pointer;transition:border .2s"
           onmouseover="this.style.borderColor='var(--blue)'" onmouseout="this.style.borderColor='#bcd'">
      <div style="font-size:2em;margin-bottom:8px">🖼️</div>
      <div style="font-size:.9em;color:#666;margin-bottom:6px">Arrastra o haz clic para seleccionar</div>
      <div style="font-size:.75em;color:#aaa">JPG, PNG, JPEG, WEBP</div>
      <input type="file" id="upload-file" accept="image/*" style="display:none" onchange="previewImagen(this)">
    </label>
    <div id="upload-preview" style="text-align:center"></div>
    <div id="upload-status" style="text-align:center;margin-top:10px;font-size:.85em;min-height:20px"></div>
    <div style="display:flex;gap:10px;margin-top:18px">
      <button onclick="cerrarUpload()" style="flex:1;padding:11px;border:1px solid #dde;border-radius:10px;background:#fff;cursor:pointer;font-weight:600;color:#888">Cancelar</button>
      <button id="btn-subir" onclick="subirComprobante()" style="flex:2;padding:11px;border:none;border-radius:10px;background:var(--blue);color:#fff;cursor:pointer;font-weight:700;font-size:.95em">⬆️ Subir Comprobante</button>
    </div>
  </div>
</div>

<!-- MODAL VER IMAGEN -->
<div id="modal-imagen" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,.85);z-index:999;align-items:center;justify-content:center;flex-direction:column;gap:14px" onclick="cerrarImagen()">
  <img id="img-full" src="" style="max-width:90vw;max-height:80vh;border-radius:12px;box-shadow:0 8px 40px rgba(0,0,0,.5)" onclick="event.stopPropagation()">
  <div style="display:flex;gap:14px">
    <a id="img-link" href="#" target="_blank" onclick="event.stopPropagation()" style="background:#fff;color:var(--blue);padding:8px 20px;border-radius:8px;text-decoration:none;font-weight:600;font-size:.9em">Abrir en Drive →</a>
    <button onclick="cerrarImagen()" style="background:rgba(255,255,255,.15);border:none;color:#fff;padding:8px 20px;border-radius:8px;cursor:pointer;font-weight:600;font-size:.9em">✕ Cerrar</button>
  </div>
</div>

</body>
</html>"""


# ─── FORMULARIO DE LLAMADAS ──────────────────────────────────────────────────

def get_contacto_pendiente(skip=0):
    """Devuelve el contacto pendiente — misma lógica que llenar_formularios.py."""
    try:
        client = get_gs_client()
        sp = client.open_by_key(SHEET_IDS['contactos'])
        ws = sp.worksheet('LISTA DE CONTACTOS')
        rows = ws.get_all_values()
        if not rows: return None
        headers = rows[0]
        # Buscar columna RESPUESTA por nombre; fallback a columna F (índice 5)
        col_idx = next(
            (i for i, h in enumerate(headers) if str(h).strip().upper() == 'RESPUESTA'),
            5
        )
        print(f"[formulario] col_pendiente='{headers[col_idx] if col_idx < len(headers) else 'F'}' idx={col_idx}")
        encontrados = 0
        for i, row in enumerate(rows[1:], start=2):
            val = row[col_idx] if len(row) > col_idx else ''
            if not str(val).strip():
                if encontrados < skip:
                    encontrados += 1
                    continue
                datos = {headers[j]: (row[j] if j < len(row) else '') for j in range(len(headers))}
                datos['_row'] = i
                datos['_col_respuesta'] = col_idx + 1  # 1-indexed para gspread
                return datos
        return None
    except Exception as e:
        print(f"[formulario] get_contacto_pendiente error: {e}")
        traceback.print_exc()
        return None


def marcar_contacto_procesado(row_num, col_respuesta=6):
    """Marca columna RESPUESTA del contacto como Llamado."""
    try:
        client = get_gs_client()
        sp = client.open_by_key(SHEET_IDS['contactos'])
        ws = sp.worksheet('LISTA DE CONTACTOS')
        # Resolver columna RESPUESTA si no se proporcionó
        if col_respuesta == 6:
            headers = ws.row_values(1)
            col_respuesta = next(
                (i + 1 for i, h in enumerate(headers) if str(h).strip().upper() == 'RESPUESTA'),
                6
            )
        ws.update_cell(row_num, col_respuesta, 'Llamado')
        _cache_pop('contactos')
        print(f"[formulario] fila {row_num} col {col_respuesta} → Llamado")
    except Exception as e:
        print(f"[formulario] marcar error: {e}")
        traceback.print_exc()


def guardar_respuesta_formulario(datos):
    """Guarda respuesta en 'Respuestas de formulario 1' — misma lógica que llenar_formularios.py."""
    try:
        client = get_gs_client()
        sp = client.open_by_key(SHEET_IDS['respuestas'])
        ws = sp.worksheet('Respuestas de formulario 1')

        # Misma lógica que llenar_formularios.py: última fila por columna B (TIENDA)
        col_b = ws.col_values(2)
        ultima_fila = len(col_b) + 1

        fecha_hora = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
        tienda     = datos.get('tienda', '')
        r0         = datos.get('r0', '')
        r1         = datos.get('r1', '')
        r2         = datos.get('r2', '')
        r3         = datos.get('r3', '')
        r4         = datos.get('r4', '')
        r5         = datos.get('r5', '')
        r6         = datos.get('r6', '')
        r7         = datos.get('r7', '')
        resultado  = datos.get('resultado', '')

        # Columna J — igual que llenar_formularios.py
        col_j = ''
        if r7 == 'Colgo':                        col_j = 'Colgo'
        elif r7 == 'Enc No Disponible':          col_j = 'Enc No Disponible'
        elif resultado == 'Enc No Disponible':   col_j = 'Enc No Disponible'
        elif r0 == 'Buzon':                      col_j = 'BUZON'
        elif r0 == 'Telefono Incorrecto':        col_j = 'TELEFONO INCORRECTO'
        elif resultado == 'NEGADO':              col_j = 'No apto'
        elif resultado == 'NO COMPATIBLE':       col_j = 'No compatible'
        elif resultado == 'MARCA UNICA':         col_j = 'Marca Unica'
        elif r7:                                 col_j = r7

        # Solo celdas con valor — igual que llenar_formularios.py
        f = ultima_fila
        actualizaciones = [
            {'range': f'A{f}', 'values': [[fecha_hora]]},
            {'range': f'B{f}', 'values': [[tienda]]},
        ]
        if r1:      actualizaciones.append({'range': f'C{f}', 'values': [[r1]]})
        if r2:      actualizaciones.append({'range': f'D{f}', 'values': [[r2]]})
        if r3:      actualizaciones.append({'range': f'E{f}', 'values': [[r3]]})
        if r4:      actualizaciones.append({'range': f'G{f}', 'values': [[r4]]})
        if r5:      actualizaciones.append({'range': f'H{f}', 'values': [[r5]]})
        if r6:      actualizaciones.append({'range': f'I{f}', 'values': [[r6]]})
        if col_j:   actualizaciones.append({'range': f'J{f}', 'values': [[col_j]]})
        actualizaciones.append(        {'range': f'S{f}', 'values': [[resultado]]})
        if r0:      actualizaciones.append({'range': f'T{f}', 'values': [[r0]]})

        print(f"[formulario] guardando fila {f} → tienda='{tienda}' resultado='{resultado}' r0='{r0}' col_j='{col_j}'")
        ws.batch_update(actualizaciones, value_input_option='RAW')
        _cache_pop('respuestas')
        _cache_pop('all_respuestas')
        print(f"[formulario] OK — fila {f} guardada en '{ws.title}'")
        return True
    except Exception as e:
        print(f"[formulario] ERROR guardar: {e}")
        traceback.print_exc()
        return False


_BRUCE_HEADERS = ['Fecha', 'Nombre', 'Teléfono', 'Tipo de Interés', 'Contactado', 'NOTA']

def get_bruce_ws():
    """Obtiene o crea la hoja PROSPECTOS BRUCE."""
    client = get_gs_client()
    sp = client.open_by_key(SHEET_IDS['bruce'])
    try:
        return sp.worksheet('PROSPECTOS BRUCE')
    except Exception:
        ws = sp.add_worksheet(title='PROSPECTOS BRUCE', rows=1000, cols=10)
        ws.append_row(_BRUCE_HEADERS)
        return ws


def get_bruce_records(force=False):
    now = time.time()
    entrada = None if force else _cache_get('bruce')
    if entrada is not None:
        data, ts = entrada
        if now - ts < CACHE_TTL:
            return data
    try:
        ws = get_bruce_ws()
        rows = ws.get_all_values()
        if not rows or len(rows) < 2:
            return []
        headers = [str(h).strip() for h in rows[0]]
        records = []
        for i, row in enumerate(rows[1:], start=2):
            if not any(str(c).strip() for c in row):
                continue
            padded = list(row) + [''] * (len(headers) - len(row))
            r = {headers[j]: str(padded[j]).strip() for j in range(len(headers))}
            r['_row'] = i
            records.append(r)
        _cache_set('bruce', (records, now))
        return records
    except Exception as e:
        print(f"[bruce] get error: {e}")
        return []


@app.route('/api/bruce/prospectos')
def api_bruce_prospectos():
    return jsonify(get_bruce_records())


@app.route('/api/bruce/agregar', methods=['POST'])
def api_bruce_agregar():
    body = request.json or {}
    nombre   = str(body.get('Nombre', '')).strip()
    telefono = str(body.get('Teléfono', '')).strip()
    tipo     = str(body.get('Tipo de Interés', '')).strip()
    nota     = str(body.get('NOTA', '')).strip()
    if not nombre:
        return jsonify({'error': 'Nombre requerido'}), 400
    try:
        ws = get_bruce_ws()
        fecha = datetime.now().strftime('%d/%m/%Y %H:%M')
        ws.append_row([fecha, nombre, telefono, tipo, '', nota])
        _cache_pop('bruce')
        return jsonify({'ok': True})
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/bruce/actualizar', methods=['POST'])
def api_bruce_actualizar():
    body    = request.json or {}
    row_num = body.get('_row')
    if not row_num:
        return jsonify({'error': 'Falta _row'}), 400
    try:
        import gspread.utils as gsu
        ws = get_bruce_ws()
        headers = [str(h).strip() for h in ws.row_values(1)]
        updates = []
        for field, value in body.items():
            if field.startswith('_'):
                continue
            if field in headers:
                col = headers.index(field) + 1
                a1  = gsu.rowcol_to_a1(int(row_num), col)
                updates.append({'range': a1, 'values': [[str(value)]]})
        if updates:
            ws.batch_update(updates, value_input_option='USER_ENTERED')
        _cache_pop('bruce')
        return jsonify({'ok': True})
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/formulario/siguiente')
def formulario_siguiente():
    skip = int(request.args.get('skip', 0))
    c = get_contacto_pendiente(skip)
    if not c:
        return jsonify({'fin': True})
    return jsonify({'fin': False, 'contacto': c})


@app.route('/api/formulario/guardar', methods=['POST'])
def formulario_guardar():
    try:
        datos = request.json
        ok = guardar_respuesta_formulario(datos)
        return jsonify({'ok': ok})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


# ─── CAPTURA DE CORREO (Plan 4): conclusión "Correo" → columna T de LISTA DE CONTACTOS ──
COL_CORREO_CONTACTOS = 20  # columna T (1-based). Confirmado libre por el owner (T4.1).
# Allowlist estricto (RFC-razonable): excluye < > " ' y metacaracteres → cierra el vector
# de XSS almacenado (un correo con HTML no pasa validación y nunca se escribe en la hoja).
_EMAIL_RE = re.compile(r'^[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}$')


def _sanitizar_correo(correo):
    """Anti formula-injection en Sheets: prefija ' si empieza con =,+,-,@.
    (Se escribe con RAW, que ya evita ejecución de fórmulas; esto es defensa en profundidad.)"""
    correo = (correo or '').strip()
    if correo and correo[0] in ('=', '+', '-', '@'):
        return "'" + correo
    return correo


def _correo_valido(correo):
    correo = (correo or '').strip()
    return bool(correo) and len(correo) <= 254 and _EMAIL_RE.match(correo) is not None


def _columna_telefono_contactos(headers):
    """Indice 1-based de la columna del telefono en 'LISTA DE CONTACTOS'.

    Se buscaba 'TELEFONO'/'TELÉFONO', que nunca existieron en esa hoja: la
    columna real es CONTACTO (la E), que es justo donde el importador escribe
    r['Telefono']. El resultado era un 400 'columna TELÉFONO no encontrada' al
    corregir un numero, y el telefono en blanco en el formulario.
    """
    for i, h in enumerate(headers):
        if str(h).strip().upper() in nc.COLUMNAS_TELEFONO_CONTACTOS:
            return i + 1
    return None


@app.route('/api/formulario/telefono', methods=['POST'])
def formulario_telefono():
    """Actualiza el TELÉFONO del contacto en LISTA DE CONTACTOS (validador pre-envío)."""
    body = request.json or {}
    row = body.get('row')
    telefono = str(body.get('telefono', '')).strip()
    if not row:
        return jsonify({'ok': False, 'error': 'row requerido'}), 400
    try:
        row = int(row)
    except (TypeError, ValueError):
        return jsonify({'ok': False, 'error': 'row inválido'}), 400
    if row < 2:
        return jsonify({'ok': False, 'error': 'row fuera de rango'}), 400
    if not nc.validar_numero(telefono):
        return jsonify({'ok': False, 'error': 'Número inválido (10 a 13 dígitos)'}), 400
    try:
        client = get_gs_client()
        wsc = client.open_by_key(SHEET_IDS['contactos']).worksheet('LISTA DE CONTACTOS')
        filas = wsc.get_all_values()
        if row > len(filas):
            return jsonify({'ok': False, 'error': 'row fuera de rango'}), 400
        headers = filas[0] if filas else []
        tel_col = _columna_telefono_contactos(headers)
        if not tel_col:
            return jsonify({'ok': False,
                            'error': 'columna de telefono no encontrada en LISTA DE CONTACTOS'}), 400
        tel_norm = nc.normalizar_telefono(telefono)
        # La hoja guarda el numero nacional con espacios ('662 353 4185'); el
        # operador la lee a ojo. tel_norm queda para la respuesta y la cola.
        tel_hoja = nc.formatear_telefono_contactos(telefono)
        wsc.batch_update(
            [{'range': gsu.rowcol_to_a1(row, tel_col), 'values': [[tel_hoja]]}],
            value_input_option='RAW',
        )
        _cache_pop('contactos')
        return jsonify({'ok': True, 'telefono': tel_norm})
    except Exception:
        print(f"[telefono] no se pudo actualizar row={row}")
        traceback.print_exc()
        return jsonify({'ok': False, 'error': 'No se pudo actualizar el teléfono'}), 500


@app.route('/api/formulario/correo', methods=['POST'])
def formulario_correo():
    """Guarda el correo del cliente en la celda T{row} de LISTA DE CONTACTOS."""
    body = request.json or {}
    row = body.get('row')
    correo = str(body.get('correo', '')).strip()
    if not row:
        return jsonify({'ok': False, 'error': 'row requerido'}), 400
    try:
        row = int(row)
    except (TypeError, ValueError):
        return jsonify({'ok': False, 'error': 'row inválido'}), 400
    if row < 2:
        return jsonify({'ok': False, 'error': 'row fuera de rango'}), 400
    if not _correo_valido(correo):
        return jsonify({'ok': False, 'error': 'Correo inválido'}), 400
    try:
        client = get_gs_client()
        wsc = client.open_by_key(SHEET_IDS['contactos']).worksheet('LISTA DE CONTACTOS')
        total = len(wsc.get_all_values())
        if row > total:  # cota superior: no escribir fuera del rango de contactos reales
            return jsonify({'ok': False, 'error': 'row fuera de rango'}), 400
        wsc.batch_update(
            [{'range': gsu.rowcol_to_a1(row, COL_CORREO_CONTACTOS),
              'values': [[_sanitizar_correo(correo)]]}],
            value_input_option='RAW',
        )
        _cache_pop('contactos')
        return jsonify({'ok': True})
    except Exception:
        print(f"[correo] no se pudo guardar en LISTA DE CONTACTOS row={row}")
        traceback.print_exc()
        return jsonify({'ok': False, 'error': 'No se pudo guardar el correo'}), 500


# ─── COLA DE ENVÍO DE CATÁLOGO (Plan 3) ──────────────────────────────────────
# La cola vive en la worksheet ENVIOS_CATALOGO del spreadsheet de respuestas.
# El transporte real (envío por WhatsApp) lo hace el worker local `envio_catalogo.py`
# (decisión owner Plan 5 = B). El panel solo encola/consulta/corrige/reintenta.

ENVIOS_WS_NAME = 'ENVIOS_CATALOGO'


def _abrir_ws_envios(crear=True):
    """Devuelve la worksheet ENVIOS_CATALOGO; la crea con encabezados si no existe.
    Distingue 'hoja no existe' (WorksheetNotFound) de errores reales de la API."""
    client = get_gs_client()
    sp = client.open_by_key(SHEET_IDS['respuestas'])
    try:
        return sp.worksheet(ENVIOS_WS_NAME)
    except WorksheetNotFound:
        if not crear:
            raise
        ws = sp.add_worksheet(title=ENVIOS_WS_NAME, rows=2000, cols=len(nc.COLUMNAS_ENVIOS))
        ws.append_row(nc.COLUMNAS_ENVIOS, value_input_option='RAW')
        return ws


def _leer_envios(ws):
    """Devuelve (filas, col) donde `col` mapea nombre→índice 1-based a partir de
    los ENCABEZADOS REALES de la hoja (robusto ante reordenamientos)."""
    filas = ws.get_all_values()
    headers = filas[0] if filas else nc.COLUMNAS_ENVIOS
    return filas, nc.columnas_indexadas(headers)


def _valor_fila(filas, col, envio_row, nombre):
    """Lee la celda `nombre` de la fila `envio_row` (1-based) ya cargada."""
    idx = col.get(nombre)
    if not idx or envio_row - 1 >= len(filas):
        return ''
    fila = filas[envio_row - 1]
    return fila[idx - 1] if idx - 1 < len(fila) else ''


def encolar_envio_catalogo(tienda, telefono, referencia, conclusion):
    """Encola un envío PENDIENTE si la conclusión es elegible. Idempotente por
    `referencia` (fila del contacto en LISTA DE CONTACTOS): no duplica.
    Devuelve dict {ok, estado|motivo, numero_valido}."""
    if not nc.conclusion_elegible(conclusion):
        return {'ok': False, 'motivo': 'conclusion_no_elegible'}
    numero_valido = nc.validar_numero(telefono)
    ws = _abrir_ws_envios()
    filas = ws.get_all_values()
    idx = nc.indice_por_fila_respuesta(filas, referencia)
    if idx is not None:
        # La idempotencia mira solo `fila_respuesta`, no el estado, asi que un
        # contacto ya ENVIADO tambien cae aqui. Devolver un 'ya_encolado' pelado
        # hacia que el panel dijera "Catalogo encolado para envio" cuando en
        # realidad no iba a pasar nada: el operador se quedaba esperando un envio
        # que ya se habia hecho horas antes. Se devuelve el estado real para que
        # el mensaje pueda decir que ocurrio y cuando.
        existente = filas[idx - 1] if idx - 1 < len(filas) else []
        def _col(nombre):
            i = nc.COLUMNAS_ENVIOS.index(nombre)
            return existente[i] if i < len(existente) else ''
        return {
            'ok': True,
            'estado': 'ya_encolado',
            'estado_actual': _col('estado'),
            'desde': _col('timestamp_estado'),
            'envio_row': idx,
            'numero_valido': numero_valido,
        }
    ws.append_row(
        nc.nueva_fila_envio(tienda, telefono, referencia, conclusion),
        value_input_option='RAW',
    )
    _cache_pop('envios_catalogo')
    # numero_valido=False: el worker lo dejará NUMERO_INVALIDO; el frontend puede avisar ya.
    return {'ok': True, 'estado': nc.PENDIENTE, 'numero_valido': numero_valido}


@app.route('/api/catalogo/encolar', methods=['POST'])
def catalogo_encolar():
    body = request.json or {}
    tienda      = str(body.get('tienda', '')).strip()
    telefono    = str(body.get('telefono', '')).strip()
    referencia  = body.get('referencia')
    conclusion  = str(body.get('conclusion', '')).strip()
    if not tienda or referencia in (None, ''):
        return jsonify({'ok': False, 'error': 'tienda y referencia requeridos'}), 400
    try:
        referencia = int(referencia)
    except (TypeError, ValueError):
        return jsonify({'ok': False, 'error': 'referencia inválida'}), 400
    try:
        return jsonify(encolar_envio_catalogo(tienda, telefono, referencia, conclusion))
    except Exception:
        print(f"[catalogo] encolar error tel={nc.enmascarar_telefono(telefono)}")
        traceback.print_exc()
        return jsonify({'ok': False, 'error': 'No se pudo encolar'}), 500


@app.route('/api/catalogo/envios')
def catalogo_envios():
    """Lista los envíos, opcionalmente filtrados por estado."""
    estado = request.args.get('estado', '').strip().upper()
    try:
        ws = _abrir_ws_envios(crear=False)
    except WorksheetNotFound:
        return jsonify({'envios': []})  # aún no se ha encolado nada (caso benigno)
    except Exception:
        print("[catalogo] envios: error abriendo ENVIOS_CATALOGO")
        traceback.print_exc()
        return jsonify({'ok': False, 'error': 'No se pudo leer la cola'}), 500
    filas = ws.get_all_values()
    if not filas:
        return jsonify({'envios': []})
    headers = filas[0]
    envios = []
    for i, fila in enumerate(filas[1:], start=2):
        reg = {headers[j]: (fila[j] if j < len(fila) else '') for j in range(len(headers))}
        reg['_row'] = i
        if estado and str(reg.get('estado', '')).strip().upper() != estado:
            continue
        envios.append(reg)
    return jsonify({'envios': envios})


@app.route('/api/catalogo/corregir-numero', methods=['POST'])
def catalogo_corregir_numero():
    """Corrige el teléfono de un envío NUMERO_INVALIDO/FALLO, lo actualiza en
    LISTA DE CONTACTOS y re-encola (estado → PENDIENTE, intentos+1)."""
    body = request.json or {}
    envio_row    = body.get('envio_row')
    nuevo_tel    = str(body.get('telefono', '')).strip()
    contacto_row = body.get('contacto_row')
    if not envio_row:
        return jsonify({'ok': False, 'error': 'envio_row requerido'}), 400
    if not nc.validar_numero(nuevo_tel):
        return jsonify({'ok': False, 'error': 'Número inválido (deben ser 10 a 13 dígitos)'}), 400
    try:
        envio_row = int(envio_row)
    except (TypeError, ValueError):
        return jsonify({'ok': False, 'error': 'envio_row inválido'}), 400
    try:
        ws = _abrir_ws_envios(crear=False)
        filas, col = _leer_envios(ws)
        if not (2 <= envio_row <= len(filas)):
            return jsonify({'ok': False, 'error': 'envio_row fuera de rango'}), 400
        # Validar transición: solo se corrige un envío reintentable (NUMERO_INVALIDO/FALLO).
        estado_actual = str(_valor_fila(filas, col, envio_row, 'estado')).strip().upper()
        if not nc.transicion_valida(estado_actual, nc.PENDIENTE):
            return jsonify({'ok': False, 'error': f'No se puede corregir desde {estado_actual}'}), 400
        tel_norm = nc.normalizar_telefono(nuevo_tel)
        ahora = datetime.now().strftime(nc.FMT_TIMESTAMP)
        try:
            intentos_actual = int(_valor_fila(filas, col, envio_row, 'intentos') or 0)
        except (TypeError, ValueError):
            intentos_actual = 0
        ws.batch_update([
            {'range': gsu.rowcol_to_a1(envio_row, col['telefono']), 'values': [[tel_norm]]},
            {'range': gsu.rowcol_to_a1(envio_row, col['estado']), 'values': [[nc.PENDIENTE]]},
            {'range': gsu.rowcol_to_a1(envio_row, col['intentos']), 'values': [[str(intentos_actual + 1)]]},
            {'range': gsu.rowcol_to_a1(envio_row, col['timestamp_estado']), 'values': [[ahora]]},
            {'range': gsu.rowcol_to_a1(envio_row, col['detalle']), 'values': [['número corregido, re-encolado']]},
        ], value_input_option='RAW')
        # Actualizar el teléfono en LISTA DE CONTACTOS. Si falla, se REPORTA (no se traga).
        # Fila del contacto en LISTA DE CONTACTOS: se toma del `fila_respuesta` GUARDADO en
        # la propia fila del envío (fuente de verdad), NO del contacto_row que envía el cliente
        # (evita sobrescribir teléfonos de filas arbitrarias / del encabezado).
        contacto_row_real = None
        try:
            contacto_row_real = int(_valor_fila(filas, col, envio_row, 'fila_respuesta'))
        except (TypeError, ValueError):
            contacto_row_real = None
        contacto_actualizado = None
        if contacto_row_real and contacto_row_real >= 2:
            contacto_actualizado = False
            try:
                spc = get_gs_client().open_by_key(SHEET_IDS['contactos'])
                wsc = spc.worksheet('LISTA DE CONTACTOS')
                headers = wsc.row_values(1)
                tel_col = _columna_telefono_contactos(headers)
                if tel_col:
                    wsc.batch_update(
                        [{'range': gsu.rowcol_to_a1(contacto_row_real, tel_col),
                          'values': [[nc.formatear_telefono_contactos(nuevo_tel)]]}],
                        value_input_option='RAW',
                    )
                    contacto_actualizado = True
                _cache_pop('contactos')
            except Exception:
                print(f"[catalogo] corregir: no se pudo actualizar LISTA DE CONTACTOS "
                      f"fila={contacto_row_real} tel={nc.enmascarar_telefono(nuevo_tel)}")
                traceback.print_exc()
        _cache_pop('envios_catalogo')
        resp = {'ok': True, 'estado': nc.PENDIENTE}
        if contacto_actualizado is not None:
            resp['contacto_actualizado'] = contacto_actualizado
            if not contacto_actualizado:
                resp['aviso'] = 'Envío re-encolado, pero no se pudo actualizar el teléfono del contacto.'
        return jsonify(resp)
    except Exception:
        print(f"[catalogo] corregir error tel={nc.enmascarar_telefono(nuevo_tel)}")
        traceback.print_exc()
        return jsonify({'ok': False, 'error': 'No se pudo corregir'}), 500


@app.route('/api/catalogo/reintentar', methods=['POST'])
def catalogo_reintentar():
    """Re-encola un envío FALLO/NUMERO_INVALIDO sin cambiar el número (estado → PENDIENTE)."""
    body = request.json or {}
    envio_row = body.get('envio_row')
    if not envio_row:
        return jsonify({'ok': False, 'error': 'envio_row requerido'}), 400
    try:
        envio_row = int(envio_row)
    except (TypeError, ValueError):
        return jsonify({'ok': False, 'error': 'envio_row inválido'}), 400
    try:
        ws = _abrir_ws_envios(crear=False)
        filas, col = _leer_envios(ws)
        if not (2 <= envio_row <= len(filas)):
            return jsonify({'ok': False, 'error': 'envio_row fuera de rango'}), 400
        estado_actual = str(_valor_fila(filas, col, envio_row, 'estado')).strip().upper()
        if not nc.transicion_valida(estado_actual, nc.PENDIENTE):
            return jsonify({'ok': False, 'error': f'No se puede reintentar desde {estado_actual}'}), 400
        ahora = datetime.now().strftime(nc.FMT_TIMESTAMP)
        ws.batch_update([
            {'range': gsu.rowcol_to_a1(envio_row, col['estado']), 'values': [[nc.PENDIENTE]]},
            {'range': gsu.rowcol_to_a1(envio_row, col['timestamp_estado']), 'values': [[ahora]]},
        ], value_input_option='RAW')
        _cache_pop('envios_catalogo')
        return jsonify({'ok': True, 'estado': nc.PENDIENTE})
    except Exception:
        print("[catalogo] reintentar error")
        traceback.print_exc()
        return jsonify({'ok': False, 'error': 'No se pudo reintentar'}), 500


# ─── HEARTBEAT DEL WORKER LOCAL (Plan 5, transporte B) ───────────────────────
# El worker local (PC del owner) hace POST cada corrida; el panel consulta el estado.
# Nota: con 2 gunicorn workers en el VPS el heartbeat en memoria es best-effort;
# para estado definitivo, el worker también deja timestamp en ENVIOS_CATALOGO.
# El heartbeat NO puede vivir en memoria del proceso: con varios workers de gunicorn
# cada uno tendria el suyo, el POST caeria en uno y la consulta en otro. Medido en el
# VPS con --workers 2, diez consultas seguidas alternaban entre dos timestamps
# distintos; al parar el worker un proceso cruzaria el TTL antes que el otro, el panel
# diria "muerto", el operador refrescaria y diria "vivo". Un monitor que miente al azar
# es peor que no tenerlo. El archivo lo comparten todos los procesos del contenedor.
WORKER_HEARTBEAT_FILE = os.environ.get(
    'WORKER_HEARTBEAT_FILE',
    os.path.join(tempfile.gettempdir(), 'worker_heartbeat.json'))


def _guardar_heartbeat(resumen):
    """Persiste el latido. Escritura atomica: un lector nunca ve un JSON a medias."""
    datos = {'ts': time.time(), 'resumen': resumen}
    tmp = '%s.%d.tmp' % (WORKER_HEARTBEAT_FILE, os.getpid())
    try:
        with open(tmp, 'w', encoding='utf-8') as fh:
            json.dump(datos, fh)
        os.replace(tmp, WORKER_HEARTBEAT_FILE)
    except OSError as e:
        # Sin disco escribible el panel sigue sirviendo: solo se degrada el monitor.
        print("[worker] no se pudo persistir el heartbeat: %s" % e)
        try:
            os.unlink(tmp)
        except OSError:
            pass
    return datos


def _leer_heartbeat():
    """Devuelve el ultimo latido, o ts=None si no hay ninguno o esta corrupto."""
    try:
        with open(WORKER_HEARTBEAT_FILE, encoding='utf-8') as fh:
            datos = json.load(fh)
    except (OSError, ValueError):
        return {'ts': None, 'resumen': None}
    ts = datos.get('ts')
    if not isinstance(ts, (int, float)):
        return {'ts': None, 'resumen': None}
    return {'ts': ts, 'resumen': datos.get('resumen')}


WORKER_HEARTBEAT_TTL = 15 * 60  # 15 min sin heartbeat → "muerto"


@app.route('/api/catalogo/heartbeat', methods=['POST'])
def catalogo_heartbeat():
    """El worker local reporta que está vivo. Exige WORKER_TOKEN (fail-closed)."""
    if not _auth_desactivada():
        esperado = os.environ.get('WORKER_TOKEN')
        provisto = request.headers.get('X-Worker-Token') or ''
        if not esperado or not hmac.compare_digest(str(provisto), str(esperado)):
            return jsonify({'ok': False, 'error': 'no autorizado'}), 401
    body = request.json or {}
    _guardar_heartbeat(body.get('resumen'))
    return jsonify({'ok': True})


@app.route('/api/catalogo/worker-estado')
def catalogo_worker_estado():
    """Estado del worker según el último heartbeat (vivo/desconocido)."""
    latido = _leer_heartbeat()
    ts = latido['ts']
    vivo = bool(ts) and (time.time() - ts) < WORKER_HEARTBEAT_TTL
    return jsonify({
        'vivo': vivo,
        'ultimo_heartbeat': ts,
        'resumen': latido['resumen'],
    })


FORMULARIO_HTML = r"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>NIOVAL — Formulario de Llamadas</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{--blue:#0047CC;--blue2:#003399;--green:#00CC47;--red:#e74c3c;--orange:#e67e22;--gray:#6c757d}
body{font-family:'Segoe UI',sans-serif;background:linear-gradient(135deg,#0047CC,#003399);min-height:100vh;display:flex;align-items:flex-start;justify-content:center;padding:20px}
.card{background:#fff;border-radius:20px;box-shadow:0 20px 60px rgba(0,0,0,.3);width:100%;max-width:600px;overflow:hidden;animation:fadeIn .4s ease}
@keyframes fadeIn{from{opacity:0;transform:translateY(-20px)}to{opacity:1;transform:translateY(0)}}
.header{background:linear-gradient(135deg,#003399,#0047CC);color:#fff;padding:24px 28px;display:flex;align-items:center;gap:14px}
.header img{height:44px;background:#fff;border-radius:10px;padding:5px}
.header h1{font-size:1.2em;font-weight:800}
.header p{font-size:.8em;opacity:.8;margin-top:3px}
.body{padding:24px 28px}
.info-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:20px}
.info-item{background:#f0f4ff;border-radius:10px;padding:12px;border-left:3px solid var(--blue)}
.info-item .lbl{font-size:.68em;color:#888;text-transform:uppercase;letter-spacing:.8px;margin-bottom:4px}
.info-item .val{font-size:.95em;font-weight:600;color:#222;word-break:break-word}
.info-item.full{grid-column:1/-1}
.section-title{font-size:.8em;font-weight:700;color:var(--blue);text-transform:uppercase;letter-spacing:1px;margin-bottom:12px;padding-bottom:6px;border-bottom:2px solid #e6f0ff}
.btn-group{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:16px}
.btn{padding:13px 20px;border:none;border-radius:12px;font-size:.92em;font-weight:700;cursor:pointer;transition:all .2s;flex:1;min-width:120px}
.btn:active{transform:scale(.97)}
.btn-green{background:var(--green);color:#fff}.btn-green:hover{background:#00aa3a}
.btn-red{background:var(--red);color:#fff}.btn-red:hover{background:#c0392b}
.btn-orange{background:var(--orange);color:#fff}.btn-orange:hover{background:#d35400}
.btn-purple{background:#8e44ad;color:#fff}.btn-purple:hover{background:#6c3483}
.btn-gray{background:#95a5a6;color:#fff}.btn-gray:hover{background:#7f8c8d}
.btn-blue{background:var(--blue);color:#fff}.btn-blue:hover{background:var(--blue2)}
.step{display:none}.step.active{display:block}
.badge{display:inline-block;background:#e6f0ff;color:var(--blue);padding:4px 12px;border-radius:20px;font-size:.75em;font-weight:700;margin-bottom:16px}
.links{display:flex;gap:10px;margin-bottom:18px;flex-wrap:wrap}
.link-btn{display:inline-flex;align-items:center;gap:6px;background:#f0f4ff;border:1px solid #c5d8ff;color:var(--blue);padding:8px 14px;border-radius:8px;text-decoration:none;font-size:.82em;font-weight:600;cursor:pointer;transition:all .2s}
.link-btn:hover{background:var(--blue);color:#fff}
.progress{display:flex;gap:4px;margin-bottom:20px}
.prog-step{flex:1;height:5px;border-radius:3px;background:#e6f0ff;transition:background .3s}
.prog-step.done{background:var(--green)}.prog-step.active{background:var(--blue)}
.spinner-box{text-align:center;padding:40px;color:#aaa}
.spinner{display:inline-block;width:32px;height:32px;border:3px solid #dde;border-top-color:var(--blue);border-radius:50%;animation:spin .8s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
.fin{text-align:center;padding:40px}
.fin .icon{font-size:4em;margin-bottom:16px}
.fin h2{color:var(--blue);margin-bottom:8px}
.fin p{color:#888;font-size:.9em}
.stat-row{display:flex;justify-content:space-around;background:#f0f4ff;border-radius:12px;padding:14px;margin-top:16px}
.stat{text-align:center}.stat .n{font-size:1.6em;font-weight:800;color:var(--blue)}.stat .l{font-size:.7em;color:#888;text-transform:uppercase}
</style>
</head>
<body>
<div class="card">
  <div class="header">
    <img src="https://res.cloudinary.com/dipt3jq6r/image/upload/v1764307686/NIOVAL-05_xhfrrh.jpg" onerror="this.style.display='none'">
    <div>
      <h1>NIOVAL — Formulario de Llamadas</h1>
      <p id="header-sub">Cargando contacto...</p>
    </div>
  </div>
  <div class="body">

    <!-- LOADING -->
    <div class="step active" id="step-loading">
      <div class="spinner-box"><div class="spinner"></div><br><br>Cargando contacto...</div>
    </div>

    <!-- CONTACTO INFO -->
    <div class="step" id="step-contacto">
      <div class="badge" id="badge-ciudad">📍 Ciudad</div>
      <div class="info-grid" id="info-grid"></div>
      <div class="links" id="links-contacto"></div>
      <div class="section-title">¿Qué resultado tuvo el contacto?</div>
      <div class="btn-group">
        <button class="btn btn-green" onclick="decidir('APROBADO')">✓ Aprobado</button>
        <button class="btn btn-red"   onclick="decidir('NEGADO')">✗ Negado</button>
      </div>
      <div class="btn-group">
        <button class="btn btn-orange" onclick="decidir('NO COMPATIBLE')">⊘ No Compatible</button>
        <button class="btn btn-purple" onclick="decidir('MARCA UNICA')">◈ Marca Única</button>
      </div>
      <button class="btn btn-gray" onclick="encNoDisp()" style="width:100%;margin-top:4px;font-size:.85em;background:#7f8c8d">👤 Enc. Compras No Disponible</button>
      <button class="btn btn-gray" onclick="saltarContacto()" style="width:100%;margin-top:8px;font-size:.82em">⟶ Saltar este contacto</button>
    </div>

    <!-- PREGUNTA 0: Estado llamada -->
    <div class="step" id="step-p0">
      <div class="progress" id="prog0"></div>
      <div class="section-title">¿Qué sucedió con la llamada?</div>
      <div class="btn-group" style="flex-direction:column">
        <button class="btn btn-green"  onclick="resp0('Respondio')">📞 1 — Respondió</button>
        <button class="btn btn-orange" onclick="resp0('Buzon')">📬 2 — Buzón</button>
        <button class="btn btn-gray"   onclick="resp0('Telefono Incorrecto')">✗ 0 — Teléfono Incorrecto</button>
      </div>
    </div>

    <!-- PREGUNTA 1 -->
    <div class="step" id="step-p1">
      <div class="progress" id="prog1"></div>
      <div class="section-title">¿Algo que requiera tener un proveedor para poder comprar?</div>
      <div id="sel-p1" style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:14px"></div>
      <button class="btn btn-blue" id="btn-p1" onclick="enviarP1()" disabled>→ Continuar</button>
      <div style="display:flex;gap:8px;margin-top:8px">
        <button class="btn btn-gray" onclick="colgo()" style="font-size:.82em;flex:1">📵 Colgó</button>
        <button class="btn btn-gray" onclick="encNoDisp()" style="font-size:.82em;flex:1;background:#7f8c8d">👤 Enc. No Dispo</button>
      </div>
    </div>

    <!-- PREGUNTA 2 -->
    <div class="step" id="step-p2">
      <div class="progress" id="prog2"></div>
      <div class="section-title">¿Toma usted las decisiones de compra?</div>
      <div class="btn-group">
        <button class="btn btn-green" onclick="resp2('Sí')">✓ Sí</button>
        <button class="btn btn-red"   onclick="resp2('No')">✗ No</button>
      </div>
      <div style="display:flex;gap:8px;margin-top:8px">
        <button class="btn btn-gray" onclick="colgo()" style="font-size:.82em;flex:1">📵 Colgó</button>
        <button class="btn btn-gray" onclick="encNoDisp()" style="font-size:.82em;flex:1;background:#7f8c8d">👤 Enc. No Dispo</button>
      </div>
    </div>

    <!-- PREGUNTA 3 -->
    <div class="step" id="step-p3">
      <div class="progress" id="prog3"></div>
      <div class="section-title">¿Le podemos ayudar con el pedido inicial?</div>
      <div class="btn-group" style="flex-direction:column">
        <button class="btn btn-green" onclick="resp3('Crear Pedido Inicial Sugerido')">✓ Crear Pedido Inicial Sugerido</button>
        <button class="btn btn-red"   onclick="resp3('No')">✗ No</button>
      </div>
      <div style="display:flex;gap:8px;margin-top:8px">
        <button class="btn btn-gray" onclick="colgo()" style="font-size:.82em;flex:1">📵 Colgó</button>
        <button class="btn btn-gray" onclick="encNoDisp()" style="font-size:.82em;flex:1;background:#7f8c8d">👤 Enc. No Dispo</button>
      </div>
    </div>

    <!-- PREGUNTA 4 -->
    <div class="step" id="step-p4">
      <div class="progress" id="prog4"></div>
      <div class="section-title">Pedido Muestra ($1,500 — envío cubierto)</div>
      <div class="btn-group">
        <button class="btn btn-green" onclick="resp4('Sí')">✓ Sí</button>
        <button class="btn btn-red"   onclick="resp4('No')">✗ No</button>
      </div>
      <div style="display:flex;gap:8px;margin-top:8px">
        <button class="btn btn-gray" onclick="colgo()" style="font-size:.82em;flex:1">📵 Colgó</button>
        <button class="btn btn-gray" onclick="encNoDisp()" style="font-size:.82em;flex:1;background:#7f8c8d">👤 Enc. No Dispo</button>
      </div>
    </div>

    <!-- PREGUNTA 5 -->
    <div class="step" id="step-p5">
      <div class="progress" id="prog5"></div>
      <div class="section-title">¿Podemos iniciar esta semana?</div>
      <div class="btn-group">
        <button class="btn btn-green"  onclick="resp5('Sí')">✓ Sí</button>
        <button class="btn btn-red"    onclick="resp5('No')">✗ No</button>
        <button class="btn btn-orange" onclick="resp5('Tal vez')">? Tal vez</button>
      </div>
      <div style="display:flex;gap:8px;margin-top:8px">
        <button class="btn btn-gray" onclick="colgo()" style="font-size:.82em;flex:1">📵 Colgó</button>
        <button class="btn btn-gray" onclick="encNoDisp()" style="font-size:.82em;flex:1;background:#7f8c8d">👤 Enc. No Dispo</button>
      </div>
    </div>

    <!-- PREGUNTA 6 -->
    <div class="step" id="step-p6">
      <div class="progress" id="prog6"></div>
      <div class="section-title">¿Cerramos el pedido con envío gratis + mapeo de top de venta?</div>
      <div class="btn-group">
        <button class="btn btn-green"  onclick="resp6('Sí')">✓ Sí</button>
        <button class="btn btn-red"    onclick="resp6('No')">✗ No</button>
        <button class="btn btn-orange" onclick="resp6('Tal vez')">? Tal vez</button>
      </div>
      <div style="display:flex;gap:8px;margin-top:8px">
        <button class="btn btn-gray" onclick="colgo()" style="font-size:.82em;flex:1">📵 Colgó</button>
        <button class="btn btn-gray" onclick="encNoDisp()" style="font-size:.82em;flex:1;background:#7f8c8d">👤 Enc. No Dispo</button>
      </div>
    </div>

    <!-- PREGUNTA 7: Conclusión -->
    <div class="step" id="step-p7">
      <div class="progress" id="prog7"></div>
      <div class="section-title">Conclusión — ¿Cuál es el siguiente paso?</div>
      <div style="display:flex;flex-direction:column;gap:8px">
        <button class="btn btn-green"  onclick="resp7('Pedido')">📦 Pedido</button>
        <button class="btn btn-blue"   onclick="resp7('Revisara el Catalogo')">📖 Revisará el Catálogo</button>
        <button class="btn btn-blue"   onclick="resp7('Correo')">📧 Correo</button>
        <button class="btn btn-orange" onclick="resp7('Avance (Fecha Pactada)')">📅 Avance (Fecha Pactada)</button>
        <button class="btn btn-orange" onclick="resp7('Continuacion (Cliente Esperando Alguna Situacion)')">⏳ Continuación</button>
        <button class="btn btn-gray"   onclick="resp7('Nulo')">✗ Nulo</button>
      </div>
    </div>

    <!-- FIN / GUARDANDO -->
    <div class="step" id="step-guardando">
      <div class="spinner-box"><div class="spinner"></div><br><br>Guardando respuestas...</div>
    </div>

    <!-- SIGUIENTE CONTACTO -->
    <div class="step" id="step-siguiente">
      <div class="fin">
        <div class="icon">✅</div>
        <h2>Contacto Guardado</h2>
        <p id="resumen-guardado"></p>
        <p id="catalogo-nota" style="margin-top:8px;font-size:.9em;color:var(--blue)"></p>
        <div class="stat-row">
          <div class="stat"><div class="n" id="stat-procesados">0</div><div class="l">Procesados</div></div>
          <div class="stat"><div class="n" id="stat-pendientes">—</div><div class="l">Restantes</div></div>
        </div>
        <button class="btn btn-green" onclick="cargarSiguiente()" style="margin-top:20px;width:100%">→ Siguiente Contacto</button>
        <button class="btn btn-orange" onclick="abrirEnviosProblema()" style="margin-top:8px;width:100%;font-size:.9em">📖 Revisar envíos con problema</button>
      </div>
    </div>

    <!-- MODAL: envíos de catálogo con problema + corrección de número (Plan 3) -->
    <div id="modal-catalogo" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:50;align-items:center;justify-content:center;padding:16px">
      <div style="background:#fff;border-radius:16px;max-width:520px;width:100%;max-height:85vh;overflow:auto;padding:22px">
        <h3 style="margin-bottom:12px;color:var(--blue2)">📖 Envíos de catálogo con problema</h3>
        <div id="envios-lista" style="font-size:.9em"></div>
        <div id="corregir-box" style="display:none;margin-top:14px;border-top:1px solid #eef;padding-top:12px">
          <p style="font-size:.9em;margin-bottom:6px">Corregir número de <b id="corregir-tienda"></b>:</p>
          <input id="corregir-input" type="tel" inputmode="numeric" placeholder="10 a 13 dígitos"
                 style="width:100%;padding:10px;border:1px solid #ccd;border-radius:8px;font-size:1em"
                 oninput="validarCorregir()">
          <p id="corregir-error" style="color:var(--red);font-size:.82em;min-height:16px;margin:4px 0"></p>
          <button id="corregir-btn" class="btn btn-green" style="width:100%" disabled onclick="guardarCorreccion()">Guardar y reintentar</button>
        </div>
        <button class="btn btn-gray" style="width:100%;margin-top:12px" onclick="cerrarModalCatalogo()">Cerrar</button>
      </div>
    </div>

    <!-- MODAL: captura de correo (Plan 4, conclusión "Correo") -->
    <div id="modal-correo" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:50;align-items:center;justify-content:center;padding:16px">
      <div style="background:#fff;border-radius:16px;max-width:460px;width:100%;padding:22px">
        <h3 style="margin-bottom:6px;color:var(--blue2)">📧 Correo del cliente</h3>
        <p style="font-size:.88em;color:var(--gray);margin-bottom:12px">Captura el correo o continúa sin correo.</p>
        <input id="correo-input" type="email" autocomplete="off" placeholder="cliente@dominio.com"
               style="width:100%;padding:11px;border:1px solid #ccd;border-radius:8px;font-size:1em"
               oninput="validarCorreo()" onkeydown="correoKeydown(event)">
        <p id="correo-error" style="color:var(--red);font-size:.82em;min-height:16px;margin:4px 0"></p>
        <button id="correo-btn" class="btn btn-green" style="width:100%" disabled onclick="guardarCorreo()">Guardar correo</button>
        <button class="btn btn-gray" style="width:100%;margin-top:8px" onclick="continuarSinCorreo()">Continuar sin correo</button>
      </div>
    </div>

    <!-- MODAL: validador PRE-envío de catálogo (confirmar/corregir número) -->
    <div id="modal-validar-catalogo" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:50;align-items:center;justify-content:center;padding:16px">
      <div style="background:#fff;border-radius:16px;max-width:480px;width:100%;padding:22px">
        <h3 style="margin-bottom:6px;color:var(--blue2)">📦 Confirmar envío de catálogo</h3>
        <p style="font-size:.9em;color:var(--gray);margin-bottom:12px">
          <b id="val-cat-tienda"></b> — conclusión: <b id="val-cat-conclusion"></b>.<br>
          Verifica que el <b>número de WhatsApp</b> sea correcto antes de enviar. Si lo corriges, se actualiza en LISTA DE CONTACTOS.
        </p>
        <label style="font-size:.82em;color:#555;font-weight:600">Número de WhatsApp (10 dígitos; la lada 52 se añade sola)</label>
        <input id="val-cat-tel" type="tel" inputmode="numeric" placeholder="662 353 4185"
               style="width:100%;padding:11px;border:1px solid #ccd;border-radius:8px;font-size:1em;margin-top:4px"
               oninput="validarValCat()">
        <p id="val-cat-error" style="color:var(--red);font-size:.82em;min-height:16px;margin:4px 0"></p>
        <button id="val-cat-btn" class="btn btn-green" style="width:100%" onclick="confirmarEnviarCatalogo()">✅ Confirmar y enviar catálogo</button>
        <button class="btn btn-gray" style="width:100%;margin-top:8px" onclick="cerrarValidadorCatalogo()">Cancelar</button>
      </div>
    </div>

    <!-- FIN TOTAL -->
    <div class="step" id="step-fin">
      <div class="fin">
        <div class="icon">🎉</div>
        <h2>¡Lista completada!</h2>
        <p>No hay más contactos pendientes por llamar.</p>
        <div class="stat-row">
          <div class="stat"><div class="n" id="stat-total">0</div><div class="l">Total procesados</div></div>
        </div>
        <button class="btn btn-blue" onclick="location.reload()" style="margin-top:20px;width:100%">↻ Recargar</button>
      </div>
    </div>

  </div>
</div>

<script>
const _ventanasAbiertas = [];
function abrirVentana(url) {
  const w = window.open(url, '_blank', 'width=1000,height=700,left=100,top=80');
  if (w) _ventanasAbiertas.push(w);
}
function cerrarVentanasContacto() {
  while (_ventanasAbiertas.length) {
    const w = _ventanasAbiertas.pop();
    try { if (w && !w.closed) w.close(); } catch(e) {}
  }
}

const O = {
  skip: 0,
  procesados: 0,
  contacto: null,
  resultado: '',
  r0:'', r1:'', r2:'', r3:'', r4:'', r5:'', r6:'', r7:'',
  opcionesP1: [],
};

const PASOS = ['loading','contacto','p0','p1','p2','p3','p4','p5','p6','p7','guardando','siguiente','fin'];
const TOTAL_PREGUNTAS = 7;

function showStep(name) {
  PASOS.forEach(p => {
    const el = document.getElementById('step-' + p);
    if (el) el.classList.toggle('active', p === name);
  });
}

function setProgress(stepId, actual, total) {
  const el = document.getElementById(stepId);
  if (!el) return;
  el.innerHTML = Array.from({length: total}, (_,i) =>
    `<div class="prog-step ${i < actual ? 'done' : i === actual ? 'active' : ''}"></div>`
  ).join('');
}

async function cargarContacto() {
  cerrarVentanasContacto();
  showStep('loading');
  document.getElementById('header-sub').textContent = 'Cargando contacto...';
  const r = await fetch(`/api/formulario/siguiente?skip=${O.skip}`);
  const d = await r.json();
  if (d.fin) { showStep('fin'); document.getElementById('stat-total').textContent = O.procesados; return; }
  O.contacto = d.contacto;
  O._telConfirmado = null;   // reset del número confirmado por contacto
  renderContacto(d.contacto);
}

function renderContacto(c) {
  const tienda = c.TIENDA || c.Tienda || c.Nombre || '(Sin nombre)';
  const ciudad = c.CIUDAD || c.Ciudad || '';
  const tel    = c.CONTACTO || c.TELÉFONO || c['Teléfono'] || c.TELEFONO || c.Telefono || '';
  const maps   = c.Maps || c.MAPS || '';
  const link   = c.Link || c.LINK || '';
  const cat    = c['CATEGORIA '] || c.CATEGORIA || c.Categoria || '';
  const esq    = c.Esquema || c.ESQUEMA || '';

  document.getElementById('badge-ciudad').textContent = `📍 ${ciudad || 'Sin ciudad'}`;
  document.getElementById('header-sub').textContent = tienda;

  const campos = [
    {l:'Tienda', v: tienda, full: true},
    {l:'Teléfono', v: tel},
    {l:'Ciudad', v: ciudad},
    {l:'Categoría', v: cat},
    {l:'Esquema', v: esq},
    {l:'Contacto', v: c.CONTACTO || c.Contacto || ''},
  ].filter(x => x.v);

  document.getElementById('info-grid').innerHTML = campos.map(f =>
    `<div class="info-item ${f.full?'full':''}"><div class="lbl">${f.l}</div><div class="val">${f.v}</div></div>`
  ).join('');

  const links = [];
  if (maps && maps.startsWith('http')) links.push(`<button class="link-btn" onclick="abrirVentana('${maps.replace(/'/g,"\\'")}')">🗺️ Google Maps</button>`);
  if (link && link.startsWith('http')) links.push(`<button class="link-btn" onclick="abrirVentana('${link.replace(/'/g,"\\'")}')">🌐 Sitio Web</button>`);
  if (tel) links.push(`<a class="link-btn" href="tel:${tel}">📞 Llamar</a>`);
  document.getElementById('links-contacto').innerHTML = links.join('');

  showStep('contacto');
}

function decidir(resultado) {
  O.resultado = resultado;
  O.r1=''; O.r2=''; O.r3=''; O.r4=''; O.r5=''; O.r6=''; O.r7='';
  if (resultado === 'APROBADO') {
    O.r0 = '';  // se captura en p0
    setProgress('prog0', 0, TOTAL_PREGUNTAS);
    showStep('p0');
  } else {
    // NEGADO / NO COMPATIBLE / MARCA UNICA → el cliente respondió
    O.r0 = 'Respondio';
    guardar();
  }
}

function resp0(v) {
  O.r0 = v;
  if (v === 'Respondio') {
    renderP1();
    setProgress('prog1', 1, TOTAL_PREGUNTAS);
    showStep('p1');
  } else {
    guardar();
  }
}

function renderP1() {
  const opciones = ['Entregas Rápidas','Líneas de Crédito','Contra Entrega','Envío Gratis','Precio Preferente','Evaluar Calidad'];
  O.opcionesP1 = [];
  document.getElementById('sel-p1').innerHTML = opciones.map(op =>
    `<button class="btn btn-blue" style="opacity:.7;font-size:.82em" onclick="toggleP1(this,'${op}')">${op}</button>`
  ).join('');
}

function toggleP1(btn, op) {
  const idx = O.opcionesP1.indexOf(op);
  if (idx > -1) { O.opcionesP1.splice(idx, 1); btn.style.opacity='.7'; }
  else { O.opcionesP1.push(op); btn.style.opacity='1'; btn.style.background='var(--green)'; }
  document.getElementById('btn-p1').disabled = O.opcionesP1.length === 0;
}

function enviarP1() {
  O.r1 = O.opcionesP1.join(', ');
  setProgress('prog2', 2, TOTAL_PREGUNTAS);
  showStep('p2');
}

function resp2(v) { O.r2=v; setProgress('prog3',3,TOTAL_PREGUNTAS); showStep('p3'); }
function resp3(v) { O.r3=v; setProgress('prog4',4,TOTAL_PREGUNTAS); showStep('p4'); }
function resp4(v) { O.r4=v; setProgress('prog5',5,TOTAL_PREGUNTAS); showStep('p5'); }
function resp5(v) { O.r5=v; setProgress('prog6',6,TOTAL_PREGUNTAS); showStep('p6'); }
function resp6(v) { O.r6=v; setProgress('prog7',7,TOTAL_PREGUNTAS); showStep('p7'); }
function resp7(v) {
  O.r7 = v;
  if (v === 'Correo') { abrirModalCorreo(); return; }  // Plan 4: capturar correo antes de guardar
  if (v === 'Pedido' || v === 'Revisara el Catalogo') { abrirValidadorCatalogo(); return; }  // validador pre-envío
  guardar();
}

// ─── Validador PRE-envío de catálogo (confirmar/corregir número antes de encolar) ───
function abrirValidadorCatalogo() {
  const modal = document.getElementById('modal-validar-catalogo');
  modal.style.display = 'flex';
  document.getElementById('val-cat-tienda').textContent =
    O.contacto ? (O.contacto.TIENDA || O.contacto.Tienda || O.contacto.Nombre || '') : '';
  document.getElementById('val-cat-conclusion').textContent = O.r7;
  const inp = document.getElementById('val-cat-tel');
  inp.value = telContacto(O.contacto) || '';
  validarValCat();
  inp.focus();
}
function validarValCat() {
  const v = document.getElementById('val-cat-tel').value;
  const dig = (v.match(/\d/g) || []).length;
  const ok = dig >= 10 && dig <= 13;
  document.getElementById('val-cat-btn').disabled = !ok;
  // Distinguir "el numero guardado esta incompleto" de "lo tecleaste mal": el
  // campo se precarga desde LISTA DE CONTACTOS y hay 131 contactos con menos de
  // 10 digitos (40 con nueve, 26 con siete, y algunos con uno solo). Sin esta
  // distincion el operador cree que se equivoco al teclear.
  const sinTocar = v === (telContacto(O.contacto) || '');
  let msg = '';
  if (v && !ok) {
    msg = (sinTocar && dig > 0 && dig < 10)
      ? 'El número guardado está incompleto (' + dig + ' dígitos). Escribe el número completo de 10 dígitos.'
      : 'Faltan dígitos: se necesitan 10 (o 12 si incluyes la lada 52).';
  }
  document.getElementById('val-cat-error').textContent = msg;
  return ok;
}
async function confirmarEnviarCatalogo() {
  if (!validarValCat()) return;
  const btn = document.getElementById('val-cat-btn'); btn.disabled = true;
  const nuevoTel = document.getElementById('val-cat-tel').value.trim();
  const origDig = (telContacto(O.contacto) || '').replace(/\D/g, '');
  const nuevoDig = nuevoTel.replace(/\D/g, '');
  try {
    // Si el número cambió, actualízalo en LISTA DE CONTACTOS (para este envío y los próximos).
    if (nuevoDig !== origDig && O.contacto && O.contacto._row) {
      const r = await fetch('/api/formulario/telefono', {
        method: 'POST', headers: {'Content-Type':'application/json'},
        body: JSON.stringify({ row: O.contacto._row, telefono: nuevoTel })
      });
      const d = await r.json();
      if (!d.ok) { document.getElementById('val-cat-error').textContent = d.error || 'No se pudo actualizar el número.'; btn.disabled = false; return; }
    }
    O._telConfirmado = nuevoTel;   // encolarCatalogo usará este número
    cerrarValidadorCatalogo();
    guardar();                     // guarda la respuesta y encola con el número confirmado
  } catch(e) {
    document.getElementById('val-cat-error').textContent = 'Error de conexión.'; btn.disabled = false;
  }
}
function cerrarValidadorCatalogo() { document.getElementById('modal-validar-catalogo').style.display = 'none'; }

// ─── Plan 4: captura de correo (conclusión "Correo") ───
function abrirModalCorreo() {
  _enviandoCorreo = false;
  document.getElementById('modal-correo').style.display = 'flex';
  const inp = document.getElementById('correo-input');
  inp.value = ''; inp.disabled = false; inp.focus();
  document.getElementById('correo-error').textContent = '';
  document.getElementById('correo-btn').disabled = true;
}
function validarCorreo() {
  const v = document.getElementById('correo-input').value.trim();
  const ok = /^[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}$/.test(v) && v.length <= 254;
  document.getElementById('correo-btn').disabled = !ok;
  document.getElementById('correo-error').textContent = (v && !ok) ? 'Correo inválido.' : '';
  return ok;
}
function correoKeydown(e) {
  if (e.key === 'Enter') { e.preventDefault(); guardarCorreo(); }
  else if (e.key === 'Escape') { continuarSinCorreo(); }
}
let _enviandoCorreo = false;
async function guardarCorreo() {
  if (_enviandoCorreo || !validarCorreo()) return;  // guard de reentrancia (doble Enter)
  _enviandoCorreo = true;
  const btn = document.getElementById('correo-btn');
  const inp = document.getElementById('correo-input');
  btn.disabled = true; inp.disabled = true;
  const fallar = (msg) => {
    document.getElementById('correo-error').textContent = msg;
    btn.disabled = false; inp.disabled = false; _enviandoCorreo = false;
  };
  try {
    const r = await fetch('/api/formulario/correo', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ row: O.contacto ? O.contacto._row : null,
                             correo: inp.value.trim() })
    });
    const d = await r.json();
    if (d.ok) { cerrarModalCorreo(); guardar(); }  // guardar() tiene su propio guard
    else fallar(d.error || 'No se pudo guardar el correo.');
  } catch(e) { fallar('Error de conexión.'); }
}
function continuarSinCorreo() { if (_enviandoCorreo) return; cerrarModalCorreo(); guardar(); }  // sin escribir T
function cerrarModalCorreo() { document.getElementById('modal-correo').style.display = 'none'; }

function colgo() { O.r7='Colgo'; guardar(); }
function encNoDisp() { O.resultado='Enc No Disponible'; O.r0='Respondio'; O.r7='Enc No Disponible'; guardar(); }

function saltarContacto() { O.skip++; cargarContacto(); }

let _guardando = false;
async function guardar() {
  if (_guardando) return;  // guard de reentrancia: evita filas duplicadas por doble envío
  _guardando = true;
  showStep('guardando');
  const tienda = O.contacto ? (O.contacto.TIENDA || O.contacto.Tienda || O.contacto.Nombre || '') : '';
  const payload = {
    row: O.contacto ? O.contacto._row : null,
    col_respuesta: O.contacto ? (O.contacto._col_respuesta || 6) : 6,
    tienda, resultado: O.resultado,
    r0: O.r0, r1: O.r1, r2: O.r2, r3: O.r3,
    r4: O.r4, r5: O.r5, r6: O.r6, r7: O.r7,
  };
  try {
    const r = await fetch('/api/formulario/guardar', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify(payload)
    });
    const d = await r.json();
    if (!d.ok) {
      _guardando = false;
      showStep('contacto');
      alert('⚠️ Error al guardar: ' + (d.error || 'No se pudo guardar en la hoja. Intenta de nuevo.'));
      return;
    }
    O.procesados++;
    document.getElementById('stat-procesados').textContent = O.procesados;
    document.getElementById('resumen-guardado').textContent =
      `${tienda} → ${O.resultado}${O.r0 && O.r0 !== 'Respondio' ? ' ('+O.r0+')' : ''}`;
    document.getElementById('catalogo-nota').textContent = '';
    showStep('siguiente');
    // Plan 3: si la conclusión dispara catálogo (Pedido / Revisará el Catálogo), encolar el envío.
    encolarCatalogo(tienda);
    _guardando = false;
  } catch(e) {
    _guardando = false;
    showStep('contacto');
    alert('⚠️ Error de conexión al guardar. Verifica tu internet e intenta de nuevo.');
  }
}

// Conclusiones elegibles (mismo criterio que nucleo_catalogo.CONCLUSIONES_ELEGIBLES).
const CONCLUSIONES_CATALOGO = ['pedido', 'revisara el catalogo'];

function telContacto(c) {
  return c ? (c.CONTACTO || c['TELÉFONO'] || c['Teléfono'] || c.TELEFONO || c.Telefono || '') : '';
}

async function encolarCatalogo(tienda) {
  if (!O.r7 || CONCLUSIONES_CATALOGO.indexOf(O.r7.trim().toLowerCase()) === -1) return;
  const nota = document.getElementById('catalogo-nota');
  try {
    const r = await fetch('/api/catalogo/encolar', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({
        tienda,
        telefono: O._telConfirmado || telContacto(O.contacto),
        referencia: O.contacto ? O.contacto._row : null,
        conclusion: O.r7,
      })
    });
    const d = await r.json();
    if (d && d.ok && d.estado === 'ya_encolado') {
      const est = (d.estado_actual || '').toUpperCase();
      const cuando = d.desde ? (' el ' + d.desde) : '';
      if (est === 'ENVIADO')          nota.textContent = '✅ Ya se envió' + cuando + '. No se encola de nuevo.';
      else if (est === 'FALLO')       nota.textContent = '⚠️ Hubo un fallo' + cuando + '. Usa Reintentar para volver a encolarlo.';
      else if (est === 'NUMERO_INVALIDO') nota.textContent = '⚠️ Número inválido' + cuando + '. Corrige el número y reintenta.';
      else                            nota.textContent = '📖 Ya está en la cola (' + (est || 'PENDIENTE') + cuando + ').';
    } else if (d && d.ok) {
      nota.textContent = '📖 Catálogo encolado para envío (' + (d.estado || 'PENDIENTE') + ').';
    }
    else nota.textContent = '⚠️ No se pudo encolar el catálogo.';
  } catch(e) { nota.textContent = '⚠️ No se pudo encolar el catálogo (sin conexión).'; }
}

function escHtml(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, c =>
    ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

let _envioSel = null;

async function abrirEnviosProblema() {
  document.getElementById('modal-catalogo').style.display = 'flex';
  document.getElementById('corregir-box').style.display = 'none';
  const cont = document.getElementById('envios-lista');
  cont.textContent = 'Cargando...';
  try {
    const [inv, fall] = await Promise.all([
      fetch('/api/catalogo/envios?estado=NUMERO_INVALIDO').then(r=>r.json()),
      fetch('/api/catalogo/envios?estado=FALLO').then(r=>r.json()),
    ]);
    const envios = [].concat(inv.envios||[], fall.envios||[]);
    if (!envios.length) { cont.innerHTML = '<p style="color:var(--gray)">Sin envíos con problema. 🎉</p>'; return; }
    cont.innerHTML = envios.map(e =>
      `<div style="border:1px solid #eef;border-radius:8px;padding:8px;margin-bottom:6px">
        <b>${escHtml(e.tienda)}</b> — <span style="color:var(--red)">${escHtml(e.estado)}</span><br>
        <span style="color:var(--gray);font-size:.85em">${escHtml(e.telefono)} · intentos: ${escHtml(e.intentos)}</span><br>
        <button class="btn btn-blue" style="margin-top:4px;font-size:.82em;padding:6px 10px"
          onclick='abrirCorregir(${JSON.stringify(e).replace(/'/g,"&#39;")})'>✏️ Corregir número</button>
      </div>`
    ).join('');
  } catch(e) { cont.textContent = 'Error cargando envíos.'; }
}

function abrirCorregir(envio) {
  _envioSel = envio;
  document.getElementById('corregir-box').style.display = 'block';
  document.getElementById('corregir-tienda').textContent = envio.tienda || '';
  const inp = document.getElementById('corregir-input');
  inp.value = ''; inp.focus();
  document.getElementById('corregir-error').textContent = '';
  document.getElementById('corregir-btn').disabled = true;
}

function validarCorregir() {
  const v = document.getElementById('corregir-input').value;
  const dig = (v.match(/\d/g) || []).length;
  const ok = dig >= 10 && dig <= 13;
  document.getElementById('corregir-btn').disabled = !ok;
  document.getElementById('corregir-error').textContent = (v && !ok) ? 'Deben ser 10 a 13 dígitos.' : '';
  return ok;
}

async function guardarCorreccion() {
  if (!validarCorregir() || !_envioSel) return;
  const btn = document.getElementById('corregir-btn');
  btn.disabled = true;
  try {
    const r = await fetch('/api/catalogo/corregir-numero', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({
        envio_row: _envioSel._row,
        telefono: document.getElementById('corregir-input').value,
        contacto_row: _envioSel.fila_respuesta,
      })
    });
    const d = await r.json();
    if (d.ok) { abrirEnviosProblema(); }
    else { document.getElementById('corregir-error').textContent = d.error || 'No se pudo corregir.'; btn.disabled = false; }
  } catch(e) { document.getElementById('corregir-error').textContent = 'Error de conexión.'; btn.disabled = false; }
}

function cerrarModalCatalogo() { document.getElementById('modal-catalogo').style.display = 'none'; }

function cargarSiguiente() {
  O.skip = 0;  // Resetear skip — el contacto anterior ya fue marcado
  cargarContacto();
}

// Iniciar
cargarContacto();
</script>
</body>
</html>"""


# ─── IMPORTADOR DE CONTACTOS ─────────────────────────────────────────────────

CATEGORIAS_IMPORTADOR = ['Ferreterías', 'Distribuidoras Ferreterías']

# Los UNICOS tres campos que se leen de Place Details. Todo lo demas que se
# exporta (nombre, direccion, calificacion, resenas, coordenadas) sale del Text
# Search, que ya esta pagado.
#
# Sin este parametro, la documentacion de Places legacy es explicita: "if you
# omit the `fields` parameter ... ALL possible fields will be returned, and you
# will be billed accordingly". Eran 50 campos facturados para leer tres, con los
# 18 de Atmosphere (reviews, editorial_summary, price_level...) entre ellos.
#
# Los tres estan en PLACES_DETAIL_FIELDS_CONTACT del cliente instalado, asi que
# la peticion factura base + Contact y deja de facturar Basic + Atmosphere.
# Ver docs/adr/2026-08-28-places-legacy-vs-new.md
CAMPOS_PLACE_DETAILS = ['formatted_phone_number', 'website', 'opening_hours']

# Cortes de gasto (Plan 2 - T2.4). Constantes con nombre, no numeros sueltos.
#
# Solo se corta ante un aporte MEDIDO de cero: no se predice que una consulta no
# va a servir, se comprueba que no sirvio. Y cada corte se registra en el log,
# porque un tope silencioso se lee como "cubri todo" cuando no lo hizo.
MAX_PAGINAS_POR_CONSULTA = 3
MAX_VARIACIONES_SIN_APORTE = 2   # variaciones seguidas con 0 nuevos antes de parar
CORTAR_PAGINAS_SIN_APORTE = True # False deja de cortar por pagina sin tocar codigo

# ─── Cache de Place Details (Plan 2 - T2.5) ──────────────────────────────────
# A quien mas ahorra no es al negocio repetido, sino al RECHAZADO. Un negocio que
# pasa resenas y calificacion pero no tiene telefono paga su Place Details, se
# descarta por `sin_telefono` y nunca llega a la hoja. Como el prefiltro de T2.3
# solo salta lo que esta EN la hoja, ese negocio se vuelve a pagar en cada corrida
# de esa ciudad, indefinidamente.
#
# TTL de 30 dias, no 90: lo que se cachea incluye el telefono que el operador va a
# marcar. Un negocio que anade telefono a su ficha es un prospecto nuevo y no
# conviene tardar un trimestre en verlo. Con 30 dias, quien recorre una ciudad
# cada semana o cada mes ya no paga nada por los rechazados.
#
# Por defecto vive en el temp del sistema, que NO sobrevive a un redespliegue.
# Para que sobreviva hay que montarle un volumen (ver docs/RUNBOOK.md). Sin
# volumen sigue funcionando: se pierde el ahorro, no el servicio.
PLACES_CACHE_FILE = os.environ.get(
    'PLACES_CACHE_FILE',
    os.path.join(tempfile.gettempdir(), 'places_detalles.json'))
PLACES_CACHE_TTL = 30 * 24 * 3600


# ─── Medidor de gasto y tope (Plan 2 - T2.6) ─────────────────────────────────
# Las tarifas van por variable de entorno y NO tienen valor por defecto. Google
# las cambia, y un numero hardcodeado empieza siendo correcto y acaba mintiendo
# sin que nadie lo toque.
#
# Sin tarifa configurada NO se publica importe. Un 0.00 se leeria como "esta
# corrida salio gratis", que es una afirmacion falsa, no una ausencia de dato.
def _float_de_entorno(nombre):
    valor = os.environ.get(nombre, '').strip()
    if not valor:
        return None
    try:
        return float(valor)
    except ValueError:
        print(f'[importador] {nombre} no es un numero ({valor!r}); se ignora')
        return None


PLACES_COSTO_TEXT_SEARCH = _float_de_entorno('PLACES_COSTO_TEXT_SEARCH')
PLACES_COSTO_DETAILS     = _float_de_entorno('PLACES_COSTO_DETAILS')

# Dos topes. El de dinero necesita tarifas; el de llamadas funciona siempre, y es
# el unico utilizable mientras T2.0 siga bloqueada.
PLACES_PRESUPUESTO_CORRIDA   = _float_de_entorno('PLACES_PRESUPUESTO_CORRIDA')
PLACES_MAX_LLAMADAS_CORRIDA  = _float_de_entorno('PLACES_MAX_LLAMADAS_CORRIDA')


class PresupuestoAgotado(Exception):
    """La corrida toco su tope. No es un error: es un limite que se respeto.

    Lleva consigo lo que la categoria en curso ya habia aprobado y PAGADO. Sin
    eso, tocar el tope tiraba a la basura detalles ya cobrados por Google: el
    mensaje prometia "sin repetir lo pagado" y era falso para la categoria que se
    estaba procesando.
    """

    def __init__(self, mensaje, resultados=None, stats=None, incidencias=None):
        super().__init__(mensaje)
        self.resultados = resultados if resultados is not None else []
        self.stats = stats if stats is not None else {}
        self.incidencias = incidencias if incidencias is not None else {}


def _nuevo_medidor():
    return {'text_search': 0, 'place_details': 0, 'cache_hits': 0,
            'duplicados_evitados': 0, 'costo': None}


def _costo_estimado(medidor):
    """Importe estimado, o None si no hay tarifas configuradas."""
    if PLACES_COSTO_TEXT_SEARCH is None or PLACES_COSTO_DETAILS is None:
        return None
    return (medidor['text_search'] * PLACES_COSTO_TEXT_SEARCH
            + medidor['place_details'] * PLACES_COSTO_DETAILS)


def _cobrar(medidor, sku):
    """Apunta una llamada YA HECHA y corta si con ella se paso del tope.

    Se llama DESPUES de la peticion, no antes. Cobrar por adelantado hacia que,
    al saltar el tope, el medidor contara una llamada que nunca llego a hacerse:
    el numero que el operador compara contra la factura de Google salia inflado
    justo en el momento en que mas lo mira.

    Consecuencia asumida: el tope corta en la llamada SIGUIENTE, asi que puede
    excederse por una. Es preferible a que el medidor mienta.
    """
    with _import_lock:
        medidor[sku] += 1
        medidor['costo'] = _costo_estimado(medidor)

    llamadas = medidor['text_search'] + medidor['place_details']
    if PLACES_MAX_LLAMADAS_CORRIDA is not None and llamadas >= PLACES_MAX_LLAMADAS_CORRIDA:
        raise PresupuestoAgotado(
            f'tope de {PLACES_MAX_LLAMADAS_CORRIDA:.0f} llamadas alcanzado '
            f'({medidor["text_search"]} Text Search + '
            f'{medidor["place_details"]} Place Details)')
    if (PLACES_PRESUPUESTO_CORRIDA is not None and medidor['costo'] is not None
            and medidor['costo'] >= PLACES_PRESUPUESTO_CORRIDA):
        raise PresupuestoAgotado(
            f'presupuesto de {PLACES_PRESUPUESTO_CORRIDA} alcanzado '
            f'(estimado {medidor["costo"]:.4f})')


def _leer_cache_places():
    """Cache de detalles, o vacia si no hay o esta ilegible.

    Una cache rota degrada el COSTO, nunca el servicio: si no se puede leer, se
    sigue pegando a la API igual que antes de que existiera.
    """
    try:
        with open(PLACES_CACHE_FILE, encoding='utf-8') as fh:
            datos = json.load(fh)
    except (OSError, ValueError) as e:
        if not isinstance(e, FileNotFoundError):
            print(f'[importador] cache de Places ilegible, se ignora: {e}')
        return {}
    if not isinstance(datos, dict):
        print('[importador] cache de Places con formato inesperado, se ignora')
        return {}
    ahora = time.time()
    vigentes = {}
    for pid, v in datos.items():
        # Cada entrada se valida por separado: una sola mal formada no puede
        # tirar la cache entera, y mucho menos la corrida.
        if not isinstance(v, dict) or not isinstance(v.get('det'), dict):
            continue
        ts = v.get('ts')
        if not isinstance(ts, (int, float)) or isinstance(ts, bool):
            continue
        if ahora - ts < PLACES_CACHE_TTL:
            vigentes[pid] = v
    return vigentes


def _guardar_cache_places(cache):
    """Escritura atomica. Que falle no puede tumbar una corrida."""
    tmp = '%s.%d.tmp' % (PLACES_CACHE_FILE, os.getpid())
    try:
        # 0600 y O_EXCL: es el unico archivo del despliegue con telefonos de
        # clientes en reposo. O_EXCL ademas impide que un enlace simbolico
        # plantado en la ruta redirija la escritura.
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as fh:
            json.dump(cache, fh)
        os.replace(tmp, PLACES_CACHE_FILE)
    except Exception as e:
        # Amplio a proposito: json.dump lanza TypeError, no OSError, y esta
        # funcion corre en el `finally`. Dejar escapar cualquier cosa de aqui
        # convertiria una corrida terminada en una corrida "fallida" por un
        # problema que solo afecta al ahorro.
        print(f'[importador] no se pudo guardar la cache de Places: {e}')
        try:
            os.unlink(tmp)
        except OSError:
            pass


def _detalle_de_place(gmaps_client, pid, cache, medidor=None):
    """El detalle de un negocio, de la cache o de la API.

    Solo se guardan los tres campos de CAMPOS_PLACE_DETAILS. Nombre y direccion
    vienen del Text Search y no hacen falta aqui: cuanto menos dato personal
    acabe en disco, mejor.
    """
    entrada = cache.get(pid)
    if entrada is not None:
        if medidor is not None:
            medidor['cache_hits'] += 1
        return entrada.get('det', {}), True
    det = gmaps_client.place(pid, language='es', fields=CAMPOS_PLACE_DETAILS)['result']
    if medidor is not None:
        _cobrar(medidor, 'place_details')   # ya se hizo: ya se paga
    # Se guarda y se DEVUELVE lo mismo, para que una fila fresca y una servida de
    # cache sean identicas. Si se devolviera el crudo, un campo explicitamente
    # nulo llegaria a la hoja distinto segun viniera de la API o del disco.
    guardado = {c: det.get(c) for c in CAMPOS_PLACE_DETAILS if det.get(c) is not None}
    cache[pid] = {'det': guardado, 'ts': time.time()}
    return guardado, False

def _avanzar_progreso(job, hechos=None, total=None, fase=None):
    """Mueve la barra. Nunca hacia atras.

    El denominador se puede ajustar en marcha: si el total crece, la fraccion
    bajaria, y una barra que retrocede se lee como que algo salio mal. Se queda
    en el maximo alcanzado hasta que el avance real lo supere. Si el total se
    recorta y eso adelanta la barra, si se aplica.
    """
    if hechos is not None:
        job['pasos_hechos'] = hechos
    if total is not None:
        job['pasos_total'] = total
    if fase is not None:
        job['fase'] = fase

    tot = job.get('pasos_total') or 0
    if tot > 0:
        cruda = int(round(job.get('pasos_hechos', 0) * 100 / tot))
    else:
        cruda = job.get('fraccion', 0)
    job['fraccion'] = max(job.get('fraccion', 0), min(100, cruda))
    return job['fraccion']


def _nuevo_import_job(ciudad='', status='idle'):
    """Forma canonica del estado del importador.

    Estaba escrita dos veces (al importar el modulo y en importador_iniciar). Con
    dos copias, un contador nuevo se olvida en una de ellas y el trabajo revienta
    con KeyError a media corrida. Una sola definicion, dos llamadas.

    Los cuatro contadores son independientes a proposito: `encontrados` es lo que
    aprobo Places y `nuevos_en_sheet` son las filas que de verdad se escribieron.
    Presentar el primero como si fuera el segundo es el bug que reporto el owner.
    """
    return {
        'status':    status,   # idle | running | done | error
        'ciudad':    ciudad,
        'categoria': '',
        'progreso':  0,        # categorías completadas (para las insignias)
        'total':     len(CATEGORIAS_IMPORTADOR),
        # La barra ya no se mueve por categoria: con dos, `progreso` solo valia
        # 0, 1 o 2 y pasaba minutos clavada en 0 %. Ahora avanza por paso
        # (categoria x variacion x pagina) y el denominador es ajustable, porque
        # el Plan 2 va a recortar variaciones y el total dejara de ser fijo.
        'fraccion':  0,        # 0-100, monotona no decreciente
        'fase':      '',       # etiqueta legible del paso actual
        'pasos_hechos': 0,
        'pasos_total':  0,
        'encontrados':     0,  # pasaron los filtros de Places
        'nuevos_en_sheet': 0,  # filas REALMENTE escritas en la hoja
        'duplicados':      0,  # ya estaban en LISTA DE CONTACTOS
        'descartados':     0,  # rechazados por resenas, calificacion o sin telefono
        'log':        [],
        'error':      '',
        'cancelado':  False,
        'medidor':    _nuevo_medidor(),
    }


_import_job = _nuevo_import_job()
_import_lock = threading.Lock()


# ─── Registro de corrida interrumpida ────────────────────────────────────────
# El hilo del importador es daemon=True: un reinicio del contenedor lo mata a
# media corrida y `_import_job` vuelve a 'idle', asi que el operador ve la
# pantalla limpia como si nunca hubiera lanzado nada.
#
# Este registro existe SOLO para poder decir "se interrumpio". No es el estado
# vivo del trabajo (ese sigue en memoria, que ahora es un unico proceso) y
# **nunca veta** una corrida nueva: persistir 'running' sin comprobar si el
# proceso vive cambiaria "arrancan dos corridas" por "no puede arrancar
# ninguna", que es peor. Por eso se guarda el PID y se comprueba.
#
# No lleva datos personales. `resultados` (nombre, domicilio y telefono de cada
# prospecto) y el log se quedan fuera a proposito: un archivo de estado es un
# log con otro nombre, y las reglas del proyecto prohiben volcarlos.
IMPORT_ESTADO_FILE = os.environ.get(
    'IMPORT_ESTADO_FILE',
    os.path.join(tempfile.gettempdir(), 'importador_estado.json'))

_CAMPOS_PERSISTIDOS = ('status', 'ciudad', 'categoria', 'progreso', 'total',
                       'fraccion', 'fase', 'medidor',
                       'encontrados', 'nuevos_en_sheet', 'duplicados',
                       'descartados', 'error')


def _proceso_vivo(pid):
    """True si el PID sigue corriendo. Ante la duda, True.

    Mismo criterio que worker_catalogo_run.py:65: es preferible dejar un
    'running' de mas que declarar interrumpida una corrida que sigue viva.
    """
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    if os.name == 'nt':
        try:
            salida = subprocess.run(['tasklist', '/FI', f'PID eq {pid}', '/NH'],
                                    capture_output=True, text=True, timeout=10).stdout
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


def _sanear_error(texto):
    """Enmascara datos personales y acota la longitud de un mensaje de error.

    `str(e)` acaba en disco, en Telegram y en stdout. Hoy ninguna excepcion del
    importador incrusta datos de prospectos, pero basta con que una futura se
    formatee con la fila (f"fila invalida: {r}") para filtrar un telefono por los
    tres sitios a la vez. La lista blanca de campos persistidos no protege de eso
    porque `error` es texto libre.

    Misma convencion que nucleo_catalogo.enmascarar_telefono: se dejan los
    ultimos 4 digitos.
    """
    texto = str(texto)

    def _tapar(m):
        d = m.group(0)
        return '*' * (len(d) - 4) + d[-4:]

    # Rachas de 7+ digitos: telefonos. Menos que eso son codigos de error,
    # cuotas y numeros de fila, que hay que poder leer.
    texto = re.sub(r'\d{7,}', _tapar, texto)
    return texto[:400]


def _guardar_estado_importador(job, pid=None):
    """Persiste el registro minimo. Escritura atomica via os.replace."""
    datos = {k: job.get(k) for k in _CAMPOS_PERSISTIDOS}
    datos['error'] = _sanear_error(datos.get('error') or '')
    datos['pid'] = os.getpid() if pid is None else pid
    datos['ts'] = time.time()
    tmp = '%s.%d.tmp' % (IMPORT_ESTADO_FILE, os.getpid())
    try:
        with open(tmp, 'w', encoding='utf-8') as fh:
            json.dump(datos, fh)
        os.replace(tmp, IMPORT_ESTADO_FILE)
    except OSError as e:
        # Sin disco escribible el panel sigue sirviendo: solo se pierde el aviso
        # de "se interrumpio". No es motivo para tumbar una corrida.
        print(f'[importador] no se pudo guardar el estado: {e}')
        try:
            os.unlink(tmp)
        except OSError:
            pass
    return datos


def _leer_estado_importador():
    """Ultimo registro, o None si no hay o esta ilegible.

    Un 'running' cuyo proceso ya no existe se devuelve como 'interrumpido'.
    """
    try:
        with open(IMPORT_ESTADO_FILE, encoding='utf-8') as fh:
            datos = json.load(fh)
    except (OSError, ValueError):
        return None
    if not isinstance(datos, dict) or 'status' not in datos:
        return None
    if datos.get('status') == 'running' and not _proceso_vivo(datos.get('pid')):
        datos['status'] = 'interrumpido'
    return datos


def _buscar_negocios(gmaps_client, categoria, ciudad, vistos=None,
                     con_detalle=None, avisar=None, claves_en_hoja=None,
                     cache_places=None, medidor=None):
    """Busca negocios con filtros de calidad. Campos y lógica idénticos al script original.

    `claves_en_hoja`, si se pasa, es el conjunto de claves `Nombre|Dirección` que
    ya existen en la hoja. Se usa SOLO para leer: un negocio cuya clave esta ahi
    se salta antes de pedir su Place Details, que es donde esta el gasto. Nombre y
    direccion vienen del Text Search, ya pagado, asi que compararlos es gratis.

    `vistos` es el conjunto de place_id ya procesados. Si quien llama pasa el
    suyo, la deduplicacion pasa a ser de CORRIDA en vez de por categoria: una
    ferreteria que sale en 'Ferreterías' y en 'Distribuidoras Ferreterías' es un
    solo negocio, se cuenta una vez y se paga un solo Place Details.

    (El Plan 2 reutiliza este mismo conjunto para no pagar detalles repetidos;
    no se crea una segunda estructura.)
    """
    resultados = []
    if vistos is None:
        vistos = set()
    # Solo cuenta como SOLAPAMIENTO lo que ya estaba visto al entrar, es decir lo
    # que aporto otra categoria. Las tres variaciones de esta misma categoria
    # devuelven en gran parte los mismos negocios; contar eso como solape daria
    # numeros inflados (24 de 12) y no dice nada sobre cuanto se pisan las dos
    # busquedas, que es la pregunta.
    ya_de_otra_categoria = set(vistos)
    # `con_detalle` separa "ya lo vi" de "ya lo PAGUE": un negocio rechazado por
    # resenas se descarta antes de pedir el detalle, asi que saltarselo despues no
    # ahorra dinero. Sin esta distincion, el contador de solapamiento se lee como
    # ahorro de Places y lo sobrestima. El Plan 2 necesita el numero exacto.
    if con_detalle is None:
        con_detalle = set()
    stats  = {'pocas_resenas': 0, 'baja_calificacion': 0, 'cerrado': 0, 'sin_telefono': 0}
    # Distinguir "Places dijo que no hay nada" de "no se pudo preguntar". Sin esto,
    # una clave invalida o la cuota agotada devuelven lista vacia y la corrida
    # termina en 'done' informando "0 aprobados": un fallo de autenticacion
    # presentado como una ciudad sin ferreterias.
    consultas_ok        = 0
    detalles_desde_cache = 0
    cortes              = []  # lo que se dejo de pedir, y por que
    if cache_places is None:
        cache_places = {}
    if medidor is None:
        medidor = _nuevo_medidor()
    ya_en_hoja          = 0   # saltados ANTES de pagar su detalle
    ya_vistos_otra_cat  = 0   # negocios que ya habia procesado OTRA categoria
    detalles_evitados   = 0   # de esos, los que ya habian costado un place()
    detalles_fallidos   = 0
    paginas_fallidas  = 0
    ultimo_error      = None

    variaciones = [
        f"{categoria} en {ciudad}",
        f"{categoria} cerca de {ciudad}",
        f"{categoria} {ciudad}",
    ]

    try:
        variaciones_sin_aporte = 0
        for idx_q, query in enumerate(variaciones, 1):
            if variaciones_sin_aporte >= MAX_VARIACIONES_SIN_APORTE:
                cortes.append(
                    f'{categoria}: se omitieron las variaciones {idx_q}-{len(variaciones)} '
                    f'tras {variaciones_sin_aporte} seguidas que trajeron resultados '
                    f'pero ninguno nuevo')
                break
            consulta_ok = False
            if avisar:
                avisar(f'{categoria} — variación {idx_q} de {len(variaciones)}')
            for intento in range(3):
                # Por INTENTO, no por variacion: un reintento que ocurra despues de
                # haber leido resultados encontraria aqui sus propios place_id y
                # mediria 0 nuevos sobre datos identicos. Ese cero es falso y
                # empuja hacia un corte que nadie se gano.
                ids_de_esta_consulta = set()
                try:
                    resp   = gmaps_client.places(query=query, language='es', type='establishment')
                    _cobrar(medidor, 'text_search')   # ya se hizo: ya se paga
                    consulta_ok = True
                    lugares = resp.get('results', [])
                    aporte_variacion = _aporte_nuevo(lugares, vistos, ids_de_esta_consulta)
                    paginas = 1
                    while 'next_page_token' in resp and paginas < MAX_PAGINAS_POR_CONSULTA:
                        time.sleep(2)
                        try:
                            resp = gmaps_client.places(page_token=resp['next_page_token'])
                            _cobrar(medidor, 'text_search')   # ya se hizo: ya se paga
                            pagina = resp.get('results', [])
                            aporte_pagina = _aporte_nuevo(pagina, vistos, ids_de_esta_consulta)
                            lugares.extend(pagina)
                            paginas += 1
                            aporte_variacion += aporte_pagina
                            if avisar:
                                avisar(f'{categoria} — variación {idx_q} de '
                                       f'{len(variaciones)}, página {paginas}',
                                       extra=True)
                            # Una pagina entera de negocios ya vistos: pedir la
                            # siguiente es pagar por lo mismo otra vez.
                            if CORTAR_PAGINAS_SIN_APORTE and aporte_pagina == 0:
                                cortes.append(
                                    f'{categoria} v{idx_q}: no se pidieron mas paginas '
                                    f'tras la {paginas}, que no trajo ninguno nuevo')
                                break
                        except PresupuestoAgotado:
                            raise            # el tope no es un tropiezo de la API
                        except Exception:
                            paginas_fallidas += 1
                            break

                    # Solo cuenta como "sin aporte" una variacion que TRAJO
                    # resultados y ninguno era nuevo: eso es saturacion, y la
                    # siguiente consulta —casi la misma frase— dara lo mismo.
                    #
                    # Una variacion VACIA no cuenta. Vacio no significa saturado,
                    # significa que esa fraseologia no caso; otra puede casar. Contar
                    # los vacios hacia que dos consultas sin resultados cancelaran la
                    # tercera, y si esa tercera era la que funcionaba, se perdia la
                    # categoria entera.
                    if lugares and aporte_variacion == 0:
                        variaciones_sin_aporte += 1
                    else:
                        # Cualquier cosa que no sea saturacion rompe la racha, y una
                        # variacion vacia no es saturacion. Hoy da igual con 3
                        # variaciones y umbral 2, pero dejarlo implicito es una trampa
                        # para quien anada una cuarta.
                        variaciones_sin_aporte = 0

                    for lugar in lugares:
                        pid     = lugar.get('place_id')
                        if pid in vistos:
                            if pid in ya_de_otra_categoria:
                                ya_de_otra_categoria.discard(pid)  # se cuenta una vez
                                ya_vistos_otra_cat += 1
                                if pid in con_detalle:
                                    detalles_evitados += 1
                            continue
                        cal     = lugar.get('rating')
                        resenas = lugar.get('user_ratings_total')

                        # El place_id se apunta ANTES de filtrar. Estaba despues, con
                        # lo que un negocio rechazado no quedaba registrado y volvia a
                        # contarse en cada variacion y en cada categoria: un solo
                        # negocio con 2 resenas se reportaba como 6 descartados.
                        vistos.add(pid)

                        # Si ya esta en la hoja, no hace falta su detalle: la clave se
                        # arma con nombre y direccion, y los dos vienen del Text
                        # Search. Antes se pagaba el Details, se filtraba por telefono
                        # y solo al exportar se descubria que ya estaba. En una ciudad
                        # ya trabajada eso era el 100 % del gasto de Details tirado.
                        if claves_en_hoja is not None and _clave_contacto(
                                lugar.get('name', ''),
                                lugar.get('formatted_address', '')) in claves_en_hoja:
                            ya_en_hoja += 1
                            medidor['duplicados_evitados'] += 1
                            continue

                        if not resenas or resenas < 5:
                            stats['pocas_resenas'] += 1; continue
                        if not cal or cal < 3.5:
                            stats['baja_calificacion'] += 1; continue
                        try:
                            det, de_cache = _detalle_de_place(
                                gmaps_client, pid, cache_places, medidor)
                            if de_cache:
                                detalles_desde_cache += 1
                            else:
                                con_detalle.add(pid)
                            # Filtro "Cerrado" eliminado — se capturan negocios sin importar horario
                            tel = det.get('formatted_phone_number', '')
                            if not tel:
                                stats['sin_telefono'] += 1; continue

                            tamano = 'Grande' if resenas >= 500 else 'Mediano' if resenas >= 200 else 'Pequeño'
                            resultados.append({
                                'Nombre':          lugar.get('name', ''),
                                'Dirección':        lugar.get('formatted_address', ''),
                                'Calificación':     cal,
                                'Núm. de Reseñas':  resenas,
                                'Google Maps Link': f"https://www.google.com/maps/place/?q=place_id:{pid}",
                                'Teléfono':         tel,
                                'Sitio Web':        det.get('website', 'No disponible'),
                                'Horarios':         str(det.get('opening_hours', {}).get('weekday_text', 'No disponible')),
                                'Estado':           'Abierto',
                                'Latitud':          lugar.get('geometry', {}).get('location', {}).get('lat', ''),
                                'Longitud':         lugar.get('geometry', {}).get('location', {}).get('lng', ''),
                                'Tamaño':           tamano,
                                'Tipo Cliente':     'Mayorista/Corporativo' if resenas > 300 else 'Minorista',
                            })
                            time.sleep(0.3)
                        except PresupuestoAgotado:
                            raise            # el tope no es un tropiezo de la API
                        except Exception:
                            # Un negocio que se cae aqui no aparece ni en `resultados`
                            # ni en `stats`: se evaporaba sin dejar numero.
                            detalles_fallidos += 1
                            continue

                    # Exito: no se reintenta, ni siquiera si vino vacia. Una
                    # consulta que responde BIEN y sin resultados devolvera lo mismo
                    # al repetirla: mismos parametros, misma respuesta. Antes solo se
                    # cortaba `if lugares`, asi que una variacion legitimamente vacia
                    # se lanzaba tres veces identicas.
                    break

                except PresupuestoAgotado:
                    raise            # el tope no es un tropiezo de la API
                except Exception as e:
                    ultimo_error = e
                    print(f'[importador] error query intento {intento+1}: {e}')
                    if intento < 2: time.sleep(2 ** intento)

            if consulta_ok:
                consultas_ok += 1
            if query != variaciones[-1]: time.sleep(1)

        # Ninguna de las variaciones logro hablar con Places: eso no es "no hay
        # resultados", es que no se pudo preguntar. Se propaga, igual que hace
        # _exportar_a_sheets con los fallos de escritura.
    except PresupuestoAgotado as tope:
        # Lo que esta categoria ya aprobo y PAGO viaja con la excepcion. Sin
        # esto, tocar el tope tiraba detalles ya cobrados por Google y el
        # mensaje de 'sin repetir lo pagado' era falso para esta categoria.
        tope.resultados = resultados
        tope.stats = stats
        tope.incidencias = {'ya_en_hoja': ya_en_hoja, 'cortes': cortes,
                            'detalles_desde_cache': detalles_desde_cache,
                            'detalles_fallidos': detalles_fallidos,
                            'paginas_fallidas': paginas_fallidas,
                            'consultas_fallidas': 0,
                            'ya_vistos_otra_cat': ya_vistos_otra_cat,
                            'detalles_evitados': detalles_evitados}
        raise

    if consultas_ok == 0:
        raise RuntimeError(
            f'no se pudo consultar Google Places para {categoria} en {ciudad}: {ultimo_error}'
        )

    incidencias = {'ya_en_hoja': ya_en_hoja,
                   'cortes': cortes,
                   'detalles_desde_cache': detalles_desde_cache,
                   'detalles_fallidos': detalles_fallidos,
                   'paginas_fallidas': paginas_fallidas,
                   'consultas_fallidas': len(variaciones) - consultas_ok,
                   'ya_vistos_otra_cat': ya_vistos_otra_cat,
                   'detalles_evitados': detalles_evitados}
    return resultados, stats, incidencias


def _aporte_nuevo(pagina, vistos, ya_contados):
    """Cuantos place_id de esta pagina NO se habian visto todavia en la corrida.

    Es la medida que decide los cortes de T2.4: no se predice que una consulta no
    va a servir, se comprueba que no sirvio. `ya_contados` se muta para que dos
    paginas de la misma consulta no se acrediten el mismo negocio.
    """
    nuevos = 0
    for lugar in pagina:
        pid = lugar.get('place_id')
        if pid and pid not in vistos and pid not in ya_contados:
            ya_contados.add(pid)
            nuevos += 1
    return nuevos


def _clave_contacto(nombre, direccion):
    """Clave de deduplicacion: la MISMA que usa la hoja (`Nombre|Dirección`).

    Vive aparte a proposito. El prefiltro (antes de pagar Place Details) y la
    exportacion tienen que calcularla igual: si divergen, o se paga el detalle de
    duplicados, o peor, se descartan negocios buenos creyendo que ya estaban.
    """
    return f"{nombre}|{direccion}"


def _escapar_formula(valor):
    """Evita que Sheets interprete un texto como formula.

    Con value_input_option='USER_ENTERED', Sheets parsea lo que empieza por
    '=', '+', '-' o '@' igual que si lo tecleara un usuario. La ferreteria
    "+ Mas Seguro Distribuidora Ferretera" se guardo asi y la celda muestra
    #ERROR!: el texto sigue intacto por debajo, pero el operador ve un error
    en vez del nombre de la tienda al llamarla.

    El apostrofo inicial es la marca de "esto es texto" de Sheets y no forma
    parte del valor almacenado. Solo se toca lo que es cadena: los numeros
    (calificacion, resenas, latitud, longitud) y las fechas deben seguir
    entrando como numero y fecha, que es justo lo que RAW habria roto.
    """
    if isinstance(valor, str) and valor[:1] in ('=', '+', '-', '@'):
        return "'" + valor
    return valor


def _exportar_a_sheets(resultados, categoria, ciudad, claves_existentes=None):
    """Exporta a LISTA DE CONTACTOS con columnas idénticas al script original.

    PROPAGA cualquier fallo de Sheets. Antes lo atrapaba y devolvia 0, con lo que
    "no habia nada nuevo que escribir" y "la escritura reventó" eran el mismo
    numero: la corrida seguia, terminaba en 'done' con palomita verde y el unico
    rastro era un print al stdout del contenedor. Quien llama decide que hacer.
    """
    ws = get_worksheet('contactos')

    # La escritura SIEMPRE relee la hoja. El conjunto que trae quien llama sirve
    # para el prefiltro —donde un duplicado no detectado solo cuesta una llamada
    # de mas— pero aqui se decide que filas se escriben, y ahi un duplicado es un
    # dato malo. Si alguien edito la hoja a mano a media corrida, esta relectura
    # lo ve; el conjunto de la corrida se refresca de paso, asi que la categoria
    # siguiente tambien se entera.
    frescas = _claves_de_la_hoja(ws)
    if claves_existentes is None:
        nombres_existentes = frescas
    else:
        claves_existentes.update(frescas)
        nombres_existentes = claves_existentes

    fecha  = datetime.now().strftime('%d/%m/%Y')
    semana = datetime.now().isocalendar()[1]
    nuevos = []
    claves_nuevas = set()   # se vuelcan al conjunto compartido solo si se escribe

    for r in resultados:
        key = _clave_contacto(r['Nombre'], r['Dirección'])
        if key not in nombres_existentes and key not in claves_nuevas:
            claves_nuevas.add(key)
            # Orden de columnas EXACTO al script original:
            # NUM SEMANA | Nombre | Ciudad | Categoría | Teléfono | "" | "" |
            # Dirección | Calificación | Núm. de Reseñas | Google Maps Link |
            # Sitio Web | Horarios | Estado | Latitud | Longitud | Tamaño | Tipo Cliente | Fecha
            nuevos.append([
                semana,
                r['Nombre'],
                ciudad,
                categoria,
                r['Teléfono'],
                '',
                '',
                r['Dirección'],
                r['Calificación'],
                r['Núm. de Reseñas'],
                r['Google Maps Link'],
                r['Sitio Web'],
                r['Horarios'],
                r['Estado'],
                r['Latitud'],
                r['Longitud'],
                r['Tamaño'],
                r['Tipo Cliente'],
                fecha,
            ])

    if nuevos:
        nuevos = [[_escapar_formula(v) for v in fila] for fila in nuevos]
        ws.append_rows(nuevos, value_input_option='USER_ENTERED')
        # Solo ahora: si append_rows revienta, el conjunto del que depende el
        # prefiltro no se queda afirmando que estos negocios ya estan en la hoja.
        nombres_existentes.update(claves_nuevas)
        _cache_pop('contactos')
    return len(nuevos)


def _claves_de_la_hoja(ws):
    """Las claves `Nombre|Dirección` que ya existen en LISTA DE CONTACTOS.

    Una fila con menos de 8 columnas no tiene domicilio, asi que no se le puede
    construir la clave. Se cuentan y se avisan: cada una es un contacto que el
    dedup no ve y que se reimportara —pagando su detalle— en cada corrida.
    """
    claves = set()
    incompletas = 0
    for fila in ws.get_all_values()[1:]:
        if len(fila) > 7:
            claves.add(_clave_contacto(fila[1], fila[7]))
        elif any(str(c).strip() for c in fila):
            incompletas += 1
    if incompletas:
        print(f'[importador] {incompletas} filas de la hoja sin domicilio: '
              f'quedan fuera del dedup y se reimportarian')
    return claves


def _enviar_telegram_importador(ciudad, resumen, desglose, tiempo_min,
                                error=None, cancelado=False, presupuesto=None):
    try:
        token   = os.environ.get('TELEGRAM_TOKEN')
        chat_id = os.environ.get('TELEGRAM_CHAT_ID')
        if not token or not chat_id:
            return
        msg = (
            f"<b>{'⛔ Importador: TOPE DE GASTO' if presupuesto else ('❌ Importador FALLÓ' if error else ('⏹ Importador DETENIDO' if cancelado else '📥 Importador Completado'))}</b>\n\n"
            f"<b>Ciudad:</b> {ciudad}\n"
            + (f"<b>Causa:</b> {error or presupuesto}\n" if (error or presupuesto) else "")
            + f"<b>Nuevos en la hoja:</b> {resumen['nuevos']}\n"
            + f"<b>Aprobados por filtros:</b> {resumen['encontrados']}\n"
            + f"<b>Ya estaban:</b> {resumen['duplicados']}\n"
            + f"<b>Descartados:</b> {resumen['descartados']}\n"
            + f"<b>Tiempo:</b> {tiempo_min:.1f} min\n\n"
        )
        med = (resumen or {}).get('medidor') or {}
        if med:
            msg += (f"<b>Llamadas a Places:</b> {med.get('text_search', 0)} búsquedas"
                    f" + {med.get('place_details', 0)} detalles\n")
            evitadas = med.get('cache_hits', 0) + med.get('duplicados_evitados', 0)
            if evitadas:
                msg += f"<b>Llamadas evitadas:</b> {evitadas}\n"
            if med.get('costo') is not None:
                msg += f"<b>Costo estimado:</b> {med['costo']:.2f}\n"
            msg += "\n"
        for cat, n in desglose.items():
            msg += f"  {cat}: {n} aprobados\n"
        req_lib.post(f'https://api.telegram.org/bot{token}/sendMessage',
                     data={'chat_id': chat_id, 'text': msg, 'parse_mode': 'HTML'}, timeout=10)
    except Exception as e:
        # Este aviso ES la via por la que el owner se entera de que algo fallo.
        # Tragarselo lo deja sin enterarse de nada, que es justo lo que esta
        # tarea vino a arreglar.
        print(f'[importador] no se pudo avisar por telegram: {e}')
        traceback.print_exc()


def _worker_importador(ciudad, gmaps_api_key):
    inicio = time.time()
    desglose = {}
    cache_places = {}
    try:
        if not GMAPS_OK:
            raise RuntimeError('googlemaps no instalado')

        gmaps = googlemaps.Client(key=gmaps_api_key)
        todos = []
        # Un solo conjunto para toda la corrida. Antes vivia dentro de
        # _buscar_negocios, o sea que se reiniciaba en cada categoria y el mismo
        # negocio se contaba (y se pagaba) dos veces.
        vistos_corrida = set()
        con_detalle_corrida = set()
        # La hoja se lee UNA vez por corrida. Sirve para dos cosas: saltar el
        # Place Details de lo que ya esta (que es donde esta el ahorro) y evitar
        # releer ~7,000 filas una vez por categoria.
        claves_en_hoja = _claves_de_la_hoja(get_worksheet('contactos'))
        # Una sola lectura por corrida; se guarda en el `finally`, pase lo que pase.
        cache_places.update(_leer_cache_places())
        with _import_lock:
            medidor = _import_job['medidor']

        # Presupuesto de pasos GARANTIZADOS por categoria: 1 al preparar, 3 (una
        # por variacion, que siempre corren) y 1 al guardar. Nada mas.
        #
        # Presupuestar el peor caso (asumiendo que toda variacion pagina hasta el
        # maximo) hacia que en la corrida normal solo se cumpliera la mitad del
        # presupuesto, y la barra pegara un salto de 25 puntos en cada frontera de
        # categoria. Las paginas son trabajo que se DESCUBRE en marcha: cuando
        # aparece una, crece el numerador y el denominador a la vez, que es
        # justamente para lo que el denominador es ajustable.
        BASE_POR_CATEGORIA = 1 + 3 + 1
        pasos_hechos = 0
        # El +1 reserva el ultimo tramo para el cierre. Sin el, la ultima
        # escritura marcaba 100 % con la escritura todavia en curso: una barra
        # llena mientras el trabajo sigue es la misma clase de mentira que este
        # plan vino a quitar.
        pasos_total = len(CATEGORIAS_IMPORTADOR) * BASE_POR_CATEGORIA + 1

        def avanzar(fase, extra=False):
            nonlocal pasos_hechos, pasos_total
            pasos_hechos += 1
            if extra:
                pasos_total += 1
            with _import_lock:
                _avanzar_progreso(_import_job, hechos=pasos_hechos,
                                  total=pasos_total, fase=fase)

        def solo_fase(fase):
            """Cambia la etiqueta sin consumir un paso del presupuesto."""
            with _import_lock:
                _avanzar_progreso(_import_job, fase=fase)

        corte_por_cancelacion = False
        for i, cat in enumerate(CATEGORIAS_IMPORTADOR):
            with _import_lock:
                cancelado = _import_job.get('cancelado')
            if cancelado:
                # Solo cuenta como detenida si quedaba algo por hacer. Pedir
                # Detener mientras la ultima categoria ya escribia no convierte
                # una corrida entera en una parcial.
                corte_por_cancelacion = True
                break

            with _import_lock:
                _import_job['categoria'] = cat
                _import_job['progreso']  = i
                _import_job['log'].append(f'Buscando {cat} en {ciudad}...')
            # Un paso nada mas empezar: la barra no se queda en 0 % mientras el
            # operador se pregunta si pulso el boton.
            avanzar(f'Preparando {cat}…')

            resultados, stats, incidencias = _buscar_negocios(
                gmaps, cat, ciudad, vistos=vistos_corrida,
                con_detalle=con_detalle_corrida, avisar=avanzar,
                claves_en_hoja=claves_en_hoja, cache_places=cache_places,
                medidor=medidor)

            avanzar(f'Guardando {cat} en Google Sheets…')

            # Agregar ciudad a cada resultado
            for r in resultados:
                r['CIUDAD'] = ciudad

            desc = sum(stats.values())
            # Los que se saltaron por estar ya en la hoja no dejan de existir
            # solo porque ahora se detecten antes de pagar su detalle: siguen
            # contando como encontrados y como duplicados.
            saltados = incidencias['ya_en_hoja']
            try:
                nuevos = _exportar_a_sheets(resultados, cat, ciudad,
                                            claves_existentes=claves_en_hoja)
            except Exception as e:
                # Lo que se sabe se apunta; lo que no, no se inventa.
                # `encontrados` y `descartados` son hechos de la BUSQUEDA y siguen
                # siendo ciertos. `nuevos_en_sheet` y `duplicados` dependen de una
                # escritura que reventó: contarlos como duplicados afirmaria que
                # esos negocios "ya estaban", que es falso y peor que no decir nada.
                with _import_lock:
                    _import_job['encontrados'] += len(resultados) + saltados
                    _import_job['duplicados']  += saltados
                    _import_job['descartados'] += desc
                raise RuntimeError(
                    f'{cat}: fallo al escribir en Google Sheets — {e}'
                ) from e

            todos.extend(resultados)
            desglose[cat] = len(resultados)
            solo_fase(f'{cat}: {len(resultados)} aprobados')
            # `nuevos` es el valor de retorno de _exportar_a_sheets: las filas que
            # de verdad se escribieron. Antes solo iba al log, y la UI mostraba
            # `encontrados` rotulado como si fueran guardados. Son cosas distintas
            # y el operador necesita las dos.
            with _import_lock:
                _import_job['encontrados']     += len(resultados) + saltados
                _import_job['nuevos_en_sheet'] += nuevos
                _import_job['duplicados']      += (len(resultados) - nuevos) + saltados
                _import_job['descartados']     += desc
                perdidos = incidencias['detalles_fallidos'] + incidencias['paginas_fallidas']
                aviso = f' · ⚠ {perdidos} se perdieron por errores de Places' if perdidos else ''
                if saltados:
                    aviso += (f' · {saltados} ya estaban en la hoja'
                              f' (detalle no pagado)')
                # Los cortes se dicen, uno por uno. Un tope silencioso se lee
                # como "cubri todo" cuando justamente no lo hizo.
                for corte in incidencias.get('cortes', []):
                    _import_job['log'].append(f'✂ {corte}')
                de_cache = incidencias.get('detalles_desde_cache', 0)
                if de_cache:
                    aviso += f' · {de_cache} detalles servidos de caché'
                solape = incidencias['ya_vistos_otra_cat']
                if solape:
                    evitados = incidencias['detalles_evitados']
                    aviso += (f' · {solape} ya vistos en otra categoría'
                              f' ({evitados} consultas de detalle ahorradas)')
                _import_job['log'].append(
                    f'✓ {cat}: {len(resultados)} aprobados, {desc} descartados, '
                    f'{nuevos} nuevos en Sheet{aviso}'
                )
                copia_estado = dict(_import_job)
            # Al cerrar cada categoria, para que una corrida cortada a la mitad
            # deje contadores reales y no ceros. Fuera del lock: es una syscall y
            # los sondeos de estado necesitan ese mismo lock.
            _guardar_estado_importador(copia_estado)

        tiempo = (time.time() - inicio) / 60
        with _import_lock:
            fue_cancelada = corte_por_cancelacion
            resumen = {
                'nuevos':      _import_job['nuevos_en_sheet'],
                'encontrados': _import_job['encontrados'],
                'duplicados':  _import_job['duplicados'],
                'descartados': _import_job['descartados'],
                'medidor':     dict(_import_job.get('medidor') or {}),
            }
        _enviar_telegram_importador(ciudad, resumen, desglose, tiempo,
                                    cancelado=fue_cancelada)

        with _import_lock:
            # Una corrida cancelada NO es una corrida completada: lo escrito
            # antes del corte es valido, pero decir 'done' seria afirmar que se
            # recorrio todo.
            _import_job['status'] = 'cancelado' if fue_cancelada else 'done'
            if fue_cancelada:
                # `desglose` solo tiene las categorias que llegaron a escribir.
                completadas = len(desglose)
                _import_job['progreso'] = completadas
                _avanzar_progreso(_import_job, fase=(
                    f'Detenida tras {completadas} de '
                    f'{len(CATEGORIAS_IMPORTADOR)} categorías'))
            else:
                _import_job['progreso'] = len(CATEGORIAS_IMPORTADOR)
                _avanzar_progreso(_import_job, hechos=pasos_total,
                                  total=pasos_total, fase='Completado')
            copia_estado = dict(_import_job)
            cierre = ('⏹ Cancelada a los' if fue_cancelada
                      else '✅ Completado en')
            _import_job['log'].append(
                f"{cierre} {tiempo:.1f} min — "
                f"{resumen['nuevos']} nuevos en la hoja de "
                f"{resumen['encontrados']} encontrados"
            )
        _guardar_estado_importador(copia_estado)

    except PresupuestoAgotado as e:
        # No es un error: la corrida hizo lo que se le pidio y paro donde se le
        # dijo. Lo escrito hasta aqui es valido. Lo unico inaceptable seria
        # pararse sin decirlo.
        #
        # Antes de reportar, se escribe lo que la categoria en curso ya habia
        # aprobado y PAGADO. Tirarlo seria cobrarlo dos veces en el siguiente
        # intento, que es justo lo que este plan vino a evitar.
        if e.resultados:
            try:
                for r in e.resultados:
                    r['CIUDAD'] = ciudad
                nuevos_parcial = _exportar_a_sheets(
                    e.resultados, _import_job.get('categoria') or '', ciudad,
                    claves_existentes=claves_en_hoja)
                saltados_parcial = e.incidencias.get('ya_en_hoja', 0)
                with _import_lock:
                    _import_job['encontrados']     += len(e.resultados) + saltados_parcial
                    _import_job['nuevos_en_sheet'] += nuevos_parcial
                    _import_job['duplicados']      += (len(e.resultados) - nuevos_parcial
                                                       + saltados_parcial)
                    _import_job['descartados']     += sum(e.stats.values())
                    _import_job['log'].append(
                        f'💾 Se guardaron {nuevos_parcial} contactos ya pagados '
                        f'antes de alcanzar el tope')
            except Exception as e2:
                # Que falle el rescate no puede tapar el motivo real de la parada.
                print(f'[importador] no se pudo guardar lo pagado antes del tope: {e2}')
        tiempo = (time.time() - inicio) / 60
        with _import_lock:
            _import_job['status'] = 'presupuesto_agotado'
            _import_job['error'] = (
                f'Se alcanzó el tope de gasto de Places: {e}. Lo que ya se '
                f'guardó en la hoja sigue ahí; volver a correr la ciudad '
                f'continúa desde donde quedó, sin repetir lo pagado.')
            _import_job['log'].append(f'⛔ {_import_job["error"]}')
            copia_estado = dict(_import_job)
            resumen = {
                'nuevos':      _import_job['nuevos_en_sheet'],
                'encontrados': _import_job['encontrados'],
                'duplicados':  _import_job['duplicados'],
                'descartados': _import_job['descartados'],
                'medidor':     dict(_import_job.get('medidor') or {}),
            }
        _guardar_estado_importador(copia_estado)
        _enviar_telegram_importador(ciudad, resumen, desglose, tiempo,
                                    presupuesto=_import_job['error'])

    except Exception as e:
        # Telegram solo avisaba en el camino feliz: si la corrida se caia, el
        # owner no se enteraba por ningun canal.
        tiempo = (time.time() - inicio) / 60
        with _import_lock:
            _import_job['status'] = 'error'
            _import_job['error']  = _sanear_error(e)
            copia_estado = dict(_import_job)
            _import_job['log'].append(f'❌ Falló: {e}')
            sin_intentar = [c for c in CATEGORIAS_IMPORTADOR if c not in desglose
                            and c != _import_job.get('categoria')]
            if sin_intentar:
                _import_job['log'].append(
                    'Sin intentar por el fallo: ' + ', '.join(sin_intentar))
            resumen = {
                'nuevos':      _import_job['nuevos_en_sheet'],
                'encontrados': _import_job['encontrados'],
                'duplicados':  _import_job['duplicados'],
                'descartados': _import_job['descartados'],
                'medidor':     dict(_import_job.get('medidor') or {}),
            }
        _guardar_estado_importador(copia_estado)
        _enviar_telegram_importador(ciudad, resumen, desglose, tiempo,
                                    error=_sanear_error(e))
        traceback.print_exc()

    finally:
        # Se guarda pase lo que pase. Si la corrida revienta tras 200 llamadas ya
        # pagadas, tirar la cache seria pagarlas otra vez en el reintento.
        if cache_places:
            _guardar_cache_places(cache_places)


@app.route('/importador')
def importador_page():
    return render_template_string(IMPORTADOR_HTML)


@app.route('/api/importador/iniciar', methods=['POST'])
def importador_iniciar():
    global _import_job
    ciudad       = request.json.get('ciudad', '').strip()
    gmaps_api_key = os.environ.get('GMAPS_API_KEY')

    if not ciudad:
        return jsonify({'ok': False, 'error': 'Ciudad requerida'})
    if not gmaps_api_key:
        return jsonify({'ok': False, 'error': 'GMAPS_API_KEY no configurada'})

    with _import_lock:
        if _import_job['status'] == 'running':
            return jsonify({'ok': False, 'error': 'Ya hay una búsqueda en curso'})
        _import_job = _nuevo_import_job(ciudad, status='running')
        copia_estado = dict(_import_job)
    _guardar_estado_importador(copia_estado)   # I/O fuera del lock

    t = threading.Thread(target=_worker_importador, args=(ciudad, gmaps_api_key), daemon=True)
    t.start()
    return jsonify({'ok': True})


@app.route('/api/importador/cancelar', methods=['POST'])
def importador_cancelar():
    """Marca la corrida para que el worker salga limpio.

    No mata el hilo: le pone una bandera que el worker comprueba ENTRE pasos,
    nunca a mitad de un append_rows. Lo que ya se escribio en la hoja es valido
    y el dedup impide duplicarlo si se vuelve a correr la ciudad.
    """
    with _import_lock:
        if _import_job['status'] != 'running':
            # No se puede cancelar lo que no esta corriendo, y decir que si
            # seria otra respuesta que no corresponde a la realidad.
            return jsonify({'ok': False, 'error': 'No hay ninguna búsqueda en curso'})
        _import_job['cancelado'] = True
        _import_job['log'].append('⏹ Cancelación pedida; terminando el paso en curso…')
        copia_estado = dict(_import_job)
    _guardar_estado_importador(copia_estado)
    return jsonify({'ok': True})


@app.route('/api/importador/estado')
def importador_estado():
    with _import_lock:
        snap = {
            'status':     _import_job['status'],
            'ciudad':     _import_job['ciudad'],
            'categoria':  _import_job['categoria'],
            'progreso':   _import_job['progreso'],
            'total':      _import_job['total'],
            'fraccion':   _import_job.get('fraccion', 0),
            'fase':       _import_job.get('fase', ''),
            'medidor':    dict(_import_job.get('medidor') or _nuevo_medidor()),
            'encontrados':     _import_job['encontrados'],
            'nuevos_en_sheet': _import_job['nuevos_en_sheet'],
            'duplicados':      _import_job['duplicados'],
            'descartados':     _import_job['descartados'],
            'log':        _import_job['log'][-10:],
            'error':      _import_job['error'],
        }

    # Tras un reinicio del contenedor, `_import_job` vuelve a 'idle' y la pantalla
    # aparece limpia, como si el operador nunca hubiera lanzado nada. El registro
    # en disco es lo unico que sabe que hubo una corrida y que se corto.
    if snap['status'] == 'idle':
        rec = _leer_estado_importador()
        if rec and rec.get('status') == 'interrumpido':
            for clave in _CAMPOS_PERSISTIDOS:
                if clave in snap and rec.get(clave) is not None:
                    snap[clave] = rec[clave]
            snap['status'] = 'interrumpido'
            snap['error'] = ('La corrida se interrumpió porque el panel se reinició. '
                             'Lo que ya se había guardado en la hoja sigue ahí.')
            snap['log'] = [snap['error']]
    return jsonify(snap)


# ══════════════════════════════════════════════════════════════════════════════
#  CATALOGO DE CIUDADES  (Plan 1 - T1.5)
# ══════════════════════════════════════════════════════════════════════════════
# Sustituye al array JS CIUDADES_MX que vivia dentro de IMPORTADOR_HTML y que el
# navegador fusionaba a mano con /api/prospectos/ciudades. Esa fusion se hace
# aqui, que es donde puede probarse.
#
# Modelo: docs/adr/2026-08-28-modelo-relevancia-ciudades.md
# Generador del catalogo: tools/generar_catalogo_ciudades.py

CATALOGO_CIUDADES_FILE = os.environ.get(
    'CATALOGO_CIUDADES_FILE',
    os.path.join(os.path.dirname(os.path.abspath(__file__)), 'datos', 'ciudades_mx.json'),
)

# Se lee una vez y se cachea: son ~600 registros que no cambian en caliente.
_catalogo_ciudades = None
_indice_ciudades = None

# Tasa de interes de referencia cuando la hoja no da para calcularla. No es una
# constante inventada: en cuanto hay llamadas se sustituye por la tasa real.
INTERES_REFERENCIA = 0.30
# Pseudo-observaciones del encogimiento. Con 20, una ciudad de 1 llamada apenas
# mueve el factor y una de 100 lo mueve casi del todo. Es lo que impide que
# "1 aprobado de 1 llamada = 100 %" mande al pueblo por delante de Guadalajara.
LLAMADAS_PARA_CONFIAR = 20
AJUSTE_MAX_DESEMPENO = 0.25       # +-25 % por desempeno propio
DESCUENTO_MAX_SATURACION = 0.35   # hasta -35 % por plaza ya cosechada


def _normalizar_ciudad(nombre) -> str:
    """Minusculas, sin acentos, sin puntuacion y sin espacios repetidos.

    Los espacios se colapsan a proposito: "Guadalupe, Zacatecas" deja dos
    seguidos al quitar la coma y dejaria de casar con "Guadalupe Zacatecas".
    """
    s = unicodedata.normalize('NFD', str(nombre or '').lower())
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    return re.sub(r'\s+', ' ', re.sub(r'[^a-z0-9 ]', ' ', s)).strip()


def _cargar_catalogo_ciudades():
    """Devuelve (catalogo, indice_por_nombre_normalizado).

    Si el archivo falta o esta roto NO se revienta la ruta: se devuelve catalogo
    vacio y el endpoint responde con lo que haya. El panel sirve para trabajar;
    quedarse sin ranking degrada, quedarse sin panel no.
    """
    global _catalogo_ciudades, _indice_ciudades
    if _catalogo_ciudades is not None:
        return _catalogo_ciudades, _indice_ciudades
    try:
        with open(CATALOGO_CIUDADES_FILE, encoding='utf-8') as f:
            catalogo = json.load(f)
    except (OSError, ValueError) as e:
        print(f"[catalogo] no se pudo leer {CATALOGO_CIUDADES_FILE}: {e}")
        catalogo = []
    indice = {}
    for c in catalogo:
        indice.setdefault(_normalizar_ciudad(c['nombre']), c)
        for a in c.get('alias', []):
            indice.setdefault(_normalizar_ciudad(a), c)
    _catalogo_ciudades, _indice_ciudades = catalogo, indice
    return catalogo, indice


def _factor_desempeno(llamados: int, aprobados: int, interes_referencia: float) -> float:
    """Cuanto ajusta el historial propio de NIOVAL. Neutro en 1.0.

    Encogido por tamano de muestra: sin llamadas vale exactamente 1.0, o sea que
    NO se penaliza no haber ido nunca. Ese es el defecto que este plan corrige.
    """
    if llamados <= 0:
        return 1.0
    tasa = aprobados / llamados
    confianza = llamados / (llamados + LLAMADAS_PARA_CONFIAR)
    ref = max(interes_referencia, 0.01)
    bruto = 1 + AJUSTE_MAX_DESEMPENO * confianza * (tasa - ref) / ref
    return max(1 - AJUSTE_MAX_DESEMPENO, min(1 + AJUSTE_MAX_DESEMPENO, bruto))


def _factor_saturacion(contactos: int, unidades_ferreteras: int) -> float:
    """Lo ya cosechado deja de ser oportunidad.

    Google Places rinde del orden de 60 resultados por corrida, asi que una plaza
    ya trabajada devuelve duplicados y seguiria siendo la primera para siempre.
    Chihuahua tiene 448 contactos en la hoja y 651 ferreterias en el DENUE: dos
    tercios cosechados. El potencial util es lo que QUEDA por cosechar.
    """
    if unidades_ferreteras <= 0:
        return 1.0
    return 1 - DESCUENTO_MAX_SATURACION * min(1.0, contactos / unidades_ferreteras)


def _explicar_ciudad(reg: dict, metricas: dict, saturacion: float) -> str:
    """Texto ya armado en el servidor, para que la UI no reconstruya el
    razonamiento y para que cada posicion sea auditable.

    Lleva el CONTEO CRUDO de ferreterias a proposito: el puntaje va en escala
    logaritmica y comprime, asi que un 86.7 frente a un 89.8 no significa lo que
    el operador leeria que significa (ADR 4.3).
    """
    partes = [f"{reg['indicadores']['unidades_ferreteras']} ferreterias en el DENUE"]
    if metricas['total']:
        partes.append(f"{metricas['total']} contactos ya en la hoja")
    else:
        partes.append('plaza sin trabajar')
    if metricas['llamados']:
        partes.append(f"{metricas['interes_pct']}% de interes en {metricas['llamados']} llamadas")
    if saturacion < 0.9:
        cosechada = round((1 - saturacion) / DESCUENTO_MAX_SATURACION * 100)
        partes.append(f"{cosechada}% ya cosechada")
    return ' - '.join(partes)


@app.route('/api/importador/ciudades')
def api_importador_ciudades():
    """Catalogo nacional + metricas de la hoja, ordenado por prioridad.

    Devuelve SOLO agregados por ciudad. Ningun telefono ni nombre de contacto
    sale de aqui, aunque el origen sea la hoja de clientes.
    """
    catalogo, indice = _cargar_catalogo_ciudades()
    metricas_hoja = _agregar_por_ciudad(get_data('contactos'), get_all_respuestas())

    # Tasa de referencia calculada de los propios datos, no una constante fija.
    total_llamados = sum(m['llamados'] for m in metricas_hoja)
    total_aprobados = sum(m['aprobados'] for m in metricas_hoja)
    referencia = (total_aprobados / total_llamados) if total_llamados else INTERES_REFERENCIA

    por_clave, sin_clasificar = {}, []
    for m in metricas_hoja:
        if m['ciudad'] == 'Sin ciudad':
            continue
        reg = indice.get(_normalizar_ciudad(m['ciudad']))
        if reg is None:
            # Nada se descarta en silencio: la hoja trae 116 valores distintos y
            # algunos son estados ("Chiapas", "Guerrero"), no ciudades.
            sin_clasificar.append({
                'ciudad': m['ciudad'], 'total': m['total'],
                'llamados': m['llamados'], 'aprobados': m['aprobados'],
                'interes_pct': m['interes_pct'],
            })
            continue
        acum = por_clave.setdefault(
            reg['clave_inegi'],
            {'total': 0, 'llamados': 0, 'aprobados': 0, 'interes_pct': 0},
        )
        for campo in ('total', 'llamados', 'aprobados'):
            acum[campo] += m[campo]

    for acum in por_clave.values():
        acum['interes_pct'] = (
            round(acum['aprobados'] / acum['llamados'] * 100, 1) if acum['llamados'] else 0
        )

    vacio = {'total': 0, 'llamados': 0, 'aprobados': 0, 'interes_pct': 0}
    ciudades = []
    for reg in catalogo:
        m = por_clave.get(reg['clave_inegi'], vacio)
        unidades = reg['indicadores']['unidades_ferreteras']
        saturacion = _factor_saturacion(m['total'], unidades)
        desempeno = _factor_desempeno(m['llamados'], m['aprobados'], referencia)
        factor = round(max(0.60, min(1.25, desempeno * saturacion)), 3)
        ciudades.append({
            'ciudad': reg['nombre'],
            'estado': reg['estado'],
            'region': reg['region'],
            'potencial_mercado': reg['potencial_mercado'],
            'desempeno_nioval': factor,
            'prioridad': round(reg['potencial_mercado'] * factor, 1),
            'unidades_ferreteras': unidades,
            'explicacion': _explicar_ciudad(reg, m, saturacion),
            'total': m['total'],
            'llamados': m['llamados'],
            'aprobados': m['aprobados'],
            'interes_pct': m['interes_pct'],
        })

    # Desempate del ADR: prioridad, luego ferreterias, luego nombre. Determinista:
    # dos peticiones sobre los mismos datos devuelven el mismo orden.
    ciudades.sort(key=lambda c: (-c['prioridad'], -c['unidades_ferreteras'], c['ciudad']))
    sin_clasificar.sort(key=lambda c: -c['total'])

    conteo = Counter(c['region'] for c in ciudades)
    regiones = sorted(
        ({'region': r, 'total': n} for r, n in conteo.items()),
        key=lambda x: -x['total'],
    )
    return jsonify({
        'ciudades': ciudades,
        'sin_clasificar': sin_clasificar,
        'regiones': regiones,
    })

IMPORTADOR_HTML = r"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>NIOVAL — Importador de Contactos</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{--blue:#0047CC;--blue2:#003399;--green:#00CC47;--orange:#e67e22}
body{font-family:'Segoe UI',sans-serif;background:linear-gradient(135deg,#003399,#0047CC);min-height:100vh;padding:20px;display:flex;justify-content:center}
.card{background:#fff;border-radius:20px;box-shadow:0 20px 60px rgba(0,0,0,.3);width:100%;max-width:640px;overflow:hidden}
.header{background:linear-gradient(135deg,#003399,#0047CC);color:#fff;padding:24px 28px;display:flex;align-items:center;gap:14px}
.header img{height:44px;background:#fff;border-radius:10px;padding:5px}
.header h1{font-size:1.15em;font-weight:800}
.header p{font-size:.78em;opacity:.8;margin-top:3px}
.body{padding:28px}
.input-row{display:flex;gap:10px;margin-bottom:20px}
.input-row input{flex:1;padding:12px 16px;border:2px solid #dde6ff;border-radius:10px;font-size:.95em;outline:none;transition:border .2s}
.input-row input:focus{border-color:var(--blue)}
.btn{padding:12px 24px;border:none;border-radius:10px;font-size:.92em;font-weight:700;cursor:pointer;transition:all .2s}
.btn-blue{background:var(--blue);color:#fff}.btn-blue:hover{background:var(--blue2)}
.btn-blue:disabled{opacity:.5;cursor:not-allowed}
.filters{background:#f0f4ff;border-radius:12px;padding:14px 16px;margin-bottom:20px;font-size:.82em;color:#555}
.filters strong{color:var(--blue)}
.progress-box{display:none;margin-bottom:20px}
.progress-label{display:flex;justify-content:space-between;font-size:.82em;color:#555;margin-bottom:8px}
.progress-bar{height:10px;background:#e6f0ff;border-radius:5px;overflow:hidden}
.progress-fill{height:100%;background:var(--blue);border-radius:5px;transition:width .5s ease}
.cats{display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap}
.cat-badge{padding:5px 12px;border-radius:20px;font-size:.78em;font-weight:600;background:#e6f0ff;color:#888;transition:all .3s}
.cat-badge.active{background:var(--blue);color:#fff}
.cat-badge.done{background:var(--green);color:#fff}
.stats-row{display:grid;grid-template-columns:1fr 1fr 1fr 1fr;gap:10px;margin-bottom:10px}
.stats-row .stat-box.principal{background:#eefaf1;border-top-width:4px}
.stat-box.principal .n{font-size:2.4em}
@media(max-width:620px){.stats-row{grid-template-columns:1fr 1fr}}
.progreso-row{display:grid;grid-template-columns:1fr;gap:10px;margin-bottom:16px}
.stat-box{background:#f8f9fa;border-radius:10px;padding:12px;text-align:center;border-top:3px solid #dde}
.stat-box.green{border-color:var(--green)}.stat-box.red{border-color:#e74c3c}.stat-box.blue{border-color:var(--blue)}
.stat-box .n{font-size:1.8em;font-weight:800;color:var(--blue)}.stat-box.green .n{color:var(--green)}.stat-box.red .n{color:#e74c3c}
.stat-box .l{font-size:.68em;color:#888;text-transform:uppercase;margin-top:2px}
.log-box{background:#1a1a2e;border-radius:10px;padding:14px;max-height:160px;overflow-y:auto;font-family:monospace;font-size:.78em;color:#a8d8a8;margin-bottom:16px}
.log-box .entry{margin-bottom:4px;line-height:1.4}
.result-box{display:none;text-align:center;padding:20px 0}
.result-box .icon{font-size:3.5em;margin-bottom:12px}
.result-box h2{color:var(--blue);margin-bottom:8px}
.result-box p{color:#888;font-size:.88em}
.link-panel{display:inline-flex;align-items:center;gap:8px;background:#e6f0ff;border:1px solid #c5d8ff;color:var(--blue);padding:10px 18px;border-radius:10px;text-decoration:none;font-weight:600;font-size:.88em;margin-top:16px}
.link-panel:hover{background:var(--blue);color:#fff}
.chip{display:inline-flex;align-items:center;gap:5px;padding:5px 12px;border-radius:20px;font-size:.78em;font-weight:600;cursor:pointer;border:1px solid #dde6ff;background:#f0f4ff;color:#555;transition:all .2s;white-space:nowrap}
.chip:hover{background:var(--blue);color:#fff;border-color:var(--blue)}
.chip.active{background:var(--blue);color:#fff;border-color:var(--blue)}
.chip.top{border-color:var(--green);background:#f0fff4;color:#155724}
.chip.top:hover,.chip.top.active{background:var(--green);color:#fff;border-color:var(--green)}
.chip .pct{font-size:.85em;opacity:.8}
</style>
</head>
<body>
<div class="card">
  <div class="header">
    <img src="https://res.cloudinary.com/dipt3jq6r/image/upload/v1764307686/NIOVAL-05_xhfrrh.jpg" onerror="this.style.display='none'">
    <div>
      <h1>Importador de Contactos</h1>
      <p>Busca ferreterías en Google Maps y las agrega a tu lista</p>
    </div>
  </div>
  <div class="body">

    <div class="filters">
      <strong>Filtros aplicados:</strong> Mínimo 5 reseñas · Calificación ≥ 3.5 ⭐ · Con teléfono
    </div>

    <!-- CATEGORÍAS -->
    <div style="font-size:.78em;color:#888;margin-bottom:8px;font-weight:600;text-transform:uppercase;letter-spacing:.8px">Categorías a buscar</div>
    <div class="cats" id="cats-list"></div>

    <!-- CIUDADES -->
    <div style="display:flex;align-items:center;justify-content:space-between;margin-top:16px;margin-bottom:8px">
      <div style="font-size:.78em;color:#888;font-weight:700;text-transform:uppercase;letter-spacing:.8px">
        Ciudades <span id="ciudades-count" style="color:var(--blue)"></span> — <span style="color:var(--green)">ordenadas por relevancia</span>
      </div>
      <input type="text" id="ciudad-filter" placeholder="🔍 Filtrar..." oninput="filtrarCiudades()"
        style="padding:5px 10px;border:1px solid #dde6ff;border-radius:8px;font-size:.8em;outline:none;width:140px">
    </div>
    <div id="ciudades-chips" style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:16px;max-height:220px;overflow-y:auto;padding:4px 2px">
      <div style="color:#aaa;font-size:.82em;padding:6px">Cargando ciudades...</div>
    </div>

    <!-- INPUT CIUDAD -->
    <div class="input-row">
      <input type="text" id="input-ciudad" placeholder="O escribe una ciudad manualmente..." onkeydown="if(event.key==='Enter') iniciar()">
      <button class="btn btn-blue" id="btn-iniciar" onclick="iniciar()">🔍 Buscar</button>
      <button class="btn" id="btn-cancelar" onclick="cancelar()"
        style="display:none;background:#f3f4f6;border:1px solid #dde;color:#666">⏹ Detener</button>
    </div>

    <!-- PROGRESO -->
    <div class="progress-box" id="progress-box">
      <div class="progress-label">
        <span id="prog-label">Iniciando...</span>
        <span id="prog-pct">0%</span>
      </div>
      <div class="progress-bar"><div class="progress-fill" id="prog-fill" style="width:0%"></div></div>
    </div>

    <!-- STATS -->
    <div class="stats-row" id="stats-row" style="display:none">
      <div class="stat-box green principal"><div class="n" id="s-nuevos">0</div><div class="l">Nuevos en la hoja</div></div>
      <div class="stat-box blue"><div class="n" id="s-encontrados">0</div><div class="l">Aprobados por filtros</div></div>
      <div class="stat-box"><div class="n" id="s-duplicados">0</div><div class="l">Ya estaban</div></div>
      <div class="stat-box red"><div class="n" id="s-descartados">0</div><div class="l">Descartados</div></div>
    </div>
    <div class="progreso-row" id="progreso-row" style="display:none">
      <div class="stat-box blue"><div class="n" id="s-progreso">0/0</div><div class="l">Categorias procesadas</div></div>
    </div>
    <div id="medidor-box" style="display:none;font-size:.78em;color:#777;margin:-6px 0 16px;
      padding:8px 12px;background:#f8f9fa;border-radius:8px;border-left:3px solid #dde">
      <span id="m-llamadas"></span><span id="m-ahorro"></span><span id="m-costo"></span>
    </div>

    <!-- LOG -->
    <div class="log-box" id="log-box" style="display:none"></div>

    <!-- RESULTADO FINAL -->
    <div class="result-box" id="result-box">
      <div class="icon">✅</div>
      <h2 id="result-titulo">Búsqueda Completada</h2>
      <p id="result-desc"></p>
      <br>
      <a href="/" class="link-panel">← Volver al Panel</a>
    </div>

  </div>
</div>

<script>
const CATS = ["Ferreterías","Distribuidoras Ferreterías"];
let polling = null;

// Render categoria badges
document.getElementById('cats-list').innerHTML = CATS.map((c,i) =>
  `<div class="cat-badge" id="cat-${i}">${c}</div>`
).join('');

// Lista completa de ciudades de México (200+)
const CIUDADES_MX = [
  // Zona Metropolitana / Grandes ciudades
  'Ciudad de México','Guadalajara','Monterrey','Puebla','Toluca',
  'Tijuana','Juárez','León','Zapopan','Nezahualcóyotl',
  'Chihuahua','Naucalpan','Ecatepec','Mérida','Querétaro',
  'San Luis Potosí','Aguascalientes','Mexicali','Hermosillo','Saltillo',
  'Morelia','Torreón','Culiacán','Veracruz','Acapulco',
  'Cancún','Tampico','Reynosa','San Nicolás de los Garza','Durango',
  'Tlalnepantla','Chimalhuacán','Oaxaca','Tuxtla Gutiérrez','Irapuato',
  'Ciudad López Mateos','Celaya','Tultitlán','Mazatlán','Xalapa',
  'Nuevo Laredo','Ensenada','Matamoros','Monclova','Tepic',
  'Ciudad Obregón','Los Mochis','Villahermosa','Cuernavaca','Colima',
  'Pachuca','Chilpancingo','Tlaxcala','Campeche','La Paz',
  // Estados y municipios importantes
  'Apodaca','San Pedro Garza García','Guadalupe','Escobedo',
  'Zapotlanejo','Tlaquepaque','Tonalá','El Salto','Tlajomulco',
  'Soledad de Graciano Sánchez','Matehuala','Rioverde',
  'Fresnillo','Zacatecas','Jerez','Guadalupe Zacatecas',
  'Tepic','Santiago','Bahía de Banderas','Puerto Vallarta',
  'Mazatlán','Culiacán','Los Mochis','Guasave','Guamúchil',
  'Navojoa','Cajeme','Nogales','San Luis Río Colorado','Caborca',
  'Delicias','Parral','Cuauhtémoc Chih','Guachochi',
  'Monclova','Piedras Negras','Acuña','Sabinas','Múzquiz',
  'Linares','Cadereyta','Allende NL','Galeana',
  'Altamira','Ciudad Madero','Río Bravo','Valle Hermoso',
  'Mante','Victoria','Tula Tamps','Jaumave',
  'Tuxpan','Poza Rica','Coatzacoalcos','Minatitlán','Córdoba',
  'Orizaba','Martínez de la Torre','Papantla','Tantoyuca',
  'Cosamaloapan','San Andrés Tuxtla','Acayucan',
  'Tehuacán','Atlixco','Teziutlán','Huauchinango','Cholula',
  'San Martín Texmelucan','Izúcar de Matamoros','Tehuacan',
  'Zamora','Uruapan','Lázaro Cárdenas','Apatzingán','Zitácuaro',
  'Pátzcuaro','Sahuayo','La Piedad','Jacona','Jiquilpan',
  'Colima','Manzanillo','Tecomán','Villa de Álvarez',
  'Guadalajara','Zapopan','Tlaquepaque','Tonalá','Tlajomulco',
  'Lagos de Moreno','Tepatitlán','Ocotlán','Ameca','Autlán',
  'Puerto Vallarta','Chapala','Sayula','Ciudad Guzmán',
  'Guanajuato','Irapuato','Celaya','León','Salamanca',
  'Silao','Pénjamo','Dolores Hidalgo','San Miguel de Allende',
  'Acámbaro','Moroleón','Uriangato','Cortazar','Valle de Santiago',
  'Pachuca','Tulancingo','Tula de Allende','Ixmiquilpan',
  'Actopan','Tizayuca','Cuautitlán Izcalli','Coacalco','Ecatepec',
  'Tlalnepantla','Naucalpan','Atizapán','Nicolás Romero','Cuautitlán',
  'Texcoco','Chalco','Valle de Chalco','Amecameca','Tultepec',
  'Metepec','Zinacantepec','Lerma','Santiago Tianguistenco',
  'Cuernavaca','Jiutepec','Temixco','Cuautla','Jojutla','Zacatepec',
  'Oaxaca','Juchitán','Salina Cruz','Tehuantepec','Tuxtepec',
  'Puerto Escondido','Huatulco','Miahuatlán','Ejutla',
  'Chilpancingo','Acapulco','Iguala','Taxco','Zihuatanejo',
  'Tlapa','Ometepec','Ayutla','Cruz Grande',
  'Tapachula','San Cristóbal de las Casas','Comitán','Tonalá Chis',
  'Pichucalco','Ocosingo','Palenque','Villaflores',
  'Villahermosa','Cárdenas','Macuspana','Comalcalco',
  'Campeche','Ciudad del Carmen','Calkiní','Hopelchén',
  'Mérida','Cancún','Valladolid','Tizimín','Ticul','Izamal',
  'Chetumal','Playa del Carmen','Cozumel','Felipe Carrillo Puerto',
  'La Paz BCS','Cabo San Lucas','San José del Cabo','Loreto',
  'Ensenada','Tijuana','Mexicali','Tecate','Rosarito',
  'Hermosillo','Ciudad Obregón','Navojoa','Guaymas','Nogales',
  'Los Mochis','Culiacán','Mazatlán','Guasave','Mochis',
  'Durango','Gómez Palacio','Lerdo','Victoria de Durango',
  'Zacatecas','Fresnillo','Jerez','Loreto Zac','Pinos',
  'Aguascalientes','Calvillo','Rincón de Romos','San Francisco de los Romo',
  'Tepic','Xalisco','Ixtlán','Santiago Ixc',
  'San Luis Potosí','Matehuala','Ciudad Valles','Rioverde','Tamazunchale',
  'Saltillo','Torreón','Monclova','Piedras Negras','Acuña',
  'Monterrey','Guadalupe NL','Apodaca','San Nicolás','Escobedo','Juárez NL',
];

let todasCiudades = [];

async function cargarCiudades() {
  try {
    const r    = await fetch('/api/prospectos/ciudades');
    const panelData = await r.json();

    // Ciudades del panel con datos reales (con relevancia calculada)
    const conDatos = panelData.filter(c => c.ciudad && c.ciudad !== 'Sin ciudad');
    const enPanel  = new Set(conDatos.map(c => c.ciudad.toLowerCase()));

    // Ciudades de la lista estática que NO están en el panel
    const unicasMX = [...new Set(CIUDADES_MX)];
    const sinDatos = unicasMX
      .filter(c => !enPanel.has(c.toLowerCase()))
      .map(c => ({ ciudad: c, total: 0, llamados: 0, aprobados: 0, interes_pct: 0, relevancia: 0 }));

    // Fusionar: panel (con datos) + estáticas (sin datos)
    todasCiudades = [...conDatos, ...sinDatos];
    todasCiudades.forEach((c, i) => { c.rank = i + 1; });

    document.getElementById('ciudades-count').textContent = `(${todasCiudades.length})`;
    renderChips(todasCiudades);
  } catch(e) {
    // Fallback: solo estáticas
    todasCiudades = [...new Set(CIUDADES_MX)].map((c, i) => ({
      ciudad: c, total: 0, llamados: 0, aprobados: 0, interes_pct: 0, relevancia: 0,
      rank: i + 1
    }));
    document.getElementById('ciudades-count').textContent = `(${todasCiudades.length})`;
    renderChips(todasCiudades);
  }
}

// El nombre de la ciudad viene de LISTA DE CONTACTOS, escrito a mano, y antes
// de eso lo tecleo un operador en el campo de texto sin validacion. Se
// interpolaba crudo en DOS sitios de la misma linea: dentro del atributo
// onclick y como texto del chip. Una ciudad llamada O'Brien rompia el handler
// y dejaba el chip muerto; una con <img onerror=...> ejecutaba.
// El dashboard ya cerraba este mismo agujero (app.py:2064).
function escaparHtml(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function renderChips(lista) {
  const cont = document.getElementById('ciudades-chips');
  if (!lista.length) { cont.innerHTML = '<div style="color:#aaa;font-size:.82em">Sin resultados</div>'; return; }

  cont.innerHTML = lista.map((c) => {
    // El rango es el del catalogo completo, no el de la lista filtrada: antes
    // se calculaba sobre el indice recibido, asi que al escribir en el filtro
    // la ciudad numero 47 aparecia con medalla de oro.
    const rank   = (c.rank != null) ? c.rank : 0;
    const medal  = rank === 1 ? '🥇 ' : rank === 2 ? '🥈 ' : rank === 3 ? '🥉 ' : `${rank}. `;
    const isTop  = rank >= 1 && rank <= 3;
    const hasInt = c.interes_pct > 0;
    const badge  = hasInt
      ? `<span style="background:rgba(0,204,71,.2);color:#155724;padding:1px 5px;border-radius:8px;font-size:.85em">${c.interes_pct}%</span>`
      : `<span style="opacity:.55;font-size:.85em">${c.total}</span>`;
    const nombre = escaparHtml(c.ciudad);
    return `<span class="chip ${isTop?'top':''}" data-ciudad="${nombre}">${medal}${nombre} ${badge}</span>`;
  }).join('');
}

// Listener delegado: el nombre viaja por dataset, nunca dentro de un atributo
// de codigo. Se registra una sola vez sobre el contenedor, asi que sobrevive a
// cada re-render de los chips.
document.getElementById('ciudades-chips').addEventListener('click', (ev) => {
  const chip = ev.target.closest('.chip');
  if (!chip) return;
  document.getElementById('input-ciudad').value = chip.dataset.ciudad || '';
  document.querySelectorAll('.chip').forEach(c => c.classList.remove('active'));
  chip.classList.add('active');
});

function filtrarCiudades() {
  const q = document.getElementById('ciudad-filter').value.toLowerCase().trim();
  renderChips(q ? todasCiudades.filter(c => c.ciudad.toLowerCase().includes(q)) : todasCiudades);
}

cargarCiudades();

// ── Sondeo ────────────────────────────────────────────────────────────────
// Antes: setInterval fijo de 3 s que solo paraba en 'done' o 'error'. Si el
// contenedor se reiniciaba, el estado llegaba 'idle' para siempre y el sondeo
// seguia latiendo indefinidamente contra un trabajo que ya no existia.
let intervaloSondeo = 3000;
let ciclosIdle = 0;          // el panel responde, pero dice que no hay trabajo
let ciclosSinRespuesta = 0;  // el panel no responde
const MAX_CICLOS_IDLE = 5;
const MAX_CICLOS_SIN_RESPUESTA = 5;

function arrancarSondeo(ms) {
  clearInterval(polling);          // sin esto quedaban dos intervalos vivos
  intervaloSondeo = ms || 3000;
  polling = setInterval(actualizarEstado, intervaloSondeo);
}

function pararSondeo() {
  clearInterval(polling);
  polling = null;
}

function limpiarPantalla() {
  // La corrida anterior dejaba sus numeros y sus insignias puestos: la segunda
  // busqueda de la sesion arrancaba con todo marcado como completado.
  ['s-nuevos','s-encontrados','s-duplicados','s-descartados'].forEach(id => {
    document.getElementById(id).textContent = '0';
  });
  document.getElementById('s-progreso').textContent = '0/0';
  document.getElementById('prog-fill').style.width = '0%';
  document.getElementById('prog-pct').textContent = '0%';
  document.getElementById('log-box').innerHTML = '';
  CATS.forEach((_, i) => document.getElementById('cat-'+i).className = 'cat-badge');
  ciclosIdle = 0;
  ciclosSinRespuesta = 0;
}

function mostrarPaneles() {
  document.getElementById('progress-box').style.display = 'block';
  document.getElementById('stats-row').style.display = 'grid';
  document.getElementById('progreso-row').style.display = 'grid';
  document.getElementById('medidor-box').style.display = 'block';
  document.getElementById('log-box').style.display = 'block';
  document.getElementById('result-box').style.display = 'none';
}

function ponerEnMarcha(enMarcha) {
  const btn = document.getElementById('btn-iniciar');
  btn.disabled = enMarcha;
  btn.textContent = enMarcha ? '⏳ Buscando...' : '🔍 Buscar';
  // El campo nunca se deshabilitaba, asi que pulsar Enter a media corrida
  // relanzaba iniciar() y podia arrancar una SEGUNDA importacion.
  document.getElementById('input-ciudad').disabled = enMarcha;
  document.getElementById('btn-cancelar').style.display = enMarcha ? 'inline-flex' : 'none';
}

async function iniciar() {
  const ciudad = document.getElementById('input-ciudad').value.trim();
  if (!ciudad) { alert('Ingresa una ciudad'); return; }

  ponerEnMarcha(true);
  limpiarPantalla();
  mostrarPaneles();

  try {
    const r = await fetch('/api/importador/iniciar', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ciudad})
    });
    const d = await r.json();
    if (!d.ok) {
      alert('Error: ' + d.error);
      ponerEnMarcha(false);
      return;
    }
    arrancarSondeo(3000);
    actualizarEstado();
  } catch (e) {
    // Sin este catch la promesa reventaba y el boton se quedaba en
    // "Buscando..." deshabilitado para siempre: hacia falta recargar.
    document.getElementById('prog-label').textContent =
      '❌ No se pudo contactar con el panel: ' + e;
    ponerEnMarcha(false);
  }
}

async function cancelar() {
  if (!confirm('¿Detener la búsqueda? Lo que ya se guardó en la hoja se queda.')) return;
  try {
    const r = await fetch('/api/importador/cancelar', {method: 'POST'});
    const d = await r.json();
    if (!d.ok) alert(d.error || 'No se pudo cancelar');
  } catch (e) {
    alert('No se pudo contactar con el panel: ' + e);
  }
}

async function restaurarEstado() {
  // Al abrir la pagina se pregunta si hay algo corriendo. Antes solo iniciar()
  // arrancaba el sondeo, asi que recargar a media corrida dejaba la pantalla
  // inerte y el operador encerrado fuera de su propio trabajo.
  try {
    const d = await (await fetch('/api/importador/estado')).json();
    if (d.status === 'running') {
      mostrarPaneles();
      ponerEnMarcha(true);
      pintarEstado(d);
      arrancarSondeo(3000);
    } else if (d.status !== 'idle') {
      // done, error, cancelado e interrumpido: la corrida anterior sigue en
      // memoria y el operador tiene derecho a verla al volver a la pagina.
      // Antes solo se contemplaban 'running' e 'interrumpido', asi que recargar
      // tras un fallo dejaba la pantalla en blanco, sin rastro del error.
      mostrarPaneles();
      pintarEstado(d);
      rematar(d);
    }
  } catch (e) {
    // Que falle la restauracion no puede impedir usar la pagina.
    console.warn('No se pudo restaurar el estado del importador:', e);
  }
}

function pintarEstado(d) {
  const pct = d.fraccion || 0;
  document.getElementById('prog-fill').style.width  = pct + '%';
  document.getElementById('prog-pct').textContent   = pct + '%';
  document.getElementById('prog-label').textContent =
    d.fase || (d.categoria ? `Buscando: ${d.categoria}...` : 'Procesando...');

  document.getElementById('s-nuevos').textContent      = d.nuevos_en_sheet;
  document.getElementById('s-encontrados').textContent = d.encontrados;
  document.getElementById('s-duplicados').textContent  = d.duplicados;
  document.getElementById('s-descartados').textContent = d.descartados;
  document.getElementById('s-progreso').textContent    = `${d.progreso}/${d.total}`;

  const m = d.medidor || {};
  document.getElementById('m-llamadas').textContent =
    `Llamadas a Google: ${m.text_search || 0} búsquedas + ${m.place_details || 0} detalles`;
  const evitadas = (m.cache_hits || 0) + (m.duplicados_evitados || 0);
  document.getElementById('m-ahorro').textContent = evitadas ? ` · ${evitadas} evitadas` : '';
  // Sin tarifas configuradas no se inventa un importe: un 0.00 se leeria como
  // "esta corrida salio gratis", que no es lo mismo que "no lo sé".
  document.getElementById('m-costo').textContent =
    (m.costo === null || m.costo === undefined) ? '' : ` · costo estimado ${m.costo.toFixed(2)}`;

  CATS.forEach((c, i) => {
    const el = document.getElementById('cat-'+i);
    if (i < d.progreso) el.className = 'cat-badge done';
    else if (d.categoria === c) el.className = 'cat-badge active';
    else el.className = 'cat-badge';       // sin esta rama se quedaban rancias
  });

  const logEl = document.getElementById('log-box');
  logEl.innerHTML = (d.log || []).map(l => `<div class="entry">> ${escaparHtml(l)}</div>`).join('');
  logEl.scrollTop = logEl.scrollHeight;
}

async function actualizarEstado() {
  let d;
  try {
    const r = await fetch('/api/importador/estado');
    d = await r.json();
  } catch (e) {
    // Un corte de red no puede dejar el sondeo latiendo a ciegas: se espacia y,
    // si no vuelve, se para solo.
    ciclosSinRespuesta++;
    if (ciclosSinRespuesta >= MAX_CICLOS_SIN_RESPUESTA) {
      pararSondeo();
      document.getElementById('prog-label').textContent =
        '❌ Se perdió el contacto con el panel. Recarga la página.';
      ponerEnMarcha(false);
    } else if (intervaloSondeo < 15000) {
      arrancarSondeo(intervaloSondeo * 2);
    }
    return;
  }

  if (d.status === 'idle') {
    // El contenedor se reinicio a media corrida: el trabajo ya no existe.
    ciclosIdle++;
    if (ciclosIdle >= MAX_CICLOS_IDLE) {
      pararSondeo();
      document.getElementById('prog-label').textContent =
        '⚠ La corrida ya no está en curso (el panel se reinició).';
      ponerEnMarcha(false);
    }
    return;
  }
  ciclosIdle = 0;
  ciclosSinRespuesta = 0;

  pintarEstado(d);

  // El sondeo se espacia si la corrida se alarga, en vez de 3 s eternos.
  if (intervaloSondeo < 10000 && (d.fraccion || 0) > 0 && (d.fraccion || 0) < 90) {
    const deseado = Math.min(10000, intervaloSondeo + 1000);
    if (deseado !== intervaloSondeo) arrancarSondeo(deseado);
  }

  if (d.status !== 'running') rematar(d);
}

function rematar(d) {
  if (d.status === 'done' || d.status === 'cancelado' || d.status === 'interrumpido'
      || d.status === 'presupuesto_agotado') {
    pararSondeo();
    ponerEnMarcha(false);
    document.getElementById('btn-iniciar').textContent = '🔍 Nueva Búsqueda';
    document.getElementById('result-box').style.display = 'block';

    if (d.status === 'done') {
      document.getElementById('prog-label').textContent = '¡Completado!';
      document.getElementById('result-titulo').textContent =
        `✅ ${d.nuevos_en_sheet} contactos nuevos en la hoja — ${d.ciudad}`;
      document.getElementById('result-desc').textContent =
        `De ${d.encontrados + d.descartados} candidatos de Google, ${d.encontrados} pasaron los ` +
        `filtros de calidad: ${d.nuevos_en_sheet} se guardaron y ${d.duplicados} ya estaban en la lista. ` +
        `Los otros ${d.descartados} se descartaron por reseñas, calificación o falta de teléfono.`;
    } else {
      const titulos = {
        cancelado: '⏹ Búsqueda detenida — ',
        presupuesto_agotado: '⛔ Se alcanzó el tope de gasto — ',
        interrumpido: '⚠ Búsqueda interrumpida — ',
      };
      document.getElementById('result-titulo').textContent =
        (titulos[d.status] || '⚠ ') + d.ciudad;
      document.getElementById('result-desc').textContent =
        (d.status === 'presupuesto_agotado' ? d.error + ' ' : '') +
        `Se alcanzaron a guardar ${d.nuevos_en_sheet} contactos nuevos, y siguen en la hoja. ` +
        `Volver a correr la misma ciudad no los duplica.`;
    }
  }

  if (d.status === 'error') {
    pararSondeo();
    ponerEnMarcha(false);
    document.getElementById('prog-label').textContent = '❌ Error: ' + d.error;
    document.getElementById('btn-iniciar').textContent = '🔍 Reintentar';
    document.getElementById('result-box').style.display = 'block';
    document.getElementById('result-titulo').textContent = '❌ La búsqueda falló — ' + d.ciudad;
    document.getElementById('result-desc').textContent =
      (d.error || '') + ` Se alcanzaron a guardar ${d.nuevos_en_sheet} contactos nuevos.`;
  }
}

restaurarEstado();

</script>
</body>
</html>"""


@app.route('/formulario')
def formulario():
    return render_template_string(FORMULARIO_HTML)


@app.route('/')
def index():
    return render_template_string(HTML)


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5050))
    print(f"Panel NIOVAL → http://localhost:{port}")
    app.run(host='0.0.0.0', port=port, debug=False)
