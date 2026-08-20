# Estado del despliegue de PanelNioval en Vultr — handoff

**Fecha:** 2026-08-17 · actualizado **2026-08-18** · **Rama:** `feat/despliegue-vultr` — **mergeada a `main` (`d58cae7`, PR #12)**

Lee esto antes de tocar nada. Los dos documentos de fondo son:
- Diseño: `docs/superpowers/specs/2026-08-17-panelnioval-vultr-design.md`
- Plan de 15 tasks: `docs/superpowers/plans/2026-08-17-despliegue-vultr.md`
- Bitácora de ejecución con todas las decisiones: `.superpowers/sdd/2026-08-17-despliegue-vultr/progress.md`

---

## Objetivo

Mover PanelNioval de Railway a un VPS Vultr (`155.138.200.66`) que ya hospeda a Bruce,
servido por TLS en `panelnioval.duckdns.org`, con autenticación fail-closed.

## Estado verificado (comprobado, no supuesto)

| Qué | Estado |
|---|---|
| Fase A — código | ✅ **COMPLETA**, mergeada a `main` en `d58cae7` (PR #12) |
| Fase B — servidor | 🟡 **Task 7 COMPLETA** (2026-08-18): `/srv/panel` provisionado, contenedor `panel` arriba y probado por red interna. Task 8 (Caddy+DNS+TLS) bloqueada por el gate del DNS |
| Fase C — testeo 7 capas | ⛔ no empezada |
| Suite de tests | **165 passed** (verificado por el controlador, no de segunda mano) |
| `panelnioval.duckdns.org` | sigue en `189.203.107.137` — verificado 2026-08-18: no responde en el puerto 80 tras 8s |
| Railway | **vivo y abierto**, pero congelado: no recoge redeploys. Es el rollback. |
| Rama | pusheada y mergeada con `--squash`; baseline **165 passed** verificado antes del push |

En el VPS solo corren `bruce` y `caddy`. De PanelNioval no hay nada todavía.

---

## Fase B — avance del 2026-08-18 (Task 7 completa)

Ejecutado contra `155.138.200.66`, **sin tocar DNS ni el Caddyfile**:

- `/srv/panel/app` clonado en `d58cae7`; `/srv/panel/secretos` con `chmod 700`.
- Service account subida a `/srv/panel/secretos/credentials.json` (`chmod 600`), validada
  por forma (`type=service_account`, proyecto `bubbly-subject-412101`), nunca por contenido.
- `PANEL_DASHBOARD_TOKEN`, `WORKER_TOKEN` y `SECRET_KEY` generados **en el servidor** con
  `openssl rand -hex 32` en `/srv/panel/secretos/.env` (`chmod 600`). Los valores no han
  salido del servidor ni aparecen en ninguna transcripción.
- Contenedor `panel` arriba: gunicorn PID 1, 2 workers, **0 reinicios**, 131 MB de 768.

Pruebas por red interna de Docker (Steps 7 y 8):

| Prueba | Resultado |
|---|---|
| `/`, `/formulario`, `/api/prospectos/stats` **sin** token | **401** en las tres |
| `/api/catalogo/worker-estado` **con** token | 200, `{"vivo":false,...}` |
| `/api/prospectos/stats` **con** token | 200 con datos reales de Sheets |

El 200 con datos reales valida en vivo la corrección de `GOOGLE_CREDENTIALS_FILE`: la ruta
de credenciales resuelve dentro del contenedor.

**No regresión de Bruce, comprobada:** `https://bruce.nioval.duckdns.org/` → 200; Bruce
consume 63 MB, igual que antes; el Caddyfile sigue con 0 referencias a `panelnioval`.
Nota: durante el despliegue había un script de despliegue de Bruce corriendo en paralelo
(PID 89823, ajeno a este trabajo) — no interfirió, pero conviene saberlo.

### Pendiente dentro de la Task 7

El **Step 5 quedó deliberadamente sin hacer** (decisión del owner: `TELEGRAM_TOKEN` aún sin
rotar). Ninguna de estas bloquea el arranque; el panel corre sin ellas:

| Variable | Sin ella |
|---|---|
| `TELEGRAM_TOKEN` / `TELEGRAM_CHAT_ID` | sin alertas de Telegram |
| `IMGBB_API_KEY` | 500 en `/api/ventas/upload-pago` |
| `GMAPS_API_KEY` | `{"ok": false}` en `/api/importador/iniciar` |
| `PAGO_FOLDER_ID` | ninguna ruta activa la llama hoy |

Se añaden con `ssh root@155.138.200.66 'nano /srv/panel/secretos/.env'` y
`cd /srv/panel && docker compose up -d`. Los valores los escribe el owner en el servidor.

### Railway

Verificado el 2026-08-18, **después** del merge: sigue devolviendo 200 sin token en `/` y en
`/api/prospectos/stats`. Confirma que está congelado (no auto-despliega desde `main`), así
que el rollback se conserva — y la fuga también. Cierre inmediato sin esperar al corte:
definir `PANEL_DASHBOARD_TOKEN` en las variables de Railway; el gate viejo sí la respeta.

---

## Lo que hizo la Fase A (16 commits)

1. **Los dos gates de auth pasaron de fail-open a fail-closed.** Antes, si faltaba la
   variable de entorno, el panel abría. Ahora la app **no arranca** sin
   `PANEL_DASHBOARD_TOKEN` ni `SECRET_KEY`, y `/api/catalogo/heartbeat` devuelve 401 sin
   `WORKER_TOKEN`. Único bypass, explícito: `PANEL_AUTH_DESACTIVADA=1` (lo usa `conftest.py`).
2. `Dockerfile` (forma exec, gunicorn como PID 1), `.dockerignore`, y plantillas en
   `despliegue/` para compose y Caddy.
3. `tools/smoke_railway.py` → `tools/smoke_panel.py`.
4. `iniciar-worker.bat` pide `WORKER_TOKEN` en bucle hasta valor no vacío.
5. Runbook de operación en VPS en `docs/RUNBOOK.md`.

## Trampas que costaron rondas de review — no volver a pisarlas

- **La ruta de credenciales.** `app.py` leía un nombre de archivo hardcodeado mientras el
  compose montaba en otra ruta: Sheets y Drive habrían reventado en el VPS. Ahora se lee de
  `GOOGLE_CREDENTIALS_FILE`, y el compose la fija a `/app/credentials.json`.
- **El baseline documentado estaba desactualizado 11 tests.** Decía 144, el real era 155
  (los PRs #6-#9 añadieron tests a archivos existentes). Corregido a 165 en `CLAUDE.md`,
  spec y plan.
- **Una ronda entregó tests que no podían fallar**: llamaban a una función inexistente cuyo
  `AttributeError` se tragaba un `except`, con el assert tras un guard que nunca se cumplía.
  Exigir siempre prueba de rotura deliberada antes de aceptar un test nuevo.
- **`get_pago_folder_id()` (`app.py:158`) es código muerto**, sin ningún llamador.

## Gates del owner (nada de esto lo puede hacer el agente)

| # | Gate | Bloquea |
|---|---|---|
| 1 | ~~Autorizar `git push` de la rama~~ | ✅ **HECHO** 2026-08-18 |
| 2 | **Repuntar `panelnioval.duckdns.org` → `155.138.200.66`** en duckdns.org. ⚠️ Es la entrada **`panelnioval`**, NO `nioval`: son registros DuckDNS distintos y `nioval` es el de Bruce | Task 8 — **único bloqueo activo** |
| 3 | Eliminar el servicio de Railway | Task 10 (es el rollback: va al final) |
| 4 | Ventana horaria fuera de 09:00-20:00 MX + teléfono del owner | Fase C |
| 5 | Rotar `TELEGRAM_TOKEN` | **YA NO bloquea**: solo alimenta alertas, no el arranque |

## Peligro operativo al llegar a la Fase C

Bruce corre en el **mismo servidor** con `WA_SCHEDULER=1`, `WA_GEO_AUTO=1`,
`WA_BUSCADOR_AUTO=1`, `WA_CAMPANA_AUTO=0`, y **25 de sus archivos leen o escriben el mismo
spreadsheet `seguimiento`** que el panel.

Una fila de prueba escrita en `seguimiento` o `PROSPECTOS BRUCE` puede hacer que Bruce le
mande un WhatsApp **real** a ese número dentro de la ventana 09:00-20:00 MX. El protocolo de
la Task 12 es obligatorio: respaldo previo verificado, huella SHA-256 de encabezados,
teléfono del owner en toda fila de prueba, y `WA_SCHEDULER=0` mientras dure la prueba.

Las hojas son de producción y están sincronizadas con proyectos externos: **no se altera el
orden de columnas.**

## Siguiente paso concreto

Con la autorización de push, la secuencia es: pushear → clonar en `/srv/panel` → generar
secretos en el servidor → levantar contenedor → **probar por red interna del Docker antes de
tocar el DNS** → repuntar DuckDNS → Caddy emite el certificado → smoke test → apuntar el
worker → apagar Railway.

---

## CIERRE — estado al 2026-08-19

**La migracion esta terminada y en produccion.** El panel corre en
`https://panelnioval.duckdns.org` con TLS de Let's Encrypt (valido hasta el 2026-11-16),
cerrado con token, y Railway esta apagado (devuelve 404).

### Testeo de 7 capas

| Capa | Estado |
|---|---|
| 1 · suite | 187 passed |
| 2 · gates sin token | 401 en 8/8 + `RuntimeError` capturado en contenedor desechable |
| 3 · rutas GET con token | 200 en 23/23 |
| 4 · escrituras sobre produccion | huellas SHA-256 identicas antes y despues: ninguna columna se movio |
| 5 · worker Selenium | pendiente: requiere arrancar `iniciar-worker.bat` en la PC del owner |
| 6 · no-regresion de Bruce | 3 pasos verificados, 1 no observable, 1 bloqueado por permisos |
| 7 · resiliencia | reinicio real del VPS: los 3 contenedores vuelven solos, mismo certificado |

Evidencia completa en `docs/auditoria/2026-08-18-testeo-vps.md`.

### Bugs encontrados y corregidos durante la verificacion

Ninguno lo causo la migracion; los tres son preexistentes que el testeo saco a la luz.

1. **Heartbeat en memoria del proceso** (PR #20). Con `gunicorn --workers 2`, diez consultas
   seguidas a `worker-estado` alternaban entre dos timestamps. Al parar el worker un proceso
   cruzaria el TTL antes que el otro y el panel diria "muerto"/"vivo" segun quien contestara.
   Resuelto persistiendo el latido en archivo compartido con escritura atomica.

2. **Inyeccion de formula en el importador** (PR #22). La ferreteria
   `+ Mas Seguro Distribuidora Ferretera` empieza por `+`, que Sheets parsea como formula:
   la celda mostraba `#ERROR!` y el operador no veia a quien llamaba. Se escapan las cadenas
   que empiezan por `= + - @`. **No** se cambio a RAW en bloque porque la fecha dejaria de
   parsearse como fecha.

3. **`.gitignore` no cubria `*.env`** (PR #15). Un archivo con credenciales vivas estaba sin
   ignorar dentro del repo. No llego a commitearse; se aparto con hash verificado.

### Incidente de credencial

`WORKER_TOKEN` quedo expuesto al pegarse en una conversacion. Rotado y verificado en las dos
direcciones: el viejo devuelve 401, el nuevo 200. Alcance acotado — solo autoriza el
heartbeat, no da acceso a datos de clientes. Detalle en el documento de auditoria.

### Pendientes del owner

| Pendiente | Por que no lo puede hacer el agente |
|---|---|
| Arrancar el worker (Capa 5) | Corre en la PC del owner, con Selenium y WhatsApp Web |
| Envio saliente de Bruce (Capa 6 Step 3) | Mandar un WhatsApp real requiere aprobacion humana |
| Cargar `GMAPS_API_KEY` | No venia en el archivo de entorno; sin ella el importador falla |
| Rotar `TELEGRAM_TOKEN` | Se revoca en el proveedor, no en el servidor |
| 57 celdas `#ERROR!` en `Respuestas de formulario 1` | Preexistentes, con el nombre original perdido; recuperarlas es decision del owner |

### Notas operativas que parecen fallos y no lo son

- **Bruce devuelve 502 durante su primer medio minuto** tras un reinicio: arranca mas lento
  que el panel.
- **`worker-estado` vuelve a `vivo:false` tras cada despliegue**, porque el archivo de latido
  vive en el contenedor y se recrea con el.
- **Gunicorn no registra accesos.** Cualquier conteo de codigos HTTP sobre `docker logs panel`
  da cero por ausencia de logging, no por ausencia de peticiones. Activar el log de accesos
  sin filtrar escribiria tokens en disco: el panel acepta `?token=` por query string.

### Servicios en el VPS al cierre

`panel`, `bruce`, `caddy` y `agendanioval` (este ultimo desplegado por el owner). Memoria en
torno a 1.0 GB de 1.9 GB. Al empezar eran dos servicios y 529 MB.
