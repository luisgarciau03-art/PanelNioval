"""El telefono de un cliente real no puede volver al repositorio.

Durante anios el proyecto uso un telefono real como "numero canonico de ejemplo":
estaba en el placeholder de dos pantallas, en los docstrings de
`nucleo_catalogo.py`, en el RUNBOOK y en las fixtures de dos archivos de tests.
No era un numero inventado — es el telefono de un contacto real de
`LISTA DE CONTACTOS`, y aparecio tal cual en capturas de pantalla del panel.

Se sustituyo por `555 123 4567` en las 20 apariciones (Plan 4). Este guarda
existe porque el barrido de secretos del CI **no lo habria detectado**: su patron
de telefono exige 10 digitos contiguos, asi que ve la forma pegada pero no la
separada por espacios, guiones o parentesis. El formato con espacios es
justo el que usa la hoja de calculo, y por tanto el que acaba copiado a mano en
codigo y documentacion.

El numero sigue vivo en el historial de git: quitarlo de los archivos no lo borra
de ahi. Esto solo impide que vuelva a entrar.
"""
import re
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent

# El numero, en las formas en que aparecia y en las que podria reaparecer.
# Se escribe partido para que este mismo archivo no sea una aparicion mas.
_LADA, _MEDIO, _FINAL = "662", "353", "4185"
# Cualquier cosa que no sea un digito entre grupo y grupo, hasta tres caracteres.
# Con `[\s.\-]*` se escapaba la forma con parentesis, que es justamente una de
# aquellas en que estaba escrito: el `)` no entraba en la clase.
_SEP = r"[^0-9]{0,3}"
PATRON = re.compile(_LADA + _SEP + _MEDIO + _SEP + _FINAL)

# Binarios y rutas donde buscar no aporta.
EXTENSIONES_SALTADAS = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".xlsx", ".zip"}


def _archivos_versionados() -> list[Path]:
    salida = subprocess.run(
        ["git", "ls-files"], cwd=RAIZ, capture_output=True, text=True, timeout=60
    )
    if salida.returncode != 0:
        pytest.skip("git no disponible")
    rutas = []
    for linea in salida.stdout.splitlines():
        p = RAIZ / linea
        if p.suffix.lower() in EXTENSIONES_SALTADAS or not p.is_file():
            continue
        rutas.append(p)
    return rutas


class TestElTelefonoRealNoVuelve:
    def test_el_patron_encuentra_lo_que_debe(self):
        """Un barrido que no encuentra nada no demuestra que no hay nada.

        Antes de creerle el cero al test de abajo, se comprueba que el patron
        casa con las cinco formas en que el numero llego a estar escrito.
        """
        for forma in (
            _LADA + " " + _MEDIO + " " + _FINAL,
            _LADA + "-" + _MEDIO + "-" + _FINAL,
            _LADA + _MEDIO + _FINAL,
            "+52 " + _LADA + " " + _MEDIO + " " + _FINAL,
            "52" + _LADA + _MEDIO + _FINAL,
            "(" + _LADA + ") " + _MEDIO + " " + _FINAL,   # se escapaba del patron anterior
            _LADA + "." + _MEDIO + "." + _FINAL,
        ):
            assert PATRON.search(forma), f"el patron no ve {forma!r}"

    def test_el_patron_no_marca_el_sustituto(self):
        """Y que no marca el numero sintetico que lo reemplazo."""
        for forma in ("555 123 4567", "5551234567", "+525551234567"):
            assert not PATRON.search(forma), f"falso positivo con {forma!r}"

    def test_no_aparece_en_ningun_archivo_versionado(self):
        hallazgos = []
        for p in _archivos_versionados():
            try:
                texto = p.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for n, linea in enumerate(texto.splitlines(), 1):
                if PATRON.search(linea):
                    hallazgos.append(f"{p.relative_to(RAIZ)}:{n}")
        assert not hallazgos, (
            "el telefono de un cliente real volvio al repositorio en:\n  "
            + "\n  ".join(hallazgos)
            + "\nUsa 555 123 4567 como ejemplo."
        )
