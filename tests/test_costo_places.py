"""Gasto de Google Places por corrida (Plan 2 - T2.2, T2.3, T2.4).

La documentacion de Place Details legacy consultada el 2026-08-28 dice, textual:

    "If you don't specify at least one field with a request, or if you omit the
    `fields` parameter from a request, ALL possible fields will be returned, and
    you will be billed accordingly."

`app.py` llamaba a `place(pid, language='es')` **sin fields**, asi que pagaba los
tres grupos —Basic (26 campos), Contact (6) y Atmosphere (18)— para leer tres.

Razonamiento completo en `docs/adr/2026-08-28-places-legacy-vs-new.md`.
"""
import os
import sys

import pytest

import app

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_importador_conteo import (  # noqa: E402
    WorksheetFalsa, negocio, catalogo,
)

# Lo unico que el codigo lee de la respuesta de Place Details.
CAMPOS_QUE_SE_USAN = {"formatted_phone_number", "website", "opening_hours"}


class GmapsEspia:
    """Registra con que argumentos se llamo a place(), no solo cuantas veces."""

    def __init__(self, por_categoria, paginas=1):
        self.por_categoria = por_categoria
        self.paginas = paginas
        self.llamadas_place = []       # [(pid, kwargs), ...]
        self.llamadas_places = 0

    def places(self, query=None, page_token=None, **kw):
        self.llamadas_places += 1
        for categoria, negocios in self.por_categoria.items():
            if query and query.startswith(categoria):
                return {"results": list(negocios)}
        return {"results": []}

    def place(self, pid, **kw):
        self.llamadas_place.append((pid, kw))
        return {"result": {"formatted_phone_number": "+52 33 1234 5678",
                           "website": "https://ejemplo.mx",
                           "opening_hours": {"weekday_text": ["L-V 9-18"]}}}


@pytest.fixture
def entorno(monkeypatch):
    monkeypatch.setattr(app, "GMAPS_OK", True)
    monkeypatch.setattr(app, "_enviar_telegram_importador", lambda *a, **k: None)
    monkeypatch.setattr(app, "_guardar_estado_importador", lambda *a, **k: None)
    monkeypatch.setattr(app.time, "sleep", lambda _s: None)
    monkeypatch.setattr(app, "_import_job",
                        app._nuevo_import_job("CiudadDemo", status="running"))
    return monkeypatch


def correr(monkeypatch, gmaps, ws):
    monkeypatch.setattr(app.googlemaps, "Client", lambda key=None, **k: gmaps)
    monkeypatch.setattr(app, "get_worksheet", lambda _n: ws)
    app._worker_importador("CiudadDemo", "clave-falsa")
    return app._import_job


def negocios(n, prefijo="Neg"):
    return [negocio("%s %d" % (prefijo, i), "pid-%s%d" % (prefijo, i), "Calle %d" % i)
            for i in range(1, n + 1)]


# ─────────────── T2.2 · pedir solo los campos que se usan ───────────────

