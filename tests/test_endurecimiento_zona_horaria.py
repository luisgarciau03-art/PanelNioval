"""Plan 5 · T5.3 (M2) — zona horaria explicita.

El contenedor corre en UTC (`python:3.11-slim` sin `TZ`) y las seis
`datetime.now()` de `app.py` no llevan `tzinfo`. Mexico es UTC-6, asi que
**todo lo capturado despues de las 18:00 hora local se guarda con la fecha del
dia siguiente**, y `isocalendar()[1]` puede caer en la semana equivocada — que
es justo el campo por el que agrupa la grafica "Contactos por Semana".

Es un bug de datos, no cosmetico.

Nombre del archivo: NO se usa `test_plan5_*` a proposito. Ese prefijo ya lo
ocupa `tests/test_plan5_operacion.py`, que es del Plan 5 de la tanda
2026-08-13 ("Operacion Railway"), otro plan distinto.
"""
import io
import pathlib
import tokenize
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

# No se importa `app` ni `worker_catalogo`: este archivo comprueba el reloj
# compartido (`nucleo_catalogo`) y el resto lo audita sobre el fuente. Importar
# `app` aqui costaria el arranque en frio sin aportar nada.
import nucleo_catalogo as nc

RAIZ = pathlib.Path(__file__).resolve().parents[1]


# ───────────────────────── utilidades del barrido ─────────────────────────

# Que tokens se borran antes de buscar el patron. FSTRING_MIDDLE solo existe en
# 3.12+ (PEP 701): ahi las partes literales de un f-string son tokens propios,
# no STRING, asi que sin incluirlo el guarda marcaba el texto literal de un
# f-string que solo MENCIONA el patron. En 3.11 no existe y no hace falta,
# porque el f-string entero ya viene como un unico STRING.
#
# Las dos versiones importan de verdad: el CI y el Dockerfile corren 3.11 y la
# maquina de desarrollo 3.14. Un guarda afinado para una sola de las dos miente
# en la otra, y la que decide el merge es la de CI.
_TIPOS_BORRABLES = {tokenize.COMMENT, tokenize.STRING}
if hasattr(tokenize, "FSTRING_MIDDLE"):
    _TIPOS_BORRABLES.add(tokenize.FSTRING_MIDDLE)


def solo_codigo(ruta: pathlib.Path) -> str:
    """Devuelve el fuente con comentarios Y cadenas borrados, sin mover lineas.

    Existe por un fallo repetido en este proyecto: un guarda que busca el patron
    prohibido en el ARCHIVO ENTERO lo encuentra en la documentacion que explica
    por que se retiro, y se dispara solo.

    Se borran las dos cosas, y por experiencia directa: la primera version de
    este helper quitaba unicamente los comentarios, y el guarda fallo sobre el
    DOCSTRING de `nucleo_catalogo.ahora_mexico()`, que dice "no usar
    datetime.now() a secas". Un docstring es un token STRING, no COMMENT.

    Se usa `tokenize` en vez de partir por '#' porque un '#' dentro de una
    cadena no abre un comentario.
    """
    texto = ruta.read_text(encoding="utf-8")
    inicio_de_linea = [0]
    for linea in texto.splitlines(keepends=True):
        inicio_de_linea.append(inicio_de_linea[-1] + len(linea))

    def absoluto(pos):
        fila, col = pos
        return inicio_de_linea[fila - 1] + col

    salida = list(texto)
    for tok in tokenize.generate_tokens(io.StringIO(texto).readline):
        if tok.type not in _TIPOS_BORRABLES:
            continue
        i, f = absoluto(tok.start), absoluto(tok.end)
        for j, c in enumerate(_enmascarar(tok.string), start=i):
            if j < len(salida):
                salida[j] = c
    return "".join(salida)


def _es_fstring(texto: str) -> bool:
    prefijo = texto[: len(texto) - len(texto.lstrip("fFrRbBuU"))]
    return "f" in prefijo.lower()


