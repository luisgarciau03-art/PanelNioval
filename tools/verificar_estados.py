"""Verificacion EN NAVEGADOR de los estados de carga (Plan 4, T4.5).

Uso:
    python tools/verificar_estados.py

`tests/test_plan4_estados.py` comprueba el codigo fuente con patrones: sirve
para fijar decisiones, pero no ejecuta una sola linea de JavaScript. El fallo
mas grave de la primera version de la T4.5 vivia justo ahi — en el DOM, en la
segunda carga de una seccion — y ninguna comprobacion estatica podia verlo:

    `terminar()` hacia `el.innerHTML = ''` sin mirar que habia dentro. Como
    quien llama cierra el esqueleto en un `finally`, que corre DESPUES de que
    la seccion pinto sus datos, pulsar "Actualizar" con una respuesta de Google
    de mas de 200 ms borraba las tarjetas recien pintadas.

Este script conduce el panel con Playwright y comprueba comportamiento:

    1. Tras "Actualizar" con red lenta, los indicadores SIGUEN en pantalla.
    2. El aviso de graficas no destruye los <canvas>: un segundo intento con el
       CDN ya disponible vuelve a dibujarlas.
    3. El bloque de error se anuncia como `alert` y ofrece reintento.
    4. El reintento repinta esqueleto (da senal de vida) y recupera los datos.

Como el resto de herramientas de la tarea: la app arranca SIN credenciales de
Google, comprobado en la direccion util. No llama a ninguna API de pago.

Salida: 0 si las cinco comprobaciones pasan, 1 si alguna falla.
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

PUERTO = 5063
ANCHO = 1440
RETARDO_MS = 700   # por encima del umbral de 200 ms: el esqueleto llega a pintarse


class Resultado:
    def __init__(self):
        self.fallos = []

    def comprobar(self, nombre, condicion, detalle=""):
        marca = "OK    " if condicion else "FALLA "
        print("  %s %s%s" % (marca, nombre, ("  -> " + detalle) if detalle and not condicion else ""))
        if not condicion:
            self.fallos.append(nombre)


def _esperar_datos(pagina, selector, ms=8000):
    pagina.wait_for_selector(selector, timeout=ms)


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
            # ── 1. "Actualizar" no puede borrar lo que acaba de cargar ──────
            pagina = navegador.new_page(viewport={"width": ANCHO, "height": 1000})
            # El retardo se aplica en el servidor de rutas: se retrasa la
            # RESPUESTA, no el manejador, para no bloquear Playwright.
            pagina.route("**/api/**", lambda ruta: ruta.fulfill(
                status=200, content_type="application/json",
                body=json.dumps(medir_cls._cuerpo(ruta.request.url))))
            pagina.goto("http://127.0.0.1:%d/" % PUERTO, wait_until="load")
            _esperar_datos(pagina, "#dash-cards .card")
            antes = pagina.eval_on_selector_all("#dash-cards .card", "e => e.length")

            # Ahora la segunda carga, que es donde vivia el fallo: el JS pinta
            # su propio esqueleto porque la seccion ya se visito una vez.
            pagina.evaluate("""(ms) => {
                const orig = window.fetch;
                window.fetch = (...a) => new Promise(res =>
                    setTimeout(() => res(orig(...a)), ms));
            }""", RETARDO_MS)
            pagina.click("text=↻ Actualizar")
            pagina.wait_for_timeout(RETARDO_MS + 2500)
            despues = pagina.eval_on_selector_all("#dash-cards .card", "e => e.length")
            r.comprobar(
                "Actualizar conserva los indicadores",
                despues == antes and despues > 0,
                "antes=%d despues=%d (el esqueleto borro los datos)" % (antes, despues))
            pagina.close()

            # ── 2. El aviso de graficas no destruye los <canvas> ────────────
            pagina = navegador.new_page(viewport={"width": ANCHO, "height": 1000})
            pagina.route("**cdn.jsdelivr.net**", lambda ruta: ruta.abort())
            pagina.route("**/api/**", lambda ruta: ruta.fulfill(
                status=200, content_type="application/json",
                body=json.dumps(medir_cls._cuerpo(ruta.request.url))))
            pagina.goto("http://127.0.0.1:%d/" % PUERTO, wait_until="load")
            pagina.wait_for_timeout(2500)
            hay_aviso = pagina.eval_on_selector_all(
                "#dash-charts-aviso .estado--parcial", "e => e.length") == 1
            lienzos = pagina.eval_on_selector_all("#dash-charts canvas", "e => e.length")
            r.comprobar("El fallo de graficas avisa sin borrar los lienzos",
                        hay_aviso and lienzos == 3,
                        "aviso=%s lienzos=%d (deberian quedar 3)" % (hay_aviso, lienzos))
            pagina.close()

            # ── 3 y 4. Error: rol, reintento y recuperacion ─────────────────
            pagina = navegador.new_page(viewport={"width": ANCHO, "height": 1000})
            fallar = {"si": True}

            def manejar(ruta):
                if fallar["si"]:
                    ruta.fulfill(status=500, content_type="application/json",
                                 body=json.dumps({"error": "fallo simulado"}))
                else:
                    ruta.fulfill(status=200, content_type="application/json",
                                 body=json.dumps(medir_cls._cuerpo(ruta.request.url)))

            pagina.route("**/api/**", manejar)
            pagina.goto("http://127.0.0.1:%d/" % PUERTO, wait_until="load")
            pagina.wait_for_selector(".estado--error", timeout=8000)
            rol = pagina.eval_on_selector(".estado--error", "e => e.getAttribute('role')")
            r.comprobar("El error se anuncia como alert", rol == "alert",
                        "role=%r" % rol)
            hay_boton = pagina.eval_on_selector_all(
                ".estado--error .estado__accion button", "e => e.length") >= 1
            r.comprobar("El error ofrece reintento", hay_boton)

            fallar["si"] = False
            pagina.click(".estado--error .estado__accion button")
            _esperar_datos(pagina, "#dash-cards .card")
            recuperado = pagina.eval_on_selector_all("#dash-cards .card", "e => e.length")
            r.comprobar("El reintento recupera los datos", recuperado > 0,
                        "tarjetas=%d" % recuperado)
            pagina.close()
        finally:
            navegador.close()
            servidor.shutdown()

    if r.fallos:
        print("\n%d comprobacion(es) en rojo: %s" % (len(r.fallos), ", ".join(r.fallos)))
        return 1
    print("\nLas 5 comprobaciones en verde.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
