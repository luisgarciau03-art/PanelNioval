# PLAN 5 — ENDURECIMIENTO DE SEGURIDAD Y OPERACIÓN DEL PANEL

**Fecha de diseño:** 2026-08-28
**Proyecto:** PanelNioval — `C:\Users\PC 1\PanelNioval`
**Superficies:** rutas Flask de `app.py`, `Dockerfile`, `despliegue/docker-compose.yml`
**Rama de trabajo:** `fix/endurecimiento-panel` (desde `main` actualizado — **NUNCA `main`**)
**Baseline verificado en disco el 2026-09-04 en la rama de trabajo:** `python -m pytest tests/` →
**388 passed, 1 skipped**, exit 0. (El «357 passed» que este encabezado daba el 2026-08-28 era
el de `perf/gasto-places-importador`, rama del Plan 2, no el de la base de este plan.)
**Origen:** mejoras **M5**, **M14**, **M2**, **M3** y **M9** del índice de la tanda
2026-08-27 (§4.2–§4.4). Todas identificadas y ninguna asignada a un plan.

---

## 1. LOS CINCO HUECOS, CON EVIDENCIA MEDIDA HOY

Cada uno se verificó en disco el 2026-08-28. Ninguno viene de memoria.

### 1.1 M5 — Cero rate limiting, sobre un panel publicado en internet

```
$ grep -c "limiter\|Limiter\|ratelimit" app.py
0
```

El panel está en `https://panelnioval.duckdns.org` detrás de un token. El gate es
fail-closed y funciona (`app.py:34-82`). Pero **un token filtrado da barra libre**, y entre
lo que da acceso está `/api/importador/iniciar`, que dispara corridas de Google Places —
la única API **facturable** del proyecto. El tope de presupuesto del Plan 2 (T2.6) acota una
corrida; nada acota cuántas corridas se lanzan.

Las reglas globales de seguridad del entorno exigen rate limiting **en todos los endpoints**.

### 1.2 M14 — El escapado de fórmulas protege una sola ruta de escritura

```
$ grep -n "_escapar_formula" app.py
5037:def _escapar_formula(valor):
5115:        nuevos = [[_escapar_formula(v) for v in fila] for fila in nuevos]
```

Se **define** en 5037 y se **usa** en 5115, dentro de `_exportar_a_sheets`: solo el
importador. Las demás rutas que escriben a Sheets —`/api/seguimiento*`,
`/api/mensajes/update`, `/api/formulario/guardar`, `/api/bruce/*`— meten texto de usuario
sin pasar por ahí. Un valor que empiece por `=`, `+`, `-` o `@` se interpreta como fórmula
al abrir la hoja.

Esto **no es hipotético para este proyecto**: la protección se construyó precisamente porque
el riesgo se materializó en el importador (16 tests del escape de fórmulas, rama
`fix/inyeccion-formula-importador`). El mismo vector sigue abierto en las otras rutas.

### 1.3 M2 — El contenedor corre en UTC y la fecha se guarda desplazada

```
$ grep -c "datetime.now()" app.py
6
$ grep -rn "TZ" Dockerfile despliegue/
(sin resultados)
```

Seis llamadas a `datetime.now()` **sin `tzinfo`**, todas en rutas que escriben a Sheets:
`app.py:3092`, `3202`, `3521`, `3594`, `5079` y `5080`. `python:3.11-slim` corre en UTC y el
`Dockerfile` no fija `TZ`. México es UTC-6.

Consecuencia: **todo lo capturado después de las 18:00 hora local se guarda con la fecha del
día siguiente.** Y `app.py:5080` usa `isocalendar()[1]`, así que la semana también puede caer
mal — justo el campo por el que agrupa la gráfica "Contactos por Semana" del dashboard.

Es un **bug de datos**, no cosmético: contamina lo ya escrito y lo seguirá haciendo.

### 1.4 M3 — El hilo del importador muere en silencio al reiniciar

`app.py:5473` lanza `threading.Thread(..., daemon=True)`. El Plan 3 ya cerró la mitad
visible del problema: hay un registro persistido (`app.py:4644` y siguientes) que permite
decir *"se interrumpió"* tras un reinicio, y **nunca veta** una corrida nueva.

Lo que sigue abierto es la mitad de datos: el hilo muere **a media escritura**, dejando
filas parciales en `LISTA DE CONTACTOS` sin que nadie lo sepa ni lo pueda deshacer.

