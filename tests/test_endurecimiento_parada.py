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


def _incidencias_vacias():
    """Dict `incidencias` fiel al contrato de `_buscar_negocios`.

    `cortes` es una LISTA (el worker la recorre), no un contador: un
    doble que la ponga a 0 revienta con "int object is not iterable" a
    mitad de corrida. El resto son contadores.
    """
    d = dict.fromkeys(app.CLAVES_INCIDENCIAS, 0)
    d["cortes"] = []
    return d


@pytest.fixture(autouse=True)
def _estado_limpio():
    """Deja el estado global como estaba.

    Restaura TRES cosas, y la lista se quedo corta en la primera version: solo
    devolvia `_import_job`. `_parada_solicitada` es un Event de modulo sin
    ambito de test, asi que quedaba `set()` para el resto de la sesion de
    pytest — y ahora que el codigo SI lo lee (guarda de corrida nueva y puntos
    de parada del bucle), eso haria que otros tests dependieran del orden de
    ejecucion de los archivos. El manejador de SIGTERM tambien se restaura:
    varios tests lo reinstalan.
    """
    import signal as _signal

    with app._import_lock:
        copia = dict(app._import_job)
    estaba_puesta = app._parada_solicitada.is_set()
    handler_previo = _signal.getsignal(_signal.SIGTERM)
    app._parada_solicitada.clear()
    yield
    with app._import_lock:
        app._import_job.clear()
        app._import_job.update(copia)
    if estaba_puesta:
        app._parada_solicitada.set()
    else:
        app._parada_solicitada.clear()
    _signal.signal(_signal.SIGTERM, handler_previo)


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

    def test_no_revienta_si_el_anterior_no_es_invocable(self, monkeypatch):
        """`getsignal` puede devolver SIG_DFL o SIG_IGN, que son enteros.

        `os.kill` se sustituye A PROPOSITO. La primera version de este test
        llamaba al manejador en vivo y, en cuanto el arreglo hizo que ese camino
        REENVIARA la senal de verdad, el test mataba al propio pytest: exit 15 a
        mitad de la suite. Que un test se suicide es la prueba de que el
        reenvio funciona, pero no es forma de comprobarlo.
        """
        enviado = {}
        previo = signal.signal(signal.SIGTERM, signal.SIG_DFL)
        try:
            app._instalar_parada_ordenada()
            monkeypatch.setattr(app.os, "kill",
                                lambda pid, sig: enviado.update(sig=sig))
            signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None)
            assert app._parada_solicitada.is_set()
            assert enviado.get("sig") == signal.SIGTERM
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

    def test_lo_ya_guardado_sobrevive_a_una_parada_a_media_corrida(self, monkeypatch):
        """La primera version de este test no medía nada.

        Pedía la parada ANTES de arrancar el worker, asi que el bucle cortaba en
        la primera vuelta sin tocar contadores, y el assert final comprobaba que
        unos valores que ningun codigo habia tocado seguian igual. Pasaba igual
        con y sin el arreglo.

        Ahora la parada llega DESPUES de que la primera categoria haya escrito
        de verdad, y se comprueba que lo producido por esa categoria sobrevive.
        """
        estado = {"categorias": 0}

        def _buscar(*a, **k):
            estado["categorias"] += 1
            # El doble debe devolver el mismo contrato que la funcion real:
            # `incidencias` lleva tres claves y el worker las lee todas.
            return ([{"Nombre": "F1", "Dirección": "D1"}], {},
                    _incidencias_vacias())

        def _exportar(resultados, categoria, ciudad, claves_existentes=None):
            # Al terminar de escribir la PRIMERA categoria llega el SIGTERM.
            if estado["categorias"] == 1:
                app._solicitar_parada_ordenada()
            return 3

        monkeypatch.setattr(app, "_buscar_negocios", _buscar)
        monkeypatch.setattr(app, "_exportar_a_sheets", _exportar)
        monkeypatch.setattr(app, "_claves_de_la_hoja", lambda ws: set())
        monkeypatch.setattr(app, "get_worksheet", lambda clave: MagicMock())
        monkeypatch.setattr(app, "_leer_cache_places", lambda: {})
        monkeypatch.setattr(app, "_guardar_cache_places", lambda c: None)
        monkeypatch.setattr(app, "_enviar_telegram_importador", lambda *a, **k: None)
        monkeypatch.setattr(app, "GMAPS_OK", True)
        monkeypatch.setattr(app, "googlemaps", MagicMock(Client=lambda key: MagicMock()))

        with app._import_lock:
            app._import_job.update({"status": "running", "cancelado": False,
                                    "parada_por_senal": False, "log": [],
                                    "medidor": {}, "encontrados": 0,
                                    "nuevos_en_sheet": 0, "duplicados": 0,
                                    "descartados": 0})
        app._worker_importador("Monterrey", "clave-de-prueba")

        with app._import_lock:
            assert estado["categorias"] == 1, (
                "no corto tras la primera categoria: la parada no llego al bucle"
            )
            assert app._import_job["nuevos_en_sheet"] == 3, (
                "se perdio lo que la primera categoria ya habia escrito"
            )
            assert app._import_job["status"] == "interrumpido"


