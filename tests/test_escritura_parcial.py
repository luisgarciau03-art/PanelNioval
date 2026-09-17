"""Que el contador diga lo que Google confirmo, no lo que le mandamos.

Hallazgo de T3.1 del Plan 3, que quedo anotado como deuda y no como causa:

    `_exportar_a_sheets` termina con `return len(nuevos)` -- **las filas que se
    ENVIARON** a `append_rows`, no las que Google dijo haber anadido. La respuesta
    trae `updates.updatedRows` y se tiraba sin mirarla.

Una escritura parcial -- la API responde 200 y anade menos filas de las pedidas --
haria que el panel publicara de mas **sin lanzar una sola excepcion**. Es el mismo
"20 vs 10" del owner, por otro camino y sin nadie mirando.

Y era invisible para los 80 tests del importador **por construccion**: todos sus
dobles hacen `self.escrituras += len(filas)`, asi que el numero enviado y el
aterrizado no pueden diferir jamas. Un doble honesto no puede reproducir un fallo de
honestidad.

Por eso estos tests estrenan un doble que **SI puede mentir**.
"""
import pytest

import app


class WorksheetQueMiente:
    """Acepta las filas y confirma menos de las que recibio, sin lanzar nada.

    Es lo que hace la API de Sheets en una escritura parcial: responde 200 con un
    `updatedRows` menor. Sin este doble, el defecto no se puede reproducir.
    """

    ENCABEZADO = ["NUM SEMANA", "Nombre", "Ciudad", "Categoria", "Telefono",
                  "", "", "Direccion"] + [""] * 11

    def __init__(self, confirma=None):
        self.filas = [list(self.ENCABEZADO)]
        self.confirma = confirma      # None = confirma todas
        self.enviadas = 0

    def get_all_values(self):
        return [list(f) for f in self.filas]

    def append_rows(self, filas, **kw):
        self.enviadas += len(filas)
        confirmadas = len(filas) if self.confirma is None else self.confirma
        self.filas.extend(filas[:confirmadas])
        return {"updates": {"updatedRows": confirmadas}}


def _fila(i):
    """Una fila con EXACTAMENTE las claves que `_exportar_a_sheets` lee.

    Inventarlas de memoria costo un `KeyError`: las claves reales llevan acento
    (`Calificación`, `Núm. de Reseñas`) y no son las del payload de Places.
    """
    return {
        'Nombre': f'Ferreteria {i}', 'Dirección': f'Calle {i}', 'Teléfono': '',
        'Calificación': 4.5, 'Núm. de Reseñas': 100, 'Google Maps Link': '',
        'Sitio Web': '', 'Horarios': '', 'Estado': '', 'Latitud': 0, 'Longitud': 0,
        'Tamaño': '', 'Tipo Cliente': '', 'CIUDAD': 'CiudadDemo',
    }


class TestLaRespuestaDeGoogleSeMIRA:

    def test_si_confirma_todas_el_conteo_no_cambia(self, monkeypatch):
        """La otra direccion: el camino feliz no puede empezar a reportar de menos."""
        ws = WorksheetQueMiente()
        monkeypatch.setattr(app, 'get_worksheet', lambda _n: ws)

        escritas = app._exportar_a_sheets([_fila(i) for i in range(5)],
                                          'Ferreterías', 'CiudadDemo')

        assert escritas == 5

    def test_una_escritura_PARCIAL_no_se_reporta_como_completa(self, monkeypatch):
        """El defecto: se mandan 5, Google confirma 3, y el panel decia 5."""
        ws = WorksheetQueMiente(confirma=3)
        monkeypatch.setattr(app, 'get_worksheet', lambda _n: ws)

        escritas = app._exportar_a_sheets([_fila(i) for i in range(5)],
                                          'Ferreterías', 'CiudadDemo')

        assert ws.enviadas == 5, "el doble no recibio lo que se esperaba"
        assert escritas == 3, (
            f"se publicaron {escritas} filas cuando Google confirmo 3: "
            "el numero del operador vuelve a no ser el de la hoja")


class TestNoSeROMPE_SI_LA_RESPUESTA_NO_DICE_NADA:
    """La compatibilidad importa: no toda respuesta trae `updatedRows`.

    Si se exigiera, un cambio de la API o un doble antiguo convertirian un camino
    que funciona en un cero. Ante la duda se conserva lo enviado, que es el
    comportamiento de siempre.
    """

    @pytest.mark.parametrize("respuesta", [None, {}, {"updates": {}}, "texto", 42])
    def test_sin_dato_se_conserva_lo_enviado(self, respuesta, monkeypatch):
        class WsMudo(WorksheetQueMiente):
            def append_rows(self, filas, **kw):
                self.enviadas += len(filas)
                self.filas.extend(filas)
                return respuesta

        ws = WsMudo()
        monkeypatch.setattr(app, 'get_worksheet', lambda _n: ws)

        assert app._exportar_a_sheets([_fila(i) for i in range(4)],
                                      'Ferreterías', 'CiudadDemo') == 4


