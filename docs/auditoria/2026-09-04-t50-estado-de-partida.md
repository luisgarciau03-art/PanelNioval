# T5.0 — Estado de partida del Plan 5 (endurecimiento)

**Fecha:** 2026-09-04
**Rama:** `fix/endurecimiento-panel`
**Base:** `main` @ `82995c3` (`docs(tanda): decisiones E1-E4 del owner y handoff del Plan 1 (#41)`)
**Tarea:** T5.0 — rama, respaldo y baseline *(bloquea T5.1–T5.7)*

Este documento es la evidencia contra la que T5.6 medirá el cierre. Todas las salidas
están pegadas literalmente, medidas en disco hoy, en esta rama.

---

## 1. Decisión de rama base (owner, 2026-09-04)

El Plan 5 podía salir de `main` o apilarse sobre `feat/rediseno-panel` (Plan 4). **El owner
eligió `main`.** Queda registrada como decisión **E5** del índice.

**Por qué importa y qué se comparó:**

| | Desde `main` (elegida) | Desde `feat/rediseno-panel` |
|---|---|---|
| Baseline | **388 passed, 1 skipped** | 900 passed, 2 skipped |
| Anclajes `archivo:línea` del plan | **Exactos** (5037 / 5115 / 5473) | Todos desplazados ~2,380 líneas |
| Bloqueo por gates ajenos | **Ninguno** | Detrás del gate CE10 (validación humana del top-20 de ciudades), sin fecha |
| Forma del PR | Un plan, un PR | Tercer PR apilado: mergearlo mergea Planes 1+4+5 |
| Coste | Rebase sobre `main` cuando #43 mergee | Ninguno |

El factor decisivo: los **cinco archivos de infraestructura** que concentran el Plan 5 son
**byte-idénticos** entre `main` y `feat/rediseno-panel`, así que salir de `main` no añade
riesgo de conflicto donde cae la mayor parte del trabajo:

```
$ for f in requirements.txt Dockerfile Procfile nixpacks.toml despliegue/docker-compose.yml; do
    git diff --quiet main feat/rediseno-panel -- "$f" && echo "$f IDENTICO"; done
requirements.txt              IDENTICO
Dockerfile                    IDENTICO
Procfile                      IDENTICO
nixpacks.toml                 IDENTICO
despliegue/docker-compose.yml IDENTICO
```

El conflicto futuro queda acotado a `app.py`, y dentro de él a las **tres rutas de
superficie** (`/`, `/formulario`, `/importador`) que el Plan 4 reescribió de
`render_template_string` a `render_template` y que T5.1 va a decorar con un límite.

⚠️ **Consecuencia operativa:** cuando el PR #43 mergee a `main`, esta rama **debe
rebasarse** antes de su propio merge, y el baseline de comparación pasa de 388 a lo que
`main` tenga entonces. El baseline es por rama; no existe un número absoluto.

---

## 2. Respaldo (rule 3: antes del cambio, no después)

```
$ python tools/respaldar_hojas.py docs/auditoria/respaldos/2026-09-04
  OK  ventas (221,794 bytes, 15 hojas)
  OK  respuestas (1,736,259 bytes, 7 hojas)
  OK  bruce-seguimiento (105,465 bytes, 4 hojas)
  OK  mensajes (766,270 bytes, 5 hojas)
  OK  contactos-frecuentes (2,192,536 bytes, 34 hojas)

65 hojas con huella. Respaldo en docs\auditoria\respaldos\2026-09-04
```

Confirmado **en disco, con tamaño > 0**, no por la salida del script:

```
$ ls -la docs/auditoria/respaldos/2026-09-04/
 105465  bruce-seguimiento-1i0bWYQG...xlsx
2192536  contactos-frecuentes-1wgEentS...xlsx
  19641  huellas.json
 766270  mensajes-1oEtAiYaYVdO...xlsx
1736259  respuestas-1U_z1KNqCxSR...xlsx
 221794  ventas-1Dlpm6swrNSP...xlsx

$ find docs/auditoria/respaldos/2026-09-04 -type f -size 0 | wc -l
0
```

Verificado en las **dos direcciones** que no se commitea dato de clientes:

