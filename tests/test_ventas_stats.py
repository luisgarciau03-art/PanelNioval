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

        assert d == {"total_ventas": 0, "clientes": 0, "por_mes": [], "top_clientes": []}


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
