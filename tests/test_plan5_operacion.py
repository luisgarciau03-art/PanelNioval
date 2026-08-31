"""Tests de la operación Railway (Plan 5): auth opcional del panel (M1) + heartbeat."""
import importlib
import json
import os
import time
from unittest.mock import patch

import pytest

import app
import nucleo_catalogo as nc
from conftest import servir_superficie


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

    def test_escape_hatch_typo_no_abre(self, client, monkeypatch):
        """PANEL_AUTH_DESACTIVADA=true (typo plausible del operador) NO es
        el valor exacto "1": debe seguir cerrando el panel."""
        monkeypatch.delenv("PANEL_DASHBOARD_TOKEN", raising=False)
        monkeypatch.setenv("PANEL_AUTH_DESACTIVADA", "true")
        r = client.get("/api/catalogo/worker-estado")
        assert r.status_code == 401


# ─────────────────────── Sección "Envíos Catálogo" en el dashboard ───────────────────────
class TestSeccionCatalogo:
    def test_dashboard_incluye_seccion_catalogo(self, client):
        r = client.get("/")
        assert r.status_code == 200
        html = servir_superficie(client, "/", "dashboard")
        # Sección, nav, badge y funciones JS presentes.
        assert 'id="sec-catalogo"' in html
        assert "showSection('catalogo')" in html
        assert 'id="cat-badge"' in html
        assert "function loadCatalogo" in html
        assert "catGuardarCorreccion" in html


# ─────────────────────── Heartbeat del worker ───────────────────────
class TestHeartbeat:
    def test_worker_token_requerido_siempre(self, client, monkeypatch):
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


# ─────────────────────── Ruta de credenciales de Google ───────────────────────
class TestRutaCredenciales:
    """La ruta del archivo de credenciales sale de GOOGLE_CREDENTIALS_FILE.

    Sin esto, el contenedor monta la credencial en /app/credentials.json y el
    codigo busca el nombre hardcodeado: Sheets y Drive revientan en la primera
    llamada.
    """

    DEFECTO = 'bubbly-subject-412101-c969f4a975c5.json'

    @pytest.fixture(autouse=True)
    def _sin_cache_ni_json(self, monkeypatch):
        # GOOGLE_CREDENTIALS_JSON tiene prioridad sobre el archivo: si esta
        # definida, la rama que probamos no se ejecuta.
        monkeypatch.delenv("GOOGLE_CREDENTIALS_JSON", raising=False)
        monkeypatch.setattr(app, "_gs_client", None)
        monkeypatch.setattr(app, "_drive_service", None)

    def test_gs_client_usa_la_env_var(self, monkeypatch):
        monkeypatch.setenv("GOOGLE_CREDENTIALS_FILE", "/app/credentials.json")
        with patch("app.Credentials.from_service_account_file") as mock_creds, \
             patch("app.gspread.authorize"):
            app.get_gs_client()
        assert mock_creds.call_args[0][0] == "/app/credentials.json"

    def test_gs_client_sin_env_var_usa_el_default(self, monkeypatch):
        monkeypatch.delenv("GOOGLE_CREDENTIALS_FILE", raising=False)
        with patch("app.Credentials.from_service_account_file") as mock_creds, \
             patch("app.gspread.authorize"):
            app.get_gs_client()
        assert mock_creds.call_args[0][0] == self.DEFECTO

    def test_drive_service_usa_la_env_var(self, monkeypatch):
        monkeypatch.setenv("GOOGLE_CREDENTIALS_FILE", "/app/credentials.json")
        with patch("app.Credentials.from_service_account_file") as mock_creds, \
             patch("app.build"):
            app.get_drive_service()
        assert mock_creds.call_args[0][0] == "/app/credentials.json"

    def test_drive_service_sin_env_var_usa_el_default(self, monkeypatch):
        monkeypatch.delenv("GOOGLE_CREDENTIALS_FILE", raising=False)
        with patch("app.Credentials.from_service_account_file") as mock_creds, \
             patch("app.build"):
            app.get_drive_service()
        assert mock_creds.call_args[0][0] == self.DEFECTO


