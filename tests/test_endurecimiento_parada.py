"""Plan 5 · T5.5 (M3) — cierre ordenado del hilo del importador ante SIGTERM.

El hilo se lanza con `daemon=True`: un reinicio del contenedor lo mata a media
corrida. El Plan 3 ya cerro la mitad visible (hay un registro persistido que
permite decir "se interrumpio" tras el reinicio y que **nunca veta** una corrida
nueva). Lo que faltaba es que el reinicio no parta el trabajo: que la corrida se
entere de que la estan parando y cierre con lo ya guardado.

NO se inventa un segundo camino de salida. El bucle YA consulta una bandera
entre categorias para la cancelacion manual del operador; T5.5 engancha la senal
a esa misma bandera, que es lo que pide el plan al decir "reutilizar el patron de
presupuesto_agotado en vez de inventar un segundo camino".

EL DETALLE QUE DECIDE SI ESTO FUNCIONA O ES UN NO-OP:
En `gunicorn/workers/base.py`, `init_signals()` corre en la linea 120 y
`load_wsgi()` —que importa `app.py`— en la 137. O sea que gunicorn instala su
manejador de SIGTERM ANTES de importar la app, y un `signal.signal()` nuestro al
importar lo REEMPLAZARIA. Su `handle_exit` solo hace `self.alive = False`, que
es como el worker se entera de que debe terminar: pisarlo dejaria a gunicorn sin
apagado ordenado. Por eso se ENCADENA al anterior en vez de sustituirlo.
"""
import signal
import threading
from unittest.mock import MagicMock

import pytest

import app


@pytest.fixture(autouse=True)
def _estado_limpio():
    """Deja `_import_job` como estaba: es un global de modulo y un test que lo
    ensucia contamina a los siguientes."""
    with app._import_lock:
        copia = dict(app._import_job)
    yield
    with app._import_lock:
        app._import_job.clear()
        app._import_job.update(copia)


class TestParadaCooperativa:

    def test_existe_la_bandera_de_parada(self):
        assert hasattr(app, "_parada_solicitada")
        assert isinstance(app._parada_solicitada, threading.Event)

    def test_solicitar_parada_marca_la_corrida(self):
        with app._import_lock:
            app._import_job["status"] = "running"
            app._import_job["cancelado"] = False
        app._solicitar_parada_ordenada()
        assert app._parada_solicitada.is_set()
        with app._import_lock:
            assert app._import_job["cancelado"] is True, (
                "el bucle consulta esta bandera entre categorias: sin ella la "
                "parada no llega nunca al worker"
            )

    def test_distingue_parada_por_senal_de_cancelacion_manual(self):
        """Que el operador pulse Detener y que el contenedor se reinicie NO son
        lo mismo, y la interfaz los muestra distinto."""
        app._solicitar_parada_ordenada()
        with app._import_lock:
            assert app._import_job.get("parada_por_senal") is True

    def test_es_idempotente(self):
        """SIGTERM puede llegar dos veces (docker stop y luego el timeout)."""
        app._solicitar_parada_ordenada()
        app._solicitar_parada_ordenada()
        assert app._parada_solicitada.is_set()


class TestElHandlerEncadena:
    """Lo mas importante de T5.5: no romper el apagado de gunicorn.

    `init_signals()` de gunicorn corre ANTES de importar `app.py`, asi que
    nuestro handler pisa el suyo. Su `handle_exit` pone `alive = False`, que es
    como el worker sabe que debe terminar. Sustituirlo sin llamarlo dejaria al
    worker sin enterarse, y el apagado acabaria en SIGKILL a los 30 s.
    """

    def test_instalar_devuelve_el_anterior_y_lo_conserva(self):
        testigo = {"llamado": False}

        def anterior(sig, frame):
            testigo["llamado"] = True

        previo = signal.signal(signal.SIGTERM, anterior)
        try:
            app._instalar_parada_ordenada()
            nuevo = signal.getsignal(signal.SIGTERM)
            assert nuevo is not anterior, "no instalo nada"
            nuevo(signal.SIGTERM, None)
            assert testigo["llamado"], (
                "el handler NO llamo al anterior: gunicorn se quedaria sin su "
                "handle_exit y el worker no se enteraria de que debe parar"
            )
            assert app._parada_solicitada.is_set()
        finally:
            signal.signal(signal.SIGTERM, previo)

    def test_no_revienta_si_el_anterior_no_es_invocable(self):
        """`getsignal` puede devolver SIG_DFL o SIG_IGN, que son enteros."""
        previo = signal.signal(signal.SIGTERM, signal.SIG_DFL)
        try:
            app._instalar_parada_ordenada()
            signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None)
            assert app._parada_solicitada.is_set()
        finally:
            signal.signal(signal.SIGTERM, previo)

    def test_no_se_instala_fuera_del_hilo_principal(self):
        """`signal.signal` solo funciona en el hilo principal y lanza
        ValueError en cualquier otro. Instalarlo desde un hilo tumbaria el
        arranque, asi que debe devolver False sin reventar."""
        resultado = {}

        def en_otro_hilo():
            resultado["ok"] = app._instalar_parada_ordenada()

        h = threading.Thread(target=en_otro_hilo)
        h.start()
        h.join()
        assert resultado["ok"] is False


