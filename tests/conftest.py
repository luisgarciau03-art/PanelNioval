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


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _cache_de_places_aislada(tmp_path, monkeypatch):
    """Cada test estrena cache de Place Details.

    Por defecto la cache vive en el temp del sistema, asi que sin esto un test
    heredaria los detalles que cacheo otro y mediria 0 llamadas a la API creyendo
    que su codigo las evito. Se aisla en el tmp_path del propio test.
    """
    import app
    monkeypatch.setattr(app, "PLACES_CACHE_FILE",
                        str(tmp_path / "places_detalles.json"), raising=False)
