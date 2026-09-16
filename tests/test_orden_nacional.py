"""Plan 1 - T1.4. El orden nacional que ve el operador es el que decidio el ADR.

El riesgo de un modelo de puntuacion no es equivocarse en la formula: es ser
correcto en el codigo y distinto en la lista. `datos/ciudades_mx.json` se ordena
en el generador y `/api/importador/ciudades` lo vuelve a ordenar en el servidor,
con la prioridad ya multiplicada por `factor_nioval`. Son DOS ordenaciones sobre
el mismo dato, y nadie habia comprobado que coincidieran.

Coinciden en las dos primeras claves y divergian en la tercera: el ADR 7 manda
desempatar por **clave INEGI ascendente** y el endpoint lo hacia por nombre.
Con 606 ciudades daba igual; con las 1,004 de T1.3 hay 103 grupos en empate
exacto que involucran 232 ciudades.

Ninguna de las dos era aleatoria, asi que esto NO era un fallo de
reproducibilidad. Era una divergencia entre una decision cerrada y el codigo,
y se resuelve a favor de la decision: la clave INEGI es estable y el nombre no
(hoy "Juarez, Chihuahua", manana lo que decida la desambiguacion).

La comprobacion se hace SIN exponer la clave en la respuesta: el endpoint no la
publica a proposito (`tests/test_importador_ciudades.py:216`), asi que el test
la resuelve por su cuenta contra el catalogo.
"""
import json
import pathlib

import pytest

import app as app_modulo

RAIZ = pathlib.Path(__file__).resolve().parents[1]
CATALOGO = RAIZ / "datos" / "ciudades_mx.json"


@pytest.fixture(scope="module")
def catalogo():
    with CATALOGO.open(encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def payload(monkeypatch):
    """Hoja vacia: con todos los factores en 1.00 la prioridad es el potencial.

    Es la unica forma de comparar el orden del endpoint contra el del catalogo.
    Con metricas de la hoja, la prioridad se separa del potencial por diseno y
    la comparacion dejaria de significar nada.
    """
    monkeypatch.setattr(app_modulo, "get_data", lambda *a, **k: [])
    monkeypatch.setattr(app_modulo, "get_all_respuestas", lambda *a, **k: [])
    app_modulo.app.config["TESTING"] = True
    r = app_modulo.app.test_client().get("/api/importador/ciudades")
    assert r.status_code == 200
    return r.get_json()


class TestElDesempateEsElDelADR:
    def test_con_la_hoja_vacia_los_factores_son_neutros(self, payload):
        """Sostiene a los dos tests de abajo. Si el factor dejara de ser 1.00
        con la hoja vacia, la prioridad se separaria del potencial y comparar
        los dos ordenes no probaria nada."""
        factores = {c["desempeno_nioval"] for c in payload["ciudades"]}
        assert factores == {1.0}, f"factores no neutros con hoja vacia: {sorted(factores)}"

    def test_el_endpoint_entrega_el_mismo_orden_que_el_catalogo(self, payload, catalogo):
        del_endpoint = [c["ciudad"] for c in payload["ciudades"]]
        del_catalogo = [c["nombre"] for c in catalogo]
        difieren = [
            f"#{i + 1} endpoint={a!r} catalogo={b!r}"
            for i, (a, b) in enumerate(zip(del_endpoint, del_catalogo)) if a != b
        ]
        assert difieren == [], (
            f"{len(difieren)} posiciones distintas entre el catalogo y el endpoint: "
            f"{difieren[:6]}"
        )

    def test_los_empates_los_rompe_la_clave_inegi_ascendente(self, payload, catalogo):
        """ADR 7, literal: «a igualdad de prioridad, descendente por numero de
        ferreterias; si persiste, **ascendente por clave INEGI**».

        Se mira grupo por grupo y no el orden global: asi el fallo dice en que
        empate concreto se rompio la regla.
        """
        clave_de = {c["nombre"]: c["clave_inegi"] for c in catalogo}
        malos = []
        grupo, anterior = [], None
        for c in payload["ciudades"] + [None]:
            actual = None if c is None else (c["prioridad"], c["unidades_ferreteras"])
            if actual != anterior:
                if len(grupo) > 1:
                    claves = [clave_de[n] for n in grupo]
                    if claves != sorted(claves):
                        malos.append((anterior, list(zip(grupo, claves))))
                grupo, anterior = [], actual
            if c is not None:
                grupo.append(c["ciudad"])
        assert malos == [], f"{len(malos)} empates mal desempatados: {malos[:3]}"

    def test_la_clave_inegi_sigue_sin_viajar_en_la_respuesta(self, payload):
        """El desempate usa la clave, pero la decision de no publicarla sigue en
        pie: se resuelve en el servidor y no se anade al payload."""
        assert all("clave_inegi" not in c for c in payload["ciudades"])


class TestElOrdenNoDependeDelAzar:
    def test_dos_peticiones_seguidas_dan_el_mismo_orden(self, payload):
        """Determinismo. El problema que el Plan 1 vino a arreglar era un `sort`
        estable sobre una lista de ceros, donde el orden dependia del orden de
        llegada de los datos.

        No se vuelve a parchear `get_data`: `monkeypatch` es de alcance de
        funcion, asi que el parcheo que puso el fixture `payload` sigue activo
        en este mismo test. Repetirlo solo apilaba entradas redundantes en su
        pila de deshacer y sugeria una garantia que no aportaba.
        """
        otra = app_modulo.app.test_client().get("/api/importador/ciudades").get_json()
        assert [c["ciudad"] for c in otra["ciudades"]] == [
            c["ciudad"] for c in payload["ciudades"]
        ]

    def test_la_cabeza_del_ranking_es_la_que_reporta_el_adr(self, payload):
        """El ADR de agosto reporta Puebla, Guadalajara, Leon y Monterrey en la
        cabeza. Bajar el corte a >=10 en T1.3 anadio cola, y esto fija que no
        movio la cabeza: si alguien toca los pesos, se entera aqui."""
        assert [c["ciudad"] for c in payload["ciudades"][:4]] == [
            "Puebla", "Guadalajara", "León", "Monterrey",
        ]
