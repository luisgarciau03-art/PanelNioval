# Alta de PanelNioval en Vultr — Plan de Implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Poner PanelNioval en producción en el VPS Vultr existente, servido por TLS en `panelnioval.duckdns.org`, con autenticación fail-closed, apagar Railway y validar el sistema completo incluyendo la no-regresión de Bruce.

**Architecture:** Segundo servicio Docker en el servidor que ya hospeda a Bruce (`155.138.200.66`), replicando su patrón: contenedor sin puertos publicados en la red interna `web`, con Caddy como único expuesto haciendo TLS automático. Antes de exponer nada se invierten los dos gates de autenticación, que hoy abren por defecto cuando falta su variable de entorno.

**Tech Stack:** Flask 3 + gunicorn · Docker Compose · Caddy 2 · Google Sheets (gspread) · DuckDNS · pytest

**Spec:** [`docs/superpowers/specs/2026-08-17-panelnioval-vultr-design.md`](../specs/2026-08-17-panelnioval-vultr-design.md)

## Global Constraints

- **Rama:** nunca trabajar directo en `main`. Este plan se ejecuta en `feat/despliegue-vultr`. PRs con `gh pr create --base main`.
- **Baseline oficial:** `python -m pytest tests/ -q` → **144 passed**. Nada avanza en rojo. Importar `app.py` en frío tarda ~2 min (pandas/googleapiclient + Defender); en caliente ~8s.
- **Commits:** en español, prefijos convencionales (`fix:`, `feat:`, `test:`, `docs:`, `chore:`).
- **Credenciales:** ningún valor de token aparece en commits, informes, ni en la conversación. Se identifican por nombre de variable y `archivo:línea`. Los tokens se generan en el servidor y se quedan ahí.
- **Datos personales:** teléfonos y nombres de clientes no se commitean; anonimizar a `+52...XXXX`.
- **Hojas de producción:** se respeta el orden de columnas existente. No se inserta ni reordena nada: están sincronizadas con proyectos externos.
- **Fuera de alcance:** trocear `app.py`, tocar el importador de prospectos, migrar el worker Selenium al VPS.
- **Servidor:** `ssh root@155.138.200.66`. Bruce corre ahí con `WA_SCHEDULER=1`, `WA_GEO_AUTO=1`, `WA_BUSCADOR_AUTO=1`, `WA_CAMPANA_AUTO=0`.

---

## Estructura de archivos

| Archivo | Responsabilidad | Acción |
|---|---|---|
| `app.py:27-62` | Guardas de arranque + gate del panel | Modificar |
| `app.py:3491-3502` | Gate del heartbeat del worker | Modificar |
| `tests/conftest.py` | Escape hatch para la suite | Modificar |
| `tests/test_plan5_operacion.py` | Tests de auth (4 codifican fail-open) | Modificar |
| `Dockerfile` | Imagen del panel para el VPS | Crear |
| `despliegue/docker-compose.yml` | Plantilla versionada del servicio | Crear |
| `despliegue/Caddyfile.fragmento` | Bloque a añadir en `/srv/proxy/Caddyfile` | Crear |
| `tools/smoke_panel.py` | Smoke test post-deploy (renombrado) | Renombrar |
| `tools/respaldar_hojas.py` | Respaldo XLSX + huellas de encabezados | Crear (Task 12) |
| `iniciar-worker.bat:14,18` | URL del panel + `WORKER_TOKEN` | Modificar |
| `docs/RUNBOOK.md` | Sección de operación en VPS | Modificar |

**Decisión de diseño del escape hatch.** El gate en tiempo de request consulta `PANEL_AUTH_DESACTIVADA`, no la ausencia del token. Así `tests/conftest.py` lo activa una vez para los 6 archivos de test que importan `app`, y la clase `TestAuthPanel` lo *borra* con `monkeypatch` para ejercitar el gate real. Sin esa separación, activar el hatch globalmente volvería vacíos los tests de autenticación.

---

# FASE A — Código (local, TDD)

### Task 1: Escape hatch explícito y gate del panel fail-closed

**Files:**
- Modify: `app.py:39-62`
- Modify: `tests/conftest.py`
- Test: `tests/test_plan5_operacion.py:16-43`

**Interfaces:**
- Produces: `app._auth_desactivada() -> bool` — única lectura de `PANEL_AUTH_DESACTIVADA`. La usan las Tasks 2 y 3.

- [ ] **Step 1: Añadir el escape hatch al conftest**

En `tests/conftest.py`, ANTES de cualquier import de `app`, insertar tras el bloque de docstring (línea 8):

```python
import os

# La app es fail-closed: sin PANEL_DASHBOARD_TOKEN no arranca (ver app.py).
# La suite no prueba autenticación salvo en TestAuthPanel, que borra esta
# variable con monkeypatch para ejercitar el gate real.
os.environ.setdefault("PANEL_AUTH_DESACTIVADA", "1")
```

- [ ] **Step 2: Escribir el test que falla**

En `tests/test_plan5_operacion.py`, reemplazar la clase `TestAuthPanel` completa (líneas 16-43) por:

```python
# ─────────────────────── Auth del panel: fail-closed ───────────────────────
class TestAuthPanel:
    @pytest.fixture(autouse=True)
    def _sin_escape_hatch(self, monkeypatch):
        """Estos tests ejercitan el gate real, no el bypass de la suite."""
        monkeypatch.delenv("PANEL_AUTH_DESACTIVADA", raising=False)

    def test_sin_token_env_cierra(self, client, monkeypatch):
        monkeypatch.delenv("PANEL_DASHBOARD_TOKEN", raising=False)
        r = client.get("/api/catalogo/worker-estado")
        assert r.status_code == 401  # fail-closed: sin token no abre

    def test_con_token_env_sin_header_401(self, client, monkeypatch):
        monkeypatch.setenv("PANEL_DASHBOARD_TOKEN", "secreto123")
        r = client.get("/api/catalogo/worker-estado")
        assert r.status_code == 401

    def test_con_token_en_header_pasa(self, client, monkeypatch):
        monkeypatch.setenv("PANEL_DASHBOARD_TOKEN", "secreto123")
        r = client.get("/api/catalogo/worker-estado", headers={"X-Dashboard-Token": "secreto123"})
        assert r.status_code == 200

    def test_con_token_en_query_pasa(self, client, monkeypatch):
        monkeypatch.setenv("PANEL_DASHBOARD_TOKEN", "secreto123")
        r = client.get("/api/catalogo/worker-estado?token=secreto123")
        assert r.status_code == 200

    def test_escape_hatch_abre_solo_si_es_explicito(self, client, monkeypatch):
        monkeypatch.delenv("PANEL_DASHBOARD_TOKEN", raising=False)
        monkeypatch.setenv("PANEL_AUTH_DESACTIVADA", "1")
        r = client.get("/api/catalogo/worker-estado")
        assert r.status_code == 200
```