### 1.5 M9 — Sin healthcheck: un panel colgado se ve igual que uno sano

```
$ grep -c "HEALTHCHECK" Dockerfile
0
```

Ni en el `Dockerfile` ni en `despliegue/docker-compose.yml`. Un contenedor que arrancó pero
no responde queda `Up` para Docker y para Caddy. El owner se entera cuando abre el panel.

---

## 2. OBJETIVO Y ALCANCE

**Objetivo.** Cerrar los cinco huecos con el mínimo de cambio funcional, sin tocar el
comportamiento visible del panel salvo donde el comportamiento actual es el defecto.

### En alcance
- Rate limiting en todas las rutas, con un límite propio y más estricto para el importador.
- `_escapar_formula` aplicado a **todas** las escrituras a Sheets.
- Zona horaria explícita, en el contenedor y en el código.
- Healthcheck en `Dockerfile` y en `docker-compose.yml`.
- Cierre ordenado del hilo del importador ante `SIGTERM`.

### Fuera de alcance
- Rotar `TELEGRAM_TOKEN` y apagar Railway. Son **gates del owner**: quitarlo del código no
  lo rota, y el despliegue solo lo apaga quien tiene la cuenta.
- Migrar el estado del importador a una cola multi-trabajo (M8). Es una feature, no un
  hueco de seguridad, y depende de decisiones de producto.
- Corregir **retroactivamente** las fechas ya escritas con desplazamiento. Ver `SUPUESTO`
  en §2.1: exige decidir qué se hace con datos históricos de clientes.

### 2.1 Supuestos

`SUPUESTO: la corrección de zona horaria aplica de aquí en adelante; las filas ya escritas
con la fecha desplazada NO se reescriben, porque reescribir histórico de clientes sin que el
owner lo pida es una operación destructiva encubierta. Se documenta cuántas filas podrían
estar afectadas y se deja la decisión al owner — afecta Plan 5, Tarea T5.3.`

`SUPUESTO: el rate limiting se implementa en proceso (memoria del único worker de gunicorn),
no con Redis. Razón: gunicorn corre --workers 1 --threads 4, así que un contador en memoria
es exacto; meter Redis añadiría una dependencia de infraestructura para resolver un problema
que hoy no existe — afecta Plan 5, Tarea T5.1.` Ver **D5** en DECISIONES PENDIENTES del
índice.

### 2.2 Criterios de éxito (medibles)

| # | Criterio | Cómo se mide |
|---|---|---|
| CE1 | Toda ruta tiene límite | Test que recorre `app.url_map` y falla si alguna ruta no está cubierta. **No** una lista escrita a mano: una ruta nueva sin límite debe romper el test |
| CE2 | El importador tiene un límite propio y más estricto | Test: N+1 llamadas a `/api/importador/iniciar` devuelven 429 |
| CE3 | El límite responde 429, no 500 | Test del código de estado y del cuerpo |
| CE4 | Toda escritura a Sheets escapa fórmulas | Test por ruta: un valor `=1+1` llega a la hoja como texto |
| CE5 | El barrido de escrituras es exhaustivo | Test que localiza todas las llamadas de escritura a gspread y falla si alguna no pasa por el escape. **Verificación en las dos direcciones**: encuentra una que sabe que está protegida y una que sabe que no |
| CE6 | La fecha guardada es hora de México | Test con reloj congelado a las 19:00 UTC-6: la fecha escrita es la de **hoy**, no la de mañana |
| CE7 | La semana ISO es la correcta | Test en un cambio de semana |
| CE8 | El healthcheck detecta un panel colgado | Se levanta el contenedor con la ruta de salud rota; `docker ps` lo marca `unhealthy` |
| CE9 | `SIGTERM` no parte una escritura | Test: la señal a media corrida deja el estado en `interrumpido` y ninguna fila a medias |
| CE10 | Baseline sin regresiones | `python -m pytest tests/` → **≥ 388 passed** (baseline de `main`, medido en T5.0 el 2026-09-04). ⚠️ **Corregido:** el «≥ 357» original era el baseline de `perf/gasto-places-importador` (rama del Plan 2), no un número universal — un gate absoluto es inalcanzable desde otra rama base. Si esta rama se rebasa sobre un `main` con el PR #43 dentro, el gate sube al baseline de ese `main` |

