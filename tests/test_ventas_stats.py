"""La superficie de Ventas, que nunca se habia ejercitado con datos.

Queda anotada como deuda desde el Plan 4: *"la seccion de Ventas nunca se ha
ejercitado con datos — no hay fixture para `/api/ventas/*`"*. De las cuatro rutas
`/api/ventas/*`, solo una aparecia en la suite, y de refilon (el escape de formulas).
`/api/ventas/stats` —la que alimenta la grafica del tablero— no tenia ni un test.

Estos tests no inventan comportamiento: caracterizan el que hay, y donde el que hay
afirma algo falso, lo dicen.
"""
import pytest

import app


@pytest.fixture
def cliente():
    app.app.config["TESTING"] = True
    return app.app.test_client()


def venta(cliente_="Ferretería El Tornillo", monto="1500.50", fecha="15/01/2026"):
    """Una fila de la hoja de ventas, con los encabezados que usa la heuristica."""
    return {"Cliente": cliente_, "Monto": monto, "Fecha": fecha}


class TestSinDatosNoInventa:

    def test_hoja_vacia_devuelve_ceros(self, cliente, monkeypatch):
        monkeypatch.setattr(app, "get_data", lambda _q: [])

        d = cliente.get("/api/ventas/stats").get_json()

        assert d["total_ventas"] == 0 and d["clientes"] == 0
        assert d["por_mes"] == [] and d["top_clientes"] == []


class TestLoQueSI_FUNCIONA:

    def test_cuenta_ventas_y_clientes_distintos(self, cliente, monkeypatch):
        filas = [venta("Ferretería A"), venta("Ferretería A"), venta("Ferretería B")]
        monkeypatch.setattr(app, "get_data", lambda _q: filas)

        d = cliente.get("/api/ventas/stats").get_json()

        assert d["total_ventas"] == 3
        assert d["clientes"] == 2, "dos clientes distintos, tres ventas"

    def test_el_top_ordena_por_numero_de_compras(self, cliente, monkeypatch):
        filas = [venta("Ferretería A")] * 3 + [venta("Ferretería B")]
        monkeypatch.setattr(app, "get_data", lambda _q: filas)

        top = cliente.get("/api/ventas/stats").get_json()["top_clientes"]

        assert top[0][0].lower().startswith("ferretería a")
        assert top[0][1] == 3

    def test_suma_los_montos_del_mes(self, cliente, monkeypatch):
        filas = [venta(monto="1000", fecha="05/01/2026"),
                 venta(monto="500.50", fecha="20/01/2026")]
        monkeypatch.setattr(app, "get_data", lambda _q: filas)

        por_mes = cliente.get("/api/ventas/stats").get_json()["por_mes"]

        assert len(por_mes) == 1
        assert por_mes[0]["total"] == pytest.approx(1500.50)


class TestLosMesesVanEN_ORDEN:
    """El defecto: `sorted(por_mes.items())` ordena la CADENA `'%b %Y'`.

    `'Abr 2026'` va antes que `'Ene 2026'` alfabeticamente, asi que la serie que
    alimenta la grafica sale desordenada — y el `[-12:]` que dice "los ultimos 12
    meses" recorta por orden alfabetico, no por fecha: puede tirar el mes mas
    reciente y conservar uno viejo.
    """

    def test_enero_va_antes_que_febrero(self, cliente, monkeypatch):
        filas = [venta(monto="100", fecha="15/01/2026"),
                 venta(monto="200", fecha="15/02/2026"),
                 venta(monto="300", fecha="15/12/2026")]
        monkeypatch.setattr(app, "get_data", lambda _q: filas)

        meses = [m["mes"] for m in cliente.get("/api/ventas/stats").get_json()["por_mes"]]

        assert len(meses) == 3
        totales = [m["total"] for m in cliente.get("/api/ventas/stats").get_json()["por_mes"]]
        assert totales == [100, 200, 300], (
            f"la serie no esta en orden cronologico: {meses}")

    def test_el_recorte_a_12_conserva_los_MAS_RECIENTES(self, cliente, monkeypatch):
        """Con 13 meses, el que sobra tiene que ser el MAS VIEJO."""
        filas = [venta(monto="1", fecha=f"15/{m:02d}/2025") for m in range(1, 13)]
        filas.append(venta(monto="999", fecha="15/01/2026"))
        monkeypatch.setattr(app, "get_data", lambda _q: filas)

        por_mes = cliente.get("/api/ventas/stats").get_json()["por_mes"]

        assert len(por_mes) == 12
        assert por_mes[-1]["total"] == 999, (
            "el mes mas reciente no quedo al final: el recorte no es cronologico")


