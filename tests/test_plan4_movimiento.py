"""Plan 4 - T4.6. El sistema de movimiento, fijado.

De que se partia: nueve `transition: all` repartidos por las tres superficies,
mas `transition: border` y `transition: width`. Tres problemas distintos, no
uno:

  1. **`all` anima lo que no debe.** Incluye `width`, `padding`, `border-width`
     y `font-size`, que obligan al navegador a recalcular layout en cada cuadro.
     Basta con que alguien anada un `padding` al `:hover` para que la
     transicion pase a costar layout sin que nadie lo note. `transition: border`
     es el mismo problema en pequeno: incluye `border-width`.
  2. **La barra de progreso animaba `width`.** No es un detalle: una corrida del
     importador son minutos con la barra moviendose.
  3. **Chart.js no lo tocaba `prefers-reduced-motion`.** Dibuja sobre `<canvas>`,
     fuera de la cascada CSS, asi que el bloque de `tokens.css` no le llega. Es
     el unico movimiento del panel que hay que apagar desde JavaScript.

CE6 pide propiedades del compositor; CE7 pide que la preferencia del sistema se
respete. Los dos son de accesibilidad, no de gusto.
"""
import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
CSS = RAIZ / "static" / "css"
JS = RAIZ / "static" / "js"
TPL = RAIZ / "templates"

HOJAS = ["base.css", "componentes.css", "dashboard.css", "formulario.css",
         "importador.css", "tokens.css"]
SUPERFICIES = ["dashboard", "formulario", "importador"]

# Propiedades que fuerzan recalculo de layout al animarse. `all` las incluye
# todas por definicion. El `(?![-\w])` no es opcional: sin el, `background`
# tambien casa con `background-color`, que SI es legitima (es pintado, no
# layout), y el patron marcaria como fallo justo lo que se acaba de corregir.
RE_PROHIBIDA = re.compile(
    r"transition:\s*(all|border|background|width|height|top|left|margin|padding|font-size)"
    r"(?![-\w])"
)


def _texto(ruta: Path) -> str:
    return ruta.read_text(encoding="utf-8")


def _sin_comentarios(texto: str) -> str:
    return re.sub(r"/\*.*?\*/", "", texto, flags=re.S)


# ───────────────── CE6: solo propiedades del compositor ─────────────────────

class TestCE6NingunaTransicionDeLayout:
    @pytest.mark.parametrize("hoja", HOJAS)
    def test_ninguna_hoja_anima_layout(self, hoja):
        hallazgos = RE_PROHIBIDA.findall(_sin_comentarios(_texto(CSS / hoja)))
        assert not hallazgos, f"{hoja} anima propiedades de layout: {hallazgos}"

    @pytest.mark.parametrize("superficie", SUPERFICIES)
    def test_ninguna_plantilla_anima_layout_en_style(self, superficie):
        """Habia dos `transition: all` escondidos en atributos `style=` del
        marcado, donde ningun barrido del CSS los veia."""
        hallazgos = RE_PROHIBIDA.findall(_texto(TPL / f"{superficie}.html"))
        assert not hallazgos, f"{superficie}.html anima layout: {hallazgos}"

    @pytest.mark.parametrize("script", ["dashboard.js", "estados.js", "formulario.js",
                                        "importador.js"])
    def test_ningun_js_inyecta_una_transicion_prohibida(self, script):
        assert not RE_PROHIBIDA.findall(_texto(JS / script))

    def test_el_patron_encuentra_los_casos_reales(self):
        """Control negativo con el marcado exacto que se retiro. Sin esto, los
        tres tests de arriba pasarian igual con un patron mal escrito — que es
        lo que paso en el primer intento: `background\\b` casaba tambien con
        `background-color` y marcaba en falso."""
        for viejo in ("transition:all .2s", "transition:border .2s",
                      "transition:width .5s ease", "transition: all .15s"):
            assert RE_PROHIBIDA.search(viejo), viejo
        for bueno in ("transition:background-color 120ms linear",
                      "transition:border-color 120ms linear",
                      "transition:transform 120ms linear"):
            assert not RE_PROHIBIDA.search(bueno), bueno


