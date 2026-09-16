"""Tests de caracterización del módulo FORMULARIO DE LLAMADAS (`app.py`).

Caracteriza el comportamiento ACTUAL de `guardar_respuesta_formulario` (mapa
col J + rangos de celdas exactos) y `get_contacto_pendiente` (RESPUESTA por
nombre, fallback col F, skip, sin pendientes). Bugs conocidos marcados con
`# BUG conocido:` (ver docs/analisis/2026-08-13-matriz-formulario.md y la
auditoría de Plan 2). NO se corrige comportamiento.

Se mockea `get_gs_client` para no tocar Google Sheets reales.
"""
from unittest.mock import MagicMock

import pytest

import app


def _fake_client(worksheet):
    client = MagicMock()
    sp = MagicMock()
    client.open_by_key.return_value = sp
    sp.worksheet.return_value = worksheet
    return client


def _guardar_captura(monkeypatch, datos, filas_col_b=("TIENDA", "fila2")):
    """Ejecuta guardar_respuesta_formulario con gspread mockeado y devuelve
    (resultado_bool, {rango: valor}, fila)."""
    ws = MagicMock()
    ws.col_values.return_value = list(filas_col_b)  # ultima_fila = len+1
    ws.title = "Respuestas de formulario 1"
    monkeypatch.setattr(app, "get_gs_client", lambda: _fake_client(ws))
    ok = app.guardar_respuesta_formulario(datos)
    updates = ws.batch_update.call_args[0][0]
    rango_valor = {u["range"]: u["values"][0][0] for u in updates}
    fila = len(filas_col_b) + 1
    return ok, rango_valor, fila


# ─────────────────────── Mapa col J (precedencia) ───────────────────────
class TestColJMapping:
    @pytest.mark.parametrize("datos,esperado_j", [
        ({"resultado": "APROBADO", "r0": "Respondio", "r7": "Pedido"}, "Pedido"),
        ({"resultado": "APROBADO", "r0": "Respondio", "r7": "Revisara el Catalogo"}, "Revisara el Catalogo"),
        ({"resultado": "APROBADO", "r0": "Respondio", "r7": "Correo"}, "Correo"),
        ({"resultado": "APROBADO", "r0": "Respondio", "r7": "Nulo"}, "Nulo"),
        ({"resultado": "APROBADO", "r0": "Respondio", "r7": "Colgo"}, "Colgo"),
        ({"resultado": "Enc No Disponible", "r0": "Respondio", "r7": "Enc No Disponible"}, "Enc No Disponible"),
        ({"resultado": "APROBADO", "r0": "Buzon", "r7": ""}, "BUZON"),
        ({"resultado": "APROBADO", "r0": "Telefono Incorrecto", "r7": ""}, "TELEFONO INCORRECTO"),
        ({"resultado": "NEGADO", "r0": "Respondio", "r7": ""}, "No apto"),
        ({"resultado": "NO COMPATIBLE", "r0": "Respondio", "r7": ""}, "No compatible"),
        ({"resultado": "MARCA UNICA", "r0": "Respondio", "r7": ""}, "Marca Unica"),
    ])
    def test_col_j(self, monkeypatch, datos, esperado_j):
        base = {"tienda": "Ferretería A"}
        base.update(datos)
        ok, rv, f = _guardar_captura(monkeypatch, base)
        assert ok is True
        assert rv[f"J{f}"] == esperado_j

    def test_col_j_vacio_no_escribe_columna_j(self, monkeypatch):
        # Sin r7 ni r0 ni resultado especial → col_j '' → J no se escribe.
        ok, rv, f = _guardar_captura(monkeypatch, {"tienda": "X", "resultado": "", "r0": "", "r7": ""})
        assert ok is True
        assert f"J{f}" not in rv

    def test_precedencia_colgo_gana_sobre_resultado(self, monkeypatch):
        # BUG/característica: r7='Colgo' gana aunque resultado sea NEGADO (precedencia por orden).
        ok, rv, f = _guardar_captura(
            monkeypatch, {"tienda": "X", "resultado": "NEGADO", "r0": "Respondio", "r7": "Colgo"}
        )
        assert rv[f"J{f}"] == "Colgo"

    def test_precedencia_buzon_gana_sobre_r7(self, monkeypatch):
        # Conflicto alcanzable vía API directa (sin gating del JS): r0='Buzon' (regla 4)
        # gana sobre r7='Pedido' (regla 9). Caracteriza que el backend no valida exclusividad.
        ok, rv, f = _guardar_captura(
            monkeypatch, {"tienda": "X", "resultado": "APROBADO", "r0": "Buzon", "r7": "Pedido"}
        )
        assert rv[f"J{f}"] == "BUZON"


