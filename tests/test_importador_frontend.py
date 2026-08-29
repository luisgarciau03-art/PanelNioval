"""Robustez del importador de cara al operador (Plan 3 - T3.7).

Defectos B7, B8, B9, mas la mitad de cliente de B10 y los B12/B13 que encontro
el recorrido de rutas de clic.

El JS vive embebido en `IMPORTADOR_HTML` dentro de app.py y el proyecto no tiene
infraestructura de pruebas de navegador, asi que lo que se puede afirmar desde
aqui son dos cosas distintas y las dos utiles:

  - el comportamiento de SERVIDOR (cancelar, restaurar estado), con el cliente
    de pruebas de Flask, que es comportamiento real;
  - la presencia o ausencia de patrones concretos en el JS servido, que es lo
    mismo que ya hace `TestMensajeFinal` en test_importador_conteo.py.

La verificacion en navegador de verdad queda anotada como gate en T3.8.
"""
import pytest

import app


@pytest.fixture
def client():
    app.app.config["TESTING"] = True
    return app.app.test_client()


@pytest.fixture
def html():
    return app.IMPORTADOR_HTML


# ───────────────── B7 · recargar no puede perder el trabajo ─────────────────

class TestRestauraAlCargar:
    def test_el_js_consulta_el_estado_al_cargar(self, html):
        """Solo `iniciar()` arrancaba el sondeo.

        Si el operador recargaba /importador a media corrida, la pagina aparecia
        inerte: sin barra, sin log, sin stats. Y al volver a pulsar Buscar
        recibia "Ya hay una busqueda en curso", encerrado fuera de su trabajo.
        """
        assert "restaurarEstado" in html, (
            "no hay ninguna restauracion de estado al cargar la pagina"
        )
        assert "restaurarEstado()" in html, "restaurarEstado se define pero no se llama"

    def test_restaurar_arranca_el_sondeo_si_hay_trabajo(self, html):
        i = html.index("function restaurarEstado")
        cuerpo = html[i:i + 1200]
        assert "'running'" in cuerpo or '"running"' in cuerpo, (
            "restaurarEstado no distingue un trabajo en curso"
        )
        assert "arrancarSondeo" in cuerpo or "setInterval" in cuerpo, (
            "restaurarEstado no vuelve a enganchar el sondeo"
        )


# ─────────── B8 · el boton no se queda trabado y el sondeo termina ───────────

class TestSondeoYBoton:
    def test_las_dos_llamadas_tienen_try_catch(self, html):
        for fn in ("async function iniciar", "async function actualizarEstado"):
            i = html.index(fn)
            cuerpo = html[i:i + 2500]
            assert "try {" in cuerpo and "catch" in cuerpo, (
                "%s sigue sin try/catch: un fallo de red deja el boton trabado" % fn
            )

    def test_el_fallo_de_red_rehabilita_el_boton(self, html):
        i = html.index("async function iniciar")
        cuerpo = html[i:i + 2500]
        catch = cuerpo[cuerpo.index("catch"):]
        # Vale cualquier forma que lo rehabilite: lo que importa es el efecto.
        assert ("ponerEnMarcha(false)" in catch
                or "disabled = false" in catch or "disabled=false" in catch), (
            "el catch de iniciar() no rehabilita el boton: %r" % catch[:200]
        )

    def test_el_sondeo_para_tras_varios_ciclos_en_idle(self, html):
        """Si el contenedor se reinicia, el estado llega 'idle' para siempre y
        `setInterval` seguia sondeando cada 3 s indefinidamente."""
        assert "ciclosIdle" in html, (
            "nada cuenta los ciclos en 'idle': el sondeo no tiene final"
        )
        i = html.index("ciclosIdle")
        assert "clearInterval" in html[i - 200:i + 900], (
            "los ciclos en idle se cuentan pero no paran el sondeo"
        )

    def test_el_sondeo_espacia_los_intentos(self, html):
        """Intervalo creciente al alargarse la corrida, en vez de 3 s eternos."""
        assert "intervaloSondeo" in html, "el sondeo no tiene retroceso"

    def test_no_se_solapan_dos_intervalos(self, html):
        """`polling = setInterval(...)` sin limpiar el anterior deja dos vivos."""
        i = html.index("function arrancarSondeo")
        cuerpo = html[i:i + 600]
        assert "clearInterval" in cuerpo, (
            "arrancarSondeo no limpia el intervalo anterior antes de crear otro"
        )


# ─────────────── B9 · el nombre de la ciudad no se interpola ───────────────