class TestLasAnimacionesSonDelCompositor:
    """Un `@keyframes` que toca `width` o `top` cuesta layout en cada cuadro
    igual que una transicion, y ningun barrido de `transition:` lo ve."""

    PERMITIDAS = {"transform", "opacity"}

    @pytest.mark.parametrize("hoja", HOJAS)
    def test_cada_keyframes_solo_toca_transform_u_opacity(self, hoja):
        texto = _sin_comentarios(_texto(CSS / hoja))
        for m in re.finditer(r"@keyframes\s+([a-zA-Z0-9-]+)\s*\{(.*?)\n\}", texto, re.S):
            props = set(re.findall(r"([a-z-]+)\s*:", m.group(2)))
            assert props <= self.PERMITIDAS, (
                f"{hoja}: @keyframes {m.group(1)} toca {sorted(props - self.PERMITIDAS)}"
            )

    def test_hay_keyframes_que_mirar(self):
        """Control: si no hubiera ninguno, el test de arriba pasaria por vacio."""
        todos = []
        for hoja in HOJAS:
            todos += re.findall(r"@keyframes\s+([a-zA-Z0-9-]+)", _texto(CSS / hoja))
        assert len(todos) >= 3, f"solo se encontraron {todos}"


# ───────────── la barra de progreso ya no anima el ancho ────────────────────

class TestLaBarraDeProgresoUsaTransform:
    def test_el_css_escala_en_vez_de_ensanchar(self):
        css = _texto(CSS / "importador.css")
        regla = re.search(r"\.progress-fill\{([^}]*)\}", css)
        assert regla, "no se encuentra .progress-fill"
        cuerpo = regla.group(1)
        assert "scaleX" in cuerpo
        assert "transform-origin" in cuerpo, (
            "sin origen a la izquierda la barra crece desde el centro"
        )
        assert "transition:transform" in cuerpo

    def test_el_js_ya_no_escribe_el_ancho(self):
        js = _texto(JS / "importador.js")
        assert "style.width" not in js, "queda un ancho escrito a mano"
        assert "--avance" in js

    def test_la_plantilla_no_fija_el_ancho_en_linea(self):
        """Lo encontro `tools/verificar_movimiento.py`, no la lectura del diff.
        La plantilla conservaba `style="width:0%"` en el relleno; un estilo en
        linea gana a la hoja, asi que el elemento se quedaba con 0 px de ancho
        de layout y `scaleX` escalaba la nada: la barra no se veia avanzar
        nunca. El reposo lo fija ahora `--avance: 0` en tokens.css."""
        html = _texto(TPL / "importador.html")
        relleno = re.search(r'<div[^>]*id="prog-fill"[^>]*>', html)
        assert relleno, "no se encuentra el relleno de la barra"
        assert "width" not in relleno.group(0), relleno.group(0)

    def test_el_avance_va_acotado_entre_0_y_1(self):
        """Un `fraccion` mayor que 100 llegado del backend escalaria la barra
        fuera de su caja."""
        js = _texto(JS / "importador.js")
        cuerpo = re.search(r"function ponerAvance\(pct\)\s*\{(.*?)\n\}", js, re.S)
        assert cuerpo, "no se encuentra ponerAvance"
        assert "Math.max" in cuerpo.group(1) and "Math.min" in cuerpo.group(1)

    def test_will_change_se_pone_y_se_retira(self):
        """`will-change` permanente reserva una capa de composicion para un
        elemento que casi todo el tiempo esta quieto."""
        js = _texto(JS / "importador.js")
        cuerpo = re.search(r"function ponerAvance\(pct\)\s*\{(.*?)\n\}", js, re.S).group(1)
        assert "willChange = 'transform'" in cuerpo
        assert "willChange = ''" in cuerpo, "se pone pero no se retira"

    def test_el_componente_del_sistema_hace_lo_mismo(self):
        """La T4.4 dejo `transition: width` en `.progreso__barra` como
        'excepcion consciente'. No hacia falta ninguna excepcion."""
        css = _sin_comentarios(_texto(CSS / "componentes.css"))
        regla = re.search(r"\.progreso__barra\s*\{([^}]*)\}", css)
        assert regla and "scaleX" in regla.group(1)


