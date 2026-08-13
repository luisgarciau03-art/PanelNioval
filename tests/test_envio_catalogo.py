"""Tests de caracterización de `envio_catalogo.py` (antes `22.PY`).

Este es el PRIMER baseline de tests del proyecto PanelNioval. Caracteriza el
comportamiento ACTUAL de las funciones puras del script (incluidos bugs, marcados
con `# BUG conocido:` y referenciados al informe de auditoría
docs/auditoria/2026-08-13-auditoria-22py.md). No corrige comportamiento: la
corrección de los bugs vive en los Planes 3/5.

Selenium NO se testea (se mockea su import en conftest.py).
"""
import os
from datetime import datetime
from unittest.mock import MagicMock

import pytest

import envio_catalogo as ec


# ─────────────────────────── fecha_es_hoy ───────────────────────────
class TestFechaEsHoy:
    def test_fecha_de_hoy_formato_ddmmyyyy_true(self):
        hoy = datetime.now().strftime("%d/%m/%Y")
        assert ec.fecha_es_hoy(hoy) is True

    def test_fecha_de_hoy_con_hora_hace_split_por_espacio(self):
        hoy = datetime.now().strftime("%d/%m/%Y") + " 14:35:00"
        assert ec.fecha_es_hoy(hoy) is True

    def test_fecha_distinta_false(self):
        assert ec.fecha_es_hoy("01/01/2000") is False

    def test_cadena_vacia_false(self):
        assert ec.fecha_es_hoy("") is False

    def test_basura_false(self):
        assert ec.fecha_es_hoy("no-es-fecha") is False


# ─────────────────────────── buscar_telefono ───────────────────────────
class TestBuscarTelefono:
    def _rows(self):
        # La fila 0 es tratada como ENCABEZADO y SALTADA por buscar_telefono (tel_rows[1:]).
        header = ["ENCABEZADO"] + [""] * 20
        fila_a = ["Ferretería A"] + [""] * 17 + ["5512345678"]   # tel en índice 18
        fila_b = ["Plomería B"] + [""] * 17 + ["+5598765432"]    # tel en índice 18
        return [header, fila_a, fila_b]

    def test_match_exacto_agrega_prefijo_mas(self):
        assert ec.buscar_telefono("Ferretería A", self._rows()) == "+5512345678"

    def test_match_case_insensitive(self):
        assert ec.buscar_telefono("ferretería a", self._rows()) == "+5512345678"

    def test_no_duplica_prefijo_si_ya_tiene_mas(self):
        assert ec.buscar_telefono("Plomería B", self._rows()) == "+5598765432"

    def test_sin_match_devuelve_none(self):
        assert ec.buscar_telefono("Inexistente", self._rows()) is None

    def test_bug_conocido_primera_fila_es_ignorada_como_encabezado(self):
        # BUG conocido (auditoría L/M): la fila índice 0 SIEMPRE se salta.
        # Si una tienda real quedara en la primera fila, nunca se encontraría.
        rows = [["Ferretería A"] + [""] * 17 + ["", "5512345678"]]
        assert ec.buscar_telefono("Ferretería A", rows) is None

    def test_fila_corta_sin_columna_telefono_devuelve_cadena_vacia(self):
        # Nombre coincide pero la fila no llega al índice 18 → telefono "" (falsy, sin '+').
        rows = [["ENCABEZADO"], ["Ferretería A", "dato"]]
        assert ec.buscar_telefono("Ferretería A", rows) == ""

    def test_bug_conocido_nombres_duplicados_usa_la_primera_coincidencia(self):
        # BUG conocido (auditoría M5): dos tiendas con el mismo nombre → gana la primera, sin aviso.
        rows = [
            ["ENCABEZADO"],
            ["Ferretería A"] + [""] * 17 + ["5511111111"],
            ["Ferretería A"] + [""] * 17 + ["5522222222"],
        ]
        assert ec.buscar_telefono("Ferretería A", rows) == "+5511111111"


# ─────────────────────────── obtener_mensajes ───────────────────────────
class TestObtenerMensajes:
    def test_salta_dos_primeras_filas_y_filtra_vacios(self):
        sheet = MagicMock()
        sheet.col_values.return_value = [
            "Encabezado", "Instrucción", "Mensaje 1", "", "   ", "Mensaje 2",
        ]
        assert ec.obtener_mensajes(sheet) == ["Mensaje 1", "Mensaje 2"]
        sheet.col_values.assert_called_once_with(1)

    def test_lista_solo_de_encabezados_devuelve_vacio(self):
        sheet = MagicMock()
        sheet.col_values.return_value = ["Encabezado", "Instrucción"]
        assert ec.obtener_mensajes(sheet) == []

    def test_no_recorta_espacios_del_mensaje(self):
        # Caracterización: el filtro usa m.strip() pero DEVUELVE m sin recortar → va tal cual a WhatsApp.
        sheet = MagicMock()
        sheet.col_values.return_value = ["Encabezado", "Instrucción", "  Hola  "]
        assert ec.obtener_mensajes(sheet) == ["  Hola  "]


