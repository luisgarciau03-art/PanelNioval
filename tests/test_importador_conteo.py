"""Tests del conteo del importador (Plan 3 - T3.2, T3.3, T3.4).

El owner reporto "dice agregados al sheet 20 pero realmente nomas aparecen 10".
La causa esta en que un solo numero, `encontrados`, se presenta como si fuera
"guardados": cuenta los negocios que pasaron los filtros de Places, no las filas
que llegaron a `LISTA DE CONTACTOS`.

Estos tests fijan los CUATRO numeros que el operador necesita distinguir:

    encontrados      negocios que pasaron los filtros de Places
    nuevos_en_sheet  filas REALMENTE escritas en la hoja
    duplicados       ya estaban en LISTA DE CONTACTOS
    descartados      rechazados por resenas, calificacion o falta de telefono
"""
from unittest.mock import MagicMock

import pytest

import app


# ─────────────────────────── dobles de prueba ───────────────────────────

def negocio(nombre, pid, direccion, resenas=120, calificacion=4.5):
    """Un resultado de Places. Por defecto pasa todos los filtros de calidad."""
    return {
        "place_id": pid,
        "name": nombre,
        "formatted_address": direccion,
        "rating": calificacion,
        "user_ratings_total": resenas,
        "geometry": {"location": {"lat": 20.0, "lng": -103.0}},
    }


class GmapsFalso:
    """Cliente de Places falso. `por_categoria` mapea prefijo de query -> negocios."""

    def __init__(self, por_categoria, sin_telefono=()):
        self.por_categoria = por_categoria
        self.sin_telefono = set(sin_telefono)
        self.detalles_pedidos = []

    def places(self, query=None, page_token=None, **kw):
        for categoria, negocios in self.por_categoria.items():
            if query and query.startswith(categoria):
                return {"results": list(negocios)}
        return {"results": []}

    def place(self, pid, **kw):
        self.detalles_pedidos.append(pid)
        tel = "" if pid in self.sin_telefono else "+52 33 1234 5678"
        return {"result": {"formatted_phone_number": tel,
                           "website": "https://ejemplo.mx",
                           "opening_hours": {"weekday_text": ["L-V 9-18"]}}}


class WorksheetFalsa:
    """Worksheet en memoria. Columna 1 = Nombre, columna 7 = Direccion."""

    ENCABEZADO = ["NUM SEMANA", "Nombre", "Ciudad", "Categoria", "Telefono",
                  "", "", "Direccion"] + [""] * 11

    def __init__(self, preexistentes=()):
        self.filas = [list(self.ENCABEZADO)]
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


def catalogo(ferreterias, distribuidoras):
    """Cubre la categoria con y sin acento, tal como la escribe app.py."""
    return {"Ferreterias": ferreterias, "Ferreterías": ferreterias,
            "Distribuidoras Ferreterias": distribuidoras,
            "Distribuidoras Ferreterías": distribuidoras}


@pytest.fixture
def entorno(monkeypatch):
    """Sustituye las fronteras externas y deja `_import_job` limpio."""
    monkeypatch.setattr(app, "GMAPS_OK", True)
    monkeypatch.setattr(app, "_enviar_telegram_importador", lambda *a, **k: None)
    monkeypatch.setattr(app.time, "sleep", lambda _s: None)
    # Se usa la MISMA factory que produccion: si el estado gana un campo, el test
    # lo hereda en vez de quedarse con una copia vieja que ya no representa nada.
    monkeypatch.setattr(app, "_import_job",
                        app._nuevo_import_job("CiudadDemo", status="running"))
    return monkeypatch


def correr(monkeypatch, gmaps, ws, ciudad="CiudadDemo"):
    monkeypatch.setattr(app.googlemaps, "Client", lambda key=None, **k: gmaps)
    monkeypatch.setattr(app, "get_worksheet", lambda _n: ws)
    app._worker_importador(ciudad, "clave-falsa")
    return app._import_job


# ─────────────── escenario del reporte del owner: 20 contra 10 ───────────────

def escenario_veinte_contra_diez():
    """12 ferreterias + 8 distribuidoras (6 repetidas), hoja con 4 ya dentro.

    encontrados = 20, filas escritas = 10. Son los numeros del reporte.
    """
    ferreterias = [negocio("Ferreteria %d" % i, "pid-F%d" % i, "Calle %d" % i)
                   for i in range(1, 13)]
    distribuidoras = (
        [negocio("Ferreteria %d" % i, "pid-F%d" % i, "Calle %d" % i) for i in range(1, 7)]
        + [negocio("Distribuidora %d" % i, "pid-D%d" % i, "Avenida %d" % i)
           for i in range(1, 3)]
    )
    ya_en_hoja = [("Ferreteria %d" % i, "Calle %d" % i) for i in range(1, 5)]
    return GmapsFalso(catalogo(ferreterias, distribuidoras)), WorksheetFalsa(ya_en_hoja)


