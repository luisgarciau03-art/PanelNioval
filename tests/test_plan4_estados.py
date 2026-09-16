"""Plan 4 - T4.5. Los cuatro estados de carga, fijados.

Antes de esta tarea el panel tenia UN solo estado no-feliz: un spinner generico
que **sustituia** el contenido. De ahi salen tres problemas distintos:

  1. **CE4 (salto de layout)**: el spinner ocupa 40 px de padding y el contenido
     que llega ocupa cientos. Al llegar los datos, todo lo de abajo se mueve.
     Un esqueleto con la forma del contenido real no mueve nada.
  2. **CE5**: `class="loading"` aparecia 16 veces. Un spinner no dice *que* se
     esta cargando ni cuanto falta, y se ve identico cuando la peticion ya
     murio.
  3. **Vacio, error y parcial no existian.** "No hay contactos en esta ciudad",
     "Google Sheets devolvio 429" y "cargo el tablero pero fallo una tabla" se
     mostraban igual: o el spinner eterno, o un `.empty` gris.

Y una regla que hereda del ADR de direccion visual (voto del Critico):

  **La celebracion queda reservada a estados verificados de forma explicita.**

  Eso no era retorica. `get_contacto_pendiente` se tragaba la excepcion y
  devolvia `None`, que el endpoint traducia a `{'fin': True}`, que el formulario
  pintaba como *"🎉 ¡Lista completada!"*. Con las hojas caidas, el operador veia
  confeti. Un estado que solo puede afirmar "no recibi datos" no se viste de
  exito.

Cada patron de este archivo se comprueba en las DOS direcciones: que no ve el
marcado nuevo, y que **si** ve el marcado viejo que se retiro (el literal esta
escrito en el propio test, para que no dependa de un respaldo en disco).
"""
import re
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import app

RAIZ = Path(__file__).resolve().parent.parent
CSS = RAIZ / "static" / "css"
JS = RAIZ / "static" / "js"
TPL = RAIZ / "templates"

SUPERFICIES = ["dashboard", "formulario", "importador"]

# El marcado exacto que la T4.5 retira. Sirve de control negativo: si un patron
# no encuentra ESTO, su cero sobre el codigo nuevo no vale nada.
MARCADO_VIEJO = (
    '<div class="loading"><div class="spinner"></div><br>Cargando...</div>'
)
CSS_VIEJO = (
    ".spinner{display:inline-block;width:28px;height:28px;"
    "border:3px solid var(--borde-fuerte);border-top-color:var(--blue);"
    "border-radius:50%;animation:spin .8s linear infinite}"
)

RE_LOADING = re.compile(r"""class=["']loading["']""")
RE_SPINNER = re.compile(r"\.spinner\b")


def _texto(ruta: Path) -> str:
    return ruta.read_text(encoding="utf-8")


def _cuerpo_regla(css: str, selector: str) -> str:
    """Devuelve el cuerpo `{...}` de la regla cuyo selector es exactamente
    `selector`. Devuelve '' si no existe."""
    for m in re.finditer(r"([^{}]+)\{([^}]*)\}", re.sub(r"/\*.*?\*/", "", css, flags=re.S)):
        selectores = [s.strip() for s in m.group(1).split(",")]
        if selector in selectores:
            return m.group(2)
    return ""


def _fake_client(worksheet):
    cliente = MagicMock()
    sp = MagicMock()
    cliente.open_by_key.return_value = sp
    sp.worksheet.return_value = worksheet
    return cliente


@pytest.fixture
def client():
    app.app.config["TESTING"] = True
    return app.app.test_client()


# ───────────────────────── CE5: se acabo el spinner ─────────────────────────

