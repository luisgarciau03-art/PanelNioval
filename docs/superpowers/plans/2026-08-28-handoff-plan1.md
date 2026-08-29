# HANDOFF — ARRANCAR EL PLAN 1 EN FRÍO

**Fecha:** 2026-08-28 · **Proyecto:** PanelNioval — `C:\Users\PC 1\PanelNioval`
**Estado:** Planes 3, 0 y 2 cerrados y mergeados. **23 / 53 tareas (43 %).**
**Siguiente:** Plan 1 — relevancia de ciudades a nivel nacional (10 tareas).

---

## 1. DÓNDE QUEDÓ TODO

| Plan | Estado | PR | SHA |
|---|---|---|---|
| 3 — Bug de conteo y pantallas de carga | ✅ 10/10 | #36 | `ae0e1c9` |
| 0 — Integración continua | ✅ 4/4 | #40 | `c10d063` |
| 2 — Gasto de Google Places | ✅ 9/9 | #38 | `4e06e64` |
| **1 — Relevancia de ciudades** | ⬜ **0/10** | — | rama `feat/relevancia-ciudades-nacional` (crear) |
| 4 — Rediseño del panel | ⬜ 0/12 | — | rama `feat/rediseno-panel` (crear) |
| 5 — Endurecimiento | ⬜ 0/8 | — | rama `fix/endurecimiento-panel` (crear) |

**`main` = `4e06e64`, baseline `python -m pytest tests/` → 388 passed, 1 skipped.**

---

## 2. LO QUE CAMBIÓ Y AFECTA AL PLAN 1

### 2.1 Ahora hay CI, y ya no depende de que alguien se acuerde

`.github/workflows/tests.yml` corre en cada PR contra `main` y en cada push a `main`. Dos
jobs: la suite de pytest (bloquea) y un barrido de secretos sobre el diff (avisa, no
bloquea). **El PR del Plan 1 lo llevará automáticamente; no hay que reimplementar nada.**

- Si el check sale rojo: `docs/RUNBOOK.md` § *Cuando el check de CI sale en rojo*.
- Si el barrido marca una fixture legítima, se exceptúa la línea con `barrido-ok: <motivo>`.
  **El motivo es obligatorio**: sin él la marca no silencia nada.
- ⚠️ **Gate del owner abierto:** sin la protección de rama en `main`, el check informa pero
  **no impide el merge**.

### 2.2 El baseline es POR RAMA, y esto ya causó un problema

Los documentos de la tanda daban **357 passed** como número absoluto. Era el de
`perf/gasto-places-importador`, no el de `main`. Cualquier gate escrito «≥ 357» resultaba
**inalcanzable** desde una rama basada en `main`.

**Comparar siempre contra el baseline de la rama base del PR, nunca contra una cifra
copiada de un documento.** Y el comando va **sin `-q`**: `pytest.ini` ya trae `addopts = -q`
y el segundo lo vuelve `-qq`, que suprime la línea del resumen.

Detalle extra: en local (Windows) salen **388 passed, 1 skipped**; en el runner Linux salen
**389 passed**, porque el test que se salta necesita `fcntl`. El CI cubre un test que la
máquina del owner no puede ejecutar nunca.

### 2.3 Dos entregables del Plan 1 YA ESTÁN HECHOS

Esto es lo más caro que se puede repetir por error. **T1.7 los VERIFICA con un test, no los
reimplementa:**

- **B9 — escapado del nombre de ciudad.** Ya existe: el nombre viaja en `data-ciudad`, se
  escapa con `escaparHtml`, y hay un listener delegado. `seleccionarCiudad` **ya no existe**
  en el archivo.
- **B11 — rank fijo al filtrar.** Ya existe: el rank se fija una vez sobre el catálogo
  completo, así que filtrar ya no renumera y la ciudad 47 no sale con medalla de oro.

⚠️ **Los números de línea de esos anclajes ya no valen.** `app.py` cambió con los planes 0 y
2. **Localizarlos con `grep`, no con el número que traiga el documento.**

### 2.4 El catálogo de ciudades tiene duplicados medidos

**293 entradas · 238 únicas · 50 duplicados exactos.** El `[...new Set()]` colapsa por
cadena exacta, así que las variantes con y sin acento **sobreviven y generan dos consultas
a Places cada una**. Ahora que Places está optimizado, cada duplicado que quede es gasto
que el Plan 2 no puede evitar.

### 2.5 Decisión D3 sigue abierta: el plan asume su opción A

**400-600 ciudades**, los municipios con presencia ferretera relevante cubriendo las 32
entidades. Si el owner responde otra cosa, cambia T1.4 y T1.7.

---

## 3. TRAMPAS QUE YA COSTARON TIEMPO EN ESTA TANDA

1. **Los archivos están en CRLF, también los `.py`.** Un reemplazo por patrón escrito con
   `\n` **no casa y devuelve el texto igual, sin error**. Usar coincidencia por línea con
   `split("\r\n")` y **verificar con `grep` sobre el archivo**, no fiarse de que la
   herramienta dijera "aplicado".
2. **`git add docs/` arrastra archivos de otro proyecto.** Añadir siempre por ruta
   explícita.
