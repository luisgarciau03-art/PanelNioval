"""Plan 5 · T5.2 (M14) — escapado de formulas en TODAS las escrituras a Sheets.

`_escapar_formula` se definia en `app.py` y se aplicaba en UN solo sitio
(`_exportar_a_sheets`, el importador). El resto de rutas metia texto de usuario
tal cual, y un valor que empiece por '=', '+', '-' o '@' lo interpreta Sheets
como formula.

No es hipotetico: la proteccion se construyo porque el riesgo se materializo con
la ferreteria "+ Mas Seguro Distribuidora Ferretera", cuya celda mostraba
#ERROR! en vez del nombre al llamar.

Nombre del archivo: NO se usa `test_plan5_*`. Ese prefijo ya lo ocupa
`tests/test_plan5_operacion.py`, del Plan 5 de la tanda 2026-08-13, que ademas
ya trae una clase `TestEscapeFormula` sobre la funcion en si. Aqui se prueba la
COBERTURA de las escrituras, no la funcion.
"""
import inspect

import pytest

from gspread.worksheet import Worksheet


# ───────────────── Los defectos de gspread, fijados como invariante ─────────────────

class TestSupuestosSobreGspread:
    """T5.2 decide DONDE escapar a partir del `value_input_option` efectivo, y
    ese dato no esta en `app.py`: esta en los defectos de gspread.

    Un supuesto sobre una libreria de terceros que nadie comprueba es una bomba
    de relojeria: `requirements.txt` pide `gspread>=5.12.0`, o sea que la version
    instalada puede cambiar sin tocar una linea de este repo. Si cambian estos
    defectos, el escape deja de aplicarse donde hace falta —o se aplica donde
    corrompe— y NADA lo avisaria. Estos tests convierten el supuesto en algo que
    se rompe ruidosamente.

    Medido con gspread 6.2.1.
    """

    def test_append_row_por_defecto_es_raw(self):
        """RAW no parsea: un '=' escrito asi se guarda como texto y NO es
        inyeccion. Por eso estas escrituras no necesitan escape."""
        p = inspect.signature(Worksheet.append_row).parameters["value_input_option"]
        assert str(p.default).upper().endswith("RAW"), (
            f"append_row ya no usa RAW por defecto, sino {p.default!r}: "
            "revisa que escrituras necesitan escape en T5.2"
        )

    def test_append_rows_por_defecto_es_raw(self):
        p = inspect.signature(Worksheet.append_rows).parameters["value_input_option"]
        assert str(p.default).upper().endswith("RAW")

    def test_update_cell_es_siempre_user_entered(self):
        """`update_cell` NO acepta `value_input_option`: lo fija a USER_ENTERED
        en su propio cuerpo. Es la trampa mas facil de pasar por alto, porque
        leyendo `app.py` no se ve ninguna opcion y parece el caso seguro.
        Cualquier `update_cell` con texto de usuario es un punto de inyeccion.
        """
        assert "value_input_option" not in inspect.signature(Worksheet.update_cell).parameters
        cuerpo = inspect.getsource(Worksheet.update_cell)
        assert "user_entered" in cuerpo, (
            "update_cell dejo de fijar USER_ENTERED: revisa T5.2"
        )

    @pytest.mark.parametrize("metodo", ["update", "batch_update"])
    def test_sin_opcion_explicita_es_user_entered(self, metodo):
        """`value_input_option=None` NO significa "el defecto seguro": gspread
        lo resuelve a USER_ENTERED salvo que se pase `raw=True`."""
        f = getattr(Worksheet, metodo)
        assert inspect.signature(f).parameters["value_input_option"].default is None
        cuerpo = inspect.getsource(f)
        assert "if not value_input_option:" in cuerpo
        assert "user_entered" in cuerpo, (
            f"{metodo} ya no cae en USER_ENTERED sin opcion: revisa T5.2"
        )


# ───────────────── CE5: el inventario de escrituras, comprobado solo ─────────────────

import ast
import pathlib

RAIZ = pathlib.Path(__file__).resolve().parents[1]