class TestCiudadEscapada:
    def test_no_queda_interpolacion_en_el_atributo_onclick(self, html):
        assert "seleccionarCiudad('${c.ciudad}'" not in html, (
            "el nombre de la ciudad sigue interpolado dentro del atributo onclick"
        )

    def test_el_chip_usa_dataset_y_listener_delegado(self, html):
        assert "dataset.ciudad" in html or "data-ciudad" in html, (
            "el chip no lleva el nombre en un data-attribute"
        )
        assert "addEventListener" in html, "no hay listener delegado para los chips"

    def test_el_texto_del_chip_tambien_se_escapa(self, html):
        """El plan citaba un solo punto de inyeccion; son dos.

        La misma linea metia el nombre en el atributo `onclick` Y como texto del
        chip. Un nombre con <img onerror=...> entraba por el segundo.
        """
        assert "escaparHtml" in html or "textContent" in html, (
            "el texto del chip se sigue construyendo sin escapar"
        )

    def test_existe_la_funcion_de_escape(self, html):
        assert "function escaparHtml" in html, (
            "falta la funcion de escape; el dashboard ya tiene uno en app.py:2064"
        )


# ─────────────── B10 (mitad de cliente) · Enter a media corrida ───────────────

class TestEntradaBloqueadaDuranteLaCorrida:
    def test_el_campo_de_ciudad_se_deshabilita(self, html):
        """El campo nunca se deshabilitaba, asi que pulsar Enter a media corrida
        relanzaba `iniciar()`."""
        assert "input-ciudad').disabled" in html or 'input-ciudad").disabled' in html, (
            "el campo de ciudad nunca se deshabilita durante la corrida"
        )


# ─────────────── B12 · las insignias no se quedan rancias ───────────────

class TestReinicioEntreCorridas:
    def test_las_insignias_vuelven_a_neutro(self, html):
        # El pintado del estado, no el de limpieza: es el que se quedaba rancio.
        # Se recorta hasta la SIGUIENTE funcion, no un numero fijo de caracteres:
        # con una ventana fija, anadir codigo a pintarEstado empuja lo que se
        # quiere comprobar fuera del recorte y el test falla sin que nada se rompa.
        i = html.index("function pintarEstado")
        fin = html.index(chr(10) + "function ", i + 1)
        cuerpo = html[i:fin]
        assert "CATS.forEach" in cuerpo, "pintarEstado ya no pinta las insignias"
        assert "else el.className = 'cat-badge'" in cuerpo, (
            "las insignias no tienen rama que las devuelva a neutro: la segunda "
            "busqueda de la sesion arranca con todo marcado como completado"
        )

    def test_iniciar_limpia_los_contadores(self, html):
        i = html.index("async function iniciar")
        cuerpo = html[i:i + 2500]
        assert "s-nuevos').textContent = '0'" in cuerpo or "limpiarPantalla" in cuerpo, (
            "iniciar() no limpia los numeros de la corrida anterior"
        )


# ─────────────── B13 · estado muerto ───────────────

class TestSinEstadoMuerto:
    def test_no_queda_la_variable_sin_usar(self, html):
        assert html.count("ciudadSeleccionada") == 0, (
            "`ciudadSeleccionada` se declaraba y no se usaba en ningun sitio"
        )

    def test_el_job_no_acumula_resultados_que_nadie_lee(self):
        """`_import_job['resultados']` guardaba filas completas de prospectos
        —nombre, domicilio, telefono— y ningun endpoint las devolvia."""
        assert "resultados" not in app._nuevo_import_job(), (
            "el estado sigue acumulando `resultados`, que nadie consume y son "
            "datos personales"
        )


# ─────────────── cancelar ───────────────

