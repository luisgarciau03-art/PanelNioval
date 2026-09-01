"""Plan 4 - T4.7. El rediseno del tablero, fijado.

Cinco cosas que la tarea arregla, y que se deshacen solas si nadie las vigila:

  1. **CE3 llega a cero.** Los 31 colores literales que quedaban vivian todos en
     `dashboard.js` y eran dos paletas de datos: las series de Chart.js y el
     color de fila del operador. Una grafica necesita una CADENA de color, no
     puede consumir `var()`, y esa es la excusa con la que los hex se quedaron.
     Se resuelve leyendo los tokens con `getComputedStyle`.

  2. **El color de un resultado significa algo.** La grafica de resultados usaba
     una paleta POSICIONAL sobre `Object.keys(res)`, o sea el orden en que la
     hoja devolvia las claves: bastaba con que Google las reordenara para
     pintar APROBADO de rojo.

  3. **La navegacion se podia usar.** Los 12 `div` con `onclick` no entran en el
     orden de tabulacion, no responden a Enter ni a Espacio y no se anuncian
     como control (SC 2.1.1).

  4. **Las ocho tarjetas dejan de pesar igual.** El propio ADR lo marcaba como
     la senal de que la direccion no se aplico.

  5. **La insignia dice la verdad.** Decia "Actualizado 10:17" con la hora del
     NAVEGADOR, pero el panel sirve de una cache de 5 minutos: con la cache
     caliente el dato podia tener 4 minutos y la insignia lo negaba.
"""
import re
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import app

RAIZ = Path(__file__).resolve().parent.parent
CSS = RAIZ / "static" / "css"
JS = RAIZ / "static" / "js"
TPL = RAIZ / "templates"

RE_HEX = re.compile(r"#[0-9a-fA-F]{3,8}\b")

FUENTES = [
    "static/js/dashboard.js", "static/js/formulario.js",
    "static/js/importador.js", "static/js/estados.js",
    "static/css/base.css", "static/css/componentes.css",
    "static/css/dashboard.css", "static/css/formulario.css",
    "static/css/importador.css",
    "templates/dashboard.html", "templates/formulario.html",
    "templates/importador.html",
]


def _texto(ruta):
    return (RAIZ / ruta).read_text(encoding="utf-8") if isinstance(ruta, str) \
        else ruta.read_text(encoding="utf-8")


@pytest.fixture
def client():
    app.app.config["TESTING"] = True
    return app.app.test_client()


# ───────────────────────────── CE3 a cero ───────────────────────────────────

class TestCE3LlegaACero:
    @pytest.mark.parametrize("archivo", FUENTES)
    def test_ningun_color_literal_fuera_de_tokens(self, archivo):
        hallazgos = RE_HEX.findall(_texto(archivo))
        assert not hallazgos, f"{archivo}: {sorted(set(hallazgos))}"

    def test_tokens_css_si_los_tiene(self):
        """Control negativo: si este saliera vacio, el de arriba pasaria porque
        no sabe mirar, no porque no haya colores."""
        assert len(RE_HEX.findall(_texto(CSS / "tokens.css"))) > 20

    def test_las_dos_paletas_de_datos_estan_declaradas(self):
        tokens = _texto(CSS / "tokens.css")
        for nombre in ("--dato-aprobado", "--dato-negado", "--dato-serie",
                       "--dato-rejilla", "--fila-ambar", "--fila-ambar-fondo"):
            assert nombre in tokens, f"falta {nombre}"

    def test_el_js_lee_los_tokens_en_vez_de_copiarlos(self):
        js = _texto(JS / "dashboard.js")
        assert "getComputedStyle(document.documentElement)" in js
        assert re.search(r"function token\(nombre\)", js)


# ──────────────── el color del resultado no depende del orden ───────────────

