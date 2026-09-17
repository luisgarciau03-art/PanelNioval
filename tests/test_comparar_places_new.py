"""Fase 0 del ADR `2026-09-15-ruta-de-telefono-places`: medir antes de migrar.

El ADR no autoriza migrar. Autoriza **trece llamadas que no escriben nada** y que
compran los dos numeros que le faltan a la decision:

  1. ¿La clave de deduplicacion construida desde la respuesta de Places API (New)
     casa con la que hoy tiene la hoja? Esa clave es `f"{nombre}|{direccion}"`
     (`app.py:_clave_contacto`) y se calcula en TRES sitios que deben coincidir
     caracter a caracter. Si divergen, la hoja se llena de duplicados **sin una
     sola excepcion ni un test rojo**. No hay ninguna guarda hoy.

  2. ¿Que porcentaje de negocios trae `nationalPhoneNumber`? Eso cierra CE1, que
     T2.1 dejo en rojo por no poder medirlo sin llamar a Google.

Estos tests NO tocan la red: comparan respuestas ya capturadas. La herramienta
separa el transporte (que si llama) de la comparacion (que es pura), justo para
que la parte que decide se pueda probar en las dos direcciones.
"""
import pytest

from tools.comparar_places_new import (
    clave_desde_legacy,
    clave_desde_new,
    comparar,
    tasa_con_telefono,
)


def legacy(pid, nombre, direccion):
    return {"place_id": pid, "name": nombre, "formatted_address": direccion}


def nuevo(pid, nombre, direccion, telefono=None):
    p = {"id": pid, "displayName": {"text": nombre}, "formattedAddress": direccion}
    if telefono:
        p["nationalPhoneNumber"] = telefono
    return p


class TestLaClaveSeConstruyeIgualQueEnLaHoja:
    """Si estas dos funciones no reproducen `_clave_contacto`, todo lo demas sobra."""

    def test_desde_legacy_sale_nombre_barra_direccion(self):
        assert clave_desde_legacy(legacy("p1", "Ferretería El Tornillo",
                                         "Av. Juárez 10, Puebla")) == \
            "Ferretería El Tornillo|Av. Juárez 10, Puebla"

    def test_desde_new_sale_la_misma_forma(self):
        assert clave_desde_new(nuevo("p1", "Ferretería El Tornillo",
                                     "Av. Juárez 10, Puebla")) == \
            "Ferretería El Tornillo|Av. Juárez 10, Puebla"

    def test_la_clave_es_la_del_codigo_de_produccion_no_una_copia(self):
        """Una copia a mano se queda vieja en cuanto `_clave_contacto` cambie."""
        import app
        assert clave_desde_legacy(legacy("p", "N", "D")) == app._clave_contacto("N", "D")


class TestSabeDecirQueSi:

    def test_claves_identicas_dan_100_por_ciento(self):
        ls = [legacy("p1", "Ferretería A", "Calle 1"),
              legacy("p2", "Ferretería B", "Calle 2")]
        ns = [nuevo("p1", "Ferretería A", "Calle 1"),
              nuevo("p2", "Ferretería B", "Calle 2")]

        r = comparar(ls, ns)

        assert r["emparejados"] == 2
        assert r["claves_iguales"] == 2
        assert r["tasa_coincidencia"] == 1.0
        assert r["discrepancias"] == []


