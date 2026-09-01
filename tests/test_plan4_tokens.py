"""Plan 4 - T4.4. El sistema de tokens, fijado.

Tres cosas que se deshacen solas si nadie las vigila:

  1. **CE3**: ningun color literal fuera de `tokens.css`. El CSS original tenia
     288 repartidos por tres capas, y `--blue` estaba declarada tres veces
     mientras `#0047cc` aparecia 17 veces escrito a mano.
  2. **Contraste**: los ratios que `tokens.css` declara en sus comentarios son
     ciertos. El verde de marca daba 2.16:1 y asi estaba construido el boton
     "Aprobado" del formulario; si alguien "ajusta" un token y rompe AA, esto
     se pone en rojo en vez de enterarnos en produccion.
  3. **Tokens fantasma**: un `var(--nombre-mal-escrito)` no falla en ninguna
     parte. El navegador se queda sin valor y el elemento hereda o se queda
     transparente, en silencio.
"""
import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
CSS = RAIZ / "static" / "css"
TOKENS = CSS / "tokens.css"

RE_HEX = re.compile(r"#[0-9a-fA-F]{3,8}\b")
# Una definicion es `--nombre:`. NO se ancla a principio de linea: el CSS de las
# superficies esta minificado en una sola linea y tokens.css agrupa varias
# declaraciones por linea, asi que un ancla `^` solo veria la primera de cada
# una. Los usos `var(--x)` no llevan dos puntos detras, asi que no casan aqui.
RE_DEF = re.compile(r"(--[a-z0-9-]+)\s*:")
RE_USO = re.compile(r"var\(\s*(--[a-z0-9-]+)")


# ─────────────────────────── contraste WCAG 2.2 ───────────────────────────

def _canal(c: float) -> float:
    c /= 255.0
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def _luminancia(hexv: str) -> float:
    h = hexv.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _canal(r) + 0.7152 * _canal(g) + 0.0722 * _canal(b)


