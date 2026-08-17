"""Tests de la operación Railway (Plan 5): auth opcional del panel (M1) + heartbeat."""
import importlib
from unittest.mock import MagicMock

import pytest

import app


@pytest.fixture
def client():
    app.app.config["TESTING"] = True
    return app.app.test_client()


# ─────────────────────── Auth del panel: fail-closed ───────────────────────
class TestAuthPanel:
    @pytest.fixture(autouse=True)
    def _sin_escape_hatch(self, monkeypatch):
        """Estos tests ejercitan el gate real, no el bypass de la suite."""
        monkeypatch.delenv("PANEL_AUTH_DESACTIVADA", raising=False)

    def test_sin_token_env_cierra(self, client, monkeypatch):
        monkeypatch.delenv("PANEL_DASHBOARD_TOKEN", raising=False)
        r = client.get("/api/catalogo/worker-estado")
        assert r.status_code == 401  # fail-closed: sin token no abre

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

    def test_escape_hatch_abre_solo_si_es_explicito(self, client, monkeypatch):
        monkeypatch.delenv("PANEL_DASHBOARD_TOKEN", raising=False)
        monkeypatch.setenv("PANEL_AUTH_DESACTIVADA", "1")
        r = client.get("/api/catalogo/worker-estado")
        assert r.status_code == 200


# ─────────────────────── Sección "Envíos Catálogo" en el dashboard ───────────────────────
class TestSeccionCatalogo:
    def test_dashboard_incluye_seccion_catalogo(self, client):
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
        monkeypatch.delenv("PANEL_AUTH_DESACTIVADA", raising=False)
        monkeypatch.delenv("PANEL_DASHBOARD_TOKEN", raising=False)
        monkeypatch.setenv("WORKER_TOKEN", "w-secreto")
        r = client.post("/api/catalogo/heartbeat", json={})
        assert r.status_code == 401
        r2 = client.post("/api/catalogo/heartbeat", json={}, headers={"X-Worker-Token": "w-secreto"})
        assert r2.status_code == 200

    def test_sin_worker_token_cierra(self, client, monkeypatch):
        """Sin WORKER_TOKEN el heartbeat NO acepta escrituras anonimas."""
        monkeypatch.delenv("PANEL_AUTH_DESACTIVADA", raising=False)
        monkeypatch.delenv("WORKER_TOKEN", raising=False)
        r = client.post("/api/catalogo/heartbeat", json={"resumen": {"enviados": 1}})
        assert r.status_code == 401

    def test_estado_refleja_heartbeat(self, client, monkeypatch):
        monkeypatch.setenv("WORKER_TOKEN", "w-secreto")
        client.post("/api/catalogo/heartbeat",
                    json={"resumen": {"enviados": 2, "fallos": 0}},
                    headers={"X-Worker-Token": "w-secreto"})
        r = client.get("/api/catalogo/worker-estado")
        d = r.get_json()
        assert d["vivo"] is True
        assert d["resumen"] == {"enviados": 2, "fallos": 0}


# ─────────────────────── Guardas de arranque ───────────────────────
class TestGuardasArranque:
    """La app se niega a arrancar sin secretos. Un despliegue mal
    configurado revienta ruidosamente en vez de abrir el panel en silencio."""

    @pytest.fixture(autouse=True)
    def _restaurar_modulo_app(self, monkeypatch):
        """Un test que espera RuntimeError deja `app` a medio recargar: la
        guarda de arranque corta la ejecución del módulo antes de que se
        registren las rutas. Recargar aquí con un entorno válido tras cada
        test evita que ese estado a medias se filtre a los tests que corran
        después (incluidos los de otras clases/archivos)."""
        yield
        monkeypatch.setenv("PANEL_DASHBOARD_TOKEN", "t" * 32)
        monkeypatch.setenv("SECRET_KEY", "k" * 32)
        monkeypatch.delenv("PANEL_AUTH_DESACTIVADA", raising=False)
        importlib.reload(app)

    def test_sin_token_no_arranca(self, monkeypatch):
        monkeypatch.delenv("PANEL_AUTH_DESACTIVADA", raising=False)
        monkeypatch.delenv("PANEL_DASHBOARD_TOKEN", raising=False)
        monkeypatch.setenv("SECRET_KEY", "k" * 32)
        with pytest.raises(RuntimeError, match="PANEL_DASHBOARD_TOKEN"):
            importlib.reload(app)

    def test_sin_secret_key_no_arranca(self, monkeypatch):
        monkeypatch.delenv("PANEL_AUTH_DESACTIVADA", raising=False)
        monkeypatch.setenv("PANEL_DASHBOARD_TOKEN", "t" * 32)
        monkeypatch.delenv("SECRET_KEY", raising=False)
        with pytest.raises(RuntimeError, match="SECRET_KEY"):
            importlib.reload(app)

    def test_con_escape_hatch_arranca(self, monkeypatch):
        monkeypatch.setenv("PANEL_AUTH_DESACTIVADA", "1")
        monkeypatch.delenv("PANEL_DASHBOARD_TOKEN", raising=False)
        monkeypatch.delenv("SECRET_KEY", raising=False)
        importlib.reload(app)  # no lanza
        assert app.app is not None

    def test_con_secretos_arranca(self, monkeypatch):
        monkeypatch.delenv("PANEL_AUTH_DESACTIVADA", raising=False)
        monkeypatch.setenv("PANEL_DASHBOARD_TOKEN", "t" * 32)
        monkeypatch.setenv("SECRET_KEY", "k" * 32)
        importlib.reload(app)  # no lanza
        assert app.app is not None
