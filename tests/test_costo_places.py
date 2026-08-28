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


# ─────────── T2.5 · cache persistente place_id -> detalle ───────────

class TestCachePersistente:
    """Quien mas se beneficia no es el negocio repetido: es el RECHAZADO.

    Un negocio que pasa resenas y calificacion pero no tiene telefono paga su
    Place Details, se descarta por `sin_telefono` y NUNCA llega a la hoja. Como
    el prefiltro de T2.3 solo salta lo que esta en la hoja, ese negocio vuelve a
    pagarse en cada corrida de esa ciudad, indefinidamente.
    """

    @pytest.fixture
    def cache_temporal(self, entorno, tmp_path):
        entorno.setattr(app, "PLACES_CACHE_FILE", str(tmp_path / "places.json"))
        return tmp_path / "places.json"

    def test_segunda_corrida_no_vuelve_a_pedir_el_mismo_detalle(
            self, entorno, cache_temporal):
        gmaps = GmapsEspia(catalogo(negocios(3), []))
        correr(entorno, gmaps, WorksheetFalsa())
        assert len(gmaps.llamadas_place) == 3

        # Segunda corrida, hoja vacia otra vez (como si los hubieran borrado):
        # el prefiltro no ayuda, pero la cache si.
        gmaps2 = GmapsEspia(catalogo(negocios(3), []))
        app._import_job = app._nuevo_import_job("CiudadDemo", status="running")
        correr(entorno, gmaps2, WorksheetFalsa())
        assert len(gmaps2.llamadas_place) == 0, (
            "se volvieron a pagar %d detalles ya cacheados"
            % len(gmaps2.llamadas_place)
        )

    def test_el_rechazado_sin_telefono_tampoco_se_repaga(self, entorno, cache_temporal):
        """El caso que mas veces se repite en la vida real."""
        class GmapsSinTelefono(GmapsEspia):
            def place(self, pid, **kw):
                self.llamadas_place.append((pid, kw))
                return {"result": {}}          # sin telefono: se descarta

        g1 = GmapsSinTelefono(catalogo(negocios(4), []))
        est = correr(entorno, g1, WorksheetFalsa())
        assert est["descartados"] == 4 and est["nuevos_en_sheet"] == 0
        assert len(g1.llamadas_place) == 4

        g2 = GmapsSinTelefono(catalogo(negocios(4), []))
        app._import_job = app._nuevo_import_job("CiudadDemo", status="running")
        est2 = correr(entorno, g2, WorksheetFalsa())
        assert len(g2.llamadas_place) == 0, (
            "se repagaron los detalles de negocios que ya sabiamos que no tienen "
            "telefono: %d" % len(g2.llamadas_place)
        )
        assert est2["descartados"] == 4, "el descarte tiene que seguir contandose"

    def test_una_entrada_vencida_se_vuelve_a_pedir(self, entorno, cache_temporal):
        import json
        import time as _t
        gmaps = GmapsEspia(catalogo(negocios(1), []))
        correr(entorno, gmaps, WorksheetFalsa())
        assert len(gmaps.llamadas_place) == 1

        # Se envejece la entrada mas alla del TTL.
        datos = json.loads(cache_temporal.read_text(encoding="utf-8"))
        for pid in datos:
            datos[pid]["ts"] = _t.time() - (app.PLACES_CACHE_TTL + 60)
        cache_temporal.write_text(json.dumps(datos), encoding="utf-8")

        gmaps2 = GmapsEspia(catalogo(negocios(1), []))
        app._import_job = app._nuevo_import_job("CiudadDemo", status="running")
        correr(entorno, gmaps2, WorksheetFalsa())
        assert len(gmaps2.llamadas_place) == 1, (
            "una entrada vencida deberia volver a pedirse a la API"
        )

    def test_una_cache_ilegible_no_rompe_la_corrida(self, entorno, cache_temporal):
        """Una cache rota degrada el COSTO, nunca el servicio."""
        cache_temporal.write_text("{esto no es json", encoding="utf-8")
        gmaps = GmapsEspia(catalogo(negocios(2), []))
        est = correr(entorno, gmaps, WorksheetFalsa())
        assert est["status"] == "done", "una cache corrupta tumbo la corrida"
        assert est["nuevos_en_sheet"] == 2
        assert len(gmaps.llamadas_place) == 2, "deberia haber pegado a la API"

    def test_no_poder_escribir_la_cache_no_rompe_la_corrida(self, entorno, tmp_path):
        # Un directorio donde el archivo no se puede crear.
        entorno.setattr(app, "PLACES_CACHE_FILE",
                        str(tmp_path / "no-existe" / "sub" / "places.json"))
        gmaps = GmapsEspia(catalogo(negocios(2), []))
        est = correr(entorno, gmaps, WorksheetFalsa())
        assert est["status"] == "done"
        assert est["nuevos_en_sheet"] == 2

    def test_el_archivo_de_cache_esta_ignorado(self):
        """Lleva telefonos de negocios, que son datos personales."""
        import os as _o
        import subprocess as _sp
        raiz = _o.path.dirname(_o.path.dirname(_o.path.abspath(__file__)))
        nombre = _o.path.basename(app.PLACES_CACHE_FILE)
        for archivo in (".gitignore", ".dockerignore"):
            with open(_o.path.join(raiz, archivo), encoding="utf-8") as fh:
                assert nombre in fh.read(), "%s no ignora %s" % (archivo, nombre)
        r = _sp.run(["git", "check-ignore", nombre], cwd=raiz,
                    capture_output=True, text=True)
        assert r.returncode == 0, "git no ignoraria %s" % nombre

    def test_la_cache_no_guarda_nombres_ni_direcciones(self, entorno, cache_temporal):
        """Solo los tres campos de Place Details, indexados por place_id.

        Nombre y direccion vienen del Text Search y no hacen falta aqui: cuanto
        menos dato personal en disco, mejor.
        """
        gmaps = GmapsEspia(catalogo(negocios(2), []))
        correr(entorno, gmaps, WorksheetFalsa())
        crudo = cache_temporal.read_text(encoding="utf-8")
        assert "Neg 1" not in crudo, "la cache guardo el nombre del negocio"
        assert "Calle 1" not in crudo, "la cache guardo la direccion"

    def test_la_cache_sobrevive_a_una_corrida_que_revienta(self, entorno, cache_temporal):
        """Si la corrida falla tras pagar 200 detalles, tirarlos seria pagarlos
        otra vez en el reintento. Se guarda en el `finally`."""
        import sys as _s, os as _o
        _s.path.insert(0, _o.path.dirname(_o.path.abspath(__file__)))
        from test_importador_conteo import WorksheetQueExplota

        gmaps = GmapsEspia(catalogo(negocios(3), []))
        est = correr(entorno, gmaps, WorksheetQueExplota(fallar_en_escritura_n=1))
        assert est["status"] == "error"
        assert len(gmaps.llamadas_place) == 3, "el escenario debia pagar 3 detalles"
        assert cache_temporal.exists(), (
            "la corrida fallo y se tiraron los 3 detalles ya pagados"
        )

        # El reintento no vuelve a pagarlos.
        gmaps2 = GmapsEspia(catalogo(negocios(3), []))
        app._import_job = app._nuevo_import_job("CiudadDemo", status="running")
        correr(entorno, gmaps2, WorksheetFalsa())
        assert len(gmaps2.llamadas_place) == 0, (
            "el reintento repago %d detalles" % len(gmaps2.llamadas_place)
        )

    def test_las_entradas_vencidas_se_podan_del_disco(self, entorno, cache_temporal):
        """El MEDIO de la review de seguridad.

        El filtro por TTL ocurre al LEER. Si el archivo nunca se reescribiera,
        los telefonos seguirian en disco pasada su vigencia. Se reescribe en cada
        corrida, asi que la poda es real y no solo en memoria.
        """
        import json
        import time as _t
        gmaps = GmapsEspia(catalogo(negocios(1), []))
        correr(entorno, gmaps, WorksheetFalsa())

        datos = json.loads(cache_temporal.read_text(encoding="utf-8"))
        datos["pid-viejo"] = {"det": {"formatted_phone_number": "+52 33 9999 0000"},
                              "ts": _t.time() - (app.PLACES_CACHE_TTL + 60)}
        cache_temporal.write_text(json.dumps(datos), encoding="utf-8")

        app._import_job = app._nuevo_import_job("CiudadDemo", status="running")
        correr(entorno, GmapsEspia(catalogo(negocios(1), [])), WorksheetFalsa())

        crudo = cache_temporal.read_text(encoding="utf-8")
        assert "9999 0000" not in crudo, (
            "un telefono vencido sigue en disco tras una corrida nueva"
        )

    def test_el_archivo_de_cache_no_es_legible_por_todos(self, entorno, cache_temporal):
        """Es el unico archivo del despliegue con telefonos de clientes en reposo."""
        import os as _o
        import stat as _st
        correr(entorno, GmapsEspia(catalogo(negocios(1), [])), WorksheetFalsa())
        if _o.name == "nt":
            pytest.skip("los permisos POSIX no aplican en Windows")
        modo = _st.S_IMODE(_o.stat(cache_temporal).st_mode)
        assert not modo & 0o077, "la cache es legible por otros: %o" % modo

    def test_una_marca_de_tiempo_corrupta_no_tumba_la_corrida(self, entorno, cache_temporal):
        """El MEDIO-ALTO de la review.

        El filtro por vigencia corria FUERA del try, asi que un `ts` no numerico
        —de una edicion a mano o de un cambio de formato futuro— lanzaba
        TypeError, escapaba y tumbaba la corrida antes de la primera llamada a
        Places. Peor que quedarse sin cache: quedarse sin importar.
        """
        import json
        cache_temporal.write_text(json.dumps({
            "pid-malo":  {"det": {"formatted_phone_number": "x"}, "ts": "ayer"},
            "pid-peor":  {"det": {"formatted_phone_number": "x"}, "ts": {"raro": 1}},
            "pid-sin":   {"det": {"formatted_phone_number": "x"}},
            "pid-nodict": "esto tampoco es un dict",
        }), encoding="utf-8")

        gmaps = GmapsEspia(catalogo(negocios(2), []))
        est = correr(entorno, gmaps, WorksheetFalsa())
        assert est["status"] == "done", (
            "una entrada de cache mal formada tumbo la corrida: %r" % est["error"]
        )
        assert est["nuevos_en_sheet"] == 2
        assert len(gmaps.llamadas_place) == 2, "deberia haber pegado a la API"

    def test_un_fallo_al_guardar_la_cache_no_marca_la_corrida_como_fallida(
            self, entorno, cache_temporal):
        """Solo se capturaba OSError, y json.dump lanza TypeError.

        Un tropiezo guardando la cache reclasificaba como 'error' una corrida que
        si habia terminado: se reportaria como fallida por un problema que solo
        afecta al ahorro.
        """
        def dump_que_revienta(*a, **k):
            raise TypeError("objeto no serializable")

        entorno.setattr(app.json, "dump", dump_que_revienta)
        gmaps = GmapsEspia(catalogo(negocios(2), []))
        est = correr(entorno, gmaps, WorksheetFalsa())
        assert est["status"] == "done", (
            "un fallo al guardar la cache marco como fallida una corrida que "
            "termino: %r" % est["error"]
        )
        assert est["nuevos_en_sheet"] == 2, "las filas si se escribieron"

    def test_una_fila_de_cache_y_una_fresca_salen_identicas(self, entorno, cache_temporal):
        """En un acierto se devolvia el dict guardado y en un fallo el crudo."""
        gmaps = GmapsEspia(catalogo(negocios(1), []))
        ws1 = WorksheetFalsa()
        correr(entorno, gmaps, ws1)
        fresca = ws1.filas[-1]

        app._import_job = app._nuevo_import_job("CiudadDemo", status="running")
        gmaps2 = GmapsEspia(catalogo(negocios(1), []))
        ws2 = WorksheetFalsa()
        correr(entorno, gmaps2, ws2)
        cacheada = ws2.filas[-1]

        assert len(gmaps2.llamadas_place) == 0, "el escenario no uso la cache"
        # Todo salvo la fecha/semana, que dependen del momento.
        assert fresca[1:18] == cacheada[1:18], (
            "la fila servida de cache difiere de la fresca:\n  %r\n  %r"
            % (fresca[1:18], cacheada[1:18])
        )


