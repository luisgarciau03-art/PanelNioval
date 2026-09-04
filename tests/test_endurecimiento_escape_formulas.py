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
    def test_sin_opcion_explicita_resuelve_a_raw(self, metodo):
        """`update`/`batch_update` sin opcion mandan RAW, no USER_ENTERED.

        La primera version de este test afirmaba lo contrario y PASABA, porque
        comprobaba que la cadena "user_entered" apareciera en el fuente de
        gspread. Aparece — pero en la rama que exige `raw=False`, que nadie
        pasa. Con los defectos reales (`raw: bool = True`) gana RAW.

        Es el ejemplo exacto de un test que pasa por la razon equivocada: leia
        el codigo en vez de EJECUTARLO. Ahora se comprueba el valor que sale
        por la peticion, con una worksheet falsa y sin red.
        """
        assert inspect.signature(getattr(Worksheet, metodo)).parameters[
            "value_input_option"].default is None
        assert _opcion_que_manda_gspread(metodo) == "RAW", (
            f"{metodo} ya no resuelve a RAW sin opcion explicita: la "
            "clasificacion de _opcion_efectiva en CE5 deja de ser valida"
        )

    @pytest.mark.parametrize("metodo", ["insert_row", "insert_rows"])
    def test_insert_por_defecto_es_raw(self, metodo):
        """No se usan hoy en `app.py`, pero estan en METODOS_ESCRITURA. Si
        alguien anade una, debe clasificarse como RAW: darla por USER_ENTERED
        haria que CE5 exigiera escaparla, y escapar una RAW corrompe el dato."""
        p = inspect.signature(getattr(Worksheet, metodo)).parameters["value_input_option"]
        assert str(p.default).upper().endswith("RAW")


def _opcion_que_manda_gspread(metodo: str) -> str:
    """El `valueInputOption` que sale de verdad por la peticion, ejecutando.

    Sin red: se construye una Worksheet con un cliente falso que captura los
    parametros. Es la unica forma honesta de fijar este invariante; leer el
    fuente ya dio una respuesta equivocada una vez.
    """
    capturado = {}

    class ClienteFalso:
        def values_update(self, sid, rango, params=None, body=None):
            capturado["opcion"] = params.get("valueInputOption")
            return {}

        def values_batch_update(self, sid, body):
            capturado["opcion"] = body.get("valueInputOption")
            return {}

    ws = Worksheet.__new__(Worksheet)
    ws.client = ClienteFalso()
    ws._properties = {"title": "H", "sheetId": 0}
    ws.spreadsheet_id = "X"

    if metodo == "update":
        ws.update([["=SUM(A1)"]], "A1")
    else:
        ws.batch_update([{"range": "A1", "values": [["=SUM(A1)"]]}])
    return str(capturado["opcion"]).upper().rsplit(".", 1)[-1].strip("'>")


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
        if kw.arg == "value_input_option":
            # Pasado como variable: no se puede resolver estaticamente. Se
            # asume el caso que exige escape, que es el error en la direccion
            # segura (escapar de mas se nota; escapar de menos, no).
            return "USER_ENTERED"
    # Sin opcion explicita. RAW para todo menos update_cell/update_acell, que
    # NO admiten el parametro y lo fijan a USER_ENTERED en su propio cuerpo.
    #
    # Esta rama decia USER_ENTERED para update/batch_update/insert_*, y era al
    # reves: `raw: bool = True` gana cuando no hay opcion. Lo fija por ejecucion
    # TestSupuestosSobreGspread. Importa la direccion del error: clasificar una
    # RAW como USER_ENTERED haria que CE5 exigiera escaparla, y escapar una RAW
    # guarda el apostrofo en la celda — el guarda forzaria la corrupcion que el
    # resto de la suite dice evitar.
    if nodo.func.attr in ("update_cell", "update_acell"):
        return "USER_ENTERED"
    return "RAW"


ESCAPES = {"_escapar_formula", "_valor_para_celda"}


def _hay_escape(nodo) -> bool:
    return any(
        isinstance(n, ast.Name) and n.id in ESCAPES for n in ast.walk(nodo)
    )


