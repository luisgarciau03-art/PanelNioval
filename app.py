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
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import os, json, time, io, base64, requests as req_lib
from datetime import datetime
from collections import Counter, defaultdict
import traceback

app = Flask(__name__)
app.json.sort_keys = False
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(16))

# ─── CONFIG ─────────────────────────────────────────────────────────────────
SHEET_IDS = {
    'ventas':      '1Dlpm6swrNSPnt9L5tQhoi2OMln0bb8bqqgeLACNos98',
    'frecuentes':  '1wgEentS16hJrcf6YdEnSpEBcp4SCBJ9TkOCZY439jV4',  # hoja FRECUENTES dentro del mismo sheet de contactos
    'contactos':   '1wgEentS16hJrcf6YdEnSpEBcp4SCBJ9TkOCZY439jV4',
    'respuestas':  '1U_z1KNqCxSRZVi7wvO2FQH4zIdS_wxuafxj6YHdHEqg',
    'mensajes':    '1oEtAiYaYVdOnEum3tbp_BminBUdj06JzXqJhaOVQFlk',
    'seguimiento': '1i0bWYQG7d5GVvOjuklZRpsg1bQfsScdY0bg7lytMXKM',
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
_gs_client = None
_drive_service = None
_pago_folder_id = None
PAGO_FOLDER_NAME = 'NIOVAL_PAGOS'

# ─── GOOGLE SHEETS ───────────────────────────────────────────────────────────
def get_gs_client():
    global _gs_client
    if _gs_client:
        return _gs_client
    scopes = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive',
    ]
    creds_json = os.environ.get('GOOGLE_CREDENTIALS_JSON')
    if creds_json:
        info = json.loads(creds_json)
        creds = Credentials.from_service_account_info(info, scopes=scopes)
    else:
        creds = Credentials.from_service_account_file(
            'bubbly-subject-412101-c969f4a975c5.json', scopes=scopes
        )
    _gs_client = gspread.authorize(creds)
    return _gs_client


def get_drive_service():
    global _drive_service
    if _drive_service:
        return _drive_service
    scopes = [
        'https://www.googleapis.com/auth/drive',
        'https://www.googleapis.com/auth/spreadsheets',
    ]
    creds_json = os.environ.get('GOOGLE_CREDENTIALS_JSON')
    if creds_json:
        info = json.loads(creds_json)
        creds = Credentials.from_service_account_info(info, scopes=scopes)
    else:
        creds = Credentials.from_service_account_file(
            'bubbly-subject-412101-c969f4a975c5.json', scopes=scopes
        )
    _drive_service = build('drive', 'v3', credentials=creds)
    return _drive_service


def get_pago_folder_id():
    """Obtiene la carpeta NIOVAL_PAGOS desde env var (carpeta compartida del usuario)."""
    global _pago_folder_id
    if _pago_folder_id:
        return _pago_folder_id
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
    if not force and key in _cache:
        data, ts = _cache[key]
        if now - ts < CACHE_TTL:
            return data
    try:
        ws = get_worksheet(key)
        rows = ws.get_all_values()
        data = values_to_records(rows)
        _cache[key] = (data, now)
        print(f"[OK] {key} -> {len(data)} filas desde '{ws.title}' (gid={ws.id})")
        return data
    except Exception as e:
        print(f"[ERROR] get_data({key}): {e}")
        traceback.print_exc()
        if key in _cache:
            return _cache[key][0]
        return []


# GIDs de todas las hojas de respuestas a combinar
_RESPUESTAS_GIDS = [1343998886]  # Respuestas de formulario 1

def get_all_respuestas(force: bool = False) -> list:
    """Lee Respuestas de formulario 1 + Bruce FORMS y los combina en un dataset unificado."""
    cache_key = 'all_respuestas'
    now = time.time()
    if not force and cache_key in _cache:
        data, ts = _cache[cache_key]
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
        _cache[cache_key] = (all_records, now)
        print(f"[respuestas] TOTAL combinado: {len(all_records)} filas")
        return all_records
    except Exception as e:
        print(f"[ERROR] get_all_respuestas: {e}")
        traceback.print_exc()
        if cache_key in _cache:
            return _cache[cache_key][0]
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
        _cache.clear()
    else:
        _cache.pop(key, None)
        if key == 'respuestas':
            _cache.pop('all_respuestas', None)
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
                _cache.pop('ventas', None)
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
        _cache.pop('ventas', None)

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
    """Mensajes: fila 1 = encabezados de columna, filas 2+ = registros (estándar)."""
    try:
        ws = get_worksheet('mensajes')
        rows = ws.get_all_values()
        records = values_to_records(rows)
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