class TestElColorDelResultadoEsSemantico:
    def test_existe_un_mapa_de_resultado_a_color(self):
        js = _texto(JS / "dashboard.js")
        m = re.search(r"COLOR_RESULTADO\s*=\s*\{(.*?)\n\};", js, re.S)
        assert m, "no hay mapa de resultado a color"
        mapa = m.group(1)
        for etiqueta, token in (("APROBADO", "--dato-aprobado"),
                                ("NEGADO", "--dato-negado"),
                                ("NO COMPATIBLE", "--dato-no-compatible"),
                                ("MARCA UNICA", "--dato-marca-unica")):
            assert etiqueta in mapa, f"falta {etiqueta}"
            assert token in mapa, f"falta {token}"

    def test_las_variantes_con_acento_estan_cubiertas(self):
        """La hoja escribe BUZON y BUZÓN, y las dos llegan tal cual."""
        js = _texto(JS / "dashboard.js")
        m = re.search(r"COLOR_RESULTADO\s*=\s*\{(.*?)\n\};", js, re.S).group(1)
        assert "BUZÓN" in m and "BUZON" in m
        assert "TELÉFONO INCORRECTO" in m and "TELEFONO INCORRECTO" in m

    def test_la_grafica_pinta_por_etiqueta_no_por_posicion(self):
        js = _texto(JS / "dashboard.js")
        assert "labelsR.map(colorDeResultado)" in js, (
            "la grafica sigue usando una paleta posicional"
        )

    def test_el_patron_ve_la_paleta_posicional_que_se_retiro(self):
        """Control negativo."""
        viejo = "backgroundColor: ['#00CC47','#e74c3c','#e67e22']"
        assert RE_HEX.findall(viejo)


# ─────────────────── la navegacion se puede usar con teclado ────────────────

class TestLaNavegacionEsAlcanzable:
    def test_ningun_div_de_navegacion_con_onclick(self):
        html = _texto(TPL / "dashboard.html")
        assert "onclick=\"showSection" not in html, (
            "la navegacion sigue colgando de un div con onclick"
        )

    def test_las_doce_secciones_son_botones(self):
        html = _texto(TPL / "dashboard.html")
        botones = re.findall(r'<button[^>]*class="nav-item[^"]*"[^>]*data-seccion="([a-z-]+)"', html)
        assert len(botones) == 12, f"solo {len(botones)}: {botones}"

    def test_los_accesos_externos_son_enlaces_con_noopener(self):
        """Abren otra pagina: son enlaces, no botones. Y `target=_blank` sin
        `rel=noopener` deja a la pestana nueva con acceso a `window.opener`."""
        html = _texto(TPL / "dashboard.html")
        enlaces = re.findall(r'<a class="nav-item nav-item--herramienta"[^>]*>', html, re.S)
        assert len(enlaces) == 2
        bloque = html[html.index("nav-item--herramienta"):]
        assert bloque.count('rel="noopener"') >= 2

    def test_la_seccion_activa_se_anuncia(self):
        html = _texto(TPL / "dashboard.html")
        assert 'aria-current="page"' in html
        js = _texto(JS / "dashboard.js")
        assert "setAttribute('aria-current', 'page')" in js
        assert "removeAttribute('aria-current')" in js

    def test_showsection_ya_no_depende_de_event(self):
        """Dependia de `event.currentTarget`, asi que llamarla desde codigo
        -no desde un manejador- reventaba con `event is not defined`."""
        js = re.sub(r"//[^\n]*", "", _texto(JS / "dashboard.js"))
        assert "event.currentTarget" not in js

    def test_el_menu_tiene_nombre(self):
        html = _texto(TPL / "dashboard.html")
        assert re.search(r'<nav aria-label="[^"]+"', html)

    def test_los_emojis_de_menu_son_decorativos(self):
        """Un lector que anuncie "grafico de barras ascendente" antes del
        nombre de la seccion solo mete ruido."""
        html = _texto(TPL / "dashboard.html")
        iconos = re.findall(r'<span class="icon"[^>]*>', html)
        assert iconos
        for i in iconos:
            assert 'aria-hidden="true"' in i, i


# ───────────────────── las ocho tarjetas dejan de pesar igual ───────────────

