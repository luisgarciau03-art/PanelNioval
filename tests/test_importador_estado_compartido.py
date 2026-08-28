"""Estado del importador entre procesos (Plan 3 - T3.5, defecto B5).

`_import_job` y `_cache` son globales de modulo. Con `gunicorn --workers 2` eso
son dos procesos sin memoria compartida: medido, 10 de 20 sondeos alternados
respondian `status: 'idle'` con el trabajo corriendo.

La decision (ver `docs/adr/2026-08-27-estado-compartido-importador.md`) es correr
UN proceso con hilos, en vez de sincronizar dos. Estos tests protegen esa
decision de deshacerse sola.
"""
import os
import re
import threading

import pytest

import app

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _leer(nombre):
    with open(os.path.join(RAIZ, nombre), encoding="utf-8") as fh:
        return fh.read()


# ─────────────── el arranque no puede volver a partirse en dos ───────────────

ARCHIVOS_DE_ARRANQUE = ["Procfile", "Dockerfile", "nixpacks.toml"]


def _sin_comentarios(texto):
    """Quita las lineas de comentario.

    Hace falta: el Dockerfile explica en un comentario por que NO se usan 2
    workers, y un lector ingenuo tomaria ese 2 como la configuracion real.
    """
    return "\n".join(l for l in texto.split("\n")
                     if not l.lstrip().startswith("#"))


def _workers_declarados(texto):
    """Extrae el valor de --workers, venga como bandera suelta o como lista JSON."""
    m = re.search(r'--workers"?,?\s*"?(\d+)', _sin_comentarios(texto))
    return int(m.group(1)) if m else None


class TestArranqueConsistente:
    """El hallazgo del panel: un cambio de config es invisible para la suite.

    `--workers` vive en TRES archivos y en dos rutas de despliegue distintas
    (Railway y Docker/VPS). Arreglar dos y olvidar el tercero deja el bug vivo en
    produccion con toda la suite en verde. Esto lo convierte en algo que falla.
    """

    @pytest.mark.parametrize("archivo", ARCHIVOS_DE_ARRANQUE)
    def test_cada_arranque_declara_un_solo_worker(self, archivo):
        n = _workers_declarados(_leer(archivo))
        assert n is not None, "%s ya no declara --workers" % archivo
        assert n == 1, (
            "%s arranca %d workers. Con mas de uno, _import_job y _cache vuelven a "
            "vivir en memorias separadas y los sondeos vuelven a mentir "
            "(ver docs/adr/2026-08-27-estado-compartido-importador.md)" % (archivo, n)
        )

    def test_los_tres_arranques_declaran_lo_mismo(self):
        valores = {a: _workers_declarados(_leer(a)) for a in ARCHIVOS_DE_ARRANQUE}
        assert len(set(valores.values())) == 1, (
            "los archivos de arranque no coinciden: %r" % valores
        )

    @pytest.mark.parametrize("archivo", ARCHIVOS_DE_ARRANQUE)
    def test_un_solo_worker_va_con_hilos(self, archivo):
        """Un worker sin hilos serializaria las peticiones tras el sondeo de 3 s."""
        texto = _leer(archivo)
        m = re.search(r'--threads"?,?\s*"?(\d+)', texto)
        assert m and int(m.group(1)) > 1, (
            "%s corre 1 worker sin --threads: las peticiones se serializan" % archivo
        )


# ─────────────────────── _cache bajo varios hilos ───────────────────────

class TestCacheConLock:
    def test_existe_un_lock_para_la_cache(self):
        assert hasattr(app, "_cache_lock"), (
            "_cache no tiene lock. Se muta desde el hilo daemon del importador "
            "(app.py, _exportar_a_sheets) a la vez que los hilos de peticion."
        )

    def test_escritura_concurrente_no_corrompe_la_cache(self):
        """Con 4 hilos, `if key in _cache` seguido de `_cache[key]` deja de ser seguro.

        Los cuatro hilos pelean por LA MISMA clave a proposito: con una clave por
        hilo no hay contencion y el test pasaria incluso sin lock, que es
        justamente lo que se quiere descartar.
        """
        errores = []

        def escribe(n):
            try:
                for i in range(200):
                    app._cache_set("clave_compartida", (n, i))
                    app._cache_get("clave_compartida")
                    app._cache_pop("clave_compartida")
            except Exception as e:  # pragma: no cover
                errores.append(e)

        hilos = [threading.Thread(target=escribe, args=(n,)) for n in range(4)]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join()
        assert not errores, "la cache se corrompio con 4 hilos: %r" % errores

    def test_cache_get_distingue_ausente_de_valor_falsy(self):
        """Un 0 o una lista vacia en cache son valores validos, no 'no esta'."""
        app._cache_pop("prueba_falsy")
        assert app._cache_get("prueba_falsy") is None
        app._cache_set("prueba_falsy", [])
        assert app._cache_get("prueba_falsy") == []
        app._cache_pop("prueba_falsy")


# ───────────── una corrida interrumpida se nota, y no bloquea ─────────────

