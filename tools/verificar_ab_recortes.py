"""A/B de los recortes de gasto: ¿ahorran tirando prospectos? (Plan 2, T2.6)

El metodo es el de agosto, no uno nuevo: se compara la **lista de aprobados** con y
sin cada recorte, y —esto es lo que hace valer el cero— **se demuestra que el chequeo
sabe detectar perdida**, forzando una configuracion que si pierde.

Un diff vacio solo significa algo si el mismo diff puede dar distinto de vacio.

**Que se compara aqui y por que.** El ADR de T2.3 decidio NO migrar, asi que no hay
configuracion "nueva" que contrastar contra la "vieja": el camino de Places no
cambio en este plan. Lo que si hay son **los dos recortes que agosto introdujo**, y
uno de ellos —`MAX_VARIACIONES_SIN_APORTE`— resulto **no ahorrar nada** en T2.0. Esta
herramienta mide los dos por separado: cuanto ahorra cada uno, y cuanto cuesta.

Ni red, ni hoja, ni Places. Uso:

    python tools/verificar_ab_recortes.py
"""
import os
import pathlib
import sys
import tempfile

RAIZ = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tools"))

os.environ.setdefault("PANEL_AUTH_DESACTIVADA", "1")

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import medir_llamadas_places as base  # noqa: E402


class GmapsQueAnota(base.GmapsContador):
    """Ademas de contar, recuerda QUE negocios devolvio cada consulta.

    Hace falta para el diff: comparar totales no distingue "los mismos 80" de
    "otros 80". La lista de aprobados sale del worksheet, que es donde acaban.
    """


def corrida(config, negocios=20, paginas=3, solape=0.5):
    """Una corrida real del importador con la configuracion dada.

    Devuelve las llamadas y **el conjunto de claves escritas en la hoja**, que es
    la lista de prospectos que el operador acaba teniendo.
    """
    import app

    previo = {k: getattr(app, k) for k in
              ("MAX_PAGINAS_POR_CONSULTA", "CORTAR_PAGINAS_SIN_APORTE",
               "MAX_VARIACIONES_SIN_APORTE", "PLACES_CACHE_FILE", "GMAPS_OK")}
    previo_mod = {"Client": app.googlemaps.Client, "sleep": app.time.sleep,
                  "ws": app.get_worksheet, "tg": app._enviar_telegram_importador,
                  "guardar": app._guardar_estado_importador}

    gmaps = GmapsQueAnota(negocios, paginas, solape)
    ws = base.WorksheetContador()
    try:
        for k, v in config.items():
            setattr(app, k, v)
        # Cache desechable POR DEFECTO, para que cada escenario mida aislado. Pero
        # si la configuracion trae una ruta, manda ella: es como se encadenan dos
        # corridas de la misma ciudad para ver el efecto del cacheo.
        #
        # La primera version ponia el temporal SIEMPRE, despues de aplicar la
        # config, y pisaba la ruta compartida: las dos corridas estrenaban cache y
        # el informe decia "la cache NO ahorro nada". Era mi bug, no del producto.
        if "PLACES_CACHE_FILE" not in config:
            app.PLACES_CACHE_FILE = os.path.join(
                tempfile.mkdtemp(prefix="ab_recortes_"), "places_detalles.json")
        app.GMAPS_OK = True
        app.time.sleep = lambda _s: None
        app._enviar_telegram_importador = lambda *a, **k: None
        app._guardar_estado_importador = lambda *a, **k: None
        app.googlemaps.Client = lambda key=None, **k: gmaps
        app.get_worksheet = lambda _n: ws
        app._import_job = app._nuevo_import_job("CiudadAB", status="running")
        app._worker_importador("CiudadAB", "clave-falsa")
    finally:
        for k, v in previo.items():
            setattr(app, k, v)
        app.googlemaps.Client = previo_mod["Client"]
        app.time.sleep = previo_mod["sleep"]
        app.get_worksheet = previo_mod["ws"]
        app._enviar_telegram_importador = previo_mod["tg"]
        app._guardar_estado_importador = previo_mod["guardar"]

    # La fila de la hoja: columna 1 nombre, columna 7 domicilio.
    aprobados = {f"{f[1]}|{f[7]}" for f in ws.filas[1:]}
    return {
        "text_search": gmaps.llamadas_text_search,
        "place_details": gmaps.llamadas_details,
        "aprobados": aprobados,
    }