def _enmascarar(texto: str) -> str:
    """Borra el token conservando longitud, saltos de linea y —si es f-string—
    las expresiones de dentro de las llaves.

    Lo ultimo NO es un detalle. En Python 3.11, que es lo que corren el
    `Dockerfile` y el CI, un f-string entero tokeniza como UN SOLO token STRING,
    llaves incluidas. Borrandolo completo, un
    `logging.info(f"guardado {datetime.now()}")` reintroducido —la forma mas
    probable de que vuelva el bug— quedaba invisible para el guarda: verde en
    CI con un reloj desnudo ejecutandose en produccion.

    En 3.12+ (PEP 701) la expresion ya tokeniza aparte, asi que ahi el problema
    no existia. O sea que el guarda funcionaba en la maquina de desarrollo
    (3.14) y era ciego justo donde decide el merge.
    """
    if not _es_fstring(texto):
        return "".join("\n" if c == "\n" else " " for c in texto)

    salida = ["\n" if c == "\n" else " " for c in texto]
    profundidad = 0
    i = 0
    while i < len(texto):
        c = texto[i]
        if c == "{":
            if profundidad == 0 and texto[i + 1:i + 2] == "{":
                i += 2                      # '{{' es una llave literal
                continue
            profundidad += 1
        elif c == "}":
            if profundidad > 0:
                profundidad -= 1
            elif texto[i + 1:i + 2] == "}":
                i += 2                      # '}}' literal
                continue
        elif profundidad > 0 and c != "\n":
            salida[i] = c                   # dentro de {...}: es codigo real
        i += 1
    return "".join(salida)


def relojes_desnudos(fuente: str) -> list:
    """Lineas de codigo con un `datetime.now()` sin zona (parentesis vacios)."""
    return [
        (n, linea.strip())
        for n, linea in enumerate(fuente.splitlines(), start=1)
        if "datetime.now()" in linea
    ]


# ───────────────────────────── el helper ─────────────────────────────

class TestHelperHoraMexico:
    """`nc.ahora_mexico()` es la unica fuente de "ahora" del proyecto.

    Vive en `nucleo_catalogo.py` y no en `app.py` a proposito: la hoja
    ENVIOS_CATALOGO recibe timestamps de DOS procesos distintos —
    `app.py` escribe `fecha_solicitud` desde el contenedor y
    `worker_catalogo.py` escribe `timestamp_estado` desde la PC del owner— y un
    helper que solo viviera en `app.py` arreglaria la mitad.
    """

    def test_ahora_mexico_existe(self):
        assert hasattr(nc, "ahora_mexico"), (
            "T5.3 centraliza el reloj en nc.ahora_mexico()"
        )

    def test_trae_tzinfo_explicito(self):
        """Un datetime naive es justo el defecto que T5.3 cierra."""
        assert nc.ahora_mexico().tzinfo is not None

    def test_es_la_zona_de_mexico(self):
        """Mexico abolio el horario de verano en 2022: UTC-6 todo el ano.

        Se acepta -5 por robustez ante un cambio futuro de legislacion, pero
        NUNCA 0: un offset de cero significa que se colo UTC.
        """
        desfase = nc.ahora_mexico().utcoffset()
        assert desfase in (timedelta(hours=-6), timedelta(hours=-5)), (
            f"offset inesperado: {desfase}"
        )

    def test_no_depende_de_la_tz_del_sistema(self):
        """Pasa igual en Windows local (hora de Mexico) y en el runner UTC.

        Comparar contra el instante derivado de UTC lo hace independiente de
        donde corra: si el helper leyera el reloj del sistema sin convertir,
        en el runner de CI daria seis horas de mas.
        """
        derivado_de_utc = datetime.now(timezone.utc).astimezone(nc.TZ_MEXICO)
        assert abs(nc.ahora_mexico() - derivado_de_utc) < timedelta(seconds=5)


# ──────────────────── CE6: la fecha guardada es de Mexico ────────────────────

class TestFechaGuardada:
    """CE6 — reloj congelado a las 19:00 de Mexico: la fecha es la de HOY."""

    # 2026-09-05 01:00 UTC == 2026-09-04 19:00 en Mexico.
    INSTANTE_UTC = datetime(2026, 9, 5, 1, 0, tzinfo=timezone.utc)

    def test_las_19_de_mexico_no_saltan_al_dia_siguiente(self):
        en_mexico = self.INSTANTE_UTC.astimezone(nc.TZ_MEXICO)
        assert en_mexico.strftime("%d/%m/%Y") == "04/09/2026"

    def test_el_mismo_instante_en_utc_si_salta(self):
        """Control: demuestra que el bug es real y que el test lo distingue.

        Sin este assert, el de arriba pasaria igual aunque la conversion no
        hiciera nada.
        """
        assert self.INSTANTE_UTC.strftime("%d/%m/%Y") == "05/09/2026"


# ────────────────────── CE7: la semana ISO es la correcta ──────────────────────