# ─────────── T2.6 · medidor de gasto y tope de presupuesto ───────────

class TestMedidorDeGasto:
    @pytest.fixture(autouse=True)
    def _sin_tope(self, entorno, tmp_path):
        entorno.setattr(app, "PLACES_CACHE_FILE", str(tmp_path / "c.json"))
        entorno.setattr(app, "PLACES_MAX_LLAMADAS_CORRIDA", None)
        entorno.setattr(app, "PLACES_PRESUPUESTO_CORRIDA", None)
        entorno.setattr(app, "PLACES_COSTO_TEXT_SEARCH", None)
        entorno.setattr(app, "PLACES_COSTO_DETAILS", None)

    def test_cuenta_una_por_cada_text_search(self, entorno):
        gmaps = GmapsEspia(catalogo(negocios(2), []))
        est = correr(entorno, gmaps, WorksheetFalsa())
        assert est["medidor"]["text_search"] == gmaps.llamadas_places, (
            "el medidor dice %d Text Search y se hicieron %d"
            % (est["medidor"]["text_search"], gmaps.llamadas_places)
        )

    def test_cuenta_una_por_cada_place_details(self, entorno):
        gmaps = GmapsEspia(catalogo(negocios(3), []))
        est = correr(entorno, gmaps, WorksheetFalsa())
        assert est["medidor"]["place_details"] == len(gmaps.llamadas_place) == 3

    def test_un_acierto_de_cache_no_suma_al_contador_de_details(self, entorno, tmp_path):
        """La comprobacion en las dos direcciones que pide el plan."""
        gmaps = GmapsEspia(catalogo(negocios(3), []))
        est1 = correr(entorno, gmaps, WorksheetFalsa())
        assert est1["medidor"]["place_details"] == 3
        assert est1["medidor"]["cache_hits"] == 0

        gmaps2 = GmapsEspia(catalogo(negocios(3), []))
        app._import_job = app._nuevo_import_job("CiudadDemo", status="running")
        est2 = correr(entorno, gmaps2, WorksheetFalsa())
        assert est2["medidor"]["place_details"] == 0, (
            "un acierto de cache sumo al contador de llamadas pagadas"
        )
        assert est2["medidor"]["cache_hits"] == 3

    def test_cuenta_los_duplicados_evitados(self, entorno):
        gmaps = GmapsEspia(catalogo(negocios(5), []))
        ws = WorksheetFalsa([("Neg %d" % i, "Calle %d" % i) for i in (1, 2, 3)])
        est = correr(entorno, gmaps, ws)
        assert est["medidor"]["duplicados_evitados"] == 3

    def test_sin_tarifas_no_se_inventa_un_costo(self, entorno):
        """T2.0 esta bloqueada: no hay tarifas reales.

        Publicar un 0.00 se leeria como "esta corrida salio gratis", que es una
        afirmacion falsa. Sin tarifa configurada, no hay importe.
        """
        gmaps = GmapsEspia(catalogo(negocios(2), []))
        est = correr(entorno, gmaps, WorksheetFalsa())
        assert est["medidor"]["costo"] is None, (
            "se publico un costo sin tarifas configuradas: %r" % est["medidor"]["costo"]
        )

    def test_con_tarifas_el_costo_es_la_suma(self, entorno):
        entorno.setattr(app, "PLACES_COSTO_TEXT_SEARCH", 0.032)
        entorno.setattr(app, "PLACES_COSTO_DETAILS", 0.017)
        gmaps = GmapsEspia(catalogo(negocios(2), []))
        est = correr(entorno, gmaps, WorksheetFalsa())
        m = est["medidor"]
        esperado = m["text_search"] * 0.032 + m["place_details"] * 0.017
        assert abs(m["costo"] - esperado) < 1e-9


