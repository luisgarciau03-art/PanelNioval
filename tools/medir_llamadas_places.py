"""Cuenta cuantas llamadas a Google Places hace una corrida del importador.

Plan 2 - T2.0 (sustituto de la mitad medible sin consola de facturacion).

T2.0 pedia el consumo por SKU desde la consola de Google Cloud. Esa parte esta
BLOQUEADA: no hay navegador, no hay `gcloud`, y la cuenta de servicio del
proyecto solo tiene alcances de Sheets y Drive. Queda escalada al owner.

Lo que SI se puede medir, y con mas precision que un recibo, es el numero de
llamadas que una corrida produce, por tipo:

    places()  -> Text Search   (una por variacion, mas una por pagina extra)
    place()   -> Place Details (una por negocio que pasa los filtros previos)

Ventajas sobre el recibo mensual: es exacto, es repetible, no cuesta nada, y
atribuye el cambio al CODIGO en vez de mezclarlo con el resto del consumo del
proyecto. Lo unico que no da es el importe en pesos; para eso hace falta la
consola, y el multiplicador se aplica despues sobre estos conteos.

Uso:
    python tools/medir_llamadas_places.py
    python tools/medir_llamadas_places.py --json    # para comparar corridas
"""
import json
import os
import pathlib
import sys
import tempfile

RAIZ = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tests"))

os.environ.setdefault("PANEL_AUTH_DESACTIVADA", "1")

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


class GmapsContador:
    """Cliente de Places falso que ademas CUENTA lo que se le pide.

    `paginas_por_variacion` modela una ciudad con mas de una pagina de
    resultados, que es lo normal en una ciudad mediana o grande.
    """

    def __init__(self, negocios_por_variacion=20, paginas_por_variacion=3,
                 solape_entre_categorias=0.5):
        self.n = negocios_por_variacion
        self.paginas = paginas_por_variacion
        self.solape = solape_entre_categorias
        self.llamadas_text_search = 0
        self.llamadas_details = 0
        self.details_pedidos = []
        self._pagina_de_token = {}

    def _lote(self, categoria, indice_pagina):
        """Negocios de una pagina. Las categorias se solapan a proposito."""
        base = 0 if categoria == "F" else int(self.n * self.paginas * (1 - self.solape))
        inicio = base + indice_pagina * self.n
        return [{
            "place_id": "pid-%d" % (inicio + i),
            "name": "Negocio %d" % (inicio + i),
            "formatted_address": "Calle %d" % (inicio + i),
            "rating": 4.5,
            "user_ratings_total": 120,
            "geometry": {"location": {"lat": 20.0, "lng": -103.0}},
        } for i in range(self.n)]

    def places(self, query=None, page_token=None, **kw):
        self.llamadas_text_search += 1
        cat = "F" if (query or "").startswith("Ferreter") else "D"
        idx = self._pagina_de_token.get(page_token, 0)
        resp = {"results": self._lote(cat, idx)}
        if idx + 1 < self.paginas:
            tok = "tok-%s-%d-%d" % (cat, idx, self.llamadas_text_search)
            self._pagina_de_token[tok] = idx + 1
            resp["next_page_token"] = tok
        return resp

    def place(self, pid, **kw):
        self.llamadas_details += 1
        self.details_pedidos.append(pid)
        return {"result": {"formatted_phone_number": "+52 33 1234 5678",
                           "website": "https://ejemplo.mx",
                           "opening_hours": {"weekday_text": ["L-V 9-18"]}}}


class WorksheetContador:
    ENCABEZADO = ["NUM SEMANA", "Nombre", "Ciudad", "Categoria", "Telefono",
                  "", "", "Direccion"] + [""] * 11

    def __init__(self, preexistentes=()):
        self.filas = [list(self.ENCABEZADO)]
        for nombre, direccion in preexistentes:
            fila = [""] * 19
            fila[1], fila[7] = nombre, direccion
            self.filas.append(fila)
        self.escrituras = 0
        self.lecturas = 0

    def get_all_values(self):
        self.lecturas += 1
        return [list(f) for f in self.filas]

    def append_rows(self, filas, **kw):
        self.escrituras += len(filas)
        self.filas.extend(filas)


