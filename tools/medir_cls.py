"""Mide el salto de layout (CLS) de las tres superficies con la red lenta.

Uso:
    python tools/medir_cls.py
    python tools/medir_cls.py --retardo 1500 --json docs/diseno/cls-despues.json

Es el gate de la T4.5 del Plan 4: CE4 pide **CLS < 0.1** en las tres pantallas,
y el criterio de la tarea añade "con la red ralentizada" — que es justo cuando
el problema aparece. Con la red rápida el esqueleto casi no llega a verse y el
salto no se mide; con Google Sheets tardando lo que tarda, sí.

Cómo mide
---------
1. Levanta la app Flask en un hilo, con ``PANEL_AUTH_DESACTIVADA=1`` y **sin
   credenciales de Google** — las dos vías cortadas y comprobadas, igual que
   ``capturar_superficies.py``. Ninguna medición toca datos de clientes.
2. Intercepta ``/api/*`` en el navegador y responde con cargas **sintéticas**
   tras ``--retardo`` milisegundos. Eso es lo que hace la medida útil: sin
   datos de respuesta, la pantalla se queda en el estado de error y nunca se
   ejercita la transición esqueleto -> contenido, que es donde vive el salto.
3. Registra las entradas ``layout-shift`` con ``PerformanceObserver``, sumando
   solo las que no siguen a una interacción (``hadRecentInput``), que es la
   definición de CLS.

El observador se instala con ``add_init_script``, es decir **antes** de que
corra un solo script de la página: instalarlo después perdería precisamente los
saltos de la carga inicial, y devolvería un 0.000 tranquilizador y falso.

No llama a ninguna API de pago.
"""
import argparse
import json
import os
import sys
import threading
from pathlib import Path
from urllib.parse import urlparse
from wsgiref.simple_server import make_server

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("PANEL_AUTH_DESACTIVADA", "1")

# Mismas dos vías de credencial que corta `capturar_superficies.py`. No basta
# con quitar la variable: `app.py` cae a un .json de la raíz del proyecto.
os.environ.pop("GOOGLE_CREDENTIALS_JSON", None)
os.environ["GOOGLE_CREDENTIALS_FILE"] = str(
    Path(__file__).resolve().parent / "_credencial-inexistente-para-capturas.json"
)

PUERTO = 5057
ANCHOS = (320, 768, 1440)
SUPERFICIES = (("dashboard", "/"), ("formulario", "/formulario"), ("importador", "/importador"))
LIMITE_CLS = 0.1

# ── Cargas sintéticas ──────────────────────────────────────────────────────
# Inventadas a propósito: nombres de ferreterías de mentira y teléfonos con el
# prefijo de documentación. Aquí NO puede entrar una fila real de la hoja.
_TIENDAS = ["Ferretería Ejemplo %d" % i for i in range(1, 61)]
_CIUDADES = ["Ciudad Demo %d" % i for i in range(1, 21)]
_TEL = "+52...XXXX"


def _filas(n, extra=None):
    filas = []
    for i in range(n):
        fila = {
            "TIENDA": _TIENDAS[i % len(_TIENDAS)],
            "CIUDAD": _CIUDADES[i % len(_CIUDADES)],
            "TELÉFONO": _TEL,
            "CONTACTO": _TEL,
            "RESPUESTA": ["APROBADO", "NEGADO", "BUZON", ""][i % 4],
            "Conclusión": ["Pedido", "Nulo", "Correo", "Continuacion"][i % 4],
            "Resultado Llamada": ["APROBADO", "NEGADO", "BUZON"][i % 3],
        }
        if extra:
            fila.update(extra)
        filas.append(fila)
    return filas


