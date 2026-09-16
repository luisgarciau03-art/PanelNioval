"""Plan 1 - T1.5. Endpoint /api/importador/ciudades.

Escritos ANTES del endpoint. Hoy el importador se baja /api/prospectos/ciudades,
lo filtra y lo fusiona A MANO en el navegador con un array estatico de 293
entradas. Esa logica se mueve al backend, que es donde puede probarse.
"""
import pytest

import app as app_modulo


@pytest.fixture
def client():
    app_modulo.app.config["TESTING"] = True
    return app_modulo.app.test_client()


@pytest.fixture
def hoja_vacia(monkeypatch):
    monkeypatch.setattr(app_modulo, "get_data", lambda *a, **k: [])
    monkeypatch.setattr(app_modulo, "get_all_respuestas", lambda *a, **k: [])


@pytest.fixture
def hoja(monkeypatch):
    """Historial con la forma que hace peligroso el problema real.

    Los Mochis entra por su alias 'Ahome' con UNA llamada aprobada (100 %), y
    Guadalajara aporta diez llamadas con una sola aprobada. Asi la tasa de
    referencia global queda en ~18 %, muy por debajo del 100 % del pueblo: es
    la unica forma de que el test ejercite de verdad el encogimiento por tamano
    de muestra. Con un fixture donde TODAS las llamadas se aprueban, la tasa del
    pueblo iguala a la referencia, el ajuste sale cero y el test pasa por el
    motivo equivocado.
    """
    contactos = (
        [{"CIUDAD": "Ahome", "TIENDA": f"Ferre Mochis {i}"} for i in range(5)]
        + [{"CIUDAD": "Chiapas", "TIENDA": f"Ferre Estado {i}"} for i in range(3)]
        + [{"CIUDAD": "Guadalajara", "TIENDA": f"Ferre Tapatia {i}"} for i in range(20)]
    )
    respuestas = [
        {"Nombre De la Tienda": "FERRE MOCHIS 0", "Compatible": "APROBADO",
         "Respondio": "RESPONDIO", "Conclusión": "Pedido"},
        {"Nombre De la Tienda": "FERRE TAPATIA 0", "Compatible": "APROBADO",
         "Respondio": "RESPONDIO", "Conclusión": "Pedido"},
    ] + [
        {"Nombre De la Tienda": f"FERRE TAPATIA {i}", "Compatible": "NEGADO",
         "Respondio": "RESPONDIO", "Conclusión": "Nulo"}
        for i in range(1, 10)
    ]
    monkeypatch.setattr(app_modulo, "get_data", lambda *a, **k: contactos)
    monkeypatch.setattr(app_modulo, "get_all_respuestas", lambda *a, **k: respuestas)


@pytest.fixture
def hoja_saturada(monkeypatch):
    """Chihuahua con 400 contactos ya escritos y ninguna llamada.

    Es la situacion real medida en la hoja de produccion: 448 contactos sobre
    651 ferreterias del DENUE. Sin llamadas, el desempeno es neutro, asi que
    cualquier caida del factor viene SOLO de la saturacion.
    """
    contactos = [{"CIUDAD": "Chihuahua", "TIENDA": f"Ferre Chi {i}"} for i in range(400)]
    monkeypatch.setattr(app_modulo, "get_data", lambda *a, **k: contactos)
    monkeypatch.setattr(app_modulo, "get_all_respuestas", lambda *a, **k: [])


def pedir(client):
    r = client.get("/api/importador/ciudades")
    assert r.status_code == 200
    return r.get_json()


def buscar(payload, nombre):
    return next(c for c in payload["ciudades"] if c["ciudad"] == nombre)


