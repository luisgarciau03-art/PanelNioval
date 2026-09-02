"""Plan 4 - T4.9. El importador, fijado.

Es la superficie donde convergen los cuatro planes: los contadores del Plan 3,
el medidor de gasto del Plan 2, el catalogo nacional del Plan 1 y el sistema de
diseno de las tareas T4.4-T4.6. Esta tarea no rehace nada de eso; le da forma.

Lo que arregla, y que no vuelve solo:

  1. **Filtrar reconstruia los 606 chips.** Cada pulsacion del buscador rehacia
     el `innerHTML` entero de la lista: 713 ms en el peor caso, medidos en
     navegador con el catalogo completo. Ahora se construyen una vez y el
     filtro solo oculta: 3.1 ms el peor caso, mismo protocolo.

  2. **Ni un chip era alcanzable con teclado.** Eran 606 `<span>` con manejador
     de clic delegado: sin `role`, sin `tabindex` y sin manejador de teclado.
     Ahora son un `listbox` con UNA parada de tabulacion y flechas que saltan
     lo que el filtro oculta.

  3. **Los cuatro finales se veian iguales.** `done`, `cancelado`,
     `presupuesto_agotado` y `error` compartian caja, fondo y color de titulo;
     solo cambiaba el emoji. Detener a mano y quedarse sin presupuesto no son
     fallos, y tampoco son exitos.

  4. **Cuatro `alert()` y un `confirm()`** bloqueaban la pagina y robaban el
     foco. Es la misma clase que la T4.8 cerro en el formulario.

  5. **El registro se reescribia entero en cada sondeo**, asi que parpadeaba y
     arrastraba el scroll de quien estuviera leyendo mas arriba.

La verificacion en navegador vive en `tools/verificar_importador.py` (44
comprobaciones, 30 de ellas en rojo contra el codigo anterior).
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
    """Quita comentarios de linea y de bloque.

    Un guarda que busca el patron prohibido en el archivo ENTERO lo encuentra
    en el comentario que explica por que se retiro. Paso cinco veces en esta
    misma tanda.
    """
    texto = re.sub(r"/\*.*?\*/", "", texto, flags=re.S)
    return re.sub(r"//.*", "", texto)


def _sin_comentarios_css(texto):
    return re.sub(r"/\*.*?\*/", "", texto, flags=re.S)


@pytest.fixture(scope="module")
def js():
    return _texto(JS / "importador.js")


@pytest.fixture(scope="module")
def css():
    return _texto(CSS / "importador.css")


@pytest.fixture(scope="module")
def html():
    return _texto(TPL / "importador.html")


# ───────────────── los chips se construyen una vez ──────────────────────────

class TestLosChipsNoSeReconstruyenAlFiltrar:
    """713 ms en el peor caso, medidos. El coste no era el filtro: era volver a
    generar y a parsear 606 nodos en cada tecla."""

    def test_filtrar_no_llama_al_constructor(self, js):
        cuerpo = _cuerpo(js, "filtrarCiudades")
        assert "renderChips" not in cuerpo, (
            "filtrarCiudades vuelve a construir la lista entera"
        )

    def test_filtrar_no_escribe_innerhtml_de_la_lista(self, js):
        cuerpo = _sin_comentarios_js(_cuerpo(js, "filtrarCiudades"))
        assert "innerHTML" not in cuerpo, (
            "filtrar sigue reescribiendo el HTML de los chips"
        )

    def test_filtrar_oculta_con_el_atributo_hidden(self, js):
        cuerpo = _cuerpo(js, "filtrarCiudades")
        assert ".hidden" in cuerpo, "el filtro no oculta: algo reconstruye"

    def test_solo_se_escribe_hidden_cuando_cambia(self, js):
        """Asignar `hidden` a los 606 en cada pulsacion invalida el estilo de
        todos aunque el valor sea el mismo."""
        cuerpo = _cuerpo(js, "filtrarCiudades")
        assert re.search(r"if \(c\.el\.hidden === casa\)", cuerpo), (
            "el filtro escribe hidden sin mirar si cambia"
        )

    def test_el_texto_buscable_se_calcula_al_construir(self, js):
        """`toLowerCase()` dentro del filtro son 606 conversiones por tecla."""
        assert "buscable:" in _sin_comentarios_js(_cuerpo(js, "renderChips"))
        filtro = _sin_comentarios_js(_cuerpo(js, "filtrarCiudades"))
        assert "c.buscable.includes(q)" in filtro, (
            "el filtro no usa el texto precalculado"
        )
        # UNA conversion por pulsacion -la del texto tecleado- y ninguna sobre
        # los nombres de las 606 ciudades.
        assert filtro.count("toLowerCase") == 1, (
            "el nombre de cada ciudad se vuelve a pasar a minusculas en cada tecla"
        )

    def test_el_filtro_sigue_combinando_region_y_texto(self, js):
        cuerpo = _cuerpo(js, "filtrarCiudades")
        assert "region" in cuerpo and "includes(q)" in cuerpo


# ───────────────── agrupacion por macro-region ──────────────────────────────

class TestAgrupacionPorMacroRegion:
    """606 chips en una lista plana son un muro. El plan pide agrupacion y
    contador por grupo."""

    def test_renderchips_emite_un_grupo_por_region(self, js):
        cuerpo = _cuerpo(js, "renderChips")
        assert 'role="group"' in cuerpo
        assert "data-region=" in cuerpo

    def test_cada_grupo_lleva_su_conteo(self, js):
        cuerpo = _cuerpo(js, "renderChips")
        assert "grupo__conteo" in cuerpo and "data-conteo" in cuerpo

    def test_el_conteo_del_grupo_se_actualiza_al_filtrar(self, js):
        cuerpo = _cuerpo(js, "filtrarCiudades")
        assert "grupo.conteo" in cuerpo and "de " in cuerpo, (
            "el conteo por grupo se pinta una vez y se queda rancio"
        )

    def test_un_grupo_sin_coincidencias_se_retira_entero(self, js):
        cuerpo = _cuerpo(js, "filtrarCiudades")
        assert "grupo.el.hidden" in cuerpo, (
            "la cabecera de una region vacia se queda sola en pantalla"
        )

    def test_el_orden_de_los_grupos_sale_de_la_prioridad(self, js):
        """El catalogo llega ordenado por prioridad (Plan 1). Agrupar por orden
        de llegada conserva ese ranking: la region de la ciudad numero 1 del
        pais va primera. Ordenar los grupos por nombre lo destruiria."""
        cuerpo = _cuerpo(js, "renderChips")
        assert "new Map()" in cuerpo, "sin Map no hay orden de insercion garantizado"
        assert not re.search(r"porRegion.*\.sort\(", cuerpo), (
            "los grupos se reordenan y el ranking del Plan 1 deja de leerse"
        )

    def test_el_rango_global_sigue_saliendo_del_catalogo_completo(self, js):
        """B11 del Plan 1: si el rango se calculara por grupo, la primera
        ciudad de cada region llevaria medalla de oro."""
        assert re.search(r"\.rank\s*=", _cuerpo(js, "cargarCiudades"))
        assert "c.rank" in _cuerpo(js, "renderChips")


# ───────────────── el teclado llega a los chips ─────────────────────────────

class TestLosChipsSeUsanConTeclado:
    """Hallazgo estructural: 606 opciones y ni una alcanzable sin raton."""

    def test_la_lista_es_un_listbox_y_los_chips_opciones(self, js):
        cuerpo = _cuerpo(js, "renderChips")
        assert 'role="listbox"' in cuerpo
        assert 'role="option"' in cuerpo

    def test_hay_manejador_de_teclado(self, js):
        assert "addEventListener('keydown'" in js, (
            "sin manejador de teclado los chips solo responden al raton"
        )

    def test_las_flechas_y_los_extremos_estan_cubiertos(self, js):
        for tecla in ("ArrowRight", "ArrowLeft", "ArrowUp", "ArrowDown", "Home", "End"):
            assert tecla in js, f"la tecla {tecla} no se maneja"

    def test_enter_y_espacio_eligen(self, js):
        assert re.search(r"ev\.key === 'Enter' \|\| ev\.key === ' '", js)

    def test_una_sola_parada_de_tabulacion(self, js):
        """606 paradas de tabulacion serian peor que ninguna: el operador
        tendria que atravesarlas todas para llegar al boton Buscar."""
        cuerpo = _cuerpo(js, "fijarParadaDeTabulacion")
        assert cuerpo, "no existe la funcion que reparte el tabindex"
        assert "-1" in cuerpo and "0" in cuerpo

    def test_la_parada_se_recoloca_al_filtrar(self, js):
        assert "fijarParadaDeTabulacion()" in _cuerpo(js, "filtrarCiudades"), (
            "tras filtrar, el tabindex puede quedarse en un chip oculto"
        )

    def test_las_flechas_solo_recorren_lo_visible(self, js):
        assert "chipsVisibles()" in js
        assert "hidden" in _cuerpo(js, "chipsVisibles")

    def test_elegir_no_recorre_los_606_chips(self, js):
        """Antes: `querySelectorAll('.chip-ciudad').forEach(...)` en cada clic."""
        cuerpo = _sin_comentarios_js(_cuerpo(js, "elegirChip"))
        assert "querySelectorAll" not in cuerpo, (
            "elegir una ciudad vuelve a recorrer la lista entera"
        )
        assert "chipElegido" in cuerpo

    def test_el_nombre_accesible_del_chip_no_deja_el_porcentaje_suelto(self, js):
        cuerpo = _cuerpo(js, "renderChips")
        assert "aria-label=" in cuerpo and "de interes" in cuerpo


# ───────────────── lo que viene de la hoja no ejecuta ───────────────────────

class TestElNombreDeCiudadSigueEscapado:
    """El nombre viene de LISTA DE CONTACTOS, y antes de eso lo tecleo un
    operador. La T4.9 anade dos sitios nuevos donde se interpola -el
    `aria-label` y el `data-region` de la cabecera de grupo- y los dos escapan."""

    def test_el_nombre_pasa_por_el_escapador(self, js):
        assert "escaparHtml(c.ciudad)" in _cuerpo(js, "renderChips")

    def test_la_region_de_la_cabecera_tambien_se_escapa(self, js):
        cuerpo = _cuerpo(js, "renderChips")
        assert re.search(r"const r = escaparHtml\(region\)", cuerpo), (
            "la region se interpola cruda en la cabecera y en data-region"
        )

    def test_el_aria_label_usa_el_nombre_ya_escapado(self, js):
        cuerpo = _cuerpo(js, "renderChips")
        etiqueta = re.search(r"const etiqueta = (.*?);\n", cuerpo, re.S)
        assert etiqueta, "no se encuentra la etiqueta accesible"
        assert "${nombre}" in etiqueta.group(1) and "c.ciudad" not in etiqueta.group(1)

    def test_la_linea_del_registro_no_pasa_por_innerhtml(self, js):
        """El log trae nombres de Places y de la hoja. `textContent` no
        interpreta marcado, asi que no hace falta escapar ni confiar."""
        cuerpo = _cuerpo(js, "pintarLog")
        assert "textContent = l" in cuerpo
        assert "innerHTML" not in _sin_comentarios_js(cuerpo)


# ───────────────── ni un dialogo del navegador ──────────────────────────────

class TestNoQuedanDialogosDelNavegador:
    def test_no_queda_ningun_alert_ni_confirm(self, js):
        limpio = _sin_comentarios_js(js)
        assert "alert(" not in limpio, (
            "alert() bloquea la pagina y roba el foco; ademas al aceptarlo no "
            "deja rastro de lo que dijo"
        )
        assert "confirm(" not in limpio, (
            "confirm() no deja leer el estado de la corrida mientras decides"
        )

    def test_el_patron_ve_los_dialogos_que_se_retiraron(self):
        """Control negativo: literal escrito aqui, sin depender de ningun
        archivo. Si el patron no ve estos, su cero no vale nada."""
        viejo = "alert('Ingresa una ciudad'); if (!confirm('¿Detener?')) return;"
        limpio = _sin_comentarios_js(viejo)
        assert "alert(" in limpio and "confirm(" in limpio

    def test_el_comentario_que_explica_el_cambio_no_dispara_el_guarda(self, js):
        """El propio archivo documenta por que se retiraron. Sin quitar
        comentarios, el guarda se dispararia con su propia explicacion."""
        assert "alert(" in js or "confirm(" in js, (
            "si el archivo ya no menciona alert/confirm ni en comentarios, este "
            "control sobra: quitalo en vez de relajarlo"
        )

    def test_la_ciudad_vacia_se_avisa_junto_al_campo(self, js):
        cuerpo = _cuerpo(js, "iniciar")
        assert "aria-invalid" in cuerpo and "campo.focus()" in cuerpo

    def test_detener_se_confirma_en_la_pagina(self, js):
        cuerpo = _cuerpo(js, "pedirDetener")
        assert "btn-detener-si" in cuerpo and "btn-detener-no" in cuerpo
        assert "focus()" in cuerpo, "la confirmacion aparece sin llevarse el foco"


# ───────────────── los cuatro finales se distinguen ─────────────────────────

class TestLosFinalesSonEstadosDePrimeraClase:
    """`cancelado` y `presupuesto_agotado` no son errores: son decisiones, una
    del operador y otra del presupuesto. Pero tampoco completaron, asi que no
    se visten de exito (ADR, voto del Critico)."""

    ESTADOS = ("done", "cancelado", "presupuesto_agotado", "interrumpido", "error")

    def test_cada_estado_tiene_su_presentacion(self, js):
        mapa = re.search(r"CLASE_RESULTADO = \{(.*?)\}", js, re.S)
        assert mapa, "no hay una clase por estado terminal"
        for estado in self.ESTADOS:
            assert re.search(rf"{estado}:\s*'resultado--", mapa.group(1)), (
                f"falta la presentacion de {estado}"
            )

    def test_solo_done_se_viste_de_exito(self, js):
        mapa = re.search(r"CLASE_RESULTADO = \{(.*?)\}", js, re.S).group(1)
        con_exito = re.findall(r"(\w+):\s*'resultado--exito'", mapa)
        assert con_exito == ["done"], f"tambien celebran: {con_exito}"

    def test_ni_cancelado_ni_el_tope_se_visten_de_error(self, js):
        mapa = re.search(r"CLASE_RESULTADO = \{(.*?)\}", js, re.S).group(1)
        for estado in ("cancelado", "presupuesto_agotado"):
            clase = re.search(rf"{estado}:\s*'([^']+)'", mapa).group(1)
            assert clase != "resultado--error", (
                f"{estado} se presenta como un fallo, y no lo es"
            )

    def test_solo_el_fallo_interrumpe_al_lector(self, js):
        cuerpo = _cuerpo(js, "vestirResultado")
        assert "'alert'" in cuerpo and "'status'" in cuerpo
        assert re.search(r"status === 'error' \? 'alert' : 'status'", cuerpo)

    def test_las_cuatro_clases_existen_en_el_css(self, css):
        for clase in ("resultado--exito", "resultado--detenido",
                      "resultado--tope", "resultado--error"):
            assert f".{clase}" in css, f"{clase} no tiene estilo: se veria igual"

    def test_los_fondos_de_los_cuatro_finales_son_distintos(self, css):
        limpio = _sin_comentarios_css(css)
        fondos = {}
        for clase in ("resultado--exito", "resultado--detenido",
                      "resultado--tope", "resultado--error"):
            regla = re.search(rf"\.{clase} \{{([^}}]*)\}}", limpio)
            assert regla, f"no se encuentra la regla de {clase}"
            fondo = re.search(r"background:\s*([^;]+)", regla.group(1))
            assert fondo, f"{clase} no fija fondo"
            fondos[clase] = fondo.group(1).strip()
        assert len(set(fondos.values())) == 4, f"dos finales comparten fondo: {fondos}"

    def test_el_icono_sigue_saliendo_del_estado(self, js):
        mapa = re.search(r"ICONO_RESULTADO = \{(.*?)\}", js, re.S)
        assert mapa
        for estado in ("cancelado", "presupuesto_agotado", "interrumpido", "error"):
            icono = re.search(rf"{estado}:\s*'([^']*)'", mapa.group(1))
            assert icono and "✅" not in icono.group(1)


# ───────────────── el registro cuenta la corrida ────────────────────────────

class TestElRegistroSeAnade:
    def test_pintar_log_anade_en_vez_de_reasignar(self, js):
        cuerpo = _sin_comentarios_js(_cuerpo(js, "pintarLog"))
        assert "appendChild" in cuerpo
        assert "innerHTML" not in cuerpo, (
            "reescribir el bloque entero hace parpadear el registro y reinicia "
            "la animacion de todas las lineas en cada sondeo"
        )

    def test_solo_se_anaden_las_lineas_nuevas(self, js):
        """El backend manda las diez ultimas, asi que la ventana se desplaza."""
        cuerpo = _cuerpo(js, "pintarLog")
        assert "comunes" in cuerpo and "slice(comunes)" in cuerpo

    def test_el_scroll_solo_sigue_si_ya_estaba_al_final(self, js):
        cuerpo = _cuerpo(js, "pintarLog")
        assert "alFinal" in cuerpo
        assert re.search(r"if \(alFinal\) caja\.scrollTop", cuerpo), (
            "el registro arrastra al operador al final aunque este leyendo arriba"
        )

    def test_el_registro_no_crece_sin_limite(self, js):
        assert "MAX_LINEAS_LOG" in js

    def test_la_entrada_nueva_se_anima_solo_si_hay_movimiento(self, js):
        cuerpo = _cuerpo(js, "pintarLog")
        assert "MOVIMIENTO_REDUCIDO.matches" in cuerpo
        assert "fila-entra" in cuerpo

    def test_la_clase_de_entrada_se_retira_al_terminar(self, js):
        """Deuda anotada en la T4.6: `escalonarFilas` no la retira. El codigo
        nuevo no la hereda."""
        cuerpo = _cuerpo(js, "pintarLog")
        assert "animationend" in cuerpo and "classList.remove('fila-entra')" in cuerpo


# ───────────────── jerarquia y sistema de diseno ────────────────────────────

class TestLaPantallaUsaElSistema:
    def test_los_contadores_usan_el_componente_del_sistema(self, html):
        """`.stat` y `.stat--principal` se escribieron en la T4.4 para esta
        pantalla y nadie los usaba: el importador mantenia su `.stat-box`."""
        assert 'class="stat stat--principal' in html
        assert html.count('class="stat"') >= 3

    def test_el_numero_grande_es_nuevos_en_sheet(self, html):
        bloque = re.search(r'<div class="stat stat--principal[^>]*>(.*?)</div>\s*</div>',
                           html, re.S)
        assert bloque, "no se encuentra el contador principal"
        assert 'id="s-nuevos"' in bloque.group(1), (
            "el numero grande no es el de filas realmente escritas en la hoja"
        )

    def test_la_consola_declara_su_pila_monoespaciada(self, css):
        """El ADR lo pide por su nombre: `monospace` a secas deja la fuente a
        merced del navegador."""
        limpio = _sin_comentarios_css(css)
        regla = re.search(r"\.log-box \{([^}]*)\}", limpio)
        assert regla, "no se encuentra .log-box"
        assert "font-family" not in regla.group(1), (
            "la consola vuelve a fijar su fuente en vez de heredar .consola"
        )
        assert 'class="consola log-box"' in _texto(TPL / "importador.html")

    def test_la_consola_con_scroll_es_alcanzable_con_teclado(self, html):
        assert re.search(r'id="log-box"[^>]*tabindex="0"', html) or \
               re.search(r'tabindex="0"[^>]*id="log-box"', html), (
            "una caja con scroll que no recibe foco no se puede recorrer (SC 2.1.1)"
        )

    def test_la_fase_tiene_su_propio_sitio_junto_al_progreso(self, html):
        assert 'id="prog-fase"' in html
        assert re.search(r'id="prog-track"[^>]*aria-labelledby="prog-fase"', html)

    def test_el_logo_tiene_texto_alternativo(self, html):
        logo = re.search(r"<img[^>]*cloudinary[^>]*>", html, re.S)
        assert logo and 'alt="NIOVAL"' in logo.group(0)

    def test_los_paneles_se_ocultan_con_hidden(self, html):
        """`style="display:none"` gana a cualquier hoja y deja la region fuera
        del arbol de accesibilidad sin decirlo. `hidden` es lo que el sistema
        declara en base.css."""
        assert 'style="display:none"' not in html
        for panel in ("progress-box", "stats-row", "log-seccion", "result-box"):
            assert re.search(rf'id="{panel}"[^>]*hidden', html) or \
                   re.search(rf'hidden[^>]*id="{panel}"', html), (
                f"{panel} no arranca oculto con el atributo hidden"
            )

    def test_el_js_no_vuelve_a_escribir_style_display(self, js):
        assert "style.display" not in _sin_comentarios_js(js)

    def test_el_css_no_trae_ni_un_color_literal(self, css):
        """CE3. tokens.css es el unico sitio donde puede vivir un hex."""
        limpio = _sin_comentarios_css(css)
        assert not re.findall(r"#[0-9a-fA-F]{3,8}\b", limpio)
        assert not re.findall(r"\brgba?\(", limpio)

    def test_el_patron_de_color_ve_un_hex_de_verdad(self):
        """Control negativo del apartado anterior."""
        assert re.findall(r"#[0-9a-fA-F]{3,8}\b", ".x{color:#00CC47}")


# ───────────── lo que encontraron los tres gates de la T4.9 ────────────────

class TestLoQueEncontraronLosGates:
    """`code-reviewer` APROBÓ sin CRITICAL ni HIGH, `security-reviewer` no halló
    ningún vector nuevo, y `a11y-architect` encontró 1 CRITICAL y 2 HIGH que
    ninguno de los otros dos vio. Cada arreglo queda fijado aquí."""

    def test_el_conteo_del_chip_no_apoya_su_color_en_la_opacidad(self, css):
        """CRITICAL de accesibilidad. `--texto` al 55 % sobre blanco da 2.97:1 y
        **ningún guarda de tokens lo atrapa**: el color declarado sí es un token;
        lo que rompe el contraste es la opacidad, que nadie mide."""
        limpio = _sin_comentarios_css(css)
        regla = re.search(r"\.chip-ciudad \.pct \{([^}]*)\}", limpio)
        assert regla, "no se encuentra el conteo del chip"
        assert "opacity" not in regla.group(1), (
            "el conteo vuelve a fiar su contraste a la opacidad"
        )
        assert "var(--texto-suave)" in regla.group(1)

    def test_el_borde_del_chip_destacado_usa_el_token_accesible(self, css):
        """`--exito-vivo` contra `--exito-tinte` da 2.1:1, por debajo del 3:1 de
        WCAG 1.4.11. Aquí el borde de color SUSTITUYE al del control, así que no
        vale la excepción de «franja decorativa»."""
        limpio = _sin_comentarios_css(css)
        regla = re.search(r"\.chip-ciudad\.top \{([^}]*)\}", limpio)
        assert regla and "border-color: var(--exito)" in regla.group(1)
        assert "--exito-vivo" not in regla.group(1)

    def test_la_confirmacion_no_se_anuncia_como_dialogo_modal(self, js):
        """HIGH. `alertdialog` promete `aria-modal`, trampa de foco y el resto de
        la página inerte. No hay ninguna de las tres **a propósito**: el ADR
        descarta el bloqueo del `confirm()`."""
        # Sin quitar comentarios, el guarda se dispara con el comentario que
        # explica por qué se retiró `alertdialog`. Van ocho en esta tanda.
        cuerpo = _sin_comentarios_js(_cuerpo(js, "pedirDetener"))
        assert "alertdialog" not in cuerpo, (
            "se anuncia como diálogo modal algo que no bloquea nada"
        )
        assert 'role="group"' in cuerpo and "aria-describedby" in cuerpo

    def test_el_foco_arranca_en_la_opcion_segura(self, js):
        """Un Enter reflejo no puede cancelar la corrida."""
        cuerpo = _cuerpo(js, "pedirDetener")
        assert re.search(r"if \(no\) no\.focus\(\);", cuerpo), (
            "el foco arranca en el botón destructivo"
        )

    def test_confirmar_la_detencion_no_pierde_el_foco(self, js):
        """HIGH. `cerrarConfirmacionDetener` destruye el botón que tenía el foco;
        sin recolocarlo, el navegador lo devuelve a `<body>`."""
        cuerpo = _cuerpo(js, "cancelar")
        assert "focus()" in cuerpo

    def test_la_fase_recuerda_que_se_pidio_detener(self, js):
        """El worker mira la bandera ENTRE pasos, así que el siguiente sondeo
        sigue diciendo 'running': «Deteniendo…» aparecía y desaparecía."""
        assert "detencionPedida" in js
        assert "detencionPedida && d.status === 'running'" in _cuerpo(js, "pintarEstado")

    def test_una_corrida_nueva_no_hereda_el_medidor_de_la_anterior(self, js):
        cuerpo = _cuerpo(js, "limpiarPantalla")
        assert "m-llamadas" in cuerpo and "m-costo" in cuerpo

    def test_el_registro_se_anuncia_como_registro(self, html):
        """`role="region"` es un landmark y no implica región viva: las líneas
        nuevas no llegaban al lector."""
        assert re.search(r'id="log-box"[^>]*role="log"', html)

    def test_el_resumen_de_chips_no_interrumpe_en_cada_tecla(self, js, html):
        """4.1.3: `filtrarCiudades` corre en el `oninput`, así que una región
        viva ahí dentro interrumpe una vez por letra tecleada."""
        assert 'id="chips-resumen"' in html and 'aria-hidden="true"' in html
        assert 'id="chips-resumen-lectores"' in html
        cuerpo = _cuerpo(js, "pintarResumenChips")
        assert "setTimeout" in cuerpo and "RETARDO_ANUNCIO" in cuerpo

    def test_el_estado_de_la_categoria_no_va_solo_en_el_color(self, js):
        cuerpo = _cuerpo(js, "pintarEstado")
        assert "cat-estado-" in cuerpo and "aria-current" in cuerpo

    def test_los_avisos_del_catalogo_llevan_rol(self, js):
        """Se saltan `Estados.*`, así que el rol hay que ponerlo a mano."""
        assert 'aviso-catalogo aviso-catalogo--error" role="alert"' in js
        assert 'aviso-catalogo" role="status"' in js

    def test_elegir_reparte_la_parada_de_tabulacion(self, js):
        """Encontrado releyendo el diff, no por un gate: poner `tabIndex = 0` en
        el elegido sin apagar el que ya la tenía deja DOS paradas."""
        cuerpo = _sin_comentarios_js(_cuerpo(js, "elegirChip"))
        assert "fijarParadaDeTabulacion()" in cuerpo
        assert "chip.tabIndex = 0" not in cuerpo

    def test_escribir_a_mano_apaga_la_marca_del_chip(self, js):
        assert re.search(r"getElementById\('input-ciudad'\)\.addEventListener\('input'", js)


# ───────────── el fuente no lleva bytes de control ──────────────────────────

class TestElFuenteEsTextoDeVerdad:
    """El separador de ventanas del registro se escribió como byte NUL **crudo**
    dentro del archivo, no como el escape `\\u0000`.

    Funcionaba, y ese era el problema: `grep` trata como binario cualquier
    archivo con bytes raros y **suprime las coincidencias sin avisar de forma
    evidente**, que es exactamente el fallo de barrido que el CLAUDE.md del
    entorno documenta. Un secreto en ese archivo habría sido invisible para
    `tools/barrer_secretos.py`.
    """

    RUTAS = ("static/js", "static/css", "templates", "tools", "tests")

    def test_ningun_fuente_lleva_un_byte_nul(self):
        culpables = []
        for carpeta in self.RUTAS:
            for ruta in (RAIZ / carpeta).rglob("*"):
                if not ruta.is_file() or "__pycache__" in ruta.parts:
                    continue
                if ruta.suffix not in (".js", ".css", ".html", ".py", ".md"):
                    continue
                if b"\x00" in ruta.read_bytes():
                    culpables.append(str(ruta.relative_to(RAIZ)))
        assert not culpables, (
            "estos archivos son 'binarios' para grep y el barrido de secretos "
            "no los mira: %s" % culpables
        )

    def test_el_separador_del_registro_va_como_escape(self):
        js = _texto(JS / "importador.js")
        assert "join('\\u0000')" in js

    def test_el_guarda_ve_un_byte_nul_de_verdad(self, tmp_path):
        """Control negativo: sin esto, un cero es indistinguible de no mirar."""
        sucio = tmp_path / "sucio.js"
        sucio.write_bytes(b"const x = 'a\x00b';\n")
        assert b"\x00" in sucio.read_bytes()


# ───────────────── util ─────────────────────────────────────────────────────

def _cuerpo(js: str, nombre: str) -> str:
    """Recorta desde la declaracion de `nombre` hasta la siguiente de nivel 0.

    Se recorta hasta la siguiente funcion y no a una ventana fija de caracteres:
    con una ventana fija, anadir codigo empuja fuera del recorte justo lo que el
    test quiere comprobar y el test se vuelve verde por mudanza.
    """
    for prefijo in ("function ", "async function "):
        i = js.find(prefijo + nombre + "(")
        if i >= 0:
            break
    else:
        return ""
    siguientes = [j for j in (js.find("\nfunction ", i + 10),
                              js.find("\nasync function ", i + 10),
                              js.find("\nconst ", i + 10),
                              js.find("\ndocument.getElementById", i + 10)) if j > 0]
    return js[i:min(siguientes)] if siguientes else js[i:]
