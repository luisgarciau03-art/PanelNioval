"""`/api/bruce/agregar`: la ruta de ALTA de Bruce, que no tenia ni un test.

Salio del barrido de superficies sin cobertura. **Y de una equivocacion mia que
conviene dejar escrita**, porque es justo el error que el endurecimiento del Plan 5
ya habia cometido y corregido:

Al ver que `/api/bruce/actualizar` escapa formulas y que esta no, di por hecho que
faltaba el escape. Es falso, y el propio repo tenia el test que lo demuestra:

    `append_row` de gspread escribe con **value_input_option='RAW' por defecto**, y
    RAW guarda la cadena TAL CUAL -- "formulas will be rendered as plain". No hay
    nada que interpretar, asi que no hay nada que escapar.

Escapar aqui seria el defecto contrario: el apostrofo se guardaria **como parte del
dato** y el operador lo veria en la celda. `test_las_escrituras_raw_no_se_tocan`
existe exactamente para impedirlo, y puso mi "arreglo" en rojo en cuanto lo aplique.

Lo que estos tests fijan, entonces, no es que escape: es **que siga escribiendo RAW**,
que es de donde viene su seguridad. Si alguien le pone `USER_ENTERED` por parecerse a
las otras rutas, dejaria de ser segura y ahora se nota.
"""
import pytest

import app


class WsEspia:
    """Una hoja que recuerda lo que le mandaron escribir."""

    def __init__(self):
        self.filas = []

    def append_row(self, fila, **kw):
        self.filas.append(list(fila))


@pytest.fixture
def cliente(monkeypatch):
    ws = WsEspia()
    monkeypatch.setattr(app, "get_bruce_ws", lambda: ws)
    monkeypatch.setattr(app, "_cache_pop", lambda _k: None)
    app.app.config["TESTING"] = True
    return app.app.test_client(), ws


class TestLoQueYA_FUNCIONABA:

    def test_un_alta_normal_escribe_su_fila(self, cliente):
        c, ws = cliente

        r = c.post("/api/bruce/agregar", json={
            "Nombre": "Ferretería El Tornillo", "Teléfono": "+52 222 123 4567",
            "Tipo de Interés": "Mayoreo", "NOTA": "Llamar el lunes"})

        assert r.get_json() == {"ok": True}
        assert len(ws.filas) == 1
        assert "Ferretería El Tornillo" in ws.filas[0]

    def test_sin_nombre_no_escribe_nada(self, cliente):
        c, ws = cliente

        r = c.post("/api/bruce/agregar", json={"Teléfono": "+52 222 123 4567"})

        assert r.status_code == 400
        assert ws.filas == [], "se escribio una fila sin nombre"


class TestLoQUE_LA_HACE_SEGURA_ES_RAW:
    """No escapa, y esta bien: escribe RAW. Lo que hay que vigilar es eso.

    `USER_ENTERED` es lo que hace que Sheets interprete `=`, `+`, `-` y `@`. Con RAW
    la cadena entra literal. Cambiar la opcion aqui convertiria en formula viva lo
    que llega de la conversacion que atiende Bruce -- o sea, de un tercero.
    """

    def test_el_alta_escribe_en_RAW(self):
        import ast, pathlib
        arbol = ast.parse(pathlib.Path("app.py").read_text(encoding="utf-8"))
        for nodo in ast.walk(arbol):
            if not (isinstance(nodo, ast.FunctionDef) and nodo.name == "api_bruce_agregar"):
                continue
            llamadas = [n for n in ast.walk(nodo)
                        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                        and n.func.attr in ("append_row", "append_rows", "update", "update_cell")]
            assert llamadas, "la ruta de alta ya no escribe: revisar este test"
            for c in llamadas:
                opciones = [k for k in c.keywords if k.arg == "value_input_option"]
                assert not opciones or getattr(opciones[0].value, "value", "") == "RAW", (
                    "la ruta de alta paso a USER_ENTERED: ahora un `=` de un tercero "
                    "entra como formula viva y hay que escapar")
            return
        pytest.fail("no se encontro `api_bruce_agregar`")

    def test_una_formula_entra_literal_y_sin_apostrofo(self, cliente):
        """La consecuencia observable de escribir RAW, comprobada de verdad."""
        c, ws = cliente

        c.post("/api/bruce/agregar", json={"Nombre": "Ferreteria",
                                           "NOTA": "=IMPORTXML(\"http://x\",\"//a\")"})

        nota = ws.filas[0][-1]
        assert nota.startswith("="), f"se modifico el dato: {nota!r}"
        assert not nota.startswith("'"), (
            "se le metio un apostrofo: con RAW quedaria guardado en la celda")