---

## 3. TAREAS

> **Formato blueprint.** Cada tarea es autocontenida.

### T5.0 — Tarea Cero: rama, respaldo y baseline *(bloquea todo)*

**Depende de:** nada. **Bloquea a:** T5.1–T5.7.

**Contexto autocontenido.** `C:\Users\PC 1\PanelNioval`, panel Flask sobre Google Sheets.
`main` tiene auto-deploy a Railway y a Vultr: **nunca se trabaja ahí**. Este plan **sí**
toca rutas que escriben en hojas de producción, así que el respaldo no es formalidad.

**Qué hacer.**
1. `git checkout main && git pull`, crear `fix/endurecimiento-panel`.
2. `python tools/respaldar_hojas.py docs/auditoria/respaldos/2026-08-28`. **Confirmar que
   los archivos existen en disco con tamaño > 0 antes de seguir.**
3. Baseline: `python -m pytest tests/` (**sin `-q`**; `pytest.ini` ya lo trae y el segundo
   lo vuelve `-qq`, que oculta el número). Anotar el número exacto.
4. Inventariar, con salida pegada, el estado de partida de los cinco huecos: el `grep -c` de
   rate limiting, los usos de `_escapar_formula`, las seis `datetime.now()`, el
   `HEALTHCHECK` y el `daemon=True`. Es la evidencia contra la que se medirá el cierre.

**Criterio de cierre.** Rama, respaldo listado con tamaño, baseline y los cinco `grep` de
partida anotados en PROGRESO.

---

### T5.1 — Rate limiting en todas las rutas *(M5)*

**Depende de:** T5.0.

**Contexto autocontenido.** `app.py` no tiene ningún limitador. La autenticación es
fail-closed y exige token (header `X-Dashboard-Token`, `?token=`, o cookie de sesión);
`/api/catalogo/heartbeat` exige por separado `WORKER_TOKEN`. El bypass explícito
`PANEL_AUTH_DESACTIVADA=1` lo usan `tests/conftest.py` y el desarrollo local.

gunicorn corre **`--workers 1 --threads 4`** (`Dockerfile:23`, `nixpacks.toml:8`,
`Procfile:1`), así que un contador en memoria de proceso es exacto: no hay dos memorias.

**Qué hacer.**
1. Añadir `Flask-Limiter` a `requirements.txt` con límite global por defecto.
2. Límite **propio y más estricto** para `/api/importador/iniciar`: es la única ruta que
   gasta dinero real.
3. El heartbeat del worker (`/api/catalogo/heartbeat`) necesita un límite **holgado**: lo
   llama un proceso legítimo cada pocos segundos. Un límite mal calibrado ahí tumba el
   worker de catálogo del owner.
4. El limitador **no debe activarse en los tests**, o los tests se vuelven dependientes del
   orden de ejecución. Se desactiva con la misma variable que ya usa `conftest.py`.
5. Respuesta 429 con cuerpo JSON coherente con el resto de la API, no la página HTML por
   defecto de Flask-Limiter.

**TDD — estos tests se escriben ANTES:**
- `test_toda_ruta_registrada_tiene_limite` — recorre `app.url_map`. **No una lista a mano**:
  una ruta nueva sin límite tiene que romper este test (CE1).
- `test_el_importador_devuelve_429_al_pasarse`
- `test_el_429_trae_json_y_no_html`
- `test_el_heartbeat_del_worker_aguanta_su_cadencia_real`
- `test_el_limitador_esta_desactivado_bajo_PANEL_AUTH_DESACTIVADA`

**Gate.** `security-reviewer` (obligatorio: toca el control de acceso) + `python-reviewer` +
`code-reviewer` + `silent-failure-hunter` (un limitador que traga su error deja pasar todo y
parece que funciona).

---

### T5.2 — Escapado de fórmulas en todas las escrituras a Sheets *(M14)*

**Depende de:** T5.0. **Independiente de T5.1**: se puede hacer en paralelo.

**Contexto autocontenido.** `_escapar_formula` está en `app.py:5037` y solo se aplica en
`app.py:5115`, dentro de `_exportar_a_sheets`. El resto de rutas de escritura mete texto de
usuario tal cual.

