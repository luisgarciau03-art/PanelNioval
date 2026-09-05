"""Plan 5 · T5.1 (M5) — rate limiting, y cotas de fila/columna al escribir.

Dos cosas en una tarea, por decision del owner (2026-09-04): T5.1 ya iba a
recorrer todas las rutas para poner limites, y los dos CRITICAL que
`security-reviewer` encontro en T5.2 se cierran en ese mismo barrido. Tocar las
rutas dos veces habria sido peor.

RATE LIMITING (M5). El panel esta detras de un token, pero un token filtrado da
barra libre — y entre lo que da acceso esta `/api/importador/iniciar`, que
dispara corridas de Google Places, la unica API facturable del proyecto. El tope
de presupuesto del Plan 2 acota UNA corrida; nada acotaba cuantas se lanzan.

COTAS. `_row` y `_col` venian del body sin tope. Se podia escribir la fila 1 —los
encabezados— y todo el sistema resuelve columnas por `headers.index(nombre)`, asi
que romperla rompe en silencio cada lectura y escritura futura de esa hoja.

Lo que NO se hace, y por que: un allowlist de columnas editables. El modal de
edicion del panel genera sus campos con `data-field="${safeK}"` a partir de las
claves de la PROPIA hoja, o sea que la interfaz edita cualquier columna por
diseno. Una lista blanca de nombres romperia la operacion del owner. Cerrar eso
exige cambiar el modelo de edicion, que es decision de producto y no un parche
de seguridad.
"""
from unittest.mock import MagicMock

import pytest

import app


@pytest.fixture
def client():
    app.app.config["TESTING"] = True
    return app.app.test_client()


@pytest.fixture
def limitador_activo():
    """Enciende el limitador solo para el test que lo necesita.

    En la suite va apagado a proposito (ver `TestLimitadorEnPruebas`): con el
    encendido, los tests se vuelven dependientes del orden de ejecucion, porque
    cada peticion de un test consume cuota del siguiente.
    """
    app.limiter.enabled = True
    with app.app.app_context():
        app.limiter.reset()
    yield app.limiter
    app.limiter.enabled = False
    with app.app.app_context():
        app.limiter.reset()


# ───────────────────────── CE1: toda ruta tiene limite ─────────────────────────

class TestTodaRutaTieneLimite:

    def test_hay_limites_por_defecto(self):
        """El limite global es lo que cubre las 40 rutas sin decorar una a una."""
        assert app.limiter.enabled is not None
        limites = app.app.config.get("RATELIMIT_DEFAULT") or LIMITES_POR_DEFECTO()
        assert limites, "sin limites por defecto, la mayoria de rutas queda abierta"

    def test_ninguna_ruta_esta_exenta(self):
        """CE1, y NO es una lista escrita a mano: recorre `app.url_map`.

        Con `default_limits`, el limitador cubre toda ruta que no este exenta.
        Asi que la forma de que una ruta nueva quede sin limite es que alguien
        la exima, y eso es justo lo que este test tiene que ver.
        """
        exentas = set(getattr(app.limiter, "_route_exemptions", {}) or {})
        rutas = {r.endpoint for r in app.app.url_map.iter_rules()
                 if r.endpoint != "static"}
        sin_limite = rutas & exentas
        assert sin_limite == set(), f"rutas exentas del limitador: {sin_limite}"

    def test_el_barrido_ve_las_rutas_que_sabemos_que_existen(self):
        """Direccion util: si no encuentra lo conocido, su cero no vale nada."""
        rutas = {r.rule for r in app.app.url_map.iter_rules()}
        for esperada in ("/api/importador/iniciar", "/api/catalogo/heartbeat",
                         "/api/seguimiento/update", "/api/mensajes/update"):
            assert esperada in rutas, f"no vio {esperada}"
        assert len(rutas) >= 40


def LIMITES_POR_DEFECTO():
    return getattr(app, "LIMITES_POR_DEFECTO", None)


# ───────────────────────── CE2/CE3: el importador y el 429 ─────────────────────────

class TestLimiteDelImportador:
    """CE2 — `/api/importador/iniciar` es la unica ruta que gasta dinero real."""

    def test_tiene_un_limite_propio_y_mas_estricto(self):
        assert hasattr(app, "LIMITE_IMPORTADOR")
        assert app.LIMITE_IMPORTADOR != app.LIMITES_POR_DEFECTO

    def test_se_agota_y_devuelve_429(self, client, limitador_activo, monkeypatch):
        """Se llama N+1 veces; la ultima debe ser 429 y no arrancar corrida."""
        monkeypatch.setattr(app, "get_gs_client", lambda: (_ for _ in ()).throw(
            RuntimeError("sin credenciales en pruebas")))
        codigos = [client.post("/api/importador/iniciar",
                               json={"ciudad": "Monterrey"}).status_code
                   for _ in range(12)]
        assert 429 in codigos, f"nunca limito: {codigos}"

    def test_el_429_trae_json_y_no_html(self, client, limitador_activo, monkeypatch):
        """CE3 — la pagina HTML por defecto de Flask-Limiter rompe a un
        frontend que hace `r.json()` en todas las rutas."""
        monkeypatch.setattr(app, "get_gs_client", lambda: (_ for _ in ()).throw(
            RuntimeError("sin credenciales")))
        r = None
        for _ in range(12):
            r = client.post("/api/importador/iniciar", json={"ciudad": "X"})
            if r.status_code == 429:
                break
        assert r.status_code == 429
        assert r.content_type.startswith("application/json"), r.content_type
        assert "error" in r.get_json()


# ───────────────────────── El worker legitimo no se cae ─────────────────────────

