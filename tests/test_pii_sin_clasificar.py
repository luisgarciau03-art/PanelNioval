"""La promesa del endpoint de ciudades tiene que ser cierta.

`/api/importador/ciudades` promete en su docstring:

    "Devuelve SOLO agregados por ciudad. Ningun telefono ni nombre de contacto
     sale de aqui, aunque el origen sea la hoja de clientes."

Y era **falso**. Medido en produccion el 2026-09-16: de 32 entradas de
`sin_clasificar`, **9 eran datos personales** -- 8 telefonos y 1 correo. No es un
fallo de diseno: son celdas de la columna CIUDAD donde alguien tecleo un telefono, y
el camino de `sin_clasificar` las pasaba **verbatim**.

Lo peligroso no era la fuga -- el endpoint esta tras token y es el owner viendo sus
propios datos -- sino **la promesa incumplida**: alguien decidira manana que este
endpoint es seguro para un contexto nuevo apoyandose en un docstring que no se
cumple.

Estos tests fijan las dos mitades del arreglo, que son inseparables:

  1. Un telefono o un correo en esa columna **no sale** en claro.
  2. El aviso **sigue sirviendo**: los conteos no cambian y una ciudad legitima mal
     escrita se sigue viendo entera. Sanear escondiendo el problema seria peor que
     la fuga -- el operador dejaria de saber que tiene celdas que arreglar.
"""
import pytest

import app


class TestNoSaleUnTelefonoEnClaro:

    @pytest.mark.parametrize("crudo", [
        "6141234519",
        "614 123 4590",
        "+52 614 123 4544",
        "5551234573",
        "52-771-123-4545",
    ])
    def test_un_telefono_se_enmascara(self, crudo):
        salida = app._sanear_etiqueta_ciudad(crudo)

        assert crudo not in salida, f"salio verbatim: {salida!r}"
        # Los digitos del medio no pueden quedar legibles.
        assert "1234" not in salida.replace("…", "")

    def test_queda_algo_para_poder_encontrar_la_celda(self):
        """Enmascarar no es borrar: el operador tiene que poder ubicar la fila."""
        salida = app._sanear_etiqueta_ciudad("6141234519")

        assert salida, "se devolvio vacio: la celda se vuelve imposible de encontrar"
        assert "19" in salida or "614" in salida


class TestNoSaleUnCorreoEnClaro:

    def test_un_correo_se_enmascara(self):
        salida = app._sanear_etiqueta_ciudad("Copiadoras.Mx@gmail.com")

        assert "Copiadoras.Mx" not in salida
        assert "gmail.com" not in salida

    def test_pero_se_ve_que_ERA_un_correo(self):
        assert "@" in app._sanear_etiqueta_ciudad("Copiadoras.Mx@gmail.com")


class TestLoLEGITIMO_NO_SE_TOCA:
    """La otra direccion, y es la que hace util el arreglo.

    Un saneador que enmascara de mas deja al operador sin saber que celdas
    arreglar, que es justo el trabajo que `sin_clasificar` existe para permitir.
    """

    @pytest.mark.parametrize("crudo", [
        "Chiapas", "Nayarit", "San Luis", "Sin ciudad",
        "Cd. Juárez", "León", "Dos Ríos", "Tlaxcala",
        "San Juan del Río", "Zona 5",            # un numero suelto NO es un telefono
        "Km 23 Carretera", "Sector 2",
    ])
    def test_un_valor_legitimo_sale_entero(self, crudo):
        assert app._sanear_etiqueta_ciudad(crudo) == crudo


class TestElEndpointCumpleSuPromesa:

    def test_sin_clasificar_no_publica_el_telefono_crudo(self, monkeypatch):
        """De extremo a extremo: lo que sale por el endpoint, no la funcion suelta."""
        contactos = [
            {"Ciudad": "6141234519", "Nombre": "N1", "Telefono": "6141234519"},
            {"Ciudad": "Chiapas", "Nombre": "N2", "Telefono": "5551112222"},
        ]
        monkeypatch.setattr(app, "get_data", lambda _q: contactos)
        monkeypatch.setattr(app, "get_all_respuestas", lambda: [])

        app.app.config["TESTING"] = True
        datos = app.app.test_client().get("/api/importador/ciudades").get_json()

        crudo = " ".join(c["ciudad"] for c in datos["sin_clasificar"])
        assert "6141234519" not in crudo, f"el telefono salio verbatim: {crudo!r}"
        assert "Chiapas" in crudo, "se enmascaro un valor legitimo"

    def test_los_conteos_no_cambian_al_sanear(self, monkeypatch):
        """Sanear la ETIQUETA no puede alterar la aritmetica del aviso."""
        contactos = [{"Ciudad": "6141234519", "Nombre": "N%d" % i,
                      "Telefono": "555000000%d" % i} for i in range(3)]
        monkeypatch.setattr(app, "get_data", lambda _q: contactos)
        monkeypatch.setattr(app, "get_all_respuestas", lambda: [])

        app.app.config["TESTING"] = True
        datos = app.app.test_client().get("/api/importador/ciudades").get_json()

        assert sum(c["total"] for c in datos["sin_clasificar"]) == 3


