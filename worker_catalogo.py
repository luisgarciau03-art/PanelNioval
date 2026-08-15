"""Worker de la cola de envío de catálogo (transport-agnostic).

Lee la worksheet `ENVIOS_CATALOGO`, procesa los `PENDIENTE` y escribe el estado
final (`ENVIADO`/`NUMERO_INVALIDO`/`FALLO`). El **transporte** (cómo se envía por
WhatsApp) se inyecta: decisión owner Plan 5 = B (worker local con Selenium/WA Web,
`transporte_whatsapp_web`). La lógica de selección y decisión de estado es pura y
testeable con un transporte FAKE — los `except` del script original NO sobreviven:
aquí toda excepción de transporte se convierte en estado `FALLO` con detalle.
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Callable, Optional

import nucleo_catalogo as nc


class ResultadoEnvio:
    """Resultado honesto de un intento de envío por el transporte."""

    def __init__(self, estado: str, detalle: str = ""):
        if estado not in (nc.ENVIADO, nc.NUMERO_INVALIDO, nc.FALLO):
            raise ValueError(f"estado inválido: {estado!r}")
        self.estado = estado
        self.detalle = detalle

    def __repr__(self):  # pragma: no cover
        return f"ResultadoEnvio({self.estado!r}, {self.detalle!r})"


# Firma del transporte: (telefono, mensajes, archivos) -> ResultadoEnvio
Transporte = Callable[[str, list, list], ResultadoEnvio]


def autorizar_envio() -> tuple:
    """Gate de seguridad: el worker NO envía nada sin autorización explícita.

    Requiere DOS variables de entorno que el owner define en su PC (robusto tanto en
    corrida manual como en Tarea Programada; sin prompts frágiles de consola):
      - `WA_ENVIO_PASSWORD`: contraseña de envío (no vacía).
      - `WA_ENVIO_ARMADO=1`: armado explícito para autorizar el envío.

    Así se evita cualquier envío accidental: mientras no estén AMBAS, no se envía.
    Devuelve (autorizado: bool, motivo: str).
    """
    passw = (os.environ.get("WA_ENVIO_PASSWORD") or "").strip()
    if not passw:
        return False, "envío deshabilitado: falta WA_ENVIO_PASSWORD"
    if (os.environ.get("WA_ENVIO_ARMADO") or "").strip() != "1":
        return False, "envío NO armado: define WA_ENVIO_ARMADO=1 para autorizar"
    return True, "autorizado (WA_ENVIO_PASSWORD definida + WA_ENVIO_ARMADO=1)"


def seleccionar_pendientes(filas: list) -> list:
    """Devuelve los registros (dict + `_row`) en estado PENDIENTE.
    `filas` = get_all_values() de ENVIOS_CATALOGO (incluye encabezado)."""
    if not filas:
        return []
    headers = filas[0]
    col = {h: i for i, h in enumerate(headers)}
    if "estado" not in col:
        return []
    ie = col["estado"]
    pendientes = []
    for i, fila in enumerate(filas[1:], start=2):
        estado = fila[ie] if len(fila) > ie else ""
        if str(estado).strip().upper() == nc.PENDIENTE:
            reg = {h: (fila[col[h]] if col[h] < len(fila) else "") for h in headers}
            reg["_row"] = i
            pendientes.append(reg)
    return pendientes


def procesar_envio(
    reg: dict, transporte: Transporte, mensajes: list, archivos: list,
) -> ResultadoEnvio:
    """Decide el estado final de UN registro pendiente. No toca la hoja.

    - Número inválido (validación previa) → NUMERO_INVALIDO sin llamar transporte.
    - Excepción del transporte → FALLO con detalle (NO se traga el error).
    """
    tel = reg.get("telefono", "")
    if not nc.validar_numero(tel):
        return ResultadoEnvio(nc.NUMERO_INVALIDO, "número inválido (validación previa)")
    try:
        res = transporte(tel, mensajes, archivos)
    except Exception as e:
        return ResultadoEnvio(nc.FALLO, f"excepción de transporte: {type(e).__name__}: {e}")
    if not isinstance(res, ResultadoEnvio):
        return ResultadoEnvio(nc.FALLO, "transporte devolvió un resultado inválido")
    return res


def _col_de(ws) -> dict:
    """Mapa nombre→índice 1-based desde los ENCABEZADOS REALES de la hoja."""
    return nc.columnas_indexadas(ws.row_values(1))


def marcar_en_proceso(ws, envio_row: int, col: dict, ahora: Optional[datetime] = None):
    """Lock optimista: marca la fila EN_PROCESO antes de invocar el transporte,
    para que una corrida solapada no la vuelva a tomar (seleccionar_pendientes
    solo toma PENDIENTE)."""
    import gspread.utils as gsu
    ts = (ahora or datetime.now()).strftime(nc.FMT_TIMESTAMP)
    ws.batch_update([
        {"range": gsu.rowcol_to_a1(envio_row, col["estado"]), "values": [[nc.EN_PROCESO]]},
        {"range": gsu.rowcol_to_a1(envio_row, col["timestamp_estado"]), "values": [[ts]]},
    ], value_input_option="RAW")


def aplicar_resultado(ws, envio_row: int, resultado: ResultadoEnvio, col: Optional[dict] = None,
                      ahora: Optional[datetime] = None):
    """Escribe el estado final en la fila de ENVIOS_CATALOGO (impuro: toca gspread).
    Usa los encabezados reales de la hoja si no se pasa `col`."""
    import gspread.utils as gsu
    if col is None:
        col = _col_de(ws)
    ts = (ahora or datetime.now()).strftime(nc.FMT_TIMESTAMP)
    ws.batch_update([
        {"range": gsu.rowcol_to_a1(envio_row, col["estado"]), "values": [[resultado.estado]]},
        {"range": gsu.rowcol_to_a1(envio_row, col["timestamp_estado"]), "values": [[ts]]},
        {"range": gsu.rowcol_to_a1(envio_row, col["detalle"]), "values": [[resultado.detalle[:500]]]},
    ], value_input_option="RAW")


def procesar_cola(ws, transporte: Transporte, mensajes: list, archivos: list,
                  ahora: Optional[datetime] = None) -> dict:
    """Orquesta una corrida: lee pendientes, marca EN_PROCESO (lock), procesa cada
    uno y escribe estado final. Devuelve {enviados, invalidos, fallos, procesados}."""
    filas = ws.get_all_values()
    col = nc.columnas_indexadas(filas[0] if filas else None)
    pendientes = seleccionar_pendientes(filas)
    resumen = {"enviados": 0, "invalidos": 0, "fallos": 0, "procesados": 0}
    for reg in pendientes:
        marcar_en_proceso(ws, reg["_row"], col, ahora=ahora)  # lock antes de enviar
        res = procesar_envio(reg, transporte, mensajes, archivos)
        aplicar_resultado(ws, reg["_row"], res, col=col, ahora=ahora)
        resumen["procesados"] += 1
        if res.estado == nc.ENVIADO:
            resumen["enviados"] += 1
        elif res.estado == nc.NUMERO_INVALIDO:
            resumen["invalidos"] += 1
        else:
            resumen["fallos"] += 1
    return resumen