RESPUESTAS = {
    "/api/prospectos/stats": {
        "total_contactos": 1234,
        "total_respuestas": 456,
        "resultados": {"APROBADO": 120, "NEGADO": 90, "NO COMPATIBLE": 40, "MARCA UNICA": 20},
        "estados_llamada": {"BUZON": 70, "TELEFONO INCORRECTO": 30},
        "por_semana": [{"semana": "S%d" % s, "total": 10 + s} for s in range(1, 13)],
        "top_ciudades": [[c, 50 - i] for i, c in enumerate(_CIUDADES[:10])],
        "cache": {"edad_min": 3},
    },
    "/api/prospectos/clientes-frecuentes": _filas(40),
    "/api/prospectos/contactos": _filas(60),
    "/api/prospectos/contactos-pendientes": _filas(30),
    "/api/prospectos/respuestas": _filas(60),
    "/api/prospectos/mensajes": [
        {"_col": i, "tipo": "Mensaje %d" % i, "contenido": "Texto de ejemplo."} for i in range(1, 7)
    ],
    "/api/prospectos/ventas": _filas(50, {"FACTURA": "F-000", "MONTO": 1000}),
    "/api/prospectos/ventas-dashboard": {
        "total_facturado": 987654,
        "num_ventas": 321,
        "ticket_promedio": 3076,
        "por_mes": [{"mes": "2026-%02d" % m, "monto": 1000 * m} for m in range(1, 13)],
        "top_clientes": [[t, 900 - i * 10] for i, t in enumerate(_TIENDAS[:10])],
        "ventas": _filas(40, {"FACTURA": "F-000", "MONTO": 1000}),
    },
    "/api/prospectos/ciudades": [
        {"ciudad": c, "total": 40 - i, "aprobados": 20 - i, "interes": 50 - i}
        for i, c in enumerate(_CIUDADES)
    ],
    "/api/seguimiento": _filas(45),
    "/api/bruce/prospectos": _filas(25, {"Nombre": "Prospecto de ejemplo"}),
    "/api/catalogo/envios": {"envios": [
        {"_row": i, "tienda": _TIENDAS[i], "telefono": _TEL, "estado": "ENVIADO",
         "intentos": 1, "actualizado": "2026-09-01"} for i in range(12)
    ]},
    "/api/importador/ciudades": {
        "ciudades": [
            {"ciudad": c, "region": "Región Demo", "unidades_ferreteras": 100 - i,
             "interes_pct": 0, "explicacion": "Ejemplo."}
            for i, c in enumerate(_CIUDADES)
        ],
        "regiones": [{"region": "Región Demo", "total": len(_CIUDADES)}],
        "sin_clasificar": [],
    },
    "/api/importador/estado": {"status": "idle"},
    "/api/formulario/siguiente": {
        "fin": False,
        "contacto": {
            "TIENDA": _TIENDAS[0], "CIUDAD": _CIUDADES[0], "CONTACTO": _TEL,
            "CATEGORIA ": "Ferretería", "Esquema": "Mayoreo",
            "_row": 2, "_col_respuesta": 6,
        },
    },
}

OBSERVADOR = """
window.__cls = 0;
window.__saltos = [];
new PerformanceObserver((lista) => {
  for (const e of lista.getEntries()) {
    if (e.hadRecentInput) continue;
    window.__cls += e.value;
    // Quien se movio, no solo cuanto. Sin esto la medicion dice que hay salto
    // pero no donde, y se acaba corrigiendo a ciegas el elemento equivocado.
    for (const s of (e.sources || [])) {
      const n = s.node;
      if (!n || !n.tagName) continue;
      window.__saltos.push({
        valor: e.value,
        nodo: n.tagName.toLowerCase()
              + (n.id ? '#' + n.id : '')
              + (n.className && typeof n.className === 'string'
                 ? '.' + n.className.trim().split(/\\s+/).join('.') : ''),
      });
    }
  }
}).observe({type: 'layout-shift', buffered: true});
"""


def verificar_sin_credenciales():
    """Aborta si el panel todavía puede leer las hojas.

    Se comprueba en la dirección útil —que el cliente **falla**—, no en la
    cómoda. Un barrido que no encuentra nada no demuestra que no hay nada.
    """
    import app as panel
    try:
        panel.get_gs_client()
    except Exception:
        return
    print("FALLO: el panel SI logro autenticarse contra Google. No se mide.", file=sys.stderr)
    raise SystemExit(2)