# ─────────────────────── Rangos de celdas escritos ───────────────────────
class TestCeldasEscritas:
    def test_a_b_s_siempre_presentes_y_t_desde_r0(self, monkeypatch):
        ok, rv, f = _guardar_captura(
            monkeypatch,
            {"tienda": "Ferretería A", "resultado": "APROBADO", "r0": "Respondio", "r7": "Pedido"},
        )
        assert rv[f"B{f}"] == "Ferretería A"
        assert rv[f"S{f}"] == "APROBADO"      # S siempre
        assert rv[f"T{f}"] == "Respondio"     # T = r0
        assert f"A{f}" in rv                   # fecha_hora

    def test_preguntas_r1_r6_van_a_C_E_G_I(self, monkeypatch):
        datos = {
            "tienda": "X", "resultado": "APROBADO", "r0": "Respondio", "r7": "Pedido",
            "r1": "op1", "r2": "op2", "r3": "op3", "r4": "op4", "r5": "op5", "r6": "op6",
        }
        ok, rv, f = _guardar_captura(monkeypatch, datos)
        assert rv[f"C{f}"] == "op1"
        assert rv[f"D{f}"] == "op2"
        assert rv[f"E{f}"] == "op3"
        assert rv[f"G{f}"] == "op4"
        assert rv[f"H{f}"] == "op5"
        assert rv[f"I{f}"] == "op6"
        assert f"F{f}" not in rv              # F nunca se escribe

    def test_r0_vacio_no_escribe_T(self, monkeypatch):
        ok, rv, f = _guardar_captura(
            monkeypatch, {"tienda": "X", "resultado": "APROBADO", "r0": "", "r7": "Pedido"}
        )
        assert f"T{f}" not in rv

    def test_ultima_fila_desde_columna_b(self, monkeypatch):
        # 3 valores en col B → escribe en fila 4.
        ok, rv, f = _guardar_captura(
            monkeypatch, {"tienda": "X", "resultado": "APROBADO", "r0": "Respondio", "r7": "Pedido"},
            filas_col_b=("TIENDA", "f2", "f3"),
        )
        assert f == 4
        assert "B4" in rv


# ─────────────────────── get_contacto_pendiente ───────────────────────
class TestGetContactoPendiente:
    def _ws(self, rows):
        ws = MagicMock()
        ws.get_all_values.return_value = rows
        return ws

    def test_respuesta_por_nombre_devuelve_primer_pendiente(self, monkeypatch):
        rows = [
            ["TIENDA", "TELÉFONO", "CIUDAD", "X", "Y", "RESPUESTA"],
            ["Tienda A", "555", "CDMX", "", "", "Llamado"],   # tiene RESPUESTA → salta
            ["Tienda B", "556", "GDL", "", "", ""],            # pendiente
        ]
        monkeypatch.setattr(app, "get_gs_client", lambda: _fake_client(self._ws(rows)))
        c = app.get_contacto_pendiente(0)
        assert c["TIENDA"] == "Tienda B"
        assert c["_row"] == 3
        assert c["_col_respuesta"] == 6  # idx 5 + 1

    def test_fallback_columna_f_cuando_no_hay_header_respuesta(self, monkeypatch):
        rows = [
            ["TIENDA", "TEL", "CIUDAD", "X", "Y", "COL_F"],   # sin 'RESPUESTA' → idx 5 (col F)
            ["Tienda A", "555", "CDMX", "", "", ""],           # col F vacía → pendiente
        ]
        monkeypatch.setattr(app, "get_gs_client", lambda: _fake_client(self._ws(rows)))
        c = app.get_contacto_pendiente(0)
        assert c["TIENDA"] == "Tienda A"
        assert c["_col_respuesta"] == 6

    def test_skip_avanza_al_siguiente_pendiente(self, monkeypatch):
        rows = [
            ["TIENDA", "TEL", "CIUDAD", "X", "Y", "RESPUESTA"],
            ["Tienda A", "555", "CDMX", "", "", ""],
            ["Tienda B", "556", "GDL", "", "", ""],
        ]
        monkeypatch.setattr(app, "get_gs_client", lambda: _fake_client(self._ws(rows)))
        c = app.get_contacto_pendiente(1)
        assert c["TIENDA"] == "Tienda B"
        assert c["_row"] == 3

    def test_sin_pendientes_devuelve_none(self, monkeypatch):
        rows = [
            ["TIENDA", "TEL", "CIUDAD", "X", "Y", "RESPUESTA"],
            ["Tienda A", "555", "CDMX", "", "", "Llamado"],
        ]
        monkeypatch.setattr(app, "get_gs_client", lambda: _fake_client(self._ws(rows)))
        assert app.get_contacto_pendiente(0) is None

    def test_un_error_de_sheets_ya_no_se_confunde_con_sin_pendientes(self, monkeypatch):
        # Era el hallazgo 3 de la auditoría del Plan 2: la excepción de la API se
        # tragaba y devolvía None, igual que "no hay pendientes", así que el
        # endpoint respondía {'fin': True} y el formulario remataba con la
        # pantalla de confeti. Corregido en el Plan 4, T4.5: ahora se relanza y
        # el endpoint responde 503. La cobertura del contrato completo está en
        # tests/test_plan4_estados.py.
        ws = MagicMock()
        ws.get_all_values.side_effect = Exception("429 RESOURCE_EXHAUSTED")
        monkeypatch.setattr(app, "get_gs_client", lambda: _fake_client(ws))
        with pytest.raises(Exception, match="RESOURCE_EXHAUSTED"):
            app.get_contacto_pendiente(0)