def _expresiones_de_celda(llamada, fn):
    """Las expresiones que acaban DENTRO de una celda en esta llamada.

    La version anterior preguntaba si la FUNCION mencionaba el escape en
    cualquier parte, y eso lo enganaba un senuelo: bastaba con escapar una
    variable que no se escribe para que la funcion entera contara como
    protegida. En `_sheet_update_row` y `api_bruce_actualizar`, que construyen
    `updates` en un bucle, ese punto ciego es facil de pisar sin querer.

    Ahora se resuelve por sitio: se toma el argumento que lleva los valores y,
    si es un nombre (el acumulador `updates`), se buscan los `.append(...)` de
    ese nombre dentro de la funcion.
    """
    metodo = llamada.func.attr
    if metodo in ("update_cell", "update_acell"):
        return llamada.args[2:3]           # (fila, col, VALOR)
    if not llamada.args:
        return []
    primero = llamada.args[0]
    if not isinstance(primero, ast.Name) or fn is None:
        return [primero]
    # Acumulador: seguir los append() de esa lista dentro de la funcion.
    acumulado = []
    for n in ast.walk(fn):
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and n.func.attr == "append"
                and isinstance(n.func.value, ast.Name)
                and n.func.value.id == primero.id):
            acumulado.extend(n.args)
    return acumulado or [primero]


def _reasignaciones_que_escapan(llamada, fn) -> bool:
    """¿Se reescribe entera la lista aplicando el escape antes de escribirla?

    Es el patron de `_exportar_a_sheets`: las filas se acumulan crudas con
    `append` y justo antes de escribir se hace
    `nuevos = [[_escapar_formula(v) for v in fila] for fila in nuevos]`.
    Siguiendo solo los `append` esa funcion salia como desprotegida, que es un
    falso positivo: el escape se aplica a TODO en la reasignacion.

    Se exige que la asignacion apunte a ESE nombre, no a cualquiera, para que
    un senuelo sobre otra variable no la marque como protegida.
    """
    if not llamada.args or not isinstance(llamada.args[0], ast.Name) or fn is None:
        return False
    objetivo = llamada.args[0].id
    for n in ast.walk(fn):
        if isinstance(n, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == objetivo for t in n.targets
        ):
            if _hay_escape(n.value):
                return True
    return False


def _escapa_lo_que_escribe(llamada, fn) -> bool:
    if _reasignaciones_que_escapan(llamada, fn):
        return True
    exprs = _expresiones_de_celda(llamada, fn)
    return bool(exprs) and all(_hay_escape(e) for e in exprs)


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
        usa_escape = _escapa_lo_que_escribe(nodo, fn)
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


# ───────────────── Los hallazgos de los reviewers, fijados ─────────────────

class TestBypassDelEscape:
    """security-reviewer, HIGH: el escape miraba `valor[:1]` sin recortar.

    Un espacio delante del operador lo evadia. Excel recorta ese espacio al
    importar el CSV y ejecuta la formula igual, asi que era un bypass real del
    control, no una sutileza.
    """

    @pytest.mark.parametrize("prefijo", [
        " ", "  ", "\t", "\n", "\r\n", "\v", "\f",
        "﻿",   # BOM
        "​",   # espacio de ancho cero
        "‌", "‍", "⁠",
    ])
    @pytest.mark.parametrize("operador", ["=", "+", "-", "@"])
    def test_un_blanco_delante_no_evade_el_escape(self, prefijo, operador):
        valor = f"{prefijo}{operador}SUM(A1:A9)"
        assert app._escapar_formula(valor) == "'" + valor

    def test_el_apostrofo_va_sobre_el_valor_original(self):
        """No se recorta el dato: los espacios de delante son del usuario."""
        assert app._escapar_formula("  =1+1") == "'  =1+1"

    def test_un_texto_normal_con_espacio_delante_sigue_intacto(self):
        assert app._escapar_formula("  Ferreteria Chavez") == "  Ferreteria Chavez"


class TestNumerosNoSeVuelvenTexto:
    """security-reviewer, MEDIUM: regresion introducida por T5.2.

    Envolver en `str()` ANTES de escapar anulaba el paso limpio de numeros que
    `_escapar_formula` tenia por diseno, y un -50 legitimo acababa guardado
    como texto "'-50", rompiendo en silencio cualquier SUM de esa columna.
    """

    @pytest.mark.parametrize("numero", [-50, -99.1332, 0, 4.5, 100])
    def test_un_numero_sigue_siendo_numero(self, numero):
        r = app._valor_para_celda(numero)
        assert r == numero and isinstance(r, type(numero))

    def test_un_booleano_se_escribe_como_texto(self):
        """bool es subclase de int en Python; escribir True como numero en la
        hoja no es lo que espera nadie."""
        assert app._valor_para_celda(True) == "True"

    @pytest.mark.parametrize("formula", FORMULAS)
    def test_una_formula_en_texto_sigue_escapandose(self, formula):
        assert app._valor_para_celda(formula) == "'" + formula

    def test_un_telefono_con_lada_se_escapa_como_texto(self):
        """Empieza por '+', asi que se escapa. Es el efecto deseado: evita que
        Sheets se coma el '+' al interpretarlo."""
        assert app._valor_para_celda("+52 81 1234 5678") == "'+52 81 1234 5678"  # barrido-ok: telefono sintetico de prueba