**Qué hacer.**
1. **Inventariar primero.** Localizar todas las llamadas de escritura a gspread
   (`append_row`, `append_rows`, `update`, `update_cell`, `batch_update`) y listarlas con
   `archivo:línea` y la ruta Flask que las alcanza. Este inventario es la salida de la
   tarea tanto como el código.
2. Aplicar `_escapar_formula` a cada valor de origen externo. Los valores generados por el
   propio panel (timestamps, contadores) no lo necesitan, pero pasarlos por el escape no
   hace daño y evita tener que razonar caso por caso en el futuro.
3. **No cambiar el comportamiento visible**: el escape antepone un apóstrofo, que Sheets no
   muestra. Verificar en una hoja de prueba, no por lectura del código.

**TDD — un test por ruta de escritura**, más:
- `test_un_valor_que_empieza_por_igual_llega_como_texto`
- `test_un_valor_normal_no_se_altera` — el escape que altera datos legítimos es peor que no
  tenerlo
- `test_el_inventario_de_escrituras_esta_completo` (CE5) — falla si aparece una llamada de
  escritura nueva sin escape. **Comprobado en las dos direcciones**: se le da una ruta
  protegida (debe pasar) y una sin proteger (debe fallar)

**Gate.** `security-reviewer` (inyección de fórmulas es su dominio) + `python-reviewer` +
`code-reviewer` + `silent-failure-hunter`.

---

### T5.3 — Zona horaria explícita *(M2)*

**Depende de:** T5.0.

**Contexto autocontenido.** Seis `datetime.now()` sin `tzinfo` en `app.py:3092`, `3202`,
`3521`, `3594`, `5079` y `5080`, todas en rutas que escriben a Sheets. El `Dockerfile` no
fija `TZ` y `python:3.11-slim` corre en UTC. México es UTC-6.

**Qué hacer.**
1. **Dos capas, no una.** Fijar `ENV TZ=America/Mexico_City` en el `Dockerfile` **y** usar
   `zoneinfo.ZoneInfo('America/Mexico_City')` explícito en el código. Solo la variable de
   entorno deja el código dependiendo del despliegue: en la máquina del owner (Windows,
   hora local) y en el runner de CI (UTC) darían resultados distintos, y los tests pasarían
   o fallarían según dónde corran.
2. Centralizar en un helper `_ahora_mexico()` en vez de repetir el `tzinfo` seis veces.
3. Añadir `tzdata` a `requirements.txt`: `python:3.11-slim` **no trae la base de zonas
   horarias**, y `ZoneInfo` lanza `ZoneInfoNotFoundError` sin ella. Verificar en un
   contenedor construido de verdad, no leyendo el `Dockerfile`.
4. **Medir el alcance del histórico**: contar cuántas filas de las hojas tienen una hora
   entre 00:00 y 06:00 (las candidatas a estar desplazadas) y anotar el número. **No
   corregirlas** — ver el `SUPUESTO` de §2.1.

**TDD:**
- `test_la_fecha_guardada_usa_hora_de_mexico` — reloj congelado a las 19:00 hora de México
  (01:00 UTC del día siguiente): la fecha escrita debe ser la de hoy (CE6)
- `test_la_semana_iso_es_la_de_mexico` (CE7)
- `test_el_helper_no_depende_de_la_tz_del_sistema` — pasa igual en Windows local y en el
  runner UTC

**Gate.** `python-reviewer` + `code-reviewer`. `security-reviewer` **no aplica** aquí y se
deja constancia: no toca auth, ni entrada de usuario, ni secretos.

---

### T5.4 — Healthcheck del contenedor *(M9)*

**Depende de:** T5.0.

**Contexto autocontenido.** `Dockerfile` sin `HEALTHCHECK`; `despliegue/docker-compose.yml`
tampoco lo define. La copia viva del compose está en `/srv/panel/` del VPS
`155.138.200.66`; las plantillas versionadas están en `despliegue/`.

**Qué hacer.**
1. Ruta `/salud` **sin autenticación** que devuelva 200 y un JSON mínimo. Sin auth a
   propósito: un healthcheck que necesita el token del panel no puede correr desde Docker.
2. Que **no toque Google Sheets**: un healthcheck que llama a una API externa convierte una
   caída de Google en un reinicio del panel, que es peor que la caída.
3. Que **no filtre nada**: ni versión de dependencias, ni rutas internas, ni si hay una
   corrida en curso. Una ruta sin auth es superficie pública.