- [ ] **Step 3: Correr los tests para verificar que fallan**

Run: `python -m pytest tests/test_plan5_operacion.py::TestAuthPanel -v`
Expected: FAIL. `test_sin_token_env_cierra` devuelve 200 en vez de 401, y `test_escape_hatch_abre_solo_si_es_explicito` falla con `AttributeError` o 401 según el orden.

- [ ] **Step 4: Implementar el gate fail-closed**

En `app.py`, reemplazar el bloque de las líneas 39-62 por:

```python
# ─── AUTENTICACIÓN DEL PANEL (fail-closed) ───────────────────────────────────
# El panel exige PANEL_DASHBOARD_TOKEN en TODAS las rutas (header
# X-Dashboard-Token, ?token=, o cookie de sesión tras el primer acceso con
# ?token=). Si la variable falta, la app no arranca (ver guardas de arranque).
# Único bypass, explícito y ruidoso: PANEL_AUTH_DESACTIVADA=1 para desarrollo
# local y para la suite de tests. El default NUNCA abre.
_RUTAS_EXENTAS_AUTH = ('/api/catalogo/heartbeat',)  # el worker usa su propio WORKER_TOKEN


def _auth_desactivada() -> bool:
    """True solo si el operador desactivó la auth a propósito."""
    return os.environ.get('PANEL_AUTH_DESACTIVADA') == '1'


@app.before_request
def _requiere_token_panel():
    if _auth_desactivada():
        return
    path = request.path or ''
    if path.startswith(_RUTAS_EXENTAS_AUTH):
        return
    token = os.environ.get('PANEL_DASHBOARD_TOKEN')
    if not token:
        return jsonify({'ok': False, 'error': 'no autorizado'}), 401
    provisto = (request.headers.get('X-Dashboard-Token')
                or request.args.get('token')
                or session.get('dashboard_token'))
    if provisto and hmac.compare_digest(str(provisto), str(token)):
        if request.args.get('token') and hmac.compare_digest(str(request.args.get('token')), str(token)):
            session['dashboard_token'] = token  # recordar para la sesión del navegador
        return
    return jsonify({'ok': False, 'error': 'no autorizado'}), 401
```

- [ ] **Step 5: Correr los tests para verificar que pasan**

Run: `python -m pytest tests/test_plan5_operacion.py::TestAuthPanel -v`
Expected: PASS, 5 tests.

- [ ] **Step 6: Correr la suite completa**

Run: `python -m pytest tests/ -q`
Expected: fallan `TestSeccionCatalogo::test_dashboard_incluye_seccion_catalogo` y los de heartbeat — se arreglan en las Tasks 2 y 3. El resto en verde.

- [ ] **Step 7: Commit**

```bash
git add app.py tests/conftest.py tests/test_plan5_operacion.py
git commit -m "feat(auth): gate del panel fail-closed con escape hatch explicito

Sin PANEL_DASHBOARD_TOKEN el panel devolvia 200 en las 39 rutas. Ahora
cierra por defecto y solo abre con PANEL_AUTH_DESACTIVADA=1 puesta a
proposito. Invierte el test que codificaba el comportamiento abierto."
```

---

### Task 2: Heartbeat del worker fail-closed

**Files:**
- Modify: `app.py:3491-3502`
- Test: `tests/test_plan5_operacion.py:61-78`

**Interfaces:**
- Consumes: `app._auth_desactivada()` de la Task 1.

- [ ] **Step 1: Escribir el test que falla**

En `tests/test_plan5_operacion.py`, reemplazar la clase `TestHeartbeat` completa por:

```python
# ─────────────────────── Heartbeat del worker ───────────────────────
class TestHeartbeat:
    def test_worker_token_requerido_si_definido(self, client, monkeypatch):
        monkeypatch.delenv("PANEL_AUTH_DESACTIVADA", raising=False)
        monkeypatch.delenv("PANEL_DASHBOARD_TOKEN", raising=False)
        monkeypatch.setenv("WORKER_TOKEN", "w-secreto")
        r = client.post("/api/catalogo/heartbeat", json={})
        assert r.status_code == 401
        r2 = client.post("/api/catalogo/heartbeat", json={}, headers={"X-Worker-Token": "w-secreto"})
        assert r2.status_code == 200

    def test_sin_worker_token_cierra(self, client, monkeypatch):
        """Sin WORKER_TOKEN el heartbeat NO acepta escrituras anonimas."""
        monkeypatch.delenv("PANEL_AUTH_DESACTIVADA", raising=False)
        monkeypatch.delenv("WORKER_TOKEN", raising=False)
        r = client.post("/api/catalogo/heartbeat", json={"resumen": {"enviados": 1}})
        assert r.status_code == 401

    def test_estado_refleja_heartbeat(self, client, monkeypatch):
        monkeypatch.setenv("WORKER_TOKEN", "w-secreto")
        client.post("/api/catalogo/heartbeat",
                    json={"resumen": {"enviados": 2, "fallos": 0}},
                    headers={"X-Worker-Token": "w-secreto"})
        r = client.get("/api/catalogo/worker-estado")
        d = r.get_json()
        assert d["vivo"] is True
        assert d["resumen"] == {"enviados": 2, "fallos": 0}
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `python -m pytest tests/test_plan5_operacion.py::TestHeartbeat -v`
Expected: FAIL en `test_sin_worker_token_cierra` — devuelve 200 en vez de 401.

- [ ] **Step 3: Implementar**

En `app.py`, reemplazar las líneas 3491-3502 por:

```python
@app.route('/api/catalogo/heartbeat', methods=['POST'])
def catalogo_heartbeat():
    """El worker local reporta que está vivo. Exige WORKER_TOKEN (fail-closed)."""
    if not _auth_desactivada():
        esperado = os.environ.get('WORKER_TOKEN')
        provisto = request.headers.get('X-Worker-Token') or ''
        if not esperado or not hmac.compare_digest(str(provisto), str(esperado)):
            return jsonify({'ok': False, 'error': 'no autorizado'}), 401
    body = request.json or {}
    _worker_heartbeat['ts'] = time.time()
    _worker_heartbeat['resumen'] = body.get('resumen')
    return jsonify({'ok': True})