class TestElOperadorSeENTERA:
    """Un numero corregido en silencio es mejor que uno falso, pero no basta."""

    def test_la_discrepancia_se_deja_por_escrito(self, monkeypatch, capsys):
        ws = WorksheetQueMiente(confirma=2)
        monkeypatch.setattr(app, 'get_worksheet', lambda _n: ws)

        app._exportar_a_sheets([_fila(i) for i in range(6)], 'Ferreterías', 'CiudadDemo')

        salida = capsys.readouterr().out
        assert "6" in salida and "2" in salida, (
            f"no se dejo rastro de que Google confirmo menos filas: {salida!r}")


# ═══════════ Lo que encontro el gate de fallos silenciosos ═══════════

class TestElDedupNoSeCONTAMINA:
    """CRITICAL del gate, y ademas mi docstring afirmaba lo contrario.

    `nombres_existentes.update(claves_nuevas)` volcaba las claves ENVIADAS antes de
    saber cuantas confirmo Google. Ese conjunto lo comparten todas las categorias de
    la corrida: un negocio perdido en la escritura parcial de "Ferreterias" quedaba
    marcado como "ya en la hoja" y la categoria siguiente lo saltaba **sin haberse
    escrito nunca**.

    Y no hay riesgo de duplicar por no marcarlas: `_exportar_a_sheets` RELEE la hoja
    en cada llamada, asi que las filas que si aterrizaron vuelven por `frescas`.
    """

    def test_una_escritura_parcial_no_marca_como_presentes_las_que_faltan(self, monkeypatch):
        ws = WorksheetQueMiente(confirma=2)
        monkeypatch.setattr(app, 'get_worksheet', lambda _n: ws)
        compartidas = set()

        app._exportar_a_sheets([_fila(i) for i in range(5)], 'Ferreterías',
                               'CiudadDemo', claves_existentes=compartidas)

        # Las 2 confirmadas si estan (vuelven al releer la hoja); las 3 perdidas NO.
        marcadas = {c for c in compartidas if c.startswith('Ferreteria ')}
        assert len(marcadas) <= 2, (
            f"se marcaron {len(marcadas)} claves como presentes y Google confirmo 2: "
            "la categoria siguiente saltaria negocios que nunca se escribieron")

    def test_si_confirma_todas_SI_se_marcan(self, monkeypatch):
        """La otra direccion: el camino feliz no puede dejar de deduplicar."""
        ws = WorksheetQueMiente()
        monkeypatch.setattr(app, 'get_worksheet', lambda _n: ws)
        compartidas = set()

        app._exportar_a_sheets([_fila(i) for i in range(4)], 'Ferreterías',
                               'CiudadDemo', claves_existentes=compartidas)

        assert len({c for c in compartidas if c.startswith('Ferreteria ')}) == 4


class TestElAvisoLLEGA_A_DONDE_MIRA_EL_OPERADOR:
    """HIGH del gate: `print()` va al stdout del contenedor, donde nadie mira.

    Todas las demas incidencias del importador van a `_import_job['log']`, que es lo
    que el endpoint de estado publica y la pantalla muestra. Dejar justo esta fuera
    reabre, en el canal de aviso, la misma clase de fallo que el arreglo cierra.
    """

    def test_la_escritura_parcial_queda_en_el_log_de_la_corrida(self, monkeypatch):
        ws = WorksheetQueMiente(confirma=1)
        monkeypatch.setattr(app, 'get_worksheet', lambda _n: ws)
        app._import_job = app._nuevo_import_job('CiudadDemo', status='running')

        app._exportar_a_sheets([_fila(i) for i in range(4)], 'Ferreterías', 'CiudadDemo')

        log = ' '.join(app._import_job['log'])
        assert 'parcial' in log.lower(), f"no hay rastro en el log: {app._import_job['log']!r}"
        assert '4' in log and '1' in log


class TestUnaRESPUESTA_MUDA_TAMPOCO_ES_MUDA:
    """HIGH del gate: el camino `except` era totalmente silencioso.

    Si la forma de la respuesta cambia -- otra version de gspread, un 200 raro --
    el codigo vuelve a publicar lo enviado sin verificar, que es el bug que este
    arreglo existe para cerrar, y esta vez sin ni siquiera el aviso.
    """

    def test_deja_rastro_de_que_no_se_pudo_verificar(self, monkeypatch, capsys):
        class WsMudo(WorksheetQueMiente):
            def append_rows(self, filas, **kw):
                self.filas.extend(filas)
                return {"algo": "con otra forma"}

        monkeypatch.setattr(app, 'get_worksheet', lambda _n: WsMudo())
        app._import_job = app._nuevo_import_job('CiudadDemo', status='running')

        escritas = app._exportar_a_sheets([_fila(i) for i in range(3)],
                                          'Ferreterías', 'CiudadDemo')

        assert escritas == 3, "ante la duda se conserva lo enviado"
        rastro = capsys.readouterr().out + ' '.join(app._import_job['log'])
        assert 'verific' in rastro.lower(), (
            f"se asumio sin verificar y sin decirlo: {rastro!r}")