SIN_RECORTES = {"CORTAR_PAGINAS_SIN_APORTE": False, "MAX_VARIACIONES_SIN_APORTE": 99}
SOLO_PAGINAS = {"CORTAR_PAGINAS_SIN_APORTE": True, "MAX_VARIACIONES_SIN_APORTE": 99}
LOS_DOS = {"CORTAR_PAGINAS_SIN_APORTE": True, "MAX_VARIACIONES_SIN_APORTE": 2}
# La contraprueba: un recorte absurdo que SI tiene que perder prospectos.
RECORTE_ABSURDO = {"CORTAR_PAGINAS_SIN_APORTE": True, "MAX_VARIACIONES_SIN_APORTE": 2,
                   "MAX_PAGINAS_POR_CONSULTA": 1}


def main():
    referencia = corrida(SIN_RECORTES)
    escenarios = [
        ("sin recortes (referencia)", referencia),
        ("solo el recorte por pagina", corrida(SOLO_PAGINAS)),
        ("los dos recortes (config real)", corrida(LOS_DOS)),
        ("CONTRAPRUEBA: 1 pagina por consulta", corrida(RECORTE_ABSURDO)),
    ]

    print("=" * 78)
    print("A/B DE LOS RECORTES  ·  ¿ahorran tirando prospectos?")
    print("=" * 78)
    print()
    print("  %-34s %7s %8s %10s %9s" % ("configuracion", "Text", "Details", "aprobados", "PERDIDOS"))
    print("  " + "-" * 72)
    perdidas = {}
    for nombre, r in escenarios:
        perdidos = referencia["aprobados"] - r["aprobados"]
        perdidas[nombre] = perdidos
        print("  %-34s %7d %8d %10d %9d"
              % (nombre, r["text_search"], r["place_details"],
                 len(r["aprobados"]), len(perdidos)))

    print()
    real = perdidas["los dos recortes (config real)"]
    absurdo = perdidas["CONTRAPRUEBA: 1 pagina por consulta"]

    print("  La configuracion REAL pierde: %d prospectos" % len(real))
    print("  La contraprueba pierde       : %d prospectos" % len(absurdo))
    print()
    if absurdo:
        print("  El chequeo SABE detectar perdida: el recorte absurdo la marca.")
    else:
        print("  ⚠ EL CHEQUEO NO DETECTA NADA. Su cero no vale: revisar el metodo.")
    if not real:
        print("  Y con esa capacidad demostrada, el diff vacio de la config real")
        print("  significa algo: los recortes ahorran SIN perder prospectos.")
    else:
        print("  ⚠ La config real PIERDE prospectos. Eso es un defecto, no un ahorro:")
        for k in sorted(real)[:5]:
            print("     -", k)

    # Cache: la segunda corrida de la misma ciudad no debe re-pagar Details.
    compartida = os.path.join(tempfile.mkdtemp(prefix="ab_cache_"), "places_detalles.json")
    import app
    previo = app.PLACES_CACHE_FILE
    try:
        app.PLACES_CACHE_FILE = compartida
        primera = corrida({**LOS_DOS, "PLACES_CACHE_FILE": compartida})
        segunda = corrida({**LOS_DOS, "PLACES_CACHE_FILE": compartida})
    finally:
        app.PLACES_CACHE_FILE = previo
    print()
    print("  Cache, misma ciudad dos veces:")
    print("    1a corrida -> %d Details" % primera["place_details"])
    print("    2a corrida -> %d Details %s"
          % (segunda["place_details"],
             "(la cache sirvio)" if segunda["place_details"] < primera["place_details"]
             else "⚠ NO AHORRO NADA"))

    return 0 if (absurdo and not real) else 1


if __name__ == "__main__":
    sys.exit(main())