class TestCuatroContadores:
    def test_nuevos_en_sheet_refleja_filas_escritas(self, entorno):
        gmaps, ws = escenario_veinte_contra_diez()
        est = correr(entorno, gmaps, ws)
        assert ws.escrituras == 10, "el escenario debe escribir 10 filas"
        assert est["nuevos_en_sheet"] == ws.escrituras, (
            "nuevos_en_sheet=%r no coincide con las %d filas escritas"
            % (est.get("nuevos_en_sheet"), ws.escrituras)
        )

    def test_encontrados_no_se_presenta_como_guardados(self, entorno):
        gmaps, ws = escenario_veinte_contra_diez()
        est = correr(entorno, gmaps, ws)
        # Los dos numeros existen y son DISTINTOS: ese es justo el bug del owner.
        assert est["encontrados"] == 20
        assert est["nuevos_en_sheet"] == 10
        assert est["encontrados"] != est["nuevos_en_sheet"]

    def test_duplicados_se_reportan_por_separado_de_descartados(self, entorno):
        # 6 negocios aprobados, 2 de ellos ya en la hoja; y 3 sin telefono
        # (descartados por Places, nunca llegan a la exportacion).
        aprobados = [negocio("Ferreteria %d" % i, "pid-F%d" % i, "Calle %d" % i)
                     for i in range(1, 7)]
        sin_tel = [negocio("SinTel %d" % i, "pid-S%d" % i, "Calle S%d" % i)
                   for i in range(1, 4)]
        gmaps = GmapsFalso(catalogo(aprobados + sin_tel, []),
                           sin_telefono=["pid-S1", "pid-S2", "pid-S3"])
        ws = WorksheetFalsa([("Ferreteria 1", "Calle 1"), ("Ferreteria 2", "Calle 2")])
        est = correr(entorno, gmaps, ws)

        assert est["encontrados"] == 6         # pasaron los filtros
        assert est["nuevos_en_sheet"] == 4     # 6 - 2 que ya estaban
        assert est["duplicados"] == 2          # ya estaban en la hoja
        assert est["descartados"] == 3         # sin telefono
        # Son conceptos distintos y no se pueden confundir entre si.
        assert est["duplicados"] != est["descartados"]

    def test_los_cuatro_numeros_cuadran(self, entorno):
        gmaps, ws = escenario_veinte_contra_diez()
        est = correr(entorno, gmaps, ws)
        assert est["nuevos_en_sheet"] + est["duplicados"] == est["encontrados"], (
            "nuevos + duplicados debe dar encontrados"
        )


class TestEstadoExponeLosContadores:
    @pytest.fixture
    def client(self):
        app.app.config["TESTING"] = True
        return app.app.test_client()

    def test_estado_expone_los_cuatro_contadores(self, client, entorno):
        gmaps, ws = escenario_veinte_contra_diez()
        correr(entorno, gmaps, ws)
        d = client.get("/api/importador/estado").get_json()
        for clave in ("encontrados", "nuevos_en_sheet", "duplicados", "descartados"):
            assert clave in d, "/api/importador/estado no expone %r" % clave
        assert d["nuevos_en_sheet"] == 10
        assert d["encontrados"] == 20

    def test_estado_inicial_trae_los_contadores_en_cero(self, client, monkeypatch):
        monkeypatch.setattr(app, "_import_job", dict(app._import_job, status="idle"))
        d = client.get("/api/importador/estado").get_json()
        assert d["nuevos_en_sheet"] == 0
        assert d["duplicados"] == 0


class TestMensajeFinal:
    def test_la_ui_no_dice_guardados_junto_a_encontrados(self):
        """El mensaje final decia "N encontrados ... Guardados en Google Sheets".

        Esa yuxtaposicion es la que hace leer "N guardados". El numero grande y
        el mensaje tienen que hablar de `nuevos_en_sheet`.
        """
        html = app.IMPORTADOR_HTML
        assert "contactos encontrados" not in html or "nuevos_en_sheet" in html, (
            "el mensaje final sigue presentando `encontrados` como guardados"
        )
        assert "s-nuevos" in html, "falta el recuadro de 'Nuevos en la hoja' en la UI"


# ═══════════════ T3.4 — un fallo de escritura tiene que verse ═══════════════