class TestElBucleSeDetiene:
    """CE9 — la parada se consulta ENTRE categorias, nunca a media escritura."""

    def test_el_worker_sale_si_la_parada_ya_estaba_pedida(self, monkeypatch):
        """Con la parada pedida antes de arrancar, no debe llamarse ni una vez
        a Places ni escribirse en la hoja."""
        llamadas = {"places": 0, "escrituras": 0}

        def _buscar(*a, **k):
            llamadas["places"] += 1
            return [], {}, {"ya_en_hoja": 0}

        def _exportar(*a, **k):
            llamadas["escrituras"] += 1
            return 0

        monkeypatch.setattr(app, "_buscar_negocios", _buscar)
        monkeypatch.setattr(app, "_exportar_a_sheets", _exportar)
        monkeypatch.setattr(app, "_claves_de_la_hoja", lambda ws: set())
        monkeypatch.setattr(app, "get_worksheet", lambda clave: MagicMock())
        monkeypatch.setattr(app, "_leer_cache_places", lambda: {})
        monkeypatch.setattr(app, "_guardar_cache_places", lambda c: None)
        monkeypatch.setattr(app, "_enviar_telegram_importador",
                            lambda *a, **k: None)
        monkeypatch.setattr(app, "GMAPS_OK", True)
        monkeypatch.setattr(app, "googlemaps",
                            MagicMock(Client=lambda key: MagicMock()))

        with app._import_lock:
            app._import_job.update({"status": "running", "cancelado": False,
                                    "parada_por_senal": False, "log": [],
                                    "medidor": {}, "encontrados": 0,
                                    "nuevos_en_sheet": 0, "duplicados": 0,
                                    "descartados": 0})
        app._solicitar_parada_ordenada()
        app._worker_importador("Monterrey", "clave-de-prueba")

        assert llamadas["places"] == 0, "gasto Places con la parada ya pedida"
        assert llamadas["escrituras"] == 0, "escribio con la parada ya pedida"

    def test_el_estado_final_es_interrumpido_y_no_cancelado(self, monkeypatch):
        """Una parada por senal NO es una cancelacion del operador: la interfaz
        las muestra distinto y el registro persistido tambien."""
        monkeypatch.setattr(app, "_claves_de_la_hoja", lambda ws: set())
        monkeypatch.setattr(app, "get_worksheet", lambda clave: MagicMock())
        monkeypatch.setattr(app, "_leer_cache_places", lambda: {})
        monkeypatch.setattr(app, "_guardar_cache_places", lambda c: None)
        monkeypatch.setattr(app, "_enviar_telegram_importador",
                            lambda *a, **k: None)
        monkeypatch.setattr(app, "GMAPS_OK", True)
        monkeypatch.setattr(app, "googlemaps",
                            MagicMock(Client=lambda key: MagicMock()))

        with app._import_lock:
            app._import_job.update({"status": "running", "cancelado": False,
                                    "parada_por_senal": False, "log": [],
                                    "medidor": {}, "encontrados": 0,
                                    "nuevos_en_sheet": 0, "duplicados": 0,
                                    "descartados": 0})
        app._solicitar_parada_ordenada()
        app._worker_importador("Monterrey", "clave-de-prueba")

        with app._import_lock:
            assert app._import_job["status"] == "interrumpido", (
                f"quedo en {app._import_job['status']}"
            )

    def test_lo_ya_guardado_sobrevive(self, monkeypatch):
        """Los contadores de lo escrito antes del corte no se pierden ni se
        ponen a cero: lo que esta en la hoja es valido."""
        with app._import_lock:
            app._import_job.update({"status": "running", "cancelado": False,
                                    "parada_por_senal": False, "log": [],
                                    "medidor": {}, "encontrados": 12,
                                    "nuevos_en_sheet": 7, "duplicados": 5,
                                    "descartados": 3})
        monkeypatch.setattr(app, "_claves_de_la_hoja", lambda ws: set())
        monkeypatch.setattr(app, "get_worksheet", lambda clave: MagicMock())
        monkeypatch.setattr(app, "_leer_cache_places", lambda: {})
        monkeypatch.setattr(app, "_guardar_cache_places", lambda c: None)
        monkeypatch.setattr(app, "_enviar_telegram_importador",
                            lambda *a, **k: None)
        monkeypatch.setattr(app, "GMAPS_OK", True)
        monkeypatch.setattr(app, "googlemaps",
                            MagicMock(Client=lambda key: MagicMock()))

        app._solicitar_parada_ordenada()
        app._worker_importador("Monterrey", "clave-de-prueba")

        with app._import_lock:
            assert app._import_job["nuevos_en_sheet"] == 7
            assert app._import_job["encontrados"] == 12
