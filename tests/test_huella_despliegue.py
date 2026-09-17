"""La guarda que faltaba: detectar que el VPS sirve codigo rancio (Plan 3 - T3.3/T3.4).

El bug de conteo del importador se arreglo el 27 de agosto y el operador lo siguio
sufriendo TRES SEMANAS, porque el arreglo estaba en `main` y produccion seguia
sirviendo `51520f3`. No hay auto-deploy, y `/salud` es mudo a proposito (decision de
seguridad del Plan 5): nadie tenia forma de notar la diferencia.

Los 80 tests del importador vigilan que el conteo sea correcto. Ninguno vigila que
el conteo correcto este DESPLEGADO. Eso es lo que se prueba aqui.

`tools/huella_despliegue.py` fecha el panel por comportamiento: le pregunta a
`/api/importador/estado` por campos que solo existen despues del arreglo. Estos
tests fijan las dos propiedades de las que depende que sirva para algo:

    1. Sabe decir que si Y sabe decir que no.
    2. Sus marcadores son campos que el endpoint devuelve DE VERDAD -- si alguien
       renombra uno, la guarda empieza a mentir y hay que enterarse aqui, no en
       produccion tres semanas despues.
"""
import sys

import pytest

import app
import tools.huella_despliegue as hd
from tools.huella_despliegue import MARCADORES, veredicto  # noqa: E402  (orden intencional: app primero)


# El panel tal como estaba desplegado del 24-ago al 16-sep (commit 51520f3): un
# solo contador, sin `nuevos_en_sheet`. Es lo que el operador tuvo delante.
ESTADO_PREFIX = {
    "status": "idle", "ciudad": "", "categoria": "", "progreso": 0,
    "total": 2, "encontrados": 0, "log": [], "error": "",
}


class TestSabeDecirQueSi:
    """Un barrido que no puede encontrar el positivo que sabe que existe no vale nada."""

    def test_marca_como_rancio_un_panel_anterior_al_arreglo(self):
        v = veredicto(ESTADO_PREFIX)

        assert v.rancio is True

    def test_nombra_que_marcadores_faltan_para_poder_actuar(self):
        """«Esta rancio» sin decir por que obliga a rediagnosticar desde cero."""
        v = veredicto(ESTADO_PREFIX)

        assert "nuevos_en_sheet" in v.faltantes
        assert "duplicados" in v.faltantes


class TestSabeDecirQueNo:
    """Y un barrido que marca todo como roto tampoco: nadie volveria a mirarlo."""

    def test_no_marca_rancio_el_estado_que_el_panel_devuelve_hoy(self, cliente):
        datos = cliente.get("/api/importador/estado").get_json()

        v = veredicto(datos)

        assert v.rancio is False, f"Falsos positivos: {v.faltantes}"

    def test_distingue_el_arreglo_de_lo_posterior_al_arreglo(self, cliente):
        """Que el codigo servido sea ESTRICTAMENTE posterior es mas fuerte que
        «igual o posterior», y la guarda tiene que poder decirlo."""
        datos = cliente.get("/api/importador/estado").get_json()

        assert veredicto(datos).posterior_al_arreglo is True
        assert veredicto(ESTADO_PREFIX).posterior_al_arreglo is False


class TestLosMarcadoresNoSePuedenOxidar:
    """El modo de fallo silencioso de esta guarda: que vigile campos que ya no existen."""

    def test_cada_marcador_es_un_campo_que_el_endpoint_devuelve_de_verdad(self, cliente):
        datos = cliente.get("/api/importador/estado").get_json()

        ausentes = [clave for clave, _, _ in MARCADORES if clave not in datos]

        assert ausentes == [], (
            f"La guarda vigila campos que `/api/importador/estado` ya no devuelve: "
            f"{ausentes}. O se renombraron en app.py y hay que actualizar MARCADORES, "
            f"o la guarda lleva tiempo dando rancio un panel que esta al dia."
        )

    def test_los_marcadores_del_arreglo_son_los_contadores_separados(self):
        """La lista no puede quedarse en un solo campo: el arreglo separo CUATRO
        numeros, y comprobar solo uno haria pasar un despliegue a medias."""
        del_arreglo = {c for c, desde, _ in MARCADORES if desde == "ae0e1c9"}

        assert {"nuevos_en_sheet", "duplicados", "descartados"} <= del_arreglo


@pytest.fixture
def cliente():
    app.app.config["TESTING"] = True
    return app.app.test_client()


# ═══════ Lo que el gate de seguridad encontro (T3.4, revision) ═══════
#
# `X-Dashboard-Token` es una cabecera propia, y `requests` SOLO limpia
# `Authorization` y `Cookie` al cambiar de host en una redireccion: una cabecera
# nuestra se reenvia intacta a donde diga el `Location`. Con DNS dinamico
# (duckdns) eso no es teorico: quien controle el nombre puede devolver un 30x y
# quedarse con el token. El endpoint no tiene ninguna razon para redirigir.