class TestUnaVentaSIN_MONTO_NO_VALE_UN_PESO:
    """El segundo defecto: `por_mes[mes] += monto or 1`.

    Si el monto no se puede leer —celda vacia, texto, columna ausente— se suma
    **1**. La serie deja de ser dinero y pasa a ser un conteo, en la misma grafica,
    sin decirlo. Un peso inventado es una afirmacion falsa, no un valor por defecto.
    """

    def test_un_monto_ilegible_no_se_convierte_en_un_peso(self, cliente, monkeypatch):
        filas = [venta(monto="1000", fecha="15/01/2026"),
                 venta(monto="no aplica", fecha="20/01/2026")]
        monkeypatch.setattr(app, "get_data", lambda _q: filas)

        por_mes = cliente.get("/api/ventas/stats").get_json()["por_mes"]

        assert por_mes[0]["total"] == pytest.approx(1000), (
            f"la venta ilegible aporto dinero que no existe: {por_mes}")

    def test_y_se_dice_cuantas_no_se_pudieron_leer(self, cliente, monkeypatch):
        """Descartar en silencio es la otra mitad del mismo fallo."""
        filas = [venta(monto="1000", fecha="15/01/2026"),
                 venta(monto="", fecha="20/01/2026"),
                 venta(monto="s/d", fecha="21/01/2026")]
        monkeypatch.setattr(app, "get_data", lambda _q: filas)

        d = cliente.get("/api/ventas/stats").get_json()

        assert d.get("montos_ilegibles") == 2, (
            "la grafica no dice cuantas ventas no pudo sumar")


# ═══════════ Lo que encontro el gate: arregle el endpoint EQUIVOCADO ═══════════

class TestLaGraficaQUE_DE_VERDAD_SE_VE:
    """El gate lo busco y yo no: `dashboard.js` NO llama a `/api/ventas/stats`.

    `loadVentasDash()` pide `/api/prospectos/ventas-dashboard`, que es otra funcion
    con su propia agrupacion por mes. O sea que los arreglos de arriba estaban en una
    ruta que el tablero no invoca. Yo habia afirmado que era "la que alimenta la
    grafica del tablero" sin comprobarlo.

    Esa si ordenaba bien -- su clave es '%Y-%m' -- pero conserva las otras dos:
    etiqueta en ingles, y montos ilegibles contados como 0.0 sin avisar.
    """

    def test_las_etiquetas_van_en_espanol(self, cliente, monkeypatch):
        # La clave del payload es `mes`, no `label`, y la columna del dinero es
        # `Monto`: las dos me las invente y las dos costaron un rojo. El endpoint
        # lee encabezados fijos (VENTAS_COLS), no la heuristica de `/stats`.
        filas = [{"Cliente": "A", "Monto": "100", "Fecha": "15/01/2026"}]
        monkeypatch.setattr(app, "get_data", lambda _q: filas)

        d = cliente.get("/api/prospectos/ventas-dashboard").get_json()

        etiquetas = [m["mes"] for m in d["por_mes"]]
        assert etiquetas == ["Ene 2026"], f"la grafica del tablero dice: {etiquetas}"

    def test_dice_cuantos_montos_no_pudo_leer(self, cliente, monkeypatch):
        filas = [{"Cliente": "A", "Monto": "100", "Fecha": "15/01/2026"},
                 {"Cliente": "B", "Monto": "no aplica", "Fecha": "16/01/2026"}]
        monkeypatch.setattr(app, "get_data", lambda _q: filas)

        d = cliente.get("/api/prospectos/ventas-dashboard").get_json()

        assert d.get("montos_ilegibles") == 1, (
            "un monto ilegible se sumo como 0 y nadie se entera")


