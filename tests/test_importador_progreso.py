"""Progreso real y continuo del importador (Plan 3 - T3.6, defecto B6).

`_import_job['progreso'] = i` con `i` el indice de la categoria. Con dos
categorias, el progreso solo valia 0, 1 o 2: la barra estaba en 0 % durante toda
la primera categoria, que son minutos, y parecia congelada.

El denominador se implementa AJUSTABLE desde el principio: el Plan 2 (T2.4) va a
cortar variaciones que no aportan, y entonces el total deja de ser fijo. Que la
fraccion no retroceda al ajustarse es requisito, no detalle.
"""
import sys
import os

import pytest

import app

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_importador_conteo import (  # noqa: E402
    GmapsFalso, WorksheetFalsa, negocio, catalogo, escenario_veinte_contra_diez,
)


@pytest.fixture
def entorno(monkeypatch):
    monkeypatch.setattr(app, "GMAPS_OK", True)
    monkeypatch.setattr(app, "_enviar_telegram_importador", lambda *a, **k: None)
    monkeypatch.setattr(app, "_guardar_estado_importador", lambda *a, **k: None)
    monkeypatch.setattr(app.time, "sleep", lambda _s: None)
    monkeypatch.setattr(app, "_import_job",
                        app._nuevo_import_job("CiudadDemo", status="running"))
    return monkeypatch


def correr_capturando(monkeypatch, gmaps, ws):
    """Corre el worker anotando la fraccion y la fase en cada cambio de estado."""
    muestras = []
    real = app._avanzar_progreso

    def espia(job, *a, **k):
        r = real(job, *a, **k)
        muestras.append((job.get("fraccion"), job.get("fase")))
        return r

    monkeypatch.setattr(app, "_avanzar_progreso", espia)
    monkeypatch.setattr(app.googlemaps, "Client", lambda key=None, **k: gmaps)
    monkeypatch.setattr(app, "get_worksheet", lambda _n: ws)
    app._worker_importador("CiudadDemo", "clave-falsa")
    return muestras


class TestProgresoContinuo:
    def test_progreso_es_monotono_no_decreciente(self, entorno):
        gmaps, ws = escenario_veinte_contra_diez()
        muestras = correr_capturando(entorno, gmaps, ws)
        fracciones = [f for f, _ in muestras if f is not None]
        assert fracciones, "no se registro ninguna fraccion de progreso"
        for antes, despues in zip(fracciones, fracciones[1:]):
            assert despues >= antes, (
                "la barra retrocedio de %s a %s en la secuencia %r"
                % (antes, despues, fracciones)
            )

    def test_progreso_tiene_mas_de_tres_valores_distintos(self, entorno):
        gmaps, ws = escenario_veinte_contra_diez()
        muestras = correr_capturando(entorno, gmaps, ws)
        distintos = {f for f, _ in muestras if f is not None}
        assert len(distintos) > 3, (
            "la barra sigue teniendo %d valores (%r): con 0/50/100 parece congelada"
            % (len(distintos), sorted(distintos))
        )

    def test_no_arranca_en_cero(self, entorno):
        """Al empezar la primera categoria ya hay un paso hecho."""
        gmaps, ws = escenario_veinte_contra_diez()
        muestras = correr_capturando(entorno, gmaps, ws)
        primera = next(f for f, _ in muestras if f is not None)
        assert primera > 0, "la barra arranca en 0 % y parece que no pasa nada"

    def test_termina_en_cien(self, entorno):
        gmaps, ws = escenario_veinte_contra_diez()
        muestras = correr_capturando(entorno, gmaps, ws)
        assert muestras[-1][0] == 100, "la corrida acabo en %r" % muestras[-1][0]

    def test_la_etiqueta_de_fase_nombra_categoria_variacion_y_pagina(self, entorno):
        gmaps, ws = escenario_veinte_contra_diez()
        muestras = correr_capturando(entorno, gmaps, ws)
        fases = [f for _, f in muestras if f]
        assert any("variación" in f for f in fases), (
            "ninguna fase menciona la variacion: %r" % fases
        )
        assert any("Ferreterías" in f for f in fases), (
            "ninguna fase nombra la categoria: %r" % fases
        )
        assert any("Sheets" in f or "Guardando" in f for f in fases), (
            "no se avisa de la escritura en Sheets: %r" % fases
        )