class TestHayJerarquiaEnLasTarjetas:
    def test_el_tablero_pinta_dos_grupos(self):
        js = _texto(JS / "dashboard.js")
        assert "cards--principal" in js and "cards--desglose" in js

    def test_hay_una_cifra_dominante(self):
        js = _texto(JS / "dashboard.js")
        assert js.count("card--principal") == 1, (
            "o no hay cifra dominante, o hay varias y entonces no domina ninguna"
        )
        css = _texto(CSS / "dashboard.css")
        regla = re.search(r"\.card\.card--principal \.value\{([^}]*)\}", css)
        assert regla and "--texto-3xl" in regla.group(1), (
            "la cifra dominante no gana la cascada: `.card .value` se declara "
            "mas abajo y con la misma especificidad gana la ultima"
        )
        # Gana por ESPECIFICIDAD (0,3,0 contra 0,2,0), no por orden: por eso el
        # selector lleva las dos clases. Que gane de verdad se comprueba
        # midiendo el tamano renderizado en `tools/verificar_tablero.py`; aqui
        # solo se fija la forma del selector, que es lo que un archivo de texto
        # puede saber.
        assert ".card.card--principal .value" in css

    def test_el_desglose_pesa_menos(self):
        css = _texto(CSS / "dashboard.css")
        assert re.search(r"\.cards--desglose \.card \.value\{[^}]*font-size", css), (
            "el desglose usa el mismo tamano que la fila principal"
        )

    def test_el_esqueleto_replica_los_dos_grupos(self):
        """Si el esqueleto pinta una sola rejilla de 8 y el contenido llega en
        dos de 3 y 5, la altura cambia y vuelve el salto de layout."""
        html = _texto(TPL / "dashboard.html")
        bloque = html[html.index('id="dash-cards"'):html.index('class="charts"')]
        assert "cards--principal" in bloque and "cards--desglose" in bloque
        assert bloque.count("esqueleto-tarjeta") == 8


# ───────────────────── la insignia de cache dice la verdad ──────────────────

class TestLaInsigniaDiceLaVerdad:
    def test_la_api_expone_la_edad_del_dato(self, client, monkeypatch):
        ws = MagicMock()
        ws.get_all_values.return_value = [["TIENDA", "CIUDAD"], ["A", "B"]]
        cliente = MagicMock()
        sp = MagicMock()
        cliente.open_by_key.return_value = sp
        sp.worksheet.return_value = ws
        monkeypatch.setattr(app, "get_gs_client", lambda: cliente)
        app._cache_clear()
        datos = client.get("/api/prospectos/stats").get_json()
        assert "cache" in datos
        assert "edad_seg" in datos["cache"] and "ttl_seg" in datos["cache"]
        assert datos["cache"]["ttl_seg"] == app.CACHE_TTL

    def test_la_edad_crece_con_el_tiempo(self, monkeypatch):
        """Y no es siempre cero: si lo fuera, la insignia mentiria igual que
        antes pero con otra redaccion."""
        app._cache_clear()
        assert app.edad_de_cache("contactos") is None
        app._cache_set("contactos", ([], time.time() - 120))
        edad = app.edad_de_cache("contactos")
        assert edad is not None and 115 < edad < 125
        app._cache_clear()

    def test_la_insignia_usa_la_edad_y_no_la_hora_del_navegador(self):
        js = _texto(JS / "dashboard.js")
        cuerpo = re.search(r"function updateCacheBadge\(\)\s*\{(.*?)\n\}", js, re.S)
        assert cuerpo, "no se encuentra updateCacheBadge"
        c = cuerpo.group(1)
        assert "edad_seg" in c
        assert "toLocaleTimeString" not in c, (
            "sigue mostrando la hora del navegador"
        )

    def test_la_insignia_explica_que_significa(self):
        """Y la explicacion tiene que estar en el ARBOL DE ACCESIBILIDAD, no
        solo en `title`: `title` no es alcanzable por teclado, no existe en
        pantalla tactil y los lectores no lo anuncian de forma fiable. Lo marco
        `a11y-architect` como HIGH."""
        js = _texto(JS / "dashboard.js")
        cuerpo = re.search(r"function ponerInsigniaCache\([^)]*\)\s*\{(.*?)\n\}", js, re.S)
        assert cuerpo, "no se encuentra ponerInsigniaCache"
        c = cuerpo.group(1)
        assert "cache-badge-detalle" in c, "la explicacion solo vive en title"
        assert ".title" in c, "se pierde la comodidad del raton"

        html = _texto(TPL / "dashboard.html")
        assert '<span class="solo-lectores" id="cache-badge-detalle"></span>' in html, (
            "falta el nodo de solo lectores dentro de la insignia"
        )


# ───────────── lo que encontraron los reviewers de la T4.7 ─────────────────