class TestCancelar:
    def test_el_endpoint_existe_y_marca_la_cancelacion(self, client, monkeypatch):
        monkeypatch.setattr(app, "_import_job",
                            app._nuevo_import_job("Guadalajara", status="running"))
        monkeypatch.setattr(app, "_guardar_estado_importador", lambda *a, **k: None)
        r = client.post("/api/importador/cancelar")
        assert r.status_code == 200
        assert r.get_json()["ok"] is True
        assert app._import_job["cancelado"] is True

    def test_cancelar_sin_corrida_no_miente(self, client, monkeypatch):
        monkeypatch.setattr(app, "_import_job", app._nuevo_import_job())
        d = client.post("/api/importador/cancelar").get_json()
        assert d["ok"] is False, "dice haber cancelado una corrida que no existe"

    def test_el_worker_se_detiene_conservando_lo_escrito(self, monkeypatch):
        """Se cancela entre pasos, nunca a mitad de un append_rows."""
        import sys, os as _os
        sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
        from test_importador_conteo import escenario_veinte_contra_diez

        monkeypatch.setattr(app, "GMAPS_OK", True)
        monkeypatch.setattr(app, "_enviar_telegram_importador", lambda *a, **k: None)
        monkeypatch.setattr(app, "_guardar_estado_importador", lambda *a, **k: None)
        monkeypatch.setattr(app.time, "sleep", lambda _s: None)
        monkeypatch.setattr(app, "_import_job",
                            app._nuevo_import_job("CiudadDemo", status="running"))
        gmaps, ws = escenario_veinte_contra_diez()
        monkeypatch.setattr(app.googlemaps, "Client", lambda key=None, **k: gmaps)
        monkeypatch.setattr(app, "get_worksheet", lambda _n: ws)

        # Se cancela en cuanto la primera categoria termina de guardar.
        real = app._exportar_a_sheets

        def exportar_y_cancelar(*a, **k):
            n = real(*a, **k)
            app._import_job["cancelado"] = True
            return n

        monkeypatch.setattr(app, "_exportar_a_sheets", exportar_y_cancelar)
        app._worker_importador("CiudadDemo", "clave-falsa")

        assert app._import_job["status"] == "cancelado", (
            "la corrida cancelada acabo en %r" % app._import_job["status"]
        )
        assert ws.escrituras == 8, "se perdio lo que la primera categoria ya habia escrito"
        assert app._import_job["nuevos_en_sheet"] == 8, (
            "el contador no conserva lo guardado antes de cancelar"
        )


# ─────────────── el JS embebido tiene que parsear ───────────────

class TestJsValido:
    """El JS vive dentro de un string de Python: un error de sintaxis ahi no lo
    ve ni pytest ni el import de app.py. La pagina se sirve rota y en silencio.
    """

    def _extraer_js(self, html):
        return html[html.rindex("<script>") + len("<script>"):html.rindex("</script>")]

    def test_las_llaves_estan_balanceadas(self, html):
        import re
        js = self._extraer_js(html)
        sin_com = re.sub(r"//[^\n]*", "", js)
        sin_str = re.sub(r"`(?:[^`\]|\.)*`|'(?:[^'\\n]|\.)*'|\"(?:[^\"\\n]|\.)*\"",
                         "''", sin_com)
        for a, c in (("{", "}"), ("(", ")"), ("[", "]")):
            assert sin_str.count(a) == sin_str.count(c), (
                "el JS del importador tiene %s/%s desbalanceados (%d vs %d)"
                % (a, c, sin_str.count(a), sin_str.count(c))
            )

    def test_node_lo_parsea(self, html, tmp_path):
        import shutil
        import subprocess
        node = shutil.which("node")
        if not node:
            pytest.skip("node no esta instalado en esta maquina")
        ruta = tmp_path / "importador.js"
        ruta.write_text(self._extraer_js(html), encoding="utf-8")
        r = subprocess.run([node, "--check", str(ruta)],
                           capture_output=True, text=True, timeout=60)
        assert r.returncode == 0, "el JS del importador no parsea:\n%s" % r.stderr


