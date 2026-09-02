"""Plan 4 - T4.8. El formulario de llamadas, fijado.

Es la superficie de uso mas intensivo del panel: se usa llamada tras llamada
durante horas. El plan lo dice sin rodeos — **un rediseno que se vea mejor y se
capture mas lento es un retroceso**. Asi que aqui casi nada es estetica.

Cuatro cosas que arregla, y que no vuelven solas:

  1. **El contenido de la hoja ejecutaba.** `TIENDA`, `CIUDAD` y las opciones de
     la pregunta 1 se interpolaban crudas en `innerHTML`. Un
     `<img src=x onerror=...>` en el nombre de una tienda corria en la pantalla
     del operador — comprobado en navegador antes de corregirlo, no supuesto.
     Es la misma clase que el Plan 3 cerro en el importador (T3.7) y que aqui
     nunca se hizo.

  2. **El teclado no servia.** Al ocultar el paso anterior con `display:none` el
     foco caia a `<body>`, asi que para contestar sin raton habia que tabular
     desde el principio del documento EN CADA UNA de las siete preguntas. Y los
     atajos que las etiquetas prometian -"1 — Respondio", "2 — Buzon",
     "0 — Telefono Incorrecto"- no existian: no habia un solo manejador de
     teclado en el archivo. Los numeros eran decoracion.

  3. **Un fallo de guardado perdia la llamada.** Era un `alert()` que, al
     aceptarlo, devolvia al paso de contacto SIN las respuestas: el operador
     tenia que rehacer la llamada de memoria.

  4. **El vacio celebraba.** "Sin envios con problema. 🎉" festejaba algo que
     tanto puede ser que todo salio bien como que el worker lleva horas caido.
"""
import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
CSS = RAIZ / "static" / "css"
JS = RAIZ / "static" / "js"
TPL = RAIZ / "templates"


def _texto(ruta):
    return ruta.read_text(encoding="utf-8")


def _sin_comentarios_js(texto):
    return re.sub(r"//.*", "", texto)


# ───────────────── el contenido de la hoja no ejecuta ───────────────────────

class TestElContenidoDeLaHojaNoEjecuta:
    """Lo que llega de `LISTA DE CONTACTOS` lo teclea un operador o lo escribe
    el importador desde Places. Ninguna de las dos fuentes es de fiar."""

    def test_la_ficha_de_contacto_escapa_lo_que_pinta(self):
        js = _texto(JS / "formulario.js")
        cuerpo = re.search(r"info-grid'\)\.innerHTML = (.*?);\n", js, re.S)
        assert cuerpo, "no se encuentra el render de la ficha"
        c = cuerpo.group(1)
        assert "esc(f.v)" in c and "esc(f.l)" in c, (
            "la ficha sigue interpolando crudo lo que viene de la hoja"
        )

    def test_las_opciones_de_la_pregunta_1_escapan(self):
        js = _texto(JS / "formulario.js")
        cuerpo = re.search(r"sel-p1'\)\.innerHTML = (.*?);\n", js, re.S).group(1)
        assert "esc(op)" in cuerpo
        assert "onclick=" not in cuerpo, (
            "la opcion sigue viajando dentro de un atributo de codigo"
        )
        assert "data-opcion" in cuerpo

    def test_las_urls_del_contacto_van_por_dataset_y_exigen_http(self):
        """El `replace` de comillas anterior tapaba un caracter y dejaba pasar
        el resto, y no cerraba `javascript:`."""
        js = _texto(JS / "formulario.js")
        assert "data-url=" in js
        assert re.search(r"const seguro = u => /\^https\?:", js) or "^https?:" in js

    def test_existe_el_escapador_y_reusa_el_del_sistema(self):
        js = _texto(JS / "formulario.js")
        assert re.search(r"function esc\(s\)", js)
        assert "Estados.escapar" in js, (
            "hay dos escapadores distintos en el proyecto"
        )

    def test_el_patron_ve_la_interpolacion_cruda_que_se_retiro(self):
        """Control negativo."""
        viejo = '<div class="val">${f.v}</div>'
        assert "${f.v}" in viejo and "esc(" not in viejo