@app.route('/api/prospectos/ciudades')
def api_ciudades():
    contactos  = get_data('contactos')
    respuestas = get_all_respuestas()

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
    _cache.pop(cache_key or ws_key, None)
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
    row_num = body.get('_row')
    if not row_num:
        return jsonify({'error': 'Falta _row'}), 400
    fields = {k: v for k, v in body.items() if not k.startswith('_')}
    try:
        n = _sheet_update_row('mensajes', row_num, fields)
        print(f"[mensajes] update row={row_num} fields={list(fields.keys())} updated={n}")
        return jsonify({'ok': True, 'updated': n})
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
  </div>

  <div class="nav-group">
    <div class="nav-label">Seguimiento</div>
    <div class="nav-item" onclick="showSection('seguimiento')">
      <span class="icon">🔄</span> Seguimiento
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
          <input type="text" id="mensajes-search" placeholder="🔍 Buscar..." oninput="filterTable('mensajes')">
        </div>
        <div class="tbl-wrap" id="mensajes-table"><div class="loading"><div class="spinner"></div></div></div>
        <div class="pagination" id="mensajes-pag"></div>
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
  seguimiento: '🔄 Seguimiento',
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
    case 'mensajes':    await loadTableSection('mensajes',    '/api/prospectos/mensajes',    'mensajes-table',    'mensajes-pag',    ['mensajes-search']); break;
    case 'seguimiento': await loadSeguimiento(); break;
  }
}