# ──────────── CE7: prefers-reduced-motion, tambien fuera del CSS ────────────

class TestCE7MovimientoReducido:
    def test_los_tokens_de_duracion_se_anulan(self):
        assert "prefers-reduced-motion" in _texto(CSS / "tokens.css")

    def test_las_animaciones_propias_se_retiran_del_todo(self):
        """Poner la duracion a 1 ms deja la animacion CORRIENDO en un cuadro.
        El criterio pide que no haya movimiento no esencial, asi que las
        animaciones de entrada se retiran enteras."""
        css = _texto(CSS / "componentes.css")
        bloques = re.findall(r"@media[^{]*prefers-reduced-motion[^{]*\{(.*?\n\})", css, re.S)
        assert bloques
        texto = "\n".join(bloques)
        for clase in ("fila-entra", "seccion-entra", "esqueleto"):
            assert clase in texto, f"{clase} sigue animandose con la preferencia activa"

    def test_el_retardo_escalonado_tambien_se_anula(self):
        """Sin esto, las doce primeras filas seguirian apareciendo en cascada,
        instantaneas pero en cascada."""
        css = _texto(CSS / "componentes.css")
        bloque = re.search(r"@media[^{]*prefers-reduced-motion[^{]*\{(.*?\n\})", css, re.S)
        assert "animation-delay" in "\n".join(
            re.findall(r"@media[^{]*prefers-reduced-motion[^{]*\{(.*?\n\})", css, re.S))

    def test_chartjs_se_apaga_desde_javascript(self):
        """Chart.js dibuja sobre <canvas>: la cascada CSS no lo alcanza. Es el
        unico movimiento del panel que hay que apagar a mano."""
        js = _texto(JS / "dashboard.js")
        assert "matchMedia" in js
        assert "prefers-reduced-motion" in js
        assert re.search(r"Chart\.defaults\.animation", js), (
            "se consulta la preferencia pero no se aplica a las graficas"
        )

    def test_la_preferencia_se_aplica_antes_de_la_primera_grafica(self):
        """Aplicarla despues dejaria las seis graficas nacidas con animacion."""
        js = _texto(JS / "dashboard.js")
        i_aplicar = js.index("aplicarPreferenciaDeMovimiento();\nloadSection")
        assert i_aplicar > 0

    def test_el_cambio_de_preferencia_en_caliente_se_escucha(self):
        """La opcion del sistema puede activarse con la pagina ya abierta."""
        js = _texto(JS / "dashboard.js")
        assert re.search(r"MOVIMIENTO_REDUCIDO\.addEventListener\(\s*'change'", js)

    def test_el_escalonado_no_corre_con_la_preferencia_activa(self):
        js = _texto(JS / "dashboard.js")
        cuerpo = re.search(r"function escalonarFilas\(contenedor\)\s*\{(.*?)\n\}", js, re.S)
        assert cuerpo, "no se encuentra escalonarFilas"
        assert "MOVIMIENTO_REDUCIDO.matches" in cuerpo.group(1)


# ───────────────── el movimiento aclara, no decora ──────────────────────────

class TestElMovimientoAclaraElFlujo:
    def test_el_escalonado_esta_acotado(self):
        """Con 50 filas y un retardo por fila, la ultima entraria mas de un
        segundo despues: el escalonado dejaria de aclarar para volverse
        espera."""
        js = _texto(JS / "dashboard.js")
        m = re.search(r"FILAS_ANIMADAS\s*=\s*(\d+)", js)
        assert m, "el escalonado no tiene tope"
        assert int(m.group(1)) <= 20

        paso = re.search(r"\(i \* (\d+)\)", js)
        assert paso, "no se encuentra el paso del escalonado"
        total = int(m.group(1)) * int(paso.group(1))
        assert total <= 400, f"la ultima fila entra {total} ms tarde"

    def test_el_escalonado_se_usa_donde_se_pintan_tablas(self):
        js = _texto(JS / "dashboard.js")
        assert js.count("escalonarFilas(") >= 4, (
            "el ayudante existe pero apenas se usa"
        )

    def test_la_seccion_entrante_se_puede_repetir(self):
        """Una clase de animacion que se queda puesta solo corre la primera
        vez: al volver a la seccion no pasaria nada."""
        js = _texto(JS / "dashboard.js")
        assert "seccion-entra" in js
        assert "animationend" in js, "la clase no se retira nunca"

    def test_el_formulario_se_queda_quieto(self):
        """Decision del ADR, no descuido: `/formulario` es el registro «denso y
        quieto». Se usa hora tras hora y la velocidad de captura manda sobre la
        estetica, asi que los pasos NO llevan animacion de entrada."""
        js = _texto(JS / "formulario.js")
        assert "seccion-entra" not in js and "escalonarFilas" not in js