class TestCE5SinSpinnerGenerico:
    @pytest.mark.parametrize("superficie", SUPERFICIES)
    def test_ninguna_plantilla_declara_class_loading(self, superficie):
        html = _texto(TPL / f"{superficie}.html")
        assert not RE_LOADING.search(html), (
            f"{superficie}.html sigue sustituyendo el contenido por un spinner"
        )

    @pytest.mark.parametrize("script", ["dashboard.js", "formulario.js", "importador.js"])
    def test_ningun_js_inyecta_class_loading(self, script):
        assert not RE_LOADING.search(_texto(JS / script)), (
            f"{script} inyecta el spinner generico en tiempo de ejecucion"
        )

    @pytest.mark.parametrize("hoja", ["dashboard.css", "formulario.css"])
    def test_las_hojas_de_superficie_ya_no_declaran_el_spinner(self, hoja):
        css = _texto(CSS / hoja)
        assert not RE_SPINNER.search(css), f"{hoja} conserva la clase .spinner"
        assert "@keyframes spin{" not in css and "@keyframes spin " not in css

    def test_los_patrones_ven_el_marcado_que_se_retiro(self):
        """Control negativo. Sin esto, los tres tests de arriba pasarian igual
        con un patron mal escrito."""
        assert RE_LOADING.search(MARCADO_VIEJO)
        assert RE_SPINNER.search(CSS_VIEJO)


# ─────────────────── los cuatro estados son componentes ────────────────────

class TestLosCuatroEstadosSonComponentes:
    COMPONENTES = [
        ".esqueleto",
        ".esqueleto-tarjeta",
        ".esqueleto-tabla__cabecera",
        ".esqueleto-tabla__fila",
        ".esqueleto-chip",
        ".estado",
        ".estado--vacio",
        ".estado--error",
        ".estado--parcial",
    ]

    @pytest.mark.parametrize("selector", COMPONENTES)
    def test_componentes_css_declara_el_componente(self, selector):
        assert _cuerpo_regla(_texto(CSS / "componentes.css"), selector), (
            f"componentes.css no declara {selector}"
        )

    def test_vacio_y_error_no_comparten_vocabulario_visual(self):
        """El ADR lo pide explicitamente: hoy 'no hay datos' y 'fallo la
        lectura' se ven igual. Si ambos estados usan los mismos tokens de
        color, siguen siendo el mismo estado con otro texto."""
        css = _texto(CSS / "componentes.css")
        vacio = set(re.findall(r"var\((--[a-z0-9-]+)\)", _cuerpo_regla(css, ".estado--vacio")))
        error = set(re.findall(r"var\((--[a-z0-9-]+)\)", _cuerpo_regla(css, ".estado--error")))
        assert vacio and error, "alguno de los dos estados no usa ningun token"
        assert vacio != error, "vacio y error usan exactamente la misma paleta"
        assert any("error" in t for t in error), "el estado de error no usa la paleta de error"
        assert not any("error" in t for t in vacio), "el estado vacio se pinta de error"

    def test_el_estado_parcial_no_es_el_de_error(self):
        css = _texto(CSS / "componentes.css")
        parcial = set(re.findall(r"var\((--[a-z0-9-]+)\)", _cuerpo_regla(css, ".estado--parcial")))
        error = set(re.findall(r"var\((--[a-z0-9-]+)\)", _cuerpo_regla(css, ".estado--error")))
        assert parcial and parcial != error


# ──────────────────── CE4: el esqueleto reserva el espacio ─────────────────

class TestElEsqueletoReservaElEspacio:
    """Un esqueleto sin altura propia colapsa a 0 px y provoca justo el salto
    que viene a evitar."""

    CON_ALTURA = [
        ".esqueleto",
        ".esqueleto-tarjeta",
        ".esqueleto-tabla__cabecera",
        ".esqueleto-tabla__fila",
        ".esqueleto-chip",
    ]

    @pytest.mark.parametrize("selector", CON_ALTURA)
    def test_cada_pieza_declara_su_altura(self, selector):
        cuerpo = _cuerpo_regla(_texto(CSS / "componentes.css"), selector)
        assert re.search(r"(?:^|;)\s*(?:min-)?height\s*:", cuerpo), (
            f"{selector} no declara altura: colapsa a 0 y el layout salta"
        )

    def test_el_esqueleto_de_tabla_trae_filas_fijas(self):
        """El numero de filas del esqueleto es un dato del JS, no una
        casualidad del CSS: si no lo declara, cada seccion pinta las que
        quiera y la altura reservada varia."""
        js = _texto(JS / "estados.js")
        assert re.search(r"FILAS_ESQUELETO\s*=\s*\d+", js)