// ─── FETCH ──────────────────────────────────────────────────────────────────
async function fetchAPI(url) {
  const res = await fetch(url);
  return res.json();
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
  const isVentas = key === 'ventas' || key === 'frecuentes';
  const isRespuestas = key === 'respuestas';

  let sortedCols;
  if (isVentas) {
    sortedCols = VENTAS_COLS.filter(c => allCols.includes(c));
    allCols.filter(c => !VENTAS_COLS.includes(c) && c.trim() !== '').forEach(c => sortedCols.push(c));
  } else if (isRespuestas) {
    sortedCols = RESPUESTAS_COLS.filter(c => allCols.includes(c));
  } else {
    sortedCols = allCols.filter(c => c.trim() !== '').slice(0, 20);
  }

  const isSeguimiento = key === 'seguimiento';
  const isMensajes    = key === 'mensajes';
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
    if (isMensajes    && row._row) _menRowMap[row._row] = row;
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

  if (val.startsWith('http')) return `<a href="${val}" target="_blank" style="color:var(--blue);font-size:.8em">Ver →</a>`;
  if (val.length > 80) return `<span title="${val.replace(/"/g,'&quot;')}">${val.slice(0,78)}…</span>`;
  return val;
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
const _menRowMap = {};
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

function openEditMen(rowNum) {
  openEdit({ endpoint: '/api/mensajes/update', rowMap: _menRowMap,
    columnOptions: {}, label: 'Mensajes',
    reload: async () => {
      delete state.loaded['mensajes'];
      await loadTableSection('mensajes', '/api/prospectos/mensajes', 'mensajes-table', 'mensajes-pag', ['mensajes-search']);
    }
  }, colNum);
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

// ─── INIT ────────────────────────────────────────────────────────────────────
loadSection('dashboard');
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
        _cache.pop('contactos', None)
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
        if r7 == 'Colgo':                  col_j = 'Colgo'
        elif r0 == 'Buzon':                col_j = 'BUZON'
        elif r0 == 'Telefono Incorrecto':  col_j = 'TELEFONO INCORRECTO'
        elif resultado == 'NEGADO':        col_j = 'No apto'
        elif resultado == 'NO COMPATIBLE': col_j = 'No compatible'
        elif resultado == 'MARCA UNICA':   col_j = 'Marca Unica'
        elif r7:                           col_j = r7

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
        _cache.pop('respuestas', None)
        _cache.pop('all_respuestas', None)
        print(f"[formulario] OK — fila {f} guardada en '{ws.title}'")
        return True
    except Exception as e:
        print(f"[formulario] ERROR guardar: {e}")
        traceback.print_exc()
        return False


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
        row          = datos.get('row')
        col_respuesta = datos.get('col_respuesta', 6)
        ok = guardar_respuesta_formulario(datos)
        if ok and row:
            marcar_contacto_procesado(int(row), int(col_respuesta))
        return jsonify({'ok': ok})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


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
      <button class="btn btn-gray" onclick="colgo()" style="margin-top:8px;width:100%;font-size:.82em">📵 Colgó</button>
    </div>

    <!-- PREGUNTA 2 -->
    <div class="step" id="step-p2">
      <div class="progress" id="prog2"></div>
      <div class="section-title">¿Toma usted las decisiones de compra?</div>
      <div class="btn-group">
        <button class="btn btn-green" onclick="resp2('Sí')">✓ Sí</button>
        <button class="btn btn-red"   onclick="resp2('No')">✗ No</button>
      </div>
      <button class="btn btn-gray" onclick="colgo()" style="margin-top:8px;width:100%;font-size:.82em">📵 Colgó</button>
    </div>

    <!-- PREGUNTA 3 -->
    <div class="step" id="step-p3">
      <div class="progress" id="prog3"></div>
      <div class="section-title">¿Le podemos ayudar con el pedido inicial?</div>
      <div class="btn-group" style="flex-direction:column">
        <button class="btn btn-green" onclick="resp3('Crear Pedido Inicial Sugerido')">✓ Crear Pedido Inicial Sugerido</button>
        <button class="btn btn-red"   onclick="resp3('No')">✗ No</button>
      </div>
      <button class="btn btn-gray" onclick="colgo()" style="margin-top:8px;width:100%;font-size:.82em">📵 Colgó</button>
    </div>

    <!-- PREGUNTA 4 -->
    <div class="step" id="step-p4">
      <div class="progress" id="prog4"></div>
      <div class="section-title">Pedido Muestra ($1,500 — envío cubierto)</div>
      <div class="btn-group">
        <button class="btn btn-green" onclick="resp4('Sí')">✓ Sí</button>
        <button class="btn btn-red"   onclick="resp4('No')">✗ No</button>
      </div>
      <button class="btn btn-gray" onclick="colgo()" style="margin-top:8px;width:100%;font-size:.82em">📵 Colgó</button>
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
      <button class="btn btn-gray" onclick="colgo()" style="margin-top:8px;width:100%;font-size:.82em">📵 Colgó</button>
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
      <button class="btn btn-gray" onclick="colgo()" style="margin-top:8px;width:100%;font-size:.82em">📵 Colgó</button>
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
        <div class="stat-row">
          <div class="stat"><div class="n" id="stat-procesados">0</div><div class="l">Procesados</div></div>
          <div class="stat"><div class="n" id="stat-pendientes">—</div><div class="l">Restantes</div></div>
        </div>
        <button class="btn btn-green" onclick="cargarSiguiente()" style="margin-top:20px;width:100%">→ Siguiente Contacto</button>
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
  showStep('loading');
  document.getElementById('header-sub').textContent = 'Cargando contacto...';
  const r = await fetch(`/api/formulario/siguiente?skip=${O.skip}`);
  const d = await r.json();
  if (d.fin) { showStep('fin'); document.getElementById('stat-total').textContent = O.procesados; return; }
  O.contacto = d.contacto;
  renderContacto(d.contacto);
}

function renderContacto(c) {
  const tienda = c.TIENDA || c.Tienda || c.Nombre || '(Sin nombre)';
  const ciudad = c.CIUDAD || c.Ciudad || '';
  const tel    = c.TELÉFONO || c['Teléfono'] || c.TELEFONO || c.Telefono || '';
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
  if (maps && maps.startsWith('http')) links.push(`<a class="link-btn" href="${maps}" target="_blank">🗺️ Google Maps</a>`);
  if (link && link.startsWith('http')) links.push(`<a class="link-btn" href="${link}" target="_blank">🌐 Sitio Web</a>`);
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
function resp7(v) { O.r7=v; guardar(); }

function colgo() { O.r7='Colgo'; guardar(); }

function saltarContacto() { O.skip++; cargarContacto(); }

async function guardar() {
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
      showStep('contacto');
      alert('⚠️ Error al guardar: ' + (d.error || 'No se pudo guardar en la hoja. Intenta de nuevo.'));
      return;
    }
    O.procesados++;
    document.getElementById('stat-procesados').textContent = O.procesados;
    document.getElementById('resumen-guardado').textContent =
      `${tienda} → ${O.resultado}${O.r0 && O.r0 !== 'Respondio' ? ' ('+O.r0+')' : ''}`;
    showStep('siguiente');
  } catch(e) {
    showStep('contacto');
    alert('⚠️ Error de conexión al guardar. Verifica tu internet e intenta de nuevo.');
  }
}

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