# ───────────── lo que encontraron los reviewers de la T4.6 ─────────────────

class TestLaFilaNuncaQuedaInvisible:
    """Hallazgo HIGH de `a11y-architect` (SC 2.4.7, Focus Visible).

    `fila-entra` usaba `backwards`, que deja la fila en su fotograma INICIAL
    durante todo el retardo: hasta 275 ms para la fila 12, mas los 200 ms de la
    animacion. Con `opacity: 0` en ese fotograma, los botones de esa fila
    -"Editar", "Subir comprobante"- eran enfocables con Tab siendo
    completamente transparentes, anillo de foco incluido. El criterio no admite
    excepcion por ser breve.
    """

    def test_la_entrada_de_fila_no_animia_opacidad(self):
        css = _sin_comentarios(_texto(CSS / "componentes.css"))
        m = re.search(r"@keyframes\s+fila-entra\s*\{(.*?)\n\}", css, re.S)
        assert m, "no se encuentra @keyframes fila-entra"
        assert "opacity" not in m.group(1), (
            "la fila vuelve a poder quedar invisible durante su retardo"
        )
        assert "transform" in m.group(1), "sin transform la entrada no se ve"

    def test_sigue_usando_backwards(self):
        """Sin `backwards` la fila salta: se queda en su sitio final y brinca a
        +6 px cuando arranca la animacion."""
        css = _sin_comentarios(_texto(CSS / "componentes.css"))
        regla = re.search(r"\.fila-entra\s*\{([^}]*)\}", css)
        assert regla and "backwards" in regla.group(1)


class TestChartJsRestauraSuValorDeFabrica:
    """Hallazgo de `a11y-architect`, confirmado en navegador: al volver de
    `reduce` a `no-preference` se escribia `undefined` en
    `Chart.defaults.animation`, que no restaura el valor de fabrica sino que lo
    borra. La grafica no se rompia, pero la configuracion de la libreria
    quedaba deshecha."""

    def test_el_valor_de_fabrica_se_captura_antes_de_tocarlo(self):
        js = _texto(JS / "dashboard.js")
        assert "ANIMACION_CHART_FABRICA" in js
        i_captura = js.index("const ANIMACION_CHART_FABRICA")
        i_uso = js.index("Chart.defaults.animation =")
        assert i_captura < i_uso, "se toca antes de capturar el valor original"

    def test_no_se_escribe_undefined_al_restaurar(self):
        js = _texto(JS / "dashboard.js")
        cuerpo = re.search(
            r"function aplicarPreferenciaDeMovimiento\(\)\s*\{(.*?)\n\}", js, re.S)
        assert cuerpo, "no se encuentra aplicarPreferenciaDeMovimiento"
        # Solo la LINEA DE ASIGNACION. El `typeof Chart === 'undefined'` de la
        # guarda es legitimo y mirar la funcion entera lo confundia con el
        # defecto.
        asignacion = re.search(r"Chart\.defaults\.animation\s*=([^;]*);", cuerpo.group(1))
        assert asignacion, "no se encuentra la asignacion"
        assert "undefined" not in asignacion.group(1), (
            "sigue restaurando con undefined en vez del valor capturado"
        )
        assert "ANIMACION_CHART_FABRICA" in asignacion.group(1)


