"""Metricas de la superficie de Ventas. Logica pura, sin Flask.

Se saca de `app.py` por dos motivos, y el segundo pesa mas que el primero:

1. El archivo lleva tres cambios seguidos pegado a su tope de 3,800 lineas, y cada
   uno ha exigido extraer algo solo para poder aterrizar.
2. Estas metricas tienen 23 tests y ninguna dependencia de Flask. Probar una funcion
   que recibe filas y devuelve un dict es mas barato que levantar un cliente HTTP, y
   la ruta se queda en dos lineas que no esconden nada.
"""
from collections import defaultdict

from nucleo_catalogo import MESES_CORTOS, parsear_fecha, parsear_monto


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
