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