```

- [ ] **Step 4: Correr los tests para verificar que pasan**

Run: `python -m pytest tests/test_plan5_operacion.py::TestHeartbeat -v`
Expected: PASS, 3 tests.

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_plan5_operacion.py
git commit -m "feat(auth): heartbeat exige WORKER_TOKEN o devuelve 401

La ruta estaba exenta del gate del panel y su token era condicional, asi
que sin la variable era un endpoint de escritura abierto a internet."
```

---

### Task 3: Guardas de arranque

**Files:**
- Modify: `app.py:27-36`
- Test: `tests/test_plan5_operacion.py` (clase nueva al final)

- [ ] **Step 1: Escribir el test que falla**

Añadir al final de `tests/test_plan5_operacion.py`:

```python
# ─────────────────────── Guardas de arranque ───────────────────────
class TestGuardasArranque:
    """La app se niega a arrancar sin secretos. Un despliegue mal
    configurado revienta ruidosamente en vez de abrir el panel en silencio."""

    def test_sin_token_no_arranca(self, monkeypatch):
        monkeypatch.delenv("PANEL_AUTH_DESACTIVADA", raising=False)
        monkeypatch.delenv("PANEL_DASHBOARD_TOKEN", raising=False)
        monkeypatch.setenv("SECRET_KEY", "k" * 32)
        with pytest.raises(RuntimeError, match="PANEL_DASHBOARD_TOKEN"):
            importlib.reload(app)

    def test_sin_secret_key_no_arranca(self, monkeypatch):
        monkeypatch.delenv("PANEL_AUTH_DESACTIVADA", raising=False)
        monkeypatch.setenv("PANEL_DASHBOARD_TOKEN", "t" * 32)
        monkeypatch.delenv("SECRET_KEY", raising=False)
        with pytest.raises(RuntimeError, match="SECRET_KEY"):
            importlib.reload(app)

    def test_con_escape_hatch_arranca(self, monkeypatch):
        monkeypatch.setenv("PANEL_AUTH_DESACTIVADA", "1")
        monkeypatch.delenv("PANEL_DASHBOARD_TOKEN", raising=False)
        monkeypatch.delenv("SECRET_KEY", raising=False)
        importlib.reload(app)  # no lanza
        assert app.app is not None

    def test_con_secretos_arranca(self, monkeypatch):
        monkeypatch.delenv("PANEL_AUTH_DESACTIVADA", raising=False)
        monkeypatch.setenv("PANEL_DASHBOARD_TOKEN", "t" * 32)
        monkeypatch.setenv("SECRET_KEY", "k" * 32)
        importlib.reload(app)  # no lanza
        assert app.app is not None
```

> `importlib` y `pytest` ya están importados en la cabecera de este archivo (líneas 2 y 5).

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `python -m pytest tests/test_plan5_operacion.py::TestGuardasArranque -v`
Expected: FAIL. `importlib.reload(app)` no lanza nada; los dos primeros fallan con `DID NOT RAISE`.

- [ ] **Step 3: Implementar**

En `app.py`, reemplazar las líneas 27-36 por:

```python
app = Flask(__name__)
app.json.sort_keys = False

# ─── GUARDAS DE ARRANQUE (fail-closed) ───────────────────────────────────────
# Sin secretos la app NO arranca. Un despliegue mal configurado revienta aquí,
# ruidosamente, en vez de publicar el panel abierto. Bypass explícito para
# desarrollo local y tests: PANEL_AUTH_DESACTIVADA=1.
if os.environ.get('PANEL_AUTH_DESACTIVADA') != '1':
    if not os.environ.get('PANEL_DASHBOARD_TOKEN'):
        raise RuntimeError(
            'PANEL_DASHBOARD_TOKEN no está definida. El panel expone datos de '
            'clientes: no arranca sin token. Defínela en el entorno, o pon '
            'PANEL_AUTH_DESACTIVADA=1 si de verdad quieres el panel abierto.')
    if not os.environ.get('SECRET_KEY'):
        raise RuntimeError(
            'SECRET_KEY no está definida. Con varios workers de gunicorn una '
            'clave aleatoria por worker rompe las cookies de sesión de forma '
            'intermitente. Genera una fija y ponla en el entorno.')

app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(16))
# Cookie de sesión endurecida (el panel corre tras TLS).
app.config.update(SESSION_COOKIE_SECURE=True, SESSION_COOKIE_SAMESITE='Lax', SESSION_COOKIE_HTTPONLY=True)
```

> **Por qué aquí se lee la variable en crudo y no con `_auth_desactivada()`:** esta guarda
> corre en la línea 27, y la función se define en la 45. Llamarla aquí sería un
> `NameError`. Es la única lectura directa de `PANEL_AUTH_DESACTIVADA` en el archivo; el
> resto del código usa la función.

- [ ] **Step 4: Correr los tests para verificar que pasan**

Run: `python -m pytest tests/test_plan5_operacion.py::TestGuardasArranque -v`
Expected: PASS, 4 tests.

- [ ] **Step 5: Arreglar el test de la sección de catálogo**

`TestSeccionCatalogo::test_dashboard_incluye_seccion_catalogo` (línea ~49) borra `PANEL_DASHBOARD_TOKEN` y espera 200. Con el hatch del conftest activo ya pasa, pero la línea del `monkeypatch` sobra y confunde. Eliminarla:

```python
class TestSeccionCatalogo:
    def test_dashboard_incluye_seccion_catalogo(self, client):
        r = client.get("/")
        assert r.status_code == 200
```

(el resto de los `assert` del test se deja intacto)

- [ ] **Step 6: Correr la suite completa — baseline**

Run: `python -m pytest tests/ -q`
Expected: PASS. El conteo sube de 144 a **149** (5 tests nuevos: 1 en TestAuthPanel, 1 en TestHeartbeat, 4 en TestGuardasArranque, menos 1 test viejo reemplazado). Si el número no cuadra, contar antes de seguir: un test que desapareció sin querer es una regresión silenciosa.