_import_job = {
    'status':    'idle',   # idle | running | done | error
    'ciudad':    '',
    'categoria': '',
    'progreso':  0,        # categorías completadas
    'total':     len(CATEGORIAS_IMPORTADOR),
    'encontrados': 0,
    'descartados': 0,
    'resultados': [],
    'log':        [],
    'error':      '',
}
_import_lock = threading.Lock()


def _buscar_negocios(gmaps_client, categoria, ciudad):
    """Busca negocios con filtros de calidad. Campos y lógica idénticos al script original."""
    resultados = []
    vistos = set()
    stats  = {'pocas_resenas': 0, 'baja_calificacion': 0, 'cerrado': 0, 'sin_telefono': 0}

    variaciones = [
        f"{categoria} en {ciudad}",
        f"{categoria} cerca de {ciudad}",
        f"{categoria} {ciudad}",
    ]

    for query in variaciones:
        for intento in range(3):
            try:
                resp   = gmaps_client.places(query=query, language='es', type='establishment')
                lugares = resp.get('results', [])
                paginas = 1
                while 'next_page_token' in resp and paginas < 3:
                    time.sleep(2)
                    try:
                        resp = gmaps_client.places(page_token=resp['next_page_token'])
                        lugares.extend(resp.get('results', []))
                        paginas += 1
                    except Exception:
                        break

                for lugar in lugares:
                    pid     = lugar.get('place_id')
                    if pid in vistos: continue
                    cal     = lugar.get('rating')
                    resenas = lugar.get('user_ratings_total')

                    if not resenas or resenas < 5:
                        stats['pocas_resenas'] += 1; continue
                    if not cal or cal < 3.5:
                        stats['baja_calificacion'] += 1; continue

                    vistos.add(pid)
                    try:
                        det = gmaps_client.place(pid, language='es')['result']
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
                    except Exception:
                        continue

                if lugares: break

            except Exception as e:
                print(f'[importador] error query intento {intento+1}: {e}')
                if intento < 2: time.sleep(2 ** intento)

        if query != variaciones[-1]: time.sleep(1)

    return resultados, stats


def _exportar_a_sheets(resultados, categoria, ciudad):
    """Exporta a LISTA DE CONTACTOS con columnas idénticas al script original."""
    try:
        ws = get_worksheet('contactos')
        datos_actuales = ws.get_all_values()

        # Detección de duplicados: Nombre|Dirección (igual que el original)
        nombres_existentes = set()
        for fila in datos_actuales[1:]:
            if len(fila) > 7:
                nombres_existentes.add(f"{fila[1]}|{fila[7]}")

        fecha  = datetime.now().strftime('%d/%m/%Y')
        semana = datetime.now().isocalendar()[1]
        nuevos = []

        for r in resultados:
            key = f"{r['Nombre']}|{r['Dirección']}"
            if key not in nombres_existentes:
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
            ws.append_rows(nuevos, value_input_option='USER_ENTERED')
            _cache.pop('contactos', None)
        return len(nuevos)
    except Exception as e:
        print(f'[importador] sheets error: {e}')
        traceback.print_exc()
        return 0


def _enviar_telegram_importador(ciudad, total, desglose, tiempo_min):
    try:
        token   = os.environ.get('TELEGRAM_TOKEN', '8404009072:AAGZC4Lb46ELP9-8zrRDWJG61a5F5lHjmSw')
        chat_id = os.environ.get('TELEGRAM_CHAT_ID', '5838212022')
        msg = f"<b>📥 Importador Completado</b>\n\n<b>Ciudad:</b> {ciudad}\n<b>Total:</b> {total} contactos\n<b>Tiempo:</b> {tiempo_min:.1f} min\n\n"
        for cat, n in desglose.items():
            msg += f"  {cat}: {n}\n"
        req_lib.post(f'https://api.telegram.org/bot{token}/sendMessage',
                     data={'chat_id': chat_id, 'text': msg, 'parse_mode': 'HTML'}, timeout=10)
    except Exception:
        pass


