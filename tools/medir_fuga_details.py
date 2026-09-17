"""Cuanto Place Details se paga por negocios que nunca llegan a la hoja.

Plan 2 - T2.1. Lo que persigue: el filtro `sin_telefono` corre DESPUES de pagar el
Place Details, asi que **cada negocio sin telefono es un Details tirado**.

QUE MIDE ESTO Y QUE NO
----------------------

Mide el **mecanismo**: cuantos Details se pagan, cuantos se tiran, y como responde el
gasto cuando cambia la proporcion de negocios sin telefono. Eso es exacto y repetible.

NO mide la **tasa real** de negocios sin telefono en Google Places: eso es una
propiedad de los datos de Google y solo se obtiene llamando a Google, que cuesta
dinero y es gate del owner. Por eso el resultado se da como una CURVA sobre la tasa,
no como un numero suelto: en cuanto el owner aporte una tasa medida, el ahorro sale
de leer la fila correspondiente.

La tasa del DENUE (INEGI) se reporta aparte, en el documento de T2.1, como lo que es:
una referencia de otra fuente, no la de Google.

Uso:
    python tools/medir_fuga_details.py
    python tools/medir_fuga_details.py --json
"""
import json
import os
import pathlib
import sys
import tempfile

RAIZ = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tools"))
sys.path.insert(0, str(RAIZ / "tests"))

os.environ.setdefault("PANEL_AUTH_DESACTIVADA", "1")

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import medir_llamadas_places as base  # noqa: E402


class GmapsConSinTelefono(base.GmapsContador):
    """Igual que el contador de T2.0, pero una fraccion de negocios NO tiene telefono.

    Es la pieza que faltaba. El doble de T2.0 aprueba a TODOS, asi que
    `sin_telefono` nunca descarta a nadie y la fuga medida seria **cero por
    construccion** — un cero del fixture, no del codigo.
    """

    def __init__(self, *a, pct_sin_telefono=0, **kw):
        super().__init__(*a, **kw)
        self.pct = pct_sin_telefono
        self.details_sin_telefono = 0

    def _sin_telefono(self, pid):
        """Determinista por `place_id`: la misma corrida repetida da lo mismo."""
        try:
            n = int(str(pid).rsplit("-", 1)[-1])
        except ValueError:
            n = abs(hash(pid))
        return (n % 100) < self.pct

    def place(self, pid, **kw):
        self.llamadas_details += 1
        self.details_pedidos.append(pid)
        if self._sin_telefono(pid):
            self.details_sin_telefono += 1
            # Un negocio sin telefono: Google cobro el Details igual.
            return {"result": {"website": "https://ejemplo.mx",
                               "opening_hours": {"weekday_text": ["L-V 9-18"]}}}
        return {"result": {"formatted_phone_number": "+52 33 1234 5678",
                           "website": "https://ejemplo.mx",
                           "opening_hours": {"weekday_text": ["L-V 9-18"]}}}


def medir(pct_sin_telefono=0, ya_en_hoja=0, negocios=20, paginas=3, solape=0.5,
          cache=None):
    """Una corrida completa del importador real, con el doble parametrizado."""
    import app

    if cache is None:
        cache = os.path.join(tempfile.mkdtemp(prefix="fuga_details_"),
                             "places_detalles.json")
    previo = {
        "cache": app.PLACES_CACHE_FILE,
        "GMAPS_OK": app.GMAPS_OK,
        "Client": app.googlemaps.Client,
        "sleep": app.time.sleep,
        "get_worksheet": app.get_worksheet,
        "telegram": app._enviar_telegram_importador,
        "guardar": app._guardar_estado_importador,
    }
    gmaps = GmapsConSinTelefono(negocios, paginas, solape,
                                pct_sin_telefono=pct_sin_telefono)
    ws = base.WorksheetContador(
        [("Negocio %d" % i, "Calle %d" % i) for i in range(ya_en_hoja)])
    try:
        app.PLACES_CACHE_FILE = cache
        app.GMAPS_OK = True
        app.time.sleep = lambda _s: None
        app._enviar_telegram_importador = lambda *a, **k: None
        app._guardar_estado_importador = lambda *a, **k: None
        app.googlemaps.Client = lambda key=None, **k: gmaps
        app.get_worksheet = lambda _n: ws
        app._import_job = app._nuevo_import_job("CiudadReferencia", status="running")
        app._worker_importador("CiudadReferencia", "clave-falsa")
        j = dict(app._import_job)
    finally:
        # `app.time` y `app.googlemaps` son los modulos REALES del proceso: dejarlos
        # parcheados convierte `time.sleep` en un no-op para todo lo que venga
        # despues. T2.0 lo dejo anotado como pendiente; aqui se restaura.
        app.PLACES_CACHE_FILE = previo["cache"]
        app.GMAPS_OK = previo["GMAPS_OK"]
        app.googlemaps.Client = previo["Client"]
        app.time.sleep = previo["sleep"]
        app.get_worksheet = previo["get_worksheet"]
        app._enviar_telegram_importador = previo["telegram"]
        app._guardar_estado_importador = previo["guardar"]

    pagados = gmaps.llamadas_details
    return {
        "pct_sin_telefono_fixture": pct_sin_telefono,
        "text_search": gmaps.llamadas_text_search,
        "details_pagados": pagados,
        "details_sin_telefono": gmaps.details_sin_telefono,
        "tasa_desperdicio": (gmaps.details_sin_telefono / pagados) if pagados else 0.0,
        "filas_escritas": ws.escrituras,
        "aprobados": j["encontrados"],
        "descartados": j["descartados"],
        "nuevos_en_sheet": j["nuevos_en_sheet"],
    }


CURVA = [0, 10, 20, 30, 40, 50, 58, 60, 70]


def main():
    filas = [medir(pct_sin_telefono=p) for p in CURVA]
    trabajada = [medir(pct_sin_telefono=p, ya_en_hoja=90) for p in (0, 58)]

    if "--json" in sys.argv:
        print(json.dumps({"ciudad_virgen": filas, "ciudad_trabajada": trabajada},
                         indent=2, ensure_ascii=False))
        return 0

    print("=" * 78)
    print("FUGA DE PLACE DETAILS  ·  el filtro de telefono corre DESPUES de pagar")
    print("=" * 78)
    print()
    print("  %-14s %9s %9s %11s %9s" % ("sin telefono", "Details", "tirados", "tasa de", "filas"))
    print("  %-14s %9s %9s %11s %9s" % ("(fixture)", "pagados", "", "desperdicio", "nuevas"))
    print("  " + "-" * 62)
    for r in filas:
        print("  %-14s %9d %9d %10.1f %% %9d"
              % ("%d %%" % r["pct_sin_telefono_fixture"], r["details_pagados"],
                 r["details_sin_telefono"], r["tasa_desperdicio"] * 100,
                 r["filas_escritas"]))
    print()
    print("  Ciudad YA TRABAJADA (90 de sus negocios ya en la hoja):")
    for r in trabajada:
        print("    sin telefono %2d %% -> Details pagados %3d, tirados %3d, filas %3d"
              % (r["pct_sin_telefono_fixture"], r["details_pagados"],
                 r["details_sin_telefono"], r["filas_escritas"]))
    print()
    print("  La tasa de desperdicio SIGUE A LA TASA DE ENTRADA, 1 a 1: cada negocio")
    print("  sin telefono cuesta exactamente un Details. No hay amortiguacion.")
    print()
    print("  Lo que NO dice esto: cual es la tasa REAL en Google Places. Eso solo")
    print("  sale de una corrida real, que cuesta dinero y es gate del owner.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
