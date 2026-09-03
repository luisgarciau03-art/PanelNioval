"""Plan 4 - T4.10. Accesibilidad, responsive y rendimiento, fijados.

La verificacion de verdad vive en navegador (`tools/verificar_accesibilidad.py`,
0 hallazgos en 3 superficies x 5 anchos, contra 22 antes de esta tarea). Estos
tests fijan las decisiones concretas para que no se deshagan sin enterarse.

Lo que arregla, y por que no vuelve solo:

  1. **El tablero desbordaba 461 px a 320 px.** `#sidebar` era una barra lateral
     fija de 230 px sin una sola media query, y `#main` no podia encogerse
     porque un elemento flex trae `min-width:auto`. Ahora la barra pasa a banda
     superior por debajo de 1024 px.

  2. **Tres pares de contraste fallaban, y los tres por `opacity`**, no por el
     color: `.nav-label` (blanco al 60 % sobre azul, 3.68:1), la insignia de
     envios (heredaba el 85 % de `.nav-item`, 3.61:1 sobre rojo) y `.lbl` del
     formulario (4.33:1). Ningun guarda de tokens los veia: el color declarado
     si era un token.

  3. **Ninguna de las tres superficies declaraba `<main>`**, y el tablero
     saltaba de `h1` a `h3`.

  4. **Chart.js venia de jsdelivr, en `<head>` y sin `defer`**: el tablero no
     pintaba nada hasta que el CDN contestara, y contestar le costo 15.1 s
     medidos desde esta maquina. Ademas sin `integrity`, o sea sin forma de
     comprobar que llegaba lo esperado.

  5. **El logo pesaba 44.8 KB para pintarse a 48 px.**
"""
import hashlib
import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
CSS = RAIZ / "static" / "css"
JS = RAIZ / "static" / "js"
TPL = RAIZ / "templates"
SUPERFICIES = ("dashboard", "formulario", "importador")


def _texto(ruta):
    return ruta.read_text(encoding="utf-8")


def _sin_comentarios_css(texto):
    return re.sub(r"/\*.*?\*/", "", texto, flags=re.S)


def _regla(css, selector):
    """Cuerpo de TODAS las reglas cuyo selector case exactamente, concatenado.

    Quedarse con la primera es como se pasan por alto las propiedades que viven
    en un segundo bloque del mismo selector -o en una media query-, y el test
    falla por donde esta escrito el CSS y no por lo que hace.
    """
    patron = r"(?:^|[},])\s*" + re.escape(selector) + r"\s*\{([^}]*)\}"
    cuerpos = re.findall(patron, _sin_comentarios_css(css), re.M)
    return "".join(cuerpos) if cuerpos else None


# ───────────────── responsive ───────────────────────────────────────────────

class TestElTableroSeAdaptaAPantallasEstrechas:
    """461 px de desborde a 320 px, medidos. La causa eran dos cosas a la vez:
    una barra lateral fija sin media query, y un `#main` que no podia encoger."""

    @pytest.fixture(scope="class")
    @staticmethod
    def css():
        return _texto(CSS / "dashboard.css")

    def test_main_puede_encogerse(self, css):
        """`min-width:auto` es el valor inicial de un elemento flex, y ata su
        ancho al minimo de su contenido: sin esto la media query no basta."""
        cuerpo = _regla(css, "#main")
        assert cuerpo and "min-width:0" in cuerpo.replace(" ", "")

    def test_las_cajas_de_grafica_pueden_encogerse(self, css):
        """Mismo caso, en rejilla: el <canvas> ponia suelo a su celda y el
        tablero seguia desbordando 36 px con la rejilla ya en una columna."""
        cuerpo = _regla(css, ".chart-box")
        assert cuerpo and "min-width:0" in cuerpo.replace(" ", "")

    def test_hay_una_media_query_para_la_barra_lateral(self, css):
        assert "@media (max-width: 1023px)" in css, (
            "la barra lateral vuelve a ser fija en todos los anchos"
        )

    def test_la_barra_deja_de_ser_lateral_y_el_contenido_recupera_el_ancho(self, css):
        bloque = css[css.index("@media (max-width: 1023px)"):]
        assert re.search(r"#sidebar\s*\{[^}]*position:\s*static", bloque, re.S)
        assert re.search(r"#main\s*\{[^}]*margin-left:\s*0", bloque, re.S)

    def test_el_enlace_de_salto_existe_ahora_que_la_navegacion_va_arriba(self):
        """Con la barra arriba, el teclado atraviesa 12 botones antes del
        contenido en CADA carga. El sistema ya traia el estilo del enlace desde
        la T4.4; lo que faltaba era usarlo."""
        html = _texto(TPL / "dashboard.html")
        assert 'class="saltar-al-contenido"' in html
        assert 'href="#content"' in html

    def test_las_capturas_cubren_los_cinco_anchos_de_ce10(self):
        tool = _texto(RAIZ / "tools" / "capturar_superficies.py")
        assert "ANCHOS = [320, 375, 768, 1024, 1440]" in tool, (
            "el desborde del tablero aparecia entre 768 y 1024, justo en el "
            "hueco que dejaban tres anchos"
        )


