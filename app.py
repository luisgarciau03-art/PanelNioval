"""
Panel Principal NIOVAL
Dashboard centralizado: Prospectos + Seguimiento
Deploy: Railway  |  Auth: GOOGLE_CREDENTIALS_JSON env var o archivo .json local
"""

from flask import Flask, jsonify, render_template_string, request
import gspread
from google.oauth2.service_account import Credentials
import os, json, time
from datetime import datetime
from collections import Counter, defaultdict
import traceback

app = Flask(__name__)

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
    'ventas':      1509137423,  # Hoja 12 (5620 filas) — validar columnas
    'frecuentes':  1061706533,   # hoja FRECUENTES en spreadsheet contactos
    'contactos':   823047163,
    'respuestas':  1343998886,
    'mensajes':    0,
    'seguimiento': 258325319,
}

_cache: dict = {}
CACHE_TTL = 300  # 5 minutos
_gs_client = None

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
    for row in rows[1:]:
        # Ignorar filas completamente vacías
        if not any(str(c).strip() for c in row):
            continue
        padded = list(row) + [''] * (len(headers) - len(row))
        records.append({headers[i]: str(padded[i]).strip() for i in range(len(headers))})
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
    return jsonify({'ok': True})


@app.route('/api/prospectos/stats')
def api_stats():
    contactos = get_data('contactos')
    respuestas = get_data('respuestas')

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


@app.route('/api/prospectos/respuestas')
def api_respuestas():
    data = get_data('respuestas')
    return jsonify(data)


@app.route('/api/prospectos/ventas')
def api_ventas():
    data = get_data('ventas')
    return jsonify(filter_ventas_cols(data))


@app.route('/api/prospectos/mensajes')
def api_mensajes():
    data = get_data('mensajes')
    return jsonify(data)


VENTAS_COLS = ['Fecha', 'Cliente', 'ESQUEMA', 'MES', 'Monto ', 'Monto', 'Envio Costo', 'Num Factura', 'Cotizacion PDF', 'PAGO']

def filter_ventas_cols(data: list) -> list:
    """Devuelve solo las columnas de ventas en el orden exacto definido."""
    result = []
    for row in data:
        # Solo columnas que existan en VENTAS_COLS, en ese orden
        clean = {k: row[k] for k in VENTAS_COLS if k in row}
        if any(str(v).strip() for v in clean.values()):
            result.append(clean)
    return result


@app.route('/api/prospectos/frecuentes')
def api_frecuentes():
    data = get_data('frecuentes')
    return jsonify(filter_ventas_cols(data))


@app.route('/api/prospectos/ciudades')
def api_ciudades():
    contactos = get_data('contactos')
    respuestas = get_data('respuestas')

    # Columnas reales: "Nombre De la Tienda", "Compatible" (resultado), "Respondio" (estado)
    resp_por_tienda: dict = {}
    for r in respuestas:
        nombre = str_val(r.get('Nombre De la Tienda', r.get('TIENDA', r.get('Tienda', '')))).strip().upper()
        if nombre:
            resp_por_tienda[nombre] = r

    ciudades: dict = defaultdict(lambda: {
        'total': 0, 'llamados': 0, 'aprobados': 0,
        'buzon': 0, 'tel_incorrecto': 0, 'negados': 0,
        'no_compatible': 0, 'marca_unica': 0,
    })

    for c in contactos:
        ciudad = str_val(c.get('CIUDAD', c.get('Ciudad', c.get('ciudad', '')))).title().strip()
        if not ciudad:
            ciudad = 'Sin ciudad'
        nombre = str_val(c.get('TIENDA', c.get('Tienda', c.get('Nombre', '')))).strip().upper()
        ciudades[ciudad]['total'] += 1

        if nombre in resp_por_tienda:
            r = resp_por_tienda[nombre]
            ciudades[ciudad]['llamados'] += 1
            res    = str_val(r.get('Compatible', '')).upper()   # col S = resultado
            estado = str_val(r.get('Respondio', '')).strip()    # col T = estado llamada
            if res == 'APROBADO':
                ciudades[ciudad]['aprobados'] += 1
            elif 'BUZON' in estado.upper() or 'BUZÓN' in estado.upper():
                ciudades[ciudad]['buzon'] += 1
            elif 'INCORRECTO' in estado.upper():
                ciudades[ciudad]['tel_incorrecto'] += 1
            elif res == 'NEGADO':
                ciudades[ciudad]['negados'] += 1
            elif res == 'NO COMPATIBLE':
                ciudades[ciudad]['no_compatible'] += 1
            elif res == 'MARCA UNICA':
                ciudades[ciudad]['marca_unica'] += 1

    result = []
    for ciudad, m in ciudades.items():
        interes = round(m['aprobados'] / m['llamados'] * 100, 1) if m['llamados'] > 0 else 0
        result.append({'ciudad': ciudad, **m, 'interes_pct': interes})

    result.sort(key=lambda x: (x['aprobados'], x['interes_pct']), reverse=True)
    return jsonify(result)


