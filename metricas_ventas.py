"""Metricas de la superficie de Ventas. Logica pura, sin Flask.

Se saca de `app.py` por dos motivos, y el segundo pesa mas que el primero:

1. El archivo lleva tres cambios seguidos pegado a su tope de 3,800 lineas, y cada
   uno ha exigido extraer algo solo para poder aterrizar.
2. Estas metricas tienen 23 tests y ninguna dependencia de Flask. Probar una funcion
   que recibe filas y devuelve un dict es mas barato que levantar un cliente HTTP, y
   la ruta se queda en dos lineas que no esconden nada.
"""
from collections import defaultdict

from nucleo_catalogo import (MESES_CORTOS, MESES_LARGOS, parsear_fecha,
                             parsear_monto, str_val)

from collections import Counter


def resumen_dashboard(ventas: list[dict]) -> dict:
    """Metricas de ventas por mes, con desglose por esquema y top clientes.

    Vive fuera de `app.py` porque no necesita Flask: recibe las filas y devuelve el
    diccionario. La ruta queda como envoltorio de dos lineas.

    Lo que este modulo hace explicito, y que costo encontrarlo mirando produccion:
    **se dice cuantas filas NO entraron y por que**. Sin `ventas_sin_fecha`, el
    tablero mostraba 0 con 185 ventas cargadas, indistinguible de "no se vendio".
    """

    ilegibles = {'n': 0}

    def parse_monto(v):
        monto, ok = parsear_monto(v)
        if not ok:
            ilegibles['n'] += 1
        return monto


    meses: dict = defaultdict(lambda: {
        'monto': 0.0, 'pedidos': 0,
        'clientes': set(), 'esquemas': defaultdict(float),
    })

    total_general = 0.0
    total_pedidos = 0
    sin_fecha = 0
    sin_cliente = 0

    for row in ventas:
        cliente = str(row.get('Cliente', '')).strip()
        fecha   = parsear_fecha(row.get('Fecha', ''))
        esquema = str(row.get('ESQUEMA', '')).strip() or 'Sin esquema'
        # `factura` se asigna y no se lee: cruft que ya venia de `app.py`. Se
        # conserva a proposito -- esta extraccion se vende como IDENTICA, y
        # limpiar de paso haria imposible afirmarlo. Toca en un commit aparte.
        factura = str(row.get('Num Factura', '')).strip()

        if not fecha:
            # La hoja real NO tiene columna `Fecha`: tiene `MES` con el nombre del
            # mes en español y sin año. Estas filas se descartaban en silencio y el
            # tablero mostraba 0 en todo con 183 ventas cargadas. Agrupar por `MES`
            # es decision de producto -- sin año, mezclar ejercicios seria inventar
            # --, pero DECIR cuantas no se pudieron ubicar en el tiempo no lo es.
            sin_fecha += 1
            continue
        if not cliente:
            # Mismo patron, otra columna: sin contador, un total mas bajo que la
            # hoja no se distingue de "se vendio menos".
            sin_cliente += 1
            continue
        # El monto se lee AQUI, no antes: contarlo como ilegible en una fila que ya
        # se descarto mezcla dos explicaciones del mismo cero en un solo numero.
        monto = parse_monto(row.get('Monto', 0))

        clave = fecha.strftime('%Y-%m')   # para ordenar
        label = f'{MESES_CORTOS[fecha.month]} {fecha.year}'   # para mostrar, en español

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

    return {
        'por_mes':        resultado,
        'total_general':  round(total_general, 2),
        'total_pedidos':  total_pedidos,
        'promedio_mes':   round(total_general / len(resultado), 2) if resultado else 0,
        'mejor_mes':      mejor_mes.get('mes', '—'),
        'mejor_mes_monto': mejor_mes.get('monto', 0),
        # Cuantos montos no se pudieron leer. Sin este numero, una grafica baja se
        # lee como "se vendio poco" en vez de "no se pudo leer" -- y `parse_monto`
        # devuelve 0.0 en ese caso, asi que la diferencia es invisible.
        'montos_ilegibles': ilegibles['n'],
        # Ventas que existen en la hoja pero no se pudieron ubicar en el tiempo.
        # Un cero en la grafica con este numero alto significa "no pude leer las
        # fechas", no "no se vendio".
        'ventas_sin_fecha': sin_fecha,
        'ventas_sin_cliente': sin_cliente,
    }