def _worker_importador(ciudad, gmaps_api_key):
    global _import_job
    inicio = time.time()
    try:
        if not GMAPS_OK:
            with _import_lock:
                _import_job['status'] = 'error'
                _import_job['error']  = 'googlemaps no instalado'
            return

        gmaps = googlemaps.Client(key=gmaps_api_key)
        todos = []
        desglose = {}

        for i, cat in enumerate(CATEGORIAS_IMPORTADOR):
            with _import_lock:
                _import_job['categoria'] = cat
                _import_job['progreso']  = i
                _import_job['log'].append(f'Buscando {cat} en {ciudad}...')

            resultados, stats = _buscar_negocios(gmaps, cat, ciudad)

            # Agregar ciudad a cada resultado
            for r in resultados:
                r['CIUDAD'] = ciudad

            nuevos = _exportar_a_sheets(resultados, cat, ciudad)
            todos.extend(resultados)
            desglose[cat] = len(resultados)

            desc = sum(stats.values())
            with _import_lock:
                _import_job['encontrados'] += len(resultados)
                _import_job['descartados'] += desc
                _import_job['resultados']   = todos[:]
                _import_job['log'].append(
                    f'✓ {cat}: {len(resultados)} aprobados, {desc} descartados, {nuevos} nuevos en Sheet'
                )

        tiempo = (time.time() - inicio) / 60
        _enviar_telegram_importador(ciudad, len(todos), desglose, tiempo)

        with _import_lock:
            _import_job['status']   = 'done'
            _import_job['progreso'] = len(CATEGORIAS_IMPORTADOR)
            _import_job['log'].append(f'✅ Completado en {tiempo:.1f} min — {len(todos)} contactos encontrados')

    except Exception as e:
        with _import_lock:
            _import_job['status'] = 'error'
            _import_job['error']  = str(e)
        traceback.print_exc()


@app.route('/importador')
def importador_page():
    return render_template_string(IMPORTADOR_HTML)


@app.route('/api/importador/iniciar', methods=['POST'])
def importador_iniciar():
    global _import_job
    ciudad       = request.json.get('ciudad', '').strip()
    gmaps_api_key = os.environ.get('GMAPS_API_KEY', 'AIzaSyANnZsLqkul5Z8x1PlVsaihlHkpJHqDhJU')

    if not ciudad:
        return jsonify({'ok': False, 'error': 'Ciudad requerida'})

    with _import_lock:
        if _import_job['status'] == 'running':
            return jsonify({'ok': False, 'error': 'Ya hay una búsqueda en curso'})
        _import_job = {
            'status': 'running', 'ciudad': ciudad,
            'categoria': '', 'progreso': 0,
            'total': len(CATEGORIAS_IMPORTADOR),
            'encontrados': 0, 'descartados': 0,
            'resultados': [], 'log': [], 'error': '',
        }

    t = threading.Thread(target=_worker_importador, args=(ciudad, gmaps_api_key), daemon=True)
    t.start()
    return jsonify({'ok': True})


@app.route('/api/importador/estado')
def importador_estado():
    with _import_lock:
        return jsonify({
            'status':     _import_job['status'],
            'ciudad':     _import_job['ciudad'],
            'categoria':  _import_job['categoria'],
            'progreso':   _import_job['progreso'],
            'total':      _import_job['total'],
            'encontrados': _import_job['encontrados'],
            'descartados': _import_job['descartados'],
            'log':        _import_job['log'][-10:],
            'error':      _import_job['error'],
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
.stats-row{display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;margin-bottom:16px}
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
      <div class="stat-box green"><div class="n" id="s-encontrados">0</div><div class="l">Encontrados</div></div>
      <div class="stat-box red"><div class="n" id="s-descartados">0</div><div class="l">Descartados</div></div>
      <div class="stat-box blue"><div class="n" id="s-progreso">0/0</div><div class="l">Progreso</div></div>
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
let ciudadSeleccionada = '';

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

    document.getElementById('ciudades-count').textContent = `(${todasCiudades.length})`;
    renderChips(todasCiudades);
  } catch(e) {
    // Fallback: solo estáticas
    todasCiudades = [...new Set(CIUDADES_MX)].map(c => ({
      ciudad: c, total: 0, llamados: 0, aprobados: 0, interes_pct: 0, relevancia: 0
    }));
    document.getElementById('ciudades-count').textContent = `(${todasCiudades.length})`;
    renderChips(todasCiudades);
  }
}