# ──────────────────────── el umbral de parpadeo ────────────────────────────

class TestElUmbralDeParpadeo:
    """Por debajo de ~200 ms un esqueleto se ve peor que la espera: aparece y
    desaparece antes de que el ojo lo lea."""

    def test_estados_js_declara_el_umbral(self):
        js = _texto(JS / "estados.js")
        m = re.search(r"UMBRAL_ESQUELETO\s*=\s*(\d+)", js)
        assert m, "estados.js no declara UMBRAL_ESQUELETO"
        assert 100 <= int(m.group(1)) <= 400, "el umbral esta fuera del rango util"

    def test_el_umbral_se_usa_en_un_temporizador(self):
        js = _texto(JS / "estados.js")
        # El umbral tiene que ser el ARGUMENTO DE RETARDO del temporizador. Un
        # patron laxo tipo `setTimeout.*UMBRAL` daria por bueno tenerlo suelto
        # en cualquier otra linea del archivo.
        assert "setTimeout(" in js, "estados.js no programa ningun temporizador"
        assert re.search(r",\s*UMBRAL_ESQUELETO\s*\)", js), (
            "el umbral esta declarado pero no es el retardo del temporizador"
        )

    def test_el_temporizador_se_cancela(self):
        """Si el fetch termina antes del umbral y nadie cancela el timer, el
        esqueleto aparece DESPUES de los datos y los borra."""
        assert "clearTimeout" in _texto(JS / "estados.js")


# ─────────────────────── el error ofrece reintentar ────────────────────────

class TestElErrorOfreceReintentar:
    def test_el_estado_de_error_construye_un_boton(self):
        js = _texto(JS / "estados.js")
        assert "estado__accion" in js
        assert "addEventListener" in js, (
            "el boton de reintento no puede colgar de un onclick inline"
        )

    def test_cada_llamada_a_error_pasa_un_reintento(self):
        """Un estado de error sin salida es una pantalla muerta: el operador
        solo puede recargar la pagina entera."""
        js = _texto(JS / "dashboard.js")
        llamadas = [m.start() for m in re.finditer(r"Estados\.error\(", js)]
        assert llamadas, "dashboard.js no usa el estado de error del sistema"
        sin_reintento = [
            js[:i].count("\n") + 1
            for i in llamadas
            if "reintentar" not in js[i:i + 400]
        ]
        assert not sin_reintento, f"Estados.error sin reintentar en lineas {sin_reintento}"


# ──────────────────── la celebracion queda reservada ───────────────────────

