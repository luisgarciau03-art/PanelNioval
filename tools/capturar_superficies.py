"""Captura las tres superficies del panel a PNG, en varios anchos.

Uso:
    python tools/capturar_superficies.py docs/diseno/antes

Levanta la app Flask en un hilo con ``PANEL_AUTH_DESACTIVADA=1`` y **sin
credenciales de Google**, a proposito: las llamadas a ``/api/*`` fallan y las
pantallas quedan en su estado de carga/error. Eso es justo lo que queremos para
comparar el rediseno — y garantiza que **ninguna captura lleva datos de
clientes** (riesgo R8 del Plan 4).

No llama a ninguna API de pago.
"""
import os
import sys
import threading
from pathlib import Path
from wsgiref.simple_server import make_server

# El script vive en tools/; la app esta en la raiz del proyecto.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

# El panel es fail-closed; para capturar en local se usa el bypass explicito.
os.environ.setdefault("PANEL_AUTH_DESACTIVADA", "1")

# Las capturas van al repo, asi que NO pueden llevar datos de clientes.
# Se cortan las DOS vias de credencial de app.py (`_construir_gs_client`):
# la variable GOOGLE_CREDENTIALS_JSON y el archivo GOOGLE_CREDENTIALS_FILE,
# que por defecto apunta a un .json de la raiz del proyecto. Sin ninguna de
# las dos, `/api/*` falla y las pantallas quedan en su estado de carga/error.
# Cortarlas no basta con confiar: `verificar_sin_credenciales()` lo comprueba.
os.environ.pop("GOOGLE_CREDENTIALS_JSON", None)
os.environ["GOOGLE_CREDENTIALS_FILE"] = str(
    Path(__file__).resolve().parent / "_credencial-inexistente-para-capturas.json"
)


def verificar_sin_credenciales() -> None:
    """Aborta si el panel todavia puede leer las hojas.

    Un barrido que no encuentra nada no demuestra que no hay nada: aqui se
    comprueba en la direccion util, que el cliente de Google **falla**.
    """
    import app as panel

    try:
        panel.get_gs_client()
    except Exception:
        return  # lo esperado: sin credencial no hay cliente
    raise SystemExit(
        "ABORTADO: el panel SI pudo autenticarse con Google. Las capturas "
        "llevarian datos de clientes. Revisa GOOGLE_CREDENTIALS_JSON y "
        "GOOGLE_CREDENTIALS_FILE antes de volver a correr."
    )

# Los cinco de CE10 desde la T4.10: el desborde del tablero aparecia entre
# 768 y 1024 px, o sea justo en el hueco que dejaban tres anchos.
ANCHOS = [320, 375, 768, 1024, 1440]
SUPERFICIES = [("dashboard", "/"), ("formulario", "/formulario"), ("importador", "/importador")]
PUERTO = 5099


def main() -> int:
    argumentos = [a for a in sys.argv[1:] if not a.startswith("--")]
    # Con `--sinteticos` las pantallas se capturan CON datos inventados en vez de
    # en su estado de error. Para comparar el rediseno da igual; para ensenar
    # como responde la maquetacion a cada ancho, no: una tabla vacia no desborda.
    sinteticos = "--sinteticos" in sys.argv
    destino = Path(argumentos[0] if argumentos else "docs/diseno/antes")
    destino.mkdir(parents=True, exist_ok=True)

    import app as panel  # import lento en frio (~1-5 min): googleapiclient + Defender

    verificar_sin_credenciales()

    servidor = make_server("127.0.0.1", PUERTO, panel.app)
    hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
    hilo.start()

    from playwright.sync_api import sync_playwright

    escritas = []
    with sync_playwright() as p:
        navegador = p.chromium.launch()
        try:
            for ancho in ANCHOS:
                pagina = navegador.new_page(viewport={"width": ancho, "height": 900})
                if sinteticos:
                    import json as _json
                    import medir_cls
                    pagina.route("**/api/**", lambda r: r.fulfill(
                        status=200, content_type="application/json",
                        body=_json.dumps(medir_cls._cuerpo(r.request.url),
                                         ensure_ascii=False)))
                for nombre, ruta in SUPERFICIES:
                    # `domcontentloaded` y no `load`: `load` espera TAMBIEN a los
                    # recursos de terceros -el logo de Cloudinary- y una peticion
                    # lenta ahi fuera tumbaba las quince capturas. La espera de
                    # abajo es la que garantiza que la pantalla esta asentada.
                    pagina.goto(f"http://127.0.0.1:{PUERTO}{ruta}",
                                wait_until="domcontentloaded")
                    # Margen para que corran los fetch y se pinte el estado de carga/error.
                    pagina.wait_for_timeout(2500)
                    archivo = destino / f"{nombre}-{ancho}.png"
                    pagina.screenshot(path=str(archivo), full_page=True)
                    escritas.append(archivo)
                    print(f"  {archivo}  ({archivo.stat().st_size} bytes)")
                pagina.close()
        finally:
            navegador.close()
            servidor.shutdown()

    vacias = [f for f in escritas if f.stat().st_size == 0]
    if vacias:
        print(f"FALLO: {len(vacias)} capturas vacias", file=sys.stderr)
        return 1
    print(f"\n{len(escritas)} capturas en {destino}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