class WorksheetQueExplota(WorksheetFalsa):
    """Escribe bien hasta `fallar_en_escritura_n`, y a partir de ahi revienta.

    Modela lo que de verdad pasa en produccion: cuota agotada, token vencido o
    un corte de red a media corrida, no un fallo total desde el primer intento.
    """

    def __init__(self, preexistentes=(), fallar_en_escritura_n=1,
                 causa="cuota de Sheets agotada"):
        super().__init__(preexistentes)
        self.intentos = 0
        self.fallar_en = fallar_en_escritura_n
        self.causa = causa

    def append_rows(self, filas, **kw):
        self.intentos += 1
        if self.intentos >= self.fallar_en:
            raise RuntimeError(self.causa)
        super().append_rows(filas, **kw)


class TestFalloDeEscrituraVisible:
    def test_excepcion_de_sheets_pone_el_trabajo_en_error(self, entorno):
        gmaps, _ = escenario_veinte_contra_diez()
        ws = WorksheetQueExplota(fallar_en_escritura_n=1)
        est = correr(entorno, gmaps, ws)
        assert est["status"] == "error", "una escritura que revienta no puede acabar en 'done'"
        assert "cuota de Sheets agotada" in est["error"], (
            "el campo error no lleva la causa real: %r" % est["error"]
        )

    def test_fallo_de_escritura_no_se_cuenta_como_duplicados(self, entorno):
        """El fallo que encontraron las dos reviews de T3.2.

        Si la escritura explota, `nuevos` valia 0 y `duplicados` se llevaba TODAS
        las filas perdidas. La UI afirmaba "ya estaban" sobre negocios que en
        realidad nunca llegaron a la hoja: una razon falsa, peor que un numero
        ambiguo.
        """
        gmaps, _ = escenario_veinte_contra_diez()
        ws = WorksheetQueExplota(fallar_en_escritura_n=1)
        est = correr(entorno, gmaps, ws)
        assert ws.escrituras == 0
        assert est["duplicados"] == 0, (
            "las filas perdidas se contaron como 'ya estaban': %d" % est["duplicados"]
        )
        assert est["nuevos_en_sheet"] == 0

    def test_error_conserva_el_conteo_de_lo_ya_escrito(self, entorno):
        """Primera categoria bien, segunda revienta: lo guardado sigue contando."""
        gmaps, _ = escenario_veinte_contra_diez()
        # Las mismas 4 filas preexistentes del escenario: sin ellas la primera
        # categoria escribe 12 y el numero esperado deja de ser el del reporte.
        ws = WorksheetQueExplota(
            [("Ferreteria %d" % i, "Calle %d" % i) for i in range(1, 5)],
            fallar_en_escritura_n=2)  # falla en la 2a escritura
        est = correr(entorno, gmaps, ws)
        assert est["status"] == "error"
        assert ws.escrituras == 8, "la primera categoria debio escribir 8 filas"
        assert est["nuevos_en_sheet"] == 8, (
            "se perdio la cuenta de lo que SI se guardo: %r" % est["nuevos_en_sheet"]
        )

    def test_cero_filas_por_error_se_distingue_de_cero_filas_por_nada_nuevo(self, entorno):
        # Caso A: no habia nada nuevo (todo ya estaba en la hoja).
        aprobados = [negocio("Ferreteria %d" % i, "pid-F%d" % i, "Calle %d" % i)
                     for i in range(1, 5)]
        ws_ok = WorksheetFalsa([("Ferreteria %d" % i, "Calle %d" % i) for i in range(1, 5)])
        est_ok = correr(entorno, GmapsFalso(catalogo(aprobados, [])), ws_ok)
        assert est_ok["nuevos_en_sheet"] == 0
        assert est_ok["status"] == "done"
        assert est_ok["error"] == ""

        # Caso B: cero filas porque la escritura reventó.
        app._import_job = app._nuevo_import_job("CiudadDemo", status="running")
        ws_mal = WorksheetQueExplota(fallar_en_escritura_n=1)
        est_mal = correr(entorno, GmapsFalso(catalogo(aprobados, [])), ws_mal)
        assert est_mal["nuevos_en_sheet"] == 0

        # Mismo 0, estados distintos: el operador puede diferenciarlos.
        assert est_ok["status"] != est_mal["status"]
        assert est_mal["error"] != ""

    def test_telegram_avisa_tambien_cuando_falla(self, entorno):
        avisos = []
        entorno.setattr(app, "_enviar_telegram_importador",
                        lambda *a, **k: avisos.append((a, k)))
        gmaps, _ = escenario_veinte_contra_diez()
        ws = WorksheetQueExplota(fallar_en_escritura_n=1)
        correr(entorno, gmaps, ws)
        assert avisos, "la corrida fallo y Telegram no aviso de nada"
        _, kwargs = avisos[-1]
        assert kwargs.get("error"), "el aviso de Telegram no lleva la causa del fallo"

    def test_el_log_dice_que_categoria_fallo(self, entorno):
        gmaps, _ = escenario_veinte_contra_diez()
        ws = WorksheetQueExplota(fallar_en_escritura_n=1)
        est = correr(entorno, gmaps, ws)
        texto = " ".join(est["log"])
        assert "Ferreterías" in texto and ("❌" in texto or "falló" in texto.lower()), (
            "el log no dice que categoria fallo: %r" % est["log"]
        )


