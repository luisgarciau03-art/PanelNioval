# Reproducción documentada de los bugs del importador

**Plan:** 3 — Bug de conteo y pantallas de carga · **Tarea:** T3.0 (Tarea Cero)
**Fecha:** 2026-08-27
**Rama:** `fix/conteo-importador-y-estados-carga` (desde `main` en `034dd42`)
**Herramientas asignadas y usadas:** `claude-mem:mem-search` (claude-mem),
`superpowers:systematic-debugging` (superpowers).

> Un arreglo sin reproducción previa no se puede verificar. Este documento fija los
> números de **antes**, para poder comparar contra los de después en T3.8.

---

## 0. Estado de partida

| Hecho | Valor | Cómo se comprobó |
|---|---|---|
| Rama base | `main` @ `034dd42` | `git log --oneline -1` |
| Baseline de tests | **230 passed in 5.68s**, exit 0 | `python -m pytest tests/` |
| Respaldo previo al cambio | 5 XLSX + `huellas.json`, 65 hojas | `tools/respaldar_hojas.py` → `docs/auditoria/respaldos/2026-08-27/` |

Respaldo confirmado **en disco** antes de tocar nada:

```
bruce-seguimiento-...xlsx        105,337 bytes
contactos-frecuentes-...xlsx   2,183,435 bytes
huellas.json                      19,641 bytes
mensajes-...xlsx                 764,820 bytes
respuestas-...xlsx             1,734,576 bytes
ventas-...xlsx                   220,837 bytes
```

El directorio `docs/auditoria/respaldos/` está en `.gitignore` (contiene datos de
clientes), así que el respaldo existe pero no se versiona. Es lo correcto.

### 0.1 Hallazgo lateral: el comando de baseline no imprime su propio número

`pytest.ini` ya trae `addopts = -q`. El comando documentado en `CLAUDE.md`,
`python -m pytest tests/ -q`, suma el segundo `-q` y se convierte en `-qq`, que
**suprime la línea de resumen**. Se ven 230 puntos y `exit 0`, pero nunca la frase
`230 passed`. Un baseline que no imprime su número obliga a contar puntos a mano.

El número real se obtiene con `python -m pytest tests/` (sin el `-q` extra).
Se corrige la documentación en T3.9.

---

## 1. Cómo se reprodujo, y por qué así

`tools/reproducir_bugs_importador.py` reproduce los defectos de forma **determinista
y repetible**, con dobles de prueba en las dos fronteras externas (Places y Sheets).

Dos decisiones que hay que dejar por escrito, porque se apartan de la letra del plan:

**No se hizo una corrida real de Places.** El plan pedía correr el importador sobre
una ciudad real. Eso (a) factura Google Places, que la regla 10 del índice prohíbe a
los scripts de análisis, y (b) **escribe filas en `LISTA DE CONTACTOS` de producción**,
que es una mutación difícil de revertir sobre datos vivos de clientes. El repro con
dobles produce los mismos números y además es repetible. La corrida real contra la hoja
sigue siendo necesaria para cerrar **CE1** en T3.8, y **requiere autorización explícita
del owner**: queda marcada como gate en la tabla PROGRESO.

**No se usó gunicorn.** `gunicorn` no corre en Windows (depende de `fcntl`) y no está
instalado en esta máquina. Se levantan **dos procesos Flask independientes**, que es
exactamente el modelo de `gunicorn --workers 2`: pre-fork, procesos separados, sin
memoria compartida. La verificación con gunicorn real sobre el VPS queda para T3.8.

---

## 2. Síntoma A — "dice 20 y aparecen 10"

**Escenario:** ciudad ya trabajada. 12 ferreterías + 8 distribuidoras, de las cuales
6 son las mismas de la primera categoría, sobre una hoja que ya tenía 4 de ellas.

```
UI dice 'Encontrados'            : 20
Filas REALMENTE escritas en hoja : 10
Diferencia                       : 10
status final                     : done
```

Mensaje que lee el operador al terminar:

> "20 contactos encontrados · 0 descartados · **Guardados en Google Sheets**"

**El síntoma reportado por el owner queda reproducido con sus mismos números.**

Desglose de los 10 que faltan:

