"""Tests de los endpoints de la cola de catálogo (Plan 3) vía Flask test client."""
from unittest.mock import MagicMock

import pytest

import app
import nucleo_catalogo as nc


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


# ─────────────────────── encolar ───────────────────────
class TestEncolar:
    def test_conclusion_elegible_encola_pendiente(self, client, monkeypatch):
        ws = MagicMock()
        ws.get_all_values.return_value = [nc.COLUMNAS_ENVIOS]  # sin filas → no existe
        monkeypatch.setattr(app, "get_gs_client", lambda: _fake_client(ws))
        r = client.post("/api/catalogo/encolar", json={
            "tienda": "Ferretería A", "telefono": "5512345678",
            "referencia": 7, "conclusion": "Revisara el Catalogo",
        })
        assert r.status_code == 200
        d = r.get_json()
        assert d["ok"] is True and d["estado"] == "PENDIENTE" and d["numero_valido"] is True
        ws.append_row.assert_called_once()

    def test_numero_invalido_marca_numero_valido_false(self, client, monkeypatch):
        ws = MagicMock()
        ws.get_all_values.return_value = [nc.COLUMNAS_ENVIOS]
        monkeypatch.setattr(app, "get_gs_client", lambda: _fake_client(ws))
        r = client.post("/api/catalogo/encolar", json={
            "tienda": "A", "telefono": "123", "referencia": 4, "conclusion": "Pedido",
        })
        d = r.get_json()
        assert d["ok"] is True and d["numero_valido"] is False  # se encola, worker lo dejará NUMERO_INVALIDO

    def test_pedido_tambien_encola(self, client, monkeypatch):
        # Decisión owner T3.1: 'Pedido' también dispara catálogo.
        ws = MagicMock()
        ws.get_all_values.return_value = [nc.COLUMNAS_ENVIOS]
        monkeypatch.setattr(app, "get_gs_client", lambda: _fake_client(ws))
        r = client.post("/api/catalogo/encolar", json={
            "tienda": "X", "telefono": "5512345678", "referencia": 3, "conclusion": "Pedido",
        })
        assert r.get_json()["estado"] == "PENDIENTE"

    def test_conclusion_no_elegible_no_encola(self, client, monkeypatch):
        monkeypatch.setattr(app, "get_gs_client", lambda: _fake_client(MagicMock()))
        r = client.post("/api/catalogo/encolar", json={
            "tienda": "X", "telefono": "5512345678", "referencia": 3, "conclusion": "Correo",
        })
        assert r.get_json() == {"ok": False, "motivo": "conclusion_no_elegible"}

    def test_idempotencia_no_duplica(self, client, monkeypatch):
        ws = MagicMock()
        fila = ["ts", "A", "+5512345678", "7", "Pedido", "PENDIENTE", "0", "ts", ""]
        ws.get_all_values.return_value = [nc.COLUMNAS_ENVIOS, fila]
        monkeypatch.setattr(app, "get_gs_client", lambda: _fake_client(ws))
        r = client.post("/api/catalogo/encolar", json={
            "tienda": "A", "telefono": "5512345678", "referencia": 7, "conclusion": "Pedido",
        })
        d = r.get_json()
        assert d["ok"] is True and d["estado"] == "ya_encolado"
        ws.append_row.assert_not_called()

    def test_falta_tienda_o_referencia_400(self, client, monkeypatch):
        monkeypatch.setattr(app, "get_gs_client", lambda: _fake_client(MagicMock()))
        r = client.post("/api/catalogo/encolar", json={"telefono": "5512345678", "conclusion": "Pedido"})
        assert r.status_code == 400


