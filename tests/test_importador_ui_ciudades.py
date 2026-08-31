"""Plan 1 - T1.7. UI de ciudades del importador.

Siguiendo el patron de tests/test_importador_frontend.py, se afirma sobre el
contenido servido de la superficie, que `leer_superficie()` reune desde
templates/ y static/: es el unico modo de probar este JavaScript sin
infraestructura de navegador.

Los dos ultimos bloques VERIFICAN B9 y B11, que ya estaban hechos antes de este
plan. No los reimplementan: los fijan para que nadie los deshaga sin enterarse.
"""
import re

import pytest

import app as app_modulo  # noqa: F401  (la suite lo necesita importado)
from conftest import leer_superficie

REGIONES = [
    "Noroeste", "Noreste", "Occidente", "Centro-Norte",
    "Centro-Sur", "Valle de Mexico", "Sureste", "Peninsula",
]


@pytest.fixture(scope="module")
def html():
    return leer_superficie("importador")


class TestElArrayEstaticoDesaparecio:
    def test_ciudades_mx_ya_no_existe_en_app(self, html):
        """293 entradas escritas a mano, 50 nombres duplicados y 9 con
        abreviatura de estado pegada que viajaba literal a Google Places."""
        assert "CIUDADES_MX" not in html

    def test_ninguna_ciudad_queda_escrita_a_mano_en_el_html(self, html):
        """Un puñado de nombres del array viejo, elegidos entre los que NO
        aparecen por otro motivo en la pagina."""
        for ciudad in ("'Tehuacan'", "'Santiago Ixc'", "'Guadalupe NL'", "'La Paz BCS'"):
            assert ciudad not in html

    def test_el_importador_consulta_su_propio_endpoint(self, html):
        assert "/api/importador/ciudades" in html

    def test_ya_no_fusiona_a_mano_con_el_endpoint_del_dashboard(self, html):
        """La fusion se hace en el backend desde T1.5. Si el navegador vuelve a
        armarla, las dos cuentas se separan otra vez."""
        assert "new Set(CIUDADES_MX)" not in html


class TestFiltroPorRegion:
    def test_existe_el_selector_de_region(self, html):
        assert 'id="region-filter"' in html

    def test_el_selector_arranca_con_la_opcion_todas(self, html):
        assert "Todas" in html

    def test_las_ocho_regiones_las_sirve_el_backend_y_no_el_html(self):
        """Escribirlas en el HTML duplicaria la lista y la dejaria libre de
        desincronizarse del catalogo. El selector se rellena en tiempo de
        ejecucion desde /api/importador/ciudades, asi que la comprobacion va
        contra el endpoint, que es donde vive la verdad.
        """
        app_modulo.app.config["TESTING"] = True
        app_modulo.get_data = lambda *a, **k: []
        app_modulo.get_all_respuestas = lambda *a, **k: []
        d = app_modulo.app.test_client().get("/api/importador/ciudades").get_json()
        assert {r["region"] for r in d["regiones"]} == set(REGIONES)

    def test_el_selector_dispara_el_filtrado(self, html):
        assert re.search(r'id="region-filter"[^>]*onchange="filtrarCiudades\(\)"', html)

    def test_el_filtro_combina_region_y_texto(self, html):
        """Escribir en el buscador con una region elegida no puede ignorar la
        region: serian dos filtros que se pisan."""
        fn = _funcion(html, "filtrarCiudades")
        assert "region" in fn and ("includes(q)" in fn or "includes(texto)" in fn)

    def test_cada_region_muestra_su_conteo(self, html):
        """'Occidente (87)': sin el numero, el operador no sabe si la region esta
        vacia o si el filtro se rompio."""
        fn = _funcion(html, "pintarRegiones") or _funcion(html, "cargarCiudades")
        assert "regiones" in fn