| Defecto | Cuántos se pierden | Por qué |
|---|---|---|
| **B2** ya estaban en la hoja | 4 | `_exportar_a_sheets` deduplica por `Nombre\|Dirección` (`app.py:4425-4432`) **después** de que se contó |
| **B3** contados dos veces | 6 | `vistos` es local a `_buscar_negocios` (`app.py:4329`), o sea por categoría |
| **B1** el contador no usa `nuevos` | — | `app.py:4525` suma `len(resultados)`; `nuevos` (`app.py:4519`) solo va al log |

El log interno **sí** tiene el número correcto — y nadie lo mira:

```
> ✓ Ferreterías: 12 aprobados, 0 descartados, 8 nuevos en Sheet
> ✓ Distribuidoras Ferreterías: 8 aprobados, 0 descartados, 2 nuevos en Sheet
> ✅ Completado en 0.0 min — 20 contactos encontrados
```

8 + 2 = 10 filas escritas. El titular dice 20.

---

## 3. Síntoma A bis — B4: la escritura falla y se reporta éxito

Se fuerza `get_worksheet` a lanzar `RuntimeError('cuota de Sheets agotada')`:

```
Filas escritas        : 0
status final          : done
campo error           : ''            <-- vacío
UI dice 'Encontrados' : 12
Última línea del log  : ✅ Completado en 0.0 min — 12 contactos encontrados
```

**Cero filas escritas, `status: done`, palomita verde y contador en 12.** El único
rastro del fallo es `[importador] sheets error: ...` por stdout del contenedor, donde
el owner no mira. Es un fallo abierto de libro: el `except` de `app.py:4471-4474`
devuelve `0`, que es indistinguible de "no había nada nuevo que escribir".

---

## 4. Síntoma B — B5: el estado vive en memoria de proceso

Dos procesos Flask en 5061 y 5062. Se lanza el trabajo **solo** en 5061 y se sondea
alternando:

```
POST /iniciar -> worker 5061: {"ok":true}

#   puerto  status   progreso  encontrados
1   5061    running  0         0
2   5062    idle     0         0  <-- MIENTE
3   5061    running  0         0
4   5062    idle     0         0  <-- MIENTE
...
20  5062    idle     0         0  <-- MIENTE

Respuestas con status 'idle' mientras el trabajo corre: 10 de 20
```

**El proceso que no lanzó el trabajo no sabe que existe.** Devuelve `idle`,
`progreso 0` y `encontrados 0`. Eso es exactamente el parpadeo que reporta el owner:
la barra salta a 0 %, "Encontrados" parpadea a 0 y la corrida "nunca termina", porque
el `done` del worker A solo lo ve la mitad de los sondeos.

**Honestidad sobre el 50 %:** esa proporción es **por construcción** — el repro alterna
a propósito. Lo que el experimento prueba es que el proceso B **no tiene el estado**,
no cuál es el reparto real del balanceador de gunicorn en producción.

**B6 aparece de regalo en la misma tabla:** durante los 20 sondeos, `progreso` se
mantuvo en `0` en el worker que sí tenía el trabajo. Con `progreso = i` (`app.py:4510`)
e `i` el índice de categoría, la barra está en 0 % durante toda la primera categoría.

---

## 5. Veredicto por defecto

Los nueve defectos de §1 del plan, con su estado tras esta tarea. T3.1 completa los
que aquí quedan como confirmados solo por lectura de código.

| # | Defecto | Estado | Evidencia |
|---|---|---|---|
| B1 | El contador cuenta aprobados, no filas escritas | **REPRODUCIDO** | §2 — 20 vs 10 |
| B2 | Duplicados contra la hoja | **REPRODUCIDO** | §2 — 4 de los 10 |
| B3 | Duplicados entre categorías | **REPRODUCIDO** | §2 — 6 de los 10 |
| B4 | Fallo silencioso de escritura | **REPRODUCIDO** | §3 — 0 filas, `done`, ✅ |
| B5 | Estado en memoria de proceso | **REPRODUCIDO** | §4 — 10 de 20 sondeos `idle` |
| B6 | Barra con tres valores | **REPRODUCIDO** | §4 — `progreso` fijo en 0 |
| B7 | Recargar pierde el trabajo | Confirmado por código | Solo `iniciar()` arranca el sondeo (`app.py:4878`); no hay restauración al cargar |
| B8 | Botón trabado / sondeo eterno | Confirmado por código | `await fetch` sin `try/catch` (`app.py:4870-4874`); `setInterval` sin corte en `idle` |
| B9 | Nombre de ciudad sin escapar | Confirmado por código | `onclick="seleccionarCiudad('${c.ciudad}',this)"` (`app.py:4840`) |

