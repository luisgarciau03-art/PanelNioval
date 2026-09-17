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
import pytest

import app
from tools.huella_despliegue import MARCADORES, veredicto


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