class TestCorridaInterrumpida:
    def test_el_registro_no_lleva_datos_personales(self, tmp_path, monkeypatch):
        """Un archivo de estado es un log con otro nombre.

        Las reglas del proyecto prohiben volcar nombres, domicilios y telefonos
        de clientes. El registro solo lleva contadores, estado y PID.
        """
        monkeypatch.setattr(app, "IMPORT_ESTADO_FILE", str(tmp_path / "estado.json"))
        job = app._nuevo_import_job("Guadalajara", status="running")
        job["encontrados"] = 14
        job["resultados"] = [{"Nombre": "Ferreteria X",
                              "Teléfono": "+52 33 1234 5678",
                              "Dirección": "Calle Falsa 123"}]
        app._guardar_estado_importador(job)

        crudo = (tmp_path / "estado.json").read_text(encoding="utf-8")
        for prohibido in ("Ferreteria X", "1234 5678", "Calle Falsa"):
            assert prohibido not in crudo, (
                "el registro de estado filtro un dato personal: %r" % prohibido
            )
        assert "14" in crudo, "el registro deberia conservar los contadores"

    def test_corrida_de_proceso_muerto_se_reporta_interrumpida(self, tmp_path, monkeypatch):
        monkeypatch.setattr(app, "IMPORT_ESTADO_FILE", str(tmp_path / "estado.json"))
        job = app._nuevo_import_job("Guadalajara", status="running")
        app._guardar_estado_importador(job, pid=999999)  # PID que no existe
        rec = app._leer_estado_importador()
        assert rec is not None
        assert rec["status"] == "interrumpido", (
            "una corrida cuyo proceso ya no existe sigue diciendo %r" % rec["status"]
        )

    def test_una_corrida_interrumpida_no_bloquea_una_nueva(self, tmp_path, monkeypatch):
        """La trampa que el panel senalo en la opcion B.

        Persistir 'running' sin comprobar si el proceso vive cambia "arrancan dos
        corridas" por "no puede arrancar ninguna". El registro informa; nunca veta.
        """
        monkeypatch.setattr(app, "IMPORT_ESTADO_FILE", str(tmp_path / "estado.json"))
        app._guardar_estado_importador(
            app._nuevo_import_job("Guadalajara", status="running"), pid=999999)
        monkeypatch.setattr(app, "_import_job", app._nuevo_import_job())
        monkeypatch.setattr(app, "GMAPS_OK", True)
        monkeypatch.setenv("GMAPS_API_KEY", "clave-de-prueba")
        monkeypatch.setattr(app.threading, "Thread",
                            lambda *a, **k: type("H", (), {"start": lambda s: None})())

        app.app.config["TESTING"] = True
        r = app.app.test_client().post("/api/importador/iniciar",
                                       json={"ciudad": "Guadalajara"})
        assert r.get_json()["ok"] is True, (
            "un registro huerfano bloqueo una corrida nueva: %r" % r.get_json()
        )

    def test_registro_ilegible_no_tumba_el_panel(self, tmp_path, monkeypatch):
        ruta = tmp_path / "estado.json"
        ruta.write_text("{esto no es json", encoding="utf-8")
        monkeypatch.setattr(app, "IMPORT_ESTADO_FILE", str(ruta))
        assert app._leer_estado_importador() is None


class TestEstadoReportaInterrupcion:
    @pytest.fixture
    def client(self):
        app.app.config["TESTING"] = True
        return app.app.test_client()

    def test_tras_reiniciar_el_panel_dice_interrumpido_no_idle(
            self, client, tmp_path, monkeypatch):
        """El sintoma que ve el operador tras un redespliegue a media corrida.

        `_import_job` vuelve a 'idle' al reiniciar el proceso, asi que la pantalla
        aparece limpia: ni barra, ni log, ni aviso. Como si nunca hubiera lanzado
        nada. El registro esta para que el panel pueda decir lo que paso.
        """
        monkeypatch.setattr(app, "IMPORT_ESTADO_FILE", str(tmp_path / "estado.json"))
        job = app._nuevo_import_job("Guadalajara", status="running")
        job["encontrados"], job["nuevos_en_sheet"] = 14, 10
        app._guardar_estado_importador(job, pid=999999)   # el proceso ya no existe
        monkeypatch.setattr(app, "_import_job", app._nuevo_import_job())  # reinicio

        d = client.get("/api/importador/estado").get_json()
        assert d["status"] == "interrumpido", (
            "tras el reinicio el panel sigue diciendo %r" % d["status"]
        )
        assert d["ciudad"] == "Guadalajara"
        assert d["nuevos_en_sheet"] == 10, "se perdio lo que si se habia guardado"

    def test_sin_registro_previo_el_estado_es_idle(self, client, tmp_path, monkeypatch):
        """Comprobacion en la otra direccion: no marcar interrupciones inventadas."""
        monkeypatch.setattr(app, "IMPORT_ESTADO_FILE", str(tmp_path / "no-existe.json"))
        monkeypatch.setattr(app, "_import_job", app._nuevo_import_job())
        assert client.get("/api/importador/estado").get_json()["status"] == "idle"


