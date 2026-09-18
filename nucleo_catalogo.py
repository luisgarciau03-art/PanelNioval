"""Lógica pura de la cola de envíos de catálogo (transport-agnostic).

No importa selenium ni gspread: solo reglas de negocio testeables. Lo consumen
tanto el panel Flask (encolar/consultar/corregir) como el worker de envío
(`envio_catalogo.py`). El transporte real (WhatsApp Web / worker local — decisión
owner Plan 5 = B) se inyecta aparte, de modo que Plan 5 solo cambie el "enviador".

Contrato de la worksheet `ENVIOS_CATALOGO` (en el spreadsheet de respuestas):
columnas = COLUMNAS_ENVIOS (ver abajo). Idempotencia por `fila_respuesta`.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

# ─── Conclusiones elegibles (col J de 'Respuestas de formulario 1') ───
# Decisión owner 2026-08-13 (Plan 3 T3.1): "Pedido" Y "Revisará el Catálogo"
# disparan envío de catálogo (== comportamiento actual de envio_catalogo.py).
CONCLUSIONES_ELEGIBLES = {"pedido", "revisara el catalogo"}

# ─── Estados de la cola ───
PENDIENTE = "PENDIENTE"
EN_PROCESO = "EN_PROCESO"
ENVIADO = "ENVIADO"
NUMERO_INVALIDO = "NUMERO_INVALIDO"
FALLO = "FALLO"

ESTADOS_FINALES = {ENVIADO, NUMERO_INVALIDO, FALLO}
ESTADOS_REINTENTABLES = {NUMERO_INVALIDO, FALLO}

# Transiciones válidas de la máquina de estados.
TRANSICIONES = {
    PENDIENTE: {EN_PROCESO},
    EN_PROCESO: {ENVIADO, NUMERO_INVALIDO, FALLO},
    NUMERO_INVALIDO: {PENDIENTE},   # re-encolar tras corregir número
    FALLO: {PENDIENTE},             # reintentar
    ENVIADO: set(),                 # estado terminal
}

# Encabezados (orden fijo) de la worksheet ENVIOS_CATALOGO.
COLUMNAS_ENVIOS = [
    "fecha_solicitud", "tienda", "telefono", "fila_respuesta",
    "conclusion", "estado", "intentos", "timestamp_estado", "detalle",
]

FMT_TIMESTAMP = "%d/%m/%Y %H:%M:%S"
_FMT_TS = FMT_TIMESTAMP  # alias interno (compatibilidad)

# ─────────────────────────── Reloj del proyecto ───────────────────────────
# Plan 5 · T5.3 (M2). El contenedor corre en UTC y Mexico es UTC-6, asi que un
# reloj sin zona guardaba TODO lo capturado despues de las 18:00 con la fecha
# del dia siguiente, y la semana ISO de la grafica "Contactos por Semana" con
# ella.
#
# El helper vive AQUI y no en app.py porque la hoja ENVIOS_CATALOGO recibe
# timestamps de dos procesos distintos: el panel escribe `fecha_solicitud`
# desde el contenedor y el worker escribe `timestamp_estado` desde la PC del
# owner. Con dos relojes, una fila podia mostrar el cambio de estado seis horas
# ANTES de la solicitud que lo origino. Este modulo es el unico que los dos
# importan.
#
# Son dos capas: esta y `ENV TZ` en el Dockerfile. Solo la variable dejaria el
# resultado dependiendo del despliegue (Windows local vs runner UTC); solo el
# codigo dejaria los logs y el `date` del contenedor en UTC.
TZ_MEXICO = ZoneInfo("America/Mexico_City")


def ahora_mexico() -> datetime:
    """Instante actual en hora de Mexico, con `tzinfo` explicito.

    Fuente de "ahora" de todo lo que corre EN EL CONTENEDOR: `app.py`,
    `nucleo_catalogo` y `worker_catalogo`. No usar `datetime.now()` a secas ahi:
    hay un guarda en `tests/test_endurecimiento_zona_horaria.py` que falla si
    reaparece.

    NO es la unica fuente de "ahora" del repo, y decirlo seria falso:
    `envio_catalogo.py` conserva tres `datetime.now()` desnudos y escribe en la
    MISMA hoja ('Respuestas de formulario 1'). Hoy no es un bug porque ese
    script corre en la PC del owner, donde el reloj ya esta en hora de Mexico.
    Se vuelve un bug el dia que se elija el transporte "C = Selenium headless"
    para WhatsApp, porque entonces correria en un contenedor UTC. Queda como
    deuda anotada y con tripwire en el test, atada a esa decision del owner.
    """
    return datetime.now(TZ_MEXICO)


def columnas_indexadas(headers: Optional[list] = None) -> dict:
    """Mapa {nombre_columna: índice 1-based}. Si se pasan `headers` reales de la
    hoja, se usan (robusto ante reordenamientos); si no, usa COLUMNAS_ENVIOS."""
    base = headers if headers else COLUMNAS_ENVIOS
    return {str(h).strip(): i + 1 for i, h in enumerate(base)}


def headers_validos(headers: list) -> bool:
    """True si los headers reales coinciden con el contrato COLUMNAS_ENVIOS."""
    return [str(h).strip() for h in (headers or [])] == COLUMNAS_ENVIOS


def conclusion_elegible(col_j: str) -> bool:
    """True si la conclusión (col J) debe disparar envío de catálogo."""
    return (col_j or "").strip().lower() in CONCLUSIONES_ELEGIBLES


LADA_MX = "52"


def normalizar_telefono(tel: str) -> str:
    """Deja solo digitos, antepone la lada de pais y el '+'. '' si no hay digitos.

    WhatsApp exige el numero internacional completo: envio_catalogo.py construye
    la URL como `send?phone={telefono sin '+'}`, asi que un '+5551234567' llega
    como phone=5551234567 y WhatsApp no puede resolverlo.

    'LISTA DE CONTACTOS' guarda el numero nacional de 10 digitos ('555 123 4567'),
    asi que sin este paso todo lo que salga de la hoja pierde la lada. Antes no se
    notaba porque el frontend leia una columna inexistente y mandaba vacio: la cola
    lo marcaba NUMERO_INVALIDO y el operador tecleaba el numero completo a mano.

    El '1' de 521 es el prefijo de movil que Mexico dejo de usar en 2019; se retira
    para no acabar con 13 digitos que WhatsApp rechaza.
    """
    digitos = re.sub(r"\D", "", tel or "")
    if not digitos:
        return ""
    if len(digitos) == 10:
        digitos = LADA_MX + digitos
    elif len(digitos) == 13 and digitos.startswith(LADA_MX + "1"):
        digitos = LADA_MX + digitos[3:]
    return f"+{digitos}"


# Nombres posibles de la columna del telefono en 'LISTA DE CONTACTOS'.
# La real es CONTACTO (columna E). El codigo buscaba 'TELEFONO'/'TELÉFONO', que
# nunca existieron en esa hoja: el importador escribe el telefono en la quinta
# posicion, y esa columna se titula CONTACTO. Las otras dos quedan como respaldo
# por si alguna hoja hermana si las usa.
COLUMNAS_TELEFONO_CONTACTOS = ("CONTACTO", "TELÉFONO", "TELEFONO")


def formatear_telefono_contactos(tel: str) -> str:
    """Formatea al convenio de 'LISTA DE CONTACTOS': 10 digitos en grupos 3-3-4.

    Medido sobre la hoja: 6787 de 7054 telefonos tienen 10 digitos y el formato
    dominante es 'NNN NNN NNNN'. Escribir '+525551234567' ahi seria legible por
    maquina pero ajeno al resto de la columna, y el operador compara a ojo.

    Los prefijos de pais se retiran porque la hoja guarda el numero nacional:
    52 + 10 digitos, o 521 + 10 digitos (el '1' de movil que Mexico ya no usa).
    Lo que no encaje en 10 digitos se devuelve solo con digitos, sin inventar
    una agrupacion que podria estar mal.
    """
    digitos = re.sub(r"\D", "", tel or "")
    if len(digitos) == 13 and digitos.startswith("521"):
        digitos = digitos[3:]
    elif len(digitos) == 12 and digitos.startswith("52"):
        digitos = digitos[2:]
    if len(digitos) == 10:
        return f"{digitos[:3]} {digitos[3:6]} {digitos[6:]}"
    return digitos


def validar_numero(tel: str) -> bool:
    """Valida un teléfono E.164-aproximado: 10 a 13 dígitos (con o sin '+')."""
    digitos = re.sub(r"\D", "", tel or "")
    return 10 <= len(digitos) <= 13


def transicion_valida(desde: str, hacia: str) -> bool:
    """True si la transición de estado está permitida."""
    return hacia in TRANSICIONES.get(desde, set())


def nueva_fila_envio(
    tienda: str, telefono: str, fila_respuesta: int, conclusion: str,
    ahora: Optional[datetime] = None,
) -> list:
    """Construye la fila (en orden COLUMNAS_ENVIOS) para un envío PENDIENTE."""
    ts = (ahora or ahora_mexico()).strftime(_FMT_TS)
    return [
        ts,                     # fecha_solicitud
        tienda,                 # tienda
        normalizar_telefono(telefono),  # telefono
        str(fila_respuesta),    # fila_respuesta (clave de idempotencia)
        conclusion,             # conclusion
        PENDIENTE,              # estado
        "0",                    # intentos
        ts,                     # timestamp_estado
        "",                     # detalle
    ]


def indice_por_fila_respuesta(filas: list, fila_respuesta: int) -> Optional[int]:
    """Busca en `filas` (get_all_values de ENVIOS_CATALOGO, incluye encabezado)
    el índice 1-based de la fila cuya col `fila_respuesta` coincide. None si no está.

    Idempotencia: encolar la misma `fila_respuesta` dos veces NO debe duplicar.
    """
    col = COLUMNAS_ENVIOS.index("fila_respuesta")
    objetivo = str(fila_respuesta).strip()
    for i, fila in enumerate(filas[1:], start=2):
        if len(fila) > col and str(fila[col]).strip() == objetivo:
            return i
    return None


MESES_LARGOS = ('', 'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
                'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre')

MESES_CORTOS = ('', 'Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun',
                'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic')


def parsear_fecha(valor):
    """La fecha de una celda, o `None` si no se puede leer. Pura, sin Flask.

    Estaba escrita dos veces en `app.py` con el mismo repertorio de formatos y
    ordenes distintos. ⚠️ El orden importa y no es inocuo: `03/04/2026` casa con
    `%d/%m/%Y` primero, asi que una hoja capturada en formato americano asignaria
    meses equivocados **sin ningun aviso**. Se conserva el orden que ya usaba el
    tablero; cambiarlo exige saber como se captura la hoja de verdad.
    """
    from datetime import datetime
    crudo = str(valor).strip()[:10]
    for fmt in ('%d/%m/%Y', '%m/%d/%Y', '%Y-%m-%d'):
        try:
            return datetime.strptime(crudo, fmt)
        except ValueError:
            continue
    return None


def parsear_monto(valor) -> tuple[float, bool]:
    """Devuelve `(monto, se_pudo_leer)`. Una celda vacia NO es ilegible.

    Estaba duplicada en dos rutas de `app.py` con comportamientos distintos, y el
    propio repo lo tenia anotado como deuda. Al unificarla se gana lo que faltaba:
    **decir si se pudo leer**. Devolver 0.0 a secas hace que "no vendio" y "no pude
    leerlo" sean el mismo numero en la misma grafica.
    """
    crudo = str(valor).replace(',', '').replace('$', '').strip()
    if not crudo:
        return 0.0, True
    try:
        return float(crudo), True
    except ValueError:
        return 0.0, False


def sanear_etiqueta_ciudad(valor: str) -> str:
    """Enmascara lo que no es un nombre de ciudad antes de publicarlo.

    La columna CIUDAD de la hoja a veces trae un telefono o un correo tecleado por
    error. Esos valores caian en `sin_clasificar` y salian **verbatim** por
    `/api/importador/ciudades` y por `/api/prospectos/ciudades`, que prometen que
    ningun telefono ni nombre de contacto sale de ahi. Medido en produccion el
    2026-09-16: 8 telefonos y 1 correo de 32 entradas.

    Enmascarar NO es borrar, y esa es la mitad que importa: el aviso existe para que
    el operador ARREGLE esas celdas, asi que se conservan los ultimos digitos para
    poder encontrarlas. Un saneador que enmascare de mas esconde el problema.

    Tres decisiones que salieron de la revision de seguridad, y que no son obvias:

    1. **Basta una arroba.** Exigir un punto detras dejaba pasar `juan@gmail`, que
       es un dominio truncado al teclear y sigue siendo un nombre de contacto.
    2. **Solo los ultimos 4 digitos**, como `nucleo_catalogo.enmascarar_telefono`.
       Dos funciones del mismo repo con el mismo proposito no pueden dar garantias
       distintas, y la lada no hacia falta para localizar la fila.
    3. **Una RACHA contigua de digitos, no la suma de los dispersos.** Sumarlos
       enmascaraba direcciones legitimas como "Manzana 3 Lote 25 CP 31125", y perder
       de vista una celda arreglable es el fallo contrario al que esto evita.
    """
    crudo = (valor or '').strip()
    if re.search(r'\S@\S', crudo):
        return '…@… (correo en la columna CIUDAD)'
    # Una racha de 8+ digitos admitiendo solo separadores de telefono entre medias.
    racha = re.search(r'\d[\d\s().+-]{6,}\d', crudo)
    if racha and len(re.sub(r'\D', '', racha.group())) >= 8:
        digitos = re.sub(r'\D', '', racha.group())
        return f'…{digitos[-4:]} (teléfono en la columna CIUDAD)'
    return crudo


def enmascarar_telefono(tel: str) -> str:
    """Enmascara para logs: deja solo los últimos 4 dígitos. Dato personal."""
    digitos = re.sub(r"\D", "", tel or "")
    if len(digitos) <= 4:
        return "****"
    return f"+{'*' * (len(digitos) - 4)}{digitos[-4:]}"