class TestSemanaISO:
    """CE7 — `isocalendar()[1]` alimenta la grafica "Contactos por Semana".

    La semana ISO cambia el lunes a las 00:00. Un domingo por la tarde en
    Mexico ya es lunes en UTC, asi que el contacto se contabiliza en la semana
    siguiente y la grafica reparte mal dos semanas seguidas.
    """

    # 2026-09-07 01:00 UTC (lunes) == 2026-09-06 19:00 en Mexico (domingo).
    INSTANTE_UTC = datetime(2026, 9, 7, 1, 0, tzinfo=timezone.utc)

    def test_un_domingo_por_la_tarde_sigue_en_su_semana(self):
        semana_del_domingo = datetime(2026, 9, 6).isocalendar()[1]
        assert self.INSTANTE_UTC.astimezone(nc.TZ_MEXICO).isocalendar()[1] == semana_del_domingo

    def test_en_utc_ese_mismo_instante_cae_en_la_semana_siguiente(self):
        """Control en la direccion contraria: si esto no fallara en UTC, el
        test de arriba no estaria midiendo nada."""
        semana_del_domingo = datetime(2026, 9, 6).isocalendar()[1]
        assert self.INSTANTE_UTC.isocalendar()[1] == semana_del_domingo + 1


# ─────────────── El barrido: no quedan relojes desnudos ───────────────

class TestSinRelojesDesnudos:

    def test_app_no_tiene_datetime_now_desnuda(self):
        restantes = relojes_desnudos(solo_codigo(RAIZ / "app.py"))
        assert restantes == [], (
            "quedan datetime.now() sin zona en app.py: "
            + "; ".join(f"L{n}: {t}" for n, t in restantes)
        )

    def test_nucleo_y_worker_tampoco(self):
        """La otra mitad del problema: estos dos escriben en la MISMA hoja."""
        for modulo in ("nucleo_catalogo.py", "worker_catalogo.py"):
            restantes = relojes_desnudos(solo_codigo(RAIZ / modulo))
            assert restantes == [], f"{modulo}: {restantes}"

    def test_envio_catalogo_sigue_siendo_deuda_conocida_y_acotada(self):
        """`envio_catalogo.py` escribe en la MISMA hoja y conserva relojes desnudos.

        NO se arregla en T5.3 y los tres reviewers coincidieron en dejarlo fuera:
        corre en la PC del owner, donde la hora local ya es la de Mexico, asi que
        hoy no hay defecto que corregir. Meterlo mezclaria dos superficies con
        duenos de despliegue distintos (contenedor vs PC local).

        Pero no puede quedar solo en un comentario. Si alguien elige el
        transporte "C = Selenium headless", ese script pasa a un contenedor UTC
        y reintroduce el mismo bug en la hoja que T5.3 acaba de arreglar.

        Este test fija el numero conocido: si sube, alguien anadio un reloj
        desnudo mas; si baja a cero, se migro y hay que retirar la deuda de la
        documentacion de `nucleo_catalogo.ahora_mexico`.

        Son CINCO, no tres. Los reviewers citaron 121, 722 y 787, que son los que
        tocan datos: dos comparan "¿es de hoy?" contra la fecha que escribe el
        panel y uno escribe el timestamp de ENVIADO_WA en la hoja. Los otros dos
        (341 y 387) solo componen el nombre de un screenshot de depuracion y no
        llegan a ninguna hoja. El guarda cuenta los cinco porque cuenta codigo,
        no intenciones.
        """
        restantes = relojes_desnudos(solo_codigo(RAIZ / "envio_catalogo.py"))
        assert len(restantes) == 5, (
            "cambio el numero de relojes desnudos de envio_catalogo.py "
            f"(esperados 5, hay {len(restantes)}): {restantes}. "
            "Si se migraron a nc.ahora_mexico(), actualiza tambien el docstring "
            "de ahora_mexico, que declara esta deuda."
        )

    def test_el_guarda_detecta_una_reintroduccion(self):
        """Verificacion en la direccion util: el barrido encuentra un positivo
        que sabemos que esta ahi. Un guarda que solo se ha visto en verde no
        esta probado."""
        inyectado = "def f():\n    return datetime.now()\n"
        assert relojes_desnudos(inyectado) != []

    def test_el_guarda_no_se_dispara_con_un_comentario(self, tmp_path):
        """Y la contraria: NO marca un negativo conocido.

        Es el fallo que este proyecto ya cometio ocho veces: el patron
        prohibido aparece en el comentario que explica por que se retiro.
        """
        f = tmp_path / "ejemplo.py"
        f.write_text(
            "# antes esto usaba datetime.now() y guardaba mal la fecha\n"
            "import nucleo_catalogo as nc\n"
            "x = nc.ahora_mexico()\n",
            encoding="utf-8",
        )
        assert relojes_desnudos(solo_codigo(f)) == []

    def test_el_guarda_ve_un_reloj_dentro_de_un_fstring(self, tmp_path):
        """El agujero mas peligroso que tuvo este guarda, y el mas silencioso.

        En Python 3.11 —el del Dockerfile y el del CI— un f-string tokeniza
        como UN SOLO token STRING con las llaves dentro. La primera version de
        `solo_codigo` borraba el token entero, asi que un
        `logging.info(f"... {datetime.now()}")` reintroducido quedaba invisible
        y el guarda pasaba EN VERDE con el reloj desnudo corriendo en
        produccion.

        En 3.12+ la expresion tokeniza aparte y el problema no se ve: el guarda
        funcionaba en la maquina de desarrollo y era ciego en CI, que es justo
        donde decide el merge.
        """
        f = tmp_path / "ejemplo.py"
        f.write_text(
            'def guardar():\n'
            '    logging.info(f"guardado a las {datetime.now()}")\n',
            encoding="utf-8",
        )
        assert relojes_desnudos(solo_codigo(f)) != []

    def test_el_texto_literal_de_un_fstring_no_dispara(self, tmp_path):
        """La contraria: solo cuenta lo que hay DENTRO de las llaves.

        Un f-string que MENCIONA el patron en su parte literal no es codigo y
        no debe marcar.
        """
        f = tmp_path / "ejemplo.py"
        f.write_text(
            'def aviso(x):\n'
            '    return f"no uses datetime.now() aqui: {x}"\n',
            encoding="utf-8",
        )
        assert relojes_desnudos(solo_codigo(f)) == []

    def test_el_guarda_no_se_dispara_con_un_docstring(self, tmp_path):
        """La variante que este guarda SI dejo pasar en su primera version.

        Un docstring es un token STRING, no COMMENT: filtrar solo comentarios
        no basta, y el fallo aparecio sobre la documentacion del propio helper
        que la tarea acababa de escribir.
        """
        f = tmp_path / "ejemplo.py"
        f.write_text(
            "def ahora():\n"
            '    """Unica fuente de ahora. No usar datetime.now() a secas."""\n'
            "    import nucleo_catalogo as nc\n"
            "    return nc.ahora_mexico()\n",
            encoding="utf-8",
        )
        assert relojes_desnudos(solo_codigo(f)) == []


