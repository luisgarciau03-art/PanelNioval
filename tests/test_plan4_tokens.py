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


class TestNoHayTokensFantasma:
    def test_todo_var_usado_esta_definido(self):
        definidos = set(RE_DEF.findall(TOKENS.read_text(encoding="utf-8")))
        problemas = []
        for archivo in CSS.glob("*.css"):
            texto = archivo.read_text(encoding="utf-8")
            propios = set(RE_DEF.findall(texto))
            for usado in RE_USO.findall(texto):
                if usado not in definidos and usado not in propios:
                    problemas.append(f"{archivo.name}: var({usado})")
        assert not problemas, "variables usadas y nunca definidas:\n  " + "\n  ".join(sorted(set(problemas)))


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