class TestElGuardaNoSeDejaEnganar:
    """silent-failure-hunter, HIGH: `usa_escape` miraba la FUNCION entera.

    Bastaba con que `_escapar_formula` apareciera en cualquier parte del cuerpo
    —sobre una variable que nunca llega a la celda— para que la funcion contara
    como protegida.
    """

    def _clasificar(self, fuente):
        arbol = ast.parse(fuente)
        fn = arbol.body[0]
        llamada = next(
            n for n in ast.walk(fn)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and n.func.attr in METODOS_ESCRITURA
        )
        return _escapa_lo_que_escribe(llamada, fn)

    def test_un_senuelo_no_cuenta_como_proteccion(self):
        """El caso exacto que el reviewer construyo para romper el guarda."""
        assert not self._clasificar(
            "def f(ws, valor):\n"
            "    decoy = _escapar_formula('otra cosa')\n"
            "    ws.batch_update([{'range': 'A1', 'values': [[str(valor)]]}],\n"
            "                    value_input_option='USER_ENTERED')\n"
        )

    def test_escapar_el_valor_que_se_escribe_si_cuenta(self):
        assert self._clasificar(
            "def f(ws, valor):\n"
            "    ws.batch_update([{'range': 'A1', 'values': [[_escapar_formula(valor)]]}],\n"
            "                    value_input_option='USER_ENTERED')\n"
        )

    def test_el_acumulador_se_sigue_por_sus_append(self):
        assert self._clasificar(
            "def f(ws, campos):\n"
            "    updates = []\n"
            "    for v in campos:\n"
            "        updates.append({'range': 'A1', 'values': [[_valor_para_celda(v)]]})\n"
            "    ws.batch_update(updates, value_input_option='USER_ENTERED')\n"
        )

    def test_un_append_sin_escape_entre_varios_lo_delata(self):
        """El punto ciego concreto: una funcion que escapa un campo y deja otro
        sin escapar seguia contando como protegida."""
        assert not self._clasificar(
            "def f(ws, campos, especial):\n"
            "    updates = []\n"
            "    for v in campos:\n"
            "        updates.append({'range': 'A1', 'values': [[_escapar_formula(v)]]})\n"
            "    updates.append({'range': 'B1', 'values': [[str(especial)]]})\n"
            "    ws.batch_update(updates, value_input_option='USER_ENTERED')\n"
        )

    def test_la_reasignacion_que_escapa_entera_si_cuenta(self):
        """Patron real de `_exportar_a_sheets`: acumula crudo y escapa todo al
        final. Seguir solo los append lo daba por desprotegido."""
        assert self._clasificar(
            "def f(ws, filas):\n"
            "    nuevos = []\n"
            "    for fila in filas:\n"
            "        nuevos.append(fila)\n"
            "    nuevos = [[_escapar_formula(v) for v in fila] for fila in nuevos]\n"
            "    ws.append_rows(nuevos, value_input_option='USER_ENTERED')\n"
        )


class TestClasificacionPorDefecto:
    """silent-failure-hunter, HIGH: `_opcion_efectiva` daba USER_ENTERED por
    defecto a update/batch_update/insert_*, y la realidad es RAW.

    La direccion del error importaba: clasificar una RAW como USER_ENTERED hace
    que CE5 EXIJA escaparla, y escapar una RAW guarda el apostrofo en la celda.
    El guarda habria forzado la corrupcion que el resto de la suite evita.
    """

    def _opcion(self, fuente):
        llamada = next(
            n for n in ast.walk(ast.parse(fuente))
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        )
        return _opcion_efectiva(llamada)

    @pytest.mark.parametrize("metodo", [
        "update", "batch_update", "append_row", "append_rows",
        "insert_row", "insert_rows",
    ])
    def test_sin_opcion_explicita_se_clasifica_raw(self, metodo):
        assert self._opcion(f"ws.{metodo}(datos)") == "RAW"

    @pytest.mark.parametrize("metodo", ["update_cell", "update_acell"])
    def test_update_cell_es_user_entered_aunque_no_lo_diga(self, metodo):
        """No admite el parametro: lo fija en su propio cuerpo. Leyendo app.py
        parece el caso seguro y es el contrario."""
        assert self._opcion(f"ws.{metodo}(1, 2, valor)") == "USER_ENTERED"

    def test_una_opcion_por_variable_se_asume_user_entered(self):
        """No se puede resolver estaticamente: se asume el caso que exige
        escape, que es el error en la direccion segura."""
        assert self._opcion("ws.batch_update(d, value_input_option=opcion)") == "USER_ENTERED"