# ─────────────── Las dos capas: contenedor y dependencias ───────────────

class TestContenedorYDependencias:
    """T5.3 pide DOS capas, no una: `ENV TZ` en el contenedor y `ZoneInfo` en
    el codigo. Solo la variable de entorno dejaria el resultado dependiendo
    del despliegue; solo el codigo dejaria los logs y `date` del contenedor en
    UTC."""

    def test_requirements_declara_tzdata(self):
        """`python:3.11-slim` NO trae la base de zonas horarias: sin `tzdata`,
        `ZoneInfo` lanza ZoneInfoNotFoundError y el panel no arranca. Es el
        riesgo R3 del plan, y su impacto es una caida en produccion."""
        req = (RAIZ / "requirements.txt").read_text(encoding="utf-8").lower()
        assert "tzdata" in req

    def test_dockerfile_fija_la_zona(self):
        df = (RAIZ / "Dockerfile").read_text(encoding="utf-8")
        assert "America/Mexico_City" in df
        assert "TZ" in df


# ─────────────── CE6/CE7 sobre la ruta de escritura REAL ───────────────

class TestRutaDeEscrituraReal:
    """Los dos reviewers senalaron el mismo hueco por separado: `TestFechaGuardada`
    y `TestSemanaISO` prueban la aritmetica de zona, no que `app.py` la USE. El
    unico lazo con el sitio real era el barrido lexico, que detecta el literal
    `datetime.now()` pero no un `date.today()` ni un envoltorio equivalente.

    Esta clase congela el reloj y comprueba lo que `_exportar_a_sheets` escribe
    de verdad en la fila.
    """

    # Domingo 19:00 en Mexico == lunes 01:00 UTC. Elegido asi para que fallen
    # LAS DOS cosas a la vez si se usara UTC: el dia Y la semana ISO.
    #
    # La fecha es del pasado A PROPOSITO. Con un instante de "hoy", un app.py
    # que ignorara el helper y leyera el reloj real escribiria igualmente la
    # fecha de hoy y el test pasaria sin probar nada.
    INSTANTE = datetime(2026, 3, 15, 19, 0, tzinfo=ZoneInfo("America/Mexico_City"))

    def test_el_instante_elegido_sirve_para_distinguir(self):
        """El test no puede volverse vacio en silencio: si el instante dejara de
        tener la propiedad (mismo dia y semana en UTC que en Mexico), los dos
        tests de abajo pasarian aunque el codigo usara UTC."""
        en_utc = self.INSTANTE.astimezone(timezone.utc)
        assert en_utc.date() != self.INSTANTE.date()
        assert en_utc.isocalendar()[1] != self.INSTANTE.isocalendar()[1]
        assert self.INSTANTE.date() != datetime.now(nc.TZ_MEXICO).date(), (
            "el instante congelado no puede ser el de hoy"
        )

    def _fila_escrita(self, monkeypatch):
        import app

        monkeypatch.setattr(nc, "ahora_mexico", lambda: self.INSTANTE)
        monkeypatch.setattr(app, "_claves_de_la_hoja", lambda ws: set())

        capturado = {}

        class WSFalsa:
            def append_rows(self, filas, value_input_option=None):
                capturado["filas"] = filas

        monkeypatch.setattr(app, "get_worksheet", lambda clave: WSFalsa())
        monkeypatch.setattr(app, "_cache_pop", lambda clave: None)

        negocio = {
            "Nombre": "Ferreteria Ejemplo", "Dirección": "Calle 1",
            "Teléfono": "", "Calificación": 4.5, "Núm. de Reseñas": 10,
            "Google Maps Link": "", "Sitio Web": "", "Horarios": "",
            "Estado": "NL", "Latitud": 25.6, "Longitud": -100.3,
            "Tamaño": "", "Tipo Cliente": "",
        }
        app._exportar_a_sheets([negocio], "Ferreteria", "Monterrey")
        assert capturado.get("filas"), "no se escribio ninguna fila"
        return capturado["filas"][0]

    def test_la_fecha_escrita_es_la_de_mexico(self, monkeypatch):
        """CE6 sobre el sitio real: la fecha va en la ultima columna."""
        assert self._fila_escrita(monkeypatch)[-1] == "15/03/2026"

    def test_la_semana_escrita_es_la_de_mexico(self, monkeypatch):
        """CE7 sobre el sitio real: NUM SEMANA es la primera columna."""
        esperada = self.INSTANTE.isocalendar()[1]
        assert self._fila_escrita(monkeypatch)[0] == esperada


