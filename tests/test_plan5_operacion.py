"""Tests de la operación Railway (Plan 5): auth opcional del panel (M1) + heartbeat."""
import importlib
from unittest.mock import MagicMock

import pytest

import app


@pytest.fixture
def client():
    app.app.config["TESTING"] = True
    return app.app.test_client()


# ─────────────────────── Auth opcional del panel (M1) ───────────────────────
class TestAuthPanel:
    def test_sin_token_env_todo_abierto(self, client, monkeypatch):
        monkeypatch.delenv("PANEL_DASHBOARD_TOKEN", raising=False)
        r = client.get("/api/catalogo/worker-estado")
        assert r.status_code == 200  # comportamiento actual: abierto

    def test_con_token_env_sin_header_401(self, client, monkeypatch):
        monkeypatch.setenv("PANEL_DASHBOARD_TOKEN", "secreto123")
        r = client.get("/api/catalogo/worker-estado")
        assert r.status_code == 401

    def test_con_token_en_header_pasa(self, client, monkeypatch):
        monkeypatch.setenv("PANEL_DASHBOARD_TOKEN", "secreto123")
        r = client.get("/api/catalogo/worker-estado", headers={"X-Dashboard-Token": "secreto123"})
        assert r.status_code == 200

    def test_con_token_en_query_pasa(self, client, monkeypatch):
        monkeypatch.setenv("PANEL_DASHBOARD_TOKEN", "secreto123")
        r = client.get("/api/catalogo/worker-estado?token=secreto123")
        assert r.status_code == 200

    def test_heartbeat_exento_de_auth_dashboard(self, client, monkeypatch):
        # El heartbeat no usa PANEL_DASHBOARD_TOKEN (el worker usa WORKER_TOKEN aparte).
        monkeypatch.setenv("PANEL_DASHBOARD_TOKEN", "secreto123")
        monkeypatch.delenv("WORKER_TOKEN", raising=False)
        r = client.post("/api/catalogo/heartbeat", json={"resumen": {"enviados": 1}})
        assert r.status_code == 200


# ─────────────────────── Sección "Envíos Catálogo" en el dashboard ───────────────────────
class TestSeccionCatalogo:
    def test_dashboard_incluye_seccion_catalogo(self, client, monkeypatch):
        monkeypatch.delenv("PANEL_DASHBOARD_TOKEN", raising=False)
        r = client.get("/")
        assert r.status_code == 200
        html = r.data.decode("utf-8", "ignore")
        # Sección, nav, badge y funciones JS presentes.
        assert 'id="sec-catalogo"' in html
        assert "showSection('catalogo')" in html
        assert 'id="cat-badge"' in html
        assert "function loadCatalogo" in html
        assert "catGuardarCorreccion" in html


# ─────────────────────── Heartbeat del worker ───────────────────────
class TestHeartbeat:
    def test_worker_token_requerido_si_definido(self, client, monkeypatch):
        monkeypatch.delenv("PANEL_DASHBOARD_TOKEN", raising=False)
        monkeypatch.setenv("WORKER_TOKEN", "w-secreto")
        r = client.post("/api/catalogo/heartbeat", json={})
        assert r.status_code == 401
        r2 = client.post("/api/catalogo/heartbeat", json={}, headers={"X-Worker-Token": "w-secreto"})
        assert r2.status_code == 200

    def test_estado_refleja_heartbeat(self, client, monkeypatch):
        monkeypatch.delenv("PANEL_DASHBOARD_TOKEN", raising=False)
        monkeypatch.delenv("WORKER_TOKEN", raising=False)
        client.post("/api/catalogo/heartbeat", json={"resumen": {"enviados": 2, "fallos": 0}})
        r = client.get("/api/catalogo/worker-estado")
        d = r.get_json()
        assert d["vivo"] is True
        assert d["resumen"] == {"enviados": 2, "fallos": 0}
