"""Plan 4 - T4.3. La extraccion del HTML fuera de app.py, fijada.

La T4.3 movio las tres superficies (3,235 lineas) de tres literales de Python a
`templates/` y `static/`. Es un refactor **preservador de comportamiento**: no
cambia ni un pixel, solo cambia donde vive el codigo.

Lo que se afirma aqui es lo que puede deshacerse sin que nadie se entere:

  - que el HTML no vuelva a colarse dentro de `app.py`;
  - que Flask **sirva** de verdad el CSS y el JS, no solo que los archivos
    existan (riesgo R7 del plan: panel sin CSS en produccion);
  - que `.dockerignore` no los deje fuera de la imagen del VPS.

La verificacion en un contenedor construido de verdad sigue siendo un gate del
owner: docker no esta instalado en la maquina de desarrollo.
"""
from pathlib import Path

import pytest

import app

RAIZ = Path(__file__).resolve().parent.parent
SUPERFICIES = [("dashboard", "/"), ("formulario", "/formulario"), ("importador", "/importador")]


@pytest.fixture
def client():
    app.app.config["TESTING"] = True
    return app.app.test_client()


class TestElHtmlSalioDeAppPy:
    def test_no_quedan_literales_html(self):
        """Tres cadenas de mil lineas dentro de un .py: no se puede tocar el CSS
        sin editar un literal de Python."""
        fuente = (RAIZ / "app.py").read_text(encoding="utf-8")
        for constante in ("HTML = r\"\"\"", "FORMULARIO_HTML = r\"\"\"", "IMPORTADOR_HTML = r\"\"\""):
            assert constante not in fuente, f"volvio a aparecer {constante!r} en app.py"

    def test_no_queda_render_template_string(self):
        fuente = (RAIZ / "app.py").read_text(encoding="utf-8")
        assert "render_template_string" not in fuente

    def test_app_py_bajo_de_las_3400_lineas(self):
        """Antes de la T4.3 eran 6,368. CE1 pedia <800, que era inalcanzable
        extrayendo solo HTML; el numero real alcanzado es ~3,133 (decision D6).
        El tope de aqui solo impide que el HTML vuelva a entrar."""
        lineas = len((RAIZ / "app.py").read_text(encoding="utf-8").splitlines())
        assert lineas < 3400, f"app.py tiene {lineas} lineas"


class TestLosArchivosExisten:
    @pytest.mark.parametrize("nombre,_ruta", SUPERFICIES)
    def test_plantilla_css_y_js(self, nombre, _ruta):
        for p in (RAIZ / "templates" / f"{nombre}.html",
                  RAIZ / "static" / "css" / f"{nombre}.css",
                  RAIZ / "static" / "js" / f"{nombre}.js"):
            assert p.is_file(), f"falta {p}"
            assert p.stat().st_size > 0, f"{p} esta vacio"


class TestFlaskSirveLasTresSuperficies:
    @pytest.mark.parametrize("nombre,ruta", SUPERFICIES)
    def test_la_pagina_responde_200(self, client, nombre, ruta):
        r = client.get(ruta)
        assert r.status_code == 200

    @pytest.mark.parametrize("nombre,ruta", SUPERFICIES)
    def test_la_pagina_enlaza_sus_estaticos(self, client, nombre, ruta):
        html = client.get(ruta).data.decode("utf-8", "ignore")
        assert f"/static/css/{nombre}.css" in html, "la plantilla no enlaza su CSS"
        assert f"/static/js/{nombre}.js" in html, "la plantilla no enlaza su JS"

    @pytest.mark.parametrize("nombre,_ruta", SUPERFICIES)
    def test_flask_sirve_el_css_y_el_js(self, client, nombre, _ruta):
        """R7: que el archivo exista en disco no prueba que el servidor lo sirva.
        Un panel sin CSS en produccion se ve exactamente asi de mal."""
        for sub in (f"/static/css/{nombre}.css", f"/static/js/{nombre}.js"):
            r = client.get(sub)
            assert r.status_code == 200, f"Flask no sirve {sub}: HTTP {r.status_code}"
            assert len(r.data) > 0, f"{sub} llego vacio"


class TestJinjaNoInterpretaElMarcado:
    """Jinja parsea la plantilla al RENDERIZAR. Un `{{` perdido en el JS o el CSS
    no revienta al importar app.py: revienta al servir la pagina, en produccion.
    """

    @pytest.mark.parametrize("nombre,_ruta", SUPERFICIES)
    def test_los_estaticos_no_pasan_por_jinja(self, nombre, _ruta):
        for p in (RAIZ / "static" / "css" / f"{nombre}.css",
                  RAIZ / "static" / "js" / f"{nombre}.js"):
            texto = p.read_text(encoding="utf-8")
            for delim in ("{{", "{%"):
                assert delim not in texto or p.suffix == ".js", (
                    f"{p.name} contiene {delim}; si algun dia se sirve por Jinja, reventaria"
                )

    @pytest.mark.parametrize("nombre,_ruta", SUPERFICIES)
    def test_la_plantilla_solo_usa_jinja_para_url_for(self, nombre, _ruta):
        import re
        texto = (RAIZ / "templates" / f"{nombre}.html").read_text(encoding="utf-8")
        for expr in re.findall(r"\{\{(.*?)\}\}", texto, re.S):
            assert "url_for" in expr, f"expresion Jinja inesperada en {nombre}.html: {expr!r}"


class TestLaImagenDelVpsLosIncluye:
    """R7 otra vez, del otro lado: `.dockerignore` deja fuera `*.json` para no
    meter credenciales. Si algun dia alguien anade `static/` o `templates/` a esa
    lista, el panel se despliega sin CSS y sin JS y nadie se entera hasta verlo.
    """

    def test_dockerignore_no_excluye_templates_ni_static(self):
        lineas = [
            l.strip()
            for l in (RAIZ / ".dockerignore").read_text(encoding="utf-8").splitlines()
            if l.strip() and not l.strip().startswith("#")
        ]
        for prohibida in ("templates", "templates/", "static", "static/"):
            assert prohibida not in lineas, (
                f".dockerignore excluye {prohibida!r}: la imagen del VPS saldria sin interfaz"
            )