- [ ] **Step 7: Commit**

```bash
git add app.py tests/test_plan5_operacion.py
git commit -m "feat(auth): la app no arranca sin PANEL_DASHBOARD_TOKEN ni SECRET_KEY

Cierra el ultimo default silencioso: antes SECRET_KEY ausente solo
imprimia una advertencia. Baseline 144 -> 149."
```

---

### Task 4: Dockerfile y plantilla de despliegue

**Files:**
- Create: `Dockerfile`
- Create: `despliegue/docker-compose.yml`
- Create: `despliegue/Caddyfile.fragmento`

- [ ] **Step 1: Crear el Dockerfile**

```dockerfile
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD gunicorn app:app --bind 0.0.0.0:8000 --workers 2 --timeout 120
```

- [ ] **Step 2: Crear la plantilla de compose**

`despliegue/docker-compose.yml`:

```yaml
# Plantilla versionada. La copia VIVA está en /srv/panel/docker-compose.yml
# del servidor 155.138.200.66 y apunta a ./app (el clon de este repo).
services:
  panel:
    build: ./app
    container_name: panel          # Caddy resuelve este nombre en reverse_proxy panel:8000
    restart: unless-stopped
    env_file:
      - ./secretos/.env
    volumes:
      - ./secretos/credentials.json:/app/credentials.json:ro
    mem_limit: 768m
    networks:
      - web
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"

networks:
  web:
    external: true
```

- [ ] **Step 3: Crear el fragmento de Caddy**

`despliegue/Caddyfile.fragmento`:

```
# Añadir a /srv/proxy/Caddyfile y recargar con:
#   docker compose -f /srv/proxy/docker-compose.yml restart caddy
panelnioval.duckdns.org {
	reverse_proxy panel:8000
}
```

- [ ] **Step 4: Verificar que la imagen construye**

Run: `docker build -t panel-test .`
Expected: build OK. Si Docker no está disponible en la máquina local, saltar este paso y verificarlo en la Task 7 (el servidor sí lo tiene); anotarlo explícitamente en vez de darlo por bueno.

- [ ] **Step 5: Commit**

```bash
git add Dockerfile despliegue/
git commit -m "feat(despliegue): Dockerfile y plantillas de compose y Caddy para el VPS

Procfile y nixpacks.toml son artefactos de Railway sin uso fuera de ahi.
Se dejan en el repo hasta apagar Railway (rollback del corte)."
```

---

### Task 5: Worker y smoke test apuntados al panel nuevo

**Files:**
- Rename: `tools/smoke_railway.py` → `tools/smoke_panel.py`
- Modify: `iniciar-worker.bat:14,18`
- Modify: `docs/RUNBOOK.md`

> **Nota:** este task deja el `.bat` listo pero con la URL nueva **comentada**. El cambio se activa en la Task 9, después de que el DNS resuelva. Cambiarlo antes deja al worker apuntando a un host que todavía no existe.

- [ ] **Step 1: Renombrar el smoke test**

```bash
git mv tools/smoke_railway.py tools/smoke_panel.py
```

Actualizar su docstring (líneas 1-7):

```python
"""Smoke test post-deploy contra la URL productiva del panel.

Sin costo de LLM. Verifica códigos 200 y shape JSON de los endpoints clave.

Uso:
    python tools/smoke_panel.py https://panelnioval.duckdns.org --token TOKEN
"""
```

- [ ] **Step 2: Preparar el lanzador del worker**

En `iniciar-worker.bat`, reemplazar las líneas 13-18 por:

```bat
REM Armar el envio para esta ventana y apuntar el panel (heartbeat).
set WA_ENVIO_ARMADO=1
REM WORKER_TOKEN es obligatorio: el heartbeat devuelve 401 sin el.
if "%WORKER_TOKEN%"=="" set /p WORKER_TOKEN=Token del worker:
set PANEL_URL=https://web-production-1d453.up.railway.app
REM TRAS EL CORTE (Task 9) sustituir las dos URLs por:
REM   set PANEL_URL=https://panelnioval.duckdns.org

REM Abrir el formulario del panel en el navegador.
echo Abriendo el panel (formulario) en el navegador...
start "" "https://web-production-1d453.up.railway.app/formulario"
```

- [ ] **Step 3: Documentar la operación en VPS**

Añadir al final de `docs/RUNBOOK.md`:

```markdown
## Operación en el VPS (desde 2026-08-17)

El panel corre en `155.138.200.66` (Vultr), servido en
`https://panelnioval.duckdns.org` por Caddy con TLS automático. Comparte
servidor con Bruce.

| Acción | Comando |
|---|---|
| Ver logs | `ssh root@155.138.200.66 'docker logs -f panel'` |
| Reiniciar | `ssh root@155.138.200.66 'docker restart panel'` |
| Desplegar cambios | `ssh root@155.138.200.66 'cd /srv/panel/app && git pull && cd /srv/panel && docker compose up -d --build'` |
| Smoke test | `python tools/smoke_panel.py https://panelnioval.duckdns.org --token <token>` |
| Consumo | `ssh root@155.138.200.66 'docker stats --no-stream'` |

Los secretos viven en `/srv/panel/secretos/.env` (chmod 600). El panel **no
arranca** sin `PANEL_DASHBOARD_TOKEN` ni `SECRET_KEY`: si el contenedor
reinicia en bucle, revisar ese archivo primero con `docker logs panel`.

⚠️ Bruce corre en el mismo servidor y lee las mismas hojas. Antes de escribir
filas de prueba en `seguimiento` o `PROSPECTOS BRUCE`, pausar su scheduler
(`WA_SCHEDULER=0` en `/srv/bruce/secretos/.env` + `docker compose up -d`) o un
job le enviará un WhatsApp real al número de la fila.
```

- [ ] **Step 4: Verificar que no quedaron referencias al nombre viejo**

Run: `grep -rn "smoke_railway" . --exclude-dir=.git`
Expected: sin resultados.

- [ ] **Step 5: Commit**

```bash
git add tools/smoke_panel.py iniciar-worker.bat docs/RUNBOOK.md
git commit -m "chore(worker): smoke test renombrado, WORKER_TOKEN obligatorio y runbook del VPS