def contraste(a: str, b: str) -> float:
    la, lb = _luminancia(a), _luminancia(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def _tokens() -> dict[str, str]:
    """Nombre -> valor hex, resolviendo un nivel de alias var(--otro)."""
    texto = TOKENS.read_text(encoding="utf-8")
    crudos = dict(re.findall(r"(--[a-z0-9-]+)\s*:\s*([^;]+);", texto))
    resueltos = {}
    for nombre, valor in crudos.items():
        valor = valor.strip()
        m = RE_USO.match(valor)
        if m:
            valor = crudos.get(m.group(1), "").strip()
        if RE_HEX.fullmatch(valor):
            resueltos[nombre] = valor
    return resueltos


class TestElPatronDeContrasteFunciona:
    """Antes de creerle un veredicto, comprobar que sabe distinguir."""

    def test_casos_conocidos(self):
        assert contraste("#000000", "#ffffff") == pytest.approx(21.0, abs=.01)
        assert contraste("#ffffff", "#ffffff") == pytest.approx(1.0, abs=.01)
        # El verde de marca, el caso que motivo todo esto.
        assert contraste("#00CC47", "#ffffff") == pytest.approx(2.16, abs=.01)


class TestCE3SinColoresLiterales:
    @pytest.mark.parametrize("archivo", [
        "base.css", "componentes.css", "dashboard.css", "formulario.css", "importador.css",
    ])
    def test_ningun_hex_fuera_de_tokens(self, archivo):
        texto = (CSS / archivo).read_text(encoding="utf-8")
        # Los comentarios documentan valores a proposito; se ignoran.
        sin_comentarios = re.sub(r"/\*.*?\*/", "", texto, flags=re.S)
        hallazgos = RE_HEX.findall(sin_comentarios)
        assert not hallazgos, f"{archivo} tiene colores literales: {sorted(set(hallazgos))}"

    def test_tokens_css_si_los_tiene(self):
        """Control negativo: si este saliera vacio, el test de arriba estaria
        pasando porque no sabe mirar, no porque no haya colores."""
        assert len(RE_HEX.findall(TOKENS.read_text(encoding="utf-8"))) > 20

    @pytest.mark.parametrize("superficie", ["dashboard", "formulario", "importador"])
    def test_ningun_hex_en_las_plantillas(self, superficie):
        """El marcado tenia 70 colores en atributos `style=`."""
        texto = (RAIZ / "templates" / f"{superficie}.html").read_text(encoding="utf-8")
        hallazgos = RE_HEX.findall(texto)
        assert not hallazgos, f"{superficie}.html: {sorted(set(hallazgos))}"

    def test_el_js_solo_conserva_las_paletas_de_datos(self):
        """De 288 literales en todo el frontend quedan 31, todos en
        `dashboard.js` y todos de las DOS paletas de datos: las series de
        Chart.js y el selector de color de fila que usa el operador.

        Se dejan a proposito: la T4.7 punto 3 pide meter las graficas dentro del
        sistema de diseno, y eso es rehacerlas, no renombrarles el color. Este
        test fija el saldo para que nadie anada un literal nuevo por el camino.
        """
        for nombre in ("formulario", "importador"):
            texto = (CSS.parent / "js" / f"{nombre}.js").read_text(encoding="utf-8")
            assert not RE_HEX.findall(texto), f"{nombre}.js ya no deberia tener colores"

        texto = (CSS.parent / "js" / "dashboard.js").read_text(encoding="utf-8")
        hallazgos = RE_HEX.findall(texto)
        assert len(hallazgos) <= 31, (
            f"dashboard.js subio a {len(hallazgos)} colores literales. Los 31 que "
            "quedan son las paletas de datos; cualquier otro va como token."
        )


class TestLosParesQueDeVerdadSeUsan:
    """Comprobar los tokens uno a uno no basta.

    `--texto-suave` esta documentado como "el mas claro que aun pasa AA", y es
    cierto **sobre blanco**: 4.76:1. Pero el badge de cache del dashboard lo
    ponia sobre `--gris-100` y ahi baja a 4.34:1, por debajo de AA. El token
    estaba bien; el par estaba mal.

    Esto recorre las reglas de verdad y saca los pares `color` + `background`
    que conviven en la misma regla.
    """

    EXENTOS = (":disabled", "[disabled]", "[aria-disabled")

    def _tabla_de_color(self, texto_superficie: str) -> dict[str, str]:
        crudo = dict(re.findall(r"(--[a-z0-9-]+)\s*:\s*([^;]+);",
                                TOKENS.read_text(encoding="utf-8")))

        def resolver(valor, prof=0):
            valor = valor.strip()
            if prof > 5:
                return None
            m = RE_USO.match(valor)
            if m:
                return resolver(crudo.get(m.group(1), ""), prof + 1)
            return valor if RE_HEX.fullmatch(valor) else None

        tabla = {k: v for k, v in ((k, resolver(v)) for k, v in crudo.items()) if v}
        # alias locales del :root de la superficie (--blue -> var(--azul) ...)
        m = re.search(r":root\{([^}]*)\}", texto_superficie)
        if m:
            for nombre, valor in re.findall(r"(--[a-z0-9-]+)\s*:\s*([^;}]+)", m.group(1)):
                mm = RE_USO.match(valor.strip())
                if mm and mm.group(1) in tabla:
                    tabla[nombre] = tabla[mm.group(1)]
        return tabla

    @pytest.mark.parametrize("archivo", [
        "base.css", "componentes.css", "dashboard.css", "formulario.css", "importador.css",
    ])
    def test_todo_par_color_fondo_pasa_aa(self, archivo):
        texto = re.sub(r"/\*.*?\*/", "", (CSS / archivo).read_text(encoding="utf-8"), flags=re.S)
        tabla = self._tabla_de_color(texto)
        fallos = []
        for m in re.finditer(r"([^{}]+)\{([^}]*)\}", texto):
            selector, cuerpo = m.group(1).strip(), m.group(2)
            # WCAG 1.4.11 excluye los componentes inactivos del requisito.
            if any(x in selector for x in self.EXENTOS):
                continue
            c = re.search(r"(?:^|;)\s*color\s*:\s*var\(\s*(--[a-z0-9-]+)", cuerpo)
            b = re.search(r"(?:^|;)\s*background(?:-color)?\s*:\s*var\(\s*(--[a-z0-9-]+)", cuerpo)
            if not (c and b):
                continue
            hc, hb = tabla.get(c.group(1)), tabla.get(b.group(1))
            if not (hc and hb):
                continue
            r = contraste(hc, hb)
            if r < 4.5:
                fallos.append(f"{selector[:50]}: {c.group(1)} sobre {b.group(1)} = {r:.2f}:1")
        assert not fallos, f"{archivo}, pares por debajo de AA:\n  " + "\n  ".join(fallos)

    def test_el_escaner_ve_el_caso_que_se_colo(self):
        """Control positivo: el par exacto que fallaba en el badge de cache."""
        assert contraste("#64748b", "#f1f5f9") < 4.5
        assert contraste("#475569", "#f1f5f9") >= 4.5


class TestElFocoSeVeSobreCualquierFondo:
    """Un anillo de un solo color no vale. `--azul` daba 7.57:1 sobre blanco
    pero 1.43:1 sobre el azul oscuro de la barra lateral, o sea invisible justo
    donde el operador navega con teclado. Con dos anillos concentricos basta con
    que uno pase 3:1 en cada fondo.
    """

    FONDOS = ["--blanco", "--gris-100", "--azul", "--azul-oscuro",
              "--azul-cian", "--gris-900", "--exito", "--error"]

    @pytest.mark.parametrize("fondo", FONDOS)
    def test_uno_de_los_dos_anillos_se_ve(self, fondo):
        t = _tokens()
        oscuro, claro = t["--gris-900"], t["--blanco"]
        f = t[fondo]
        mejor = max(contraste(oscuro, f), contraste(claro, f))
        assert mejor >= 3.0, f"el anillo de foco no se ve sobre {fondo}: {mejor:.2f}:1"

    def test_un_anillo_de_un_solo_color_no_habria_bastado(self):
        """Control en la otra direccion: si esto empezara a pasar, el test de
        arriba no estaria demostrando que hacian falta dos anillos."""
        t = _tokens()
        assert contraste(t["--azul"], t["--azul-oscuro"]) < 3.0

    def test_base_css_declara_los_dos_anillos(self):
        base = (CSS / "base.css").read_text(encoding="utf-8")
        assert "--foco-oscuro" in base and "--foco-claro" in base
        assert "forced-colors" in base, "falta el modo de alto contraste de Windows"


class TestNoQuedaCssRotoPorLaMigracion:
    """La migracion a tokens se hizo con sustitucion de texto, y eso tiene una
    trampa: `#fff` es PREFIJO de `#fff3cd`. Sustituir el primero dejo
    `background:var(--superficie)3cd`, que no es un valor valido -- el parser
    descarta la declaracion entera y la etiqueta se queda sin fondo.

    No lo veia ningun test: `RE_HEX` solo busca literales que empiecen por `#`,
    y en cuanto el reemplazo deja basura sin `#`, se vuelve invisible.
    """

    RE_RESTO = re.compile(r"var\(--[a-z0-9-]+\)[0-9a-fA-F]")

    @pytest.mark.parametrize("archivo", [
        "base.css", "componentes.css", "dashboard.css", "formulario.css",
        "importador.css", "tokens.css",
    ])
    def test_ningun_var_pegado_a_restos_de_hex(self, archivo):
        texto = (CSS / archivo).read_text(encoding="utf-8")
        hallazgos = self.RE_RESTO.findall(texto)
        assert not hallazgos, f"{archivo}: declaracion rota, {hallazgos}"

    def test_tambien_en_plantillas_y_js(self):
        problemas = []
        for ruta in list((RAIZ / "templates").glob("*.html")) + list((CSS.parent / "js").glob("*.js")):
            for n, linea in enumerate(ruta.read_text(encoding="utf-8").splitlines(), 1):
                if self.RE_RESTO.search(linea):
                    problemas.append(f"{ruta.name}:{n}")
        assert not problemas, f"declaraciones rotas en {problemas}"

    def test_el_patron_encuentra_el_caso_real(self):
        """Control positivo con el defecto exacto que se colo."""
        assert self.RE_RESTO.search("background:var(--superficie)3cd")
        assert not self.RE_RESTO.search("background:var(--buzon-banda)")


class TestSinColisionesConElSistema:
    """Un componente compartido que una superficie redefine con el mismo nombre
    deja de estar enlazado al sistema, y nadie se entera: no hay error, solo un
    `.chip` que ignora los cambios del diseno. Peor todavia cuando el pisado es
    PARCIAL -- `.stat` en el formulario solo redeclaraba `text-align`, asi que
    heredaba fondo, borde y padding del componente y pintaba una tarjeta dentro
    de otra.
    """

    @pytest.mark.parametrize("superficie", ["dashboard", "formulario", "importador"])
    def test_ninguna_superficie_redefine_un_componente(self, superficie):
        def clases_base(texto: str) -> set[str]:
            """Clases cuyo selector es EXACTAMENTE `.nombre`.

            Se compara el selector entero, no un fragmento: `.btn-group .btn`
            es un override contextual (uso normal de la cascada) y
            `.btn:active` una extension de estado. La colision danina es
            redeclarar la base, porque hereda A MEDIAS del componente --
            como `.stat{text-align:center}`, que solo pisaba una propiedad y
            se quedaba con el fondo, el borde y el padding de la tarjeta,
            pintando una tarjeta dentro de otra.
            """
            nombres = set()
            for m in re.finditer(r"([^{}]+)\{[^}]*\}", texto):
                for sel in m.group(1).split(","):
                    sel = sel.strip()
                    if re.fullmatch(r"\.[a-z][a-z0-9-]*", sel):
                        nombres.add(sel[1:])
            return nombres

        del_sistema = clases_base((CSS / "componentes.css").read_text(encoding="utf-8"))
        de_la_superficie = clases_base((CSS / f"{superficie}.css").read_text(encoding="utf-8"))
        choques = sorted(del_sistema & de_la_superficie)
        assert not choques, (
            f"{superficie}.css redefine componentes del sistema: {choques}. "
            "Dale nombre propio a lo local o consume el componente compartido."
        )


class TestNoHayTokensFantasma:
    @staticmethod
    def _sin_comentarios(texto: str) -> str:
        """Los comentarios se descartan (correccion de la T4.6).

        El barrido miraba el archivo entero, asi que un comentario que
        EXPLICABA el propio patron se contaba como uso real y ponia el test en
        rojo. Un guarda que se dispara con su propia documentacion acaba
        desactivado por quien viene detras.
        """
        return re.sub(r"/\*.*?\*/", "", texto, flags=re.S)

    def test_todo_var_usado_esta_definido(self):
        definidos = set(RE_DEF.findall(self._sin_comentarios(
            TOKENS.read_text(encoding="utf-8"))))
        problemas = []
        for archivo in CSS.glob("*.css"):
            texto = self._sin_comentarios(archivo.read_text(encoding="utf-8"))
            propios = set(RE_DEF.findall(texto))
            for usado in RE_USO.findall(texto):
                if usado not in definidos and usado not in propios:
                    problemas.append(f"{archivo.name}: var({usado})")
        assert not problemas, "variables usadas y nunca definidas:\n  " + "\n  ".join(sorted(set(problemas)))

    def test_el_barrido_sigue_viendo_un_fantasma_real(self):
        """Control negativo: descartar comentarios no puede haber apagado el
        guarda. Sobre codigo -no sobre comentario- tiene que seguir viendolo."""
        muestra = "/* var(--solo-un-comentario) */" + chr(10) + ".x { color: var(--no-existe-jamas); }"
        usados = set(RE_USO.findall(self._sin_comentarios(muestra)))
        assert "--no-existe-jamas" in usados
        assert "--solo-un-comentario" not in usados


class TestContrasteDeLosTokens:
    """Los ratios que tokens.css declara tienen que ser ciertos."""

    def test_texto_sobre_blanco_pasa_aa(self):
        t = _tokens()
        for nombre in ("--gris-900", "--gris-800", "--gris-700", "--gris-600", "--gris-500"):
            r = contraste(t[nombre], "#ffffff")
            assert r >= 4.5, f"{nombre} ({t[nombre]}) da {r:.2f}:1 sobre blanco"

    def test_los_colores_de_estado_pasan_con_texto_blanco_encima(self):
        """Son fondos de boton con texto blanco. El ratio es simetrico, asi que
        esto cubre tambien su uso como texto sobre blanco."""
        t = _tokens()
        for nombre in ("--exito", "--aviso", "--error", "--azul", "--marca-unica"):
            r = contraste("#ffffff", t[nombre])
            assert r >= 4.5, f"{nombre} ({t[nombre]}) da {r:.2f}:1 con texto blanco"

    def test_los_vivos_siguen_fallando_y_por_eso_no_llevan_texto(self):
        """Control en la otra direccion: si alguno de estos empezara a pasar,
        el test de arriba no estaria probando nada."""
        t = _tokens()
        for nombre in ("--exito-vivo", "--aviso-vivo", "--error-vivo"):
            r = contraste("#ffffff", t[nombre])
            assert r < 4.5, (
                f"{nombre} ya pasa AA ({r:.2f}:1): usalo como color normal y "
                "retira la advertencia de tokens.css"
            )

    @pytest.mark.parametrize("texto,fondo", [
        ("--aprobado-fuerte", "--aprobado-banda"),
        ("--buzon-fuerte", "--buzon-banda"),
        ("--negado-fuerte", "--negado-banda"),
        ("--incompat-fuerte", "--incompat-banda"),
        ("--marca-unica-fuerte", "--marca-unica-banda"),
    ])
    def test_cada_estado_de_llamada_es_legible_sobre_su_banda(self, texto, fondo):
        t = _tokens()
        r = contraste(t[texto], t[fondo])
        assert r >= 4.5, f"{texto} sobre {fondo} da {r:.2f}:1"

    def test_el_borde_de_control_cumple_el_minimo_no_textual(self):
        """WCAG 1.4.11: un borde que delimita un campo necesita 3:1 contra el
        fondo. El #ccd anterior daba 1.4:1."""
        t = _tokens()
        r = contraste(t["--borde-control"], "#ffffff")
        assert r >= 3.0, f"--borde-control da {r:.2f}:1"

    def test_el_anillo_de_foco_se_ve(self):
        t = _tokens()
        assert contraste(t["--azul"], "#ffffff") >= 3.0

    def test_la_consola_es_legible(self):
        t = _tokens()
        r = contraste(t["--consola-texto"], t["--gris-900"])
        assert r >= 4.5, f"la consola da {r:.2f}:1"


class TestElSistemaEstaEnlazado:
    @pytest.mark.parametrize("superficie", ["dashboard", "formulario", "importador"])
    def test_las_tres_superficies_cargan_tokens_base_y_componentes(self, superficie):
        html = (RAIZ / "templates" / f"{superficie}.html").read_text(encoding="utf-8")
        for hoja in ("tokens", "base", "componentes"):
            assert f"css/{hoja}.css" in html, f"{superficie}.html no enlaza {hoja}.css"

    @pytest.mark.parametrize("superficie", ["dashboard", "formulario", "importador"])
    def test_los_tokens_van_antes_que_el_css_de_la_superficie(self, superficie):
        """La cascada importa: si la superficie carga primero, sus reglas
        pierden contra las genericas y el sistema se aplica al reves."""
        html = (RAIZ / "templates" / f"{superficie}.html").read_text(encoding="utf-8")
        assert html.index("css/tokens.css") < html.index(f"css/{superficie}.css")
        assert html.index("css/componentes.css") < html.index(f"css/{superficie}.css")


class TestReducedMotion:
    def test_tokens_respeta_la_preferencia_del_sistema(self):
        """Accesibilidad, no preferencia. El CSS original no la respetaba en
        ningun sitio."""
        texto = TOKENS.read_text(encoding="utf-8")
        assert "prefers-reduced-motion" in texto
