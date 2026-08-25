"""Las rutas del worker deben seguir al usuario, no a una maquina concreta.

PDF_LOCAL_PATH y FALLBACK_PROFILE_DIR estaban fijadas a 'C:/Users/PC 1/...'.
Al instalar el proyecto en otra PC, Chrome no podia crear el perfil y el worker
moria con SessionNotCreatedException: "cannot create default profile directory".
"""
import importlib
import os

import pytest

import envio_catalogo as ec


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


class TestRutasSiguenAlUsuario:
    def test_otra_pc_otra_carpeta(self, monkeypatch):
        """El caso reportado: instalado en una PC cuyo usuario es DELL."""
        m = _recargar(monkeypatch, inicio=r"C:\Users\DELL")
        assert m.FALLBACK_PROFILE_DIR == os.path.join(r"C:\Users\DELL", "ChromeSeleniumProfile")
        assert m.PDF_LOCAL_PATH == os.path.join(r"C:\Users\DELL", "Files mensajes")
        assert "PC 1" not in m.FALLBACK_PROFILE_DIR
        assert "PC 1" not in m.PDF_LOCAL_PATH

    def test_la_pc_original_resuelve_igual_que_antes(self, monkeypatch):
        """Sin regresion en la maquina del owner: ~ es C:/Users/PC 1."""
        m = _recargar(monkeypatch, inicio=r"C:\Users\PC 1")
        assert m.FALLBACK_PROFILE_DIR == os.path.join(r"C:\Users\PC 1", "ChromeSeleniumProfile")
        assert m.PDF_LOCAL_PATH == os.path.join(r"C:\Users\PC 1", "Files mensajes")

    def test_las_env_vars_mandan(self, monkeypatch):
        """Un disco compartido o una ruta a medida deben poder imponerse."""
        m = _recargar(monkeypatch, inicio=r"C:\Users\DELL",
                      NIOVAL_CHROME_PROFILE=r"D:\perfiles\wa",
                      NIOVAL_ARCHIVOS_DIR=r"D:\catalogo")
        assert m.FALLBACK_PROFILE_DIR == r"D:\perfiles\wa"
        assert m.PDF_LOCAL_PATH == r"D:\catalogo"


class TestUbicarChrome:
    def test_devuelve_vacio_si_no_hay_ninguno(self, monkeypatch):
        """Sin Chrome, cadena vacia: crear_opciones no fija binary_location y
        Selenium lo busca por su cuenta, en vez de reventar."""
        monkeypatch.setattr(os.path, "isfile", lambda p: False)
        assert ec._ubicar_chrome() == ""

    def test_la_env_var_tiene_prioridad(self, monkeypatch):
        monkeypatch.setenv("NIOVAL_CHROME_BINARY", r"D:\chrome\chrome.exe")
        monkeypatch.setattr(os.path, "isfile", lambda p: True)
        assert ec._ubicar_chrome() == r"D:\chrome\chrome.exe"

    def test_encuentra_el_que_existe(self, monkeypatch):
        """Con Chrome solo en LOCALAPPDATA (instalacion por usuario)."""
        monkeypatch.delenv("NIOVAL_CHROME_BINARY", raising=False)
        monkeypatch.setenv("LOCALAPPDATA", r"C:\Users\DELL\AppData\Local")
        esperado = os.path.join(r"C:\Users\DELL\AppData\Local",
                                "Google", "Chrome", "Application", "chrome.exe")
        monkeypatch.setattr(os.path, "isfile", lambda p: p == esperado)
        assert ec._ubicar_chrome() == esperado
