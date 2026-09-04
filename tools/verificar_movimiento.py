"""Verificacion EN NAVEGADOR del sistema de movimiento (Plan 4, T4.6).

Uso:
    python tools/verificar_movimiento.py

`tests/test_plan4_movimiento.py` barre el codigo con patrones: sirve para que
nadie reintroduzca un `transition: all`, pero no puede responder a la pregunta
que de verdad importa —¿se mueve algo cuando el sistema pide que no se mueva
nada?—, porque eso solo se ve ejecutando.

Y hay una razon concreta para mirarlo aqui: **Chart.js dibuja sobre `<canvas>`**.
Sus animaciones no pasan por la cascada CSS, asi que el bloque
`prefers-reduced-motion` de `tokens.css` no las alcanza. Un barrido del CSS
diria que todo esta bien mientras seis graficas siguen animandose.

Comprueba, con la preferencia del sistema emulada en las DOS posiciones:

    1. Con `reduce`: Chart.js no anima.
    2. Sin `reduce`: Chart.js si anima (si no, el punto 1 no probaria nada).
    3. Con `reduce`: ninguna fila entra escalonada.
    4. Sin `reduce`: las filas si entran escalonadas.
    5. La barra de progreso escala en vez de ensancharse.

Como el resto de herramientas de la tanda: la app arranca SIN credenciales de
Google, comprobado en la direccion util. No llama a ninguna API de pago.
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

PUERTO = 5064
ANCHO = 1440


class Resultado:
    def __init__(self):
        self.fallos = []

    def comprobar(self, nombre, condicion, detalle=""):
        print("  %s %s%s" % ("OK    " if condicion else "FALLA ", nombre,
                             ("  -> " + detalle) if detalle and not condicion else ""))
        if not condicion:
            self.fallos.append(nombre)


def _pagina(navegador, movimiento):
    """Pagina con la preferencia del sistema emulada y /api/* interceptado."""
    contexto = navegador.new_context(viewport={"width": ANCHO, "height": 1000},
                                     reduced_motion=movimiento)
    pagina = contexto.new_page()
    pagina.route("**/api/**", lambda ruta: ruta.fulfill(
        status=200, content_type="application/json",
        body=json.dumps(medir_cls._cuerpo(ruta.request.url))))
    return contexto, pagina


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
            for movimiento in ("reduce", "no-preference"):
                reducido = movimiento == "reduce"
                contexto, pagina = _pagina(navegador, movimiento)
                pagina.goto("http://127.0.0.1:%d/" % PUERTO, wait_until="load")
                pagina.wait_for_selector("#dash-cards .card", timeout=8000)

                # Chart.js: la configuracion con la que nacieron las graficas.
                anima = pagina.evaluate(
                    "() => (typeof Chart === 'undefined') ? null : Chart.defaults.animation")
                if reducido:
                    r.comprobar("Con movimiento reducido, Chart.js no anima",
                                anima is False, "Chart.defaults.animation = %r" % anima)
                else:
                    r.comprobar("Sin la preferencia, Chart.js si anima",
                                anima is not False,
                                "Chart.defaults.animation = %r (el caso 'reduce' no probaria nada)"
                                % anima)

                # Entrada escalonada de filas, en una seccion con tabla.
                pagina.click("text=Lista de Contactos")
                pagina.wait_for_selector("#contactos-table tbody tr", timeout=8000)
                escalonadas = pagina.eval_on_selector_all(
                    "#contactos-table tbody tr.fila-entra", "e => e.length")
                if reducido:
                    r.comprobar("Con movimiento reducido, ninguna fila entra escalonada",
                                escalonadas == 0, "%d filas con la clase" % escalonadas)
                else:
                    r.comprobar("Sin la preferencia, las filas entran escalonadas",
                                escalonadas > 0, "0 filas con la clase")
                contexto.close()

            # ── La barra de progreso escala, no se ensancha ─────────────────
            contexto, pagina = _pagina(navegador, "no-preference")
            pagina.goto("http://127.0.0.1:%d/importador" % PUERTO, wait_until="load")
            pagina.wait_for_timeout(1200)
            medida = pagina.evaluate("""() => {
                // La T4.9 pasa los paneles del importador a `hidden`, y
                // base.css lo declara `display:none !important`: escribir
                // `style.display` ya no los muestra. Se usa la misma via que el
                // panel de verdad.
                mostrarPaneles();
                ponerAvance(50);
                const fill = document.getElementById('prog-fill');
                const cs = getComputedStyle(fill);
                return {
                    avance: cs.getPropertyValue('--avance').trim(),
                    transform: cs.transform,
                    // `offsetWidth`, NO `getBoundingClientRect`: el rect
                    // incluye la transformacion, asi que devuelve el ancho
                    // VISUAL y ademas atrapado a mitad de la transicion. Lo
                    // que aqui se quiere comprobar es justo lo contrario: que
                    // el ancho de LAYOUT no se toca.
                    ancho: fill.offsetWidth,
                    anchoPista: fill.parentElement.offsetWidth,
                    willChange: fill.style.willChange,
                };
            }""")
            # scaleX(0.5) llega como matrix(0.5, 0, 0, 1, 0, 0).
            escala_ok = medida["transform"].startswith("matrix(0.5")
            r.comprobar("La barra escala en vez de ensancharse",
                        escala_ok and medida["avance"] == "0.5000",
                        "transform=%s avance=%s" % (medida["transform"], medida["avance"]))
            # El elemento conserva su ancho completo: lo que cambia es la escala.
            r.comprobar("El ancho de layout no cambia con el avance",
                        medida["anchoPista"] > 0
                        and abs(medida["ancho"] - medida["anchoPista"]) < 1.5,
                        "ancho=%s pista=%s" % (medida["ancho"], medida["anchoPista"]))
            r.comprobar("will-change puesto mientras avanza",
                        medida["willChange"] == "transform",
                        "willChange=%r" % medida["willChange"])

            retirado = pagina.evaluate("""() => {
                ponerAvance(100);
                return document.getElementById('prog-fill').style.willChange;
            }""")
            r.comprobar("will-change retirado al terminar", retirado == "",
                        "willChange=%r" % retirado)

            # El caso que se escapaba: la corrida NO llega a 100. `fraccion` es
            # monotona y el backend no la normaliza al cancelar, asi que la capa
            # de composicion se quedaba reservada hasta la siguiente busqueda.
            tras_cancelar = pagina.evaluate("""() => {
                ponerAvance(42);
                rematar({status: 'cancelado', ciudad: 'Ciudad Demo 1',
                         nuevos_en_sheet: 3, encontrados: 5, duplicados: 2,
                         descartados: 1, progreso: 1, total: 3, medidor: {}});
                return document.getElementById('prog-fill').style.willChange;
            }""")
            r.comprobar("will-change retirado tambien al cancelar a medias",
                        tras_cancelar == "", "willChange=%r" % tras_cancelar)

            aria = pagina.evaluate("""() => {
                ponerAvance(37);
                const p = document.getElementById('prog-track');
                return p ? {
                    rol: p.getAttribute('role'),
                    valor: p.getAttribute('aria-valuenow'),
                    nombre: p.getAttribute('aria-labelledby'),
                } : null;
            }""")
            r.comprobar("La barra expone rol y avance a un lector",
                        bool(aria) and aria["rol"] == "progressbar"
                        and aria["valor"] == "37" and bool(aria["nombre"]),
                        "aria=%r" % (aria,))
            contexto.close()

            # ── La preferencia cambiada EN CALIENTE, ida y vuelta ───────────
            # Ningun test de patron puede ver esto: hay que emular el cambio con
            # la pagina ya abierta y mirar que pasa con las graficas y con el
            # estado del operador.
            contexto, pagina = _pagina(navegador, "no-preference")
            pagina.goto("http://127.0.0.1:%d/" % PUERTO, wait_until="load")
            pagina.wait_for_selector("#dash-cards .card", timeout=8000)
            fabrica = pagina.evaluate("() => JSON.stringify(Chart.defaults.animation)")

            pagina.emulate_media(reduced_motion="reduce")
            pagina.wait_for_timeout(500)
            en_reduce = pagina.evaluate("""() => ({
                defecto: JSON.stringify(Chart.defaults.animation),
                grafica: JSON.stringify(Object.values(charts)[0].options.animation),
            })""")
            r.comprobar("Al activar la preferencia en caliente, las graficas dejan de animar",
                        en_reduce["defecto"] == "false" and en_reduce["grafica"] == "false",
                        "%r" % (en_reduce,))

            pagina.emulate_media(reduced_motion="no-preference")
            pagina.wait_for_timeout(500)
            de_vuelta = pagina.evaluate("() => JSON.stringify(Chart.defaults.animation)")
            r.comprobar("Al desactivarla, se restaura el valor de FABRICA",
                        de_vuelta == fabrica and de_vuelta not in (None, "false"),
                        "fabrica=%r vuelta=%r" % (fabrica, de_vuelta))

            # Y el estado del operador sobrevive al cambio.
            pagina.click("text=Lista de Contactos")
            pagina.wait_for_selector("#contactos-table tbody tr", timeout=8000)
            pagina.fill("#contactos-search", "Ejemplo 3")
            pagina.wait_for_timeout(400)
            antes = pagina.eval_on_selector_all("#contactos-table tbody tr", "e => e.length")
            pagina.emulate_media(reduced_motion="reduce")
            pagina.wait_for_timeout(700)
            despues = pagina.eval_on_selector_all("#contactos-table tbody tr", "e => e.length")
            r.comprobar("El filtro del operador sobrevive al cambio de preferencia",
                        antes == despues and antes > 0,
                        "filas antes=%d despues=%d (se recargo la seccion)" % (antes, despues))
            contexto.close()
        finally:
            navegador.close()
            servidor.shutdown()

    if r.fallos:
        print("\n%d comprobacion(es) en rojo: %s" % (len(r.fallos), ", ".join(r.fallos)))
        return 1
    print("\nLas 13 comprobaciones en verde.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