class TestElCambioDePreferenciaNoRecargaLaSeccion:
    """Los DOS gates dieron con esto por separado. Recargar la seccion entera
    (a) descarta el filtro y la pagina que el operador tenia puestos, porque
    `loadTableSection` reasigna el dataset completo sin reaplicar `filterTable`,
    y (b) destruye el nodo con el foco, que cae a <body> sin aviso (SC 2.4.3).
    Las dos cosas le pasan a quien acaba de pedir MENOS movimiento."""

    def _cuerpo_listener(self):
        js = _texto(JS / "dashboard.js")
        i = js.index("MOVIMIENTO_REDUCIDO.addEventListener('change'")
        return js[i:i + 1200]

    def test_el_listener_no_llama_a_loadsection(self):
        assert "loadSection(" not in self._cuerpo_listener()

    def test_el_listener_no_invalida_el_estado_cargado(self):
        assert "state.loaded" not in self._cuerpo_listener()

    def test_las_graficas_se_actualizan_en_sitio(self):
        cuerpo = self._cuerpo_listener()
        assert ".update(" in cuerpo, "las graficas se quedarian como nacieron"
        assert "'none'" in cuerpo, "el propio cambio de preferencia se animaria"


class TestElListenerDeAnimacionNoQuedaColgado:
    def test_se_comprueba_que_la_animacion_va_a_correr(self):
        """Si una hoja anula la animacion, `animationend` no llega nunca y el
        listener `once` se queda registrado sin disparar."""
        js = _texto(JS / "dashboard.js")
        assert "animationName" in js


class TestLaCapaDeComposicionSeSuelta:
    """Hallazgo MEDIUM de `code-reviewer`. `ponerAvance` solo suelta el
    `will-change` en 0 y en 100, pero `fraccion` es monotona y el backend NO la
    normaliza a 100 al cancelar, al agotarse el presupuesto, al interrumpirse
    ni al fallar. Una busqueda cancelada al 42 % dejaba la capa reservada hasta
    la siguiente corrida."""

    def test_existe_una_forma_explicita_de_soltarla(self):
        js = _texto(JS / "importador.js")
        assert re.search(r"function soltarAvance\(\)", js)

    def test_se_suelta_en_todos_los_caminos_terminales(self):
        js = _texto(JS / "importador.js")
        cuerpo = re.search(r"function rematar\(d\)\s*\{(.*?)\nrestaurarEstado", js, re.S)
        if not cuerpo:
            cuerpo = re.search(r"function rematar\(d\)\s*\{(.*)", js, re.S)
        assert cuerpo.group(1).count("soltarAvance()") >= 2, (
            "algun camino terminal deja la capa de composicion reservada"
        )


class TestLaBarraExponeSuAvance:
    """Hallazgo HIGH de `a11y-architect` (SC 4.1.2). La barra no tenia rol ni
    valor programatico: quien usa lector no podia conocer el avance de una
    corrida que dura minutos."""

    def test_la_pista_declara_el_rol_y_el_rango(self):
        html = _texto(TPL / "importador.html")
        pista = re.search(r'<div class="progress-bar"[^>]*>', html)
        assert pista, "no se encuentra la pista de la barra"
        marca = pista.group(0)
        for attr in ('role="progressbar"', 'aria-valuemin="0"',
                     'aria-valuemax="100"', 'aria-valuenow='):
            assert attr in marca, "falta %s" % attr

    def test_la_pista_tiene_nombre_accesible(self):
        html = _texto(TPL / "importador.html")
        pista = re.search(r'<div class="progress-bar"[^>]*>', html).group(0)
        assert "aria-labelledby" in pista or "aria-label" in pista

    def test_el_js_actualiza_el_valor(self):
        js = _texto(JS / "importador.js")
        cuerpo = re.search(r"function ponerAvance\(pct\)\s*\{(.*?)\n\}", js, re.S).group(1)
        assert "aria-valuenow" in cuerpo

    def test_no_se_usa_aria_live_en_el_porcentaje(self):
        """Con sondeo cada pocos segundos durante minutos serian decenas de
        anuncios. `role=progressbar` se lee cuando el operador navega al
        control, que es lo que aqui hace falta."""
        html = _texto(TPL / "importador.html")
        pct = re.search(r'<span id="prog-pct"[^>]*>', html)
        assert pct and "aria-live" not in pct.group(0)