B7, B8 y B9 se cierran en T3.1 con experimento propio (recorrido de rutas de clic).

---

## 6. Corrección de una cita del plan

El documento del Plan 3 sitúa el `--workers 2` del Dockerfile en `Dockerfile:22`.
La línea real es **`Dockerfile:17`**:

```
17:CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "120"]
```

`Procfile:1` sí es correcto. El defecto es el mismo; solo se corrige la referencia.

---

## 7. T3.1 — Veredicto por experimento, y lo que el plan no listaba

**Herramientas asignadas y usadas:** `superpowers:systematic-debugging` (superpowers),
`debugger` (catalogo-agentes), `click-path-audit` (community), `Explore` (built-in).

Los nueve defectos de §1 salieron de leer código. Deducir no es confirmar. Esta
sección los somete a experimento. Un defecto **descartado** también es resultado
válido, y hay dos.

### 7.1 B5 — evidencia de PID

El repro imprime el PID de cada proceso:

```
puerto 5061 -> PID 20460     <- recibe el POST, tiene el trabajo
puerto 5062 -> PID 16972     <- responde 'idle' a los sondeos
```

Dos procesos del sistema operativo distintos, cada uno con su propio `_import_job`.
No es una hipótesis sobre el balanceador: son dos memorias separadas.

**Hay un tercer sitio con `--workers 2` que el plan no listaba.** Son tres:

```
Procfile:1       web: gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120
Dockerfile:17    CMD ["gunicorn", "app:app", ..., "--workers", "2", "--timeout", "120"]
nixpacks.toml:8  cmd = "gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120"
```

Cualquier cambio en el arranque tiene que tocar los tres o quedará a medias.

### 7.2 B3 — corroboración con datos reales de producción

El repro demuestra el mecanismo con datos sintéticos. El respaldo del 2026-08-27
demuestra que el solape **existe de verdad** en `LISTA DE CONTACTOS` (7,145 filas):

| Medida | Valor |
|---|---|
| Filas con `place_id` extraíble del enlace de Maps | 3,030 |
| `place_id` distintos | 2,955 |
| `place_id` bajo la categoría `Ferreterías` | 1,904 |
| `place_id` bajo `Distribuidoras Ferreterías` | 747 |
| **`place_id` presentes bajo AMBAS categorías** | **12** |
| Ciudades con filas de las dos categorías | 62 |

Doce negocios reales entraron a la hoja bajo las dos categorías. El dedup por
`Nombre|Dirección` no los atrapó porque el nombre o el domicilio variaban un poco;
un dedup por `place_id` sí lo habría hecho. **B3 no es teórico.**

La proporción `Distribuidoras / Ferreterías` por ciudad va de 0.14 a 1.46: la segunda
categoría escribe muchas menos filas de las que cuenta, que es lo que predice B3.

*Dato lateral, no atribuible al importador:* hay 352 claves `Nombre|Dirección`
repetidas (768 filas). La hoja tiene 7,145 filas de varias procedencias y solo 3,030
traen `place_id`, así que pueden ser anteriores al importador o de captura manual.
Se reporta, no se le cuelga a este plan.

### 7.3 B2 y B3, replanteados: la cuenta la arregla B1; ellos cuestan dinero

Hallazgo del `debugger` que cambia el reparto de trabajo entre tareas.

`_exportar_a_sheets` **relee la hoja en cada categoría** (`app.py:4425`). Cuando
corre la segunda categoría, los negocios que escribió la primera ya están en la
hoja, así que el dedup los rechaza. Es decir: **el solape entre categorías ya está
excluido de las escrituras**; solo está mal contado.

Consecuencia: arreglar B1 (que `nuevos_en_sheet` salga del valor de retorno de
`_exportar_a_sheets`) **hace que el número que ve el operador sea correcto**, incluida
la parte que aporta B3. B2 y B3 no son síntomas independientes del "20 contra 10";
son los dos mecanismos por los que la diferencia existe.

Pero B2 y B3 **sí tienen un costo propio que sobrevive al arreglo de B1**: por cada
negocio que nunca va a ser fila nueva se paga igual un `place()` de Places
(`app.py:4366`) — B2 por los que ya estaban desde antes, B3 por el mismo negocio
consultado dos veces en la misma corrida. Ese gasto no lo arregla contar mejor.