class TestLaCelebracionQuedaReservada:
    CELEBRACION = ("🎉", "✅", "¡Completado!")

    def test_el_importador_no_hornea_la_marca_de_exito_en_la_plantilla(self):
        """El recuadro de resultado traia `<div class="icon">✅</div>` fijo, asi
        que una corrida cancelada, agotada por presupuesto o caida con error se
        remataba con una marca de verificacion verde."""
        html = _texto(TPL / "importador.html")
        assert '<div class="icon">✅</div>' not in html
        assert 'id="result-icono"' in html, "el icono tiene que salir del estado real"

    def test_el_importador_elige_el_icono_por_estado(self):
        js = _texto(JS / "importador.js")
        m = re.search(r"ICONO_RESULTADO\s*=\s*\{(.*?)\}", js, re.S)
        assert m, "importador.js no declara un icono por estado"
        mapa = m.group(1)
        assert "done" in mapa
        for estado in ("cancelado", "presupuesto_agotado", "interrumpido", "error"):
            fragmento = re.search(rf"{estado}\s*:\s*'([^']*)'", mapa)
            assert fragmento, f"falta el icono de {estado}"
            assert "✅" not in fragmento.group(1), (
                f"{estado} se remata con una marca de exito"
            )

    def test_ningun_estado_vacio_del_tablero_celebra(self):
        """`Sin envios en este filtro. 🎉` festejaba no tener datos."""
        js = _texto(JS / "dashboard.js")
        assert "🎉" not in js

    def test_el_formulario_tiene_un_paso_de_error_distinto_del_de_fin(self):
        html = _texto(TPL / "formulario.html")
        assert 'id="step-fin"' in html
        assert 'id="step-error"' in html, (
            "sin paso de error, un fallo de lectura acaba en la pantalla de confeti"
        )

    def test_el_formulario_enruta_el_error_a_su_paso(self):
        js = _texto(JS / "formulario.js")
        assert "showStep('error')" in js
        assert "'error'" in js and "PASOS" in js

    def test_el_patron_ve_la_celebracion_que_se_retiro(self):
        """Control negativo del apartado entero."""
        viejo = '<div class="icon">🎉</div>'
        assert any(c in viejo for c in self.CELEBRACION)


# ────────── el backend distingue "no hay mas" de "no pude leer" ────────────

class TestElBackendDistingueSinDatosDeFalloDeLectura:
    """El bug de fondo. `get_contacto_pendiente` capturaba `Exception` y
    devolvia `None`, exactamente igual que cuando la hoja se lee bien y no
    quedan pendientes. El endpoint no tenia forma de saber cual de las dos."""

    def _ws(self, rows):
        ws = MagicMock()
        ws.get_all_values.return_value = rows
        return ws

    SIN_PENDIENTES = [
        ["TIENDA", "TEL", "CIUDAD", "X", "Y", "RESPUESTA"],
        ["Tienda A", "555", "CDMX", "", "", "Llamado"],
    ]

    def test_un_fallo_de_lectura_ya_no_se_traga(self, monkeypatch):
        ws = MagicMock()
        ws.get_all_values.side_effect = Exception("429 RESOURCE_EXHAUSTED")
        monkeypatch.setattr(app, "get_gs_client", lambda: _fake_client(ws))
        with pytest.raises(Exception):
            app.get_contacto_pendiente(0)

    def test_sin_pendientes_sigue_devolviendo_none(self, monkeypatch):
        """La otra direccion: el arreglo no puede convertir un vacio legitimo
        en un error."""
        monkeypatch.setattr(
            app, "get_gs_client", lambda: _fake_client(self._ws(self.SIN_PENDIENTES))
        )
        assert app.get_contacto_pendiente(0) is None

    def test_el_endpoint_responde_error_y_no_fin(self, client, monkeypatch):
        ws = MagicMock()
        ws.get_all_values.side_effect = Exception("429 RESOURCE_EXHAUSTED")
        monkeypatch.setattr(app, "get_gs_client", lambda: _fake_client(ws))
        r = client.get("/api/formulario/siguiente?skip=0")
        assert r.status_code == 503
        datos = r.get_json()
        assert datos.get("fin") is not True, "un fallo de lectura se anuncia como fin de lista"
        assert datos.get("error")

    def test_el_endpoint_sigue_cerrando_la_lista_cuando_toca(self, client, monkeypatch):
        monkeypatch.setattr(
            app, "get_gs_client", lambda: _fake_client(self._ws(self.SIN_PENDIENTES))
        )
        r = client.get("/api/formulario/siguiente?skip=0")
        assert r.status_code == 200
        assert r.get_json() == {"fin": True}

    def test_el_error_no_filtra_datos_del_cliente(self, client, monkeypatch):
        """El mensaje va a la pantalla del operador; no puede arrastrar filas
        de la hoja."""
        ws = MagicMock()
        ws.get_all_values.side_effect = Exception("fallo leyendo +52 55 1234 5678")
        monkeypatch.setattr(app, "get_gs_client", lambda: _fake_client(ws))
        cuerpo = client.get("/api/formulario/siguiente?skip=0").get_data(as_text=True)
        assert "1234" not in cuerpo