# ───────────────── contraste ────────────────────────────────────────────────

class TestElContrasteNoSeApoyaEnLaOpacidad:
    """Los tres fallos de contraste de esta tarea son del mismo tipo que el
    CRITICAL de la T4.9: el color declarado es un token y aun asi el par no pasa,
    porque la opacidad lo destruye. Es el hueco que ningun guarda de CE3 cubre."""

    def test_la_etiqueta_de_grupo_de_la_barra_no_usa_opacidad(self):
        cuerpo = _regla(_texto(CSS / "dashboard.css"), ".nav-label")
        assert cuerpo and "opacity" not in cuerpo, (
            "blanco al 60 % sobre el azul de la barra da 3.68:1"
        )
        assert "color:var(--azul-tenue)" in cuerpo.replace(" ", "")

    def test_el_boton_de_navegacion_no_atenua_a_sus_hijos(self):
        """La insignia roja de envios heredaba el 85 % del boton y quedaba en
        3.61:1. Una opacidad en el padre no se puede deshacer desde el hijo."""
        cuerpo = _regla(_texto(CSS / "dashboard.css"), ".nav-item")
        assert cuerpo and "opacity" not in cuerpo

    def test_la_etiqueta_de_la_ficha_usa_el_gris_que_pasa(self):
        cuerpo = _regla(_texto(CSS / "formulario.css"), ".info-item .lbl")
        assert cuerpo and "var(--gris-600)" in cuerpo, (
            "--texto-suave sobre --azul-tenue-2 da 4.33:1"
        )

    def test_el_auditor_mide_la_opacidad_acumulada(self):
        """Si el auditor dejara de componer la opacidad, su cero valdria lo
        mismo que el del guarda de tokens: nada."""
        tool = _texto(RAIZ / "tools" / "verificar_accesibilidad.py")
        assert "opacidadAcumulada" in tool
        assert "opacidad acumulada" in tool

    def test_el_auditor_mide_tambien_sobre_degradados(self):
        """Las cabeceras y la barra lateral son degradados. Un auditor que se
        salte el degradado deja sin medir media pantalla y sale limpio."""
        tool = _texto(RAIZ / "tools" / "verificar_accesibilidad.py")
        assert "backgroundImage" in tool and "paradas" in tool


# ───────────────── semantica ────────────────────────────────────────────────

class TestLasTresSuperficiesSonSemanticas:
    @pytest.mark.parametrize("superficie", SUPERFICIES)
    def test_cada_superficie_declara_main(self, superficie):
        html = _texto(TPL / f"{superficie}.html")
        assert re.search(r"<main[\s>]", html), "sin <main> no hay landmark de contenido"
        assert "</main>" in html

    @pytest.mark.parametrize("superficie", SUPERFICIES)
    def test_cada_superficie_tiene_exactamente_un_h1(self, superficie):
        html = _texto(TPL / f"{superficie}.html")
        assert len(re.findall(r"<h1[\s>]", html)) == 1

    def test_el_tablero_ya_no_salta_de_h1_a_h3(self):
        html = _texto(TPL / "dashboard.html")
        assert "<h3" not in html, (
            "el esquema de encabezados anunciaba un nivel h2 que no existia"
        )

    @pytest.mark.parametrize("superficie", SUPERFICIES)
    def test_toda_imagen_de_la_plantilla_tiene_alt(self, superficie):
        html = _texto(TPL / f"{superficie}.html")
        for etiqueta in re.findall(r"<img\b[^>]*>", html):
            assert "alt=" in etiqueta, etiqueta[:90]

    @pytest.mark.parametrize("superficie", SUPERFICIES)
    def test_el_logo_reserva_su_hueco(self, superficie):
        """M15 del indice: tres logos sin `width`/`height`, o sea sin reserva de
        espacio, o sea salto de layout al cargar."""
        html = _texto(TPL / f"{superficie}.html")
        logo = re.search(r"<img[^>]*cloudinary[^>]*>", html)
        assert logo, "no se encuentra el logo"
        assert "width=" in logo.group(0) and "height=" in logo.group(0)


# ───────────────── rendimiento ──────────────────────────────────────────────

