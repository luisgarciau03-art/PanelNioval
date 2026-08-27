"""Reproduce, de forma determinista y sin gastar API, los bugs del importador.

Plan 3 - T3.0/T3.1. Dos modos:

    python tools/reproducir_bugs_importador.py conteo
    python tools/reproducir_bugs_importador.py workers

`conteo` reproduce B1/B2/B3 (el numero que ve el operador no es el numero de
filas escritas) y B4 (un fallo de escritura termina en exito) con un cliente de
Places falso y una worksheet falsa. No toca la red ni la hoja de produccion:
la regla 10 del indice prohibe que los scripts de analisis llamen a APIs de pago,
y una corrida real ademas escribiria en `LISTA DE CONTACTOS`.

`workers` reproduce B5 (el estado vive en memoria de proceso). gunicorn no corre
en Windows -- necesita `fcntl` --, asi que se levantan DOS procesos Flask
independientes, que es exactamente el modelo de `gunicorn --workers 2`:
pre-fork, procesos separados, sin memoria compartida. Se lanza el trabajo en uno
y se sondea alternando entre los dos.
"""
import json
import os
import subprocess
import sys
import time
import pathlib

RAIZ = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

os.environ.setdefault("PANEL_AUTH_DESACTIVADA", "1")

# La consola de Windows es cp1252 y el log del importador lleva "✓".
# Sin esto el repro revienta al imprimir, no al reproducir.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


# ---------------------------------------------------------------- dobles de prueba

def _negocio(nombre, pid, direccion):
    """Un resultado de Places que pasa todos los filtros de calidad."""
    return {
        "place_id": pid,
        "name": nombre,
        "formatted_address": direccion,
        "rating": 4.5,
        "user_ratings_total": 120,
        "geometry": {"location": {"lat": 20.0, "lng": -103.0}},
    }


class GmapsFalso:
    """Cliente de Places falso. `por_categoria` mapea prefijo de query -> negocios."""

    def __init__(self, por_categoria):
        self.por_categoria = por_categoria
        self.llamadas_places = 0
        self.llamadas_detalle = 0

    def places(self, query=None, page_token=None, **kw):
        self.llamadas_places += 1
        for categoria, negocios in self.por_categoria.items():
            if query and query.startswith(categoria):
                return {"results": list(negocios)}
        return {"results": []}

    def place(self, pid, **kw):
        self.llamadas_detalle += 1
        return {"result": {"formatted_phone_number": "+52 33 1234 XXXX",
                           "website": "https://ejemplo.mx",
                           "opening_hours": {"weekday_text": ["L-V 9-18"]}}}


class WorksheetFalsa:
    """Worksheet en memoria. Columna 1 = Nombre, columna 7 = Direccion."""

    ENCABEZADO = ["NUM SEMANA", "Nombre", "Ciudad", "Categoria", "Telefono",
                  "", "", "Direccion"] + [""] * 11

    def __init__(self, preexistentes=()):
        self.filas = [self.ENCABEZADO]
        for nombre, direccion in preexistentes:
            fila = [""] * 19
            fila[1], fila[7] = nombre, direccion
            self.filas.append(fila)
        self.escrituras = 0

    def get_all_values(self):
        return [list(f) for f in self.filas]

    def append_rows(self, filas, **kw):
        self.escrituras += len(filas)
        self.filas.extend(filas)


# ---------------------------------------------------------------- modo conteo

def _preparar(app, gmaps_falso, worksheet_o_error):
    """Sustituye las fronteras externas de app.py por dobles."""
    app.GMAPS_OK = True
    app.googlemaps.Client = lambda key=None, **kw: gmaps_falso
    if isinstance(worksheet_o_error, Exception):
        err = worksheet_o_error

        def _get_ws(_nombre):
            raise err
        app.get_worksheet = _get_ws
    else:
        app.get_worksheet = lambda _nombre: worksheet_o_error
    app._enviar_telegram_importador = lambda *a, **kw: None
    app.time.sleep = lambda _s: None


def _catalogo(ferreterias, distribuidoras):
    """Las claves cubren la categoria con y sin acento, tal como la escribe app.py."""
    return {"Ferreterias": ferreterias,
            "Ferreterías": ferreterias,
            "Distribuidoras Ferreterias": distribuidoras,
            "Distribuidoras Ferreterías": distribuidoras}