METODOS_ESCRITURA = {
    "append_row", "append_rows", "update", "update_cell", "update_acell",
    "batch_update", "insert_row", "insert_rows",
}

# Receptores que SI son worksheets de gspread en app.py.
RECEPTORES_WORKSHEET = {"ws", "wsc"}

# Receptores que casan con el patron pero NO son hojas: `.update(` es tambien
# metodo de dict y de set. Medido: de 24 coincidencias del patron ingenuo, 8 son
# de estos. Estan enumerados a proposito para que un receptor NUEVO y
# desconocido rompa el test en vez de colarse como "no es una hoja".
RECEPTORES_NO_SON_HOJA = {
    "config",              # app.config.update  (Flask)
    "all_keys",            # set
    "claves_existentes",   # set
    "nombres_existentes",  # set
    "cache_places",        # dict
    "_cache",              # dict (_cache.clear())
    "cache",               # dict
}

# Escrituras USER_ENTERED que NO necesitan escape, con el motivo. Una excepcion
# sin motivo escrito es un agujero; por eso van con nombre de funcion y razon.
SIN_ESCAPE_JUSTIFICADO = {
    # Codigo muerto: ningun llamador en todo el repo (la escritura de 'Llamado'
    # salio del flujo en e84c1a0). Ademas escribe una constante literal, que no
    # puede empezar por '=' sin que alguien edite el fuente.
    "marcar_contacto_procesado",
}


def _receptor(nodo):
    """Nombre del objeto sobre el que se llama el metodo, o None."""
    valor = nodo.func.value
    if isinstance(valor, ast.Name):
        return valor.id
    if isinstance(valor, ast.Attribute):
        return valor.attr
    return None


def _opcion_efectiva(nodo):
    """El `value_input_option` que acaba usando la llamada.

    Los defectos NO son los que uno supondria y estan fijados en
    TestSupuestosSobreGspread: `update_cell` fuerza USER_ENTERED sin admitir el
    parametro, y `update`/`batch_update` caen en USER_ENTERED si no se les pasa.
    """
    for kw in nodo.keywords:
        if kw.arg == "value_input_option" and isinstance(kw.value, ast.Constant):
            return str(kw.value.value).upper()
    metodo = nodo.func.attr
    if metodo in ("append_row", "append_rows"):
        return "RAW"
    return "USER_ENTERED"


def _funciones_con_escrituras():
    """[(funcion, metodo, linea, opcion, usa_escape)] de todo app.py."""
    arbol = ast.parse((RAIZ / "app.py").read_text(encoding="utf-8"))
    padres = {}
    for nodo in ast.walk(arbol):
        for hijo in ast.iter_child_nodes(nodo):
            padres[hijo] = nodo

    def funcion_de(nodo):
        actual = padres.get(nodo)
        while actual is not None:
            if isinstance(actual, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return actual
            actual = padres.get(actual)
        return None

    salida = []
    for nodo in ast.walk(arbol):
        if not (isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Attribute)):
            continue
        if nodo.func.attr not in METODOS_ESCRITURA:
            continue
        receptor = _receptor(nodo)
        if receptor in RECEPTORES_NO_SON_HOJA:
            continue
        assert receptor in RECEPTORES_WORKSHEET, (
            f"receptor desconocido '{receptor}' en app.py:{nodo.lineno} "
            f"({nodo.func.attr}). Clasificalo: o es una worksheet y necesita "
            f"escape, o no lo es y va en RECEPTORES_NO_SON_HOJA con su motivo. "
            f"No se puede dejar sin decidir."
        )
        fn = funcion_de(nodo)
        nombre = fn.name if fn else "<modulo>"
        usa_escape = fn is not None and any(
            isinstance(n, ast.Name) and n.id == "_escapar_formula"
            for n in ast.walk(fn)
        )
        salida.append((nombre, nodo.func.attr, nodo.lineno, _opcion_efectiva(nodo), usa_escape))
    return salida