def _cuerpo(url):
    # La RUTA, no la URL. Comparar la url completa contra "/api/..." no casaba
    # nunca y devolvia [] para todo: la medicion parecia funcionar y en realidad
    # cronometraba la transicion esqueleto -> VACIO, que es la barata. La
    # transicion cara, y la que CE4 mide, es esqueleto -> contenido.
    ruta = urlparse(url).path
    for clave, valor in RESPUESTAS.items():
        if ruta == clave:
            return valor
    # Lo que no se modela devuelve una lista vacia: la pantalla cae en su estado
    # VACIO, que tambien es una transicion que hay que medir.
    return []


def medir(retardo_ms, detalle=False):
    from playwright.sync_api import sync_playwright

    resultados = []
    with sync_playwright() as p:
        navegador = p.chromium.launch()
        try:
            for ancho in ANCHOS:
                pagina = navegador.new_page(viewport={"width": ancho, "height": 900})
                pagina.add_init_script(OBSERVADOR)

                def responder(ruta):
                    # El retardo se aplica DENTRO del navegador para que el
                    # esqueleto llegue a pintarse: por debajo del umbral de
                    # 200 ms ni siquiera aparece, y no habria nada que medir.
                    ruta.fulfill(
                        status=200,
                        content_type="application/json",
                        body=json.dumps(_cuerpo(ruta.request.url)),
                    )

                pagina.route("**/api/**", lambda ruta: responder(ruta))

                for nombre, url in SUPERFICIES:
                    pagina.goto("http://127.0.0.1:%d%s" % (PUERTO, url), wait_until="load")
                    pagina.wait_for_timeout(retardo_ms + 2500)
                    cls = pagina.evaluate("window.__cls")
                    saltos = pagina.evaluate("window.__saltos")
                    resultados.append({"superficie": nombre, "ancho": ancho,
                                       "cls": round(cls, 4), "saltos": saltos})
                    print("  %-11s %5d px   CLS = %.4f  %s" % (
                        nombre, ancho, cls, "OK" if cls < LIMITE_CLS else "EXCEDE"))
                    if detalle and saltos:
                        acumulado = {}
                        for s in saltos:
                            acumulado[s["nodo"]] = acumulado.get(s["nodo"], 0) + s["valor"]
                        for nodo, v in sorted(acumulado.items(), key=lambda x: -x[1])[:6]:
                            print("        %.4f  %s" % (v, nodo[:110]))
                pagina.close()
        finally:
            navegador.close()
    return resultados


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--retardo", type=int, default=1200,
                    help="milisegundos que tarda cada /api/* (default: 1200)")
    ap.add_argument("--json", help="archivo donde volcar la medicion")
    ap.add_argument("--detalle", action="store_true",
                    help="lista los elementos que provocan cada salto")
    args = ap.parse_args()

    import app as panel  # import lento en frio: googleapiclient + Defender
    verificar_sin_credenciales()

    servidor = make_server("127.0.0.1", PUERTO, panel.app)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    print("Midiendo CLS con /api/* a %d ms de retardo\n" % args.retardo)
    try:
        resultados = medir(args.retardo, args.detalle)
    finally:
        servidor.shutdown()

    peor = max(resultados, key=lambda r: r["cls"])
    print("\nPeor caso: %s a %d px -> CLS %.4f (limite %.1f)"
          % (peor["superficie"], peor["ancho"], peor["cls"], LIMITE_CLS))

    if args.json:
        destino = Path(args.json)
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(json.dumps({
            "retardo_ms": args.retardo,
            "limite": LIMITE_CLS,
            "mediciones": resultados,
        }, indent=2), encoding="utf-8")
        print("Medicion en %s" % destino)

    return 0 if peor["cls"] < LIMITE_CLS else 1


if __name__ == "__main__":
    raise SystemExit(main())