# ────────────────────── la captura se hace con teclado ──────────────────────

class TestLaCapturaSeHaceConTeclado:
    def test_el_foco_viaja_al_cambiar_de_paso(self):
        """Sin esto hay que tabular desde el principio del documento en cada
        una de las siete preguntas, llamada tras llamada."""
        js = _texto(JS / "formulario.js")
        cuerpo = re.search(r"function showStep\(name\)\s*\{(.*?)\n\}", js, re.S)
        assert cuerpo, "no se encuentra showStep"
        assert "prepararPaso" in cuerpo.group(1)

        prep = re.search(r"function prepararPaso\(paso\)\s*\{(.*?)\n\}", js, re.S)
        assert prep and ".focus(" in prep.group(1)

    def test_el_foco_no_va_a_un_boton_deshabilitado(self):
        """En la pregunta 1 el boton "Continuar" nace deshabilitado."""
        js = _texto(JS / "formulario.js")
        prep = re.search(r"function prepararPaso\(paso\)\s*\{(.*?)\n\}", js, re.S).group(1)
        assert "!b.disabled" in prep

    def test_hay_un_manejador_de_teclado_de_verdad(self):
        js = _texto(JS / "formulario.js")
        assert "addEventListener('keydown'" in js
        assert "data-atajo" in js

    def test_la_numeracion_incluye_los_deshabilitados(self):
        """Si se numerara solo lo habilitado, "Continuar" se quedaria sin
        digito — o peor, los numeros cambiarian bajo el dedo del operador al
        marcar una opcion."""
        js = _texto(JS / "formulario.js")
        cuerpo = re.search(r"function opcionesDelPaso\(paso\)\s*\{(.*?)\n\}", js, re.S).group(1)
        assert ":not([disabled])" not in cuerpo
        # Y el disparo si los filtra.
        assert ':not([disabled])' in js, "el manejador dispara sobre deshabilitados"

    def test_el_atajo_no_roba_teclas_a_los_campos(self):
        """El modal de correo y el de telefono se escriben con numeros."""
        js = _texto(JS / "formulario.js")
        assert "INPUT|TEXTAREA|SELECT" in js

    def test_el_atajo_se_calla_con_un_modal_abierto(self):
        js = _texto(JS / "formulario.js")
        assert "modalAbierto" in js

    def test_las_etiquetas_ya_no_prometen_atajos_a_mano(self):
        """Decian "1 — Respondio" y "0 — Telefono Incorrecto" mientras el
        sistema numera 1, 2, 3: dos verdades distintas en la misma pantalla."""
        html = _texto(TPL / "formulario.html")
        for viejo in ("1 — Respondió", "2 — Buzón", "0 — Teléfono Incorrecto"):
            assert viejo not in html, viejo

    def test_el_atajo_se_anuncia(self):
        js = _texto(JS / "formulario.js")
        assert "aria-keyshortcuts" in js
        assert 'aria-hidden' in js, "la pastilla del numero se leeria suelta"

    def test_el_validador_de_numero_acepta_enter(self):
        """Es de las conclusiones mas frecuentes: sin esto hay que tabular del
        campo al boton en cada pedido."""
        html = _texto(TPL / "formulario.html")
        assert "valCatKeydown(event)" in html
        js = _texto(JS / "formulario.js")
        cuerpo = re.search(r"function valCatKeydown\(e\)\s*\{(.*?)\n\}", js, re.S)
        assert cuerpo
        assert "'Enter'" in cuerpo.group(1) and "'Escape'" in cuerpo.group(1)


# ──────────────── un fallo de guardado no pierde la llamada ─────────────────

