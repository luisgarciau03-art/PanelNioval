# PanelNioval — Instrucciones del Proyecto

Panel web interno de NIOVAL (distribuidora mayorista de ferretería/plomería) para operar ventas, contactos/prospectos, seguimiento y un formulario de encuestas de llamadas. Complementado por un script Selenium que envía catálogos por WhatsApp Web. Stack: **Flask + gunicorn · Google Sheets (gspread + google-auth) · Google Drive · Google Maps/Places · VPS Vultr con Docker + Caddy (auto-deploy desde `main`)**. Railway se apagó el 2026-09-05.

## Arquitectura (leer antes de tocar código)

- **`app.py`** (~3.6k líneas, monolito Flask): todas las rutas API + HTML embebido + integración Sheets/Drive/Places + importador de prospectos en background. ⚠️ Viola el límite de 800 líneas de las reglas globales (mejora M2 pendiente: trocear en módulos).
- **`envio_catalogo.py`** (antes `22.PY`): script Selenium **standalone** que corre en la PC del owner (no en el VPS). Lee pedidos del día, busca teléfonos, abre WhatsApp Web con perfil Chrome local y envía mensajes + 4 archivos, marca `ENVIADO_WA` y reporta por Telegram. Auditoría completa: `docs/auditoria/2026-08-13-auditoria-22py.md`.
- **`nucleo_catalogo.py`** (Plan 3): lógica pura de la cola de catálogo (conclusiones elegibles, estados, validación de números). Sin selenium/gspread. **`worker_catalogo.py`**: worker transport-agnostic que procesa la worksheet `ENVIOS_CATALOGO` (transporte = worker local, decisión owner). El panel encola/consulta/corrige vía `/api/catalogo/*`. Diseño: `docs/superpowers/plans/2026-08-13-plan3-diseno-cola.md`.
- **`worker_catalogo_run.py`** (Plan 5): runner del worker local (Selenium + heartbeat + lock) que el owner corre en su PC (`instalar-worker.ps1` = Tarea Programada). Operación: `docs/RUNBOOK.md`; decisión de transporte: `docs/adr/2026-08-13-transporte-catalogo.md`. Smoke test: `tools/smoke_panel.py`.
- **Importador — gasto de Places:** el costo se mide por corrida (`text_search`, `place_details`, `cache_hits`, `duplicados_evitados`) y se publica en la UI y en Telegram. Las tarifas van por entorno **sin valor por defecto** (`PLACES_COSTO_TEXT_SEARCH`, `PLACES_COSTO_DETAILS`): sin ellas no se muestra importe, porque un `0.00` afirmaría que la corrida salió gratis. Topes: `PLACES_MAX_LLAMADAS_CORRIDA` (funciona siempre) y `PLACES_PRESUPUESTO_CORRIDA` (necesita tarifas). Al tocarlos la corrida queda en `presupuesto_agotado`, que **no es un error**. Caché de detalles en `PLACES_CACHE_FILE` (30 días, lleva teléfonos: 0600 y en `.gitignore`/`.dockerignore`). Ver `docs/RUNBOOK.md`.
- **Importador — los cuatro contadores:** `encontrados` (aprobados por los filtros de Places, deduplicados por `place_id` a nivel corrida), `nuevos_en_sheet` (**filas realmente escritas** — el número grande de la UI), `duplicados` (ya estaban en `LISTA DE CONTACTOS`) y `descartados` (reseñas, calificación o sin teléfono). Se cumple `nuevos_en_sheet + duplicados == encontrados`; `descartados` es disjunto. Un fallo de escritura **no** se cuenta como duplicado: la corrida termina en `error` con la causa.
- **Estado del importador:** vive en memoria de UN solo proceso (`--workers 1 --threads 4`). Además se persiste un registro mínimo y sin datos personales en `IMPORT_ESTADO_FILE` (temp del sistema) con el único fin de poder decir "se interrumpió" tras un reinicio; **nunca veta** una corrida nueva. Ver `docs/adr/2026-08-27-estado-compartido-importador.md`.
- **Autenticación fail-closed:** la app no arranca sin `PANEL_DASHBOARD_TOKEN` ni `SECRET_KEY` (`app.py:34-44`) — revienta con `RuntimeError` en vez de publicar el panel abierto. Ya arrancada, todas las rutas exigen el token (header `X-Dashboard-Token`, `?token=`, o cookie de sesión), y `/api/catalogo/heartbeat` exige por separado `WORKER_TOKEN` o devuelve 401. Único bypass, explícito y ruidoso: `PANEL_AUTH_DESACTIVADA=1` (usado por `tests/conftest.py` y para desarrollo local). El default nunca abre.
- **Endurecimiento (Plan 5)**: cinco cosas que el panel no tenía y ahora sí.
  **Rate limiting** con `Flask-Limiter` en memoria del proceso (`--workers 1` lo hace exacto):
  global 600/h y 60/min, importador **6/h** porque es la única ruta que gasta dinero,
  heartbeat y `/salud` holgados porque un 429 ahí tumba al worker o al healthcheck. Se
  engancha con `init_app()` **después** del gate de token: al revés, 60 peticiones anónimas
  agotaban el cubo y dejaban fuera a quien sí tenía token. **`ProxyFix(x_for=1)`** porque
  tras Caddy `remote_addr` es la IP del proxy y todos compartían un solo cubo.
  **Escapado de fórmulas** en las 6 escrituras con `USER_ENTERED` efectivo — no en las
  `RAW`, donde el apóstrofo se guardaría *dentro* del dato. ⚠️ `update_cell` **fija**
  `USER_ENTERED` y no admite el parámetro: leyendo `app.py` parece el caso seguro y es el
  contrario. **Zona horaria** en dos capas: `nucleo_catalogo.ahora_mexico()` con `ZoneInfo`
  más `ENV TZ` y `tzdata` (sin él, `ZoneInfo` revienta al importar y el panel no arranca).
  **`/salud`**, la única ruta sin auth: `{'ok': True}` pelado, sin tocar Google y sin
  reflejar estado interno. **Parada cooperativa ante `SIGTERM`**, que *encadena* al
  manejador de gunicorn — pisarlo dejaría al worker sin apagado ordenado. Detalle y
  verificación: `docs/auditoria/2026-09-04-t56-verificacion-integral.md`.
