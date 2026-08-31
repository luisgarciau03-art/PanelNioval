"""Configuración de pytest para PanelNioval.

`envio_catalogo.py` importa Selenium, webdriver_manager, pyperclip y oauth2client
en la cabecera del módulo. Esas dependencias solo existen en la PC del owner (no
en CI/Railway), así que las stubbeamos en ``sys.modules`` ANTES de importar el
módulo. Ninguna de las funciones puras que caracterizamos usa Selenium en runtime;
solo necesitan que el módulo importe sin error.
"""
import os

# La app es fail-closed: sin PANEL_DASHBOARD_TOKEN no arranca (ver app.py).
# La suite no prueba autenticación salvo en TestAuthPanel, que borra esta
# variable con monkeypatch para ejercitar el gate real.
os.environ.setdefault("PANEL_AUTH_DESACTIVADA", "1")

import sys
import types
from unittest.mock import MagicMock


class _StubModule(types.ModuleType):
    """Módulo falso: cualquier atributo devuelve un MagicMock (soporta `from x import Y`)."""

    def __getattr__(self, name):  # noqa: D401
        return MagicMock(name=f"{self.__name__}.{name}")


# Rutas de módulo (incluidos submódulos) que `envio_catalogo` importa y que
# no están instaladas en el entorno de test.
_STUBBED_MODULES = [
    "oauth2client",
    "oauth2client.service_account",
    "selenium",
    "selenium.webdriver",
    "selenium.webdriver.common",
    "selenium.webdriver.common.by",
    "selenium.webdriver.common.keys",
    "selenium.webdriver.common.action_chains",
    "selenium.webdriver.chrome",
    "selenium.webdriver.chrome.service",
    "selenium.webdriver.chrome.options",
    "selenium.webdriver.support",
    "selenium.webdriver.support.ui",
    "selenium.common",
    "selenium.common.exceptions",
    "webdriver_manager",
    "webdriver_manager.chrome",
]

for _mod_name in _STUBBED_MODULES:
    if _mod_name not in sys.modules:
        sys.modules[_mod_name] = _StubModule(_mod_name)


from pathlib import Path  # noqa: E402

import pytest  # noqa: E402

def leer_superficie(nombre: str) -> str:
    """Marcado + CSS + JS de una superficie, como estaba antes del Plan 4.

    Hasta el Plan 4 las tres superficies vivian en literales de `app.py`
    (`IMPORTADOR_HTML` y companeras) y varios tests afirmaban sobre esa cadena.
    La T4.3 las movio a `templates/` y `static/` **sin cambiar su contenido**;
    esta funcion vuelve a reunir las tres piezas para que esas afirmaciones
    sigan valiendo exactamente lo mismo que antes del refactor.
    """
    raiz = Path(__file__).resolve().parent.parent
    partes = [
        (raiz / "templates" / f"{nombre}.html").read_text(encoding="utf-8"),
        (raiz / "static" / "css" / f"{nombre}.css").read_text(encoding="utf-8"),
        (raiz / "static" / "js" / f"{nombre}.js").read_text(encoding="utf-8"),
    ]
    return chr(10).join(partes)


def leer_js(nombre: str) -> str:
    """Solo el JavaScript de una superficie."""
    raiz = Path(__file__).resolve().parent.parent
    return (raiz / "static" / "js" / f"{nombre}.js").read_text(encoding="utf-8")


def servir_superficie(client, ruta: str, nombre: str) -> str:
    """Todo lo que el navegador acaba recibiendo de una superficie.

    Pide la pagina y ademas baja su CSS y su JS **por la ruta `/static`**, no
    del disco. Antes del Plan 4 el CSS y el JS venian incrustados en el HTML y
    bastaba con mirar la respuesta; ahora son peticiones aparte, asi que esta
    funcion mantiene el alcance original de las afirmaciones y de paso
    comprueba que Flask sirve los estaticos de verdad (riesgo R7 del Plan 4).
    """
    partes = [client.get(ruta).data.decode("utf-8", "ignore")]
    for sub in (f"/static/css/{nombre}.css", f"/static/js/{nombre}.js"):
        r = client.get(sub)
        assert r.status_code == 200, f"Flask no sirve {sub}: HTTP {r.status_code}"
        partes.append(r.data.decode("utf-8", "ignore"))
    return chr(10).join(partes)



@pytest.fixture(autouse=True)
def _cache_de_places_aislada(tmp_path, monkeypatch):
    """Cada test estrena cache de Place Details.

    Por defecto la cache vive en el temp del sistema, asi que sin esto un test
    heredaria los detalles que cacheo otro y mediria 0 llamadas a la API creyendo
    que su codigo las evito. Se aisla en el tmp_path del propio test.
    """
    import app
    monkeypatch.setattr(app, "PLACES_CACHE_FILE",
                        str(tmp_path / "places_detalles.json"))