class TestLaRutaHERMANA_TambienCumple:
    """`/api/prospectos/ciudades` publica la MISMA columna, y filtraba igual de mal.

    La auditoria del 2026-09-16 ya lo decia: *"el endpoint viejo publica exactamente
    los mismos 8 patrones y la misma arroba"*. Arreglar solo uno de los dos habria
    dejado la promesa rota por la puerta de al lado.

    Su consumidor (`dashboard.js`) usa `ciudad` como **etiqueta de busqueda**, no
    como clave de union, asi que enmascarar no rompe nada: un telefono deja de
    aparecer cuando el operador teclea el nombre de una ciudad, que es lo correcto.
    """

    def test_no_publica_el_telefono_crudo(self, monkeypatch):
        contactos = [
            {"Ciudad": "6141234519", "Nombre": "N1", "Telefono": "6141234519"},
            {"Ciudad": "Chiapas", "Nombre": "N2", "Telefono": "5551112222"},
        ]
        monkeypatch.setattr(app, "get_data", lambda _q: contactos)
        monkeypatch.setattr(app, "get_all_respuestas", lambda: [])

        app.app.config["TESTING"] = True
        datos = app.app.test_client().get("/api/prospectos/ciudades").get_json()

        crudo = " ".join(str(c.get("ciudad", "")) for c in datos)
        assert "6141234519" not in crudo, f"el telefono salio verbatim: {crudo!r}"
        assert "Chiapas" in crudo, "se enmascaro un valor legitimo"

    def test_no_pierde_filas_al_sanear(self, monkeypatch):
        contactos = [{"Ciudad": "6141234519", "Nombre": "N1", "Telefono": "1"},
                     {"Ciudad": "Chiapas", "Nombre": "N2", "Telefono": "2"}]
        monkeypatch.setattr(app, "get_data", lambda _q: contactos)
        monkeypatch.setattr(app, "get_all_respuestas", lambda: [])

        app.app.config["TESTING"] = True
        datos = app.app.test_client().get("/api/prospectos/ciudades").get_json()

        assert len(datos) == 2, "sanear no puede hacer desaparecer un contacto real"


# ═══════════ Lo que encontro el gate de seguridad ═══════════

class TestElCorreoNoSeEscapaPorLaPUERTA_DE_ATRAS:
    """HIGH del gate: el detector exigia un punto DESPUES de la arroba.

    `juan_perez1234@gmail` -- un dominio truncado al teclear -- salia entero. Y el
    docstring promete que ningun *nombre de contacto* sale de aqui, no solo que no
    salgan correos bien formados.
    """

    @pytest.mark.parametrize("crudo", [
        "juan_perez1234@gmail",          # dominio sin TLD
        "ventas@nioval",
        "Copiadoras.Mx@gmail.com",
        "  ferreteria@hotmail.com  ",
    ])
    def test_cualquier_cosa_con_arroba_se_enmascara(self, crudo):
        salida = app._sanear_etiqueta_ciudad(crudo)

        assert "@" in salida, "se pierde la pista de que era un correo"
        for trozo in ("juan", "ventas", "Copiadoras", "ferreteria", "gmail", "hotmail", "nioval"):
            assert trozo not in salida, f"salio {trozo!r} en claro: {salida!r}"


class TestElEnmascaradoSIGUE_LA_CONVENCION_DEL_PROYECTO:
    """MEDIUM del gate: `nucleo_catalogo.enmascarar_telefono` deja SOLO los ultimos 4.

    Dos funciones de la misma base de codigo con el mismo proposito no pueden dar
    garantias distintas. Y el prefijo de lada no hacia falta para localizar la fila:
    los ultimos digitos ya desambiguan entre 32 entradas.
    """

    def test_no_se_publica_la_lada(self):
        salida = app._sanear_etiqueta_ciudad("6141234519")

        assert "614" not in salida, f"la lada sigue publicandose: {salida!r}"

    def test_pero_quedan_los_ultimos_digitos_para_ubicar_la_fila(self):
        assert "4519" in app._sanear_etiqueta_ciudad("6141234519")


class TestUnaDIRECCION_CON_NUMEROS_NO_ES_UN_TELEFONO:
    """MEDIUM del gate: sumar digitos dispersos por toda la celda daba falsos positivos.

    Enmascarar una direccion legitima no es una fuga, pero le quita al operador la
    visibilidad de una celda que si puede arreglar -- que es para lo que existe el
    aviso.
    """

    @pytest.mark.parametrize("crudo", [
        "Manzana 3 Lote 25 CP 31125",
        "Km 123.456 Carretera Federal 45",
        "Calle 5 de Mayo 123 Col. Centro 4",
    ])
    def test_sale_entera(self, crudo):
        assert app._sanear_etiqueta_ciudad(crudo) == crudo

    @pytest.mark.parametrize("crudo", [
        "6141234519", "614 123 4519", "+52 614 123 4519", "(614) 123-4519",
    ])
    def test_pero_una_racha_larga_de_digitos_SI_es_un_telefono(self, crudo):
        assert "4519" in app._sanear_etiqueta_ciudad(crudo)
        assert crudo.strip() != app._sanear_etiqueta_ciudad(crudo)