class TestUnFalloDeGuardadoNoPierdeLaLlamada:
    def test_no_queda_ningun_alert(self):
        js = _sin_comentarios_js(_texto(JS / "formulario.js"))
        assert "alert(" not in js, (
            "alert() bloquea la pagina, roba el foco y al aceptarlo devolvia al "
            "contacto sin las respuestas"
        )

    def test_el_payload_se_arma_aparte_de_enviarse(self):
        """Es lo que hace posible reenviar EXACTAMENTE lo que fallo."""
        js = _texto(JS / "formulario.js")
        assert re.search(r"async function enviarGuardado\(payload\)", js)
        assert re.search(r"function guardar\(\)", js)

    def test_el_fallo_conserva_el_payload(self):
        js = _texto(JS / "formulario.js")
        cuerpo = re.search(r"function fallarGuardado\(motivo, payload\)\s*\{(.*?)\n\}",
                           js, re.S)
        assert cuerpo, "no se encuentra fallarGuardado"
        assert "_ultimoPayload = payload" in cuerpo.group(1)

    def test_el_reintento_reenvia_lo_mismo(self):
        js = _texto(JS / "formulario.js")
        cuerpo = re.search(r"async function reintentarGuardado\(\)\s*\{(.*?)\n\}",
                           js, re.S).group(1)
        assert "enviarGuardado(payload)" in cuerpo

    def test_hay_un_paso_propio_para_el_fallo(self):
        html = _texto(TPL / "formulario.html")
        assert 'id="step-guardado-error"' in html
        assert 'id="btn-reintentar-guardado"' in html
        js = _texto(JS / "formulario.js")
        assert "'guardado-error'" in js, "el paso no esta registrado en PASOS"

    def test_el_fallo_de_guardado_interrumpe(self):
        """Bloquea la tarea del operador: no puede seguir llamando hasta
        resolverlo. `status` (polite) puede perderse."""
        html = _texto(TPL / "formulario.html")
        bloque = html[html.index('id="step-guardado-error"'):]
        assert 'role="alert"' in bloque[:400]


# ─────────────────── la confirmacion es inequivoca ──────────────────────────

class TestLaConfirmacionEsInequivoca:
    def test_el_guardado_se_anuncia(self):
        html = _texto(TPL / "formulario.html")
        bloque = html[html.index('id="step-siguiente"'):]
        assert 'role="status"' in bloque[:300]

    def test_el_resumen_dice_que_se_guardo(self):
        js = _texto(JS / "formulario.js")
        assert "resumen-guardado" in js
        cuerpo = re.search(r"async function enviarGuardado\(payload\)\s*\{(.*?)\n\}",
                           js, re.S).group(1)
        assert "payload.tienda" in cuerpo and "payload.resultado" in cuerpo, (
            "el resumen sale del estado global y no de lo que de verdad se envio"
        )

    def test_los_iconos_de_remate_son_decorativos(self):
        html = _texto(TPL / "formulario.html")
        for icono in ("✅", "🎉"):
            i = html.find(icono)
            assert i > 0, icono
            # El contenedor mas cercano lleva aria-hidden.
            assert 'aria-hidden="true"' in html[max(0, i - 60):i], icono


# ──────────────────── la celebracion queda reservada ────────────────────────

class TestElVacioNoCelebra:
    def test_no_queda_confeti_en_un_estado_vacio(self):
        # Sin comentarios: el comentario que explica POR QUE se retiro el
        # confeti lo cita, y mirar el archivo entero pone el test en rojo por
        # su propia documentacion. Es la quinta vez que pasa en esta tanda.
        js = _sin_comentarios_js(_texto(JS / "formulario.js"))
        assert "🎉" not in js, (
            "un vacio puede significar que todo salio bien o que el worker "
            "lleva horas caido, y la pantalla no sabe cual de las dos"
        )

    def test_el_patron_ve_la_celebracion_que_se_retiro(self):
        viejo = "Sin envíos con problema. 🎉"
        assert "🎉" in viejo


