"""Tests del endpoint de captura de correo (Plan 4) → columna T de LISTA DE CONTACTOS."""
from unittest.mock import MagicMock

import pytest

import app


@pytest.fixture
def client():
    app.app.config["TESTING"] = True
    return app.app.test_client()


def _fake_client(ws):
    c = MagicMock()
    sp = MagicMock()
    c.open_by_key.return_value = sp
    sp.worksheet.return_value = ws
    return c


def _ws_contactos(nfilas=10):
    """Worksheet mock con `nfilas` filas de datos (para la cota superior de row)."""
    ws = MagicMock()
    ws.get_all_values.return_value = [["h"]] * nfilas  # header + filas
    return ws


class TestGuardarCorreo:
    def test_correo_valido_escribe_col_T(self, client, monkeypatch):
        ws = _ws_contactos(10)
        monkeypatch.setattr(app, "get_gs_client", lambda: _fake_client(ws))
        r = client.post("/api/formulario/correo", json={"row": 5, "correo": "cliente@ferreteria.com"})
        assert r.status_code == 200
        assert r.get_json() == {"ok": True}
        # Debe escribir en T5 (columna 20) con RAW.
        args, kwargs = ws.batch_update.call_args
        updates = args[0]
        assert updates[0]["range"] == "T5"
        assert updates[0]["values"] == [["cliente@ferreteria.com"]]
        assert kwargs.get("value_input_option") == "RAW"

    @pytest.mark.parametrize("correo", [
        "sin-arroba",
        "sin@dominio",
        "espacio @dominio.com",
        "@dominio.com",
        "cliente@.com",
        "",
        "x" * 250 + "@d.com",          # > 254 chars
        "<img src=x onerror=alert(1)>@a.b",  # XSS: metacaracteres HTML rechazados por la regex estricta
        "=HYPERLINK@evil.com",         # formula-injection: '=' no está en el allowlist
        'a"b@x.com',                   # comilla doble
    ])
    def test_correo_invalido_400_sin_escritura(self, client, monkeypatch, correo):
        ws = _ws_contactos(10)
        monkeypatch.setattr(app, "get_gs_client", lambda: _fake_client(ws))
        r = client.post("/api/formulario/correo", json={"row": 5, "correo": correo})
        assert r.status_code == 400
        ws.batch_update.assert_not_called()

    def test_falta_row_400(self, client, monkeypatch):
        monkeypatch.setattr(app, "get_gs_client", lambda: _fake_client(_ws_contactos()))
        r = client.post("/api/formulario/correo", json={"correo": "cliente@x.com"})
        assert r.status_code == 400

    def test_row_encabezado_rechazado(self, client, monkeypatch):
        ws = _ws_contactos(10)
        monkeypatch.setattr(app, "get_gs_client", lambda: _fake_client(ws))
        r = client.post("/api/formulario/correo", json={"row": 1, "correo": "cliente@x.com"})
        assert r.status_code == 400
        ws.batch_update.assert_not_called()

    def test_row_fuera_de_rango_superior_rechazado(self, client, monkeypatch):
        # Fix seguridad (MEDIUM): row > nº de filas reales → 400, no escribe.
        ws = _ws_contactos(6)  # header + 5 → total 6
        monkeypatch.setattr(app, "get_gs_client", lambda: _fake_client(ws))
        r = client.post("/api/formulario/correo", json={"row": 99, "correo": "cliente@x.com"})
        assert r.status_code == 400
        ws.batch_update.assert_not_called()


class TestSanitizarCorreo:
    @pytest.mark.parametrize("entrada,esperado", [
        ("cliente@x.com", "cliente@x.com"),
        ("=cmd@x.com", "'=cmd@x.com"),
        ("+x@x.com", "'+x@x.com"),
        ("-x@x.com", "'-x@x.com"),
        ("@x.com", "'@x.com"),
        ("  cliente@x.com  ", "cliente@x.com"),
    ])
    def test_sanitiza(self, entrada, esperado):
        assert app._sanitizar_correo(entrada) == esperado
