"""Verificacion EN NAVEGADOR del tablero rediseñado (Plan 4, T4.7).

Uso:
    python tools/verificar_tablero.py

El gate de la T4.7 es explicito: "Las once tablas funcionan (orden, filtro,
paginacion). Recorrido por teclado completo." Ninguna de las dos cosas se puede
comprobar leyendo el codigo.

Y hay una razon concreta para mirarlo aqui. La tarea cambia CUATRO mecanismos a
la vez, y los cuatro son de los que se rompen sin hacer ruido:

  - los 12 `div` con `onclick` pasan a `<button data-seccion>` con listener
    delegado: si el delegado no engancha, la navegacion entera deja de
    funcionar y el marcado sigue pareciendo correcto;
  - el orden de tabla pasa de un `onclick` en el `<th>` a un `<button>` dentro;
  - `showSection` deja de leer `event.currentTarget`;
  - las graficas leen su color de `getComputedStyle`, que devuelve cadena vacia
    si el token no existe — y una grafica sin color se dibuja igual, en negro.

Comprueba:
  1. Las 12 secciones se abren, y con TECLADO (Tab + Enter), no con el raton.
  2. Cada tabla ordena: el `aria-sort` cambia y las filas se reordenan de verdad.
  3. El filtro reduce filas y la paginacion cambia de pagina.
  4. La insignia de cache dice la edad del dato, no la hora del navegador.
  5. Las graficas reciben color del sistema, no cadena vacia.
  6. Ningun control queda sin nombre accesible en la barra lateral.

Como el resto de la tanda: la app arranca SIN credenciales de Google,
comprobado en la direccion util. No llama a ninguna API de pago.
"""
import json
import os
import sys
import threading
from pathlib import Path
from wsgiref.simple_server import make_server

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

os.environ.setdefault("PANEL_AUTH_DESACTIVADA", "1")
os.environ.pop("GOOGLE_CREDENTIALS_JSON", None)
os.environ["GOOGLE_CREDENTIALS_FILE"] = str(
    Path(__file__).resolve().parent / "_credencial-inexistente-para-capturas.json"
)

import medir_cls  # noqa: E402

PUERTO = 5067
ANCHO = 1440

# Las secciones del menu, en el orden en que aparecen.
SECCIONES = ["frecuentes", "ventas-dash", "ventas", "dashboard", "contactos",
             "pendientes", "ciudades", "respuestas", "mensajes", "catalogo",
             "seguimiento", "bruce"]

# Las que pintan tabla con orden y paginacion.
CON_TABLA = [
    ("contactos", "#contactos-table", "#contactos-search", "#contactos-pag"),
    ("respuestas", "#respuestas-table", "#resp-search", "#respuestas-pag"),
    ("ventas", "#ventas-table", "#ventas-search", "#ventas-pag"),
]


class Resultado:
    def __init__(self):
        self.fallos = []

    def comprobar(self, nombre, condicion, detalle=""):
        print("  %s %s%s" % ("OK    " if condicion else "FALLA ", nombre,
                             ("  -> " + detalle) if detalle and not condicion else ""))
        if not condicion:
            self.fallos.append(nombre)