class TestElArbolDelDocumentoEstaBien:
    """El CRITICAL. Un `</div>` de mas dejo 11 de las 12 secciones colgando de
    `<body>` en vez de `#content`, y las graficas del tablero fuera de su
    seccion: no se ocultaban NUNCA al cambiar de pantalla.

    Lo grave no es el `</div>`: es que la verificacion en navegador lo dio por
    bueno, porque comprobaba la CLASE `.section.active` -que seguia siendo
    correcta- y no el anidamiento real. `tools/verificar_tablero.py` mira ahora
    las dos cosas.
    """

    def test_las_etiquetas_div_estan_balanceadas(self):
        html = _texto(TPL / "dashboard.html")
        abiertos = len(re.findall(r"<div\b", html))
        cerrados = html.count("</div>")
        assert abiertos == cerrados, f"{abiertos} abiertos, {cerrados} cerrados"

    def test_siguen_estando_las_doce_secciones(self):
        html = _texto(TPL / "dashboard.html")
        assert html.count('class="section') == 12

    def test_el_verificador_mira_el_arbol_y_no_solo_la_clase(self):
        herramienta = _texto(RAIZ / "tools" / "verificar_tablero.py")
        assert "parentElement.id !== 'content'" in herramienta
        assert "offsetParent" in herramienta, (
            "sin visibilidad real, una clase correcta tapa un arbol roto"
        )


class TestElFocoSeVeSobreElEncabezadoFijo:
    """CRITICAL de `a11y-architect`. El anillo de base.css se dibuja hacia
    AFUERA, y el boton de orden vive en un `<th>` pegado con `sticky` al borde
    del contenedor con `overflow`: el anillo claro se recortaba siempre, y el
    oscuro que quedaba da 2.36:1 sobre el azul del encabezado — por debajo del
    3:1 que WCAG 1.4.11 pide para un indicador de foco."""

    def test_el_anillo_del_boton_de_orden_va_por_dentro(self):
        css = _texto(CSS / "dashboard.css")
        regla = re.search(r"\.tabla__orden:focus-visible\{([^}]*)\}", css)
        assert regla, "el boton de orden no declara foco propio"
        c = regla.group(1)
        assert "inset" in c, "el anillo se sigue dibujando hacia afuera"
        assert "outline:none" in c, "el outline exterior sigue puesto"
        assert "--foco-claro" in c and "--foco-oscuro" in c, (
            "un anillo de un solo tono no se ve sobre los ocho fondos"
        )

    def test_el_desplazamiento_deja_hueco_bajo_el_encabezado(self):
        """SC 2.4.11: al enfocar una fila desplazada, el navegador la alinea
        con el borde del contenedor, que es donde esta el encabezado fijo y
        opaco. El elemento enfocado quedaba tapado."""
        css = _texto(CSS / "dashboard.css")
        assert re.search(r"\.tbl-wrap\{[^}]*scroll-padding-top", css)


class TestLaInsigniaDelMenuNoContaminaElBoton:
    """HIGH de `a11y-architect`. Un `role=status` dentro del boton se cuela en
    su nombre accesible -pasaba a leerse "Envios Catalogo 3 envios con
    problema" cada vez que se tabula- y, al usarse su contenido para calcular
    ese nombre, varios motores dejan de exponerlo como region viva, que es
    justo para lo que estaba."""

    def test_la_insignia_es_decorativa(self):
        html = _texto(TPL / "dashboard.html")
        insignia = re.search(r'<span class="nav-item__insignia"[^>]*>', html)
        assert insignia, "no se encuentra la insignia"
        assert 'aria-hidden="true"' in insignia.group(0)
        assert "role=" not in insignia.group(0)

    def test_el_anuncio_vive_fuera_del_boton(self):
        html = _texto(TPL / "dashboard.html")
        assert 'id="anuncios-menu"' in html
        region = re.search(r'<[^>]*id="anuncios-menu"[^>]*>', html).group(0)
        assert 'role="status"' in region
        assert html.index('id="anuncios-menu"') > html.index("</nav>")

    def test_el_nombre_completo_va_en_el_boton(self):
        js = _texto(JS / "dashboard.js")
        cuerpo = re.search(r"async function actualizarBadgeCatalogo\(\)\s*\{(.*?)\n\}",
                           js, re.S).group(1)
        assert "boton.setAttribute('aria-label'" in cuerpo
        assert "anuncios" in cuerpo