class TestFormaDeLaRespuesta:
    def test_trae_ciudades_sin_clasificar_y_regiones(self, client, hoja):
        d = pedir(client)
        assert {"ciudades", "sin_clasificar", "regiones"} <= set(d)

    def test_cada_ciudad_trae_el_contrato_completo(self, client, hoja):
        for c in pedir(client)["ciudades"]:
            faltan = {
                "ciudad", "estado", "region", "potencial_mercado",
                "desempeno_nioval", "prioridad", "total", "llamados",
                "aprobados", "interes_pct", "unidades_ferreteras", "explicacion",
            } - set(c)
            assert faltan == set(), f"{c.get('ciudad')} sin {sorted(faltan)}"

    def test_la_explicacion_viene_armada_del_backend(self, client, hoja):
        """Para que la UI no tenga que reconstruir el razonamiento y para que la
        posicion sea auditable sin creerse el puntaje comprimido."""
        for c in pedir(client)["ciudades"][:20]:
            assert c["explicacion"].strip()
            assert str(c["unidades_ferreteras"]) in c["explicacion"]

    def test_las_regiones_traen_su_conteo(self, client, hoja):
        d = pedir(client)
        total = sum(r["total"] for r in d["regiones"])
        assert total == len(d["ciudades"])
        assert all(r["total"] > 0 for r in d["regiones"])


class TestOrdenYPuntuacion:
    def test_ordenado_por_prioridad_descendente(self, client, hoja):
        p = [c["prioridad"] for c in pedir(client)["ciudades"]]
        assert p == sorted(p, reverse=True)

    def test_ninguna_ciudad_queda_en_cero(self, client, hoja):
        """Restriccion no negociable del ADR: un cero reintroduce el empate
        arbitrario que este plan corrige."""
        ceros = [c["ciudad"] for c in pedir(client)["ciudades"] if not c["prioridad"] > 0]
        assert ceros == []

    def test_una_ciudad_virgen_tiene_desempeno_neutro(self, client, hoja):
        """Sin historial el factor vale 1.0: no se penaliza no haber ido."""
        c = buscar(pedir(client), "Puebla")
        assert c["llamados"] == 0
        assert c["desempeno_nioval"] == 1.0
        assert c["prioridad"] == c["potencial_mercado"]

    def test_el_desempeno_ajusta_pero_no_domina(self, client, hoja):
        """CE7. Un pueblo con 1 aprobado de 1 llamada no puede superar a una
        plaza de potencial alto sin historial."""
        d = pedir(client)
        pueblo = buscar(d, "Los Mochis")
        assert pueblo["interes_pct"] == 100.0
        grandes = [c for c in d["ciudades"] if c["potencial_mercado"] > 85]
        assert grandes, "el catalogo deberia traer plazas de potencial alto"
        assert all(pueblo["prioridad"] < g["prioridad"] for g in grandes)

    def test_el_desempeno_se_queda_dentro_de_su_rango(self, client, hoja):
        for c in pedir(client)["ciudades"]:
            assert 0.6 <= c["desempeno_nioval"] <= 1.25

    def test_una_llamada_al_100_pct_apenas_mueve_el_factor(self, client, hoja):
        """El encogimiento por tamano de muestra, medido directamente.

        Los Mochis va 1 de 1 (100 %) contra una referencia global de ~18 %. Sin
        encogimiento el factor se iria al tope de 1.25; con el, se queda cerca
        de neutro porque UNA llamada no es evidencia de nada.
        """
        c = buscar(pedir(client), "Los Mochis")
        assert c["interes_pct"] == 100.0
        assert c["desempeno_nioval"] < 1.10


class TestSaturacionDeLaPlaza:
    def test_una_plaza_ya_cosechada_baja_de_prioridad(self, client, hoja_saturada):
        """Places rinde ~60 resultados por corrida: sin este descuento, una plaza
        exprimida seguiria siendo la primera para siempre."""
        c = buscar(pedir(client), "Chihuahua")
        assert c["llamados"] == 0, "sin llamadas, el desempeno no interviene"
        assert c["desempeno_nioval"] < 0.85
        assert c["prioridad"] < c["potencial_mercado"]

    def test_la_misma_plaza_sin_cosechar_no_se_descuenta(self, client, hoja_vacia):
        c = buscar(pedir(client), "Chihuahua")
        assert c["desempeno_nioval"] == 1.0
        assert c["prioridad"] == c["potencial_mercado"]

    def test_la_explicacion_dice_cuanto_se_cosecho(self, client, hoja_saturada):
        c = buscar(pedir(client), "Chihuahua")
        assert "cosechada" in c["explicacion"]
        assert "400 contactos" in c["explicacion"]


