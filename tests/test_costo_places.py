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


# ─────────── T2.4 · no gastar en consultas que no aportan nada ───────────

class GmapsPorVariacion:
    """Devuelve un lote distinto por variacion y por pagina, a eleccion.

    `plan` es {(n_variacion, n_pagina): [place_ids]}. Lo que no este en el plan
    devuelve vacio. Permite montar el caso "la variacion 2 no aporta nada nuevo"
    sin depender de la casualidad.
    """

    def __init__(self, plan):
        self.plan = plan
        self.consultas = []          # [(query, page_token), ...]
        self.llamadas_place = []
        self._tokens = {}

    def _negocios(self, ids):
        return [negocio("Neg %s" % i, "pid-%s" % i, "Calle %s" % i) for i in ids]

    def places(self, query=None, page_token=None, **kw):
        self.consultas.append((query, page_token))
        if page_token is None:
            var = sum(1 for q, t in self.consultas if t is None)
            pag = 1
        else:
            var, pag = self._tokens[page_token]
        ids = self.plan.get((var, pag), [])
        resp = {"results": self._negocios(ids)}
        if (var, pag + 1) in self.plan:
            tok = "t-%d-%d" % (var, pag)
            self._tokens[tok] = (var, pag + 1)
            resp["next_page_token"] = tok
        return resp

    def place(self, pid, **kw):
        self.llamadas_place.append(pid)
        return {"result": {"formatted_phone_number": "+52 33 1234 5678"}}


class TestNoRepetirConsultasVacias:
    def test_una_consulta_vacia_no_se_reintenta(self, entorno):
        """Una consulta que responde BIEN y vacia devolvera lo mismo al repetirla.

        `if lugares: break` solo rompe cuando hubo resultados, asi que una
        variacion legitimamente vacia se lanzaba 3 veces identicas. Es gasto
        puro: mismos parametros, misma respuesta.
        """
        gmaps = GmapsPorVariacion({})       # todo vacio
        correr(entorno, gmaps, WorksheetFalsa())
        # Antes: 3 variaciones x 3 reintentos x 2 categorias = 18 consultas.
        # Ahora 6: no se reintenta una consulta que respondio vacia, pero las
        # tres variaciones SI se lanzan. Vacio no es saturacion: puede ser que
        # esa fraseologia no case y otra si.
        assert len(gmaps.consultas) == 6, (
            "se lanzaron %d consultas; deberian ser 6" % len(gmaps.consultas)
        )

    def test_un_fallo_de_verdad_si_se_reintenta(self, entorno):
        """La otra direccion: un error transitorio merece sus reintentos."""
        class GmapsQueFallaYLuegoVa:
            def __init__(self):
                self.intentos = 0
                self.llamadas_place = []

            def places(self, query=None, page_token=None, **kw):
                self.intentos += 1
                if self.intentos == 1:
                    raise RuntimeError("timeout transitorio")
                return {"results": []}

            def place(self, pid, **kw):
                return {"result": {"formatted_phone_number": "+52 33 1234 5678"}}

        gmaps = GmapsQueFallaYLuegoVa()
        est = correr(entorno, gmaps, WorksheetFalsa())
        assert gmaps.intentos > 1, "no se reintento tras un error transitorio"
        assert est["status"] == "done", (
            "un error transitorio del que se salio no puede tumbar la corrida"
        )