@app.route('/api/seguimiento')
def api_seguimiento():
    data = get_data('seguimiento')
    return jsonify(data)


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
    <div class="nav-label">Clientes Prospectos</div>
    <div class="nav-item active" onclick="showSection('dashboard')">
      <span class="icon">📊</span> Dashboard
    </div>
    <div class="nav-item" onclick="showSection('frecuentes')">
      <span class="icon">⭐</span> Clientes Frecuentes
    </div>
    <div class="nav-item" onclick="showSection('ventas')">
      <span class="icon">💰</span> Ventas
    </div>
    <div class="nav-item" onclick="showSection('contactos')">
      <span class="icon">📋</span> Lista de Contactos
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
        <h3>📝 Respuestas del Formulario</h3>
        <div class="table-controls">
          <input type="text" id="resp-search" placeholder="🔍 Buscar..." oninput="filterTable('respuestas')">
          <select id="resp-resultado" onchange="filterTable('respuestas')">
            <option value="">Todos los resultados</option>
            <option>APROBADO</option>
            <option>NEGADO</option>
            <option>NO COMPATIBLE</option>
            <option>MARCA UNICA</option>
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
      <div class="table-box">
        <h3>🔄 Tabla de Seguimiento</h3>
        <div class="table-controls">
          <input type="text" id="seg-search" placeholder="🔍 Buscar..." oninput="filterTable('seguimiento')">
        </div>
        <div class="tbl-wrap" id="seguimiento-table"><div class="loading"><div class="spinner"></div></div></div>
        <div class="pagination" id="seguimiento-pag"></div>
      </div>
    </div>

  </div><!-- /content -->
</div><!-- /main -->

<script>
// ─── STATE ──────────────────────────────────────────────────────────────────
const state = {
  currentSection: 'dashboard',
  loaded: {},
  data: {},
  filtered: {},
  page: {},
  pageSize: 50,
};

const SECTION_TITLES = {
  dashboard:   '📊 Dashboard Prospectos',
  frecuentes:  '⭐ Dashboard Clientes Frecuentes',
  ventas:      '💰 Ventas',
  contactos:   '📋 Lista de Contactos',
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
    case 'ventas':      await loadVentas(); break;
    case 'contactos':   await loadContactos(); break;
    case 'ciudades':    await loadCiudades(); break;
    case 'respuestas':  await loadTableSection('respuestas',  '/api/prospectos/respuestas',  'respuestas-table',  'respuestas-pag',  ['resp-search','resp-resultado']); break;
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
  // Mostrar hoja FRECUENTES tal cual, en orden de ingreso (sin agrupación)
  const data = await fetchAPI('/api/prospectos/frecuentes');
  state.data['frecuentes'] = data;
  state.filtered['frecuentes'] = data;
  state.page['frecuentes'] = 1;

  // KPIs simples
  document.getElementById('frec-cards').innerHTML = `
    <div class="card"><div class="label">Total Registros</div><div class="value">${data.length}</div><div class="sub">Clientes frecuentes</div></div>
  `;

  // Ocultar chart box si existe
  const chartBox = document.querySelector('#sec-frecuentes .chart-box');
  if (chartBox) chartBox.style.display = 'none';

  // Tabla directa en orden de ingreso (tal cual la hoja)
  renderTable('frecuentes', 'frec-top-table', 'frec-pag');
}