class TestReconciliacionDeNombres:
    def test_la_hoja_casa_por_alias(self, client, hoja):
        """La hoja dice 'Ahome' y el catalogo se llama 'Los Mochis'. Si no casan,
        cinco contactos reales desaparecen del ranking."""
        c = buscar(pedir(client), "Los Mochis")
        assert c["total"] == 5
        assert c["llamados"] == 1

    def test_lo_que_no_casa_va_a_sin_clasificar_y_es_visible(self, client, hoja):
        """'Chiapas' es un estado, no una ciudad, y esta escrito asi en la hoja
        de produccion. Nada se descarta en silencio (riesgo R2 del plan)."""
        d = pedir(client)
        nombres = {c["ciudad"] for c in d["sin_clasificar"]}
        assert "Chiapas" in nombres
        chiapas = next(c for c in d["sin_clasificar"] if c["ciudad"] == "Chiapas")
        assert chiapas["total"] == 3

    def test_ningun_contacto_se_pierde_entre_las_dos_listas(self, client, hoja):
        d = pedir(client)
        contados = sum(c["total"] for c in d["ciudades"])
        contados += sum(c["total"] for c in d["sin_clasificar"])
        assert contados == 28  # 5 Ahome + 3 Chiapas + 20 Guadalajara

    def test_el_catalogo_llega_entero_con_la_hoja_vacia(self, client, hoja_vacia):
        d = pedir(client)
        assert len(d["ciudades"]) > 500
        assert d["sin_clasificar"] == []
        assert all(c["total"] == 0 for c in d["ciudades"])
        assert all(c["desempeno_nioval"] == 1.0 for c in d["ciudades"])

    def test_las_32_entidades_llegan_al_importador(self, client, hoja_vacia):
        d = pedir(client)
        assert len({c["estado"] for c in d["ciudades"]}) == 32


class TestNoFiltraDatosPersonales:
    def test_no_devuelve_nombres_de_tienda_ni_telefonos(self, client, hoja):
        """El endpoint deriva de la hoja de clientes: solo agregados por ciudad."""
        # Sin el 200 este test pasaba tambien contra un 404, que no contiene
        # ningun nombre de tienda por el simple hecho de no contener nada.
        pedir(client)
        crudo = client.get("/api/importador/ciudades").get_data(as_text=True)
        assert "Ferre Mochis" not in crudo
        assert "Ferre Tapatia" not in crudo
        assert "TIENDA" not in crudo

    def test_no_expone_la_clave_inegi_como_dato_de_negocio(self, client, hoja_vacia):
        """No es sensible, pero tampoco lo usa la UI: cuanto menos viaje, mejor.
        Si algun dia hace falta, se anade a proposito y con su motivo."""
        assert all("clave_inegi" not in c for c in pedir(client)["ciudades"])


@pytest.fixture
def hoja_con_ciudad_vacia(monkeypatch):
    """Un contacto con la celda CIUDAD vacia. Es un estado normal de una hoja
    mantenida a mano, y hacia desaparecer al contacto de las DOS listas."""
    contactos = [
        {"CIUDAD": "", "TIENDA": "Ferre Sin Ciudad"},
        {"CIUDAD": None, "TIENDA": "Ferre Nula"},
        {"CIUDAD": "Guadalajara", "TIENDA": "Ferre Tapatia"},
    ]
    monkeypatch.setattr(app_modulo, "get_data", lambda *a, **k: contactos)
    monkeypatch.setattr(app_modulo, "get_all_respuestas", lambda *a, **k: [])


class TestNingunContactoDesaparece:
    def test_los_contactos_sin_ciudad_aparecen_en_sin_clasificar(self, client, hoja_con_ciudad_vacia):
        d = pedir(client)
        nombres = {c["ciudad"] for c in d["sin_clasificar"]}
        assert "Sin ciudad" in nombres

    def test_la_suma_de_las_dos_listas_cuadra_con_la_hoja(self, client, hoja_con_ciudad_vacia):
        """El test equivalente de mas arriba no podia cazar este fallo: su fixture
        no tenia ni un contacto con la celda vacia, asi que sumaba correcto por no
        ejercitar el camino roto."""
        d = pedir(client)
        total = sum(c["total"] for c in d["ciudades"])
        total += sum(c["total"] for c in d["sin_clasificar"])
        assert total == 3