class TestCortarPaginasYVariaciones:
    def test_no_pide_la_siguiente_pagina_si_la_actual_no_aporto_nada(self, entorno):
        # Variacion 1: pagina 1 trae A y B; pagina 2 repite A y B; pagina 3
        # traeria C, pero no se debe llegar a pedirla.
        plan = {(1, 1): ["A", "B"], (1, 2): ["A", "B"], (1, 3): ["C"]}
        gmaps = GmapsPorVariacion(plan)
        correr(entorno, gmaps, WorksheetFalsa())
        paginadas = [t for _, t in gmaps.consultas if t is not None]
        assert len(paginadas) == 1, (
            "se pidieron %d paginas; tras una pagina sin aporte no deberia "
            "pedirse otra" % len(paginadas)
        )

    def test_si_la_pagina_aporta_se_sigue_paginando(self, entorno):
        """Comprobacion en la otra direccion: el corte no puede dispararse solo."""
        plan = {(1, 1): ["A"], (1, 2): ["B"], (1, 3): ["C"]}
        gmaps = GmapsPorVariacion(plan)
        correr(entorno, gmaps, WorksheetFalsa())
        paginadas = [t for _, t in gmaps.consultas if t is not None]
        assert len(paginadas) >= 2, (
            "se cortó la paginación aunque cada página aportaba negocios nuevos"
        )

    def test_el_log_registra_cada_corte(self, entorno):
        """Un tope silencioso se lee como 'cubri todo' cuando no lo hizo."""
        plan = {(1, 1): ["A", "B"], (1, 2): ["A", "B"], (1, 3): ["C"]}
        gmaps = GmapsPorVariacion(plan)
        est = correr(entorno, gmaps, WorksheetFalsa())
        cortes = [l for l in est["log"] if l.startswith("✂")]
        assert cortes, "no se avisa de ningun corte: %r" % est["log"]
        # El aviso tiene que decir QUE se dejo de pedir, no solo que se corto algo.
        assert any("pagina" in c or "página" in c for c in cortes), cortes
        assert any("Ferreterías" in c for c in cortes), cortes

    def test_dos_vacias_no_cancelan_una_tercera_que_si_encuentra(self, entorno):
        """El caso que casi se me cuela.

        Si "Ferreterias en X" y "Ferreterias cerca de X" vuelven vacias pero
        "Ferreterias X" si encuentra, contar los vacios como saturacion habria
        cancelado la unica consulta que funcionaba, y con ella la categoria
        entera. Vacio no es saturado.
        """
        plan = {(3, 1): ["UNICO"]}          # solo la tercera variacion encuentra
        gmaps = GmapsPorVariacion(plan)
        est = correr(entorno, gmaps, WorksheetFalsa())
        assert len(gmaps.consultas) >= 3, (
            "se corto antes de llegar a la tercera variacion: %d consultas"
            % len(gmaps.consultas)
        )
        assert est["nuevos_en_sheet"] == 1, (
            "se perdio el negocio que solo encontraba la tercera variacion"
        )

    def test_el_corte_solo_se_activa_con_saturacion_real(self, entorno):
        """Dos variaciones que TRAEN resultados y ninguno nuevo: eso si es
        saturacion.

        Nota de diseno: dentro de la PRIMERA categoria el corte no puede
        dispararse, porque en la variacion 1 el conjunto de vistos esta vacio y
        todo cuenta como nuevo. El ahorro real es ENTRE categorias, que es
        justamente el caso de este proyecto: 'Distribuidoras Ferreterías' se
        solapa fuerte con 'Ferreterías'.

        En el doble, las variaciones se numeran de corrido: 1-3 son de la primera
        categoria y 4-6 de la segunda.
        """
        plan = {(1, 1): ["A"],                    # categoria 1 encuentra A
                (4, 1): ["A"], (5, 1): ["A"]}     # categoria 2 solo repite A
        gmaps = GmapsPorVariacion(plan)
        est = correr(entorno, gmaps, WorksheetFalsa())
        cortes = [l for l in est["log"] if l.startswith("✂")]
        assert cortes, "no se corto ante saturacion evidente: %r" % est["log"]
        assert any("Distribuidoras" in c for c in cortes), cortes
        assert est["nuevos_en_sheet"] == 1, (
            "el corte se llevo por delante algun negocio: %d" % est["nuevos_en_sheet"]
        )

    def test_un_reintento_no_falsea_la_medicion_de_aporte(self, entorno):
        """El HIGH que encontro la review.

        El conjunto que mide "cuantos son nuevos" se reiniciaba por variacion y
        no por intento. Si un intento leia resultados y luego algo reventaba
        procesandolos, el reintento encontraba ahi sus propios place_id y medía
        0 nuevos sobre datos identicos. Ese cero es falso, y empuja hacia el
        corte que esta funcion existe justamente para no disparar de mas.

        Se fuerza el tropiezo con un resultado malformado: `_buscar_negocios`
        revienta al procesarlo, DESPUES de haber medido el aporte.
        """
        class GmapsQueRevientaAlProcesar:
            def __init__(self):
                self.intentos = 0
                self.llamadas_place = []
                self.consultas = []

            def places(self, query=None, page_token=None, **kw):
                self.consultas.append((query, page_token))
                self.intentos += 1
                bueno = negocio("Bueno", "pid-bueno", "Calle B")
                if self.intentos == 1:
                    # El segundo elemento no es un dict: al procesarlo revienta,
                    # ya con el aporte del primero contabilizado.
                    return {"results": [bueno, "esto-no-es-un-dict"]}
                return {"results": [bueno]}

            def place(self, pid, **kw):
                self.llamadas_place.append(pid)
                return {"result": {"formatted_phone_number": "+52 33 1234 5678"}}

        gmaps = GmapsQueRevientaAlProcesar()
        est = correr(entorno, gmaps, WorksheetFalsa())

        assert gmaps.intentos > 1, "el escenario no llego a provocar un reintento"
        # Con el conjunto contaminado, el reintento habria medido 0 nuevos y el
        # negocio no habria llegado a la hoja.
        assert est["nuevos_en_sheet"] == 1, (
            "se perdio el negocio tras el reintento: %d" % est["nuevos_en_sheet"]
        )
        # El corte se comprueba en la categoria donde ocurrio el reintento. Con
        # el conjunto contaminado, la variacion 1 habria medido 0 nuevos, la 2
        # tambien, y la 3 se habria cortado sin que nadie se lo ganara.
        # (En la segunda categoria SI hay un corte, y es legitimo: el doble
        # devuelve el mismo negocio en todas las consultas, que es saturacion.)
        cortes_cat1 = [l for l in est["log"]
                       if l.startswith("✂ Ferreterías:")]
        assert not cortes_cat1, (
            "un reintento disparo un corte que nadie se gano: %r" % cortes_cat1
        )

    def test_una_sola_variacion_saturada_no_corta(self, entorno):
        """El limite exacto: hace falta llegar al umbral, no acercarse."""
        plan = {(1, 1): ["A"], (4, 1): ["A"], (5, 1): ["B"]}
        gmaps = GmapsPorVariacion(plan)
        est = correr(entorno, gmaps, WorksheetFalsa())
        cortes = [l for l in est["log"] if l.startswith("✂") and "variaciones" in l]
        assert not cortes, (
            "se corto con una sola variacion saturada, antes del umbral: %r" % cortes
        )