# ─────────────── Un solo reloj para las dos columnas ───────────────

class TestUnSoloReloj:
    """ENVIOS_CATALOGO recibe `fecha_solicitud` desde el contenedor
    (`app.py:3440` -> `nc.nueva_fila_envio`) y `timestamp_estado` desde la PC
    del owner (`worker_catalogo.marcar_en_proceso` / `aplicar_resultado`).

    Con dos relojes distintos una fila podia mostrar el cambio de estado SEIS
    HORAS ANTES de la solicitud que lo origino. No es un desfase uniforme
    corregible a posteriori: depende de que proceso escribio cada celda.
    """

    def test_nueva_fila_envio_usa_hora_de_mexico(self):
        tel = "5512345678"  # barrido-ok: telefono sintetico secuencial, de ningun cliente
        fila = nc.nueva_fila_envio("Tienda", tel, 7, "conclusion")
        ts = datetime.strptime(fila[0], nc.FMT_TIMESTAMP)
        referencia = nc.ahora_mexico().replace(tzinfo=None)
        assert abs(ts - referencia) < timedelta(seconds=10)

    @pytest.mark.parametrize("funcion", ["marcar_en_proceso", "aplicar_resultado"])
    def test_el_worker_comparte_el_reloj(self, funcion):
        """Se comprueba sobre el fuente porque llamarlas exige una worksheet."""
        fuente = solo_codigo(RAIZ / "worker_catalogo.py")
        cuerpo = fuente.split(f"def {funcion}")[1].split("\ndef ")[0]
        assert "ahora_mexico()" in cuerpo, (
            f"{funcion} sigue usando un reloj propio"
        )