class TestDegradacionSinCatalogo:
    """Si el archivo del catalogo falta o esta roto, el panel sigue sirviendo. Pero
    el operador tiene que poder distinguirlo de "ninguna ciudad caso"."""

    @pytest.fixture
    def catalogo_roto(self, monkeypatch, tmp_path):
        falso = tmp_path / "no_existe.json"
        monkeypatch.setattr(app_modulo, "CATALOGO_CIUDADES_FILE", str(falso))
        # monkeypatch restaura el valor previo al salir, asi que la cache buena
        # vuelve sola: no hace falta limpiarla a mano despues del yield.
        monkeypatch.setattr(app_modulo, "_estado_catalogo", None)

    def test_responde_200_y_no_revienta(self, client, catalogo_roto, hoja):
        d = pedir(client)
        assert d["ciudades"] == []

    def test_lo_dice_en_el_payload(self, client, catalogo_roto, hoja):
        assert pedir(client)["catalogo_cargado"] is False

    def test_con_catalogo_bueno_la_bandera_es_verdadera(self, client, hoja):
        assert pedir(client)["catalogo_cargado"] is True

    def test_los_contactos_no_se_pierden_aunque_no_haya_catalogo(self, client, catalogo_roto, hoja):
        """Sin catalogo, TODO cae a sin_clasificar. Ninguno al limbo."""
        d = pedir(client)
        assert sum(c["total"] for c in d["sin_clasificar"]) == 28


class TestFactoresPuros:
    """Las dos funciones del modelo, llamadas directamente y con datos sucios.
    La hoja no garantiza consistencia: es una hoja de calculo editada a mano."""

    def test_sin_llamadas_el_desempeno_es_exactamente_neutro(self):
        assert app_modulo._factor_desempeno(0, 0, 0.30) == 1.0

    def test_aprobados_mayores_que_llamados_no_revienta(self):
        v = app_modulo._factor_desempeno(1, 5, 0.30)
        assert isinstance(v, float)

    def test_una_referencia_de_cero_no_divide_entre_cero(self):
        assert app_modulo._factor_desempeno(10, 5, 0.0) is not None

    def test_el_desempeno_nunca_sale_de_su_rango(self):
        for llamados, aprobados, ref in [(1, 1, 0.01), (1000, 1000, 0.01),
                                         (1000, 0, 0.99), (5, 5, 0.5)]:
            v = app_modulo._factor_desempeno(llamados, aprobados, ref)
            assert 0.75 <= v <= 1.25, (llamados, aprobados, ref, v)

    def test_sin_ferreterias_la_saturacion_es_neutra(self):
        assert app_modulo._factor_saturacion(50, 0) == 1.0

    def test_mas_contactos_que_ferreterias_topa_en_el_descuento_maximo(self):
        """Puede pasar de verdad: la hoja lleva contactos que ya no existen en el
        DENUE, o de otro municipio mal etiquetado."""
        v = app_modulo._factor_saturacion(10_000, 10)
        assert v == pytest.approx(1 - app_modulo.DESCUENTO_MAX_SATURACION)

    def test_una_plaza_virgen_no_se_descuenta(self):
        assert app_modulo._factor_saturacion(0, 500) == 1.0

    def test_el_factor_combinado_respeta_los_limites(self):
        extremos = [
            {"llamados": 0, "aprobados": 0, "total": 0},
            {"llamados": 1000, "aprobados": 1000, "total": 0},
            {"llamados": 1000, "aprobados": 0, "total": 100_000},
        ]
        for m in extremos:
            v = app_modulo._calcular_factor_nioval(m, 100, 0.30)
            assert app_modulo.FACTOR_MIN <= v <= app_modulo.FACTOR_MAX, (m, v)