def estadisticas(ventas: list[dict]) -> dict:
    """Resumen heuristico de la hoja de ventas: totales, top y serie mensual.

    ⚠️ **Detecta las columnas por substring** del encabezado, no por un esquema
    fijo. Es fragil a proposito -- la hoja la capturan personas -- y por eso
    publica `columna_monto` y `columna_fecha`: si eligio mal, se ve.
    """
    if not ventas:
        # La forma no cambia con los datos: un cliente que lea `montos_ilegibles`
        # sin comprobar su existencia no puede llevarse un `undefined` aqui.
        return {'total_ventas': 0, 'clientes': 0, 'por_mes': [],
                        'top_clientes': [], 'columnas': [],
                        'montos_ilegibles': None, 'columna_monto': None,
                'columna_fecha': None}

    claves = list(ventas[0].keys()) if ventas else []

    # Detectar columnas relevantes heurísticamente
    col_cliente = next((k for k in claves if 'cliente' in k.lower() or 'tienda' in k.lower() or 'nombre' in k.lower()), None)
    col_monto = next((k for k in claves if 'monto' in k.lower() or 'total' in k.lower() or 'venta' in k.lower() or 'importe' in k.lower()), None)
    col_fecha = next((k for k in claves if 'fecha' in k.lower() or 'date' in k.lower()), None)

    clientes = Counter()
    # La clave es (año, mes) y NO la etiqueta: ordenar por la cadena '%b %Y' es
    # ordenar alfabeticamente — 'Dec' antes que 'Feb' antes que 'Jan' — y el
    # recorte a 12 tiraba el mes mas reciente conservando uno viejo.
    por_mes: dict[tuple[int, int], float] = defaultdict(float)
    montos_ilegibles = 0

    for v in ventas:
        if col_cliente:
            cli = str_val(v.get(col_cliente, '')).title()
            if cli:
                clientes[cli] += 1
        if col_fecha:
            dt = parsear_fecha(str_val(v.get(col_fecha, '')))
            if dt:
                monto = None
                if col_monto:
                    crudo = str_val(v.get(col_monto, '')).replace(',', '').replace('$', '')
                    try:
                        monto = float(crudo)
                    except ValueError:
                        monto = None
                if monto is None:
                    # Antes sumaba 1. Un peso inventado convierte la serie de dinero
                    # en un conteo a medias, en la misma grafica y sin decirlo.
                    #
                    # Y solo cuenta si la columna EXISTE: sin columna de monto, todas
                    # las filas caerian aqui y el numero se leeria como "mil ventas
                    # corruptas" cuando es "no se cual es la columna del dinero".
                    if col_monto:
                        montos_ilegibles += 1
                else:
                    por_mes[(dt.year, dt.month)] += monto
                # Se toca la clave aunque el monto no se pueda leer: el mes existio.
                por_mes.setdefault((dt.year, dt.month), 0.0)

    return {
        'total_ventas': len(ventas),
        'clientes': len(clientes),
        'columnas': claves,
        'top_clientes': clientes.most_common(10),
        # Los 12 meses MAS RECIENTES, en orden cronologico, con la etiqueta en
        # español: `%b` da 'Dec'/'Jan' en el locale C, y el panel esta en español.
        'por_mes': [{'mes': f'{MESES_CORTOS[m]} {a}', 'total': por_mes[(a, m)]}
                    for a, m in sorted(por_mes)[-12:]],
        # Cuantas ventas cayeron en un mes pero no pudieron sumar dinero. Sin esto,
        # una grafica baja se lee como "se vendio poco" en vez de "no se pudo leer".
        # `None` = no se pudo evaluar (no hay columna de monto). Es distinto de 0.
        'montos_ilegibles': montos_ilegibles if col_monto else None,
        'columna_monto': col_monto,
        'columna_fecha': col_fecha,
    }


def clientes_frecuentes(ventas: list[dict]) -> list[dict]:
    """Agrupa ventas por cliente: suma montos, cuenta pedidos, ordena mayor a menor."""

    def parse_monto(v):
        return parsear_monto(v)[0]

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


    def fecha_a_mes(f):
        dt = parsear_fecha(f)
        return f"{MESES_LARGOS[dt.month]} {dt.year}" if dt else f

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
    return result