class TestInventarioDeEscrituras:
    """CE5 — el barrido de escrituras es exhaustivo y se comprueba solo.

    No es una lista escrita a mano: recorre el AST de `app.py`. Una escritura
    nueva sin escape rompe el test, y un receptor que no este clasificado
    tambien.
    """

    def test_toda_escritura_user_entered_pasa_por_el_escape(self):
        sin_proteger = [
            (fn, m, ln) for fn, m, ln, opcion, escapa in _funciones_con_escrituras()
            if opcion == "USER_ENTERED" and not escapa and fn not in SIN_ESCAPE_JUSTIFICADO
        ]
        assert sin_proteger == [], (
            "escrituras USER_ENTERED sin escapar formulas: "
            + "; ".join(f"{fn} ({m}) en app.py:{ln}" for fn, m, ln in sin_proteger)
        )

    def test_el_inventario_encuentra_las_escrituras_conocidas(self):
        """Direccion util: si el barrido no ve lo que sabemos que esta, su cero
        no vale nada. 17 escrituras reales, medidas en el inventario de T5.2."""
        escrituras = _funciones_con_escrituras()
        assert len(escrituras) >= 15, f"solo encontro {len(escrituras)} escrituras"
        funciones = {fn for fn, _, _, _, _ in escrituras}
        for esperada in ("_exportar_a_sheets", "_sheet_update_row",
                         "api_bruce_actualizar", "api_mensajes_update",
                         "guardar_respuesta_formulario"):
            assert esperada in funciones, f"el barrido no vio {esperada}"

    def test_las_escrituras_raw_no_se_tocan(self):
        """La direccion contraria, y NO es simetria decorativa.

        RAW guarda la cadena tal cual ("formulas will be rendered as plain",
        doc de gspread), asi que ya es segura. Meterle el apostrofo del escape
        lo guardaria COMO PARTE DEL DATO, y se veria en la celda. El plan decia
        que pasar todo por el escape "no hace dano": es falso para RAW.
        """
        raw_con_escape = [
            (fn, ln) for fn, _, ln, opcion, escapa in _funciones_con_escrituras()
            if opcion == "RAW" and escapa and fn != "_exportar_a_sheets"
        ]
        assert raw_con_escape == [], (
            "escrituras RAW en funciones que escapan: el apostrofo quedaria "
            f"guardado en la celda: {raw_con_escape}"
        )


# ───────────────── Comportamiento real, ruta por ruta ─────────────────

from unittest.mock import MagicMock

import app

FORMULAS = ["=SUM(A1:A9)", "+Ferreteria del Norte", "-Descuento", "@arroba"]


@pytest.fixture
def client():
    app.app.config["TESTING"] = True
    return app.app.test_client()


def _valores_escritos(ws):
    """Todos los valores de celda que se mandaron en un batch_update."""
    args, _ = ws.batch_update.call_args
    return [u["values"][0][0] for u in args[0]]


class TestSeguimientoUpdate:
    """`/api/seguimiento/update` escribe con USER_ENTERED y sin allowlist:
    cualquier clave del body que coincida con un encabezado llega a una celda."""

    def _ws(self):
        ws = MagicMock()
        ws.row_values.return_value = ["Nombre", "Nota"]
        return ws

    @pytest.mark.parametrize("formula", FORMULAS)
    def test_una_formula_llega_escapada(self, client, monkeypatch, formula):
        ws = self._ws()
        monkeypatch.setattr(app, "get_worksheet", lambda clave: ws)
        r = client.post("/api/seguimiento/update", json={"_row": 5, "Nota": formula})
        assert r.status_code == 200
        assert _valores_escritos(ws) == ["'" + formula]

    def test_un_valor_normal_no_se_altera(self, client, monkeypatch):
        """El escape que ensucia datos legitimos es peor que no tenerlo."""
        ws = self._ws()
        monkeypatch.setattr(app, "get_worksheet", lambda clave: ws)
        client.post("/api/seguimiento/update", json={"_row": 5, "Nota": "Ferreteria Chavez"})
        assert _valores_escritos(ws) == ["Ferreteria Chavez"]


