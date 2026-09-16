"""Plan 1 - T1.4. CE2 y CE3 sobre el camino real: catalogo -> endpoint -> filtro.

CE2 dice: *cada macro-region lista **todas** sus ciudades del catalogo*. Es la
mitad del requisito del dueno, y la mitad que puede romperse sin hacer ruido:
si el filtro por region funciona pero la lista sale recortada, la cobertura que
T1.3 gano (606 -> 1,004 municipios) no llega al operador y nadie se entera,
porque una lista corta se ve exactamente igual que una lista completa.

El contraste va por los tres eslabones, no solo por el ultimo:

  1. `datos/ciudades_mx.json`  -- la verdad del catalogo
  2. `/api/importador/ciudades` -- lo que el servidor entrega
  3. `filtrarCiudades()`        -- lo que el navegador muestra

Un test que solo mire el endpoint daria verde con un `renderChips` que corte a
100 chips. Uno que solo mire el JSON daria verde aunque el endpoint truncara.

Por que el JS se prueba como string: vive embebido en `app.py` y no hay
infraestructura de navegador en esta suite. Es el mismo patron de
`tests/test_importador_frontend.py` y `tests/test_importador_ui_ciudades.py`.
La aritmetica del filtro SI se ejerce de verdad: se replica su predicado
(`c.region === region`, igualdad exacta) sobre la carga util real del endpoint,
y un test aparte fija que el predicado del JS sigue siendo ese.
"""
import json
import pathlib
import re

import pytest

import app as app_modulo

RAIZ = pathlib.Path(__file__).resolve().parents[1]
CATALOGO = RAIZ / "datos" / "ciudades_mx.json"

REGIONES = [
    "Noroeste", "Noreste", "Occidente", "Centro-Norte",
    "Centro-Sur", "Valle de Mexico", "Sureste", "Peninsula",
]

# app.py:943-944. El piso del factor es lo que impide que una ciudad muy
# trabajada caiga por debajo del piso de CE3 al multiplicar.
FACTOR_MIN = 0.60
POTENCIAL_MINIMO_ACEPTABLE = 5


@pytest.fixture(scope="module")
def html():
    """El JS del importador, venga de donde venga.

    Hasta el Plan 4 vivia embebido en `app.py` como `IMPORTADOR_HTML`; el PR #43
    lo saco a `static/js/importador.js`. Estos tests comprueban el PREDICADO del
    filtro, que es el mismo en las dos estructuras, asi que se busca primero en
    el archivo extraido y se cae al modulo si todavia no existe.

    Sin esto, el test se rompe al mergear el rediseno **por una mudanza**, no
    porque el filtro haya dejado de funcionar -- que es justo el falso rojo que
    hace que alguien acabe borrando un test bueno.
    """
    extraido = RAIZ / "static" / "js" / "importador.js"
    if extraido.exists():
        return extraido.read_text(encoding="utf-8")
    return app_modulo.IMPORTADOR_HTML


def _funcion(html: str, nombre: str) -> str:
    """Recorta desde `function <nombre>` hasta la siguiente declaracion.

    Hasta la siguiente funcion y no a una ventana fija de caracteres: con una
    ventana fija, anadir codigo empuja fuera del recorte justo lo que el test
    quiere comprobar, y el test se vuelve verde por mudanza.
    """
    i = html.find(f"function {nombre}")
    if i < 0:
        i = html.find(f"async function {nombre}")
    assert i >= 0, f"no existe la funcion {nombre}"
    j = html.find("\nfunction ", i + 10)
    return _sin_comentarios(html[i:j if j > 0 else len(html)])


def _sin_comentarios(js: str) -> str:
    """Quita los comentarios de linea antes de buscar dentro del recorte.

    Sin esto el guard del predicado se puede enganar solo: cambiar el filtro
    vivo a `normaliza(c.region) === ...` y dejar `// antes: c.region ===
    region` como comentario lo dejaria en verde, mientras los ocho tests de
    CE2 seguirian midiendo un predicado que ya no existe.

    `://` se respeta para no destrozar una URL. Hoy no hay ninguna en estas
    funciones, pero un `fetch("https://...")` futuro no tiene por que romper
    esto en silencio.
    """
    return re.sub(r"(?<!:)//[^\n]*", "", js)