**Reparto que se deriva de esto:** T3.2 (contadores) cierra el síntoma del owner.
T3.3 (dedup entre categorías) deja de contar dos veces **y** deja de pagar dos veces;
su valor mayor es de costo, y por eso el **Plan 2 · T2.3** reutiliza su estructura.

### 7.4 Recorrido de rutas de clic (`click-path-audit`)

Se trazó cada toque de `/importador` por su secuencia completa de cambios de estado.

| # | Toque | Patrón | Veredicto |
|---|---|---|---|
| CP-001 | Botón Buscar | Transición faltante | **B8 CONFIRMADO** |
| CP-002 | Enter en el campo de ciudad | Deshacer secuencial | **B10 NUEVO** |
| CP-003 | Chips de ciudad | Ruta muerta / inyección | **B9 CONFIRMADO y agravado** |
| CP-004 | Filtro de ciudades | Interferencia | **B11 NUEVO** |
| CP-005 | Bucle de sondeo | Estado rancio | **B12 NUEVO** |
| CP-006 | Bucle de sondeo | Sin corte en `idle` | **B8 (segunda mitad) CONFIRMADO** |

### 7.5 Los defectos nuevos, con su traza

**B10 · El guard de "ya hay una búsqueda en curso" es por proceso, y la UI deja
dispararlo.** *(ALTO — cuesta dinero)*

`app.py:4681`: `<input id="input-ciudad" ... onkeydown="if(event.key==='Enter') iniciar()">`.
Ese campo **nunca se deshabilita**: `grep input-ciudad` da tres usos (4681, 4850,
4858) y ninguno pone `disabled`. Traza con dos workers:

1. El operador lanza una búsqueda. Worker A queda en `status: 'running'`.
2. A media corrida pulsa Enter en el campo de ciudad. `iniciar()` corre otra vez.
3. El `POST` cae en **worker B**, cuyo `_import_job` está en `'idle'`. El guard de
   `app.py:4564` es por proceso: **no ve nada**. Devuelve `ok: true` y arranca una
   **segunda importación**.
4. `app.py:4878` hace `polling = setInterval(...)` **sin `clearInterval` previo**
   (`clearInterval` solo aparece en 4910 y 4924). Quedan **dos intervalos vivos**.

Resultado: dos corridas de Places concurrentes sobre la misma ciudad — se paga dos
veces — escribiendo ambas a la misma hoja, y el cliente sondeando al doble de ritmo.
`_import_lock` (`app.py:4323`) no protege: un `threading.Lock` es por proceso.

Si el POST cae en el worker A, devuelve `ok: false` y el `return` de `app.py:4874`
**rehabilita el botón** mientras el trabajo sigue: la UI dice "listo" con una corrida
encima.

**B11 · Filtrar ciudades renumera el ranking.** *(MEDIO — se traspasa al Plan 1)*

`renderChips` (`app.py:4828-4843`) calcula `rank = i + 1` sobre el índice de **la
lista que recibe**. `filtrarCiudades` le pasa la lista ya filtrada, así que la ciudad
que era la 47 del país aparece con `🥇 1.` en cuanto se escribe algo en el filtro.
La medalla miente. Además `renderChips` reescribe todo el `innerHTML`, con lo que se
pierde la clase `.active` del chip elegido.

**B12 · Las insignias y los stats no se reinician entre corridas.** *(MEDIO)*

`app.py:4899-4901` no tiene rama `else` que devuelva la insignia a su estado neutro:

```js
if (i < d.progreso) el.className = 'cat-badge done';
else if (d.categoria === c) el.className = 'cat-badge active';
```

Al terminar, `app.py:4913` pone **todas** en `done`, y `iniciar()` no las limpia: en
la segunda búsqueda de la misma sesión las dos categorías salen ya completadas desde
el segundo cero. Tampoco se reinician `s-encontrados`, `s-descartados`, `prog-fill`
ni el log.

**B13 · Estado muerto.** *(BAJO)*

- `app.py:4719`: `let ciudadSeleccionada = '';` — declarada y **nunca** leída ni
  escrita (`grep` da una sola aparición).