class TestMontosIlegiblesNO_MIENTE_SOBRE_SU_CAUSA:
    """MEDIUM del gate: "no encontre la columna" y "la celda es ilegible" no son
    lo mismo, y el contador los mezclaba.

    Con una hoja sin columna de monto, el endpoint respondia
    `montos_ilegibles == todas las filas`, que se lee como "mil ventas corruptas"
    cuando en realidad es "no se cual es la columna del dinero".
    """

    def test_sin_columna_de_monto_se_dice_ESO_y_no_que_son_ilegibles(self, cliente, monkeypatch):
        filas = [{"Cliente": "A", "Fecha": "15/01/2026"},
                 {"Cliente": "B", "Fecha": "16/01/2026"}]
        monkeypatch.setattr(app, "get_data", lambda _q: filas)

        d = cliente.get("/api/ventas/stats").get_json()

        assert d["montos_ilegibles"] is None, (
            f"con la columna ausente no se puede evaluar; dijo {d['montos_ilegibles']!r}")
        assert d["columna_monto"] is None


class TestLaFORMA_DE_LA_RESPUESTA_NO_CAMBIA_CON_LOS_DATOS:
    """MEDIUM del gate: los campos nuevos solo existian cuando habia datos."""

    def test_la_hoja_vacia_trae_las_mismas_claves(self, cliente, monkeypatch):
        monkeypatch.setattr(app, "get_data", lambda _q: [])
        vacia = set(cliente.get("/api/ventas/stats").get_json())

        monkeypatch.setattr(app, "get_data", lambda _q: [venta()])
        con_datos = set(cliente.get("/api/ventas/stats").get_json())

        assert vacia == con_datos, f"faltan en la vacia: {con_datos - vacia}"


class TestUnaCeldaVACIA_NO_ES_ILEGIBLE:
    """Lo destapo la mutacion: ninguna guarda cubria la diferencia.

    Una venta con el monto en blanco es una venta de importe desconocido, no un
    dato corrupto. Contarla como ilegible inflaria la alarma y haria que el numero
    dejara de significar "hay celdas que arreglar".
    """

    def test_vacio_no_suma_al_contador(self, cliente, monkeypatch):
        filas = [{"Cliente": "A", "Monto": "", "Fecha": "15/01/2026"},
                 {"Cliente": "B", "Monto": "   ", "Fecha": "16/01/2026"}]
        monkeypatch.setattr(app, "get_data", lambda _q: filas)

        d = cliente.get("/api/prospectos/ventas-dashboard").get_json()

        assert d["montos_ilegibles"] == 0, "una celda vacia no es un dato corrupto"

    def test_pero_un_texto_SI(self, cliente, monkeypatch):
        filas = [{"Cliente": "A", "Monto": "pendiente", "Fecha": "15/01/2026"}]
        monkeypatch.setattr(app, "get_data", lambda _q: filas)

        assert cliente.get("/api/prospectos/ventas-dashboard").get_json()["montos_ilegibles"] == 1


class TestNoSeMUESTRAN_CEROS_CON_LA_HOJA_LLENA:
    """Hallazgo en PRODUCCION, no en el fixture.

    La hoja de ventas trae **183 filas** y **no tiene columna `Fecha`**: tiene `MES`
    con el nombre del mes en español ("Julio", "Agosto"), sin año. Las dos rutas
    leen `Fecha`, no la encuentran, y `if not fecha: continue` descarta TODAS las
    filas. El tablero lleva mostrando **0 en todo** con 183 ventas en la hoja.

    El cero no es el defecto: el defecto es que no se distingue de "no vendiste
    nada". Agrupar por `MES` es una decision de producto -- no hay año, y mezclar
    ejercicios seria inventar -- pero **decir cuantas filas no se pudieron ubicar en
    el tiempo no lo es**.
    """

    def test_dice_cuantas_ventas_no_pudo_ubicar_en_el_tiempo(self, cliente, monkeypatch):
        filas = [{"Cliente": "A", "Monto": "100", "MES": "Julio"},
                 {"Cliente": "B", "Monto": "200", "MES": "Agosto"}]
        monkeypatch.setattr(app, "get_data", lambda _q: filas)

        d = cliente.get("/api/prospectos/ventas-dashboard").get_json()

        assert d["por_mes"] == [], "sin fecha no se puede construir la serie"
        assert d["ventas_sin_fecha"] == 2, (
            "el tablero muestra ceros y no dice que no pudo leer NINGUNA fecha")

    def test_con_fecha_utilizable_el_contador_queda_en_cero(self, cliente, monkeypatch):
        filas = [{"Cliente": "A", "Monto": "100", "Fecha": "15/01/2026"}]
        monkeypatch.setattr(app, "get_data", lambda _q: filas)

        d = cliente.get("/api/prospectos/ventas-dashboard").get_json()

        assert d["ventas_sin_fecha"] == 0
        assert len(d["por_mes"]) == 1

    def test_una_fila_sin_cliente_no_cuenta_como_sin_fecha(self, cliente, monkeypatch):
        """Son dos motivos distintos de descarte y confundirlos da un numero falso."""
        filas = [{"Cliente": "", "Monto": "100", "Fecha": "15/01/2026"}]
        monkeypatch.setattr(app, "get_data", lambda _q: filas)

        assert cliente.get("/api/prospectos/ventas-dashboard").get_json()["ventas_sin_fecha"] == 0