def medir(ya_en_hoja=0, negocios=20, paginas=3, solape=0.5, cache=None):
    """Corre el importador con dobles instrumentados y devuelve los conteos.

    `cache` es la ruta del archivo de cache de Place Details:

    - `None` (por defecto) estrena una cache VACIA y desechable. Es lo
      correcto para medir un escenario aislado.
    - una ruta concreta encadena dos corridas sobre la MISMA cache, que es
      como se mide el efecto del cacheo: la segunda corrida de una ciudad.

    Sin este aislamiento la medicion miente, y ya lo hizo. La cache vive por
    defecto en el temp del SISTEMA, asi que sobrevive entre invocaciones del
    script: una medicion arrastraba 108 entradas de corridas anteriores y
    reportaba 0 Details en escenarios donde el codigo si habria pagado. Con
    eso, el ahorro de la cache y el de deduplicar contra la hoja quedaban
    sumados en un solo numero y no habia forma de atribuir cual hizo que.
    """
    import app

    if cache is None:
        cache = os.path.join(tempfile.mkdtemp(prefix="medicion_places_"),
                             "places_detalles.json")
    app.PLACES_CACHE_FILE = cache

    gmaps = GmapsContador(negocios, paginas, solape)
    # Una ciudad ya trabajada: parte de lo que Places devuelve ya esta en la hoja.
    pre = [("Negocio %d" % i, "Calle %d" % i) for i in range(ya_en_hoja)]
    ws = WorksheetContador(pre)

    app.GMAPS_OK = True
    app.time.sleep = lambda _s: None
    app._enviar_telegram_importador = lambda *a, **k: None
    app._guardar_estado_importador = lambda *a, **k: None
    app.googlemaps.Client = lambda key=None, **k: gmaps
    app.get_worksheet = lambda _n: ws
    app._import_job = app._nuevo_import_job("CiudadReferencia", status="running")
    app._worker_importador("CiudadReferencia", "clave-falsa")

    j = app._import_job
    return {
        "text_search": gmaps.llamadas_text_search,
        "place_details": gmaps.llamadas_details,
        "details_distintos": len(set(gmaps.details_pedidos)),
        "details_repetidos": len(gmaps.details_pedidos) - len(set(gmaps.details_pedidos)),
        "lecturas_hoja": ws.lecturas,
        "filas_escritas": ws.escrituras,
        "encontrados": j["encontrados"],
        "nuevos_en_sheet": j["nuevos_en_sheet"],
        "duplicados": j["duplicados"],
        "descartados": j["descartados"],
        "status": j["status"],
    }


ESCENARIOS = [
    ("ciudad nueva (nada en la hoja)", dict(ya_en_hoja=0)),
    ("ciudad a medio trabajar (30 ya en la hoja)", dict(ya_en_hoja=30)),
    ("ciudad ya trabajada (90 ya en la hoja)", dict(ya_en_hoja=90)),
]


def main():
    filas = [(nombre, medir(**kw)) for nombre, kw in ESCENARIOS]

    # La segunda corrida de la MISMA ciudad, compartiendo cache con la
    # primera. Es el unico escenario que aisla el efecto del cacheo: los
    # otros tres estrenan cache, asi que miden solo la deduplicacion contra
    # la hoja. Mezclarlos fue lo que produjo la medicion falsa anterior.
    compartida = os.path.join(tempfile.mkdtemp(prefix="medicion_2a_"),
                              "places_detalles.json")
    medir(ya_en_hoja=0, cache=compartida)
    filas.append(("segunda corrida, misma ciudad (cache caliente)",
                  medir(ya_en_hoja=0, cache=compartida)))

    if "--json" in sys.argv:
        print(json.dumps({n: r for n, r in filas}, indent=2, ensure_ascii=False))
        return

    print("=" * 78)
    print("LLAMADAS A GOOGLE PLACES POR CORRIDA  (2 categorias x 3 variaciones x 3 paginas)")
    print("=" * 78)
    print()
    print("  %-42s %8s %8s %8s" % ("escenario", "Text", "Details", "filas"))
    print("  %-42s %8s %8s %8s" % ("", "Search", "", "nuevas"))
    print("  " + "-" * 70)
    for nombre, r in filas:
        print("  %-42s %8d %8d %8d"
              % (nombre, r["text_search"], r["place_details"], r["filas_escritas"]))
    print()
    for nombre, r in filas:
        desperdicio = r["place_details"] - r["filas_escritas"]
        pct = (desperdicio * 100 // r["place_details"]) if r["place_details"] else 0
        print("  %s:" % nombre)
        print("    Details pagados        : %d" % r["place_details"])
        print("    de esos, repetidos     : %d" % r["details_repetidos"])
        print("    filas nuevas obtenidas : %d" % r["filas_escritas"])
        print("    -> pagados y tirados   : %d  (%d %% del gasto de Details)"
              % (desperdicio, pct))
        print()
    print("  Nota: el importe en pesos necesita la consola de facturacion, que")
    print("  esta fuera de alcance (T2.0 BLOQUEADA). Estos conteos son la base")
    print("  sobre la que se aplica el precio por SKU cuando el owner lo aporte.")


if __name__ == "__main__":
    main()