class TestCanceladaNoParecCompletada:
    """Una corrida detenida no puede presentarse como una corrida entera.

    Si lo hace, el operador no tiene motivo para volver a correr la ciudad y la
    categoria que falto no se recoge nunca.
    """

    def _correr_cancelando_tras_la_primera(self, monkeypatch):
        import sys, os as _os
        sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
        from test_importador_conteo import escenario_veinte_contra_diez
        monkeypatch.setattr(app, "GMAPS_OK", True)
        monkeypatch.setattr(app, "_guardar_estado_importador", lambda *a, **k: None)
        monkeypatch.setattr(app.time, "sleep", lambda _s: None)
        monkeypatch.setattr(app, "_import_job",
                            app._nuevo_import_job("CiudadDemo", status="running"))
        gmaps, ws = escenario_veinte_contra_diez()
        monkeypatch.setattr(app.googlemaps, "Client", lambda key=None, **k: gmaps)
        monkeypatch.setattr(app, "get_worksheet", lambda _n: ws)
        real = app._exportar_a_sheets

        def exportar_y_cancelar(*a, **k):
            n = real(*a, **k)
            app._import_job["cancelado"] = True
            return n

        monkeypatch.setattr(app, "_exportar_a_sheets", exportar_y_cancelar)
        app._worker_importador("CiudadDemo", "clave-falsa")
        return app._import_job

    def test_no_marca_todas_las_categorias_como_hechas(self, monkeypatch):
        monkeypatch.setattr(app, "_enviar_telegram_importador", lambda *a, **k: None)
        est = self._correr_cancelando_tras_la_primera(monkeypatch)
        assert est["status"] == "cancelado"
        assert est["progreso"] < len(app.CATEGORIAS_IMPORTADOR), (
            "una corrida detrada tras 1 de %d categorias dice progreso=%d: las "
            "insignias saldrian todas en verde"
            % (len(app.CATEGORIAS_IMPORTADOR), est["progreso"])
        )

    def test_la_barra_no_llega_al_cien(self, monkeypatch):
        monkeypatch.setattr(app, "_enviar_telegram_importador", lambda *a, **k: None)
        est = self._correr_cancelando_tras_la_primera(monkeypatch)
        assert est["fraccion"] < 100, (
            "la barra marca 100 %% en una corrida detenida a la mitad"
        )

    def test_telegram_dice_que_se_detuvo(self, monkeypatch):
        """El unico canal que llega al owner cuando no esta mirando la pantalla.

        Si ahi pone "Importador Completado", el operador da por hecho que se
        recorrio todo y no vuelve a correr las categorias que faltaron.
        """
        avisos = []
        monkeypatch.setattr(app, "_enviar_telegram_importador",
                            lambda *a, **k: avisos.append((a, k)))
        self._correr_cancelando_tras_la_primera(monkeypatch)
        assert avisos, "no se aviso por Telegram de una corrida detenida"
        _, kwargs = avisos[-1]
        assert kwargs.get("cancelado") is True, (
            "el aviso de Telegram no distingue una corrida detenida de una "
            "completada: %r" % (kwargs,)
        )

    def test_el_titulo_de_telegram_no_dice_completado(self, monkeypatch):
        enviados = []
        monkeypatch.setenv("TELEGRAM_TOKEN", "tok")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "1")
        monkeypatch.setattr(app.req_lib, "post",
                            lambda url, data=None, **k: enviados.append(data))
        app._enviar_telegram_importador(
            "CiudadDemo", {"nuevos": 8, "encontrados": 12, "duplicados": 4,
                           "descartados": 0}, {}, 1.0, cancelado=True)
        assert enviados, "no se envio nada"
        texto = enviados[-1]["text"]
        assert "Completado" not in texto, "dice 'Completado' de una corrida detenida"
        assert "deten" in texto.lower(), (
            "el titulo no dice en ninguna forma que la corrida se detuvo: %r" % texto
        )


class TestCorridaEnteraNoEsCancelada:
    def test_cancelar_durante_la_ultima_categoria_no_la_marca_parcial(self, monkeypatch):
        """`cancelado` se leia despues del bucle, sin mirar COMO salio.

        Pulsar Detener mientras la ultima categoria ya estaba escribiendo dejaba
        una corrida que recorrio el 100 % etiquetada como detenida.
        """
        import sys, os as _os
        sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
        from test_importador_conteo import escenario_veinte_contra_diez
        monkeypatch.setattr(app, "GMAPS_OK", True)
        monkeypatch.setattr(app, "_enviar_telegram_importador", lambda *a, **k: None)
        monkeypatch.setattr(app, "_guardar_estado_importador", lambda *a, **k: None)
        monkeypatch.setattr(app.time, "sleep", lambda _s: None)
        monkeypatch.setattr(app, "_import_job",
                            app._nuevo_import_job("CiudadDemo", status="running"))
        gmaps, ws = escenario_veinte_contra_diez()
        monkeypatch.setattr(app.googlemaps, "Client", lambda key=None, **k: gmaps)
        monkeypatch.setattr(app, "get_worksheet", lambda _n: ws)
        real = app._exportar_a_sheets
        llamadas = {"n": 0}

        def exportar(*a, **k):
            llamadas["n"] += 1
            n = real(*a, **k)
            if llamadas["n"] == len(app.CATEGORIAS_IMPORTADOR):
                app._import_job["cancelado"] = True   # ya no queda nada por hacer
            return n

        monkeypatch.setattr(app, "_exportar_a_sheets", exportar)
        app._worker_importador("CiudadDemo", "clave-falsa")
        assert app._import_job["status"] == "done", (
            "se recorrieron todas las categorias y quedo como %r"
            % app._import_job["status"]
        )
