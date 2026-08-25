# PanelNioval — Instrucciones del Proyecto

Panel web interno de NIOVAL (distribuidora mayorista de ferretería/plomería) para operar ventas, contactos/prospectos, seguimiento y un formulario de encuestas de llamadas. Complementado por un script Selenium que envía catálogos por WhatsApp Web. Stack: **Flask + gunicorn · Google Sheets (gspread + google-auth) · Google Drive · Google Maps/Places · Railway (auto-deploy desde `main`)**.

## Arquitectura (leer antes de tocar código)

- **`app.py`** (~3.6k líneas, monolito Flask): todas las rutas API + HTML embebido + integración Sheets/Drive/Places + importador de prospectos en background. ⚠️ Viola el límite de 800 líneas de las reglas globales (mejora M2 pendiente: trocear en módulos).
- **`envio_catalogo.py`** (antes `22.PY`): script Selenium **standalone** que corre en la PC del owner (no en Railway). Lee pedidos del día, busca teléfonos, abre WhatsApp Web con perfil Chrome local y envía mensajes + 4 archivos, marca `ENVIADO_WA` y reporta por Telegram. Auditoría completa: `docs/auditoria/2026-08-13-auditoria-22py.md`.
- **`nucleo_catalogo.py`** (Plan 3): lógica pura de la cola de catálogo (conclusiones elegibles, estados, validación de números). Sin selenium/gspread. **`worker_catalogo.py`**: worker transport-agnostic que procesa la worksheet `ENVIOS_CATALOGO` (transporte = worker local, decisión owner). El panel encola/consulta/corrige vía `/api/catalogo/*`. Diseño: `docs/superpowers/plans/2026-08-13-plan3-diseno-cola.md`.
- **`worker_catalogo_run.py`** (Plan 5): runner del worker local (Selenium + heartbeat + lock) que el owner corre en su PC (`instalar-worker.ps1` = Tarea Programada). Operación: `docs/RUNBOOK.md`; decisión de transporte: `docs/adr/2026-08-13-transporte-catalogo.md`. Smoke test: `tools/smoke_panel.py`.
- **Autenticación fail-closed:** la app no arranca sin `PANEL_DASHBOARD_TOKEN` ni `SECRET_KEY` (`app.py:34-44`) — revienta con `RuntimeError` en vez de publicar el panel abierto. Ya arrancada, todas las rutas exigen el token (header `X-Dashboard-Token`, `?token=`, o cookie de sesión), y `/api/catalogo/heartbeat` exige por separado `WORKER_TOKEN` o devuelve 401. Único bypass, explícito y ruidoso: `PANEL_AUTH_DESACTIVADA=1` (usado por `tests/conftest.py` y para desarrollo local). El default nunca abre.
- **`Procfile` / `nixpacks.toml`**: `gunicorn app:app --workers 2 --timeout 120`. Artefactos de Railway; se retiran cuando ese despliegue se apague (ver `docs/superpowers/plans/2026-08-17-despliegue-vultr.md`, Task 10).
- **`Dockerfile`**: imagen del panel para el VPS Vultr (`python:3.11-slim` + gunicorn, `--bind 0.0.0.0:8000`). **`despliegue/`**: plantillas versionadas de `docker-compose.yml` y del fragmento de Caddy que se copian al servidor `155.138.200.66`; la copia viva está en `/srv/panel/` (ver `docs/RUNBOOK.md` § Operación en el VPS y `docs/superpowers/specs/2026-08-17-panelnioval-vultr-design.md`).
- **`requirements.txt`**: deps del panel Flask. **`requirements-dev.txt`**: pytest + deps runtime de `envio_catalogo.py` (selenium, etc.), no instaladas en el contenedor del panel.

## Hojas de Google (IDs — fuente de verdad en `app.py:28-45` `SHEET_IDS`/`SHEET_GIDS`)

| Clave | Spreadsheet ID | Worksheet(s) | Uso |
|---|---|---|---|
| `ventas` | `1Dlpm6swrNSPnt9L5tQhoi2OMln0bb8bqqgeLACNos98` | Ventas | dashboard de ventas, comprobantes de pago (Drive) |
| `contactos` / `frecuentes` | `1wgEentS16hJrcf6YdEnSpEBcp4SCBJ9TkOCZY439jV4` | `LISTA DE CONTACTOS`, FRECUENTES | prospectos, clientes frecuentes, importador |
| `respuestas` | `1U_z1KNqCxSRZVi7wvO2FQH4zIdS_wxuafxj6YHdHEqg` | `Respuestas de formulario 1` | encuestas de llamadas; **misma hoja de pedidos que `envio_catalogo.py`** |
| `mensajes` | `1oEtAiYaYVdOnEum3tbp_BminBUdj06JzXqJhaOVQFlk` | `BD CONTACTOS`, `Mensajes` | teléfonos y plantillas que consume `envio_catalogo.py` |
| `seguimiento` / `bruce` | `1i0bWYQG7d5GVvOjuklZRpsg1bQfsScdY0bg7lytMXKM` | Seguimiento, PROSPECTOS BRUCE | seguimiento y prospectos de Bruce |

