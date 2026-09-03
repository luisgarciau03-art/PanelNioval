"""Presupuesto de CSS/JS y metricas de carga de las tres superficies (T4.10).

Uso:
    python tools/medir_presupuesto.py

Mide, por superficie:

  - **Bytes por tipo de recurso**, tal y como viajan por la red
    (`encodedBodySize`), separando lo propio de lo de terceros. El presupuesto
    de las reglas del entorno para una pagina de aplicacion es **< 300 KB de JS
    y < 50 KB de CSS**, comprimidos.
  - **Recursos que bloquean el render**: los que el navegador tiene que
    descargar y ejecutar antes de pintar. Es la metrica que motivo auto-hospedar
    Chart.js: venia de un CDN, en `<head>`, sin `defer` — o sea que el tablero no
    pintaba nada hasta que jsdelivr contestara, y jsdelivr tardo **15.1 s**
    medidos desde esta maquina.
  - **LCP** y **DOMContentLoaded**, que es donde se ve el efecto.

Los recursos se sirven desde el propio panel; `/api/*` devuelve datos
sinteticos. Sin credenciales de Google y sin APIs de pago.
"""
import gzip
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

PUERTO = 5075
PRESUPUESTO_JS = 300 * 1024
PRESUPUESTO_CSS = 50 * 1024
REPETICIONES = 3

OBSERVADOR_LCP = """
window.__lcp = 0;
new PerformanceObserver((l) => {
  for (const e of l.getEntries()) window.__lcp = Math.max(window.__lcp, e.startTime);
}).observe({type: 'largest-contentful-paint', buffered: true});
"""

RECURSOS = """
() => {
  const propio = (u) => u.startsWith(location.origin);
  const salida = {js: 0, css: 0, img: 0, otros: 0, terceros: 0, lista: []};
  for (const r of performance.getEntriesByType('resource')) {
    const bytes = r.encodedBodySize || r.transferSize || 0;
    const url = r.name;
    if (!propio(url)) { salida.terceros += bytes; }
    if (url.endsWith('.js')) salida.js += bytes;
    else if (url.endsWith('.css')) salida.css += bytes;
    else if (/\\.(png|jpe?g|gif|svg|webp|avif)/i.test(url)) salida.img += bytes;
    else salida.otros += bytes;
    salida.lista.push({url: url.replace(location.origin, ''), bytes,
                       tercero: !propio(url)});
  }
  const nav = performance.getEntriesByType('navigation')[0] || {};
  salida.html = nav.encodedBodySize || 0;
  salida.dcl = Math.round(nav.domContentLoadedEventEnd || 0);
  salida.lcp = Math.round(window.__lcp || 0);
  // Lo que bloquea el pintado: <script> sin defer/async en <head> y hojas de
  // estilo. Se lee del DOM, que es donde esta la verdad, no de una lista.
  salida.bloqueantes = [
    ...[...document.querySelectorAll('head script[src]')]
        .filter(s => !s.defer && !s.async)
        .map(s => 'script ' + s.src.replace(location.origin, '')),
    ...[...document.querySelectorAll('head link[rel="stylesheet"]')]
        .map(l => 'css ' + l.href.replace(location.origin, '')),
  ];
  return salida;
}
"""


def kb(n):
    return "%.1f KB" % (n / 1024)


def _comprimido(rutas):
    """Bytes que de verdad viajan en produccion.

    El servidor de desarrollo NO comprime, asi que `encodedBodySize` devuelve el
    tamano en claro. Los presupuestos de las reglas del entorno estan escritos
    en **gzip**, asi que compararlos contra la cifra sin comprimir declara fuera
    de presupuesto algo que no lo esta: el CSS del tablero da 54.7 KB en claro y
    18.5 KB comprimido, contra un tope de 50. En el VPS quien comprime es Caddy.
    """
    total = 0
    for ruta in rutas:
        local = RAIZ / ruta.lstrip("/")
        if local.is_file():
            total += len(gzip.compress(local.read_bytes(), 9))
    return total


def main():
    import app as panel
    medir_cls.verificar_sin_credenciales()
    servidor = make_server("127.0.0.1", PUERTO, panel.app)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()

    excesos = 0
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        navegador = p.chromium.launch()
        try:
            for nombre, ruta in medir_cls.SUPERFICIES:
                # Tres cargas y se queda la MEDIANA. Una sola medida sobre el
                # servidor de desarrollo varia al doble entre corridas -medido:
                # el mismo tablero dio 3,464 ms y 1,428 ms-, y un numero
                # inestable presentado como metrica engana igual que uno falso.
                # Los BYTES no varian; los tiempos si, y por eso van separados.
                medidas = []
                d = None
                for _ in range(REPETICIONES):
                    contexto = navegador.new_context(viewport={"width": 1440, "height": 900})
                    pagina = contexto.new_page()
                    pagina.add_init_script(OBSERVADOR_LCP)
                    pagina.route("**/api/**", lambda r: r.fulfill(
                        status=200, content_type="application/json",
                        body=json.dumps(medir_cls._cuerpo(r.request.url), ensure_ascii=False)))
                    pagina.goto("http://127.0.0.1:%d%s" % (PUERTO, ruta), wait_until="load")
                    pagina.wait_for_timeout(2500)
                    d = pagina.evaluate(RECURSOS)
                    medidas.append((d["lcp"], d["dcl"]))
                    contexto.close()
                medidas.sort()
                d["lcp"], d["dcl"] = medidas[len(medidas) // 2]

                print("\n=== %s ===" % nombre.upper())
                print("  HTML %-10s JS %-10s CSS %-10s imagenes %s"
                      % (kb(d["html"]), kb(d["js"]), kb(d["css"]), kb(d["img"])))
                print("  de terceros: %s" % (kb(d["terceros"]) if d["terceros"] else "nada"))
                print("  LCP %d ms · DOMContentLoaded %d ms  (mediana de %d cargas)"
                      % (d["lcp"], d["dcl"], REPETICIONES))
                print("        son del servidor de desarrollo: valen para comparar"
                      " entre si, no como cifra de produccion")
                print("  bloquean el render (%d):" % len(d["bloqueantes"]))
                for b in d["bloqueantes"]:
                    print("      %s" % b)
                propios = [r["url"] for r in d["lista"] if not r["tercero"]]
                gz = {
                    "JS": _comprimido([u for u in propios if u.endswith(".js")]),
                    "CSS": _comprimido([u for u in propios if u.endswith(".css")]),
                }
                for etiqueta, tope in (("JS", PRESUPUESTO_JS), ("CSS", PRESUPUESTO_CSS)):
                    marca = "OK" if gz[etiqueta] <= tope else "EXCEDE"
                    print("  %-3s comprimido: %-10s (tope %s)  %s"
                          % (etiqueta, kb(gz[etiqueta]), kb(tope), marca))
                    if gz[etiqueta] > tope:
                        excesos += 1
                mayores = sorted(d["lista"], key=lambda x: -x["bytes"])[:4]
                for m in mayores:
                    print("      %-52s %9s%s" % (m["url"][-52:], kb(m["bytes"]),
                                                 "  (TERCERO)" if m["tercero"] else ""))
        finally:
            navegador.close()
            servidor.shutdown()

    print("\n%s" % ("TODAS dentro de presupuesto." if not excesos
                    else "%d superficie(s) fuera de presupuesto." % excesos))
    return 1 if excesos else 0


if __name__ == "__main__":
    raise SystemExit(main())