# ─────────────────────────── sin regresiones ────────────────────────────────

# ───────────── lo que encontraron los reviewers de la T4.8 ─────────────────

class TestElAtajoTambienSeOye:
    """Hallazgo MEDIUM de `code-reviewer`, y es una REGRESION que yo introduje.

    Los tres botones del paso p0 llevaban el digito escrito en el texto
    visible ("1 — Respondio"), asi que un lector de pantalla lo anunciaba como
    parte del nombre del boton. Al mover el digito a un `<kbd aria-hidden>`,
    quien ve la pantalla lo conservo y quien la escucha lo perdio:
    `aria-keyshortcuts` es metadata que NVDA, JAWS y VoiceOver no anuncian por
    defecto. El cambio dejaba a ese operador PEOR que antes."""

    def test_el_digito_va_en_el_nombre_accesible(self):
        js = _texto(JS / "formulario.js")
        prep = re.search(r"function prepararPaso\(paso\)\s*\{(.*?)\n\}", js, re.S).group(1)
        assert "setAttribute('aria-label'" in prep, (
            "el digito solo existe para quien ve la pantalla"
        )
        assert "digito + '. '" in prep

    def test_la_pastilla_no_se_lee_dos_veces(self):
        js = _texto(JS / "formulario.js")
        prep = re.search(r"function prepararPaso\(paso\)\s*\{(.*?)\n\}", js, re.S).group(1)
        assert "aria-hidden" in prep

    def test_el_texto_se_guarda_antes_de_meter_la_pastilla(self):
        """Despues ya no se puede distinguir el digito del nombre de la
        opcion, y el `aria-label` saldria con el numero repetido."""
        js = _texto(JS / "formulario.js")
        prep = re.search(r"function prepararPaso\(paso\)\s*\{(.*?)\n\}", js, re.S).group(1)
        assert "dataset.etiqueta" in prep
        assert prep.index("dataset.etiqueta") < prep.index("btn.prepend(kbd)")


class TestLaPestanaNuevaNoPuedeTocarLaDelPanel:
    """MEDIUM de `security-reviewer`. Sin `noopener`, la pestana que se abre
    conserva `window.opener` y puede redirigir la del panel. Un sitio que imite
    el login, con el operador convencido de que su pestana de siempre sigue
    ahi, es una via barata de robo de credenciales. La URL sale de la hoja, que
    edita gente y alimenta el importador desde Places."""

    def test_abrir_ventana_usa_noopener(self):
        js = _texto(JS / "formulario.js")
        cuerpo = re.search(r"function abrirVentana\(url\)\s*\{(.*?)\n\}", js, re.S).group(1)
        assert "noopener" in cuerpo, "reverse tabnabbing"
        assert "noreferrer" in cuerpo

    def test_solo_se_abren_urls_http(self):
        js = _texto(JS / "formulario.js")
        assert "https?:" in js, "no se filtra el esquema de la URL"


class TestNoQuedaCodigoDentroDeAtributos:
    """LOW de `security-reviewer`. El listado de envios con problema conservaba
    el patron `onclick='abrirCorregir(${JSON.stringify(e)...})'` que este mismo
    commit retiro de la ficha de contacto y de las opciones. No era explotable
    -el `replace` de comillas aguantaba-, pero dejar una excepcion es dejar el
    patron que el siguiente copiara."""

    def test_el_envio_viaja_por_dataset(self):
        js = _texto(JS / "formulario.js")
        assert "data-envio=" in js
        assert "btn--corregir" in js

    def test_no_queda_json_stringify_dentro_de_un_onclick(self):
        js = _sin_comentarios_js(_texto(JS / "formulario.js"))
        assert not re.search(r"onclick=['\"][^'\"]*JSON\.stringify", js)

    def test_el_dataset_se_lee_con_guarda(self):
        """Un `JSON.parse` de algo que llego del servidor puede reventar."""
        js = _texto(JS / "formulario.js")
        assert re.search(r"JSON\.parse\(caja\.dataset\.envio\)", js)
        i = js.index("JSON.parse(caja.dataset.envio)")
        assert "try {" in js[max(0, i - 120):i]


