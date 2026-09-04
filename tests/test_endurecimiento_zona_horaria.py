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

import pytest

# No se importa `app` ni `worker_catalogo`: este archivo comprueba el reloj
# compartido (`nucleo_catalogo`) y el resto lo audita sobre el fuente. Importar
# `app` aqui costaria el arranque en frio sin aportar nada.
import nucleo_catalogo as nc

RAIZ = pathlib.Path(__file__).resolve().parents[1]


# ───────────────────────── utilidades del barrido ─────────────────────────

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
    lineas = texto.splitlines()
    for tok in tokenize.generate_tokens(io.StringIO(texto).readline):
        if tok.type not in (tokenize.COMMENT, tokenize.STRING):
            continue
        (fila_i, col_i), (fila_f, col_f) = tok.start, tok.end
        if fila_i == fila_f:
            fila = fila_i - 1
            lineas[fila] = lineas[fila][:col_i] + " " * (col_f - col_i) + lineas[fila][col_f:]
        else:
            lineas[fila_i - 1] = lineas[fila_i - 1][:col_i]
            for fila in range(fila_i, fila_f - 1):
                lineas[fila] = ""
            lineas[fila_f - 1] = lineas[fila_f - 1][col_f:]
    return "\n".join(lineas)


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