La URL nueva queda comentada: se activa en el corte, cuando el DNS resuelva."
```

---

### Task 6: PR y merge a main

- [ ] **Step 1: Correr la suite completa una última vez**

Run: `python -m pytest tests/ -q`
Expected: **149 passed**. Si hay un solo fallo, no se abre el PR.

- [ ] **Step 2: Verificar que no se coló ningún secreto**

Run: `git diff main...HEAD | grep -aiE "token|secret|password|key" | grep -avE "^\+.*(TOKEN|SECRET_KEY|PASSWORD)[\"']?\s*(=|:|,|\))|os\.environ|getenv|#|REM"`
Expected: revisar a mano cada línea que salga. Solo deben aparecer nombres de variable y los literales de test (`"secreto123"`, `"w-secreto"`, `"t"*32`), nunca un valor real.

- [ ] **Step 3: Abrir el PR**

```bash
git push -u origin feat/despliegue-vultr
gh pr create --base main --title "feat(despliegue): alta en VPS Vultr con auth fail-closed" --body "$(cat <<'EOF'
## Qué

Prepara PanelNioval para correr en el VPS Vultr que ya hospeda a Bruce, e
invierte los dos gates de autenticación que hoy abren por defecto.

## Por qué

`https://web-production-1d453.up.railway.app/` devuelve hoy 200 con el
dashboard completo sin exigir token: `PANEL_DASHBOARD_TOKEN` no está definida
en Railway. Publicar eso en un dominio predecible como
`panelnioval.duckdns.org` sin cerrar antes el gate sería exponer las hojas de
ventas, contactos y seguimiento.

## Cambios

- `app.py`: la app no arranca sin `PANEL_DASHBOARD_TOKEN` ni `SECRET_KEY`
- `app.py`: el gate del panel y el del heartbeat cierran por defecto
- Bypass único y explícito: `PANEL_AUTH_DESACTIVADA=1`
- `Dockerfile` + plantillas de compose y Caddy
- `iniciar-worker.bat` pide `WORKER_TOKEN`; smoke test renombrado
- Runbook de operación en VPS

## Plan de pruebas

- [x] `pytest tests/ -q` → 149 passed (baseline previo: 144)
- [ ] Despliegue en VPS y testeo de 7 capas (Fase C del plan)

