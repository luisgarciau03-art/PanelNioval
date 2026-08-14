"""Verificación E2E ligera del formulario vía el test client de Flask (T2.5).

Ejercita los 3 endpoints reales del formulario con `get_gs_client` mockeado (sin
tocar Google Sheets ni levantar navegador). El recorrido Playwright con
screenshots de 3 rutas requiere el entorno del owner (credenciales
GOOGLE_CREDENTIALS_JSON + hoja de staging) — ver PROGRESO del Plan 2.
"""
from unittest.mock import MagicMock

import pytest

import app


@pytest.fixture
def client():
    app.app.config["TESTING"] = True
    return app.app.test_client()


def _fake_client(worksheet):
    c = MagicMock()
    sp = MagicMock()
    c.open_by_key.return_value = sp
    sp.worksheet.return_value = worksheet
    return c


def test_formulario_html_se_sirve(client):
    r = client.get("/formulario")
    assert r.status_code == 200
    assert b"Formulario de Llamadas" in r.data


def test_siguiente_devuelve_contacto(client, monkeypatch):
    ws = MagicMock()
    ws.get_all_values.return_value = [
        ["TIENDA", "TEL", "CIUDAD", "X", "Y", "RESPUESTA"],
        ["Tienda B", "556", "GDL", "", "", ""],
    ]
    monkeypatch.setattr(app, "get_gs_client", lambda: _fake_client(ws))
    r = client.get("/api/formulario/siguiente?skip=0")
    assert r.status_code == 200
    data = r.get_json()
    assert data["fin"] is False
    assert data["contacto"]["TIENDA"] == "Tienda B"


def test_siguiente_sin_pendientes_devuelve_fin(client, monkeypatch):
    ws = MagicMock()
    ws.get_all_values.return_value = [
        ["TIENDA", "TEL", "CIUDAD", "X", "Y", "RESPUESTA"],
        ["Tienda A", "555", "CDMX", "", "", "Llamado"],
    ]
    monkeypatch.setattr(app, "get_gs_client", lambda: _fake_client(ws))
    r = client.get("/api/formulario/siguiente?skip=0")
    assert r.get_json() == {"fin": True}


def test_guardar_ruta_revisara_catalogo(client, monkeypatch):
    # Ruta feliz APROBADO → Revisará el Catálogo (contrato Plan 3).
    ws = MagicMock()
    ws.col_values.return_value = ["TIENDA", "f2"]  # ultima_fila = 3
    ws.title = "Respuestas de formulario 1"
    monkeypatch.setattr(app, "get_gs_client", lambda: _fake_client(ws))
    # row=999 (distinto de ultima_fila=3) para probar que el backend IGNORA el row del payload.
    payload = {
        "tienda": "Ferretería A", "resultado": "APROBADO", "r0": "Respondio",
        "r1": "op1", "r7": "Revisara el Catalogo", "row": 999, "col_respuesta": 6,
    }
    r = client.post("/api/formulario/guardar", json=payload)
    assert r.status_code == 200
    assert r.get_json() == {"ok": True}
    # Verifica que se escribió J = 'Revisara el Catalogo' (lo que lee envio_catalogo.py)
    updates = ws.batch_update.call_args[0][0]
    rv = {u["range"]: u["values"][0][0] for u in updates}
    assert rv["J3"] == "Revisara el Catalogo"   # fila 3 (calculada), NO 999 del payload
    assert rv["S3"] == "APROBADO"
    assert "J999" not in rv                       # BUG conocido FH3: el row del payload se ignora

    # BUG conocido FC1: guardar NO marca el contacto en LISTA DE CONTACTOS (no update_cell).
    ws.update_cell.assert_not_called()


def test_guardar_payload_invalido_devuelve_ok_false(client, monkeypatch):
    # BUG conocido FM6: error → 200 con {ok:false} (no 400/500).
    def _boom():
        raise Exception("sheets caído")
    monkeypatch.setattr(app, "get_gs_client", _boom)
    r = client.post("/api/formulario/guardar", json={"tienda": "X"})
    assert r.status_code == 200
    assert r.get_json()["ok"] is False
