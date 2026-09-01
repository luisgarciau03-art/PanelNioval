"""Captura los CUATRO estados de carga del panel (Plan 4, T4.5).

Uso:
    python tools/capturar_estados.py docs/diseno/2026-09-01-estados-t45

Hasta la T4.5 el panel tenía un solo estado no-feliz: un spinner que servía
igual para "cargando", "no hay filas" y "la lectura falló". Esta herramienta
fuerza cada uno por separado y lo fotografía, que es la única forma de
comprobar que de verdad se ven distintos.

Los cuatro:

    carga    ``/api/*`` tarda; se fotografía el esqueleto en vuelo.
    vacio    ``/api/*`` responde bien y sin filas.
    error    ``/api/*`` responde 500.
    parcial  los datos llegan, pero Chart.js no: se bloquea el CDN. Es un caso
             real, no inventado — el script viene de jsdelivr sin SRI.

Como ``capturar_superficies.py``: la app arranca **sin credenciales de Google**,
comprobado en la dirección útil, así que ninguna captura puede llevar datos de
clientes. No llama a ninguna API de pago.
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

import medir_cls  # noqa: E402  (reutiliza las cargas sinteticas y el chequeo)

PUERTO = 5059
ANCHO = 1440
CDN_CHART = "**cdn.jsdelivr.net**"


def _capturar(navegador, destino, nombre, ruta, preparar, espera, seccion=None):
    pagina = navegador.new_page(viewport={"width": ANCHO, "height": 1000})
    preparar(pagina)
    pagina.goto("http://127.0.0.1:%d%s" % (PUERTO, ruta), wait_until="load")
    if seccion:
        # El tablero abre en una seccion sin tabla, donde el estado vacio no
        # tiene donde aparecer. Se navega con un CLIC real porque `showSection`
        # lee `event.currentTarget`: llamarla a mano desde la consola reventaria.
        pagina.click("text=%s" % seccion)
    pagina.wait_for_timeout(espera)
    archivo = destino / ("%s.png" % nombre)
    pagina.screenshot(path=str(archivo), full_page=(nombre != "carga"))
    pagina.close()
    print("  %-28s %8d bytes" % (archivo.name, archivo.stat().st_size))
    return archivo


def main():
    destino = Path(sys.argv[1] if len(sys.argv) > 1 else "docs/diseno/estados-t45")
    destino.mkdir(parents=True, exist_ok=True)

    import app as panel
    medir_cls.verificar_sin_credenciales()

    servidor = make_server("127.0.0.1", PUERTO, panel.app)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()

    def json_de(ruta, cuerpo):
        ruta.fulfill(status=200, content_type="application/json", body=json.dumps(cuerpo))

    def prep_carga(pagina):
        # El manejador NO responde ni aborta: deja la peticion colgada, que es
        # exactamente el estado que se quiere fotografiar. Esperar dentro del
        # manejador bloquearia el bucle de Playwright y cerraria la pagina.
        pagina.route("**/api/**", lambda r: None)

    def prep_vacio(pagina):
        pagina.route("**/api/**", lambda r: json_de(r, []))

    def prep_error(pagina):
        pagina.route("**/api/**", lambda r: r.fulfill(
            status=500, content_type="application/json",
            body=json.dumps({"error": "fallo simulado"})))

    def prep_parcial(pagina):
        # Los datos llegan; la libreria de graficas no. Es lo que pasa cuando
        # jsdelivr no responde, que hoy nadie puede descartar: el script se
        # carga sin SRI y sin copia local (deuda anotada para el Plan 5).
        pagina.route(CDN_CHART, lambda r: r.abort())
        pagina.route("**/api/**", lambda r: json_de(r, medir_cls._cuerpo(r.request.url)))

    from playwright.sync_api import sync_playwright

    escritas = []
    with sync_playwright() as p:
        navegador = p.chromium.launch()
        try:
            escritas.append(_capturar(navegador, destino, "carga", "/", prep_carga, 1500))
            escritas.append(_capturar(navegador, destino, "error", "/", prep_error, 2500))
            escritas.append(_capturar(navegador, destino, "parcial", "/", prep_parcial, 3000))
            # Vacio y error EN UNA TABLA, que es donde se distinguen: hasta la
            # T4.5 los dos eran el mismo `.empty` gris.
            escritas.append(_capturar(navegador, destino, "vacio-tabla", "/", prep_vacio, 2000,
                                      seccion="Lista de Contactos"))
            escritas.append(_capturar(navegador, destino, "error-tabla", "/", prep_error, 2000,
                                      seccion="Lista de Contactos"))
            escritas.append(_capturar(navegador, destino, "formulario-error", "/formulario",
                                      prep_error, 2000))
            escritas.append(_capturar(navegador, destino, "importador-carga", "/importador",
                                      prep_carga, 1200))
        finally:
            navegador.close()
            servidor.shutdown()

    vacias = [f for f in escritas if f.stat().st_size == 0]
    if vacias:
        print("FALLO: %d capturas vacias" % len(vacias), file=sys.stderr)
        return 1
    print("\n%d capturas en %s" % (len(escritas), destino))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