- **Arranque — solo `Dockerfile` desde el 2026-09-05.** Antes eran tres sitios (`Procfile`,
  `nixpacks.toml`, `Dockerfile`) y podían divergir; Railway se apagó y sus dos archivos se
  retiraron con la Task 10 del plan de Vultr. Siguen en el historial de git y en
  `docs/auditoria/respaldos/2026-09-05/`. Hay un test que falla si reaparecen, porque
  volverían sin `--graceful-timeout` ni `--workers 1`.
  Comando: `gunicorn app:app --bind 0.0.0.0:8000 --workers 1 --threads 4 --worker-class
  gthread --timeout 120 --graceful-timeout 120`. **Un solo worker a propósito**:
  `_import_job`, `_cache` y el contador del limitador son globales de módulo, y con 2
  procesos son 2 memorias distintas (razón completa en
  `docs/adr/2026-08-27-estado-compartido-importador.md`). **`--graceful-timeout 120`** no es
  cosmético: con los 30 s por defecto, la parada ordenada del importador no llega a
  ejecutarse antes del SIGKILL.
- **`Dockerfile` / `despliegue/`**: imagen del panel para el VPS Vultr (`python:3.11-slim` +
  gunicorn, `--bind 0.0.0.0:8000`, con `HEALTHCHECK`). **`despliegue/`**: plantillas
  versionadas de `docker-compose.yml` y del fragmento de Caddy que se copian al servidor
  `155.138.200.66`; la copia viva está en `/srv/panel/` (ver `docs/RUNBOOK.md` § Operación
  en el VPS y `docs/superpowers/specs/2026-08-17-panelnioval-vultr-design.md`).
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