# ─────────────── Heartbeat compartido entre procesos de gunicorn ───────────────
class TestHeartbeatCompartido:
    """El latido no puede vivir en memoria del proceso.

    El panel corre con `gunicorn --workers 2`: el POST del worker cae en un
    proceso y la consulta puede caer en el otro. Medido en el VPS, diez
    consultas seguidas alternaban entre dos timestamps distintos. Al parar el
    worker, un proceso cruzaria el TTL antes que el otro y el panel diria
    "muerto"/"vivo" segun quien contestara.
    """

    @pytest.fixture(autouse=True)
    def _archivo_aislado(self, monkeypatch, tmp_path):
        monkeypatch.setattr(app, "WORKER_HEARTBEAT_FILE", str(tmp_path / "hb.json"))

    def test_estado_lee_del_archivo_no_de_memoria(self, client, monkeypatch):
        """El test que falla si alguien revierte a la variable en memoria.

        Se guarda un latido por la ruta y despues se reescribe el archivo por
        fuera, simulando a OTRO proceso de gunicorn. La consulta debe reflejar
        el archivo; si leyera de memoria devolveria el resumen anterior.
        """
        client.post("/api/catalogo/heartbeat", json={"resumen": {"origen": "proceso-A"}})

        with open(app.WORKER_HEARTBEAT_FILE, "w", encoding="utf-8") as fh:
            json.dump({"ts": time.time(), "resumen": {"origen": "proceso-B"}}, fh)

        d = client.get("/api/catalogo/worker-estado").get_json()
        assert d["vivo"] is True
        assert d["resumen"] == {"origen": "proceso-B"}

    def test_sin_archivo_reporta_muerto(self, client):
        """Un proceso recien arrancado no debe inventarse un latido."""
        assert not os.path.exists(app.WORKER_HEARTBEAT_FILE)
        d = client.get("/api/catalogo/worker-estado").get_json()
        assert d["vivo"] is False
        assert d["ultimo_heartbeat"] is None

    def test_archivo_corrupto_reporta_muerto(self, client):
        """Un JSON a medias no debe tumbar la ruta ni dar un vivo falso."""
        with open(app.WORKER_HEARTBEAT_FILE, "w", encoding="utf-8") as fh:
            fh.write('{"ts": 123')  # truncado a proposito

        d = client.get("/api/catalogo/worker-estado").get_json()
        assert d["vivo"] is False
        assert d["ultimo_heartbeat"] is None

    def test_ts_no_numerico_reporta_muerto(self, client):
        """JSON valido pero con basura en ts: no debe reventar comparando."""
        with open(app.WORKER_HEARTBEAT_FILE, "w", encoding="utf-8") as fh:
            json.dump({"ts": "ayer", "resumen": {}}, fh)

        d = client.get("/api/catalogo/worker-estado").get_json()
        assert d["vivo"] is False

    def test_latido_viejo_reporta_muerto(self, client):
        """Pasado el TTL el worker se reporta caido aunque haya archivo."""
        viejo = time.time() - app.WORKER_HEARTBEAT_TTL - 1
        with open(app.WORKER_HEARTBEAT_FILE, "w", encoding="utf-8") as fh:
            json.dump({"ts": viejo, "resumen": {"x": 1}}, fh)

        d = client.get("/api/catalogo/worker-estado").get_json()
        assert d["vivo"] is False
        assert d["ultimo_heartbeat"] == viejo

    def test_escritura_no_deja_temporales(self, client, tmp_path):
        """La escritura atomica renombra: no debe quedar ningun .tmp."""
        client.post("/api/catalogo/heartbeat", json={"resumen": {"n": 1}})
        assert list(tmp_path.glob("*.tmp")) == []
        assert os.path.exists(app.WORKER_HEARTBEAT_FILE)