3. **La caché de Places contamina cualquier medición.** `PLACES_CACHE_FILE` vive en el temp
   del sistema y **sobrevive entre invocaciones**. Una medición de esta tanda arrastró 108
   entradas y reportó un ahorro que no existía. Apuntarla a un archivo nuevo antes de medir.
4. **Un test que pasa con y sin el arreglo no vale nada.** En esta tanda hubo dos: un diff
   de CE7 que comparaba dos conjuntos vacíos por un nombre de atributo equivocado, y tres
   tests de negativos que no ejercitaban ninguna regla. Comprobar siempre que el chequeo
   **sabe ponerse en rojo**.
5. **Importar `app.py` en frío tarda ~70-100 s** (googleapiclient + Defender). No es un
   cuelgue: usar timeouts largos o fondo.
6. **No editar `app.py` mientras un reviewer lo está leyendo.**

---

## 4. MENSAJE DE ARRANQUE

Para pegar tal cual en un chat nuevo.

```
Continua los planes de trabajo de PanelNioval. Toca el Plan 1.

PROYECTO: C:\Users\PC 1\PanelNioval
RAMA: feat/relevancia-ciudades-nacional (crear desde main actualizado).
NUNCA main: Railway y Vultr auto-despliegan desde ahi.

LEE EN ESTE ORDEN ANTES DE TOCAR CODIGO:
1. C:\Users\PC 1\.claude\BIBLIOTECA-HERRAMIENTAS.md  <- 653 herramientas, 6
   fuentes. Confirma que la leiste citando el total.
2. C:\Users\PC 1\PanelNioval\CLAUDE.md
3. docs/superpowers/plans/2026-08-28-handoff-plan1.md  <- EMPIEZA AQUI
4. docs/superpowers/plans/2026-08-27-indice-tanda.md  <- orden, marcador (S6),
   gates del owner (S7.1), decisiones resueltas (S7.2) y pendientes (S8)
5. docs/superpowers/plans/2026-08-27-plan1-relevancia-ciudades-nacional.md
   Su seccion 0 MANDA sobre los numeros de linea del resto del documento.
6. Memoria: usa claude-mem (mem-search).

ESTADO: 23/53 tareas (43 %). Planes 3, 0 y 2 cerrados y mergeados.
BASELINE: python -m pytest tests/  ->  388 passed, 1 skipped en main.
  SIN -q: pytest.ini ya trae addopts=-q y el segundo lo vuelve -qq, que
  suprime la linea del resumen. Y el baseline ES POR RAMA: compara contra
  la rama base del PR, nunca contra un numero copiado de un documento.

YA HAY CI: cada PR corre la suite y un barrido de secretos. No lo
reimplementes. Si el barrido marca una fixture legitima, exceptua la linea
con un comentario `barrido-ok: <motivo>` (el motivo es obligatorio).

NO REIMPLEMENTES B9 NI B11: el escapado del nombre de ciudad y el rank fijo
al filtrar YA ESTAN HECHOS. T1.7 los VERIFICA con un test. Localizalos con
grep, no con los numeros de linea de los documentos, que ya no valen.

REGLAS: herramientas de la tabla de asignacion de cada tarea (python-reviewer
ADEMAS de code-reviewer, nunca en su lugar). TDD donde el plan lo marque.
Respaldo antes del cambio y confirmado en disco con tamano > 0. Nada se borra:
se aparta al respaldo fechado. Datos de clientes enmascarados. Credenciales
por nombre de variable y archivo:linea, nunca por valor. Verifica que cada
reemplazo por patron quedo EN el archivo: los .py estan en CRLF y un patron
con \n no casa y devuelve el texto igual, sin error.

AL CERRAR: actualiza la tabla PROGRESO del plan y el marcador global del
indice (S6), abre PR con gh pr create --base main y mergealo con --squash
SOLO si los gates estan verdes. Commits convencionales en espanol, ASCII,
terminando con:
Co-authored-by: LUIS V <luisht3g@gmail.com>

GATES DEL OWNER (reportalos, NO los intentes): activar la proteccion de rama
en main, consumo por SKU de Places, corrida real de la ciudad de referencia,
las 5 variables en .env.example, validacion humana del top-20 de ciudades,
rotar TELEGRAM_TOKEN, apagar Railway.
```

---

## 5. LO QUE NO SE HIZO, Y POR QUÉ

- **No se tocó el Plan 4 ni el 5.** Van después del 1 por el orden de la tanda: el rediseño
  necesita saber cuántos chips de ciudad tiene que acomodar.
- **No se activó `--estricto` en el barrido de secretos.** Decisión **E1·A** del owner:
  revisar el **2026-09-18**. Antes de activarlo hay que endurecer `barrido-ok`, que con el
  job bloqueando pasa de silenciar un aviso a saltarse un gate.
- **No se puso gate de cobertura.** Decisión **E2·A**: se reporta (69 %) y no bloquea.
  Reconsiderar después del Plan 4, que va a mover 5,067 líneas de HTML fuera de `app.py` y
  hará saltar el porcentaje por reestructuración, no por tests nuevos.
- **Ninguna rama se borró.** `ci/prueba-de-rojo` es la evidencia de CE2 y
  `fix/conteo-importador-y-estados-carga` guarda los 10 commits del Plan 3, que son la única
  vía de revertir un arreglo sin perder los otros.
