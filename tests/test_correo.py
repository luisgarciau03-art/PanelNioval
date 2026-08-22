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


class TestActualizarTelefono:
    def _ws(self, nfilas=10):
        """Encabezados REALES de 'LISTA DE CONTACTOS', comprobados en la hoja.

        La version anterior de este test simulaba ["TIENDA", "TELÉFONO", "CIUDAD"],
        un layout que no existe: la columna del telefono es CONTACTO, la E. El
        test pasaba contra esa ficcion mientras produccion devolvia 400
        'columna TELÉFONO no encontrada'.
        """
        ws = MagicMock()
        header = ["  ", "TIENDA", "CIUDAD", "CATEGORIA ", "CONTACTO", "RESPUESTA"]
        ws.get_all_values.return_value = [header] + [["1", "x", "y", "z", "111", ""]] * (nfilas - 1)
        return ws

    def test_valido_actualiza_col_telefono(self, client, monkeypatch):
        ws = self._ws(10)
        monkeypatch.setattr(app, "get_gs_client", lambda: _fake_client(ws))
        r = client.post("/api/formulario/telefono", json={"row": 5, "telefono": "5599998888"})
        assert r.status_code == 200 and r.get_json()["ok"] is True
        upd = ws.batch_update.call_args[0][0]
        assert upd[0]["range"] == "E5"                  # CONTACTO = col E, fila 5
        assert upd[0]["values"] == [["559 999 8888"]]   # convenio de la hoja

    def test_respuesta_conserva_el_formato_normalizado(self, client, monkeypatch):
        """La hoja lleva el formato legible; la respuesta de la API sigue
        devolviendo el normalizado, que es el que consume la cola de catalogo."""
        ws = self._ws(10)
        monkeypatch.setattr(app, "get_gs_client", lambda: _fake_client(ws))
        r = client.post("/api/formulario/telefono", json={"row": 5, "telefono": "5599998888"})
        assert r.get_json()["telefono"] == "+5599998888"

    def test_invalido_400_sin_escritura(self, client, monkeypatch):
        ws = self._ws()
        monkeypatch.setattr(app, "get_gs_client", lambda: _fake_client(ws))
        r = client.post("/api/formulario/telefono", json={"row": 5, "telefono": "123"})
        assert r.status_code == 400
        ws.batch_update.assert_not_called()

    def test_row_encabezado_rechazado(self, client, monkeypatch):
        ws = self._ws()
        monkeypatch.setattr(app, "get_gs_client", lambda: _fake_client(ws))
        r = client.post("/api/formulario/telefono", json={"row": 1, "telefono": "5599998888"})
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
