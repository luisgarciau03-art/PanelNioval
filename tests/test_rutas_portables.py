"""Las rutas del worker no deben depender de una maquina concreta.

PDF_LOCAL_PATH y FALLBACK_PROFILE_DIR estaban fijadas a 'C:/Users/PC 1/...'.
Al instalar el proyecto en otra PC, Chrome no podia crear el perfil y el worker
moria con SessionNotCreatedException: "cannot create default profile directory".

Se usan barras normales en las rutas de prueba a proposito: Windows las acepta,
y ambos lados de cada assert se construyen con el mismo os.path.join, asi que la
comparacion no depende del separador.
"""
import importlib
import os

import pytest

import envio_catalogo as ec

HOME_DELL = "C:/Users/DELL"
HOME_OWNER = "C:/Users/PC 1"
HOME_OTRO = "C:/Users/OTRO"


def _recargar(monkeypatch, inicio=None, **entorno):
    """Recarga envio_catalogo con un HOME y unas env vars dados."""
    for k in ("NIOVAL_ARCHIVOS_DIR", "NIOVAL_CHROME_PROFILE", "NIOVAL_CHROME_BINARY"):
        monkeypatch.delenv(k, raising=False)
    for k, v in entorno.items():
        monkeypatch.setenv(k, v)
    if inicio is not None:
        monkeypatch.setattr(os.path, "expanduser", lambda p: inicio if p == "~" else p)
    return importlib.reload(ec)


@pytest.fixture(autouse=True)
def _restaurar():
    """Devolver el modulo a su estado real tras cada test."""
    yield
    importlib.reload(ec)


class TestPerfilDeChrome:
    """El perfil sigue al usuario: cada PC usa el suyo."""

    def test_otra_pc_otra_carpeta(self, monkeypatch):
        """El caso reportado: instalado en una PC cuyo usuario es DELL."""
        m = _recargar(monkeypatch, inicio=HOME_DELL)
        assert m.FALLBACK_PROFILE_DIR == os.path.join(HOME_DELL, "ChromeSeleniumProfile")
        assert "PC 1" not in m.FALLBACK_PROFILE_DIR

    def test_la_pc_original_resuelve_igual_que_antes(self, monkeypatch):
        """Sin regresion en la maquina del owner: ~ es C:/Users/PC 1."""
        m = _recargar(monkeypatch, inicio=HOME_OWNER)
        assert m.FALLBACK_PROFILE_DIR == os.path.join(HOME_OWNER, "ChromeSeleniumProfile")

    def test_la_env_var_manda(self, monkeypatch):
        m = _recargar(monkeypatch, inicio=HOME_DELL, NIOVAL_CHROME_PROFILE="D:/perfiles/wa")
        assert m.FALLBACK_PROFILE_DIR == "D:/perfiles/wa"


class TestArchivosDelCatalogo:
    """Los archivos viven en Files/ dentro del proyecto (decision del owner).

    Al ser relativa al propio modulo, la ruta es la misma en cualquier PC donde
    se clone, sin depender del nombre de usuario.
    """

    def test_apunta_a_Files_dentro_del_proyecto(self, monkeypatch):
        m = _recargar(monkeypatch, inicio=HOME_DELL)
        proyecto = os.path.dirname(os.path.abspath(m.__file__))
        assert m.PDF_LOCAL_PATH == os.path.join(proyecto, "Files")

    def test_no_depende_del_usuario(self, monkeypatch):
        """El bug original: la ruta cambiaba de PC y no se encontraba nada."""
        a = _recargar(monkeypatch, inicio=HOME_DELL).PDF_LOCAL_PATH
        b = _recargar(monkeypatch, inicio=HOME_OTRO).PDF_LOCAL_PATH
        assert a == b
        assert "DELL" not in a and "OTRO" not in a

    def test_la_env_var_sigue_mandando(self, monkeypatch):
        m = _recargar(monkeypatch, inicio=HOME_DELL, NIOVAL_ARCHIVOS_DIR="D:/catalogo")
        assert m.PDF_LOCAL_PATH == "D:/catalogo"


class TestUbicarChrome:
    def test_devuelve_vacio_si_no_hay_ninguno(self, monkeypatch):
        """Sin Chrome, cadena vacia: crear_opciones no fija binary_location y
        Selenium lo busca por su cuenta, en vez de reventar."""
        monkeypatch.setattr(os.path, "isfile", lambda p: False)
        assert ec._ubicar_chrome() == ""

    def test_la_env_var_tiene_prioridad(self, monkeypatch):
        monkeypatch.setenv("NIOVAL_CHROME_BINARY", "D:/chrome/chrome.exe")
        monkeypatch.setattr(os.path, "isfile", lambda p: True)
        assert ec._ubicar_chrome() == "D:/chrome/chrome.exe"

    def test_encuentra_el_que_existe(self, monkeypatch):
        """Con Chrome solo en LOCALAPPDATA (instalacion por usuario)."""
        monkeypatch.delenv("NIOVAL_CHROME_BINARY", raising=False)
        monkeypatch.setenv("LOCALAPPDATA", "C:/Users/DELL/AppData/Local")
        esperado = os.path.join("C:/Users/DELL/AppData/Local",
                                "Google", "Chrome", "Application", "chrome.exe")
        monkeypatch.setattr(os.path, "isfile", lambda p: p == esperado)
        assert ec._ubicar_chrome() == esperado