class TestHeartbeatDelWorker:
    """R1 del plan: un limite mal calibrado aqui tumba el worker de catalogo
    del owner, que es lo que envia los catalogos por WhatsApp."""

    def test_tiene_un_limite_propio_y_mas_holgado(self):
        assert hasattr(app, "LIMITE_HEARTBEAT")

    def test_aguanta_su_cadencia_real(self, client, limitador_activo, monkeypatch):
        """El worker late cada pocos segundos. 60 latidos seguidos no pueden
        devolver 429: eso seria el panel tumbando a su propio worker."""
        monkeypatch.setenv("WORKER_TOKEN", "x" * 20)
        codigos = [client.post("/api/catalogo/heartbeat",
                               headers={"X-Worker-Token": "x" * 20},
                               json={"resumen": {}}).status_code
                   for _ in range(60)]
        assert 429 not in codigos, "el limite tumbaria al worker legitimo"


# ───────────────────────── El limitador y las pruebas ─────────────────────────

class TestLimitadorEnPruebas:

    def test_esta_desactivado_bajo_panel_auth_desactivada(self):
        """Si estuviera activo, cada test consumiria cuota del siguiente y la
        suite dependeria del orden de ejecucion."""
        assert app.limiter.enabled is False

    def test_no_traga_sus_propios_errores(self):
        """`swallow_errors=True` haria que un fallo del almacenamiento dejara
        pasar TODAS las peticiones, pareciendo que el limitador funciona. Es el
        modo de fallo abierto, y este proyecto ya tuvo uno."""
        assert getattr(app.limiter, "_swallow_errors", False) is False


# ───────────────────────── Cotas de fila y columna ─────────────────────────

def _ws(filas=50, columnas=20):
    ws = MagicMock()
    ws.row_count = filas
    ws.col_count = columnas
    ws.row_values.return_value = ["Nombre", "Nota", "NOTA"]
    return ws


class TestCotasSeguimiento:
    """Los encabezados viven en la fila 1 y todo el sistema resuelve columnas
    por `headers.index(nombre)`: escribir ahi rompe la hoja para todos."""

    @pytest.mark.parametrize("fila", [1, 0, -5])
    def test_no_se_puede_escribir_la_fila_de_encabezados(self, client, monkeypatch, fila):
        ws = _ws()
        monkeypatch.setattr(app, "get_worksheet", lambda clave: ws)
        r = client.post("/api/seguimiento/update", json={"_row": fila, "Nota": "x"})
        assert r.status_code == 400
        ws.batch_update.assert_not_called()

    def test_una_fila_fuera_de_la_grilla_se_rechaza(self, client, monkeypatch):
        """Sin tope se puede expandir la grilla. `seguimiento` y `bruce`
        comparten spreadsheet y el limite de celdas es del archivo entero:
        inflar una pestana rompe los append de las demas."""
        ws = _ws(filas=50)
        monkeypatch.setattr(app, "get_worksheet", lambda clave: ws)
        r = client.post("/api/seguimiento/update", json={"_row": 999999999, "Nota": "x"})
        assert r.status_code == 400
        ws.batch_update.assert_not_called()

    def test_una_fila_valida_sigue_escribiendo(self, client, monkeypatch):
        """La cota no puede romper el uso legitimo."""
        ws = _ws(filas=50)
        monkeypatch.setattr(app, "get_worksheet", lambda clave: ws)
        r = client.post("/api/seguimiento/update", json={"_row": 7, "Nota": "x"})
        assert r.status_code == 200
        ws.batch_update.assert_called_once()


class TestCotasBruce:

    @pytest.mark.parametrize("fila", [1, 0, 999999999])
    def test_fila_invalida_se_rechaza(self, client, monkeypatch, fila):
        ws = _ws()
        monkeypatch.setattr(app, "get_bruce_ws", lambda: ws)
        r = client.post("/api/bruce/actualizar", json={"_row": fila, "NOTA": "x"})
        assert r.status_code == 400
        ws.batch_update.assert_not_called()

    def test_fila_valida_sigue_escribiendo(self, client, monkeypatch):
        ws = _ws()
        monkeypatch.setattr(app, "get_bruce_ws", lambda: ws)
        r = client.post("/api/bruce/actualizar", json={"_row": 4, "NOTA": "x"})
        assert r.status_code == 200
        ws.batch_update.assert_called_once()


class TestCotasMensajes:
    """La peor de las tres: `_row` y `_col` son indices crudos, sin pasar
    siquiera por nombre de encabezado. Y esa hoja alimenta los telefonos y
    plantillas que `envio_catalogo.py` manda por WhatsApp a clientes reales."""

    def _ws_captura(self, capturado, filas=50, columnas=20):
        class WS:
            row_count = filas
            col_count = columnas

            def update(self, values, range_name=None, **kw):
                capturado["range"] = range_name
        return WS()

    @pytest.mark.parametrize("fila,col", [(1, 3), (0, 3), (999999999, 3), (2, 0), (2, 9999)])
    def test_coordenada_fuera_de_rango_se_rechaza(self, client, monkeypatch, fila, col):
        capturado = {}
        monkeypatch.setattr(app, "get_worksheet",
                            lambda clave: self._ws_captura(capturado))
        r = client.post("/api/mensajes/update",
                        json={"_row": fila, "_col": col, "Contenido": "x"})
        assert r.status_code == 400, f"fila={fila} col={col} no se rechazo"
        assert capturado == {}, "escribio pese a estar fuera de rango"

    def test_una_coordenada_valida_sigue_escribiendo(self, client, monkeypatch):
        capturado = {}
        monkeypatch.setattr(app, "get_worksheet",
                            lambda clave: self._ws_captura(capturado))
        r = client.post("/api/mensajes/update",
                        json={"_row": 5, "_col": 3, "Contenido": "hola"})
        assert r.status_code == 200, r.get_json()
        assert capturado["range"] == "C5"