# ─────────────────── movimiento del esqueleto (CE6, CE7) ───────────────────

class TestElMovimientoDelEsqueleto:
    def test_la_animacion_solo_toca_propiedades_del_compositor(self):
        """Animar `width` o `background-position` obliga a repintar en cada
        cuadro; con 14 tablas esqueleto a la vez eso se nota."""
        css = _texto(CSS / "componentes.css")
        m = re.search(r"@keyframes\s+esqueleto-brillo\s*\{(.*?)\n\}", css, re.S)
        assert m, "componentes.css no declara la animacion del esqueleto"
        cuerpo = m.group(1)
        propiedades = set(re.findall(r"([a-z-]+)\s*:", cuerpo))
        assert propiedades <= {"transform", "opacity"}, (
            f"la animacion toca propiedades que fuerzan repintado: {propiedades}"
        )

    def test_la_preferencia_de_movimiento_reducido_la_apaga(self):
        css = _texto(CSS / "componentes.css")
        bloques = re.findall(
            r"@media[^{]*prefers-reduced-motion[^{]*\{(.*?\n\})", css, re.S
        )
        assert bloques, "componentes.css no atiende prefers-reduced-motion"
        assert any("esqueleto" in b for b in bloques), (
            "el esqueleto sigue animandose con la preferencia activa"
        )

    def test_no_se_cuela_un_transition_all(self):
        # Los comentarios del archivo citan `transition: all` para explicar por
        # que se retiro; se descartan antes de mirar.
        css = re.sub(r"/\*.*?\*/", "", _texto(CSS / "componentes.css"), flags=re.S)
        assert "transition:all" not in css.replace(" ", "")

    def test_el_patron_del_transition_all_encuentra_el_caso_real(self):
        css = re.sub(r"/\*.*?\*/", "", ".x{transition: all .2s}", flags=re.S)
        assert "transition:all" in css.replace(" ", "")


# ───────────────────────── el sistema esta enlazado ────────────────────────

class TestElSistemaEstaEnlazado:
    @pytest.mark.parametrize("superficie", SUPERFICIES)
    def test_las_tres_superficies_cargan_estados_js(self, superficie):
        assert "js/estados.js" in _texto(TPL / f"{superficie}.html")

    @pytest.mark.parametrize("superficie", SUPERFICIES)
    def test_estados_js_va_antes_que_el_script_de_la_superficie(self, superficie):
        html = _texto(TPL / f"{superficie}.html")
        assert html.index("js/estados.js") < html.index(f"js/{superficie}.js"), (
            f"{superficie}.js corre antes de que exista Estados"
        )

    def test_estados_js_expone_los_cuatro_estados(self):
        """Sobre el objeto exportado, no sobre el archivo entero: un patron que
        acepte cualquier aparicion del nombre pasa con solo tener una llamada
        interna, sin que `Estados` exponga nada."""
        js = _texto(JS / "estados.js")
        m = re.search(r"global\.Estados\s*=\s*\{(.*?)\n  \};", js, re.S)
        assert m, "estados.js no exporta un objeto Estados"
        expuesto = dict(re.findall(r"(\w+)\s*:\s*(\w+)", m.group(1)))
        for metodo in ("esqueleto", "vacio", "error", "parcial"):
            assert metodo in expuesto, f"Estados no expone {metodo}"

    @pytest.mark.parametrize("superficie", SUPERFICIES)
    def test_las_plantillas_no_traen_colores_literales_nuevos(self, superficie):
        """CE3 sigue vigente: los estados nuevos no pueden reintroducir hex."""
        assert not re.findall(r"#[0-9a-fA-F]{3,8}\b", _texto(TPL / f"{superficie}.html"))