class TestLaParadaLlegaADondeSeGastaDinero:
    """silent-failure-hunter, ALTA: el unico punto de control estaba entre las
    DOS categorias, y una categoria dura minutos. Con el graceful_timeout de
    gunicorn en 30 s por defecto, el SIGKILL llegaba antes de que el hilo
    alcanzara ese punto: la parada ordenada existia en el codigo y no se
    ejecutaba nunca en produccion."""

    def test_hay_puntos_de_parada_dentro_del_trabajo_de_una_categoria(self):
        """`_buscar_negocios` es donde se gasta el tiempo y el dinero."""
        import ast
        import inspect

        arbol = ast.parse(inspect.getsource(app._buscar_negocios))
        consultas = [n for n in ast.walk(arbol)
                     if isinstance(n, ast.Attribute) and n.attr == "is_set"]
        assert len(consultas) >= 2, (
            f"solo {len(consultas)} puntos de parada dentro de la categoria; "
            "sin ellos el unico control de la corrida esta entre categorias y "
            "el SIGKILL llega antes"
        )

    def test_el_graceful_timeout_esta_fijado(self):
        """30 s por defecto no alcanzan para llegar a un punto de parada.

        Solo el Dockerfile: `Procfile` y `nixpacks.toml` se retiraron el
        2026-09-05 al apagarse Railway (Task 10 del plan de Vultr). El VPS
        arranca por Docker, asi que ese es el unico sitio que manda.
        """
        import pathlib
        ruta = pathlib.Path(app.__file__).parent / "Dockerfile"
        assert "graceful-timeout" in ruta.read_text(encoding="utf-8"), (
            "el Dockerfile no fija graceful-timeout: la parada ordenada no "
            "llega a ejecutarse antes del SIGKILL"
        )

    def test_no_reaparecen_los_arranques_de_railway(self):
        """Si vuelven, vuelven sin graceful-timeout y con la deuda de tener
        tres sitios de arranque que pueden divergir."""
        import pathlib

        raiz = pathlib.Path(app.__file__).parent
        for muerto in ("Procfile", "nixpacks.toml"):
            assert not (raiz / muerto).exists(), (
                f"{muerto} reaparecio: Railway se apago el 2026-09-05 y sus "
                "artefactos se retiraron. Si vuelve el despliegue, hay que "
                "reponer tambien --graceful-timeout y --workers 1."
            )


class TestNoSeNeutralizaLaSenal:
    """python-reviewer, CRITICAL: si el manejador anterior no es invocable
    (SIG_DFL, que es el caso sin gunicorn delante: pytest, CI, `python app.py`),
    limitarse a poner la bandera y volver deja el proceso INMUNE a SIGTERM para
    siempre. Mi test anterior lo llamaba "no revienta" sin ver lo que implicaba.
    """

    def test_con_sig_dfl_la_senal_sigue_terminando_el_proceso(self, monkeypatch):
        reenviado = {}

        def _kill_falso(pid, sig):
            reenviado["pid"], reenviado["sig"] = pid, sig

        previo = signal.signal(signal.SIGTERM, signal.SIG_DFL)
        try:
            app._instalar_parada_ordenada()
            monkeypatch.setattr(app.os, "kill", _kill_falso)
            signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None)
            assert app._parada_solicitada.is_set()
            assert reenviado.get("sig") == signal.SIGTERM, (
                "no reenvio la senal: el proceso quedaria inmune a SIGTERM"
            )
            assert signal.getsignal(signal.SIGTERM) == signal.SIG_DFL, (
                "no restauro la disposicion original antes de reenviar"
            )
        finally:
            signal.signal(signal.SIGTERM, previo)


class TestGuardaDeCorridaNueva:
    """silent-failure-hunter, MEDIA: un SIGTERM recibido fuera de una corrida se
    perdia, y una corrida lanzada despues de la senal arrancaba sin marca."""

    def test_no_arranca_una_corrida_con_el_apagado_en_curso(self, monkeypatch):
        monkeypatch.setenv("GMAPS_API_KEY", "clave-de-prueba")
        app.app.config["TESTING"] = True
        c = app.app.test_client()
        app._solicitar_parada_ordenada()
        r = c.post("/api/importador/iniciar", json={"ciudad": "Monterrey"})
        assert r.status_code == 503, r.status_code
        assert r.get_json()["ok"] is False

    def test_con_el_apagado_no_en_curso_si_arranca(self, monkeypatch):
        """La contraria: el guarda no puede bloquear el uso normal."""
        monkeypatch.setenv("GMAPS_API_KEY", "clave-de-prueba")
        monkeypatch.setattr(app.threading, "Thread",
                            lambda *a, **k: MagicMock(start=lambda: None))
        monkeypatch.setattr(app, "_guardar_estado_importador", lambda e: None)
        app._parada_solicitada.clear()
        with app._import_lock:
            app._import_job["status"] = "idle"
        app.app.config["TESTING"] = True
        r = app.app.test_client().post("/api/importador/iniciar",
                                       json={"ciudad": "Monterrey"})
        assert r.status_code == 200, r.get_json()


def test_las_claves_de_incidencias_son_las_que_declara_la_constante():
    """Si `_buscar_negocios` gana o pierde una clave, los dobles de toda la
    suite dejan de ser fieles y revientan con KeyError a mitad de corrida.
    Esta comprobacion hace que la divergencia se note aqui y no alli."""
    import ast
    import inspect

    arbol = ast.parse(inspect.getsource(app._buscar_negocios))
    reales = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Dict) and nodo.keys:
            claves = {k.value for k in nodo.keys
                      if isinstance(k, ast.Constant) and isinstance(k.value, str)}
            if "ya_en_hoja" in claves:
                reales |= claves
    assert reales == set(app.CLAVES_INCIDENCIAS), (
        f"el contrato cambio: sobran {reales - set(app.CLAVES_INCIDENCIAS)}, "
        f"faltan {set(app.CLAVES_INCIDENCIAS) - reales}"
    )