class TestSabeDecirQueNo:
    """El defecto que la Fase 0 existe para cazar, y que no tiene guarda en produccion."""

    def test_una_direccion_formateada_distinto_se_reporta(self):
        ls = [legacy("p1", "Ferretería A", "Av. Juárez 10, Puebla, Pue.")]
        ns = [nuevo("p1", "Ferretería A", "Av. Juárez 10, 72000 Puebla, Pue., México")]

        r = comparar(ls, ns)

        assert r["tasa_coincidencia"] == 0.0
        assert len(r["discrepancias"]) == 1
        d = r["discrepancias"][0]
        assert d["legacy"] != d["new"], "hay que poder ver las DOS cadenas"
        assert "72000" in d["new"]

    def test_un_nombre_con_sufijo_distinto_tambien(self):
        ls = [legacy("p1", "Ferretería A", "Calle 1")]
        ns = [nuevo("p1", "Ferretería A S.A. de C.V.", "Calle 1")]

        assert comparar(ls, ns)["tasa_coincidencia"] == 0.0

    def test_una_sola_discrepancia_de_cien_baja_la_tasa_por_debajo_del_99(self):
        """El ADR cancela la migracion por debajo del 99 %. El umbral tiene que
        poder distinguir 99 de 100, no redondear a «casi todo bien»."""
        ls = [legacy("p%d" % i, "F%d" % i, "C%d" % i) for i in range(100)]
        ns = [nuevo("p%d" % i, "F%d" % i, "C%d" % i) for i in range(99)]
        ns.append(nuevo("p99", "F99", "C99 (interior 2)"))

        r = comparar(ls, ns)

        assert r["tasa_coincidencia"] == 0.99
        assert r["tasa_coincidencia"] < 0.995


class TestLoQueNoSePuedeEmparejarNoSeCuenta:
    """Un negocio que solo devuelve una de las dos APIs no dice nada de la clave."""

    def test_los_no_emparejados_se_reportan_aparte(self):
        ls = [legacy("p1", "A", "C1"), legacy("p2", "B", "C2")]
        ns = [nuevo("p1", "A", "C1"), nuevo("p3", "C", "C3")]

        r = comparar(ls, ns)

        assert r["emparejados"] == 1
        assert r["tasa_coincidencia"] == 1.0
        assert r["solo_en_legacy"] == ["p2"]
        assert r["solo_en_new"] == ["p3"]

    def test_sin_ningun_emparejado_la_tasa_es_None_no_cero(self):
        """Cero seria «todas mal». None es «no pude medirlo», que es distinto."""
        r = comparar([legacy("p1", "A", "C1")], [nuevo("p2", "B", "C2")])

        assert r["emparejados"] == 0
        assert r["tasa_coincidencia"] is None


class TestCE1LaTasaDeTelefono:

    def test_cuenta_los_que_traen_nationalPhoneNumber(self):
        ns = [nuevo("p1", "A", "C1", telefono="222 123 4567"),
              nuevo("p2", "B", "C2"),
              nuevo("p3", "C", "C3", telefono="222 765 4321"),
              nuevo("p4", "D", "C4")]

        r = tasa_con_telefono(ns)

        assert r["total"] == 4
        assert r["con_telefono"] == 2
        assert r["sin_telefono"] == 2
        assert r["tasa_sin_telefono"] == 0.5

    def test_una_cadena_vacia_no_cuenta_como_telefono(self):
        """El campo PRESENTE pero vacio es distinto del campo ausente.

        La primera version de este test usaba el helper `nuevo(telefono="")`, que
        por su `if telefono:` **no anadia la clave**: comprobaba el caso ausente y
        daba verde aunque la implementacion contara por `in`. Lo destapo la
        mutacion. Aqui la clave se pone a mano, vacia.
        """
        vacio = {"id": "p1", "displayName": {"text": "A"}, "formattedAddress": "C1",
                 "nationalPhoneNumber": ""}
        espacios = {"id": "p2", "displayName": {"text": "B"}, "formattedAddress": "C2",
                    "nationalPhoneNumber": "   "}

        r = tasa_con_telefono([vacio, espacios])

        assert r["con_telefono"] == 0
        assert r["sin_telefono"] == 2

    def test_sin_lugares_la_tasa_es_None(self):
        assert tasa_con_telefono([])["tasa_sin_telefono"] is None


class TestFallaCerrado:

    def test_sin_clave_de_api_no_llama_a_nadie(self, monkeypatch):
        import tools.comparar_places_new as mod
        monkeypatch.delenv("GMAPS_API_KEY", raising=False)

        with pytest.raises(SystemExit):
            mod.exigir_clave()