4. `HEALTHCHECK` en el `Dockerfile` y el bloque equivalente en
   `despliegue/docker-compose.yml`.

**TDD:**
- `test_salud_responde_200_sin_token`
- `test_salud_no_llama_a_google`
- `test_salud_no_expone_estado_interno_ni_versiones`

**Verificación (CE8).** Levantar el contenedor con la ruta rota a propósito y confirmar que
`docker ps` lo marca `unhealthy`. **Un healthcheck que solo se ha visto en verde no está
probado.**

**Gate.** `security-reviewer` (**obligatorio**: es la única ruta sin auth del panel) +
`code-reviewer` + `docker-patterns`.

---

### T5.5 — Cierre ordenado del hilo del importador *(M3)*

**Depende de:** T5.0.

**Contexto autocontenido.** `app.py:5473` lanza el hilo con `daemon=True`. El Plan 3 ya
persiste un registro que permite decir "se interrumpió" (`app.py:4644` y siguientes) y que
**nunca veta** una corrida nueva. Lo que falta es que el reinicio no parta una escritura.

**Qué hacer.**
1. Manejador de `SIGTERM` que ponga una bandera de parada cooperativa. El bucle del worker
   la consulta **entre negocios**, nunca a media escritura a la hoja.
2. Al recibirla: terminar la fila en curso, marcar el estado como `interrumpido` **con lo ya
   guardado**, y salir. Es exactamente el patrón que T2.6 ya usa para
   `presupuesto_agotado`, y conviene reutilizarlo en vez de inventar un segundo camino.
3. `gunicorn` ya recibe el `SIGTERM` como PID 1 gracias a la forma exec del `CMD`
   (`Dockerfile:23` y su comentario). Verificarlo, no suponerlo.

**TDD:**
- `test_sigterm_a_media_corrida_deja_estado_interrumpido`
- `test_sigterm_no_parte_una_fila_a_medias` (CE9)
- `test_lo_ya_guardado_sobrevive_a_la_interrupcion`

**Gate.** `python-reviewer` + `code-reviewer` + `silent-failure-hunter` (una parada
cooperativa que se traga la señal deja el hilo corriendo y **parece** que funcionó).

---

### T5.6 — Verificación integral

**Depende de:** T5.1–T5.5.

**Qué hacer.**
1. `python -m pytest tests/` → **≥ 388 passed** (baseline de esta rama, T5.0), sin regresiones.
2. Los cinco `grep` de T5.0, repetidos: el de rate limiting pasa de 0 a > 0; el de
   `_escapar_formula` cubre todas las escrituras; `HEALTHCHECK` aparece; las
   `datetime.now()` desnudas desaparecen.
3. **Verificación en las dos direcciones de cada gate nuevo**: cada uno se prueba
   introduciendo el defecto a propósito y confirmando que el test **falla**, y quitándolo y
   confirmando que **pasa**. Un test que pasa con y sin el arreglo no vale nada.
4. Construir la imagen de verdad y comprobar dentro del contenedor: la zona horaria, `tzdata`
   presente, y el healthcheck marcando `healthy` y luego `unhealthy`.
5. Recorrido funcional: guardar una respuesta del formulario, actualizar seguimiento y
   lanzar una corrida corta del importador. Nada de esto debe haber cambiado de
   comportamiento.

**Gate.** `security-reviewer` sobre el conjunto + `code-reviewer` + `production-audit`.

---

### T5.7 — Cierre

**Depende de:** T5.6.

**Qué hacer.** Actualizar `CLAUDE.md` (baseline nuevo, la ruta `/salud`, los límites) y
`docs/RUNBOOK.md` (qué hacer ante un 429, cómo leer el healthcheck, cómo purgar). Documentar
la variable nueva de límites en `.env.example` **sin valores**. Commits convencionales en
español, uno por hueco, para poder revertir uno sin perder los otros cuatro. PR con
`gh pr create --base main`. Handoff.

**Gate de merge.** Baseline verde + reviews sin CRITICAL/HIGH abiertos.

---

## 4. TABLA DE ASIGNACIÓN DE HERRAMIENTAS POR ETAPA