```
$ git check-ignore -v docs/auditoria/respaldos/2026-09-04/x.json
.gitignore:30:docs/auditoria/respaldos/   docs/auditoria/respaldos/2026-09-04/x.json

$ git check-ignore -v docs/superpowers/plans/2026-08-28-plan5-endurecimiento-panel.md
(sin coincidencia: NO ignorado, correcto)

$ git status --short docs/auditoria/respaldos/ | wc -l
0
```

`huellas.json` guarda el SHA-256 de los encabezados de las 65 hojas: permite demostrar
después de T5.2 y T5.3 que **el orden de columnas no se alteró**, que es lo que rompería a
los proyectos externos sincronizados con esas hojas.

---

## 3. Baseline

Comando oficial, **sin `-q`** (`pytest.ini` ya trae `addopts = -q`; el segundo lo vuelve
`-qq` y suprime la línea del resumen):

```
$ python -m pytest tests/
........................................................................ [ 18%]
...............................s........................................ [ 37%]
........................................................................ [ 55%]
........................................................................ [ 74%]
........................................................................ [ 92%]
.............................                                            [100%]
388 passed, 1 skipped in 34.68s
EXIT=0
```

**Baseline de esta rama: 388 passed, 1 skipped.**

⚠️ El criterio **CE10** del Plan 5 dice «≥ 357 passed». Ese 357 es el baseline de
`perf/gasto-places-importador` (rama del Plan 2), no un número universal. Desde esta rama el
gate correcto es **≥ 388**, y se reescribe así en T5.6.

---

## 4. Los cinco huecos, medidos hoy

### 4.1 M5 — Rate limiting: cero

```
$ grep -c "limiter\|Limiter\|ratelimit" app.py
0
$ grep -ci "flask.limiter\|flask_limiter" requirements.txt
0
```

Confirmado abierto. Ni en el código ni en las dependencias.

### 4.2 M14 — Escapado de fórmulas: se define una vez, se usa una vez

```
$ grep -n "_escapar_formula" app.py
5037:def _escapar_formula(valor):
5115:        nuevos = [[_escapar_formula(v) for v in fila] for fila in nuevos]
```

Confirmado: definido en 5037, aplicado solo en 5115 (dentro de `_exportar_a_sheets`, el
importador). Las demás rutas de escritura no pasan por ahí.

### 4.3 M2 — Zona horaria: seis `datetime.now()` desnudas, sin `TZ` en el contenedor

```
$ grep -c "datetime.now()" app.py
6
$ grep -n "datetime.now()" app.py
3092:        fecha_hora = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
3202:        fecha = datetime.now().strftime('%d/%m/%Y %H:%M')
3521:        ahora = datetime.now().strftime(nc.FMT_TIMESTAMP)
3594:        ahora = datetime.now().strftime(nc.FMT_TIMESTAMP)
5079:    fecha  = datetime.now().strftime('%d/%m/%Y')
5080:    semana = datetime.now().isocalendar()[1]

$ grep -rn "TZ" Dockerfile despliegue/
(sin resultados)
$ grep -ci "tzdata" requirements.txt
0
```

Las seis coinciden con las del plan. `5080` es la `isocalendar()[1]` que alimenta la gráfica
«Contactos por Semana». Ni `TZ` en el contenedor ni `tzdata` en las dependencias: **las dos
capas que pide T5.3 están ausentes**, y la falta de `tzdata` es el riesgo R3 (el panel no
arranca) si se añade `ZoneInfo` sin ella.

### 4.4 M9 — Healthcheck: no existe, ni la ruta ni la directiva

```
$ grep -c "HEALTHCHECK" Dockerfile
0
$ grep -rni "healthcheck" despliegue/
(sin resultados)
$ grep -n "/salud" app.py
(sin resultados: la ruta no existe)
```

### 4.5 M3 — Hilo daemon sin manejador de señal

```
$ grep -c "daemon=True" app.py
2
$ grep -n "daemon=True" app.py
4644:# El hilo del importador es daemon=True: un reinicio del contenedor lo mata a
5473:    t = threading.Thread(target=_worker_importador, args=(ciudad, gmaps_api_key), daemon=True)

$ grep -n "SIGTERM\|signal\." app.py
(sin resultados: no hay manejador de senal)
```

⚠️ **Trampa registrada.** El conteo crudo da **2**, pero solo **una** es código: la línea
`4644` es el *comentario* que explica el problema. Es exactamente el fallo documentado en
`un-guarda-se-dispara-con-su-propia-documentacion`. T5.6 **no** debe medir «`daemon=True`
pasó de 2 a N»: debe excluir las líneas de comentario, así:

```
$ grep -n "daemon=True" app.py | grep -v ":[[:space:]]*#"
5473:    t = threading.Thread(..., daemon=True)
```

---

## 5. Hallazgos que cambian tareas posteriores

Ninguno se resuelve en T5.0; los tres se anotan aquí para que la tarea que los hereda no
tropiece.

### H1 — El nombre `test_plan5_*` ya está tomado, por **otro** Plan 5

`tests/test_plan5_operacion.py` (376 líneas) **existe ya en `main`** y pertenece al Plan 5
de la tanda **2026-08-13** («Operación 100% Railway»), no a este. Contiene
`TestAuthPanel`, `TestHeartbeat`, `TestGuardasArranque`, `TestRutaCredenciales`,
`TestHeartbeatCompartido`, `TestEscapeFormula`, `TestColumnaTelefonoContactos` y
`TestFormatoTelefonoContactos`.

**Consecuencia:** los tests nuevos de T5.1–T5.5 **no** deben llamarse `test_plan5_*`, o el
archivo de dos tandas distintas queda mezclado y el `git log` deja de explicar nada. Usar
nombres por hueco (`test_endurecimiento_limites.py`, `test_endurecimiento_escape.py`, …).

**Además:** ese archivo ya trae `TestEscapeFormula`. T5.2 tiene que **inventariar lo que ya
está cubierto antes de escribir**, no duplicarlo.

### H2 — El patrón obvio para inventariar escrituras a Sheets sobrecuenta

CE5 pide un test que localice **todas** las escrituras a gspread y falle si alguna no pasa
por el escape. El patrón directo no sirve:

```
$ grep -c "append_row\|append_rows\|\.update(\|update_cell\|batch_update\|update_acell" app.py
24
```

De esas 24, **al menos siete no son escrituras a Sheets**: `.update(` casa también con
métodos de `dict` y `set` de Python, y con comentarios.

| Línea | Qué es en realidad |
|---|---|
| 51 | `app.config.update(...)` — configuración de Flask |
| 333 | `all_keys.update(...)` — `set` de Python |
| 5076 | `claves_existentes.update(...)` — `set` |
| 5119 | `nombres_existentes.update(...)` — `set` |
| 5203 | `cache_places.update(...)` — `dict` |
| 5117, 5483 | líneas de comentario |

Un test CE5 construido sobre este patrón «protegería» la línea de configuración de Flask y
daría por exhaustivo un inventario que no lo es. **T5.2 debe clasificar por objeto receptor
(la worksheet), no por nombre de método.**

### H3 — `value_input_option` decide si la fórmula llega a evaluarse

Las escrituras reales no son equivalentes entre sí. Conviven los dos modos:

- `value_input_option='USER_ENTERED'` — Sheets **interpreta** el contenido: aquí el `=` es
  fórmula. Líneas `941`, `974`, `3230`, `5116`.
- `value_input_option='RAW'` — Sheets guarda la cadena tal cual. Líneas `3133`, `3389`.

T5.2 debe **decir por escrito** qué hace con las `RAW` en vez de tratarlas como iguales: si
se escapan también, hay que confirmar con el test `test_un_valor_normal_no_se_altera` que no
se está ensuciando un dato que ya era seguro. Esa es la mitad de R2.

---

## 6. Cierre de T5.0

| Requisito del criterio de cierre | Estado |
|---|---|
| Rama creada desde la base decidida por el owner | ✅ `fix/endurecimiento-panel` @ `82995c3` |
| Respaldo listado con tamaño, confirmado en disco | ✅ 5 XLSX + `huellas.json`, ninguno vacío, 65 hojas |
| Baseline anotado con el comando oficial | ✅ **388 passed, 1 skipped**, exit 0 |
| Los cinco `grep` de partida, con salida pegada | ✅ §4.1–§4.5 |

**Gates del owner tocados por este plan (se reportan, no se intentan):** rotar
`TELEGRAM_TOKEN` (gate 7) y apagar el despliegue de Railway (gate 8). Ninguno lo cierra el
Plan 5. La verificación de la imagen Docker construida (gate 5) bloquea **CE8 de T5.4**:
Docker no está instalado en esta máquina.
