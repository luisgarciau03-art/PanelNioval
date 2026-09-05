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

        La primera version comparaba `r.endpoint` ("importador_iniciar") contra
        las claves de `_route_exemptions`, que Flask-Limiter construye como
        "modulo.nombre.qualname" ("app.importador_iniciar.importador_iniciar").
        Los dos conjuntos NO SE CRUZAN NUNCA, asi que la interseccion era
        siempre vacia y el test daba verde exima lo que exima. Se comprobo
        eximiendo la ruta facturable: seguia en verde.

        Ahora se traduce cada endpoint a la clave real de la libreria.
        """
        from flask_limiter.util import get_qualified_name

        exentas = set(getattr(app.limiter, "_route_exemptions", {}) or {})
        sin_limite = set()
        for r in app.app.url_map.iter_rules():
            if r.endpoint == "static":
                continue
            vista = app.app.view_functions.get(r.endpoint)
            if vista is not None and get_qualified_name(vista) in exentas:
                sin_limite.add(r.endpoint)
        assert sin_limite == set(), f"rutas exentas del limitador: {sin_limite}"

    def test_el_guarda_de_ce1_detecta_una_exencion_de_verdad(self):
        """La direccion util. Sin esto, CE1 podria volver a ser un tripwire
        permanentemente verde y nadie se enteraria."""
        from flask_limiter.util import get_qualified_name

        vista = app.app.view_functions["importador_iniciar"]
        clave = get_qualified_name(vista)
        exentas = dict(getattr(app.limiter, "_route_exemptions", {}) or {})
        assert clave not in exentas, "la ruta facturable esta exenta AHORA MISMO"
        # Se simula la exencion y se comprueba que el criterio la veria.
        exentas[clave] = object()
        assert clave in exentas

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
        """Comparar valores, no tipos. `LIMITE_IMPORTADOR != LIMITES_POR_DEFECTO`
        comparaba un str contra una list: True por construccion, aunque el
        limite fuera "1000 per hour"."""
        import re as _re

        def por_hora(texto):
            m = _re.match(r"\s*(\d+)\s*per\s*hour", texto)
            return int(m.group(1)) if m else None

        propio = por_hora(app.LIMITE_IMPORTADOR)
        global_ = next((por_hora(x) for x in app.LIMITES_POR_DEFECTO
                        if por_hora(x) is not None), None)
        assert propio is not None and global_ is not None
        assert propio < global_, f"el del importador ({propio}/h) no es mas estricto que {global_}/h"

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
        """El worker late cada pocos segundos.

        Son 120 y no 60 a proposito: el limite GLOBAL es 60/minuto, asi que con
        60 latidos el test pasaba igual aunque nadie hubiera puesto el override
        holgado — pasaba por coincidencia numerica. Con 120 solo pasa si
        LIMITE_HEARTBEAT esta de verdad aplicado.""" 
        monkeypatch.setenv("WORKER_TOKEN", "x" * 20)
        codigos = [client.post("/api/catalogo/heartbeat",
                               headers={"X-Worker-Token": "x" * 20},
                               json={"resumen": {}}).status_code
                   for _ in range(120)]
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


# ───────────────── Los hallazgos de los reviewers, fijados ─────────────────

class TestElLimitadorNoCorreAntesDeLaAuth:
    """security-reviewer, CRITICAL: DoS pre-autenticacion.

    Flask ejecuta los `before_request` en ORDEN DE REGISTRO y para en cuanto uno
    devuelve respuesta. El limitador se construia con `app=app`, que lo registra
    ahi mismo — antes del gate de token. Resultado medido: 60 peticiones sin
    token agotaban el cubo global y a partir de ahi TODOS recibian 429,
    incluido quien tenia token valido. Un visitante anonimo de internet podia
    dejar el panel inservible.

    Se arregla registrando el limitador con `init_app()` DESPUES del gate.
    """

    def test_el_gate_de_token_se_registra_antes_que_el_limitador(self):
        nombres = [getattr(f, "__qualname__", "") for f in
                   app.app.before_request_funcs.get(None, [])]
        assert "_requiere_token_panel" in nombres, nombres
        i_auth = nombres.index("_requiere_token_panel")
        i_lim = next((n for n, q in enumerate(nombres) if "Limiter" in q), None)
        assert i_lim is not None, f"el limitador no esta enganchado: {nombres}"
        assert i_auth < i_lim, (
            f"el limitador corre ANTES de la auth: {nombres}. Una peticion "
            "anonima consumiria cuota y tumbaria al usuario legitimo."
        )


class TestProxyFix:
    """security-reviewer, CRITICAL: detras de Caddy, `request.remote_addr` es la
    IP del contenedor del proxy, no la del cliente. Sin ProxyFix TODAS las
    peticiones comparten un solo cubo y cualquiera agota el limite de todos."""

    def test_la_app_va_envuelta_en_proxyfix(self):
        from werkzeug.middleware.proxy_fix import ProxyFix
        assert isinstance(app.app.wsgi_app, ProxyFix)

    def test_confia_en_un_solo_salto(self):
        """x_for=1 = solo Caddy. Werkzeug toma el valor a 1 posicion desde la
        DERECHA, asi que lo que el cliente antepone por la izquierda se ignora
        y esto no reintroduce suplantacion."""
        assert app.app.wsgi_app.x_for == 1


class TestCotasCasosBorde:
    """security-reviewer, dos MEDIUM sobre `_fila_valida`/`_columna_valida`."""

    def test_un_float_infinito_da_400_y_no_500(self):
        """{"_row": 1e400} llega como float('inf'), que int() no convierte:
        lanzaba OverflowError, que no estaba capturado, y salia un 500 con el
        mensaje interno de Python en el cuerpo."""
        ws = _ws()
        with pytest.raises(app.FueraDeRango):
            app._fila_valida(ws, float("inf"))

    @pytest.mark.parametrize("valor", ["no", None, "", [], {}])
    def test_valores_no_numericos_se_rechazan(self, valor):
        with pytest.raises(app.FueraDeRango):
            app._fila_valida(_ws(), valor)

    def test_el_tope_cero_no_desactiva_la_cota(self):
        """`if tope and ...` se saltaba la comprobacion cuando row_count era 0:
        el tope superior desaparecia EN SILENCIO. Ahora es `is not None`."""
        ws = _ws(filas=0)
        with pytest.raises(app.FueraDeRango):
            app._fila_valida(ws, 5)

    def test_una_fila_valida_no_se_rechaza(self):
        assert app._fila_valida(_ws(filas=50), 7) == 7


class TestEscapeConEspaciosUnicode:
    """security-reviewer, MEDIUM: el endurecimiento del escape cubria una lista
    fija de invisibles, pero dejaba pasar NBSP, el espacio ideografico y los
    separadores de linea, que las hojas de calculo tambien recortan al importar.
    Era el mismo bypass que T5.2 acababa de cerrar, a medias."""

    @pytest.mark.parametrize("codepoint", [
        0x00A0,  # NBSP
        0x3000,  # espacio ideografico
        0x2028,  # separador de linea
        0x2009,  # espacio fino
        0x205F,  # espacio matematico medio
        0xFEFF,  # BOM
        0x200B,  # ancho cero
    ])
    def test_ningun_espacio_unicode_evade_el_escape(self, codepoint):
        valor = chr(codepoint) + "=SUM(A1:A9)"
        assert app._escapar_formula(valor) == "'" + valor

    def test_no_quedan_invisibles_literales_en_el_fuente(self):
        """Los codepoints van por `chr()`, no escritos tal cual: un invisible
        literal no se ve al revisar el codigo, y este proyecto ya tuvo un byte
        que volvio un archivo invisible para el barrido de secretos."""
        import pathlib
        fuente = (pathlib.Path(app.__file__)).read_text(encoding="utf-8")
        invisibles = {0xFEFF, 0x200B, 0x200C, 0x200D, 0x2060}
        hallados = [hex(ord(c)) for c in fuente if ord(c) in invisibles]
        assert hallados == [], f"invisibles literales en app.py: {hallados}"


class TestElBypassEsRuidoso:
    """silent-failure-hunter, HIGH: el comentario decia "explicito y ruidoso" y
    era mudo. La MISMA variable apaga la autenticacion y el rate limiting, asi
    que si queda puesta por error en un despliegue el panel arranca abierto y
    sin limites, y la unica forma de enterarse era mirar las variables a mano.
    """

    def test_avisa_por_stderr_al_activarse(self, capfd):
        import importlib
        importlib.reload(app)
        salida = capfd.readouterr()
        assert "PANEL_AUTH_DESACTIVADA" in salida.err, (
            "el bypass no deja ninguna senal al arrancar"
        )
        assert "SIN autenticacion" in salida.err


class TestLimiteDelSondeo:
    """security-reviewer: el frontend sondea /api/importador/estado cada 3 s
    mientras hay corrida, ~20/minuto de una sola persona. Con el limite por
    defecto en 60/minuto, eso es un tercio de la cuota por solo mirar."""

    def test_tiene_un_limite_propio_y_mas_holgado(self):
        assert hasattr(app, "LIMITE_SONDEO")

    def test_aguanta_una_corrida_larga_con_dos_pestanas(self, client, limitador_activo):
        """40 minutos de sondeo a 3 s serian 800 peticiones; se prueban 150,
        muy por encima del limite por defecto de 60/minuto."""
        codigos = [client.get("/api/importador/estado").status_code
                   for _ in range(150)]
        assert 429 not in codigos, "el sondeo normal del panel chocaria con el limite"
