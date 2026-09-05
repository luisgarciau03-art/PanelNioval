"""Plan 5 · T5.4 (M9) — healthcheck del contenedor.

Ni el `Dockerfile` ni `despliegue/docker-compose.yml` definian `HEALTHCHECK`.
Un contenedor que arranco pero no responde queda `Up` para Docker y para Caddy,
y el owner se entera cuando abre el panel.

Las tres condiciones de la ruta, y ninguna es cosmetica:

1. **Sin autenticacion.** Un healthcheck que necesita el token del panel no
   puede correr desde Docker.
2. **Sin tocar Google.** Un healthcheck que llama a Sheets reportaria enfermo
   un panel sano cada vez que Google tuviera un mal rato.
3. **Sin filtrar nada.** Es la unica ruta publica del panel: ni versiones de
   dependencias, ni rutas internas, ni si hay una corrida en curso.

CE8 (levantar el contenedor con la ruta rota y verlo `unhealthy` en `docker ps`)
NO se puede cerrar aqui: Docker no esta instalado en la maquina de desarrollo.
Es el gate 5 del owner. Lo que si se comprueba es todo lo demas.
"""
import json
import pathlib

import pytest

import app

RAIZ = pathlib.Path(app.__file__).parent


@pytest.fixture
def client():
    app.app.config["TESTING"] = True
    return app.app.test_client()


class TestLaRutaResponde:

    def test_devuelve_200(self, client):
        assert client.get("/salud").status_code == 200

    def test_devuelve_json(self, client):
        r = client.get("/salud")
        assert r.content_type.startswith("application/json")
        assert isinstance(r.get_json(), dict)

    def test_responde_sin_token(self, client, monkeypatch):
        """La condicion que la hace util: Docker no tiene el token del panel.

        Se activa la auth de verdad (se quita el bypass de los tests) para que
        esto pruebe algo: con `PANEL_AUTH_DESACTIVADA=1` TODAS las rutas
        responden sin token y el test no distinguiria nada.
        """
        monkeypatch.delenv("PANEL_AUTH_DESACTIVADA", raising=False)
        monkeypatch.setenv("PANEL_DASHBOARD_TOKEN", "t" * 32)
        assert client.get("/salud").status_code == 200

    def test_el_resto_del_panel_si_exige_token(self, client, monkeypatch):
        """Control en la direccion contraria: si con la auth activa cualquier
        ruta respondiera igual, el test de arriba no probaria nada.

        La ruta tiene que EXISTIR. La primera version usaba /api/ventas/data,
        que da 404 — y como el before_request de la auth corre ANTES del
        enrutado, devolvia 401 igual: el test pasaba sobre una ruta inexistente
        y no comprobaba nada del panel real.
        """
        monkeypatch.delenv("PANEL_AUTH_DESACTIVADA", raising=False)
        monkeypatch.setenv("PANEL_DASHBOARD_TOKEN", "t" * 32)
        assert client.get("/api/prospectos/contactos").status_code == 401


class TestNoTocaGoogle:
    """Un healthcheck que llama a una API externa reporta enfermo un panel sano
    cada vez que la API externa tiene un mal rato."""

    def test_no_llama_a_google(self, client, monkeypatch):
        def _explotar(*a, **k):
            raise AssertionError("/salud llamo a Google")

        monkeypatch.setattr(app, "get_gs_client", _explotar)
        monkeypatch.setattr(app, "get_worksheet", _explotar)
        monkeypatch.setattr(app, "get_data", _explotar)
        assert client.get("/salud").status_code == 200

    def test_responde_aunque_google_este_caido(self, client, monkeypatch):
        """Lo mismo por el otro lado: con el cliente reventando, /salud sigue
        diciendo que el panel esta vivo, porque lo esta."""
        monkeypatch.setattr(app, "get_gs_client", lambda: (_ for _ in ()).throw(
            RuntimeError("Google caido")))
        assert client.get("/salud").status_code == 200

    def test_el_guarda_detecta_una_llamada_de_verdad(self, client, monkeypatch):
        """Direccion util: si el arnes no viera una llamada real, su verde no
        valdria nada. Se comprueba sobre una ruta que SI llama a Google."""
        llamadas = {"n": 0}

        def _contar(*a, **k):
            llamadas["n"] += 1
            raise RuntimeError("sin credenciales")

        monkeypatch.setattr(app, "get_gs_client", _contar)
        client.get("/api/prospectos/contactos")
        assert llamadas["n"] > 0, (
            "el arnes no detecta una llamada a Google ni cuando la hay"
        )