Spec: `docs/superpowers/specs/2026-08-17-panelnioval-vultr-design.md`
EOF
)"
```

- [ ] **Step 4: Mergear tras revisión sin CRITICAL/HIGH**

```bash
gh pr merge --squash
```

---

# FASE B — Servidor

> **GATE DEL OWNER antes de empezar la Fase B:** rotar `TELEGRAM_TOKEN` (está en ~14 copias del historial git). Cargar el token quemado en el VPS migra el problema en vez de cerrarlo.

### Task 7: Provisionar /srv/panel sin tocar DNS

**Files:** ninguno del repo — todo en el servidor.

- [ ] **Step 1: Clonar el repo en el servidor**

```bash
ssh root@155.138.200.66 'mkdir -p /srv/panel/secretos && chmod 700 /srv/panel/secretos && git clone https://github.com/luisgarciau03-art/PanelNioval.git /srv/panel/app'
```

- [ ] **Step 2: Copiar la plantilla de compose**

```bash
ssh root@155.138.200.66 'cp /srv/panel/app/despliegue/docker-compose.yml /srv/panel/docker-compose.yml'
```

- [ ] **Step 3: Subir la service account**

```bash
scp "/c/Users/PC 1/PanelNioval/bubbly-subject-412101-c969f4a975c5.json" root@155.138.200.66:/srv/panel/secretos/credentials.json
ssh root@155.138.200.66 'chmod 600 /srv/panel/secretos/credentials.json'
```

- [ ] **Step 4: Generar los secretos EN el servidor**

Los tokens se generan en el servidor y no salen de ahí. No pegarlos en la conversación ni en ningún informe.

```bash
ssh root@155.138.200.66 'umask 077; {
  echo "PANEL_DASHBOARD_TOKEN=$(openssl rand -hex 32)"
  echo "WORKER_TOKEN=$(openssl rand -hex 32)"
  echo "SECRET_KEY=$(openssl rand -hex 32)"
} > /srv/panel/secretos/.env; chmod 600 /srv/panel/secretos/.env; wc -l /srv/panel/secretos/.env'
```

Expected: `3 /srv/panel/secretos/.env`

- [ ] **Step 5: Añadir las variables de Telegram**

El owner añade `TELEGRAM_TOKEN` (el **rotado**) y `TELEGRAM_CHAT_ID` al mismo archivo:

```bash
ssh root@155.138.200.66 'nano /srv/panel/secretos/.env'
```

Verificar solo la presencia, nunca el valor:

```bash
ssh root@155.138.200.66 'grep -c "^TELEGRAM_TOKEN=" /srv/panel/secretos/.env'
```

Expected: `1`

- [ ] **Step 6: Levantar el contenedor**

```bash
ssh root@155.138.200.66 'cd /srv/panel && docker compose up -d --build && sleep 20 && docker ps --filter name=panel --format "{{.Names}} {{.Status}}"'
```

Expected: `panel Up ...`. Si aparece `Restarting`, leer `docker logs panel` — casi siempre es un secreto ausente, que ahora falla ruidosamente por diseño.

- [ ] **Step 7: Probar por red interna, sin DNS**

```bash
ssh root@155.138.200.66 'docker exec caddy wget -qO- --server-response http://panel:8000/ 2>&1 | head -5'
```

Expected: `HTTP/1.1 401 Unauthorized`. **Un 200 aquí significa que el gate no está activo: parar y revisar antes de tocar el DNS.**

- [ ] **Step 8: Probar con el token**

```bash
ssh root@155.138.200.66 'TOK=$(grep "^PANEL_DASHBOARD_TOKEN=" /srv/panel/secretos/.env | cut -d= -f2); docker exec caddy wget -qO- --header="X-Dashboard-Token: $TOK" --server-response http://panel:8000/api/catalogo/worker-estado 2>&1 | head -8'
```

Expected: `HTTP/1.1 200 OK` y un JSON con la clave `vivo`.

---

### Task 8: Caddy, DNS y TLS

- [ ] **Step 1: Añadir el bloque al Caddyfile**

```bash
ssh root@155.138.200.66 'cat /srv/panel/app/despliegue/Caddyfile.fragmento | grep -v "^#" >> /srv/proxy/Caddyfile && cat /srv/proxy/Caddyfile'
```

Expected: el archivo ahora tiene los tres bloques (`nioval`, `bruce.nioval`, `panelnioval`).

- [ ] **Step 2: Validar la sintaxis ANTES de recargar**

```bash
ssh root@155.138.200.66 'docker exec caddy caddy validate --config /etc/caddy/Caddyfile'
```

Expected: `Valid configuration`. Un Caddyfile inválido tumbaría también a Bruce: no recargar sin este paso en verde.

- [ ] **Step 3: GATE DEL OWNER — repuntar DuckDNS**

El owner cambia el registro `panelnioval` a `155.138.200.66` en duckdns.org.

- [ ] **Step 4: Verificar la propagación**

```bash
nslookup panelnioval.duckdns.org 1.1.1.1
```

Expected: `155.138.200.66`. No seguir hasta que resuelva: Caddy no puede emitir el certificado si el desafío HTTP no llega al servidor.

- [ ] **Step 5: Recargar Caddy**

```bash
ssh root@155.138.200.66 'docker compose -f /srv/proxy/docker-compose.yml restart caddy && sleep 30 && docker logs caddy --tail 20'
```

Expected: en el log, la obtención del certificado para `panelnioval.duckdns.org`. Bruce sigue arriba.

- [ ] **Step 6: Verificar TLS y el gate desde fuera**

```bash
curl -sS -o /dev/null -w "%{http_code} %{ssl_verify_result}\n" https://panelnioval.duckdns.org/
```

Expected: `401 0` — cierra sin token, y el certificado valida.

---

### Task 9: Apuntar el worker a la URL nueva

**Files:**
- Modify: `iniciar-worker.bat:15,20`

- [ ] **Step 1: Activar la URL nueva**

En `iniciar-worker.bat`, sustituir las dos apariciones de la URL de Railway:

```bat
set PANEL_URL=https://panelnioval.duckdns.org
```

```bat
start "" "https://panelnioval.duckdns.org/formulario"
```

Y borrar las dos líneas `REM TRAS EL CORTE...`.

- [ ] **Step 2: Correr el smoke test contra producción**

```bash
python tools/smoke_panel.py https://panelnioval.duckdns.org --token <leer de /srv/panel/secretos/.env>
```

Expected: `Todo OK ✅` con los 5 endpoints en verde.

- [ ] **Step 3: Arrancar el worker y verificar el heartbeat**

Ejecutar `iniciar-worker.bat` en la PC del owner, introduciendo el `WORKER_TOKEN` del servidor cuando lo pida. Luego:

```bash
curl -sS -H "X-Dashboard-Token: <token>" https://panelnioval.duckdns.org/api/catalogo/worker-estado
```

Expected: `{"vivo": true, ...}`. Un `"vivo": false` con el worker corriendo significa que el `WORKER_TOKEN` no coincide.

- [ ] **Step 4: Commit**

```bash
git add iniciar-worker.bat
git commit -m "chore(worker): apunta al panel del VPS tras el corte"
git push
```

---

### Task 10: Apagar Railway

> Railway es el rollback de todos los pasos anteriores. Solo se apaga cuando las Tasks 7-9 están verdes.

- [ ] **Step 1: Confirmar que el VPS aguanta la operación**

Verificar con el owner que usó el panel nuevo para su trabajo real al menos un ciclo completo (un formulario guardado, un envío de catálogo).

- [ ] **Step 2: GATE DEL OWNER — eliminar el servicio en Railway**

El owner elimina el servicio desde el panel de Railway.

- [ ] **Step 3: Verificar que murió**

```bash
curl -sS -o /dev/null -w "%{http_code}\n" --max-time 20 https://web-production-1d453.up.railway.app/
```

Expected: 404, error de conexión, o timeout. **Un 200 significa que sigue vivo y abierto**: no cerrar esta task.

- [ ] **Step 4: Retirar los artefactos de Railway**

```bash
git rm Procfile nixpacks.toml
git commit -m "chore(despliegue): retira Procfile y nixpacks.toml tras apagar Railway"
```

---

# FASE C — Testeo completo (7 capas)

> **GATE DEL OWNER antes de la Fase C:** confirmar (a) la ventana horaria fuera de 09:00–20:00 MX para las capas 4 y 5, y (b) el número de teléfono del owner para las filas de prueba.

### Task 11: Capas 1, 2 y 3 — suite, gates y lectura

- [ ] **Step 1: Capa 1 — suite unitaria**

Run: `python -m pytest tests/ -q`
Expected: **149 passed**.

- [ ] **Step 2: Capa 2 — gates desde internet**

```bash
BASE=https://panelnioval.duckdns.org
for R in / /formulario /importador /api/prospectos/stats /api/debug /api/debug/respuestas /api/catalogo/envios; do
  printf "%-32s %s\n" "$R" "$(curl -sS -o /dev/null -w '%{http_code}' --max-time 20 "$BASE$R")"
done
curl -sS -o /dev/null -w "heartbeat sin token: %{http_code}\n" -X POST -H "Content-Type: application/json" -d '{}' "$BASE/api/catalogo/heartbeat"
```

Expected: **401 en las 8 líneas**. Cualquier 200 es un fallo bloqueante.

- [ ] **Step 3: Capa 2 — el contenedor no arranca sin secretos**

```bash
ssh root@155.138.200.66 'cd /srv/panel && cp secretos/.env /tmp/env.bak && grep -v "^PANEL_DASHBOARD_TOKEN=" /tmp/env.bak > secretos/.env && docker compose up -d && sleep 15 && docker logs panel --tail 5; cp /tmp/env.bak secretos/.env && chmod 600 secretos/.env && docker compose up -d && sleep 20 && rm /tmp/env.bak && docker ps --filter name=panel --format "{{.Status}}"'
```

Expected: en el log aparece el `RuntimeError` de `PANEL_DASHBOARD_TOKEN`, y al restaurar el archivo el contenedor vuelve a `Up`.

- [ ] **Step 4: Capa 3 — las 24 rutas GET con token**

```bash
BASE=https://panelnioval.duckdns.org
TOK=<leer del servidor>
for R in / /formulario /importador /api/prospectos/ciudades /api/prospectos/clientes-frecuentes \
         /api/prospectos/contactos /api/prospectos/contactos-pendientes /api/prospectos/frecuentes \
         /api/prospectos/mensajes /api/prospectos/respuestas /api/prospectos/stats \
         /api/prospectos/ventas /api/prospectos/ventas-dashboard /api/seguimiento \
         /api/ventas/stats /api/bruce/prospectos /api/catalogo/envios \
         /api/catalogo/worker-estado /api/formulario/siguiente /api/importador/estado \
         /api/debug /api/debug/respuestas; do
  printf "%-40s %s\n" "$R" "$(curl -sS -o /dev/null -w '%{http_code}' --max-time 40 -H "X-Dashboard-Token: $TOK" "$BASE$R")"