# ══════ T3.4 bis — los fallos de LECTURA tampoco pueden pasar por exito ══════

class GmapsQueFalla:
    """Places revienta en toda consulta: clave invalida, cuota agotada o sin red."""

    def __init__(self, causa="REQUEST_DENIED: clave invalida"):
        self.causa = causa
        self.intentos = 0

    def places(self, query=None, page_token=None, **kw):
        self.intentos += 1
        raise RuntimeError(self.causa)

    def place(self, pid, **kw):
        raise RuntimeError(self.causa)


class GmapsVacio:
    """Places responde bien, pero esa ciudad no tiene nada. No es un fallo."""

    def places(self, query=None, page_token=None, **kw):
        return {"results": []}

    def place(self, pid, **kw):
        return {"result": {"formatted_phone_number": "+52 33 1234 5678"}}


class TestFalloDeLecturaVisible:
    def test_fallo_total_de_places_no_termina_en_done(self, entorno):
        """El gemelo de B4 del lado de la lectura.

        Con la clave invalida, _buscar_negocios agotaba sus reintentos y devolvia
        lista vacia. El log escribia "0 aprobados, 0 descartados, 0 nuevos" con
        palomita y la corrida terminaba en 'done'. Un fallo de autenticacion
        presentado como "esta ciudad no tiene ferreterias".
        """
        est = correr(entorno, GmapsQueFalla(), WorksheetFalsa())
        assert est["status"] == "error", (
            "Places fallo en todas las consultas y la corrida acabo en %r"
            % est["status"]
        )
        assert "REQUEST_DENIED" in est["error"] or "Places" in est["error"], (
            "el error no dice que fallo la consulta a Places: %r" % est["error"]
        )

    def test_ciudad_legitimamente_vacia_si_termina_en_done(self, entorno):
        """La otra direccion: cero resultados de verdad NO es un error.

        Un barrido que marca como fallo un negativo conocido enganna igual que
        uno que se traga un positivo.
        """
        est = correr(entorno, GmapsVacio(), WorksheetFalsa())
        assert est["status"] == "done", (
            "una ciudad sin resultados no es un fallo: %r" % est["status"]
        )
        assert est["encontrados"] == 0
        assert est["error"] == ""


class TestAvisoYRastro:
    def test_telegram_que_falla_deja_rastro(self, monkeypatch, capsys):
        """El aviso de fallo puede fallar, y entonces el owner no se entera de nada.

        `except Exception: pass` en el notificador significa que un token rotado
        deja al owner exactamente donde estaba: sin enterarse.

        Usa `monkeypatch` pelado a proposito, NO la fixture `entorno`: esa
        sustituye `_enviar_telegram_importador` por un no-op, con lo que el test
        estaria midiendo el doble en vez del codigo.
        """
        monkeypatch.setenv("TELEGRAM_TOKEN", "token-de-prueba")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "123")

        def post_que_falla(*a, **k):
            raise RuntimeError("api.telegram.org inalcanzable")

        monkeypatch.setattr(app.req_lib, "post", post_que_falla)
        app._enviar_telegram_importador("CiudadDemo",
                                        {"nuevos": 0, "encontrados": 0,
                                         "duplicados": 0, "descartados": 0},
                                        {}, 1.0, error="algo se rompio")
        salida = capsys.readouterr()
        assert "telegram" in (salida.out + salida.err).lower(), (
            "el fallo del aviso de Telegram no dejo ningun rastro"
        )

    def test_el_log_dice_que_categorias_no_se_intentaron(self, entorno):
        """Si la corrida aborta, las categorias que quedaron sin tocar se dicen."""
        gmaps, _ = escenario_veinte_contra_diez()
        ws = WorksheetQueExplota(fallar_en_escritura_n=1)
        est = correr(entorno, gmaps, ws)
        texto = " ".join(est["log"])
        assert "Distribuidoras Ferreterías" in texto, (
            "no se dice que la segunda categoria nunca se intento: %r" % est["log"]
        )