- **Integración continua (desde 2026-08-28):** `.github/workflows/tests.yml` corre la suite en cada PR contra `main` y en cada push a `main`, y barre secretos y teléfonos sobre el diff del PR con `tools/barrer_secretos.py`. El workflow **no recibe ningún secreto**: `tests/conftest.py` ya aísla los clientes externos. El barrido **avisa, no bloquea** en su primera versión; una línea se exceptúa con `barrido-ok: <motivo>`, que exige motivo escrito a propósito. Qué hacer cuando el check sale rojo: `docs/RUNBOOK.md` § Cuando el check de CI sale en rojo. ⚠️ **Falta el gate del owner**: sin la protección de rama en `main` (Settings → Branches), el check informa pero **no impide** el merge.
- **Baseline de verificación:** `python -m pytest tests/` → **620 passed, 1 skipped** (al 2026-09-04, en `fix/endurecimiento-panel`, tras los 232 tests del Plan 5). ⚠️ Ese 620 es de **Windows**; el runner Linux del CI da **621**, porque el test que aquí se salta necesita `fcntl` — ese +1 no es un test nuevo. Antes: **345 passed** (al 2026-08-28, tras los 31 tests del barrido de secretos del Plan 0). ⚠️ **El baseline es por rama.** En `main` eran **314**; la rama `perf/gasto-places-importador` del Plan 2 da **357 passed, 1 skipped** porque añade 43 tests suyos. Un gate escrito como «≥ 357» es inalcanzable desde una rama basada en `main` hasta que el Plan 2 mergee: comparar siempre contra el baseline de la rama base, no contra un número absoluto. (Al 2026-08-27, tras los 84 tests del Plan 3: 26 de frontend, 13 de progreso, 23 de estado compartido y 22 de conteo. **Ojo con el comando**: `pytest.ini` ya trae `addopts = -q`, así que añadir `-q` lo convierte en `-qq` y **suprime la línea del resumen** — se ven los puntos y `exit 0`, pero nunca el número. Por eso el comando oficial va sin `-q`. Antes: 230 al 2026-08-24, tras los 9 tests de rutas portables y archivos en Files/; 227 tras los 6 primeros; 221 tras los 2 del estado real en ya_encolado; 219 tras los 4 del cierre de Chrome huerfano; 215 tras los 10 del lock huerfano del worker; 205 tras los 5 de la lada de pais para WhatsApp; 200 tras los 13 de la columna CONTACTO y el formato de telefono; 187 tras los 16 del escape de formulas del importador; 171 tras los 6 del heartbeat compartido; 165 al 2026-08-17 tras la ronda final de correcciones de `feat/despliegue-vultr`; 164 justo antes; 155 al cierre del 2026-08-13; el 144 anterior era stale: PRs #6-#9 agregaron 11 tests a archivos existentes sin actualizar la documentación). Es el ÚNICO baseline oficial. Nada se mergea con la suite en rojo. Nota: importar `app.py` en frío tarda ~100s (`googleapiclient` + Defender); en caliente ~8s. **No es pandas**: medido con `sys.modules`, ni pandas ni numpy llegan a cargarse — pandas estaba en `requirements.txt` sin que nadie lo importara y se retiró. `pytest.ini` ancla el rootdir al proyecto.
- **Datos personales:** teléfonos/nombres/correos de clientes **no** se commitean ni se vuelcan completos en logs; enmascarar (`+52...XXXX`). `.gitignore` cubre `*.json` (credenciales) y `debug_invalid_*`/`debug_timeout_*` (screenshots con PII de `envio_catalogo.py`).
- **Secretos:** nada hardcodeado. `GOOGLE_CREDENTIALS_JSON`, `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID` van por variables de entorno en el VPS (`/srv/panel/secretos/.env`, cargado entero por `env_file` del compose). **Pendiente owner:** rotar el token Telegram `8404009072` (expuesto en el historial git; ~14 copias).  <!-- barrido-ok: 8404009072 es el ID del bot de Telegram, no un telefono de cliente; ya consta como pendiente de rotar -->
- **Ramas:** **nunca** trabajar directo en `main` (el VPS auto-deploya desde ahí). Una rama por plan; PRs con `gh pr create --base main`; merge `--squash` solo con baseline verde y reviews sin CRITICAL/HIGH abiertos.
- **Idioma:** código con nombres en español (`guardar_respuesta_formulario`, `buscar_telefono`); docs y commits en español con prefijos convencionales (`fix:`, `feat:`, `test:`).

## Planes activos

**Tanda 2026-08-27, validada y ampliada el 2026-08-28** (6 planes, 53 tareas, **23 hechas**).
Índice: `docs/superpowers/plans/2026-08-27-indice-tanda.md`.
⚠️ **Empieza por** `docs/superpowers/plans/2026-08-28-validacion-tanda.md`: los anclajes
`archivo:línea` de los planes originales quedaron desplazados hasta 1,000 líneas cuando
`app.py` creció de 4,948 a 6,098, y ese documento trae los corregidos, dice qué trabajo ya
está hecho (B9 y B11 del Plan 1) y qué criterios cambiaron (CE1 del Plan 4, CE6 del Plan 2).
Cada plan abre además con una §0 de validación que **manda** sobre el resto del documento.

Orden de ejecución **0 → 2 → 1 → 4 → 5** (el Plan 3 está cerrado, PR #36 `ae0e1c9`):

| Plan | Estado | Qué resuelve |
|---|---|---|
| 0 — Integración continua | **4/4 ✅** | CI en cada PR: suite + barrido de secretos. PR #40 `c10d063` |
| 2 — Gasto de Google Places | **9/9 ✅** | Places optimizado, medidor y tope. PR #38 `4e06e64` |
| 1 — Relevancia de ciudades | 0/10 | **SIGUIENTE** — arranque en `docs/superpowers/plans/2026-08-28-handoff-plan1.md`. El ranking mide el historial de NIOVAL, no el mercado |
| 4 — Rediseño del panel | 0/12 | Movimiento, presentación y estados de carga en las 3 superficies |
| 5 — Endurecimiento | 0/8 | Rate limiting, escape de fórmulas, zona horaria, healthcheck |

Las decisiones abiertas al owner están en el índice §8; los nueve gates del owner, en §7.1.

**Tanda anterior 2026-08-13** (5 planes, histórica). Índice:
`docs/superpowers/plans/2026-08-13-indice-tanda.md`.
1. Evaluación `envio_catalogo.py` + baseline de tests + sanitización de secretos (**este plan**).
2. Evaluación del formulario de llamadas + matriz de flujo.
3. Integración catálogo + estados + corrección de número.
4. Captura de correo → columna T.
5. Operación 100% Railway (decisión de transporte WhatsApp = gate owner).

## Pendientes conocidos (gates del owner)

- Rotar `TELEGRAM_TOKEN` — **el riesgo abierto más grande** ahora que Railway está apagado: sigue vivo en el historial de git (~14 copias) y válido en el proveedor hasta que se rote allí.
- Elegir transporte de WhatsApp para el VPS: A=WhatsApp Business API (recomendado) / B=worker local (lo que corre hoy) / C=Selenium headless. ⚠️ Si se elige **C**, `envio_catalogo.py` pasa a un contenedor UTC y sus 5 relojes desnudos reintroducen el bug de fecha que cerró el Plan 5 — hay tripwire en `tests/test_endurecimiento_zona_horaria.py`.
- Corridas reales de WhatsApp (Plan 3 T3.6 / Plan 5 T5.5) y confirmación de la columna T de `LISTA DE CONTACTOS` (Plan 4 T4.1).
- ~~Autenticación del panel (M1)~~ — **RESUELTO** en `feat/despliegue-vultr`: el gate es
  fail-closed (`app.py:34-82`). ~~Y la exposición en Railway~~ — **CERRADA el 2026-09-05**:
  el owner apagó ese despliegue. Verificado: `https://web-production-1d453.up.railway.app/`
  devuelve **502 con `x-railway-fallback: true`** en todas las rutas, o sea sin despliegue
  activo detrás del dominio. ⚠️ Desde fuera **no se distingue** «servicio eliminado» de
  «app en bucle de fallo» — las dos dan 502, y la guarda fail-closed de `main` produciría
  exactamente eso si el servicio siguiera existiendo sin `PANEL_DASHBOARD_TOKEN`.
  Confirmarlo en la consola de Railway es del owner. En cualquiera de los dos casos el
  panel **no está abierto**: si resucitara sin token, moriría al arrancar en vez de servir.
