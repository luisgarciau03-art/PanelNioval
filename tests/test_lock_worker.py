"""Tests del lock del worker de catálogo.

El lock evita dos corridas solapadas, que duplicarían envíos de WhatsApp. Antes
solo miraba la edad del archivo: un worker cerrado con Ctrl+C o caído por un
apagón dejaba el lock y bloqueaba los reintentos hasta 30 minutos, sin ninguna
corrida real en curso. Este es el caso que se reportó en producción.
"""
import os
import subprocess
import sys

import pytest

import worker_catalogo_run as w


@pytest.fixture
def lock_aislado(tmp_path, monkeypatch):
    """Lock en un temporal propio: no tocar el del worker real del owner."""
    ruta = tmp_path / "worker_catalogo.lock"
    monkeypatch.setattr(w, "LOCK_PATH", str(ruta))
    return ruta


@pytest.fixture(scope="module")
def pid_muerto():
    """PID de un proceso que ya termino, garantizado muerto."""
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    p.wait()
    return p.pid


class TestProcesoVivo:
    def test_el_propio_proceso_esta_vivo(self):
        assert w._proceso_vivo(os.getpid()) is True

    def test_un_proceso_terminado_no(self, pid_muerto):
        assert w._proceso_vivo(pid_muerto) is False

    def test_pid_invalido_no_esta_vivo(self):
        assert w._proceso_vivo(0) is False
        assert w._proceso_vivo(-1) is False


class TestPidDelLock:
    def test_lee_el_pid(self, lock_aislado):
        lock_aislado.write_text("12345 1787416590.29", encoding="utf-8")
        assert w._pid_del_lock() == 12345

    def test_devuelve_cero_si_no_existe(self, lock_aislado):
        assert w._pid_del_lock() == 0

    def test_devuelve_cero_si_esta_corrupto(self, lock_aislado):
        lock_aislado.write_text("basura", encoding="utf-8")
        assert w._pid_del_lock() == 0


class TestAdquirirLock:
    def test_adquiere_si_no_hay_lock(self, lock_aislado):
        assert w._adquirir_lock() is True
        assert lock_aislado.is_file()

    def test_reemplaza_lock_de_proceso_muerto(self, lock_aislado, pid_muerto):
        """EL CASO REPORTADO: lock reciente pero de un worker que ya murio.

        Con la version anterior esto devolvia False y el operador no podia
        arrancar el worker durante 30 minutos sin ninguna corrida en curso.
        """
        lock_aislado.write_text(f"{pid_muerto} 1787416590.29", encoding="utf-8")
        assert w._adquirir_lock() is True
        assert w._pid_del_lock() == os.getpid()   # el lock es nuestro ahora

    def test_respeta_lock_de_proceso_vivo(self, lock_aislado):
        """Lo que el lock si debe impedir: arrancar sobre una corrida real."""
        lock_aislado.write_text(f"{os.getpid()} 1787416590.29", encoding="utf-8")
        assert w._adquirir_lock() is False

    def test_libera_el_lock(self, lock_aislado):
        w._adquirir_lock()
        assert lock_aislado.is_file()
        w._liberar_lock()
        assert not lock_aislado.is_file()