| Etapa | Tarea | Herramienta asignada | Tipo | Fuente | Por qué es la mejor |
|---|---|---|---|---|---|
| A | T5.0 | `claude-mem:mem-search` | skill | claude-mem | El proyecto ya vivió la inyección de fórmulas en el importador (16 tests) y el gate fail-closed. Recuperar esas decisiones evita re-litigarlas. |
| A | T5.0, T5.2 | `Explore` | agente | built-in | Barrido de **todas** las llamadas de escritura a gspread sin quemar contexto: el inventario de T5.2 es su caso de uso exacto. |
| A | T5.0 | `production-audit` | skill | community | Auditoría de evidencia local de "qué se rompe en prod": los cinco huecos son justo eso. |
| A | T5.1 | `documentation-lookup` | skill | ECC | API **vigente** de Flask-Limiter vía Context7. Su configuración cambió entre 2.x y 3.x; escribirla de memoria produce límites que no se aplican. |
| B | todas | `blueprint` | skill | community | Brief autocontenido por paso para ejecución en frío. |
| B | T5.1 | `security-engineer` | agente | catalogo-agentes | Diseño del control: qué límite por ruta, dónde va el 429, cómo no tumbar al worker legítimo. |
| B | T5.3 | `architecture-decision-records` | skill | ECC | Congelar la decisión de las dos capas (ENV + `ZoneInfo`) y por qué no basta una. |
| C | T5.1–T5.5 | `superpowers:test-driven-development` | skill | superpowers | Todos los criterios son verificables con test: RED antes de tocar. |
| C | T5.1–T5.5 | `tdd-guide` | agente | catalogo-agentes | Hace cumplir tests-primero y cobertura; se **suma** a la skill de proceso. |
| C | T5.1–T5.3, T5.5 | `python-pro` | agente | catalogo-agentes | Implementación idiomática del stack real (Flask + Python 3.11). |
| C | T5.1, T5.4 | `backend-patterns` | skill | ECC | Forma del payload del 429 y de `/salud`, manejo de error del lado servidor. |
| C | T5.1, T5.2 | `security-review` | skill | ECC | Checklist de referencia al implementar rate limiting y sanitización de entrada. |
| C | T5.4 | `docker-patterns` | skill | ECC | `HEALTHCHECK`, `ENV TZ` y seguridad de contenedor: las tres cosas que toca T5.3 y T5.4. |
| C | T5.4 | `docker-expert` | agente | catalogo-agentes | Construir y verificar la imagen de verdad, no leer el `Dockerfile`. |
| C | T5.5 | `error-handling` | skill | ECC | Parada cooperativa y propagación: patrones de error sin tragarse la señal. |
| C | T5.5 | `superpowers:systematic-debugging` | skill | superpowers | El hilo daemon es un comportamiento inesperado bajo reinicio: se diagnostica antes de proponer el fix. |
| C | T5.1, T5.3 | `django-build-resolver` **[OPCIONAL]** | agente | catalogo-agentes | *Condición:* si añadir `Flask-Limiter` o `tzdata` rompe la instalación o produce un `ImportError` en la imagen. **El catálogo no tiene build-resolver de Flask puro**; este es el único especializado en errores de pip, Poetry e importación en Python, y su parte de Django no se usa. Se prefiere al genérico `build-error-resolver`, que es de TypeScript. |
| D | T5.1–T5.5 | `code-reviewer` | agente | catalogo-agentes | Obligatorio tras escribir o modificar código. |
| D | T5.1–T5.3, T5.5 | `python-reviewer` | agente | catalogo-agentes | Reviewer del stack. Se **suma** al code-reviewer, no lo reemplaza. |
| D | T5.1, T5.2, T5.4 | `security-reviewer` | agente | catalogo-agentes | Obligatorio: control de acceso, entrada de usuario que llega a una hoja, y una ruta pública sin auth. |
| D | T5.6 | `security-auditor` | agente | catalogo-agentes | Auditoría sistemática del conjunto al cerrar, distinta del review pieza a pieza. |
| D | T5.1, T5.2, T5.5 | `silent-failure-hunter` | agente | catalogo-agentes | Un limitador, un escape y una parada cooperativa son los tres sitios donde algo puede fallar **pareciendo** que funciona. Especialidad exacta. |
| D | T5.1–T5.5 | `python-testing` | skill | ECC | pytest, fixtures, reloj congelado y parametrización por ruta. |
| D | T5.2 | `pr-test-analyzer` | agente | catalogo-agentes | ¿El test del inventario mide comportamiento o solo que el módulo importa? |
| D | T5.6 | `superpowers:verification-before-completion` | skill | superpowers | Gate final: cada `grep` de cierre con su salida delante, no de memoria. |
| D | T5.6 | `verification-loop` | skill | ECC | Verificación de sesión completa antes del PR. |
| D | T5.4 | `canary-watch` **[OPCIONAL]** | skill | ECC | *Condición:* tras desplegar al VPS, vigilar `/salud` y detectar regresiones del despliegue. |
| E | T5.7 | `doc-updater` | agente | catalogo-agentes | `CLAUDE.md`, RUNBOOK y `.env.example` al día. |
| E | T5.7 | `github-ops` | skill | ECC | PR con historial completo y formato convencional. |
| E | T5.7 | `superpowers:finishing-a-development-branch` | skill | superpowers | Decide merge / PR / cleanup con los gates puestos. |
| E | T5.7 | `handoff` | skill | skills-local (ver §4.1) | Contexto comprimido para la siguiente sesión. |