done
```

Expected: 200 en todas. Registrar cualquier no-200 con su ruta antes de seguir.

Son 22 de las 24 rutas GET. Las dos que faltan exigen parámetros y se prueban aparte:
`/api/ventas/buscar-imagen` (requiere un identificador de venta real, se ejercita desde el
dashboard) y `/api/test/<key>` (requiere una `key` de `SHEET_IDS`; probar con
`/api/test/ventas`). Ninguna se omite del registro de evidencia.

- [ ] **Step 5: Registrar evidencia**

Crear `docs/auditoria/2026-08-17-testeo-vps.md` con la salida de los pasos 1-4. Sin valores de token.

---

### Task 12: Capa 4 — escrituras sobre producción

> Las 15 rutas POST escriben en hojas compartidas con proyectos externos. El protocolo es obligatorio y su orden importa.

- [ ] **Step 1: Respaldo ANTES de escribir nada**

Añadir `docs/auditoria/respaldos/` al `.gitignore` (contienen datos de clientes) y crear
`tools/respaldar_hojas.py`, que usa las credenciales que ya tiene el panel:

```python
"""Respalda a XLSX los spreadsheets del panel antes de una prueba de escritura.

Uso:  python tools/respaldar_hojas.py docs/auditoria/respaldos/2026-08-17
"""
import hashlib
import json
import pathlib
import sys

import gspread
from google.auth.transport.requests import AuthorizedSession
from google.oauth2.service_account import Credentials

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from app import SHEET_IDS  # noqa: E402  (fuente de verdad de los IDs)

DESTINO = pathlib.Path(sys.argv[1])
DESTINO.mkdir(parents=True, exist_ok=True)

creds = Credentials.from_service_account_file(
    "bubbly-subject-412101-c969f4a975c5.json",
    scopes=["https://www.googleapis.com/auth/spreadsheets.readonly",
            "https://www.googleapis.com/auth/drive.readonly"])
sesion = AuthorizedSession(creds)
cliente = gspread.authorize(creds)

huellas = {}
for clave, sid in sorted(set(SHEET_IDS.items()), key=lambda kv: kv[1]):
    r = sesion.get(f"https://docs.google.com/spreadsheets/d/{sid}/export?format=xlsx")
    r.raise_for_status()
    (DESTINO / f"{clave}-{sid}.xlsx").write_bytes(r.content)

    for hoja in cliente.open_by_key(sid).worksheets():
        encabezados = hoja.row_values(1)
        huellas[f"{clave}/{hoja.title}"] = {
            "sha256_encabezados": hashlib.sha256(
                "\x1f".join(encabezados).encode("utf-8")).hexdigest(),
            "columnas": len(encabezados),
            "filas": hoja.row_count,
        }
    print(f"  OK  {clave} ({sid})")

(DESTINO / "huellas.json").write_text(json.dumps(huellas, indent=2, ensure_ascii=False))
print(f"\nRespaldo y huellas en {DESTINO}")
```

Run: `python tools/respaldar_hojas.py docs/auditoria/respaldos/2026-08-17`
Expected: 5 archivos `.xlsx` más `huellas.json`. **Si este paso falla, la Task 12 no empieza.**
El respaldo existe antes del cambio, no después.

- [ ] **Step 2: Verificar que el respaldo sirve**

Abrir uno de los `.xlsx` y confirmar que trae datos, no una página de error de 2 KB.
Un respaldo que no se comprueba no es un respaldo.

```bash
ls -la docs/auditoria/respaldos/2026-08-17/
```

Expected: archivos de tamaño plausible (decenas o cientos de KB), no de 1-2 KB.

- [ ] **Step 3: Derivar el payload exacto de cada ruta POST**

Los cuerpos de las 15 rutas no se inventan: se leen del código. Para cada una, localizar
qué campos consume y con qué nombres:

```bash
grep -n -A 25 "@app.route('/api/bruce/agregar'" app.py | grep -E "request.json|\.get\(|request.form|request.files"
```

Repetir por ruta y anotar en el registro de evidencia el payload mínimo válido de cada una,
**antes** de enviar nada. Un POST con el cuerpo equivocado puede escribir una fila
malformada en una hoja de producción compartida.

- [ ] **Step 4: Pausar el scheduler de Bruce**

```bash
ssh root@155.138.200.66 'grep -E "^WA_[A-Z_]+=[01]$" /srv/bruce/secretos/.env | sort'   # anotar valores previos
ssh root@155.138.200.66 'sed -i "s/^WA_SCHEDULER=1/WA_SCHEDULER=0/" /srv/bruce/secretos/.env && cd /srv/bruce && docker compose up -d && sleep 15 && docker logs bruce --tail 10'
```

Expected: en el log, ausencia del registro de jobs del scheduler.

- [ ] **Step 5: Ejercitar las 15 rutas POST**

Con marcado `PRUEBA-2026-08-17` en el campo de nombre y el teléfono del owner en toda fila que toque `seguimiento` o `PROSPECTOS BRUCE`. Respetando el orden de columnas existente: solo `append` con el esquema actual, nunca insertar ni reordenar.

Rutas: `/api/bruce/agregar`, `/api/bruce/actualizar`, `/api/seguimiento/update`, `/api/mensajes/update`, `/api/formulario/guardar`, `/api/formulario/telefono`, `/api/formulario/correo`, `/api/catalogo/encolar`, `/api/catalogo/corregir-numero`, `/api/catalogo/reintentar`, `/api/ventas/update-pago-url`, `/api/ventas/upload-pago`, `/api/refresh`, `/api/importador/iniciar`, `/api/catalogo/heartbeat`.

Registrar por cada una: código HTTP, fila escrita y hoja afectada.

- [ ] **Step 6: Retirar las filas de prueba**

Eliminar solo las filas marcadas `PRUEBA-2026-08-17`.

- [ ] **Step 7: Verificar que la estructura no se movió**

Volver a correr el respaldador contra un destino nuevo y comparar las huellas:

```bash
python tools/respaldar_hojas.py docs/auditoria/respaldos/2026-08-17-post
diff docs/auditoria/respaldos/2026-08-17/huellas.json \
     docs/auditoria/respaldos/2026-08-17-post/huellas.json