def _job_limpio(ciudad="CiudadDemo"):
    return {"status": "running", "ciudad": ciudad, "categoria": "",
            "progreso": 0, "total": 2, "encontrados": 0, "descartados": 0,
            "resultados": [], "log": [], "error": ""}


def modo_conteo():
    import app

    # Escenario: una ciudad YA TRABAJADA, con solape entre las dos categorias.
    # 4 de las 12 ferreterias ya estan en la hoja; 6 de las 8 distribuidoras son
    # las MISMAS que ya aparecieron en la primera categoria.
    ferreterias = [_negocio("Ferreteria %d" % i, "pid-F%d" % i, "Calle %d" % i)
                   for i in range(1, 13)]
    distribuidoras = (
        [_negocio("Ferreteria %d" % i, "pid-F%d" % i, "Calle %d" % i) for i in range(1, 7)]
        + [_negocio("Distribuidora %d" % i, "pid-D%d" % i, "Avenida %d" % i)
           for i in range(1, 3)]
    )
    ya_en_hoja = [("Ferreteria %d" % i, "Calle %d" % i) for i in range(1, 5)]

    gmaps = GmapsFalso(_catalogo(ferreterias, distribuidoras))
    ws = WorksheetFalsa(preexistentes=ya_en_hoja)

    _preparar(app, gmaps, ws)
    app._import_job = _job_limpio()
    app._worker_importador("CiudadDemo", "clave-falsa")

    est = app._import_job
    filas_reales = ws.escrituras

    print("=" * 72)
    print("REPRO A - B1/B2/B3: el numero que ve el operador vs. filas en la hoja")
    print("=" * 72)
    print("  Escenario: 12 ferreterias + 8 distribuidoras (6 repetidas entre")
    print("             categorias) sobre una hoja que ya tenia 4 de ellas.")
    print("")
    print("  UI dice 'Encontrados'            : %d" % est["encontrados"])
    print("  Filas REALMENTE escritas en hoja : %d" % filas_reales)
    print("  Diferencia                       : %d" % (est["encontrados"] - filas_reales))
    print("  status final                     : %s" % est["status"])
    print("")
    print("  Mensaje final que lee el operador:")
    print("    \"%d contactos encontrados - %d descartados - Guardados en Google Sheets\""
          % (est["encontrados"], est["descartados"]))
    print("")
    print("  Desglose de la diferencia:")
    print("    B2 (ya estaban en la hoja)            : 4")
    print("    B3 (contados 2 veces entre categorias): 6")
    print("    B1 (el contador nunca usa 'nuevos')   : por eso ninguna resta se ve")
    print("")
    print("  Log interno (que si tiene el numero correcto, pero nadie mira):")
    for linea in est["log"]:
        print("    > %s" % linea)
    print("")

    # B4: la escritura explota y la corrida termina en exito.
    import importlib
    importlib.reload(app)
    gmaps2 = GmapsFalso(_catalogo(ferreterias, []))
    _preparar(app, gmaps2, RuntimeError("cuota de Sheets agotada (simulado)"))
    app._import_job = _job_limpio()
    app._worker_importador("CiudadDemo", "clave-falsa")
    est4 = app._import_job

    print("=" * 72)
    print("REPRO B - B4: la escritura falla y la corrida se declara exitosa")
    print("=" * 72)
    print("  get_worksheet lanza              : RuntimeError('cuota de Sheets agotada')")
    print("  Filas escritas                   : 0")
    print("  status final                     : %s" % est4["status"])
    print("  campo error                      : '%s'" % est4["error"])
    print("  UI dice 'Encontrados'            : %d" % est4["encontrados"])
    print("  Ultima linea del log             : %s"
          % (est4["log"][-1] if est4["log"] else "(vacio)"))
    print("")
    print("  VEREDICTO: cero filas escritas, status 'done', palomita verde.")
    print("")

    return {"encontrados": est["encontrados"], "filas_reales": filas_reales,
            "status_b4": est4["status"], "encontrados_b4": est4["encontrados"]}