class TestTopeDePresupuesto:
    @pytest.fixture(autouse=True)
    def _cache(self, entorno, tmp_path):
        entorno.setattr(app, "PLACES_CACHE_FILE", str(tmp_path / "c.json"))
        entorno.setattr(app, "PLACES_PRESUPUESTO_CORRIDA", None)
        entorno.setattr(app, "PLACES_COSTO_TEXT_SEARCH", None)
        entorno.setattr(app, "PLACES_COSTO_DETAILS", None)

    def test_la_corrida_se_detiene_al_superar_el_tope_de_llamadas(self, entorno):
        entorno.setattr(app, "PLACES_MAX_LLAMADAS_CORRIDA", 5)
        gmaps = GmapsEspia(catalogo(negocios(20), []))
        est = correr(entorno, gmaps, WorksheetFalsa())
        total = gmaps.llamadas_places + len(gmaps.llamadas_place)
        assert total <= 7, "se pasó del tope: %d llamadas" % total
        assert est["status"] == "presupuesto_agotado", (
            "la corrida acabo en %r en vez de avisar del tope" % est["status"]
        )

    def test_el_tope_no_corta_en_silencio(self, entorno):
        """El gate de este tope: pararse sin que nadie se entere es lo unico
        inaceptable."""
        entorno.setattr(app, "PLACES_MAX_LLAMADAS_CORRIDA", 5)
        gmaps = GmapsEspia(catalogo(negocios(20), []))
        est = correr(entorno, gmaps, WorksheetFalsa())
        texto = " ".join(est["log"])
        assert "presupuesto" in texto.lower() or "tope" in texto.lower(), (
            "el tope corto la corrida sin decirlo: %r" % est["log"]
        )
        assert est["error"], "no se dejo una causa legible"

    def test_conserva_lo_ya_guardado_al_agotar_presupuesto(self, entorno):
        entorno.setattr(app, "PLACES_MAX_LLAMADAS_CORRIDA", 8)
        gmaps = GmapsEspia(catalogo(negocios(20), []))
        ws = WorksheetFalsa()
        est = correr(entorno, gmaps, ws)
        assert est["status"] == "presupuesto_agotado"
        assert est["nuevos_en_sheet"] == ws.escrituras, (
            "el contador no cuadra con lo que de verdad se escribio"
        )

    def test_sin_tope_configurado_la_corrida_no_se_corta(self, entorno):
        """La otra direccion: el tope no puede dispararse solo."""
        entorno.setattr(app, "PLACES_MAX_LLAMADAS_CORRIDA", None)
        gmaps = GmapsEspia(catalogo(negocios(6), []))
        est = correr(entorno, gmaps, WorksheetFalsa())
        assert est["status"] == "done"
        assert est["nuevos_en_sheet"] == 6