class TestNoFiltraNada:
    """Es la unica ruta publica del panel: todo lo que devuelva lo ve
    cualquiera desde internet, sin autenticarse."""

    CAMPOS_PERMITIDOS = {"ok"}

    def test_el_cuerpo_es_minimo(self, client):
        cuerpo = client.get("/salud").get_json()
        sobrantes = set(cuerpo) - self.CAMPOS_PERMITIDOS
        assert sobrantes == set(), (
            f"/salud expone campos de mas: {sobrantes}. Es la unica ruta sin "
            "auth del panel."
        )

    @pytest.mark.parametrize("prohibido", [
        "version", "versions", "python", "flask", "gspread", "commit",
        "build", "hostname", "host", "pid", "path", "rutas", "endpoints",
        "ciudad", "categoria", "status", "corrida", "importador", "job",
        "token", "secret", "key", "credential", "env",
    ])
    def test_no_menciona_nada_sensible(self, client, prohibido):
        texto = json.dumps(client.get("/salud").get_json()).lower()
        assert prohibido not in texto, f"/salud menciona '{prohibido}'"

    def test_no_dice_si_hay_una_corrida_en_curso(self, client):
        """Saber si el importador esta corriendo es informacion de operacion, y
        ademas cambiaria la respuesta segun el estado: un healthcheck debe
        contestar lo mismo siempre que el proceso este vivo."""
        with app._import_lock:
            app._import_job["status"] = "running"
        corriendo = client.get("/salud").get_json()
        with app._import_lock:
            app._import_job["status"] = "idle"
        parado = client.get("/salud").get_json()
        assert corriendo == parado, (
            "la respuesta cambia segun el estado interno: eso lo filtra"
        )


class TestNoRompeElRateLimiting:
    """Docker sondea /salud cada pocos segundos. Si esa ruta llega a devolver
    429, Docker marcaria el contenedor `unhealthy` estando sano: el limitador
    convertiria el healthcheck en una fuente de alarmas falsas."""

    def test_tiene_un_limite_propio_y_holgado(self):
        assert hasattr(app, "LIMITE_SALUD")

    def test_aguanta_la_cadencia_de_docker(self, client):
        """Con `interval=10s` son 6/minuto; se prueban 200 muy por encima del
        limite por defecto de 60/minuto."""
        app.limiter.enabled = True
        with app.app.app_context():
            app.limiter.reset()
        try:
            codigos = [client.get("/salud").status_code for _ in range(200)]
        finally:
            app.limiter.enabled = False
            with app.app.app_context():
                app.limiter.reset()
        assert 429 not in codigos, "el limitador tumbaria el healthcheck"

    def test_no_esta_exenta_del_limitador(self):
        """Holgada no es lo mismo que exenta: CE1 exige que ninguna ruta lo
        este, y esta es la unica publica — la mas facil de martillear.

        Se comprueba por COMPORTAMIENTO, no leyendo `_route_exemptions`. Esa es
        API privada y la version anterior la leia con `getattr(..., {})`: si
        Flask-Limiter la renombra, el fallback devuelve un dict vacio y el test
        pasa SIEMPRE, aunque alguien exima la ruta de verdad. Es el mismo guarda
        que se apaga en silencio que ya aparecio en CE1.

        Se mandan 800 peticiones, por encima del limite real de la ruta
        (LIMITE_SALUD, 600/minuto). Si ninguna devuelve 429, el limitador no la
        esta mirando.

        No se intenta bajar LIMITE_SALUD con monkeypatch: el decorador
        `@limiter.limit(LIMITE_SALUD)` capturo la cadena al importar el modulo,
        asi que sustituir el atributo despues no cambia el limite aplicado. Una
        linea asi habria hecho creer que el test prueba algo que no prueba.
        """
        limite_original = app.app.view_functions["salud"]
        app.limiter.enabled = True
        with app.app.app_context():
            app.limiter.reset()
        try:
            codigos = [app.app.test_client().get("/salud").status_code
                       for _ in range(800)]
        finally:
            app.limiter.enabled = False
            with app.app.app_context():
                app.limiter.reset()
        assert limite_original is app.app.view_functions["salud"]
        assert 429 in codigos, (
            "800 peticiones sin un solo 429: /salud no esta pasando por el "
            "limitador"
        )


