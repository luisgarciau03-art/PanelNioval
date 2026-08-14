"""Tests del worker de cola de catálogo con transporte FAKE (Plan 3 T3.3)."""
from unittest.mock import MagicMock

import pytest

import nucleo_catalogo as nc
import worker_catalogo as wc


def _filas(*regs):
    """Construye get_all_values() (encabezado + filas) desde dicts parciales."""
    filas = [list(nc.COLUMNAS_ENVIOS)]
    for reg in regs:
        filas.append([str(reg.get(h, "")) for h in nc.COLUMNAS_ENVIOS])
    return filas


class TestSeleccionarPendientes:
    def test_solo_pendientes(self):
        filas = _filas(
            {"tienda": "A", "telefono": "+5512345678", "fila_respuesta": "7", "estado": nc.PENDIENTE},
            {"tienda": "B", "telefono": "+5512345678", "fila_respuesta": "9", "estado": nc.ENVIADO},
            {"tienda": "C", "telefono": "+5512345678", "fila_respuesta": "5", "estado": nc.PENDIENTE},
        )
        pend = wc.seleccionar_pendientes(filas)
        assert [p["tienda"] for p in pend] == ["A", "C"]
        assert pend[0]["_row"] == 2
        assert pend[1]["_row"] == 4

    def test_hoja_vacia(self):
        assert wc.seleccionar_pendientes([]) == []


class TestProcesarEnvio:
    def _reg(self, tel="+5512345678"):
        return {"tienda": "A", "telefono": tel, "_row": 2}

    def test_transporte_enviado(self):
        transporte = lambda t, m, a: wc.ResultadoEnvio(nc.ENVIADO, "ok")
        res = wc.procesar_envio(self._reg(), transporte, ["hola"], [])
        assert res.estado == nc.ENVIADO

    def test_numero_invalido_no_llama_transporte(self):
        llamado = {"v": False}
        def transporte(t, m, a):
            llamado["v"] = True
            return wc.ResultadoEnvio(nc.ENVIADO)
        res = wc.procesar_envio(self._reg(tel="123"), transporte, [], [])
        assert res.estado == nc.NUMERO_INVALIDO
        assert llamado["v"] is False  # no se intentó enviar a un número inválido

    def test_transporte_reporta_numero_invalido(self):
        transporte = lambda t, m, a: wc.ResultadoEnvio(nc.NUMERO_INVALIDO, "popup detectado")
        res = wc.procesar_envio(self._reg(), transporte, [], [])
        assert res.estado == nc.NUMERO_INVALIDO
        assert "popup" in res.detalle

    def test_excepcion_de_transporte_es_fallo_no_se_traga(self):
        def transporte(t, m, a):
            raise RuntimeError("chat no cargó")
        res = wc.procesar_envio(self._reg(), transporte, [], [])
        assert res.estado == nc.FALLO
        assert "chat no cargó" in res.detalle  # el error se conserva, no se silencia


class TestAutorizarEnvio:
    def test_sin_password_env_no_autoriza(self, monkeypatch):
        monkeypatch.delenv("WA_ENVIO_PASSWORD", raising=False)
        ok, motivo = wc.autorizar_envio(es_tty=False)
        assert ok is False
        assert "WA_ENVIO_PASSWORD" in motivo

    def test_interactivo_password_correcta_autoriza(self, monkeypatch):
        monkeypatch.setenv("WA_ENVIO_PASSWORD", "clave-de-prueba")
        ok, motivo = wc.autorizar_envio(prompt_fn=lambda: "clave-de-prueba", es_tty=True)
        assert ok is True

    def test_interactivo_password_incorrecta_no_autoriza(self, monkeypatch):
        monkeypatch.setenv("WA_ENVIO_PASSWORD", "clave-de-prueba")
        ok, motivo = wc.autorizar_envio(prompt_fn=lambda: "mala", es_tty=True)
        assert ok is False
        assert "incorrecta" in motivo

    def test_no_interactivo_requiere_armado(self, monkeypatch):
        monkeypatch.setenv("WA_ENVIO_PASSWORD", "clave-de-prueba")
        monkeypatch.delenv("WA_ENVIO_ARMADO", raising=False)
        ok, _ = wc.autorizar_envio(es_tty=False)
        assert ok is False

    def test_no_interactivo_armado_autoriza(self, monkeypatch):
        monkeypatch.setenv("WA_ENVIO_PASSWORD", "clave-de-prueba")
        monkeypatch.setenv("WA_ENVIO_ARMADO", "1")
        ok, _ = wc.autorizar_envio(es_tty=False)
        assert ok is True


class TestProcesarCola:
    def test_corrida_completa_mixta(self):
        ws = MagicMock()
        ws.get_all_values.return_value = _filas(
            {"tienda": "A", "telefono": "+5512345678", "fila_respuesta": "7", "estado": nc.PENDIENTE},
            {"tienda": "B", "telefono": "123", "fila_respuesta": "9", "estado": nc.PENDIENTE},  # inválido
            {"tienda": "C", "telefono": "+5512345678", "fila_respuesta": "5", "estado": nc.ENVIADO},  # no pendiente
        )
        transporte = lambda t, m, a: wc.ResultadoEnvio(nc.ENVIADO, "ok")
        resumen = wc.procesar_cola(ws, transporte, ["hola"], [])
        assert resumen == {"enviados": 1, "invalidos": 1, "fallos": 0, "procesados": 2}
        # Por cada pendiente: 1 batch_update de EN_PROCESO (lock) + 1 de estado final.
        assert ws.batch_update.call_count == 4