class TestElPanelNoDependeDeUnCdnParaPintar:
    """Chart.js venia de jsdelivr, en `<head>` y sin `defer`. El tablero no
    pintaba nada hasta que el CDN contestara; contestar le costo **15.1 s**."""

    VENDOR = JS / "vendor" / "chart.umd.min.js"
    SHA256 = "0e2326c6868072bec1592760c6729043caeea2960a2b46cee6a2192aac6abff0"

    def test_ninguna_plantilla_carga_scripts_de_terceros(self):
        for superficie in SUPERFICIES:
            html = _texto(TPL / f"{superficie}.html")
            externos = re.findall(r'<script[^>]*src="(https?://[^"]+)"', html)
            assert not externos, f"{superficie} carga script de tercero: {externos}"

    def test_chartjs_esta_en_el_repo(self):
        assert self.VENDOR.is_file(), (
            "sin el archivo, el tablero se queda sin graficas y con un 404"
        )

    def test_el_archivo_es_exactamente_el_que_se_reviso(self):
        """Auto-hospedar quita el problema de SRI cambiando de sitio el
        control: ya no hay que confiar en un tercero, pero si hay que poder
        demostrar que el archivo del repo es el que se descargo y se reviso."""
        digest = hashlib.sha256(self.VENDOR.read_bytes()).hexdigest()
        assert digest == self.SHA256, (
            "el Chart.js del repo NO es el revisado (sha256 %s)" % digest[:16]
        )

    def test_el_guarda_del_hash_detecta_un_cambio(self):
        """Control negativo, sobre un literal del propio test."""
        assert hashlib.sha256(b"otro contenido").hexdigest() != self.SHA256

    def test_se_carga_antes_del_script_que_lo_usa(self):
        """Con `defer` correria DESPUES de dashboard.js, que no lo difiere, y
        `Chart` estaria sin definir justo cuando el tablero lo consulta."""
        html = _texto(TPL / "dashboard.html")
        i_chart = html.index("vendor/chart.umd.min.js")
        i_dash = html.index("js/dashboard.js")
        assert i_chart < i_dash
        etiqueta = re.search(r"<script[^>]*vendor/chart[^>]*>", html).group(0)
        assert "defer" not in etiqueta and "async" not in etiqueta

    def test_ningun_script_de_tercero_bloquea_la_cabecera(self):
        for superficie in SUPERFICIES:
            html = _texto(TPL / f"{superficie}.html")
            cabecera = html[:html.index("</head>")]
            assert "<script" not in cabecera, (
                f"{superficie} vuelve a bloquear el render desde <head>"
            )

    @pytest.mark.parametrize("superficie", SUPERFICIES)
    def test_el_logo_se_pide_del_tamano_que_se_pinta(self, superficie):
        """44.8 KB para pintarse a 48 px. Con la transformacion de Cloudinary
        son 0.6 KB, y el asset sigue siendo el del owner."""
        html = _texto(TPL / f"{superficie}.html")
        logo = re.search(r"<img[^>]*cloudinary[^>]*>", html).group(0)
        assert "w_96" in logo and "f_auto" in logo, logo[:120]


# ───────────── lo que encontraron los gates de la T4.10 ────────────────────