# ═══════ Lo que encontro el gate: arregle UNA ruta y mi propio test decia DOS ═══════

class TestLaOtraRutaTAMBIEN_LO_DICE:
    """HIGH del gate, y el docstring de arriba ya lo reconocia: "las DOS rutas leen
    `Fecha`, no la encuentran". Y solo se arreglo una.

    `/api/ventas/stats` no tenia como decir "no encontre la columna de fecha", a
    diferencia de `montos_ilegibles`/`columna_monto`, que si distinguen.
    """

    def test_publica_que_columna_de_fecha_uso(self, cliente, monkeypatch):
        monkeypatch.setattr(app, "get_data", lambda _q: [venta()])

        assert cliente.get("/api/ventas/stats").get_json()["columna_fecha"] == "Fecha"

    def test_sin_columna_de_fecha_lo_dice_en_vez_de_devolver_una_serie_vacia(self, cliente, monkeypatch):
        """La hoja real: `Cliente`, `MES`, `Monto`... y ninguna `Fecha`."""
        filas = [{"Cliente": "A", "Monto": "100", "MES": "Julio"},
                 {"Cliente": "B", "Monto": "200", "MES": "Agosto"}]
        monkeypatch.setattr(app, "get_data", lambda _q: filas)

        d = cliente.get("/api/ventas/stats").get_json()

        assert d["por_mes"] == []
        assert d["columna_fecha"] is None, (
            "serie vacia sin decir por que: indistinguible de 'no se vendio'")
        assert d["total_ventas"] == 2, "las filas existen aunque no se puedan ubicar"


class TestSIN_CLIENTE_TAMPOCO_SE_DESCARTA_EN_SILENCIO:
    """HIGH del gate: el mismo patron, por la otra columna.

    Una fila con `Cliente` vacio desaparecia de todos los totales sin contador. Es
    el mismo sintoma de fondo que motivo el PR -- un total mas bajo que la hoja, sin
    que nada lo indique -- solo que por otra puerta.
    """

    def test_se_cuentan_aparte_de_las_que_no_tienen_fecha(self, cliente, monkeypatch):
        filas = [{"Cliente": "", "Monto": "100", "Fecha": "15/01/2026"},
                 {"Cliente": "B", "Monto": "200", "MES": "Julio"},
                 {"Cliente": "C", "Monto": "300", "Fecha": "20/01/2026"}]
        monkeypatch.setattr(app, "get_data", lambda _q: filas)

        d = cliente.get("/api/prospectos/ventas-dashboard").get_json()

        assert d["ventas_sin_cliente"] == 1
        assert d["ventas_sin_fecha"] == 1, "son motivos distintos y se cuentan aparte"
        assert d["total_pedidos"] == 1, "solo una fila tenia las dos cosas"


