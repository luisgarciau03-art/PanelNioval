"""Que rutas puede alcanzar alguien SIN token, y que devuelven las de depuracion.

Salio de un barrido: de las 42 rutas del panel, **13 no se mencionan en ninguna
prueba**. Tres de ellas son endpoints de depuracion que vuelcan filas crudas de las
hojas -- `/api/debug`, `/api/debug/respuestas` y `/api/test/<key>`, esta ultima las
primeras filas de CUALQUIER hoja, incluida `contactos`, con nombres y telefonos.

Hoy estan detras del token y eso esta bien. Lo que no habia era nada que lo
vigilara: `_ENDPOINTS_EXENTOS_AUTH` es **el unico sitio del panel donde un descuido
convierte datos de clientes en datos publicos**, y nadie lo estaba mirando.

Estas pruebas no cambian comportamiento. Fijan el que hay, en el punto donde
equivocarse es caro.
"""
import pytest

import app


# Las dos exenciones DOCUMENTADAS, con su motivo en el codigo:
#   - `catalogo_heartbeat`: el worker usa su propio WORKER_TOKEN.
#   - `salud`: el healthcheck de Docker, que no tiene el token del panel.
EXENTAS_LEGITIMAS = {"catalogo_heartbeat", "salud"}


@pytest.fixture
def cliente_con_auth(monkeypatch):
    """Un panel con la autenticacion ACTIVA, que es como corre en el VPS.

    La suite entera corre con `PANEL_AUTH_DESACTIVADA=1` (lo pone `conftest`), asi
    que sin esto cualquier prueba de auth pasaria sin ejercitar el gate.
    """
    monkeypatch.delenv("PANEL_AUTH_DESACTIVADA", raising=False)
    monkeypatch.setattr(app, "PANEL_DASHBOARD_TOKEN", "token-de-prueba", raising=False)
    app.app.config["TESTING"] = True
    return app.app.test_client()


class TestLaListaDeExencionesNoCRECE_SOLA:

    def test_solo_estan_las_dos_documentadas(self):
        assert set(app._ENDPOINTS_EXENTOS_AUTH) == EXENTAS_LEGITIMAS, (
            "alguien anadio una ruta sin token. Cada entrada de esta lista es una "
            "puerta abierta a internet: exige motivo escrito en el codigo")


class TestLasRutasDeDEPURACION_NO_SE_ABREN:
    """Vuelcan filas crudas de las hojas. Si alguna dejara de pedir token, seria
    una fuga de datos de clientes, no una molestia."""

    @pytest.mark.parametrize("ruta", [
        "/api/debug",
        "/api/debug/respuestas",
        "/api/test/contactos",
        "/api/test/ventas",
    ])
    def test_sin_token_responden_401(self, cliente_con_auth, ruta):
        r = cliente_con_auth.get(ruta)

        assert r.status_code == 401, (
            f"{ruta} respondio {r.status_code} sin token: vuelca filas de la hoja")


class TestNingunaRUTA_NUEVA_SE_CUELA_SIN_TOKEN:
    """La comprobacion de conjunto: recorre TODAS las rutas registradas.

    Un test por ruta conocida envejece mal -- la que se añada mañana no estaria. Esta
    recorre el mapa de Flask, asi que cubre tambien lo que no existe todavia.
    """

    def test_toda_ruta_GET_sin_parametros_pide_token(self, cliente_con_auth):
        abiertas = []
        for regla in app.app.url_map.iter_rules():
            if "GET" not in (regla.methods or set()) or regla.arguments:
                continue
            if regla.endpoint in EXENTAS_LEGITIMAS or regla.endpoint == "static":
                continue
            r = cliente_con_auth.get(regla.rule)
            if r.status_code != 401:
                abiertas.append((regla.rule, r.status_code))

        assert abiertas == [], f"rutas alcanzables sin token: {abiertas}"

    def test_y_el_healthcheck_SIGUE_abierto(self, cliente_con_auth):
        """La otra direccion: si `/salud` empezara a pedir token, el contenedor se
        quedaria `unhealthy` y Docker lo reiniciaria en bucle."""
        assert cliente_con_auth.get("/salud").status_code == 200