class TestLoQueEncontraronLosGates:
    """`a11y-architect` y `accessibility-tester` corrieron en paralelo. El
    primero encontró el fallo que importa: **el auditor sólo miraba UN estado
    por superficie**, así que cualquier defecto confinado a una sección que no
    fuera la inicial, o a un modal, era invisible por diseño. Al recorrer los
    estados aparecieron 36 hallazgos donde antes había 0."""

    def test_el_auditor_recorre_las_secciones_y_los_dialogos(self):
        tool = _texto(RAIZ / "tools" / "verificar_accesibilidad.py")
        assert "_auditar_todos_los_estados" in tool
        assert "data-seccion" in tool, "no activa las secciones del tablero"
        assert 'role="dialog"' in tool, "no abre los dialogos"

    def test_las_pestanas_de_seguimiento_son_botones(self):
        """CRITICAL. Eran `<div onclick>`: mismo defecto que la T4.7 corrigió en
        la navegación, sobrevivió aquí porque vive en una sección que el
        auditor nunca activaba."""
        js = _texto(JS / "dashboard.js")
        assert 'role="tab"' in js and "seg-tab" in js
        assert '<div class="seg-tab' not in js

    def test_el_selector_de_color_son_botones(self):
        """CRITICAL. Igual, dentro de un modal que nunca se abría."""
        js = _texto(JS / "dashboard.js")
        assert 'role="radio"' in js
        assert '<div class="color-opt' not in js

    def test_la_casilla_de_bruce_es_un_interruptor(self):
        js = _texto(JS / "dashboard.js")
        assert 'role="switch"' in js
        assert "setAttribute('aria-checked'" in js, (
            "cambia el emoji pero no el estado que lee un lector"
        )

    def test_la_tabla_de_ciudades_ordena_con_un_boton(self):
        """Once tablas usaban botón desde la T4.7; ésta se quedó con el
        `<th onclick>`."""
        js = _texto(JS / "dashboard.js")
        assert 'onclick="sortCiudades(' in js
        assert '<th style="cursor:pointer;white-space:nowrap" onclick' not in js

    # Los siete dialogos, por id. Se listan a proposito en vez de buscarlos por
    # patron: `edit-modal-title` es un TITULO, no un dialogo, y un patron laxo
    # sobre "modal" lo arrastraba. Si aparece un octavo, lo caza el auditor en
    # navegador, que mira posicion fija y no el nombre del id.
    DIALOGOS = {
        "dashboard": ("modal-corregir-cat", "edit-seg-modal", "modal-upload", "modal-imagen"),
        "formulario": ("modal-catalogo", "modal-correo", "modal-validar-catalogo"),
    }

    @pytest.mark.parametrize("superficie", ("dashboard", "formulario"))
    def test_los_dialogos_se_anuncian_como_dialogos(self, superficie):
        html = _texto(TPL / f"{superficie}.html")
        for ident in self.DIALOGOS[superficie]:
            etiqueta = re.search(r'<div id="%s"[^>]*>' % re.escape(ident), html)
            assert etiqueta, f"no se encuentra {ident}"
            assert 'role="dialog"' in etiqueta.group(0), etiqueta.group(0)[:90]
            assert 'aria-modal="true"' in etiqueta.group(0)
            assert "aria-label" in etiqueta.group(0)

    @pytest.mark.parametrize("superficie", ("dashboard", "formulario"))
    def test_todo_dialogo_modal_tiene_salida_por_teclado(self, superficie):
        """Una trampa de foco sin salida es PEOR que no tener trampa: es un
        incumplimiento de SC 2.1.2 (sin trampa de teclado)."""
        html = _texto(TPL / f"{superficie}.html")
        for ident in self.DIALOGOS[superficie]:
            i = html.index('<div id="%s"' % ident)
            # Hasta el siguiente dialogo, o hasta el final.
            siguientes = [html.index('<div id="%s"' % o) for o in self.DIALOGOS[superficie]
                          if html.index('<div id="%s"' % o) > i]
            bloque = html[i:min(siguientes)] if siguientes else html[i:]
            assert "data-cerrar" in bloque, f"{ident} atrapa el foco sin salida"

    def test_el_modulo_de_dialogos_devuelve_el_foco(self):
        js = _texto(JS / "dialogo.js")
        assert "focoPrevio" in js and "atrapar" in js and "Escape" in js

    def test_los_campos_de_filtro_tienen_nombre(self):
        """22 campos con `placeholder` y nada más. El placeholder desaparece al
        escribir y no todos los lectores lo anuncian: no es una etiqueta."""
        for superficie, minimo in (("dashboard", 20), ("formulario", 2)):
            html = _texto(TPL / f"{superficie}.html")
            assert html.count("aria-label=") >= minimo, superficie

    def test_las_graficas_tienen_nombre_accesible(self):
        html = _texto(TPL / "dashboard.html")
        assert html.count('role="img"') == 6
        js = _texto(JS / "dashboard.js")
        assert "describirGrafica" in js, (
            "el nombre estatico dice que hay una grafica; las CIFRAS son lo que "
            "la hace util para quien no la ve"
        )

    def test_el_auditor_exime_lo_que_wcag_exime(self):
        """Un control deshabilitado no tiene requisito de contraste (1.4.3). Sin
        la exención, cada botón deshabilitado sale CRITICO y entierra los
        hallazgos de verdad."""
        tool = _texto(RAIZ / "tools" / "verificar_accesibilidad.py")
        assert ":disabled" in tool
        assert "aria-disabled" in tool

    def test_el_auditor_comprueba_el_destino_del_enlace_de_salto(self):
        tool = _texto(RAIZ / "tools" / "verificar_accesibilidad.py")
        assert "WCAG 2.4.1" in tool

    def test_el_auditor_mide_el_tamano_del_objetivo(self):
        tool = _texto(RAIZ / "tools" / "verificar_accesibilidad.py")
        assert "2.5.8" in tool and "24" in tool

    @pytest.mark.parametrize("superficie", SUPERFICIES)
    def test_el_destino_del_enlace_de_salto_recibe_foco(self, superficie):
        """Sin `tabindex="-1"` el navegador desplaza pero no emite evento de
        foco: para un lector el salto es un scroll silencioso."""
        html = _texto(TPL / f"{superficie}.html")
        salto = re.search(r'<a class="saltar-al-contenido" href="#([^"]+)"', html)
        if not salto:
            pytest.skip("esta superficie no tiene enlace de salto")
        destino = salto.group(1)
        etiqueta = re.search(r'id="%s"[^>]*' % re.escape(destino), html).group(0)
        assert 'tabindex="-1"' in etiqueta, etiqueta[:80]