class TestDenominadorAjustable:
    """El Plan 2 (T2.4) va a cortar variaciones, asi que el total cambiara."""

    def test_denominador_se_ajusta_sin_que_la_fraccion_baje(self):
        job = app._nuevo_import_job("X", status="running")
        app._avanzar_progreso(job, hechos=5, total=10)          # 50 %
        antes = job["fraccion"]
        app._avanzar_progreso(job, hechos=5, total=20)          # seria 25 %
        assert job["fraccion"] >= antes, (
            "ampliar el total hizo retroceder la barra de %s a %s"
            % (antes, job["fraccion"])
        )

    def test_recortar_el_total_si_puede_adelantar(self):
        job = app._nuevo_import_job("X", status="running")
        app._avanzar_progreso(job, hechos=5, total=20)          # 25 %
        app._avanzar_progreso(job, hechos=5, total=10)          # 50 %
        assert job["fraccion"] == 50

    def test_nunca_pasa_de_cien(self):
        job = app._nuevo_import_job("X", status="running")
        app._avanzar_progreso(job, hechos=99, total=10)
        assert job["fraccion"] == 100

    def test_total_cero_no_revienta(self):
        job = app._nuevo_import_job("X", status="running")
        app._avanzar_progreso(job, hechos=0, total=0)
        assert isinstance(job["fraccion"], int)


class TestEstadoExponeElProgreso:
    @pytest.fixture
    def client(self):
        app.app.config["TESTING"] = True
        return app.app.test_client()

    def test_el_endpoint_expone_fraccion_y_fase(self, client, entorno):
        gmaps, ws = escenario_veinte_contra_diez()
        correr_capturando(entorno, gmaps, ws)
        d = client.get("/api/importador/estado").get_json()
        assert "fraccion" in d, "/api/importador/estado no expone la fraccion"
        assert "fase" in d, "/api/importador/estado no expone la fase"


class GmapsConPaginacion:
    """Places devuelve `next_page_token`: hay mas de una pagina de resultados.

    Ninguna prueba cubria esta rama, y es justo la que el Plan 2 va a tocar al
    recortar variaciones: es donde el denominador deja de ser fijo.
    """

    def __init__(self, paginas=2):
        self.paginas = paginas
        self.llamadas = 0

    def places(self, query=None, page_token=None, **kw):
        self.llamadas += 1
        lote = [negocio("Neg %d" % self.llamadas, "pid-%d" % self.llamadas,
                        "Calle %d" % self.llamadas)]
        # Solo las primeras paginas de cada variacion ofrecen continuacion.
        if page_token is None and self.paginas > 1:
            return {"results": lote, "next_page_token": "tok-1"}
        if page_token == "tok-1" and self.paginas > 2:
            return {"results": lote, "next_page_token": "tok-2"}
        return {"results": lote}

    def place(self, pid, **kw):
        return {"result": {"formatted_phone_number": "+52 33 1234 5678"}}


class TestProgresoConPaginacion:
    def test_la_fase_nombra_la_pagina(self, entorno):
        muestras = correr_capturando(entorno, GmapsConPaginacion(paginas=2),
                                     WorksheetFalsa())
        fases = [f for _, f in muestras if f]
        assert any("página" in f for f in fases), (
            "con paginacion, ninguna fase menciona la pagina: %r" % fases
        )

    def test_las_paginas_no_desbordan_la_barra(self, entorno):
        """Las paginas son trabajo descubierto: crecen numerador Y denominador.

        Si solo creciera el numerador, la barra llegaria a 100 % antes de tiempo
        y se quedaria clavada ahi el resto de la corrida.
        """
        muestras = correr_capturando(entorno, GmapsConPaginacion(paginas=3),
                                     WorksheetFalsa())
        fracciones = [f for f, _ in muestras if f is not None]
        # Ningun 100 % antes del ultimo tramo.
        assert fracciones[-1] == 100
        # Nada de 100 % mientras todavia queda trabajo: el ultimo tramo esta
        # reservado para el cierre.
        assert all(f < 100 for f in fracciones[:-3]), (
            "la barra llego al 100%% antes de terminar: %r" % fracciones
        )
        for antes, despues in zip(fracciones, fracciones[1:]):
            assert despues >= antes, "retrocedio: %r" % fracciones

    def test_sin_paginacion_no_hay_salto_de_categoria(self, entorno):
        """El caso comun: sin paginas, el presupuesto se cumple exactamente.

        Antes se presupuestaba el peor caso, asi que en la corrida normal solo se
        cumplia la mitad y la barra pegaba un salto de 25 puntos en cada frontera
        de categoria.
        """
        gmaps, ws = escenario_veinte_contra_diez()
        muestras = correr_capturando(entorno, gmaps, ws)
        fracciones = [f for f, _ in muestras if f is not None]
        saltos = [b - a for a, b in zip(fracciones, fracciones[1:])]
        assert max(saltos) <= 12, (
            "la barra da un salto de %d puntos: %r" % (max(saltos), fracciones)
        )
