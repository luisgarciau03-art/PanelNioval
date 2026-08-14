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


def normalizar_telefono(tel: str) -> str:
    """Deja solo dígitos y antepone '+'. '' si no hay dígitos."""
    digitos = re.sub(r"\D", "", tel or "")
    return f"+{digitos}" if digitos else ""


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
    ts = (ahora or datetime.now()).strftime(_FMT_TS)
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


def enmascarar_telefono(tel: str) -> str:
    """Enmascara para logs: deja solo los últimos 4 dígitos. Dato personal."""
    digitos = re.sub(r"\D", "", tel or "")
    if len(digitos) <= 4:
        return "****"
    return f"+{'*' * (len(digitos) - 4)}{digitos[-4:]}"
