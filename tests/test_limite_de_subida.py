"""Un comprobante de pago no puede tumbar el panel.

`/api/ventas/upload-pago` -- otra de las rutas sin cobertura -- hace:

    contenido = archivo.read()          # el cuerpo ENTERO en memoria
    img_b64 = base64.b64encode(contenido)   # y otra copia, un 33 % mayor

Sin `MAX_CONTENT_LENGTH`, Flask acepta el cuerpo que le manden. Subir un video en
vez de una foto -- un descuido corriente desde el movil -- carga cientos de MB en un
contenedor con `mem_limit`, y el panel se cae **para todos**, no solo para quien
subio el archivo.

No es un agujero de seguridad: la ruta esta tras token. Es disponibilidad, y el
arreglo es el estandar de Flask: un tope que convierte el problema en un **413
limpio** en vez de un OOM.

⚠️ Lo que este tope NO hace: no valida que sea una imagen, ni cambia que el archivo
se suba a **ImgBB**, un hosting publico de terceros. Eso ultimo es una decision de
diseño que esta escrita en el codigo ("evita limite de cuota de Drive") y **no se
toca aqui** -- pero conviene saber que los comprobantes de pago de clientes salen a
un tercero.
"""
import io

import pytest

import app


@pytest.fixture
def cliente():
    app.app.config["TESTING"] = True
    return app.app.test_client()


class TestHayUnTope:

    def test_la_app_declara_MAX_CONTENT_LENGTH(self):
        tope = app.app.config.get("MAX_CONTENT_LENGTH")

        assert tope, ("sin tope, `archivo.read()` carga en memoria lo que le manden "
                      "y el contenedor muere por OOM")

    def test_el_tope_es_razonable_para_una_foto_de_comprobante(self):
        tope = app.app.config["MAX_CONTENT_LENGTH"]

        assert 1 * 1024 * 1024 <= tope <= 32 * 1024 * 1024, (
            f"{tope} bytes: o no deja subir una foto de movil, o no protege de nada")


class TestUnCuerpoENORME_SE_RECHAZA_LIMPIO:

    def test_responde_413_en_vez_de_morir(self, cliente):
        tope = app.app.config["MAX_CONTENT_LENGTH"]
        gordo = b"x" * (tope + 1024)

        r = cliente.post("/api/ventas/upload-pago", data={
            "num_factura": "F-1",
            "imagen": (io.BytesIO(gordo), "video.mp4"),
        }, content_type="multipart/form-data")

        assert r.status_code == 413, (
            f"respondio {r.status_code}: el cuerpo entero llego a memoria")


class TestUNA_FOTO_NORMAL_SIGUE_PASANDO:
    """La otra direccion. Un tope que rechaza lo legitimo es peor que no tenerlo:
    el operador dejaria de poder registrar pagos."""

    def test_una_imagen_de_tamano_corriente_no_la_corta_el_tope(self, cliente, monkeypatch):
        monkeypatch.delenv("IMGBB_API_KEY", raising=False)
        foto = b"\xff\xd8\xff" + b"x" * (2 * 1024 * 1024)      # ~2 MB, como una foto

        r = cliente.post("/api/ventas/upload-pago", data={
            "num_factura": "F-1",
            "imagen": (io.BytesIO(foto), "comprobante.jpg"),
        }, content_type="multipart/form-data")

        assert r.status_code != 413, "el tope corta una foto de tamaño normal"
        # Sin IMGBB_API_KEY la ruta devuelve 500 con su motivo: eso es que LLEGO.
        assert r.status_code == 500 and "IMGBB_API_KEY" in r.get_json().get("error", "")

    def test_sin_num_factura_sigue_siendo_400_y_no_413(self, cliente):
        r = cliente.post("/api/ventas/upload-pago", data={
            "imagen": (io.BytesIO(b"x" * 1024), "c.jpg"),
        }, content_type="multipart/form-data")

        assert r.status_code == 400