class TestFieldsExplicitos:
    def test_place_details_pide_fields_explicitos(self, entorno):
        gmaps = GmapsEspia(catalogo(negocios(3), []))
        correr(entorno, gmaps, WorksheetFalsa())
        assert gmaps.llamadas_place, "no se llamo a place() en absoluto"
        for pid, kw in gmaps.llamadas_place:
            assert "fields" in kw, (
                "place(%r) sin `fields`: se factura Basic + Contact + Atmosphere "
                "para leer tres campos" % pid
            )
            assert kw["fields"], "`fields` va vacio, que equivale a no mandarlo"

    def test_pide_exactamente_los_tres_campos_que_se_leen(self, entorno):
        gmaps = GmapsEspia(catalogo(negocios(2), []))
        correr(entorno, gmaps, WorksheetFalsa())
        pedidos = set(gmaps.llamadas_place[0][1]["fields"])
        assert pedidos == CAMPOS_QUE_SE_USAN, (
            "se piden %r; el codigo solo lee %r" % (sorted(pedidos), sorted(CAMPOS_QUE_SE_USAN))
        )

    def test_no_pide_campos_que_nadie_usa(self, entorno):
        """Atmosphere es el grupo caro y no se lee ni uno de sus 18 campos."""
        from googlemaps import places as gplaces
        gmaps = GmapsEspia(catalogo(negocios(2), []))
        correr(entorno, gmaps, WorksheetFalsa())
        pedidos = set(gmaps.llamadas_place[0][1]["fields"])
        assert not (pedidos & gplaces.PLACES_DETAIL_FIELDS_ATMOSPHERE), (
            "se sigue pagando Atmosphere: %r"
            % sorted(pedidos & gplaces.PLACES_DETAIL_FIELDS_ATMOSPHERE)
        )
        assert not (pedidos & gplaces.PLACES_DETAIL_FIELDS_BASIC), (
            "se sigue pagando Basic, que ya viene del Text Search: %r"
            % sorted(pedidos & gplaces.PLACES_DETAIL_FIELDS_BASIC)
        )

    def test_los_campos_son_validos_para_el_cliente_instalado(self):
        """El cliente valida los nombres; uno mal escrito revienta en produccion."""
        from googlemaps import places as gplaces
        assert CAMPOS_QUE_SE_USAN <= gplaces.PLACES_DETAIL_FIELDS, (
            "campos que el cliente no reconoce: %r"
            % sorted(CAMPOS_QUE_SE_USAN - gplaces.PLACES_DETAIL_FIELDS)
        )
        assert not (CAMPOS_QUE_SE_USAN & gplaces.DEPRECATED_FIELDS), (
            "se pide un campo deprecado: %r"
            % sorted(CAMPOS_QUE_SE_USAN & gplaces.DEPRECATED_FIELDS)
        )

    def test_las_columnas_exportadas_no_cambian(self, entorno):
        """CE7: pedir menos campos no puede cambiar lo que llega a la hoja.

        Todo lo que no es telefono, sitio web u horario sale del Text Search, que
        ya esta pagado. Si alguna columna se vacia, el ahorro salio caro.
        """
        gmaps = GmapsEspia(catalogo(negocios(2), []))
        ws = WorksheetFalsa()
        correr(entorno, gmaps, ws)
        assert ws.escrituras == 2
        fila = ws.filas[-1]
        assert len(fila) == 19, "la fila cambio de ancho: %d columnas" % len(fila)
        assert fila[1] == "Neg 2", "se perdio el Nombre (viene del Text Search)"
        assert fila[7] == "Calle 2", "se perdio la Direccion (viene del Text Search)"
        # `_escapar_formula` antepone un apostrofo para que Sheets no lo tome por
        # formula, pero ese apostrofo no forma parte del valor guardado: al releer
        # la hoja vuelve el telefono limpio.
        assert fila[4] == "+52 33 1234 5678", "se perdio el Telefono (viene de Details)"
        assert fila[8] == 4.5, "se perdio la Calificacion (viene del Text Search)"
        assert fila[9] == 120, "se perdieron las Resenas (vienen del Text Search)"
        assert fila[11] == "https://ejemplo.mx", "se perdio el Sitio Web"


# ─────────── T2.3 · no pagar el detalle de lo que ya esta en la hoja ───────────

class TestNoPagarDuplicados:
    def test_no_llama_place_si_el_negocio_ya_esta_en_la_hoja(self, entorno):
        """La clave de dedup es Nombre|Direccion y los DOS vienen del Text Search.

        Se pueden comparar sin pagar nada. Hoy se paga el detalle, se filtra por
        telefono, se exporta, y solo ahi se descubre que ya estaba.
        """
        gmaps = GmapsEspia(catalogo(negocios(5), []))
        # Tres de los cinco ya estan en la hoja.
        ws = WorksheetFalsa([("Neg %d" % i, "Calle %d" % i) for i in (1, 2, 3)])
        correr(entorno, gmaps, ws)
        pedidos = {pid for pid, _ in gmaps.llamadas_place}
        for i in (1, 2, 3):
            assert "pid-Neg%d" % i not in pedidos, (
                "se pago el detalle de 'Neg %d', que ya estaba en la hoja" % i
            )
        assert len(gmaps.llamadas_place) == 2, (
            "se pagaron %d detalles para 2 negocios nuevos" % len(gmaps.llamadas_place)
        )

    def test_negocio_nuevo_si_llama_a_place(self, entorno):
        """La otra direccion: no saltarse negocios buenos.

        Un salto de deduplicacion mal puesto descarta prospectos sin avisar.
        """
        gmaps = GmapsEspia(catalogo(negocios(3), []))
        ws = WorksheetFalsa()          # hoja vacia: los tres son nuevos
        correr(entorno, gmaps, ws)
        assert len(gmaps.llamadas_place) == 3
        assert ws.escrituras == 3, "se perdio algun negocio nuevo"

    def test_un_duplicado_evitado_se_cuenta_como_duplicado(self, entorno):
        """Saltarlo antes de pagar no puede cambiar los numeros del operador."""
        gmaps = GmapsEspia(catalogo(negocios(5), []))
        ws = WorksheetFalsa([("Neg %d" % i, "Calle %d" % i) for i in (1, 2, 3)])
        est = correr(entorno, gmaps, ws)
        assert est["nuevos_en_sheet"] == 2
        assert est["duplicados"] == 3, (
            "los 3 que ya estaban se reportan como %d duplicados" % est["duplicados"]
        )
        assert est["descartados"] == 0, (
            "un duplicado no es un descartado por filtros de calidad"
        )
        assert est["nuevos_en_sheet"] + est["duplicados"] == est["encontrados"]

    def test_la_escritura_relee_la_hoja_aunque_el_prefiltro_no(self, entorno):
        """Correccion tras la review: el prefiltro puede ir con datos de hace un
        minuto, porque un duplicado no detectado ahi solo cuesta una llamada de
        mas. La ESCRITURA no puede: si alguien edito la hoja a mano a media
        corrida, escribir una fila repetida es un dato malo y en silencio.

        Por eso la exportacion relee (1 por categoria) y el prefiltro reutiliza
        (1 por corrida). Se cambia una lectura por correccion, a proposito.
        """
        gmaps = GmapsEspia(catalogo(negocios(2), negocios(2, "Dist")))
        ws = WorksheetFalsa()
        correr(entorno, gmaps, ws)
        assert ws.lecturas == 3, (
            "se esperaban 3 lecturas (1 prefiltro + 1 por categoria), hubo %d"
            % ws.lecturas
        )

    def test_una_fila_escrita_a_mano_a_media_corrida_no_se_duplica(self, entorno):
        """El MEDIO que encontro silent-failure-hunter.

        El conjunto del prefiltro se lee una vez. Si entre categoria y categoria
        alguien agrega el contacto a mano, la escritura tiene que verlo.
        """
        gmaps = GmapsEspia(catalogo(negocios(2), negocios(2, "Dist")))
        ws = WorksheetFalsa()
        real = app._exportar_a_sheets
        estado = {"n": 0}

        def exportar_y_meter_mano(*a, **k):
            estado["n"] += 1
            if estado["n"] == 1:
                # Un humano agrega "Dist 1" a la hoja mientras corre la primera
                # categoria; la segunda no debe volver a escribirlo.
                fila = [""] * 19
                fila[1], fila[7] = "Dist 1", "Calle 1"
                ws.filas.append(fila)
            return real(*a, **k)

        entorno.setattr(app, "_exportar_a_sheets", exportar_y_meter_mano)
        correr(entorno, gmaps, ws)

        nombres = [f[1] for f in ws.filas[1:]]
        assert nombres.count("Dist 1") == 1, (
            "se escribio una fila duplicada de un contacto agregado a mano: %r"
            % nombres
        )