**Fuentes canónicas usadas: 5 de 6** — catalogo-agentes, ECC, community, claude-mem,
superpowers, más built-in.

**Descarte explícito de claude-ads.** La suite entera (`ads-*`, `audit-*`, `copy-writer`,
`creative-strategist`, `visual-designer`, `format-adapter`) presupone cuentas publicitarias,
píxeles, creatividades o presupuesto de medios. Este plan endurece rutas Flask y un
contenedor: **no hay sujeto publicitario**. Ni siquiera `ads-math`, que en el Plan 2 sí
encaja porque allí hay un costo por prospecto que calcular; aquí no se optimiza gasto, se
cierra acceso. Constancia por escrito según la regla 4 de la biblioteca.

### 4.1 Nota sobre `skills-local`

El Nivel 2 de la biblioteca usa la etiqueta `skills-local`, que no es una de las 6 fuentes
canónicas. Se reporta tal cual y **no cuenta** para el mínimo de diversidad.

---

## 5. GATES DE VERIFICACIÓN POR TAREA

| Tarea | Tests | Reviewer del stack | code-reviewer | security-reviewer | Baseline |
|---|---|---|---|---|---|
| T5.0 | — (registra baseline y los 5 grep) | — | — | — | ✅ anota el número |
| T5.1 | ✅ TDD, 5 tests + `silent-failure-hunter` | python-reviewer | ✅ | ✅ **control de acceso** | ✅ sin regresiones |
| T5.2 | ✅ TDD, 1 por ruta + CE5 bidireccional | python-reviewer | ✅ | ✅ **inyección de fórmulas** | ✅ sin regresiones |
| T5.3 | ✅ TDD, 3 tests con reloj congelado | python-reviewer | ✅ | — (constancia en T5.3) | ✅ sin regresiones |
| T5.4 | ✅ TDD, 3 tests + contenedor `unhealthy` real | — | ✅ | ✅ **ruta sin auth** | ✅ sin regresiones |
| T5.5 | ✅ TDD, 3 tests + `silent-failure-hunter` | python-reviewer | ✅ | — | ✅ sin regresiones |
| T5.6 | ✅ suite + 5 grep + contenedor construido | ✅ `security-auditor` | ✅ | ✅ | ✅ ≥ 388 passed |
| T5.7 | ✅ suite completa antes del merge | — | ✅ | — | ✅ verde para mergear |

---

## 6. RIESGOS Y ROLLBACK