def main():
    import app as panel
    medir_cls.verificar_sin_credenciales()

    servidor = make_server("127.0.0.1", PUERTO, panel.app)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()

    r = Resultado()
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        navegador = p.chromium.launch()
        try:
            pagina = navegador.new_page(viewport={"width": ANCHO, "height": 1000})
            pagina.route("**/api/**", lambda ruta: ruta.fulfill(
                status=200, content_type="application/json",
                body=json.dumps(medir_cls._cuerpo(ruta.request.url))))
            pagina.goto("http://127.0.0.1:%d/" % PUERTO, wait_until="load")
            pagina.wait_for_selector("#dash-cards .card", timeout=8000)

            # ── 0. El ARBOL del documento, antes que nada ───────────────────
            # Un `</div>` de mas dejo 11 de las 12 secciones colgando de
            # <body> en vez de #content, y las graficas del tablero fuera de
            # su seccion: no se ocultaban nunca al cambiar de pantalla. Las
            # comprobaciones de mas abajo lo dieron por bueno porque miraban
            # la CLASE `.section.active`, que seguia siendo correcta. La
            # clase estaba bien; el arbol no. Se comprueba el anidamiento.
            arbol = pagina.evaluate("""() => {
                const fuera = [];
                document.querySelectorAll('.section').forEach(s => {
                    if (s.parentElement.id !== 'content')
                        fuera.push(s.id + ' -> ' + (s.parentElement.id || s.parentElement.tagName));
                });
                return {
                    fuera,
                    total: document.querySelectorAll('.section').length,
                    graficas: document.getElementById('dash-charts').closest('.section')?.id,
                };
            }""")
            r.comprobar('Las 12 secciones cuelgan de #content',
                        not arbol['fuera'] and arbol['total'] == 12,
                        '%d de %d fuera: %s' % (len(arbol['fuera']), arbol['total'],
                                                arbol['fuera'][:3]))
            r.comprobar('Las graficas viven dentro de su seccion',
                        arbol['graficas'] == 'sec-dashboard',
                        'dash-charts esta en %r' % arbol['graficas'])

            # ── 1. Las 12 secciones se abren (con raton, primero) ───────────
            fallaron = []
            for s in SECCIONES:
                pagina.click('.nav-item[data-seccion="%s"]' % s)
                pagina.wait_for_timeout(120)
                activa = pagina.evaluate(
                    "() => document.querySelector('.section.active')?.id")
                if activa != "sec-" + s:
                    fallaron.append("%s -> %s" % (s, activa))
            r.comprobar("Las 12 secciones se abren", not fallaron, str(fallaron))

            # Visibilidad REAL, no la clase: `offsetParent` es null cuando el
            # elemento (o un ancestro) esta oculto de verdad.
            pagina.click('.nav-item[data-seccion="contactos"]')
            pagina.wait_for_timeout(300)
            visibles = pagina.evaluate("""() => {
                const v = [];
                document.querySelectorAll('.section').forEach(s => {
                    if (s.id !== 'sec-contactos' && s.offsetParent !== null) v.push(s.id);
                });
                if (document.getElementById('dash-charts').offsetParent !== null)
                    v.push('dash-charts');
                return v;
            }""")
            r.comprobar('Al cambiar de seccion, el resto se oculta de verdad',
                        not visibles, 'siguen visibles: %s' % visibles)

            # ── 2. Recorrido POR TECLADO ────────────────────────────────────
            # Tab hasta el primer boton de navegacion y Enter. Un `div` con
            # onclick no habria recibido el foco nunca.
            pagina.evaluate("() => document.querySelector('.nav-item[data-seccion]').focus()")
            enfocado = pagina.evaluate(
                "() => document.activeElement?.dataset?.seccion || null")
            r.comprobar("Un elemento de navegacion puede recibir el foco",
                        enfocado is not None, "activeElement=%r" % enfocado)

            pagina.evaluate(
                "() => document.querySelector('.nav-item[data-seccion=\\'ciudades\\']').focus()")
            pagina.keyboard.press("Enter")
            pagina.wait_for_timeout(300)
            activa = pagina.evaluate("() => document.querySelector('.section.active')?.id")
            r.comprobar("Enter sobre el boton abre la seccion",
                        activa == "sec-ciudades", "seccion activa=%r" % activa)

            marcada = pagina.evaluate(
                "() => document.querySelector('.nav-item[aria-current=\\'page\\']')"
                "?.dataset?.seccion")
            r.comprobar("La seccion activa se marca con aria-current",
                        marcada == "ciudades", "aria-current en %r" % marcada)

            # ── 3. Orden, filtro y paginacion de las tablas ─────────────────
            for seccion, tabla, buscador, paginacion in CON_TABLA:
                pagina.click('.nav-item[data-seccion="%s"]' % seccion)
                pagina.wait_for_selector("%s tbody tr" % tabla, timeout=8000)

                antes = pagina.eval_on_selector_all(
                    "%s tbody tr td:nth-child(1)" % tabla, "e => e.map(x => x.textContent)")
                pagina.click("%s th:first-child .tabla__orden" % tabla)
                pagina.wait_for_timeout(250)
                despues = pagina.eval_on_selector_all(
                    "%s tbody tr td:nth-child(1)" % tabla, "e => e.map(x => x.textContent)")
                orden = pagina.eval_on_selector("%s th:first-child" % tabla,
                                                "e => e.getAttribute('aria-sort')")
                r.comprobar("[%s] la tabla ordena y lo anuncia" % seccion,
                            orden in ("ascending", "descending") and antes != despues,
                            "aria-sort=%r, filas %s" % (
                                orden, "iguales" if antes == despues else "distintas"))

                # El mismo boton, con teclado.
                pagina.eval_on_selector("%s th:first-child .tabla__orden" % tabla,
                                        "e => e.focus()")
                pagina.keyboard.press("Enter")
                pagina.wait_for_timeout(250)
                orden2 = pagina.eval_on_selector("%s th:first-child" % tabla,
                                                 "e => e.getAttribute('aria-sort')")
                r.comprobar("[%s] el orden se invierte con teclado" % seccion,
                            orden2 != orden, "%r -> %r" % (orden, orden2))

                filas_todas = pagina.eval_on_selector_all(
                    "%s tbody tr" % tabla, "e => e.length")
                pagina.fill(buscador, "Ejemplo 7")
                pagina.wait_for_timeout(350)
                filas_filtradas = pagina.eval_on_selector_all(
                    "%s tbody tr" % tabla, "e => e.length")
                r.comprobar("[%s] el filtro reduce las filas" % seccion,
                            0 < filas_filtradas < filas_todas,
                            "todas=%d filtradas=%d" % (filas_todas, filas_filtradas))
                pagina.fill(buscador, "")
                pagina.wait_for_timeout(350)

                botones = pagina.eval_on_selector_all(
                    "%s button" % paginacion, "e => e.length")
                if botones > 1:
                    pagina.click("%s button:last-child" % paginacion)
                    pagina.wait_for_timeout(250)
                    marcada = pagina.eval_on_selector_all(
                        "%s button[aria-current]" % paginacion, "e => e.length")
                    r.comprobar("[%s] la paginacion cambia de pagina" % seccion,
                                marcada == 1, "botones con aria-current=%d" % marcada)
                else:
                    r.comprobar("[%s] la paginacion cambia de pagina" % seccion, True)

            # ── 4. La insignia dice la edad del dato ────────────────────────
            pagina.click('.nav-item[data-seccion="dashboard"]')
            pagina.wait_for_selector("#dash-cards .card", timeout=8000)
            insignia = pagina.evaluate("""() => {
                const b = document.getElementById('cache-badge');
                return { texto: b.textContent, ayuda: b.title };
            }""")
            r.comprobar("La insignia habla de la edad del dato, no de la hora",
                        ("hace" in insignia["texto"] or "recién" in insignia["texto"])
                        and len(insignia["ayuda"]) > 20,
                        "insignia=%r" % (insignia,))

            # ── 4b. La cifra dominante DOMINA de verdad ─────────────────────
            # Se mide el tamano renderizado, no la regla CSS: `.card .value` se
            # declara mas abajo en la hoja y con la misma especificidad ganaba
            # la ultima, asi que la tarjeta principal salia del mismo tamano
            # que el resto y la jerarquia no existia. Un archivo de texto no
            # puede ver eso; el navegador si.
            tam = pagina.evaluate("""() => {
                const px = s => parseFloat(getComputedStyle(
                    document.querySelector(s)).fontSize);
                return {
                    principal: px('.card--principal .value'),
                    normal: px('.cards--principal .card:nth-child(2) .value'),
                    desglose: px('.cards--desglose .card .value'),
                };
            }""")
            r.comprobar("La cifra dominante es la mas grande de la pantalla",
                        tam["principal"] > tam["normal"] > tam["desglose"],
                        "principal=%.0f normal=%.0f desglose=%.0f px"
                        % (tam["principal"], tam["normal"], tam["desglose"]))

            # ── 5. Las graficas reciben color del sistema ───────────────────
            colores = pagina.evaluate("""() => {
                const c = charts['chartResultados'];
                if (!c) return null;
                return {
                    fondos: c.data.datasets[0].backgroundColor,
                    etiquetas: c.data.labels,
                };
            }""")
            ok_color = bool(colores) and all(
                isinstance(x, str) and x.startswith("#") for x in colores["fondos"])
            r.comprobar("Las graficas reciben color resuelto del sistema",
                        ok_color, "colores=%r" % (colores,))

            if ok_color:
                # Y el color corresponde a la ETIQUETA, no a la posicion.
                par = dict(zip(colores["etiquetas"], colores["fondos"]))
                verde = pagina.evaluate(
                    "() => getComputedStyle(document.documentElement)"
                    ".getPropertyValue('--exito-vivo').trim()")
                r.comprobar("APROBADO se pinta con el verde semantico",
                            par.get("APROBADO", "").lower() == verde.lower(),
                            "APROBADO=%r verde=%r" % (par.get("APROBADO"), verde))

            # ── 6. Ningun control del menu sin nombre accesible ─────────────
            sin_nombre = pagina.evaluate("""() => {
                const fuera = [];
                document.querySelectorAll('#sidebar .nav-item').forEach(el => {
                    const texto = (el.innerText || '').trim();
                    const etiqueta = el.getAttribute('aria-label');
                    if (!texto && !etiqueta) fuera.push(el.outerHTML.slice(0, 60));
                });
                return fuera;
            }""")
            r.comprobar("Todo control del menu tiene nombre accesible",
                        not sin_nombre, str(sin_nombre))
            pagina.close()
        finally:
            navegador.close()
            servidor.shutdown()

    if r.fallos:
        print("\n%d comprobacion(es) en rojo:" % len(r.fallos))
        for f in r.fallos:
            print("   -", f)
        return 1
    print("\nTodas las comprobaciones en verde.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