class TestClaveConNombresQueSheetsEscapa:
    """El caso real que ya vivio este proyecto.

    `_escapar_formula` existe porque la ferreteria "+ Mas Seguro Distribuidora
    Ferretera" se guardo sin escapar y la celda mostraba #ERROR!. Ese nombre
    empieza por '+', asi que se escribe con apostrofo... pero Sheets NO lo guarda.

    Si el prefiltro calculara la clave desde el valor escapado y la hoja
    devolviera el limpio (o al reves), ese negocio se reimportaria en CADA
    corrida: pagando su detalle y escribiendo una fila duplicada, para siempre.
    """

    def test_un_negocio_que_empieza_por_signo_no_se_reimporta(self, entorno):
        raro = [negocio("+ Mas Seguro Distribuidora Ferretera", "pid-raro", "Av. Uno")]
        gmaps = GmapsEspia(catalogo(raro, []))
        ws = WorksheetFalsa()

        # Primera corrida: es nuevo, se paga y se escribe.
        correr(entorno, gmaps, ws)
        assert ws.escrituras == 1
        assert len(gmaps.llamadas_place) == 1

        # Segunda corrida sobre la MISMA hoja: ya esta, no debe pagarse ni escribirse.
        gmaps2 = GmapsEspia(catalogo(raro, []))
        app._import_job = app._nuevo_import_job("CiudadDemo", status="running")
        correr(entorno, gmaps2, ws)
        assert len(gmaps2.llamadas_place) == 0, (
            "se volvio a pagar el detalle de un negocio que ya estaba en la hoja"
        )
        assert ws.escrituras == 1, "se escribio una fila duplicada"


class TestFalloDeEscrituraConSaltados:
    """El hueco que las dos reviews marcaron por separado.

    La rama de error suma `saltados` a `encontrados` y a `duplicados`, pero
    ningun test la ejercitaba con `saltados > 0`: si ese termino se omitiera o se
    contara dos veces, nadie se enteraria.
    """

    def test_los_saltados_cuentan_aunque_la_escritura_reviente(self, entorno):
        import sys as _s, os as _o
        _s.path.insert(0, _o.path.dirname(_o.path.abspath(__file__)))
        from test_importador_conteo import WorksheetQueExplota

        # 5 negocios en la PRIMERA categoria, 3 de ellos ya en la hoja.
        gmaps = GmapsEspia(catalogo(negocios(5), []))
        ws = WorksheetQueExplota(
            [("Neg %d" % i, "Calle %d" % i) for i in (1, 2, 3)],
            fallar_en_escritura_n=1)
        est = correr(entorno, gmaps, ws)

        assert est["status"] == "error"
        assert len(gmaps.llamadas_place) == 2, (
            "se pago el detalle de negocios que ya estaban en la hoja"
        )
        assert est["duplicados"] == 3, (
            "los 3 saltados por estar ya en la hoja se perdieron del conteo: %d"
            % est["duplicados"]
        )
        assert est["encontrados"] == 5, (
            "encontrados deberia incluir los saltados: %d" % est["encontrados"]
        )
        assert est["nuevos_en_sheet"] == 0, (
            "la escritura reventó; no puede haber filas nuevas contadas"
        )