# ─────────────────────────── tipo_archivo ───────────────────────────
class TestTipoArchivo:
    @pytest.mark.parametrize("path,esperado", [
        ("foto.jpg", "media"),
        ("clip.mp4", "media"),
        ("FOTO.JPG", "media"),          # extensión en mayúsculas → normalizada
        ("catalogo.pdf", "documento"),
        ("hoja.xlsx", "documento"),
        ("archivo.xyz", None),
        ("sin_extension", None),
    ])
    def test_clasificacion(self, path, esperado):
        assert ec.tipo_archivo(path) == esperado


# ─────────────────────────── resolve_media_path ───────────────────────────
class TestResolveMediaPath:
    def test_absoluto_existente(self, tmp_path):
        f = tmp_path / "IMG1.jpg"
        f.write_bytes(b"x")
        assert ec.resolve_media_path(str(f)) == str(f)

    def test_absoluto_inexistente_devuelve_none(self, tmp_path):
        assert ec.resolve_media_path(str(tmp_path / "no_existe.pdf")) is None

    def test_absoluto_sin_extension_encuentra_candidato(self, tmp_path):
        (tmp_path / "video.mp4").write_bytes(b"x")
        base = str(tmp_path / "video")
        assert ec.resolve_media_path(base) == base + ".mp4"

    def test_relativo_existente_usa_pdf_local_path(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ec, "PDF_LOCAL_PATH", str(tmp_path))
        (tmp_path / "CATALOGO.pdf").write_bytes(b"x")
        assert ec.resolve_media_path("CATALOGO.pdf") == os.path.join(str(tmp_path), "CATALOGO.pdf")

    def test_relativo_con_extension_inexistente_devuelve_none(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ec, "PDF_LOCAL_PATH", str(tmp_path))
        assert ec.resolve_media_path("no_existe.pdf") is None

    def test_relativo_sin_extension_encuentra_candidato(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ec, "PDF_LOCAL_PATH", str(tmp_path))
        (tmp_path / "Video1.mp4").write_bytes(b"x")
        assert ec.resolve_media_path("Video1") == os.path.join(str(tmp_path), "Video1.mp4")


# ─────────────────────────── ensure_sent_column ───────────────────────────
class TestEnsureSentColumn:
    def test_columna_existente_devuelve_indice_1based(self):
        sheet = MagicMock()
        sheet.row_values.return_value = ["Fecha", "Tienda", "ENVIADO_WA"]
        assert ec.ensure_sent_column(sheet) == 3
        sheet.update_cell.assert_not_called()

    def test_columna_existente_case_insensitive(self):
        sheet = MagicMock()
        sheet.row_values.return_value = ["Fecha", "enviado_wa"]
        assert ec.ensure_sent_column(sheet) == 2

    def test_columna_inexistente_se_crea_al_final(self):
        sheet = MagicMock()
        sheet.row_values.return_value = ["Fecha", "Tienda", "Estado"]
        col = ec.ensure_sent_column(sheet)
        assert col == 4
        sheet.update_cell.assert_called_once_with(1, 4, "ENVIADO_WA")

    def test_bug_conocido_fallo_de_lectura_devuelve_col_1_corrompible(self):
        # BUG conocido C4 (auditoría): si row_values falla, headers=[] → col=1
        # (misma columna que 'fecha'), lo que puede corromper la hoja. Caracterizado, NO corregido.
        sheet = MagicMock()
        sheet.row_values.side_effect = Exception("rate limit")
        assert ec.ensure_sent_column(sheet) == 1

    def test_bug_conocido_fallo_de_update_cell_igual_devuelve_indice(self):
        # BUG conocido (auditoría H6): si update_cell falla, solo imprime y devuelve col
        # como si el header se hubiera creado (fallo silencioso). Caracterizado, NO corregido.
        sheet = MagicMock()
        sheet.row_values.return_value = ["Fecha", "Tienda"]
        sheet.update_cell.side_effect = Exception("permiso denegado")
        assert ec.ensure_sent_column(sheet) == 3