function renderChips(lista) {
  const cont = document.getElementById('ciudades-chips');
  if (!lista.length) { cont.innerHTML = '<div style="color:#aaa;font-size:.82em">Sin resultados</div>'; return; }

  cont.innerHTML = lista.map((c, i) => {
    const rank   = i + 1;
    const medal  = rank === 1 ? '🥇 ' : rank === 2 ? '🥈 ' : rank === 3 ? '🥉 ' : `${rank}. `;
    const isTop  = rank <= 3;
    const hasInt = c.interes_pct > 0;
    const badge  = hasInt
      ? `<span style="background:rgba(0,204,71,.2);color:#155724;padding:1px 5px;border-radius:8px;font-size:.85em">${c.interes_pct}%</span>`
      : `<span style="opacity:.55;font-size:.85em">${c.total}</span>`;
    return `<span class="chip ${isTop?'top':''}" onclick="seleccionarCiudad('${c.ciudad}',this)">${medal}${c.ciudad} ${badge}</span>`;
  }).join('');
}

function filtrarCiudades() {
  const q = document.getElementById('ciudad-filter').value.toLowerCase().trim();
  renderChips(q ? todasCiudades.filter(c => c.ciudad.toLowerCase().includes(q)) : todasCiudades);
}

function seleccionarCiudad(ciudad, el) {
  document.getElementById('input-ciudad').value = ciudad;
  document.querySelectorAll('.chip').forEach(c => c.classList.remove('active'));
  el.classList.add('active');
}

cargarCiudades();

async function iniciar() {
  const ciudad = document.getElementById('input-ciudad').value.trim();
  if (!ciudad) { alert('Ingresa una ciudad'); return; }

  const btn = document.getElementById('btn-iniciar');
  btn.disabled = true;
  btn.textContent = '⏳ Buscando...';

  document.getElementById('progress-box').style.display = 'block';
  document.getElementById('stats-row').style.display = 'grid';
  document.getElementById('log-box').style.display = 'block';
  document.getElementById('result-box').style.display = 'none';

  const r = await fetch('/api/importador/iniciar', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({ciudad})
  });
  const d = await r.json();
  if (!d.ok) { alert('Error: ' + d.error); btn.disabled=false; btn.textContent='🔍 Buscar'; return; }

  polling = setInterval(actualizarEstado, 3000);
  actualizarEstado();
}

async function actualizarEstado() {
  const r = await fetch('/api/importador/estado');
  const d = await r.json();

  // Progreso
  const pct = d.total > 0 ? Math.round((d.progreso / d.total) * 100) : 0;
  document.getElementById('prog-fill').style.width  = pct + '%';
  document.getElementById('prog-pct').textContent   = pct + '%';
  document.getElementById('prog-label').textContent = d.categoria ? `Buscando: ${d.categoria}...` : 'Procesando...';

  // Stats
  document.getElementById('s-encontrados').textContent = d.encontrados;
  document.getElementById('s-descartados').textContent = d.descartados;
  document.getElementById('s-progreso').textContent    = `${d.progreso}/${d.total}`;

  // Cat badges
  CATS.forEach((c, i) => {
    const el = document.getElementById('cat-'+i);
    if (i < d.progreso) el.className = 'cat-badge done';
    else if (d.categoria === c) el.className = 'cat-badge active';
  });

  // Log
  const logEl = document.getElementById('log-box');
  logEl.innerHTML = d.log.map(l => `<div class="entry">> ${l}</div>`).join('');
  logEl.scrollTop = logEl.scrollHeight;

  if (d.status === 'done') {
    clearInterval(polling);
    document.getElementById('prog-fill').style.width = '100%';
    document.getElementById('prog-pct').textContent = '100%';
    document.getElementById('prog-label').textContent = '¡Completado!';
    CATS.forEach((_,i) => document.getElementById('cat-'+i).className = 'cat-badge done');
    document.getElementById('result-box').style.display = 'block';
    document.getElementById('result-titulo').textContent = `✅ Búsqueda completada — ${d.ciudad}`;
    document.getElementById('result-desc').textContent =
      `${d.encontrados} contactos encontrados · ${d.descartados} descartados · Guardados en Google Sheets`;
    document.getElementById('btn-iniciar').textContent = '🔍 Nueva Búsqueda';
    document.getElementById('btn-iniciar').disabled = false;
  }

  if (d.status === 'error') {
    clearInterval(polling);
    document.getElementById('prog-label').textContent = '❌ Error: ' + d.error;
    document.getElementById('btn-iniciar').disabled = false;
    document.getElementById('btn-iniciar').textContent = '🔍 Reintentar';
  }
}
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