⚠️ `envio_catalogo.py` usa `BD CONTACTOS` (hoja `mensajes`) para teléfonos, mientras el panel usa `LISTA DE CONTACTOS` (hoja `contactos`): **son fuentes distintas**.

## Superficies del panel (rutas principales en `app.py`)

- `/` (dashboard), `/formulario` (encuesta de llamadas), `/importador` (scraping de prospectos con Places).
- API: `/api/prospectos/*`, `/api/ventas/*`, `/api/seguimiento*`, `/api/mensajes/update`, `/api/bruce/*`, `/api/formulario/{siguiente,guardar}`, `/api/importador/*`.

## Reglas del proyecto

- **Baseline de verificación:** `python -m pytest tests/ -q` → **230 passed** (al 2026-08-24, tras los 9 tests de rutas portables y archivos en Files/; 227 tras los 6 primeros; 221 tras los 2 del estado real en ya_encolado; 219 tras los 4 del cierre de Chrome huerfano; 215 tras los 10 del lock huerfano del worker; 205 tras los 5 de la lada de pais para WhatsApp; 200 tras los 13 de la columna CONTACTO y el formato de telefono; 187 tras los 16 del escape de formulas del importador; 171 tras los 6 del heartbeat compartido; 165 al 2026-08-17 tras la ronda final de correcciones de `feat/despliegue-vultr`; 164 justo antes; 155 al cierre del 2026-08-13; el 144 anterior era stale: PRs #6-#9 agregaron 11 tests a archivos existentes sin actualizar la documentación). Es el ÚNICO baseline oficial. Nada se mergea con la suite en rojo. Nota: importar `app.py` en frío tarda ~100s (`googleapiclient` + Defender); en caliente ~8s. **No es pandas**: medido con `sys.modules`, ni pandas ni numpy llegan a cargarse — pandas estaba en `requirements.txt` sin que nadie lo importara y se retiró. `pytest.ini` ancla el rootdir al proyecto.
- **Datos personales:** teléfonos/nombres/correos de clientes **no** se commitean ni se vuelcan completos en logs; enmascarar (`+52...XXXX`). `.gitignore` cubre `*.json` (credenciales) y `debug_invalid_*`/`debug_timeout_*` (screenshots con PII de `envio_catalogo.py`).
- **Secretos:** nada hardcodeado. `GOOGLE_CREDENTIALS_JSON`, `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID` van por variables de entorno en Railway. **Pendiente owner:** rotar el token Telegram `8404009072` (expuesto en el historial git; ~14 copias).
- **Ramas:** **nunca** trabajar directo en `main` (Railway auto-deploya). Una rama por plan; PRs con `gh pr create --base main`; merge `--squash` solo con baseline verde y reviews sin CRITICAL/HIGH abiertos.
- **Idioma:** código con nombres en español (`guardar_respuesta_formulario`, `buscar_telefono`); docs y commits en español con prefijos convencionales (`fix:`, `feat:`, `test:`).

## Planes activos

**Tanda 2026-08-13** (5 planes). Índice: `docs/superpowers/plans/2026-08-13-indice-tanda.md`.
1. Evaluación `envio_catalogo.py` + baseline de tests + sanitización de secretos (**este plan**).
2. Evaluación del formulario de llamadas + matriz de flujo.
3. Integración catálogo + estados + corrección de número.
4. Captura de correo → columna T.
5. Operación 100% Railway (decisión de transporte WhatsApp = gate owner).

## Pendientes conocidos (gates del owner)

- Rotar `TELEGRAM_TOKEN` y cargar secretos en Railway (Plan 5 T5.3).
- Elegir transporte de WhatsApp para Railway: A=WhatsApp Business API (recomendado) / B=worker local / C=Selenium headless (Plan 5 T5.1).
- Corridas reales de WhatsApp (Plan 3 T3.6 / Plan 5 T5.5) y confirmación de la columna T de `LISTA DE CONTACTOS` (Plan 4 T4.1).
- ~~Autenticación del panel (M1)~~ — **RESUELTO** en `feat/despliegue-vultr`: el gate es fail-closed (`app.py:34-82`). Pendiente real: la exposición sigue **viva en Railway** — `https://web-production-1d453.up.railway.app/` corre sin `PANEL_DASHBOARD_TOKEN` definida ahí — hasta que ese despliegue se elimine (gate del owner, Task 10 de `docs/superpowers/plans/2026-08-17-despliegue-vultr.md`).
