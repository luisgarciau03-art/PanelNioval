# T5.6 — Verificación integral del Plan 5

**Fecha:** 2026-09-04 · **Rama:** `fix/endurecimiento-panel` @ `ed3453e` · **Base:** `main` @ `82995c3`

---

## 1. Los cinco huecos, antes y después

Medido con los mismos comandos de T5.0, sobre la misma rama.

| Hueco | T5.0 (partida) | T5.6 (ahora) |
|---|---|---|
| **M5** rate limiting | `grep -c limiter app.py` → **0**; sin dependencia | **12**; `Flask-Limiter>=4.0,<5` declarado |
| **M14** escapado | definido 1 vez, usado **1** (solo el importador) | **10** referencias; las 6 escrituras `USER_ENTERED` cubiertas |
| **M2** zona horaria | **6** `datetime.now()` desnudas; sin `TZ`; sin `tzdata` | **0** desnudas; `ENV TZ=America/Mexico_City`; `tzdata` declarado |
| **M9** healthcheck | `HEALTHCHECK` → **0**; ruta `/salud` inexistente | **1** en `Dockerfile`, **1** en compose; ruta en `app.py:226` |
| **M3** hilo daemon | `daemon=True` sin manejador; **0** menciones de `SIGTERM` | **7** menciones; parada cooperativa y `--graceful-timeout 120` en los 3 arranques |

⚠️ **`daemon=True` sigue ahí, y es correcto.** T5.5 no retira la bandera: añade la parada
cooperativa. Retirarla convertiría un reinicio en un cuelgue del apagado.

⚠️ **La trampa de T5.0 sigue viva.** `grep -c "daemon=True"` da 2 y solo una es código; la
otra es el comentario que explica el problema. La medición de arriba excluye comentarios.

## 2. Cada guarda, comprobado en las dos direcciones

`tools/verificar_endurecimiento.py` reintroduce cada defecto y exige que la suite se ponga
en rojo. Un test que pasa con y sin el arreglo no vale nada.

```
$ python tools/verificar_endurecimiento.py
  OK  M2 · el reloj vuelve a ser UTC
  OK  M2 · app.py deja de usar el helper
  OK  M14 · el escape se evade con un espacio delante
  OK  M14 · seguimiento deja de escapar
  OK  M5 · el importador pierde su limite propio
  OK  M5 · el limitador vuelve a correr antes de la auth
  OK  M5 · se retira ProxyFix (todos comparten cubo)
  OK  M5 · la fila 1 (encabezados) vuelve a ser escribible
  OK  M3 · el manejador deja de encadenar al de gunicorn
  OK  M3 · la senal deja de llegar al bucle
  OK  M9 · /salud empieza a filtrar estado interno
  OK  M9 · el healthcheck pasa a usar curl (que la imagen no trae)

12 de 12 guardas detectan su defecto.
```

**El arnés está comprobado en las dos direcciones también.** Se le inyectó un «defecto» que
nadie vigila (un cambio inocuo en un comentario) y lo marcó `MAL`, lo listó como guarda que
no mide y salió con código 1. Un arnés que solo sabe decir OK no demuestra nada.

Los tres archivos que toca se restauran desde copia y **se verifica el SHA-256**:

```
  app.py               f85cc7bd20b1 == f85cc7bd20b1
  nucleo_catalogo.py   39be8fdb8efa == 39be8fdb8efa
  Dockerfile           d6bee1b28ee1 == d6bee1b28ee1
```

Nunca se usa `git checkout` para restaurar: revierte a HEAD y se lleva lo no commiteado.

## 3. Baseline

```
$ python -m pytest tests/
620 passed, 1 skipped
```

| Momento | Tests |
|---|---|
| Base (`main`, T5.0) | 388 |
| Tras T5.3 (zona horaria) | 412 |
| Tras T5.2 (escapado) | 514 |
| Tras T5.1 (límites y cotas) | 562 |
| Tras T5.5 (parada ordenada) | 580 |
| Tras T5.4 (healthcheck) | **620** |

**+232 tests, ninguna regresión.** CE10 pedía ≥ 388 desde esta base.

⚠️ Este 620 es de **Windows**. El runner Linux del CI dará **621**: el test que aquí se
salta necesita `fcntl`. Ese +1 no es un test nuevo.

## 4. Barrido de secretos

```
$ git --no-pager diff main HEAD | python tools/barrer_secretos.py
Barrido limpio: 0 hallazgos en 3463 lineas anadidas.
```

Comprobado en la dirección útil: el mismo barrido sobre una clave sintética con forma de
Google API key **sí la marca**. Un barrido que no encuentra nada no demuestra nada.

## 5. Recorrido funcional, con la auth y el limitador ACTIVOS