```

Expected: **sin diferencias**. Los `sha256_encabezados` idénticos prueban que el orden de
columnas del que dependen los proyectos externos no se movió, y el conteo de filas igual
prueba que la limpieza del Step 6 fue completa. Cualquier diferencia se investiga antes de
cerrar la task.

- [ ] **Step 8: Restaurar el scheduler de Bruce**

```bash
ssh root@155.138.200.66 'sed -i "s/^WA_SCHEDULER=0/WA_SCHEDULER=1/" /srv/bruce/secretos/.env && cd /srv/bruce && docker compose up -d && sleep 20 && docker logs bruce --tail 30 | grep -ci "job"'
```

Expected: los 16 jobs vuelven a registrarse, y los cuatro flags con sus valores del Step 3.

---

### Task 13: Capa 5 — worker Selenium extremo a extremo

- [ ] **Step 1: Encolar un envío desde el panel** al número del owner, marcado como prueba.

- [ ] **Step 2: Verificar que el worker lo toma** — la ventana del worker muestra el procesamiento y el heartbeat sigue vivo en el panel.

- [ ] **Step 3: Confirmar la recepción** del mensaje y los 4 archivos en el WhatsApp del owner.

- [ ] **Step 4: Probar la corrección de número** vía `/api/catalogo/corregir-numero` y reintento.

- [ ] **Step 5: Retirar la fila de prueba** de la hoja `ENVIOS_CATALOGO`.

---

### Task 14: Capa 6 — no-regresión de Bruce

> El sistema ahora incluye a Bruce: comparte servidor y hojas. Un testeo que no lo verifique no está completo.

- [ ] **Step 1: Webhook de Meta**

```bash
curl -sS -o /dev/null -w "%{http_code}\n" "https://bruce.nioval.duckdns.org/webhook?hub.mode=subscribe&hub.verify_token=<verify_token>&hub.challenge=test123"
```

Expected: 200 con el challenge devuelto.

- [ ] **Step 2: Los 16 jobs del scheduler**

```bash
ssh root@155.138.200.66 'docker logs bruce --tail 100 | grep -ci "job\|scheduler"'
```

Expected: los 16 jobs registrados, con `campana_inicial_auto` correctamente deshabilitado (`WA_CAMPANA_AUTO=0`).

- [ ] **Step 3: Envío saliente real** de Bruce al número del owner. Expected: recibido.

- [ ] **Step 4: Consumo de recursos con los dos servicios**

```bash
ssh root@155.138.200.66 'docker stats --no-stream --format "{{.Name}}\t{{.MemUsage}}\t{{.MemPerc}}"; free -m'
```

Expected: `panel` por debajo de su `mem_limit` de 768m, `bruce` en su rango habitual (~64 MB), sin presión de swap sostenida.

- [ ] **Step 5: Los flags quedaron como estaban**

```bash
ssh root@155.138.200.66 'grep -E "^WA_[A-Z_]+=[01]$" /srv/bruce/secretos/.env | sort'
```

Expected: `WA_BUSCADOR_AUTO=1`, `WA_CAMPANA_AUTO=0`, `WA_GEO_AUTO=1`, `WA_SCHEDULER=1`.

---

### Task 15: Capa 7 — resiliencia y cierre

- [ ] **Step 1: Reboot del VPS**

```bash
ssh root@155.138.200.66 'reboot'
```

Esperar ~60s y verificar:

```bash
ssh root@155.138.200.66 'docker ps --format "{{.Names}} {{.Status}}"'
curl -sS -o /dev/null -w "panel: %{http_code}\n" https://panelnioval.duckdns.org/
curl -sS -o /dev/null -w "bruce: %{http_code}\n" https://bruce.nioval.duckdns.org/
```

Expected: los tres contenedores `Up` sin intervención, panel 401, Bruce respondiendo.

- [ ] **Step 2: Rotación de logs activa**

```bash
ssh root@155.138.200.66 'docker inspect panel --format "{{.HostConfig.LogConfig}}"'
```

Expected: `json-file` con `max-size:10m` y `max-file:3`.

- [ ] **Step 3: Renovación del certificado**

```bash
ssh root@155.138.200.66 'docker exec caddy ls /data/caddy/certificates/*/panelnioval.duckdns.org/ 2>/dev/null'
```

Expected: el certificado y su `.json` de metadatos presentes — Caddy renovará solo.

- [ ] **Step 4: Cerrar el registro de evidencia**

Completar `docs/auditoria/2026-08-17-testeo-vps.md` con las 7 capas y su resultado. Sin valores de credencial, teléfonos anonimizados a `+52...XXXX`.

- [ ] **Step 5: Verificar los 10 criterios de aceptación del spec**

Recorrer §10 del spec uno por uno y marcar cada uno con su evidencia. Un criterio sin evidencia es un criterio no cumplido.

- [ ] **Step 6: Commit final**

```bash
git add docs/auditoria/2026-08-17-testeo-vps.md .gitignore
git commit -m "docs(testeo): evidencia de las 7 capas del testeo post-migracion"
git push
```

---

## Estado de los gates del owner

| # | Gate | Bloquea |
|---|---|---|
| 1 | Rotar `TELEGRAM_TOKEN` | Fase B |
| 2 | Repuntar DuckDNS a `155.138.200.66` | Task 8 |
| 3 | Eliminar el servicio de Railway | Task 10 |
| 4 | Ventana horaria + teléfono del owner | Fase C |
| 5 | Identificar los proyectos externos que sincronizan las hojas | Aprieta el protocolo de la Task 12 |