class TestDockerfileArrancable:
    def test_el_cmd_del_dockerfile_es_json_valido(self):
        r"""Un CMD partido en varias lineas sin `\` rompe `docker build`.

        Los tests de regex leen el texto y no se enteran: el valor declarado es
        correcto, pero la imagen no llega a construirse. Esto lo detecta.
        """
        import json
        cmds = [l for l in _leer("Dockerfile").split("\n") if l.startswith("CMD ")]
        assert len(cmds) == 1, "se esperaba un unico CMD, hay %d" % len(cmds)
        argv = json.loads(cmds[0][len("CMD "):].strip())  # revienta si no es JSON
        assert argv[0] == "gunicorn"
        assert "--worker-class" in argv and argv[argv.index("--worker-class") + 1] == "gthread"


class TestRegistroDuranteLaCorrida:
    """El registro tiene que valer para la interrupcion REAL, no solo al arrancar.

    Si solo se persiste al inicio y al final, una corrida cortada a la mitad deja
    un registro con todos los contadores en cero. El panel diria "se interrumpio,
    0 nuevos" junto a "lo que ya se guardo sigue ahi": dos frases que se
    contradicen, y el operador reimportaria la ciudad entera pagando Places otra
    vez por lo que ya estaba.
    """

    def test_el_registro_se_actualiza_al_cerrar_cada_categoria(
            self, tmp_path, monkeypatch):
        import sys
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from test_importador_conteo import escenario_veinte_contra_diez

        monkeypatch.setattr(app, "IMPORT_ESTADO_FILE", str(tmp_path / "estado.json"))
        monkeypatch.setattr(app, "GMAPS_OK", True)
        monkeypatch.setattr(app, "_enviar_telegram_importador", lambda *a, **k: None)
        monkeypatch.setattr(app.time, "sleep", lambda _s: None)
        monkeypatch.setattr(app, "_import_job",
                            app._nuevo_import_job("CiudadDemo", status="running"))

        gmaps, ws = escenario_veinte_contra_diez()
        monkeypatch.setattr(app.googlemaps, "Client", lambda key=None, **k: gmaps)
        monkeypatch.setattr(app, "get_worksheet", lambda _n: ws)

        vistos = []
        real = app._guardar_estado_importador

        def espia(job, pid=None):
            vistos.append(dict(job))
            return real(job, pid)

        monkeypatch.setattr(app, "_guardar_estado_importador", espia)
        app._worker_importador("CiudadDemo", "clave-falsa")

        intermedios = [v for v in vistos if v["status"] == "running"]
        assert intermedios, (
            "el registro solo se escribe al terminar: una corrida cortada a la "
            "mitad quedaria con todos los contadores en cero"
        )
        assert any(v["nuevos_en_sheet"] > 0 for v in intermedios), (
            "ningun registro intermedio llego a tener filas escritas: %r"
            % [(v["progreso"], v["nuevos_en_sheet"]) for v in intermedios]
        )


class TestErrorSinDatosPersonales:
    def test_un_telefono_en_el_mensaje_de_error_se_enmascara(self):
        """El campo `error` es `str(e)` crudo y acaba en disco, en Telegram y en
        stdout. Basta con que una excepcion futura se formatee con la fila para
        filtrar un telefono por tres sitios a la vez."""
        sucio = "fila invalida: Ferreteria X, tel 3312345678, Calle Falsa 123"
        limpio = app._sanear_error(sucio)
        assert "3312345678" not in limpio, "el telefono sigue entero: %r" % limpio
        assert "5678" in limpio, "deberia dejar los ultimos 4, como enmascarar_telefono"

    def test_el_error_saneado_se_trunca(self):
        assert len(app._sanear_error("x" * 5000)) <= 400

    def test_un_error_normal_no_se_toca(self):
        """La otra direccion: no destrozar mensajes que no llevan datos personales."""
        msg = "Ferreterías: fallo al escribir en Google Sheets — quota exceeded"
        assert app._sanear_error(msg) == msg


class TestClientesPerezososConLock:
    """Con --threads 4, dos peticiones en frio construian dos clientes.

    `if _gs_client: return _gs_client` seguido de la construccion es un
    double-checked init sin proteger. Con --workers 2 cada worker atendia una
    peticion a la vez y era seguro por construccion; con hilos deja de serlo y se
    autentica dos veces contra Google.
    """

    def test_existe_un_lock_para_los_clientes(self):
        assert hasattr(app, "_clientes_lock")

    def test_cuatro_hilos_en_frio_construyen_un_solo_cliente(self, monkeypatch):
        construidos = []

        def construir_lento():
            import time as _t
            _t.sleep(0.02)          # ensancha la ventana de la carrera
            construidos.append(1)
            app._gs_client = object()
            return app._gs_client

        monkeypatch.setattr(app, "_gs_client", None)
        monkeypatch.setattr(app, "_construir_gs_client", construir_lento)

        hilos = [threading.Thread(target=app.get_gs_client) for _ in range(4)]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join()
        assert len(construidos) == 1, (
            "se construyeron %d clientes: cuatro hilos en frio se autenticaron "
            "por separado contra Google" % len(construidos)
        )
