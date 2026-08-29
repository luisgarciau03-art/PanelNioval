"""Plan 1 - T1.6. Red de seguridad de /api/prospectos/ciudades.

Este endpoint alimenta la tabla de ciudades del dashboard y, de rebote, el orden
de los chips del importador, y hasta hoy NO tenia ni un solo test. El criterio
CE8 del plan dice "los tests existentes de /api/prospectos/ciudades siguen en
verde SIN modificarse": no existian, asi que primero hay que escribirlos.

Son tests de caracterizacion: fijan lo que el endpoint hace HOY, antes de que
T1.6 le anada campos. Si alguno se pone en rojo al cambiar el endpoint, es
ruptura de contrato y hay que justificarla, no ajustar el test.
"""
import pytest

import app as app_modulo


@pytest.fixture
def client():
    app_modulo.app.config["TESTING"] = True
    return app_modulo.app.test_client()


@pytest.fixture
def hoja(monkeypatch):
    """Dos ciudades con historial distinto y una sin ciudad."""
    contactos = [
        {"CIUDAD": "guadalajara", "TIENDA": "Ferreteria Uno"},
        {"CIUDAD": "GUADALAJARA", "TIENDA": "Ferreteria Dos"},
        {"CIUDAD": "Monterrey", "TIENDA": "Ferreteria Tres"},
        {"CIUDAD": "", "TIENDA": "Ferreteria Sin Ciudad"},
    ]
    respuestas = [
        {"Nombre De la Tienda": "FERRETERIA UNO", "Compatible": "APROBADO",
         "Respondio": "RESPONDIO", "Conclusión": "Pedido"},
        {"Nombre De la Tienda": "FERRETERIA DOS", "Compatible": "NEGADO",
         "Respondio": "BUZON", "Conclusión": "Nulo"},
        {"Nombre De la Tienda": "FERRETERIA TRES", "Compatible": "APROBADO",
         "Respondio": "RESPONDIO", "Conclusión": "Catalogo"},
    ]
    monkeypatch.setattr(app_modulo, "get_data", lambda *a, **k: contactos)
    monkeypatch.setattr(app_modulo, "get_all_respuestas", lambda *a, **k: respuestas)
    return contactos, respuestas


def por_ciudad(payload):
    return {c["ciudad"]: c for c in payload}


class TestContratoActual:
    def test_responde_200_y_una_lista(self, client, hoja):
        r = client.get("/api/prospectos/ciudades")
        assert r.status_code == 200
        assert isinstance(r.get_json(), list)

    def test_agrupa_por_ciudad_normalizando_mayusculas(self, client, hoja):
        """'guadalajara' y 'GUADALAJARA' son la misma ciudad: .title() las une."""
        d = por_ciudad(client.get("/api/prospectos/ciudades").get_json())
        assert "Guadalajara" in d
        assert d["Guadalajara"]["total"] == 2

    def test_los_contactos_sin_ciudad_van_a_sin_ciudad(self, client, hoja):
        d = por_ciudad(client.get("/api/prospectos/ciudades").get_json())
        assert d["Sin ciudad"]["total"] == 1

    def test_cuenta_llamados_aprobados_y_estado_de_llamada(self, client, hoja):
        d = por_ciudad(client.get("/api/prospectos/ciudades").get_json())
        gdl = d["Guadalajara"]
        assert gdl["llamados"] == 2
        assert gdl["aprobados"] == 1
        assert gdl["negados"] == 1
        assert gdl["respondio"] == 1
        assert gdl["buzon"] == 1
        assert gdl["pedido"] == 1
        assert gdl["nulo"] == 1

    def test_interes_pct_es_aprobados_sobre_llamados(self, client, hoja):
        d = por_ciudad(client.get("/api/prospectos/ciudades").get_json())
        assert d["Guadalajara"]["interes_pct"] == 50.0
        assert d["Monterrey"]["interes_pct"] == 100.0

    def test_interes_pct_es_cero_sin_llamadas(self, client, hoja):
        d = por_ciudad(client.get("/api/prospectos/ciudades").get_json())
        assert d["Sin ciudad"]["interes_pct"] == 0

    def test_el_campo_relevancia_sigue_existiendo(self, client, hoja):
        """T1.6 anade campos nuevos pero CONSERVA relevancia: el dashboard
        ordena por ella y quitarla rompe la lectura del owner."""
        payload = client.get("/api/prospectos/ciudades").get_json()
        assert all("relevancia" in c for c in payload)

    def test_relevancia_conserva_su_formula_historica(self, client, hoja):
        d = por_ciudad(client.get("/api/prospectos/ciudades").get_json())
        gdl = d["Guadalajara"]
        esperado = round(
            gdl["interes_pct"] * 1.5
            + (gdl["total"] / 2) * 40
            + min(gdl["llamados"] * 2, 20), 1
        )
        assert gdl["relevancia"] == esperado

    def test_las_quince_metricas_base_siguen_en_el_payload(self, client, hoja):
        campos = {
            "total", "llamados", "respondio", "buzon", "tel_incorrecto",
            "aprobados", "negados", "no_compatible", "marca_unica",
            "pedido", "catalogo", "correo", "avance", "continuacion",
            "nulo", "colgo",
        }
        payload = client.get("/api/prospectos/ciudades").get_json()
        for c in payload:
            assert campos <= set(c), f"faltan {sorted(campos - set(c))} en {c['ciudad']}"

    def test_no_devuelve_telefonos_ni_nombres_de_contacto(self, client, hoja):
        """Es un agregado por ciudad. Si algun dia se cuela un dato personal,
        este endpoint pasa a filtrar la hoja de clientes entera."""
        crudo = client.get("/api/prospectos/ciudades").get_data(as_text=True)
        assert "Ferreteria Uno" not in crudo
        assert "TIENDA" not in crudo


class TestOrdenDeLaRespuesta:
    def test_viene_ordenado_de_mayor_a_menor(self, client, hoja):
        """El importador NO reordena: pinta los chips en el orden que llega del
        servidor. Si esta lista deja de venir ordenada, los chips se desordenan
        sin que nadie toque una linea de JavaScript."""
        payload = client.get("/api/prospectos/ciudades").get_json()
        clave = "prioridad" if "prioridad" in payload[0] else "relevancia"
        valores = [c[clave] for c in payload]
        assert valores == sorted(valores, reverse=True)