class TestDeclaracionEnLosDosSitios:
    """`Dockerfile` y `docker-compose.yml` deben declararlo los dos: la copia
    viva del compose esta en /srv/panel/ del VPS y es la que manda ahi, pero la
    imagen tambien se construye sola en otros contextos."""

    def test_el_dockerfile_declara_healthcheck(self):
        df = (RAIZ / "Dockerfile").read_text(encoding="utf-8")
        assert "HEALTHCHECK" in df
        assert "/salud" in df

    def test_el_compose_declara_healthcheck(self):
        compose = (RAIZ / "despliegue" / "docker-compose.yml").read_text(encoding="utf-8")
        assert "healthcheck:" in compose
        assert "/salud" in compose

    def test_el_healthcheck_no_usa_curl(self):
        """`python:3.11-slim` no trae curl ni wget: un HEALTHCHECK que los use
        falla SIEMPRE y marca el contenedor unhealthy estando sano. Es el error
        clasico y silencioso de esta directiva."""
        df = (RAIZ / "Dockerfile").read_text(encoding="utf-8")
        linea = [l for l in df.splitlines() if l.startswith("HEALTHCHECK")
                 or "/salud" in l]
        texto = "\n".join(linea)
        assert "curl" not in texto and "wget" not in texto, (
            f"el healthcheck usa una herramienta que la imagen no trae: {texto}"
        )


def test_el_dockerfile_y_el_compose_declaran_lo_mismo():
    """Los dos declaran healthcheck y `docker compose up` usa el del compose,
    mientras que un `docker run` suelto usa el de la imagen. Comprobar solo que
    ambos EXISTEN deja que diverjan en silencio: un cambio de `interval` o de
    `retries` en un solo sitio dejaria las dos formas de arranque con salud
    distinta y la suite en verde.
    """
    import re

    df = (RAIZ / "Dockerfile").read_text(encoding="utf-8")
    cp = (RAIZ / "despliegue" / "docker-compose.yml").read_text(encoding="utf-8")

    linea = [l for l in df.splitlines() if l.startswith("HEALTHCHECK")]
    assert len(linea) == 1, f"esperaba 1 directiva HEALTHCHECK, hay {len(linea)}"
    del_df = dict(re.findall(r"--(\w[\w-]*)=(\w+)", linea[0]))
    del_cp = {
        "interval": re.search(r"^\s+interval:\s*(\S+)", cp, re.M).group(1),
        "timeout": re.search(r"^\s+timeout:\s*(\S+)", cp, re.M).group(1),
        "start-period": re.search(r"^\s+start_period:\s*(\S+)", cp, re.M).group(1),
        "retries": re.search(r"^\s+retries:\s*(\S+)", cp, re.M).group(1),
    }
    assert del_df == del_cp, f"divergen: Dockerfile={del_df} compose={del_cp}"

    # Y la sonda tiene que ser la misma, incluido el ProxyHandler.
    for texto, nombre in ((df, "Dockerfile"), (cp, "docker-compose.yml")):
        assert "ProxyHandler" in texto, (
            f"{nombre}: la sonda no desactiva los proxies del entorno. En Linux "
            "urllib no exceptua 127.0.0.1, y el compose carga secretos/.env "
            "entero: un HTTP_PROXY ahi mandaria el healthcheck a la red."
        )
        assert "/salud" in texto