# ─────────────── Inyeccion de formula en el importador ───────────────
class TestEscapeFormula:
    """Sheets parsea lo que empieza por = + - @ cuando se escribe con
    USER_ENTERED. La ferreteria "+ Mas Seguro Distribuidora Ferretera" se
    guardo asi: el texto quedo intacto por debajo, pero la celda muestra
    #ERROR! y el operador ve un error en vez del nombre al llamarla.
    """

    @pytest.mark.parametrize("entrada", [
        "+ Mas Seguro Distribuidora Ferretera",   # el caso real, fila 6807
        "=SUMA(A1:A9)",
        "-Ferreteria del Norte",
        "@arroba SA de CV",
    ])
    def test_escapa_lo_que_sheets_tomaria_por_formula(self, entrada):
        r = app._escapar_formula(entrada)
        assert r == "'" + entrada
        assert r[1:] == entrada  # el texto original se conserva entero

    @pytest.mark.parametrize("entrada", [
        "Ferreteria Chavez",
        "3M Mexico",
        "",
        "Tornillos & Co",
    ])
    def test_no_toca_texto_normal(self, entrada):
        assert app._escapar_formula(entrada) == entrada

    @pytest.mark.parametrize("entrada", [19.4326, -99.1332, 0, 4, 8, 3.5])
    def test_no_toca_numeros(self, entrada):
        """Latitud, longitud, calificacion y resenas deben seguir siendo
        numeros: convertirlos a texto es justo lo que RAW habria roto."""
        r = app._escapar_formula(entrada)
        assert r == entrada
        assert isinstance(r, type(entrada))

    def test_longitud_negativa_sigue_siendo_numero(self):
        """Una longitud como -99.13 empieza por '-' pero NO es cadena: no se toca."""
        assert app._escapar_formula(-99.1332) == -99.1332

    def test_fecha_como_texto_no_se_escapa(self):
        """La fecha entra como texto y debe seguir parseandose como fecha."""
        assert app._escapar_formula("18/08/2026") == "18/08/2026"


# ─────────────── Columna del telefono en LISTA DE CONTACTOS ───────────────
class TestColumnaTelefonoContactos:
    """La columna se llama CONTACTO (la E), no TELEFONO.

    Buscar 'TELÉFONO'/'TELEFONO' devolvia 400 'columna TELÉFONO no encontrada'
    al corregir un numero, y dejaba el telefono en blanco en el formulario.
    Encabezados reales de la hoja, comprobados: A='  ', B='TIENDA', C='CIUDAD',
    D='CATEGORIA ', E='CONTACTO'.
    """

    ENCABEZADOS_REALES = ['  ', 'TIENDA', 'CIUDAD', 'CATEGORIA ', 'CONTACTO',
                          'RESPUESTA', 'PORCENTAJES ', 'Domicilio']

    def test_encuentra_contacto_en_la_columna_e(self):
        assert app._columna_telefono_contactos(self.ENCABEZADOS_REALES) == 5

    def test_acepta_telefono_como_respaldo(self):
        """Si una hoja hermana si usa 'TELÉFONO', se sigue soportando."""
        assert app._columna_telefono_contactos(['TIENDA', 'TELÉFONO']) == 2
        assert app._columna_telefono_contactos(['TIENDA', 'TELEFONO']) == 2

    def test_ignora_mayusculas_y_espacios(self):
        assert app._columna_telefono_contactos(['x', ' contacto ']) == 2

    def test_devuelve_none_si_no_esta(self):
        assert app._columna_telefono_contactos(['TIENDA', 'CIUDAD']) is None
        assert app._columna_telefono_contactos([]) is None


class TestFormatoTelefonoContactos:
    """La hoja guarda el numero nacional con espacios: 6787 de 7054 telefonos
    tienen 10 digitos y el formato dominante es 'NNN NNN NNNN'. Escribir
    '+525551234567' seria ajeno al resto de la columna."""

    @pytest.mark.parametrize("entrada", [
        "525551234567",        # el caso que fallo, con lada de pais
        "5551234567",          # nacional pelado
        "+52 555 123 4567",    # ya formateado con prefijo
        "5215551234567",       # con el '1' de movil que Mexico ya no usa
        "555-123-4567",        # con guiones
        "(555) 123 4567",      # con parentesis
    ])
    def test_normaliza_al_formato_de_la_hoja(self, entrada):
        assert nc.formatear_telefono_contactos(entrada) == "555 123 4567"

    def test_no_inventa_agrupacion_si_no_son_10_digitos(self):
        """Agrupar a ciegas un numero raro escribiria algo falso en produccion."""
        assert nc.formatear_telefono_contactos("12345") == "12345"
        assert nc.formatear_telefono_contactos("") == ""
        assert nc.formatear_telefono_contactos(None) == ""

    def test_no_confunde_un_nacional_que_empieza_por_52(self):
        """5212345678 son 10 digitos: es nacional, no lada 52 + 8 digitos."""
        assert nc.formatear_telefono_contactos("5212345678") == "521 234 5678"