class TestElTokenNoViajaADondeDigaOtro:

    def test_la_consulta_no_sigue_redirecciones(self, monkeypatch):
        capturado = {}

        def falso_get(url, **kw):
            capturado.update(kw)
            class R:
                status_code = 200
            return R()

        monkeypatch.setattr(hd.requests, "get", falso_get)
        hd.consultar("https://ejemplo.mx", "/api/importador/estado", "token-de-prueba")

        assert capturado.get("allow_redirects") is False

    def test_un_3xx_no_se_sigue_y_no_se_lee_como_verde(self, monkeypatch):
        class Redirige:
            status_code = 302
            headers = {"Location": "https://otro-host.example/roba"}
            text = ""

        monkeypatch.setattr(hd, "consultar", lambda *a, **k: Redirige())
        monkeypatch.setattr(sys, "argv", ["huella", "https://ejemplo.mx", "--token", "x"])

        assert hd.main() != 0


class TestUnFalloDeMedicionNoEsUnVerde:
    """Exit 0 significa «al dia». No puede significar «no pude comprobarlo»."""

    def test_un_error_de_red_tiene_codigo_de_salida_propio(self, monkeypatch, capsys):
        def revienta(*a, **k):
            raise hd.requests.exceptions.ConnectTimeout("sin ruta al host")

        monkeypatch.setattr(hd, "consultar", revienta)
        monkeypatch.setattr(sys, "argv", ["huella", "https://ejemplo.mx", "--token", "x"])

        codigo = hd.main()

        assert codigo not in (0, 1), "se confunde con «al dia» o con «rancio»"
        assert "token" not in capsys.readouterr().out.lower().replace("token:", "")


class TestElTokenNoTieneQueIrEnLaLineaDeComandos:
    """`--token` queda visible en `ps` y en el historial del shell."""

    def test_se_toma_de_la_variable_de_entorno_si_no_se_pasa(self, monkeypatch):
        vistos = {}
        monkeypatch.setenv("PANEL_DASHBOARD_TOKEN", "desde-el-entorno")
        monkeypatch.setattr(hd, "consultar",
                            lambda base, ruta, tok: vistos.setdefault("tok", tok) and None
                            or _respuesta_ok())
        monkeypatch.setattr(sys, "argv", ["huella", "https://ejemplo.mx"])

        hd.main()

        assert vistos["tok"] == "desde-el-entorno"


def _respuesta_ok():
    class R:
        status_code = 200
        def json(self):
            return {c: 0 for c, _, _ in MARCADORES}
    return R()


class TestUnCampoPresenteQueNoSirveNoCuenta:
    """El CRITICAL del gate: `clave in datos` da por bueno un `None`.

    Hoy el endpoint nunca devuelve `None` en estos campos, asi que no era un
    incidente vivo. Pero un cambio de una linea en `app.py` lo dispararia sin que
    nada se enterara, y "un fallo de medicion que se lee como exito" es justo lo
    que esta herramienta existe para evitar.
    """

    def test_un_marcador_en_None_cuenta_como_ausente(self):
        datos = {c: None for c, _, _ in MARCADORES}

        v = veredicto(datos)

        assert v.rancio is True
        assert "nuevos_en_sheet" in v.faltantes

    def test_pero_cero_y_cadena_vacia_SI_valen(self):
        """Un importador en reposo tiene los contadores a 0 y la fase en ''.
        Tratarlos como ausentes daria rancio un panel al dia."""
        datos = {c: 0 for c, _, _ in MARCADORES}
        datos["fase"] = ""
        datos["medidor"] = {}

        assert veredicto(datos).rancio is False

    def test_un_dict_vacio_falla_cerrado(self):
        assert veredicto({}).rancio is True


class TestLaRespuestaQueNoSePuedeInterpretar:

    def test_json_valido_que_no_es_objeto_no_revienta_con_traceback(self, monkeypatch):
        class NoEsObjeto:
            status_code = 200
            headers = {"Content-Type": "application/json"}
            content = b"null"
            text = "null"
            def json(self):
                return None

        monkeypatch.setattr(hd, "consultar", lambda *a, **k: NoEsObjeto())
        monkeypatch.setattr(sys, "argv", ["huella", "https://ejemplo.mx", "--token", "x"])

        assert hd.main() == hd.NO_INTERPRETABLE

    def test_el_cuerpo_no_se_vuelca_salvo_que_se_pida(self, monkeypatch, capsys):
        class Rara:
            status_code = 503
            headers = {"Content-Type": "text/html"}
            content = b"x" * 50
            text = "SECRETO-DE-UN-PROXY-INTERMEDIO"

        monkeypatch.setattr(hd, "consultar", lambda *a, **k: Rara())
        monkeypatch.setattr(sys, "argv", ["huella", "https://ejemplo.mx", "--token", "x"])
        hd.main()

        assert "SECRETO-DE-UN-PROXY" not in capsys.readouterr().out