class TestLaCascadaNoSeComeLaJerarquia:
    def test_la_franja_de_la_tarjeta_dominante_tambien_gana(self):
        """El mismo defecto de especificidad que el comentario de al lado dice
        haber corregido para `.value`, sin corregir en el borde. Lo encontro
        `code-reviewer` midiendo `borderLeftWidth` en un navegador real."""
        css = _texto(CSS / "dashboard.css")
        assert ".card.card--principal{border-left-width:5px}" in css


class TestElReflowNoEmpeora:
    def test_la_fila_principal_no_pide_mas_ancho_que_las_demas(self):
        """La barra lateral sigue siendo `fixed` de 230 px sin media query
        (responsive es T4.10). Subir el minimo de columna de la fila de KPI a
        220 px pedia 60 px mas de ancho justo en la franja que debe verse
        primero. La jerarquia la da el TAMANO de la cifra, no el ancho."""
        css = _texto(CSS / "dashboard.css")
        principal = re.search(r"\.cards--principal\{[^}]*minmax\((\d+)px", css)
        generica = re.search(r"^\.cards\{[^}]*minmax\((\d+)px", css, re.M)
        assert principal and generica
        assert int(principal.group(1)) <= int(generica.group(1)), (
            "la fila principal exige mas ancho que el resto del tablero"
        )


# ──────────────────────── las tablas son el trabajo ─────────────────────────

class TestLasTablasSeDejanTrabajar:
    def test_el_encabezado_se_queda_fijo(self):
        css = _texto(CSS / "dashboard.css")
        assert re.search(r"\.tbl-wrap th\{[^}]*position:sticky", css)
        assert re.search(r"\.tbl-wrap\{[^}]*max-height", css), (
            "sin area desplazable, sticky no tiene contra que pegarse"
        )

    def test_el_orden_es_un_boton(self):
        js = _texto(JS / "dashboard.js")
        assert "tabla__orden" in js
        assert 'onclick="sortTable' not in js, "el th sigue con onclick"

    def test_el_orden_se_anuncia(self):
        js = _texto(JS / "dashboard.js")
        assert "aria-sort" in js
        for valor in ("ascending", "descending", "none"):
            assert valor in js, f"falta aria-sort={valor}"

    def test_cada_fila_tiene_tantas_celdas_como_encabezados(self):
        """Fallo PREEXISTENTE, sin relacion con el rediseno, que encontro la
        verificacion funcional en navegador de esta tarea.

        `editTh` era condicional (`isEditable ? th : ''`) y `editTd` no: emitia
        siempre un `<td>`. Toda tabla NO editable salia con 7 encabezados y 8
        celdas, asi que el contenido aparecia corrido una columna a la derecha:
        el telefono debajo de "CIUDAD", la ciudad debajo de "TIENDA" y la
        primera columna vacia. Ocho de las once tablas del panel.
        """
        js = _texto(JS / "dashboard.js")
        cuerpo = re.search(r"const editTd = (.*?);$", js, re.M | re.S)
        assert cuerpo, "no se encuentra editTd"
        # La celda solo existe si existe su encabezado.
        assert "!isEditable ? ''" in cuerpo.group(1), (
            "la celda de acciones se emite aunque no haya encabezado"
        )

    def test_la_paginacion_dice_donde_esta(self):
        js = _texto(JS / "dashboard.js")
        assert "Página ${page} de ${totalPages}" in js
        assert "aria-label=" in js and "Página anterior" in js

    def test_la_insignia_del_menu_se_oculta_con_hidden(self):
        """`style.display='none'` deja el elemento en el arbol de
        accesibilidad; `hidden` no."""
        js = _texto(JS / "dashboard.js")
        cuerpo = re.search(r"async function actualizarBadgeCatalogo\(\)\s*\{(.*?)\n\}", js, re.S)
        assert cuerpo
        # Sin comentarios: el propio comentario que explica el cambio cita
        # `style.display`, y mirarlo entero ponia el test en rojo por su
        # documentacion. Es la tercera vez que pasa en esta tanda.
        codigo = re.sub(r"//.*", "", cuerpo.group(1))
        assert "badge.hidden" in codigo
        assert "style.display" not in codigo