class TestTransparenciaDelRanking:
    def test_el_chip_lleva_la_explicacion_del_backend(self, html):
        fn = _funcion(html, "renderChips")
        assert "explicacion" in fn
        assert "title=" in fn

    def test_el_chip_muestra_el_conteo_de_ferreterias(self, html):
        """El puntaje va en escala logaritmica y comprime: sin el conteo crudo al
        lado, un 86.7 frente a un 89.8 no dice lo que el operador leeria que dice
        (ADR seccion 4.3)."""
        fn = _funcion(html, "renderChips")
        assert "unidades_ferreteras" in fn

    def test_las_ciudades_sin_clasificar_son_visibles(self, html):
        """La hoja trae valores que no son ciudades. Nada se pierde en silencio."""
        assert "sin_clasificar" in html


class TestB9ElNombreDeCiudadSigueEscapado:
    """Ya estaba hecho antes del Plan 1. Estos tests lo FIJAN."""

    def test_existe_el_escapador(self, html):
        assert "function escaparHtml" in html

    def test_el_nombre_pasa_por_el_escapador(self, html):
        assert "escaparHtml(c.ciudad)" in _funcion(html, "renderChips")

    def test_no_hay_interpolacion_dentro_de_onclick(self, html):
        """Un apostrofo en el nombre rompia el handler; un <img onerror> ejecutaba."""
        assert "seleccionarCiudad" not in html
        assert not re.search(r"onclick=\"[^\"]*\$\{c\.", html)

    def test_el_nombre_viaja_por_dataset_con_listener_delegado(self, html):
        assert "data-ciudad=" in html
        assert "dataset.ciudad" in html
        assert "addEventListener('click'" in html


class TestB11ElRangoNoSeRenumeraAlFiltrar:
    """Tambien hecho antes del Plan 1. Fijado aqui."""

    def test_el_rank_se_fija_sobre_el_catalogo_completo(self, html):
        fn = _funcion(html, "cargarCiudades")
        assert re.search(r"\.rank\s*=", fn), "el rank tiene que asignarse al cargar"

    def test_render_chips_lee_el_rank_y_no_el_indice_de_la_lista(self, html):
        """Si renderChips numerara por el indice recibido, al escribir en el
        filtro la ciudad numero 47 apareceria con medalla de oro."""
        fn = _funcion(html, "renderChips")
        assert "c.rank" in fn
        assert not re.search(r"lista\.map\(\s*\(\s*c\s*,\s*i\s*\)", fn)


def _funcion(html: str, nombre: str) -> str:
    """Recorta desde 'function <nombre>' hasta la siguiente declaracion.

    Se recorta hasta la siguiente funcion y no a una ventana fija de caracteres:
    con una ventana fija, anadir codigo empuja fuera del recorte justo lo que el
    test quiere comprobar y el test se vuelve verde por mudanza.
    """
    i = html.find(f"function {nombre}")
    if i < 0:
        i = html.find(f"async function {nombre}")
    if i < 0:
        return ""
    j = html.find("\nfunction ", i + 10)
    k = html.find("\nasync function ", i + 10)
    fines = [x for x in (j, k) if x > 0]
    return html[i:min(fines)] if fines else html[i:]


class TestElJsNoSeTragaUnaRespuestaMalformada:
    """El catch solo salta con fallo de red, status no-2xx o JSON invalido. Un 200
    con JSON valido pero SIN las claves esperadas —una pagina de error del proxy
    inverso, o un cambio futuro del backend— no lanzaba nada y acababa en dos
    listas vacias indistinguibles de "no hay resultados". Es el estado mas
    silencioso de los tres porque no dispara ni el catch ni el aviso amarillo.
    """

    def test_valida_la_forma_de_la_respuesta_antes_de_usarla(self, html):
        fn = _funcion(html, "cargarCiudades")
        assert "Array.isArray(d.ciudades)" in fn
        assert "throw" in fn

    def test_ya_no_cae_a_lista_vacia_con_el_operador_or(self, html):
        fn = _funcion(html, "cargarCiudades")
        assert "d.ciudades || []" not in fn

    def test_avisa_cuando_el_servidor_no_pudo_leer_el_catalogo(self, html):
        """Sin esto, "el archivo no carga" y "ninguna ciudad caso" se ven igual
        desde el navegador. Son dos problemas con dos arreglos distintos."""
        fn = _funcion(html, "cargarCiudades")
        assert "catalogo_cargado" in fn