class TestMontosIlegiblesSOLO_CUENTA_DINERO_QUE_IBA_A_ENTRAR:
    """MEDIUM del gate: `parse_monto` corria ANTES de los dos `continue`.

    Con la hoja real -- 183 filas sin fecha -- un monto ilegible subia el contador
    aunque esa fila nunca iba a sumar. Dos explicaciones distintas del mismo cero,
    mezcladas en un numero.
    """

    def test_una_fila_ya_descartada_no_ensucia_el_contador(self, cliente, monkeypatch):
        filas = [{"Cliente": "A", "Monto": "no aplica", "MES": "Julio"},
                 {"Cliente": "B", "Monto": "400", "Fecha": "15/01/2026"}]
        monkeypatch.setattr(app, "get_data", lambda _q: filas)

        d = cliente.get("/api/prospectos/ventas-dashboard").get_json()

        assert d["ventas_sin_fecha"] == 1
        assert d["montos_ilegibles"] == 0, (
            "conto un monto ilegible de una fila que ya se descarto por fecha")

    def test_pero_uno_ilegible_QUE_SI_ENTRABA_se_cuenta(self, cliente, monkeypatch):
        filas = [{"Cliente": "A", "Monto": "pendiente", "Fecha": "15/01/2026"}]
        monkeypatch.setattr(app, "get_data", lambda _q: filas)

        assert cliente.get("/api/prospectos/ventas-dashboard").get_json()["montos_ilegibles"] == 1


class TestLaCUARTA_COPIA_ERA_LA_MAS_ROTA:
    """LOW del gate, y merece arreglarse porque es el patron exacto del PR.

    `api_stats` truncaba el FORMATO, no solo el dato: `'%d/%m/%Y %H:%M:%S'[:10]` da
    `'%d/%m/%Y %'` -- un patron que termina en un `%` suelto y **no puede casar con
    nada**. Codigo muerto, tapado por un `except: pass` desnudo.
    """

    def test_una_marca_temporal_con_hora_SI_se_ubica_en_su_semana(self, cliente, monkeypatch):
        monkeypatch.setattr(app, "get_data", lambda _q: [])
        monkeypatch.setattr(app, "get_all_respuestas",
                            lambda: [{"Marca temporal": "15/01/2026 14:30:00",
                                      "Nombre De la Tienda": "A"}])

        d = cliente.get("/api/prospectos/stats").get_json()

        semanas = d.get("por_semana") or {}
        assert semanas, f"la respuesta con hora no cayo en ninguna semana: {semanas}"


class TestClientesFrecuentes:
    """La tercera ruta de Ventas, que tampoco tenia ni un test.

    Se extrajo a `metricas_ventas` como las otras dos, y mover codigo sin cobertura
    es mover a ciegas: el diff normalizado dice que es identico, pero nada lo
    vigilaria despues. Estos dos fijan lo que hace.
    """

    def test_agrupa_por_cliente_y_ordena_por_monto(self, cliente, monkeypatch):
        filas = [{"Cliente": "A", "Monto": "100", "Fecha": "15/01/2026", "ESQUEMA": "X"},
                 {"Cliente": "A", "Monto": "50", "Fecha": "20/02/2026", "ESQUEMA": "X"},
                 {"Cliente": "B", "Monto": "300", "Fecha": "10/01/2026", "ESQUEMA": "Y"}]
        monkeypatch.setattr(app, "get_data", lambda _q: filas)

        r = cliente.get("/api/prospectos/clientes-frecuentes").get_json()

        assert [c["Cliente"] for c in r] == ["B", "A"], "no ordena de mayor a menor"
        a = next(c for c in r if c["Cliente"] == "A")
        assert a["Pedidos"] == 2 and a["Total Monto"] == 150.0

    def test_el_ultimo_pedido_es_el_MAS_RECIENTE_y_en_espanol(self, cliente, monkeypatch):
        filas = [{"Cliente": "A", "Monto": "10", "Fecha": "15/01/2026", "ESQUEMA": "X"},
                 {"Cliente": "A", "Monto": "10", "Fecha": "20/02/2026", "ESQUEMA": "X"}]
        monkeypatch.setattr(app, "get_data", lambda _q: filas)

        r = cliente.get("/api/prospectos/clientes-frecuentes").get_json()

        assert r[0]["Ultimo Pedido"] == "Febrero 2026"

    def test_sin_fecha_utilizable_lo_dice_con_una_raya(self, cliente, monkeypatch):
        """La hoja real no tiene columna `Fecha`: esta ruta cae en el mismo sitio."""
        monkeypatch.setattr(app, "get_data",
                            lambda _q: [{"Cliente": "A", "Monto": "10", "MES": "Julio"}])

        assert cliente.get("/api/prospectos/clientes-frecuentes").get_json()[0]["Ultimo Pedido"] == "—"