# ───────────────── los estados se anuncian a un lector de pantalla ─────────

class TestLosEstadosSeAnuncian:
    """Un estado que cambia en silencio no existe para quien usa lector. La
    auditoria previa contaba 0 `aria-live` y 0 `role=status` en el panel."""

    def test_el_bloque_de_estado_es_una_region_viva(self):
        js = _texto(JS / "estados.js")
        assert 'role="status"' in js or "role='status'" in js

    def test_el_esqueleto_no_se_lee_celda_a_celda(self):
        """Un esqueleto es decoracion: anunciarlo llena el lector de ruido."""
        js = _texto(JS / "estados.js")
        assert 'aria-hidden="true"' in js or "aria-hidden='true'" in js


# ───────────── lo que encontraron los reviewers de la T4.5 ─────────────────

class TestElEsqueletoNoBorraLosDatosQueYaLlegaron:
    """El fallo mas grave de la primera version, encontrado por `code-reviewer`
    y por `a11y-architect` de forma independiente.

    `terminar()` hacia `el.innerHTML = ''` sin mirar que habia dentro. Quien
    llama cierra el esqueleto en un `finally`, que corre DESPUES de que la
    seccion pinto sus datos: al pulsar "Actualizar" con una respuesta de Google
    de mas de 200 ms, el esqueleto se pintaba, los datos lo sustituian, y el
    `finally` borraba los datos. Pantalla en blanco, sin error que lo explique.
    """

    def test_terminar_retira_su_nodo_y_no_vacia_el_contenedor(self):
        js = _texto(JS / "estados.js")
        cuerpo = re.search(r"return function terminar\(\)\s*\{(.*?)\n    \};", js, re.S)
        assert cuerpo, "no se encuentra terminar()"
        assert "removeChild" in cuerpo.group(1), "terminar() no retira su propio nodo"
        assert "innerHTML" not in cuerpo.group(1), (
            "terminar() sigue vaciando el contenedor entero"
        )

    def test_el_esqueleto_guarda_referencia_a_lo_que_inserto(self):
        js = _texto(JS / "estados.js")
        assert "appendChild" in js, (
            "sin un nodo propio, terminar() no puede saber que retirar"
        )

    def test_el_patron_ve_la_version_rota(self):
        """Control negativo: el `terminar()` anterior, tal cual estaba."""
        roto = "clearTimeout(temporizador); if (pintado) el.innerHTML = '';"
        assert "innerHTML" in roto and "removeChild" not in roto


class TestElReintentoDaSenalDeVida:
    """El reintento no pintaba esqueleto: `pintada` solo se marcaba tras un
    exito, asi que al reintentar desde el error seguia en `false` y el mensaje
    de fallo anterior se quedaba en pantalla. El boton parecia no hacer nada."""

    def test_pintada_se_marca_pase_lo_que_pase(self):
        js = _texto(JS / "dashboard.js")
        bloque = re.search(r"\}\s*finally\s*\{(.*?)\n  \}", js, re.S)
        assert bloque, "loadSection no tiene finally"
        assert "state.pintada[name] = true" in bloque.group(1), (
            "pintada se marca solo en el camino feliz"
        )


