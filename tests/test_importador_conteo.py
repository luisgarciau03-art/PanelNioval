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
