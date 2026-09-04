"""Capturas del importador rediseñado (Plan 4, T4.9).

Uso:
    python tools/capturar_importador.py docs/diseno/2026-09-02-importador-t49

`capturar_superficies.py` deja las tres pantallas en su estado de error, que es
lo correcto para comparar el rediseño sin datos de clientes, pero no enseña la
superficie en marcha: el importador solo cuenta su historia **durante** una
corrida. Aquí se sirven las mismas cargas sintéticas del arnés
(`verificar_importador.py`) para poder ver la pantalla con el catálogo cargado,
a media corrida y en cada uno de los cuatro finales.

Las ciudades son las del catálogo versionado (datos públicos del INEGI) y los
contadores son inventados: **ninguna captura lleva un dato de cliente**. La app
arranca sin credenciales de Google y se comprueba. No llama a APIs de pago.
"""
import json
import os
import sys
import threading
from pathlib import Path
from wsgiref.simple_server import make_server

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))

os.environ.setdefault("PANEL_AUTH_DESACTIVADA", "1")
os.environ.pop("GOOGLE_CREDENTIALS_JSON", None)
os.environ["GOOGLE_CREDENTIALS_FILE"] = str(
    Path(__file__).resolve().parent / "_credencial-inexistente-para-capturas.json"
)

import medir_cls  # noqa: E402
import verificar_importador as arnes  # noqa: E402

PUERTO = 5077
ANCHOS = (320, 768, 1440)


def main():
    destino = Path(sys.argv[1] if len(sys.argv) > 1
                   else "docs/diseno/2026-09-02-importador-t49")
    destino.mkdir(parents=True, exist_ok=True)

    import app as panel
    medir_cls.verificar_sin_credenciales()
    servidor = make_server("127.0.0.1", PUERTO, panel.app)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()

    from playwright.sync_api import sync_playwright
    url = "http://127.0.0.1:%d/importador" % PUERTO
    hechas = []
    try:
        with sync_playwright() as p:
            navegador = p.chromium.launch()
            try:
                # 1. Reposo, con el catalogo cargado, en los tres anchos.
                for ancho in ANCHOS:
                    pagina = arnes._pagina(navegador, ancho=ancho)
                    pagina.goto(url, wait_until="domcontentloaded")
                    pagina.wait_for_selector(".chip-ciudad", timeout=20000)
                    pagina.wait_for_timeout(400)
                    ruta = destino / ("reposo-%dpx.png" % ancho)
                    pagina.screenshot(path=str(ruta), full_page=True)
                    hechas.append(ruta)
                    pagina.close()

                # 2. Filtro en marcha: agrupacion y conteo por grupo.
                pagina = arnes._pagina(navegador, ancho=768)
                pagina.goto(url, wait_until="domcontentloaded")
                pagina.wait_for_selector(".chip-ciudad", timeout=20000)
                pagina.evaluate("""() => {
                    document.getElementById('ciudad-filter').value = 'guadal';
                    filtrarCiudades();
                }""")
                pagina.wait_for_timeout(300)
                ruta = destino / "filtro-agrupado.png"
                pagina.screenshot(path=str(ruta), full_page=True)
                hechas.append(ruta)
                pagina.close()

                # 3. Corrida en marcha y los cuatro finales.
                escenas = [("corrida", {}),
                           ("final-completado", {"status": "done", "fraccion": 100}),
                           ("final-detenido", {"status": "cancelado"}),
                           ("final-tope-de-gasto", {"status": "presupuesto_agotado"}),
                           ("final-error", {"status": "error",
                                            "error": "Google respondió 429."})]
                for nombre, cambios in escenas:
                    pagina = arnes._pagina(navegador, ancho=768)
                    pagina.goto(url, wait_until="domcontentloaded")
                    pagina.wait_for_selector(".chip-ciudad", timeout=20000)
                    estado = arnes._estado(**cambios)
                    pagina.evaluate(
                        "(d) => { mostrarPaneles(); pintarEstado(d); "
                        "if (d.status !== 'running') rematar(d); }", estado)
                    pagina.wait_for_timeout(500)
                    ruta = destino / ("%s.png" % nombre)
                    pagina.screenshot(path=str(ruta), full_page=True)
                    hechas.append(ruta)
                    pagina.close()
            finally:
                navegador.close()
    finally:
        servidor.shutdown()

    for ruta in hechas:
        print("  %-28s %6.1f KB" % (ruta.name, ruta.stat().st_size / 1024))
    print("%d capturas en %s" % (len(hechas), destino))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