@pytest.fixture(scope="module")
def catalogo():
    with CATALOGO.open(encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def payload(monkeypatch):
    """La respuesta del endpoint con la hoja vacia.

    Vacia a proposito: CE2 es una afirmacion sobre el CATALOGO, y las metricas
    de la hoja solo cambian el orden, nunca quien esta dentro. Con una hoja
    poblada, un fallo de cobertura podria quedar tapado por un reordenamiento.
    """
    monkeypatch.setattr(app_modulo, "get_data", lambda *a, **k: [])
    monkeypatch.setattr(app_modulo, "get_all_respuestas", lambda *a, **k: [])
    app_modulo.app.config["TESTING"] = True
    r = app_modulo.app.test_client().get("/api/importador/ciudades")
    assert r.status_code == 200
    return r.get_json()


def _como_filtra_la_ui(payload: dict, region: str) -> list:
    """Replica `filtrarCiudades()`: `lista.filter(c => c.region === region)`.

    Igualdad EXACTA de cadena, sin normalizar ni recortar, igual que el JS.
    `test_el_filtro_del_js_sigue_comparando_por_igualdad_exacta` es el que
    impide que esta replica se desincronice del original.
    """
    return [c for c in payload["ciudades"] if c["region"] == region]


class TestElEndpointEntregaElCatalogoEntero:
    def test_no_se_queda_ninguna_ciudad_por_el_camino(self, payload, catalogo):
        assert len(payload["ciudades"]) == len(catalogo)

    def test_son_exactamente_las_mismas_ciudades(self, payload, catalogo):
        """Mismo numero no es lo mismo que mismas ciudades: una sustitucion
        —una entra, otra se cae— conserva el conteo."""
        del_endpoint = sorted(c["ciudad"] for c in payload["ciudades"])
        del_catalogo = sorted(c["nombre"] for c in catalogo)
        assert del_endpoint == del_catalogo

    def test_el_catalogo_se_leyo_de_verdad(self, payload):
        """Si el servidor no pudo leer el archivo, el endpoint lo dice en vez de
        devolver una lista vacia que parece 'no hay resultados'."""
        assert payload["catalogo_cargado"] is True
        assert len(payload["ciudades"]) > 900, "el catalogo de T1.3 trae 1,004"


class TestCadaRegionListaTodasSusCiudades:
    """CE2, region por region y no en agregado.

    Parametrizado a proposito: si fallara una sola region, un test agregado
    diria 'algo no cuadra' y este dice CUAL.
    """

    @pytest.mark.parametrize("region", REGIONES)
    def test_el_filtro_devuelve_exactamente_las_del_catalogo(
        self, payload, catalogo, region
    ):
        # (nombre, estado) y no solo el nombre: un set de nombres colapsaria dos
        # ciudades homonimas y podria tapar una mal clasificada de region. Hoy no
        # hay nombres repetidos —lo garantiza test_sin_duplicados_por_nombre_
        # normalizado, en OTRO archivo— y este test no quiere depender en
        # silencio de una garantia ajena.
        del_catalogo = {(c["nombre"], c["estado"]) for c in catalogo if c["region"] == region}
        de_la_ui = {(c["ciudad"], c["estado"]) for c in _como_filtra_la_ui(payload, region)}
        faltan = sorted(del_catalogo - de_la_ui)
        sobran = sorted(de_la_ui - del_catalogo)
        assert faltan == [] and sobran == [], (
            f"{region}: faltan {len(faltan)} {faltan[:8]} | sobran {len(sobran)} {sobran[:8]}"
        )

    @pytest.mark.parametrize("region", REGIONES)
    def test_el_conteo_del_selector_no_miente(self, payload, region):
        """El desplegable dice 'Sureste (213)'. Ese numero es lo unico que
        distingue una region vacia de un filtro roto, asi que tiene que
        coincidir con lo que de verdad se pinta al elegirla."""
        anunciado = next(r["total"] for r in payload["regiones"] if r["region"] == region)
        listado = len(_como_filtra_la_ui(payload, region))
        assert anunciado == listado, f"{region}: anuncia {anunciado} y lista {listado}"

    def test_las_ocho_regiones_estan_y_no_hay_una_novena(self, payload):
        assert {r["region"] for r in payload["regiones"]} == set(REGIONES)

    def test_ninguna_ciudad_queda_fuera_de_toda_region(self, payload):
        """Sumar las ocho tiene que dar el catalogo entero. Una ciudad con la
        region mal escrita no aparece en ningun filtro y solo se ve con la
        opcion 'Todas': invisible para quien filtra."""
        suma = sum(len(_como_filtra_la_ui(payload, r)) for r in REGIONES)
        assert suma == len(payload["ciudades"])


class TestLaListaLlegaEnteraAlNavegador:
    """Lo que el endpoint entrega no es lo que el operador ve si el JS recorta.

    Con 606 ciudades un tope de 200 pasaba desapercibido; con 1,004 se lleva por
    delante justo la cola que T1.3 acaba de ganar.
    """

    def test_render_chips_no_recorta_la_lista(self, html):
        fn = _funcion(html, "renderChips")
        for corte in (".slice(", ".splice(", "MAX_CHIPS", "limite"):
            assert corte not in fn, f"renderChips recorta con {corte}"

    def test_el_filtro_no_recorta_la_lista(self, html):
        fn = _funcion(html, "filtrarCiudades")
        assert ".slice(" not in fn and ".splice(" not in fn

    def test_el_filtro_del_js_sigue_comparando_por_igualdad_exacta(self, html):
        """Este test es el que sostiene a `_como_filtra_la_ui`. Si alguien
        cambia el predicado del JS (a `includes`, a comparar normalizado, a
        filtrar por estado), la replica de Python deja de representarlo y todos
        los tests de CE2 de arriba pasarian midiendo otra cosa."""
        fn = _funcion(html, "filtrarCiudades")
        assert "c.region === region" in fn

    def test_el_conteo_visible_sale_del_catalogo_completo(self, html):
        """`(1004)` junto al titulo. Se fija sobre `todasCiudades`, no sobre la
        lista filtrada: si no, al filtrar diria que el catalogo encogio."""
        fn = _funcion(html, "cargarCiudades")
        assert "todasCiudades.length" in fn


class TestCE3SobreLoQueElOperadorVeOrdenado:
    """CE3 ya tiene su test sobre el catalogo en tests/test_catalogo_ciudades.py.

    Aqui se comprueba el otro extremo del camino: lo que sale por el endpoint
    despues de multiplicar por `factor_nioval`. Es donde un cero reaparecería
    aunque el catalogo estuviera limpio.
    """

    def test_ninguna_ciudad_sale_del_endpoint_con_potencial_bajo(self, payload):
        peor = min(payload["ciudades"], key=lambda c: c["potencial_mercado"])
        assert peor["potencial_mercado"] > POTENCIAL_MINIMO_ACEPTABLE, (
            f"{peor['ciudad']} sale con potencial {peor['potencial_mercado']}"
        )

    def test_la_prioridad_tampoco_puede_hundirse_bajo_el_piso(self, payload):
        """La prioridad es potencial x factor, y el factor tiene suelo en 0.60
        (app.py:943). El caso peor imaginable es la ciudad mas chica del
        catalogo con el factor en el suelo: 14.1 x 0.60 = 8.46. El test lo
        comprueba sobre el dato, no sobre esa cuenta."""
        peor = min(payload["ciudades"], key=lambda c: c["prioridad"])
        assert peor["prioridad"] > POTENCIAL_MINIMO_ACEPTABLE, (
            f"{peor['ciudad']} sale con prioridad {peor['prioridad']}"
        )

    def test_ninguna_prioridad_es_cero(self, payload):
        """El empate arbitrario que el Plan 1 vino a quitar: una lista de ceros
        ordenada por `sort` estable depende del orden de llegada."""
        ceros = [c["ciudad"] for c in payload["ciudades"] if not c["prioridad"] > 0]
        assert ceros == [], f"ciudades con prioridad 0: {ceros[:10]}"