// ─── VENTAS (orden cronológico de ingreso) ────────────────────────────────────
async function loadVentas() {
  const data = await fetchAPI('/api/prospectos/ventas');
  // Mostrar en orden inverso: últimas entradas primero
  const reversed = [...data].reverse();
  state.data['ventas'] = reversed;
  state.filtered['ventas'] = reversed;
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

  // Generic text search across all fields
  const searchId = key === 'respuestas' ? 'resp-search' : key === 'frecuentes' ? 'frecuentes-search' : key + '-search';
  const searchEl = document.getElementById(searchId);
  const q = searchEl ? searchEl.value.toLowerCase() : '';
  if (q) {
    filtered = filtered.filter(row =>
      Object.values(row).some(v => String(v).toLowerCase().includes(q))
    );
  }

  // Specific filters
  if (key === 'respuestas') {
    const resEl = document.getElementById('resp-resultado');
    const res = resEl ? resEl.value.toUpperCase() : '';
    if (res) filtered = filtered.filter(r => String(r.Resultado || '').toUpperCase() === res);
  }
  if (key === 'contactos') {
    const ciudadEl = document.getElementById('contactos-ciudad');
    const ciudad = ciudadEl ? ciudadEl.value.toLowerCase() : '';
    const catEl = document.getElementById('contactos-cat');
    const cat = catEl ? catEl.value.toLowerCase() : '';
    if (ciudad) filtered = filtered.filter(r => String(r.Ciudad || r.ciudad || r.CIUDAD || '').toLowerCase() === ciudad);
    if (cat) filtered = filtered.filter(r => Object.values(r).some(v => String(v).toLowerCase() === cat));
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
  const slice = data.slice((page-1)*ps, page*ps);

  if (!slice.length) {
    document.getElementById(tableId).innerHTML = '<div class="empty">No hay datos</div>';
    document.getElementById(pagId).innerHTML = '';
    return;
  }

  const allCols = Object.keys(slice[0]).filter(k => !k.startsWith('_'));

  // Columnas fijas para ventas/frecuentes (en orden exacto de la hoja)
  const VENTAS_COLS = ['Fecha','Cliente','ESQUEMA','MES','Monto ','Monto','Envio Costo','Num Factura','Cotizacion PDF','PAGO'];
  const isVentas = key === 'ventas' || key === 'frecuentes';

  let sortedCols;
  if (isVentas) {
    // Mostrar solo columnas relevantes en el orden exacto indicado
    sortedCols = VENTAS_COLS.filter(c => allCols.includes(c));
    // Agregar cualquier columna extra no vacía que no esté en la lista fija
    allCols.filter(c => !VENTAS_COLS.includes(c) && c.trim() !== '').forEach(c => sortedCols.push(c));
  } else {
    // Para otras secciones: orden exacto de la hoja, sin reordenar
    sortedCols = allCols.filter(c => c.trim() !== '').slice(0, 20);
  }

  let html = `<table><thead><tr>${sortedCols.map(c => `<th>${c}</th>`).join('')}</tr></thead><tbody>`;
  slice.forEach(row => {
    html += '<tr>' + sortedCols.map(c => {
      const v = row[c] !== undefined ? row[c] : '';
      return `<td>${renderCell(c, String(v))}</td>`;
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

function renderCell(col, val) {
  if (!val || val === 'undefined') return '<span style="color:#ccc">—</span>';
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

// ─── CIUDADES ───────────────────────────────────────────────────────────────
let ciudadesData = [];
async function loadCiudades() {
  ciudadesData = await fetchAPI('/api/prospectos/ciudades');
  renderCiudades(ciudadesData);
}

function filterCiudades() {
  const q = document.getElementById('ciudades-search').value.toLowerCase();
  renderCiudades(q ? ciudadesData.filter(c => c.ciudad.toLowerCase().includes(q)) : ciudadesData);
}

function renderCiudades(data) {
  if (!data.length) { document.getElementById('ciudades-table').innerHTML = '<div class="empty">Sin datos</div>'; return; }
  const maxAprobados = Math.max(...data.map(c => c.aprobados), 1);
  let html = `<table><thead><tr>
    <th>#</th><th>Ciudad</th><th>Total Lista</th><th>Llamados</th><th>✓ Aprobados</th><th>Interés %</th>
    <th>Buzón</th><th>Tel. Inc.</th><th>Negados</th><th>No Compatible</th><th>Marca Única</th>
  </tr></thead><tbody>`;
  data.forEach((c, i) => {
    const barW = Math.round((c.aprobados / maxAprobados) * 120);
    html += `<tr>
      <td>${i+1}</td>
      <td><strong>${c.ciudad}</strong></td>
      <td>${c.total}</td>
      <td>${c.llamados}</td>
      <td>${c.aprobados} <span class="interes-bar" style="width:${barW}px"></span></td>
      <td><strong style="color:var(--green)">${c.interes_pct}%</strong></td>
      <td>${c.buzon}</td>
      <td>${c.tel_incorrecto}</td>
      <td>${c.negados}</td>
      <td>${c.no_compatible}</td>
      <td>${c.marca_unica}</td>
    </tr>`;
  });
  html += '</tbody></table>';
  document.getElementById('ciudades-table').innerHTML = html;
}

// ─── SEGUIMIENTO ────────────────────────────────────────────────────────────
async function loadSeguimiento() {
  const data = await fetchAPI('/api/seguimiento');
  state.data['seguimiento'] = data;
  state.filtered['seguimiento'] = data;
  state.page['seguimiento'] = 1;

  // Simple KPIs from seguimiento data
  const total = data.length;
  // Try to detect status column
  const statusKey = data.length ? Object.keys(data[0]).find(k => k.toLowerCase().includes('estado') || k.toLowerCase().includes('status') || k.toLowerCase().includes('etapa')) : null;
  let statusCounts = {};
  if (statusKey) {
    data.forEach(r => {
      const s = String(r[statusKey] || '').trim() || 'Sin estado';
      statusCounts[s] = (statusCounts[s] || 0) + 1;
    });
  }

  let cardsHtml = `<div class="card"><div class="label">Total Seguimiento</div><div class="value">${total}</div><div class="sub">Registros</div></div>`;
  Object.entries(statusCounts).slice(0,5).forEach(([s, n]) => {
    cardsHtml += `<div class="card"><div class="label">${s}</div><div class="value">${n}</div><div class="sub">${((n/total)*100).toFixed(0)}%</div></div>`;
  });
  document.getElementById('seg-cards').innerHTML = cardsHtml;

  renderTable('seguimiento', 'seguimiento-table', 'seguimiento-pag');
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

// ─── INIT ────────────────────────────────────────────────────────────────────
loadSection('dashboard');
</script>
</body>
</html>"""


@app.route('/')
def index():
    return render_template_string(HTML)


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5050))
    print(f"Panel NIOVAL → http://localhost:{port}")
    app.run(host='0.0.0.0', port=port, debug=False)