- `_import_job['resultados']` se escribe en `app.py:4527` con `todos[:]` y **ningún
  endpoint lo expone**: `/api/importador/estado` (`app.py:4582-4592`) no lo devuelve.
  Es una copia completa que solo crece.

### 7.6 B9 sube de severidad: es un ciclo de XSS almacenado autoservicio

El plan lo describe como "un apóstrofo rompe el handler". Es bastante peor, y el
camino completo está dentro de la propia aplicación:

1. `POST /api/importador/iniciar` toma `ciudad` con **solo `.strip()`**
   (`app.py:4555`): sin validación, sin lista blanca contra `CIUDADES_MX`.
2. `_exportar_a_sheets` la escribe cruda en la columna CIUDAD (`app.py:4448`).
3. `/api/prospectos/ciudades` la relee de la hoja (`app.py:807`).
4. `renderChips` la interpola **en dos sitios** de la misma línea 4840 — el atributo
   `onclick` **y** el texto del chip:

```js
`<span class="chip ..." onclick="seleccionarCiudad('${c.ciudad}',this)">${medal}${c.ciudad} ${badge}</span>`
```

Cualquiera con acceso al panel puede teclear una carga en el campo de ciudad, correr
una importación, y esa carga se ejecuta en el navegador de **todo** el que abra
`/importador` después. Una ciudad llamada `O'Brien` además deja el chip **muerto**:
al hacer clic no pasa nada.

El arreglo de T3.7 tiene que cubrir los **dos** puntos de interpolación, y conviene
revisar si el selector de ciudad del dashboard (`app.py:2140`) consume el mismo
endpoint con el mismo patrón.

### 7.7 Dos hipótesis DESCARTADAS

**`_import_job` se inicializa dos veces → NO es un defecto.** El reset de
`app.py:4566` ocurre dentro de `with _import_lock:` (4563) y **estrictamente antes**
de `threading.Thread(...).start()` (4574). El hilo resuelve el global en tiempo de
ejecución vía `global _import_job`, así que siempre lee el diccionario recién
asignado. No hay carrera. Se descarta.

**`if lugares: break` corta las variaciones → NO, corta los reintentos.** Por
indentación:

```
4338|    for query in variaciones:          <- indent 4
4339|        for intento in range(3):       <- indent 8
4392|                if lugares: break      <- indent 16, dentro del try del intento
4398|        if query != variaciones[-1]: time.sleep(1)
```

El `break` sale del bucle de **reintentos**, no del de variaciones. **Las tres
variaciones se ejecutan siempre.** Esto corrige una observación previa de la memoria
del proyecto que afirmaba lo contrario, y tiene dos consecuencias:

- El gasto de Places es mayor de lo que se creía: **3 consultas de texto por
  categoría, 6 por corrida**, cada una con hasta 3 páginas. Insumo para el Plan 2.
- El denominador de progreso de T3.6 (2 categorías × 3 variaciones × hasta 3 páginas
  ≈ 18 pasos) **es correcto tal como lo escribió el plan**.

*De camino:* cuando una consulta devuelve legítimamente cero resultados (sin
excepción, lista vacía), `if lugares` es falso y **se repite la misma consulta vacía
hasta 3 veces**, sin backoff — el `2 ** intento` solo está en la rama `except`. Es
gasto pequeño pero real. Se anota para el **Plan 2**.

### 7.8 `_cache` arrastra el mismo defecto en 16 sitios

El barrido de `Explore` confirma que `_cache` (`app.py:112`) tiene la misma
enfermedad que `_import_job`, con más superficie:

- `POST /api/refresh` hace `_cache.clear()` (`app.py:355`) **solo en el worker que
  atendió esa petición**. El otro sirve datos viejos hasta 300 s (`CACHE_TTL`).
- Hay **16** `_cache.pop(...)` tras escrituras a Sheets (`app.py:409, 474, 879, 912,
  3011, 3071, 3072, 3140, 3167, 3263, 3298, 3379, 3493, 3498, 3535, 4470`). Todos
  invalidan medio sistema: el operador guarda un cambio, recarga, y lo ve volver al
  valor anterior cuando la petición cae en el otro worker.
- `_cache` **no está protegido por ningún lock**, y `app.py:4470` lo muta desde el
  hilo daemon del importador a la vez que los hilos de petición.

### 7.9 El repo ya tiene el patrón que necesita T3.5