# ─────────────────────── listar ───────────────────────
class TestEnvios:
    def _ws(self):
        ws = MagicMock()
        ws.get_all_values.return_value = [
            nc.COLUMNAS_ENVIOS,
            ["ts", "A", "+55", "7", "Pedido", "NUMERO_INVALIDO", "1", "ts", "popup"],
            ["ts", "B", "+55", "9", "Revisara el Catalogo", "ENVIADO", "1", "ts", ""],
        ]
        return ws

    def test_lista_todos(self, client, monkeypatch):
        monkeypatch.setattr(app, "get_gs_client", lambda: _fake_client(self._ws()))
        r = client.get("/api/catalogo/envios")
        envios = r.get_json()["envios"]
        assert len(envios) == 2
        assert envios[0]["_row"] == 2

    def test_filtra_por_estado(self, client, monkeypatch):
        monkeypatch.setattr(app, "get_gs_client", lambda: _fake_client(self._ws()))
        r = client.get("/api/catalogo/envios?estado=NUMERO_INVALIDO")
        envios = r.get_json()["envios"]
        assert len(envios) == 1
        assert envios[0]["tienda"] == "A"


# ─────────────────────── corregir número ───────────────────────
def _ws_con_envio(estado, intentos="1"):
    """Worksheet mock con un envío en la fila 2 con el estado dado."""
    ws = MagicMock()
    fila = ["ts", "A", "+5500000000", "7", "Pedido", estado, intentos, "ts", ""]
    ws.get_all_values.return_value = [nc.COLUMNAS_ENVIOS, fila]
    ws.row_values.return_value = nc.COLUMNAS_ENVIOS
    return ws


class TestCorregirNumero:
    def test_numero_valido_reencola(self, client, monkeypatch):
        ws = _ws_con_envio(nc.NUMERO_INVALIDO)
        monkeypatch.setattr(app, "get_gs_client", lambda: _fake_client(ws))
        r = client.post("/api/catalogo/corregir-numero", json={
            "envio_row": 2, "telefono": "5599998888",
        })
        assert r.status_code == 200
        assert r.get_json() == {"ok": True, "estado": "PENDIENTE"}
        ws.batch_update.assert_called_once()

    def test_desde_enviado_rechaza_fsm(self, client, monkeypatch):
        # CRITICAL fix: no se puede corregir/re-encolar un envío ya ENVIADO.
        ws = _ws_con_envio(nc.ENVIADO)
        monkeypatch.setattr(app, "get_gs_client", lambda: _fake_client(ws))
        r = client.post("/api/catalogo/corregir-numero", json={"envio_row": 2, "telefono": "5599998888"})
        assert r.status_code == 400
        ws.batch_update.assert_not_called()

    def test_envio_row_fuera_de_rango_400(self, client, monkeypatch):
        # Fix seguridad: envio_row=1 (encabezado) o > filas → rechazo, no corrompe.
        ws = _ws_con_envio(nc.FALLO)
        monkeypatch.setattr(app, "get_gs_client", lambda: _fake_client(ws))
        r = client.post("/api/catalogo/corregir-numero", json={"envio_row": 1, "telefono": "5599998888"})
        assert r.status_code == 400
        ws.batch_update.assert_not_called()

    def test_numero_invalido_400_sin_escritura(self, client, monkeypatch):
        ws = MagicMock()
        monkeypatch.setattr(app, "get_gs_client", lambda: _fake_client(ws))
        r = client.post("/api/catalogo/corregir-numero", json={"envio_row": 2, "telefono": "123"})
        assert r.status_code == 400
        ws.batch_update.assert_not_called()

    def test_falta_envio_row_400(self, client, monkeypatch):
        monkeypatch.setattr(app, "get_gs_client", lambda: _fake_client(MagicMock()))
        r = client.post("/api/catalogo/corregir-numero", json={"telefono": "5599998888"})
        assert r.status_code == 400


# ─────────────────────── reintentar ───────────────────────
class TestReintentar:
    def test_desde_fallo_reencola(self, client, monkeypatch):
        ws = _ws_con_envio(nc.FALLO)
        monkeypatch.setattr(app, "get_gs_client", lambda: _fake_client(ws))
        r = client.post("/api/catalogo/reintentar", json={"envio_row": 2})
        assert r.get_json() == {"ok": True, "estado": "PENDIENTE"}

    def test_desde_enviado_rechaza(self, client, monkeypatch):
        ws = _ws_con_envio(nc.ENVIADO)  # terminal
        monkeypatch.setattr(app, "get_gs_client", lambda: _fake_client(ws))
        r = client.post("/api/catalogo/reintentar", json={"envio_row": 2})
        assert r.status_code == 400