Arranque realista: token definido, bypass retirado, y **las dos vías de credenciales de
Google cortadas** (`GOOGLE_CREDENTIALS_JSON` fuera y `GOOGLE_CREDENTIALS_FILE` a una ruta
inexistente), comprobando que `get_gs_client()` falla de verdad — sin eso, el panel lee
hojas de producción desde el `.json` de la raíz.

| Comprobación | Resultado |
|---|---|
| La app arranca con token definido | OK |
| `/salud` sin token | **200** |
| Ruta protegida sin token | **401** |
| Ruta protegida con token | 200 (datos vacíos — ver §7) |
| Manejador de `SIGTERM` instalado | sí, invocable |
| `ProxyFix` envolviendo la app | sí |
| `get_gs_client()` falla sin credenciales | sí (`FileNotFoundError`) |

Y con el limitador encendido, medido en T5.1: **200 peticiones anónimas** dan 401 sin
consumir cuota, y la petición legítima con token pasa. Antes del arreglo, 60 anónimas
dejaban fuera a todo el mundo.

## 6. Lo que NO se pudo verificar aquí

| Qué falta | Por qué | Gate |
|---|---|---|
| **CE8: contenedor marcado `unhealthy`** | Docker no está instalado en la máquina de desarrollo | Owner, gate 5 |
| **Imagen construida: `TZ`, `tzdata`, arranque** | Lo mismo | Owner, gate 5 |
| **gunicorn real** (encadenado de `SIGTERM`, `--graceful-timeout`) | No corre en Windows: necesita `fcntl` | Owner, gate 3 |
| **Recorrido con datos reales** (guardar formulario, seguimiento, corrida corta) | Escribe en hojas de producción y gasta Places | Owner |

Lo que **sí** se hizo en lugar de CE8: la sonda **exacta** del `Dockerfile`, ejecutada
contra el panel corriendo de verdad, da **exit 0**; con la ruta cambiada por una inexistente
da **exit 1**; y con `HTTP_PROXY` apuntando a un destino muerto sigue dando **exit 0**,
porque usa un opener con `ProxyHandler({})` vacío.

⚠️ **Las ocho herramientas de verificación del Plan 4 no aplican en esta rama.** Viven en
`feat/rediseno-panel` junto con `templates/` y `static/`, que aquí no existen porque esta
rama sale de `main`. En `tools/` de esta rama solo hay tres: `medir_llamadas_places.py`
(Plan 2), `medir_desfase_horario.py` (T5.3) y `verificar_endurecimiento.py` (T5.6).

## 7. Hallazgos que quedan abiertos y no los cierra el Plan 5

Todos salieron de las revisiones. Ninguno es una regresión introducida por este plan.

| # | Hallazgo | Origen |
|---|---|---|
| 1 | **El healthcheck no auto-repara.** En `docker compose` plano `unhealthy` es informativo: `restart: unless-stopped` reacciona a que el proceso muera, y Caddy hace `reverse_proxy panel:8000` sin `health_uri`. Da visibilidad, no remediación. Cerrarlo: sidecar `autoheal` o `health_uri` en Caddy | code-reviewer, T5.4 |
| 2 | **El contenedor corre como root** (sin `USER` en el `Dockerfile`) | security-reviewer, T5.4 |
| 3 | **`ProxyFix(x_for=1)` confía en la red `web`**, no solo en Caddy: cualquier contenedor de esa red llega a `panel:8000` directo y puede falsear `X-Forwarded-For`. Afecta al límite de 6/hora del importador, la única ruta facturable | security-reviewer, T5.4 |
| 4 | **Sin allowlist de columnas** en `/api/seguimiento/update` y `/api/bruce/actualizar`. Las cotas impiden romper los encabezados; escribir *cualquier* columna sigue siendo posible, y no se puede cerrar sin cambiar el modal de edición, que genera sus campos desde las claves de la propia hoja | security-reviewer, T5.2 |
| 5 | **`envio_catalogo.py` conserva 5 relojes desnudos** y escribe en la misma hoja. Hoy no es bug porque corre en la PC del owner; se vuelve bug si se elige el transporte C (Selenium headless). Hay tripwire en los tests | los tres reviewers, T5.3 |
| 6 | **Una caída de Sheets devuelve 200 con datos vacíos.** `get_data` atrapa el error y degrada en silencio, así que el panel muestra «sin datos» en vez de un fallo. Preexistente, detectado en el recorrido de esta tarea | T5.6 |
| 7 | **Riesgo residual de las escrituras `RAW`**: seguras al escribir, pero el texto se reactiva al exportar a CSV/Excel o si otra ruta lo reescribe con `USER_ENTERED` | security-reviewer, T5.2 |

## 7.1 Auditoría del conjunto (`security-auditor`) — lo que ninguna revisión individual vio

Veredicto: **el panel queda más seguro y ninguna pieza revierte un control existente.**
Verificado contra la instantánea pre-Plan-5: ninguna escritura pasó de `RAW` a
`USER_ENTERED`, y las cotas nuevas no rechazan una edición legítima.