# ---------------------------------------------------------------- modo workers

def modo_servidor(puerto):
    """Un worker: proceso Flask independiente con su propio _import_job."""
    import app

    def _buscar_lento(_cliente, _categoria, _ciudad):
        for _ in range(30):
            time.sleep(1)
        return ([_negocio("Demo", "pid-X", "Calle X")],
                {"pocas_resenas": 0, "baja_calificacion": 0,
                 "cerrado": 0, "sin_telefono": 0})

    app.GMAPS_OK = True
    app.googlemaps.Client = lambda key=None, **kw: object()
    app._buscar_negocios = _buscar_lento
    app._exportar_a_sheets = lambda *a, **kw: 1
    app._enviar_telegram_importador = lambda *a, **kw: None
    app.app.run(host="127.0.0.1", port=int(puerto), threaded=True, debug=False)


def modo_workers():
    import urllib.request

    puertos = [5061, 5062]
    entorno = dict(os.environ, PANEL_AUTH_DESACTIVADA="1",
                   GMAPS_API_KEY="clave-falsa-local")
    procesos = []
    for p in puertos:
        procesos.append(subprocess.Popen(
            [sys.executable, str(pathlib.Path(__file__)), "--servidor", str(p)],
            env=entorno, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))

    def _get(puerto, ruta):
        with urllib.request.urlopen("http://127.0.0.1:%d%s" % (puerto, ruta),
                                    timeout=5) as r:
            return json.loads(r.read().decode())

    try:
        for p in puertos:
            for _ in range(90):
                try:
                    _get(p, "/api/importador/estado")
                    break
                except Exception:
                    time.sleep(1)
            else:
                raise RuntimeError("el worker del puerto %d no arranco" % p)

        print("=" * 72)
        print("REPRO C - B5: el estado vive en memoria de proceso")
        print("=" * 72)
        print("  Dos procesos Flask independientes en %d y %d." % (puertos[0], puertos[1]))
        print("  Es el mismo modelo que 'gunicorn --workers 2' (pre-fork, sin")
        print("  memoria compartida). gunicorn no corre en Windows: necesita fcntl.")
        print("")

        req = urllib.request.Request(
            "http://127.0.0.1:%d/api/importador/iniciar" % puertos[0],
            data=json.dumps({"ciudad": "CiudadDemo"}).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=10) as r:
            print("  POST /iniciar -> worker %d: %s" % (puertos[0], r.read().decode().strip()))
        print("")

        filas = []
        idle = 0
        for i in range(20):
            puerto = puertos[i % 2]
            d = _get(puerto, "/api/importador/estado")
            if d["status"] == "idle":
                idle += 1
            filas.append((i + 1, puerto, d["status"], d["progreso"], d["encontrados"]))
            time.sleep(0.2)

        print("  20 sondeos alternando entre los dos workers:")
        print("    #   puerto  status   progreso  encontrados")
        for n, puerto, status, prog, enc in filas:
            marca = "  <-- MIENTE" if status == "idle" else ""
            print("    %-3d %d    %-8s %-9s %s%s" % (n, puerto, status, prog, enc, marca))
        print("")
        print("  Respuestas con status 'idle' mientras el trabajo corre: %d de 20" % idle)
        print("")
        print("  VEREDICTO: el worker que no lanzo el trabajo responde 'idle',")
        print("  'progreso 0' y 'encontrados 0'. Ese es el parpadeo que ve el owner.")
        print("  La proporcion 50% aqui es POR CONSTRUCCION (se alterna a proposito);")
        print("  lo que el experimento PRUEBA es que el proceso B no sabe nada del")
        print("  trabajo, no cual es el reparto real del balanceador de gunicorn.")
        return {"idle": idle, "total": 20}
    finally:
        for pr in procesos:
            pr.terminate()
            try:
                pr.wait(timeout=10)
            except Exception:
                pr.kill()


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--servidor":
        modo_servidor(sys.argv[2])
    elif len(sys.argv) >= 2 and sys.argv[1] == "conteo":
        modo_conteo()
    elif len(sys.argv) >= 2 and sys.argv[1] == "workers":
        modo_workers()
    else:
        print(__doc__)
        sys.exit(2)