class TestElAvisoDeGraficasNoDestruyeLosLienzos:
    """`Estados.parcial('dash-charts')` sustituia el contenido del contenedor,
    y con el se llevaba los <canvas>. El siguiente intento moria buscando un
    elemento que ya no existe: el fallo pasaba de temporal a permanente."""

    def test_el_aviso_tiene_contenedor_propio_y_va_fuera(self):
        html = _texto(TPL / "dashboard.html")
        for cid in ("dash-charts-aviso", "vdash-charts-aviso"):
            assert 'id="%s"' % cid in html, "falta el contenedor %s" % cid
            caja = cid.replace("-aviso", "")
            assert html.index('id="%s"' % cid) < html.index('id="%s"' % caja), (
                "%s esta dentro de la caja que pretende sustituir" % cid
            )

    def test_ninguna_llamada_a_parcial_apunta_a_la_caja_de_graficas(self):
        js = _texto(JS / "dashboard.js")
        destinos = re.findall(r"Estados\.parcial\(\s*([^,]+),", js)
        assert destinos, "nadie usa el estado parcial"
        for destino in destinos:
            assert "charts'" not in destino or "aviso" in destino, (
                "Estados.parcial apunta a %s: borraria los <canvas>" % destino
            )

    def test_las_dos_secciones_con_graficas_usan_el_mismo_guarda(self):
        """La asimetria que marco `code-reviewer`: el tablero degradaba a
        parcial y ventas-dash no, asi que el mismo fallo se llevaba por delante
        la seccion entera en una de las dos."""
        js = _texto(JS / "dashboard.js")
        assert js.count("pintarGraficasConAviso(") >= 3, (
            "el guarda existe pero no lo usan las dos secciones"
        )


class TestElErrorInterrumpeYElRestoNo:
    """`role=status` es aria-live polite: se anuncia cuando el lector esta
    ocioso y puede perderse. Un fallo de lectura bloquea la tarea del operador
    y merece `alert`; vacio y parcial no bloquean nada."""

    def test_solo_el_error_usa_alert(self):
        js = _texto(JS / "estados.js")
        assert re.search(r"estado--error.*?\?\s*'alert'\s*:\s*'status'", js, re.S), (
            "el rol no depende del tipo de estado"
        )

    def test_el_formulario_revela_el_paso_antes_de_escribir_el_texto(self):
        """Un `role=status` dentro de un `display:none` esta fuera del arbol de
        accesibilidad: mutarlo ahi y revelarlo despues no anuncia nada."""
        js = _texto(JS / "formulario.js")
        cuerpo = re.search(r"function mostrarErrorDeLectura\(e\)\s*\{(.*?)\n\}", js, re.S)
        assert cuerpo, "no se encuentra mostrarErrorDeLectura"
        c = cuerpo.group(1)
        assert c.index("showStep('error')") < c.index("error-detalle"), (
            "el texto se escribe con el paso todavia oculto"
        )

    def test_el_formulario_lleva_el_foco_al_reintento(self):
        js = _texto(JS / "formulario.js")
        assert re.search(r"btn-reintentar-contacto.*?\.focus\(\)", js, re.S)


class TestElAvisoDeCargaSeAnuncia:
    """Un `role=status` que ya estaba en el HTML cuando el lector construyo el
    arbol no se anuncia: los lectores anuncian MUTACIONES. La plantilla deja el
    nodo vacio y el texto lo escribe el JS despues del primer render."""

    @pytest.mark.parametrize("superficie", SUPERFICIES)
    def test_las_plantillas_dejan_el_aviso_vacio(self, superficie):
        html = _texto(TPL / ("%s.html" % superficie))
        assert "data-aviso-carga=" in html
        assert not re.search(
            r'<div class="solo-lectores" role="status">[^<]+</div>', html), (
            "hay un aviso con texto horneado: no se anunciara"
        )

    def test_estados_js_los_rellena_tras_el_render(self):
        js = _texto(JS / "estados.js")
        assert "data-aviso-carga" in js
        assert "DOMContentLoaded" in js


class TestElTituloRecortadoSigueSiendoLegible:
    def test_el_h1_lleva_su_texto_completo_en_title(self):
        """Se recorta con elipsis para que la barra no cambie de alto. El
        lector anuncia el textContent completo, pero quien amplia la pagina sin
        lector se quedaba sin forma de leer el resto (SC 1.4.10)."""
        js = _texto(JS / "dashboard.js")
        assert re.search(r"titulo\.title\s*=", js)