No hay que inventar el estado compartido: este repositorio ya lo resolvió dos veces,
y esas soluciones tienen tests en la suite.

- **Heartbeat del worker** — `app.py:3553-3586`. `WORKER_HEARTBEAT_FILE` con
  escritura atómica vía `os.replace` desde un temporal con el PID en el nombre, y
  lectura tolerante a corrupción. El comentario de `app.py:3548-3552` da la razón de
  diseño **con estas mismas palabras**: un valor en memoria sería distinto en cada
  worker de gunicorn y haría mentir al monitor. Aplica literal a `_import_job`.
- **Lock entre procesos** — `worker_catalogo_run.py:43-44`, con `LOCK_TTL` y
  detección de lock huérfano en 148-162 (comprueba antigüedad **y** que el PID siga
  vivo). Es el reemplazo directo del papel de guard de `_import_lock`.

Esto respalda la **opción B** de T3.5 con evidencia del propio repo.

### 7.10 Severidad añadida a B5: el hilo es `daemon=True` y no hay persistencia

`app.py:4574` lanza el hilo con `daemon=True` y el estado vive solo en RAM. Un
redespliegue de `main` (Railway y Vultr auto-despliegan) o un reciclado de worker
**descarta la corrida en silencio**: sin checkpoint, sin aviso, y al reiniciar
`_import_job` vuelve a `idle` sin rastro. No es un defecto independiente — es el
mismo B5 manifestándose como pérdida permanente en vez de ceguera transitoria — pero
sube su severidad. Es la mejora M3 del índice.

### 7.11 Tabla final de veredictos

| # | Defecto | Veredicto | Cómo se probó |
|---|---|---|---|
| B1 | Contador cuenta aprobados, no filas | **CONFIRMADO** | Repro: 20 vs 10 |
| B2 | Duplicados contra la hoja | **CONFIRMADO** (mecanismo de B1 + costo propio) | Repro: 4 de los 10 |
| B3 | Duplicados entre categorías | **CONFIRMADO** (íd.) | Repro (6 de 10) + 12 `place_id` reales bajo ambas |
| B4 | Fallo silencioso de escritura | **CONFIRMADO** | Repro: 0 filas, `done`, error vacío |
| B5 | Estado en memoria de proceso | **CONFIRMADO** | PID 20460 vs 16972; 10/20 sondeos `idle` |
| B6 | Barra con tres valores | **CONFIRMADO** | `progreso` fijo en 0 toda la primera categoría |
| B7 | Recargar pierde el trabajo | **CONFIRMADO** | Cero llamadas a `/estado` en la carga; `polling` solo se asigna en `iniciar()` |
| B8 | Botón trabado / sondeo eterno | **CONFIRMADO** | CP-001 y CP-006 |
| B9 | Ciudad sin escapar | **CONFIRMADO, severidad ALTA** | Ciclo completo autoservicio; dos puntos de inyección |
| **B10** | Guard por proceso + Enter siempre vivo | **NUEVO — ALTO** | CP-002. Doble corrida, doble cobro, doble intervalo |
| **B11** | Filtrar renumera el ranking | **NUEVO — MEDIO** | CP-004 |
| **B12** | Insignias y stats rancios | **NUEVO — MEDIO** | CP-005 |
| **B13** | Estado muerto | **NUEVO — BAJO** | `ciudadSeleccionada`; `resultados` nunca expuesto |
| — | `_import_job` se inicializa dos veces | **DESCARTADO** | Reset bajo lock, antes del `start()` |
| — | `if lugares: break` corta variaciones | **DESCARTADO** | Corta reintentos; las 3 variaciones siempre corren |

Ninguno de los nueve quedó descartado. Aparecieron **cuatro nuevos** y se
**descartaron dos** hipótesis.

**Reparto del trabajo nuevo:** B10 → T3.5 (mitad de servidor) y T3.7 (mitad de
cliente). B12 y B13 → T3.7. B11 → se traspasa al **Plan 1 · T1.7**. La zona horaria
(**M2** del índice) y el gasto de las consultas vacías → **Plan 2**.

---

## 8. Reproducir esto otra vez

```bash
python tools/reproducir_bugs_importador.py conteo    # B1, B2, B3, B4
python tools/reproducir_bugs_importador.py workers   # B5, B6
```

Ninguno de los dos toca la red, la hoja de producción ni la API de Places.