class TestBruceActualizar:
    def _ws(self):
        ws = MagicMock()
        ws.row_values.return_value = ["Nombre", "NOTA"]
        return ws

    @pytest.mark.parametrize("formula", FORMULAS)
    def test_una_formula_llega_escapada(self, client, monkeypatch, formula):
        ws = self._ws()
        monkeypatch.setattr(app, "get_bruce_ws", lambda: ws)
        r = client.post("/api/bruce/actualizar", json={"_row": 3, "NOTA": formula})
        assert r.status_code == 200
        assert _valores_escritos(ws) == ["'" + formula]

    def test_un_valor_normal_no_se_altera(self, client, monkeypatch):
        ws = self._ws()
        monkeypatch.setattr(app, "get_bruce_ws", lambda: ws)
        client.post("/api/bruce/actualizar", json={"_row": 3, "NOTA": "Llamar el lunes"})
        assert _valores_escritos(ws) == ["Llamar el lunes"]


class TestVentasUpdatePagoUrl:
    """`update_cell` no admite `value_input_option`: siempre USER_ENTERED."""

    def _ws(self):
        ws = MagicMock()
        ws.get_all_values.return_value = [["Num Factura", "PAGO"], ["F-1", ""]]
        return ws

    def test_una_url_con_formula_llega_escapada(self, client, monkeypatch):
        ws = self._ws()
        monkeypatch.setattr(app, "get_worksheet", lambda clave: ws)
        r = client.post("/api/ventas/update-pago-url",
                        data={"num_factura": "F-1", "url_existente": "=HYPERLINK(\"x\")"})
        assert r.status_code == 200
        assert ws.update_cell.call_args[0][2] == "'=HYPERLINK(\"x\")"

    def test_una_url_normal_no_se_altera(self, client, monkeypatch):
        ws = self._ws()
        monkeypatch.setattr(app, "get_worksheet", lambda clave: ws)
        client.post("/api/ventas/update-pago-url",
                    data={"num_factura": "F-1", "url_existente": "https://drive.google.com/x"})
        assert ws.update_cell.call_args[0][2] == "https://drive.google.com/x"


class TestMensajesUpdate:
    """Ademas del escape, esta ruta arrastraba un bug de firma de gspread.

    Hasta 5.x era `update(range_name, values)`; en 6.x es `update(values,
    range_name)`. `app.py` usaba el orden viejo, asi que con la version
    instalada pasaba la celda como valores y la lista como rango.
    """

    def _ws_con_firma_de_gspread_6(self, capturado):
        """Worksheet falsa que impone la firma REAL de gspread 6.

        Un MagicMock aceptaria cualquier orden y el test no detectaria nada:
        seria un test que pasa con y sin el arreglo.
        """
        class WS:
            def update(self, values, range_name=None, **kw):
                assert isinstance(values, list) and isinstance(values[0], list), (
                    f"primer argumento debe ser los VALORES, llego {values!r}"
                )
                assert isinstance(range_name, str), (
                    f"segundo argumento debe ser el RANGO A1, llego {range_name!r}"
                )
                capturado["values"] = values
                capturado["range"] = range_name
        return WS()

    @pytest.mark.parametrize("formula", FORMULAS)
    def test_una_formula_llega_escapada(self, client, monkeypatch, formula):
        capturado = {}
        monkeypatch.setattr(app, "get_worksheet",
                            lambda clave: self._ws_con_firma_de_gspread_6(capturado))
        r = client.post("/api/mensajes/update",
                        json={"_row": 2, "_col": 3, "Contenido": formula})
        assert r.status_code == 200, r.get_json()
        assert capturado["values"] == [["'" + formula]]

    def test_usa_el_orden_de_argumentos_de_gspread_6(self, client, monkeypatch):
        """Con el orden viejo la worksheet falsa revienta y la ruta da 500."""
        capturado = {}
        monkeypatch.setattr(app, "get_worksheet",
                            lambda clave: self._ws_con_firma_de_gspread_6(capturado))
        r = client.post("/api/mensajes/update",
                        json={"_row": 2, "_col": 3, "Contenido": "hola"})
        assert r.status_code == 200, r.get_json()
        assert capturado["range"] == "C2"
        assert capturado["values"] == [["hola"]]
