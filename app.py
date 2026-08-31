"""
Panel Principal NIOVAL
Dashboard centralizado: Prospectos + Seguimiento
Deploy: Railway  |  Auth: GOOGLE_CREDENTIALS_JSON env var o archivo .json local
"""

from flask import Flask, jsonify, render_template, request, session
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
# Va en UNA sola variable a proposito. Con dos, publicarlas son dos STORE_GLOBAL
# separados y un thread podia ver el catalogo ya puesto y el indice todavia en None
# —gunicorn corre 4 threads y el dashboard y el importador piden a la vez al
# cargar—, y el segundo se llevaba un AttributeError en indice.get().
_estado_catalogo = None

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
    global _estado_catalogo
    if _estado_catalogo is not None:
        return _estado_catalogo
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
    _estado_catalogo = (catalogo, indice)
    return _estado_catalogo


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


# Limites del factor. Nombrados porque el mismo recorte lo aplican las dos rutas:
# como literales, cambiar el ADR obligaba a acordarse de tocar los dos sitios.
FACTOR_MIN = 0.60
FACTOR_MAX = 1.25


def _calcular_factor_nioval(metricas: dict, unidades: int, referencia: float) -> float:
    """desempeno x saturacion, recortado. UNICO sitio donde se combinan."""
    bruto = (_factor_desempeno(metricas['llamados'], metricas['aprobados'], referencia)
             * _factor_saturacion(metricas['total'], unidades))
    return round(max(FACTOR_MIN, min(FACTOR_MAX, bruto)), 3)


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
        # 'Sin ciudad' NO se salta: es un contacto real con la celda CIUDAD vacia,
        # y saltarlo lo hacia desaparecer de las dos listas a la vez. Cae por el
        # mismo camino que cualquier otro valor que no case, que es donde el
        # operador puede verlo.
        reg = None if m['ciudad'] == 'Sin ciudad' else indice.get(_normalizar_ciudad(m['ciudad']))
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
        factor = _calcular_factor_nioval(m, unidades, referencia)
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
        # Sin esto, "el archivo del catalogo no carga" y "ninguna ciudad de la hoja
        # caso" se ven identicos desde el navegador: lista vacia y todo en
        # sin_clasificar. Son dos problemas distintos con dos arreglos distintos.
        'catalogo_cargado': bool(catalogo),
    })

def _agregar_por_ciudad(contactos: list, respuestas: list) -> list:
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

    # OBSOLETO desde 2026-08-28 (Plan 1, T1.6). Retirar cuando el dashboard deje
    # de leerlo, no antes del 2026-12-01. Sus TRES terminos son endogenos —salen
    # del historial propio de NIOVAL—, asi que una ciudad donde nunca se trabajo
    # puntua 0 haga lo que haga el mercado. Se conserva porque el dashboard
    # ordenaba por el y cambiarle el significado sin avisar rompe la lectura del
    # owner. Lo que hay que mirar ahora es `prioridad`.
    max_total = max((r['total'] for r in result), default=1)
    for r in result:
        r['relevancia'] = round(
            r['interes_pct'] * 1.5 +
            (r['total'] / max_total) * 40 +
            min(r['llamados'] * 2, 20), 1
        )

    # Modelo de dos factores: docs/adr/2026-08-28-modelo-relevancia-ciudades.md
    _, indice = _cargar_catalogo_ciudades()
    total_llamados = sum(r['llamados'] for r in result)
    total_aprobados = sum(r['aprobados'] for r in result)
    referencia = (total_aprobados / total_llamados) if total_llamados else INTERES_REFERENCIA

    for r in result:
        reg = indice.get(_normalizar_ciudad(r['ciudad']))
        if reg is None:
            # 'Sin ciudad' y los valores sucios de la hoja no tienen potencial que
            # medir. Se dice que no hay en vez de inventar un cero: un cero se lee
            # como "mercado nulo", que es una afirmacion, no una ausencia de dato.
            r['potencial_mercado'] = None
            r['desempeno_nioval'] = None
            r['prioridad'] = None
            continue
        unidades = reg['indicadores']['unidades_ferreteras']
        factor = _calcular_factor_nioval(r, unidades, referencia)
        r['potencial_mercado'] = reg['potencial_mercado']
        r['desempeno_nioval'] = factor
        r['prioridad'] = round(reg['potencial_mercado'] * factor, 1)

    # Las ciudades sin catalogo van al final en vez de mezclarse en la mitad de la
    # tabla con una prioridad inventada. El desempate replica el del ADR.
    result.sort(key=lambda x: (
        x['prioridad'] is None,
        -(x['prioridad'] or 0),
        -x['relevancia'],
        x['ciudad'],
    ))
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
        # La hoja guarda el numero nacional con espacios ('555 123 4567'); el
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
    return render_template('importador.html')


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




@app.route('/formulario')
def formulario():
    return render_template('formulario.html')


@app.route('/')
def index():
    return render_template('dashboard.html')


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5050))
    print(f"Panel NIOVAL → http://localhost:{port}")
    app.run(host='0.0.0.0', port=port, debug=False)