Seis hallazgos de **interacción** — cada uno vive en el cruce de dos cambios. **Cinco
corregidos** en `ac4c2d6`; uno queda abierto y reencuadra un criterio.

| # | Hallazgo | Estado |
|---|---|---|
| H6 | **Regresión real:** `tzdata` era dependencia dura del **worker local** y solo estaba declarada en el `requirements.txt` del panel. Sin ella la Tarea Programada del owner moría al importar, sin enviar un catálogo | ✅ corregido |
| H2 | Se podía **envenenar la sonda de Docker**: `X-Forwarded-For: 127.0.0.1` agotaba el cubo de la clave que usa la sonda | ✅ corregido |
| H5 | El manejador de señal tomaba un lock **no reentrante** antes de encadenar: retrasaba el apagado y podía autobloquearse | ✅ corregido |
| H4 | `ProxyFix` concedía `x_proto`/`x_host` que **nadie consume**, haciendo falsificables el Host y el esquema | ✅ corregido |
| — | El cubo de 6/hora del importador **se consumía al rechazar**: seis clics en un redespliegue lo bloqueaban una hora | ✅ corregido |
| **H1** | **CE1 estaba mal encuadrado.** Ver abajo | ⚠️ **abierto** |
| H3 | Ningún test ejercita la combinación de producción (auth ON + limitador ON) | ⚠️ abierto |

### H1 — CE1 es cierto de la tabla de rutas y falso del camino de la petición

El arreglo del DoS pre-auth (el gate corta antes de que la petición anónima consuma cuota)
tiene una consecuencia simétrica que no estaba documentada: **una petición sin token nunca
llega al limitador**, así que **los intentos de adivinar `PANEL_DASHBOARD_TOKEN` no están
acotados por nada**. No hay bloqueo, ni backoff, ni un log del 401, y Caddy no pone nada
delante.

Así que el limitador del Plan 5 es un control de **abuso autenticado** —que es exactamente
para lo que se diseñó: acotar la ruta facturable— y **no** de fuerza bruta ni de DoS. CE1
debe leerse así, y no como si cubriera las dos cosas.

Cierre propuesto, sin tocar el orden que arregló el DoS: un cubo propio de fallos de
autenticación dentro del propio gate, antes del 401. Es un **control nuevo**, no un arreglo,
y por eso se reporta en vez de colarlo al cierre del plan.

### Reordenación de los siete hallazgos abiertos

El auditor cambió la prioridad, y el motivo importa más que el orden:

1. **nº 3** (ProxyFix confía en la red `web`) sube al primer puesto: es la **precondición**
   de H2. Deja de ser «se puede evadir el 6/h» y pasa a ser «se puede manipular el
   healthcheck».
2. **nº 2** (contenedor como root) sube: es la única que se cierra con **una línea** (`USER`)
   y compone con todas las demás.
3. **nº 6** (Sheets caído devuelve 200 vacío) sube y **se cierra junto con el nº 1**: `/salud`
   responde 200 mientras todas las rutas devuelven listas vacías y el operador cree que no
   hay contactos. El healthcheck no puede verlo por diseño, y es correcto que no lo haga.
7. **nº 1** (el healthcheck no auto-repara) **baja, con advertencia**: ⚠️ **no cerrarlo antes
   que el nº 3**, o se construye un botón de reinicio remoto del panel.

### Uno más, preexistente, que ahora conviene anotar

`?token=` como vía de autenticación deja el token en el historial del navegador y en
cualquier `Referer` — y quedaría en el log de acceso el día que se añada `log` al bloque de
Caddy.

## 8. Estado de los criterios de éxito

| # | Criterio | Estado |
|---|---|---|
| CE1 | Toda ruta tiene límite | ✅ y el guarda **corregido**: la primera versión no podía detectar una exención |
| CE2 | El importador tiene límite propio y más estricto | ✅ 6/hora, verificado por comportamiento |
| CE3 | El límite responde 429 en JSON, no HTML | ✅ |
| CE4 | Toda escritura a Sheets escapa fórmulas | ✅ las 6 con `USER_ENTERED` efectivo |
| CE5 | El barrido de escrituras es exhaustivo | ✅ por AST, con las dos direcciones |
| CE6 | La fecha guardada es hora de México | ✅ sobre la ruta de escritura real |
| CE7 | La semana ISO es la correcta | ✅ |
| CE8 | El healthcheck detecta un panel colgado | ⚠️ **abierto — gate 5 del owner** |
| CE9 | `SIGTERM` no parte una escritura | ✅ y hubo que añadir puntos de parada dentro de la categoría: sin ellos no llegaba antes del `SIGKILL` |
| CE10 | Baseline sin regresiones | ✅ 620 ≥ 388 |

**9 de 10 cumplidos. CE8 depende de Docker y es del owner.**