| # | Riesgo | Prob. | Impacto | Mitigación | Rollback |
|---|---|---|---|---|---|
| R1 | **El rate limiting tumba el worker de catálogo del owner** | **Alta** | Alto — deja de enviarse el catálogo por WhatsApp | El heartbeat tiene límite propio y holgado, calibrado contra su cadencia real, con test dedicado (CE2 no aplica ahí) | `git revert` del commit de T5.1; cada hueco va en su commit |
| R2 | El escape de fórmulas altera datos legítimos | Media | Medio — se ensucian las hojas | Test explícito `test_un_valor_normal_no_se_altera`. El escape solo actúa sobre valores que empiezan por `=`, `+`, `-`, `@` | `git revert` de T5.2; el importador conserva su escape original |
| R3 | `ZoneInfo` revienta en el contenedor por falta de `tzdata` | **Alta** | Alto — el panel no arranca en producción | T5.3 punto 3 lo añade a `requirements.txt` y **verifica en imagen construida**, no leyendo el `Dockerfile` | `git revert` de T5.3; vuelve a UTC, que es el bug conocido y no una caída |
| R4 | `/salud` sin auth expone información | Media | Medio | Devuelve un JSON mínimo, sin versiones ni estado interno, con test que lo fija (CE3 de T5.4) | Poner la ruta tras el token y usar un healthcheck de TCP en su lugar |
| R5 | La parada cooperativa nunca se dispara y el hilo sigue muriendo igual | Media | Bajo — se queda como está hoy | `silent-failure-hunter` en el gate; test que envía la señal de verdad | Ninguno necesario: el estado actual es el comportamiento previo |
| R6 | Conflicto de merge con el Plan 2, que también toca el worker del importador | **Alta** | Medio | Este plan va **después** del Plan 2 mergeado. T5.5 reutiliza el patrón de `presupuesto_agotado` en vez de crear un segundo camino de salida | Rebase sobre `main` ya con el Plan 2 dentro |
| R7 | Corregir el histórico de fechas se cuela en el alcance | Media | **Alto** — reescritura de datos de clientes sin pedirlo | El `SUPUESTO` de §2.1 lo excluye explícitamente: se **mide** cuántas filas podrían estar afectadas y se **reporta**, no se toca | — |

**Rollback general.** Rama `fix/endurecimiento-panel`, **un commit por hueco** (T5.1 a T5.5
separados) para revertir el culpable sin perder los otros cuatro. Nada se borra: lo retirado
va al respaldo fechado.

---

## 7. PROGRESO

| # | Tarea | Estado | Evidencia (commit/test/PR) | Fecha |
|---|---|---|---|---|
| T5.0 | Tarea Cero: rama, respaldo, baseline y los 5 grep | ✅ **HECHA** | Rama `fix/endurecimiento-panel` desde `main` @ `82995c3` (decisión E5 del owner). Respaldo: 5 XLSX + `huellas.json`, 65 hojas, ninguno vacío. Baseline **388 passed, 1 skipped**. Los 5 grep con salida pegada en [`docs/auditoria/2026-09-04-t50-estado-de-partida.md`](../../auditoria/2026-09-04-t50-estado-de-partida.md) | 2026-09-04 |
| T5.1 | Rate limiting en todas las rutas (M5) | PENDIENTE | | |
| T5.2 | Escapado de fórmulas en todas las escrituras (M14) | ✅ **HECHA** | `b78130b` + `b9b3216`. Inventario de 17 escrituras en [`docs/auditoria/2026-09-04-t52-inventario-escrituras.md`](../../auditoria/2026-09-04-t52-inventario-escrituras.md); escapan las 6 con USER_ENTERED efectivo (antes 1). 77 tests; suite **514 passed, 1 skipped**. Reviews: security-reviewer 1 HIGH + 1 MEDIUM resueltos, python-reviewer 1 HIGH resuelto, silent-failure-hunter 3 resueltos. ⚠️ 2 CRITICAL **preexistentes** sin cerrar (§5.1 del inventario) | 2026-09-04 |
| T5.3 | Zona horaria explícita, dos capas (M2) | ✅ **HECHA** | `fe907b0` + `bdfa5cb`. Helper `nc.ahora_mexico()` (ZoneInfo) + `ENV TZ` + `tzdata`. 24 tests nuevos; suite **412 passed, 1 skipped**. Reviews: code-reviewer APPROVE, python-reviewer Warning, silent-failure-hunter 2 HIGH — todos resueltos. Histórico medido y NO corregido: 2 de 2,662 filas del panel (0.1 %) | 2026-09-04 |
| T5.4 | Healthcheck del contenedor (M9) | PENDIENTE | | |
| T5.5 | Cierre ordenado del hilo del importador (M3) | PENDIENTE | | |
| T5.6 | Verificación integral | PENDIENTE | | |
| T5.7 | Cierre: docs, PR, handoff | PENDIENTE | | |

**Avance del plan: 3 / 8 tareas (38 %)**

**Gates del owner asociados (reportar, no intentar):** rotar `TELEGRAM_TOKEN` (M7) y apagar
el despliegue de Railway (M6). Ninguno lo cierra este plan, y ambos siguen siendo el riesgo
de seguridad más grande del proyecto.
