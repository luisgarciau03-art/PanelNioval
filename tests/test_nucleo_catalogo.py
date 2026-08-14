"""Tests de la lógica pura de la cola de catálogo (`nucleo_catalogo.py`)."""
from datetime import datetime

import pytest

import nucleo_catalogo as nc


class TestConclusionElegible:
    @pytest.mark.parametrize("col_j,esperado", [
        ("Pedido", True),
        ("Revisara el Catalogo", True),
        ("PEDIDO", True),                 # case-insensitive
        ("  revisara el catalogo  ", True),
        ("Correo", False),
        ("Nulo", False),
        ("No apto", False),
        ("", False),
        (None, False),
    ])
    def test_elegible(self, col_j, esperado):
        assert nc.conclusion_elegible(col_j) is esperado


class TestNormalizarTelefono:
    @pytest.mark.parametrize("entrada,esperado", [
        ("5512345678", "+5512345678"),
        ("+52 55 1234 5678", "+525512345678"),
        ("(55) 1234-5678", "+5512345678"),
        ("", ""),
        ("sin numero", ""),
    ])
    def test_normaliza(self, entrada, esperado):
        assert nc.normalizar_telefono(entrada) == esperado


class TestValidarNumero:
    @pytest.mark.parametrize("tel,ok", [
        ("5512345678", True),          # 10 dígitos
        ("+525512345678", True),       # 12 dígitos
        ("123456789", False),          # 9 dígitos (corto)
        ("12345678901234", False),     # 14 dígitos (largo)
        ("", False),
        ("abc", False),
    ])
    def test_valida(self, tel, ok):
        assert nc.validar_numero(tel) is ok


class TestTransiciones:
    @pytest.mark.parametrize("desde,hacia,ok", [
        (nc.PENDIENTE, nc.EN_PROCESO, True),
        (nc.EN_PROCESO, nc.ENVIADO, True),
        (nc.EN_PROCESO, nc.NUMERO_INVALIDO, True),
        (nc.EN_PROCESO, nc.FALLO, True),
        (nc.NUMERO_INVALIDO, nc.PENDIENTE, True),   # re-encolar
        (nc.FALLO, nc.PENDIENTE, True),             # reintentar
        (nc.ENVIADO, nc.PENDIENTE, False),          # terminal
        (nc.PENDIENTE, nc.ENVIADO, False),          # debe pasar por EN_PROCESO
    ])
    def test_transicion(self, desde, hacia, ok):
        assert nc.transicion_valida(desde, hacia) is ok


class TestNuevaFilaEnvio:
    def test_estructura_y_estado_inicial(self):
        ahora = datetime(2026, 8, 13, 10, 30, 0)
        fila = nc.nueva_fila_envio("Ferretería A", "5512345678", 7, "Revisara el Catalogo", ahora=ahora)
        assert len(fila) == len(nc.COLUMNAS_ENVIOS)
        d = dict(zip(nc.COLUMNAS_ENVIOS, fila))
        assert d["tienda"] == "Ferretería A"
        assert d["telefono"] == "+5512345678"
        assert d["fila_respuesta"] == "7"
        assert d["conclusion"] == "Revisara el Catalogo"
        assert d["estado"] == nc.PENDIENTE
        assert d["intentos"] == "0"
        assert d["fecha_solicitud"] == "13/08/2026 10:30:00"


class TestIndicePorFilaRespuesta:
    def _filas(self):
        return [
            nc.COLUMNAS_ENVIOS,  # encabezado
            ["13/08/2026", "A", "+55...", "7", "Pedido", "PENDIENTE", "0", "13/08/2026", ""],
            ["13/08/2026", "B", "+55...", "9", "Revisara el Catalogo", "ENVIADO", "1", "13/08/2026", ""],
        ]

    def test_encuentra_por_fila_respuesta(self):
        assert nc.indice_por_fila_respuesta(self._filas(), 9) == 3

    def test_no_existe_devuelve_none(self):
        assert nc.indice_por_fila_respuesta(self._filas(), 99) is None

    def test_idempotencia_misma_fila_no_duplica(self):
        # Si ya existe la fila_respuesta 7, el índice existe → el caller NO debe insertar otra.
        assert nc.indice_por_fila_respuesta(self._filas(), 7) == 2


class TestEnmascararTelefono:
    def test_deja_ultimos_4(self):
        assert nc.enmascarar_telefono("5512345678") == "+******5678"

    def test_corto(self):
        assert nc.enmascarar_telefono("12") == "****"