class TestElComentarioNoMienteSobreElOrigen:
    def test_las_opciones_de_p1_se_declaran_como_constantes(self):
        """El comentario decia que "tambien sale de la hoja". No: son seis
        cadenas fijas. Un comentario que miente sobre el origen de un dato hace
        que el siguiente de por cubierta una fuente que no lo esta."""
        js = _texto(JS / "formulario.js")
        cuerpo = re.search(r"function renderP1\(\)\s*\{(.*?)\n\}", js, re.S).group(1)
        assert "CONSTANTES del codigo" in cuerpo
        assert "tambien sale de la hoja" not in cuerpo


class TestElBarridoNoSeEsquiva:
    """MEDIUM de `security-reviewer`. El numero sintetico se componia en
    tiempo de ejecucion (`"55" + "5" * 8`) para que el regex del barrido no lo
    viera. Funcionaba, y ese es el problema: no se lee como una excepcion al
    mirar el diff, y normaliza un bypass que -aplicado por costumbre a un
    numero real- dejaria pasar una fuga sin que nadie se entere. El proyecto ya
    define una marca auditable para esto."""

    def test_el_numero_de_prueba_usa_la_marca_del_proyecto(self):
        h = _texto(RAIZ / "tools" / "verificar_formulario.py")
        linea = [l for l in h.splitlines() if "TEL_SINTETICO =" in l]
        assert linea, "no se encuentra el numero de prueba"
        assert "barrido-ok:" in linea[0], (
            "la excepcion se esconde del barrido en vez de declararse"
        )

    def test_la_marca_lleva_motivo(self):
        """`barrido-ok` a secas silenciaria una linea sin explicar por que."""
        h = _texto(RAIZ / "tools" / "verificar_formulario.py")
        linea = [l for l in h.splitlines() if "TEL_SINTETICO =" in l][0]
        motivo = linea.split("barrido-ok:", 1)[1].strip()
        assert len(motivo) > 10, repr(motivo)

    def test_no_se_compone_la_cadena_para_esquivar_el_regex(self):
        h = _sin_comentarios_js(_texto(RAIZ / "tools" / "verificar_formulario.py"))
        assert '"55" + "5" * 8' not in h


class TestSinRegresiones:
    def test_el_formulario_sigue_sin_colores_literales(self):
        for archivo in (CSS / "formulario.css", TPL / "formulario.html",
                        JS / "formulario.js"):
            assert not re.findall(r"#[0-9a-fA-F]{3,8}\b", _texto(archivo)), archivo.name

    def test_el_formulario_sigue_quieto(self):
        """Registro "denso y quieto" del ADR: los pasos NO llevan animacion de
        entrada. La velocidad de captura manda sobre la estetica."""
        js = _texto(JS / "formulario.js")
        assert "seccion-entra" not in js and "escalonarFilas" not in js

    def test_sigue_sin_transiciones_de_layout(self):
        css = re.sub(r"/\*.*?\*/", "", _texto(CSS / "formulario.css"), flags=re.S)
        malas = re.findall(
            r"transition:\s*(all|border|background|width|height|top|left)(?![-\w])", css)
        assert not malas, malas

    @pytest.mark.parametrize("herramienta", ["verificar_formulario.py"])
    def test_la_verificacion_en_navegador_existe(self, herramienta):
        """El gate de la tarea pide una captura cronometrada solo con teclado.
        Ningun test de patron puede hacer eso."""
        h = _texto(RAIZ / "tools" / herramienta)
        assert "pulsaciones" in h and "keyboard.press" in h
