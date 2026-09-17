# T3.5 — Auditoría de los estados: ¿cuál miente?

**Plan:** 3 · **Tarea:** T3.5 · **Fecha:** 2026-09-17
**Rama:** `fix/conteo-importador-reincidencia` · **Baseline:** 1,208 passed, 2 skipped
**Herramienta:** `tools/auditar_estados_importador.py` · **Evidencia:** `docs/investigacion/estados-2026-09-17/`

> Esto **no** audita cómo se ven los estados — eso fue el Plan 4 y está cerrado. Audita si lo
> que la pantalla **afirma** coincide con lo que de verdad pasó.

---

## 1. El resultado

> **Nueve escenarios recorridos. Cero afirmaciones falsas.** Y el auditor demostró que **sabe
> detectar una**: reintroduciendo tres defectos reales de agosto, los tres salieron en rojo.

**T3.6 se salta** — es lo que el plan manda cuando todos coinciden, anotándolo sin borrar la
fila.

---

## 2. Método, y por qué así

**1. Cada estado se provoca de verdad.** Se corre `_worker_importador` con dobles sólo en las
dos fronteras externas —Places y Sheets—. Fabricar el diccionario de estado a mano probaría que
la pantalla sabe pintar *ese* diccionario, no que el backend lo produzca nunca.

**2. El aviso de Telegram se captura interceptando el `post`**, no reimplementando el mensaje.
Reescribirlo aquí probaría mi copia, no la suya.

**3. La pantalla se renderiza en navegador** con ese estado exacto, y se lee lo que el operador
ve: el titular, los cuatro contadores, el título del final, el icono, la clase y el `role`.

Ni red, ni hoja de producción, ni un centavo de Places. Los negocios son inventados.

---

## 3. Los nueve escenarios

| Estado | `nuevos` | `aprobados` | Pantalla | Telegram | |
|---|---:|---:|---:|---|---|
| `idle` reposo | 0 | 0 | fila **oculta** | *(no envía)* | ✅ |
| `running` a media corrida | 6 | 6 | 6 | *(no envía)* | ✅ |
| **`done` ciudad ya trabajada** | **10** | **14** | **10** | 📥 Completado | ✅ |
| `cancelado` parada del operador | 6 | 6 | 6 | ⏹ **DETENIDO** | ✅ |
| `interrumpido` por `SIGTERM` | 6 | 6 | 6 | ⏹ **DETENIDO** | ✅ |
| `error` fallo de Sheets | 0 | 0 | 0 | ❌ **FALLÓ** | ✅ |
| `presupuesto_agotado` tope | 6 | 6 | 6 | ⛔ **TOPE DE GASTO** | ✅ |
| `done_vacia` ciudad sin resultados | 0 | 0 | 0 | 📥 Completado | ✅ |
| `recarga_tras_reinicio` | 6 | 6 | 6 | *(no envía)* | ✅ |

Capturas: una PNG por estado en `docs/investigacion/estados-2026-09-17/`.

### 3.1 Los dos hallazgos de agosto están cerrados

El plan traía dos sospechas heredadas, y las dos resultan arregladas **en el código de hoy**:

- **#17575** — *«Telegram anuncia "Completado" de una corrida detenida»*. Hoy dice **⏹ DETENIDO**,
  y también para `interrumpido`.
- **#17826** — *«Telegram muestra "❌ Importador FALLÓ" para un tope de gasto»*. Hoy dice
  **⛔ TOPE DE GASTO**. Un corte por tope **no es un fallo**, y ya no lo parece.

### 3.2 La recarga tras un reinicio: las dos fuentes no se separan

Es el punto que el plan pedía mirar aparte, porque el hilo es `daemon=True` y el estado vive en
memoria **y** en disco. Provocado de verdad: se persiste una corrida a medias, se vacía la
memoria a `idle`, y se pregunta al endpoint.

**Responde `interrumpido` con los contadores que había alcanzado**, no `idle` en blanco. La
memoria y el disco dicen lo mismo.

---

## 4. La verificación del propio auditor

Un auditor que sólo sabe decir «coincide» no vale su cero. Se reintrodujeron tres defectos
reales, uno por canal:

| Defecto reintroducido | Detectado |
|---|---|
| **B1 de agosto**: el titular vuelve a pintar `encontrados` en `importador.js` | ✅ `MIENTE done` — pantalla 14, backend 10 |
| **#17575**: Telegram vuelve a titular «Completado» en una corrida detenida | ✅ `MIENTE cancelado` **y** `MIENTE interrumpido` |
| **#17826**: el tope de gasto vuelve a anunciarse como fallo | ✅ `MIENTE presupuesto_agotado` |

Los tres archivos quedaron restaurados con **sha256 idéntico**, y la suite en verde después.

### 4.1 Un agujero en mi propia auditoría, encontrado por la mutación

La primera versión pasaba los nueve escenarios… **y no habría detectado B1.**

En todos ellos `nuevos_en_sheet == encontrados`, así que comparar los dos números era una
comprobación vacía: la pantalla podía pintar el contador equivocado y salir verde igual. La
mutación lo destapó — el defecto se reintrodujo y **no lo vio nadie**.

Se corrigió añadiendo **solape a propósito** al escenario `done`: una ciudad ya trabajada, con 4
filas previas en la hoja y 6 negocios repetidos entre las dos categorías. Eso separa los
contadores —**14 aprobados, 10 filas nuevas**— y es el «20 vs 10» del owner en pequeño. Sólo
entonces la mutación salió en rojo.

**Un escenario en el que dos números coinciden por casualidad no prueba que se distingan.**

---

## 4bis. LO QUE EL GATE ENCONTRÓ DESPUÉS, y que invalida parte de lo de arriba

*(Añadido tras la revisión de `python-reviewer`, que devolvió **BLOCK**.)*

La primera versión reportó *«9 escenarios, 0 afirmaciones falsas»*. **Era cierto y era
incompleto: uno de los nueve no comprobaba nada.**

### El CRITICAL

Todo el cuerpo de `_veredicto()` estaba detrás de `if st != "idle"`. Para el estado en reposo no
quedaba ninguna rama aplicable —`icono` viene vacío por construcción, no hay final que vestir, y
no hay aviso de Telegram—, así que **`idle` devolvía «coincide» pasara lo que pasara en la
pantalla**. Incluso con la fila de contadores visible arrastrando las cifras de la corrida
anterior, que es justo la forma en que el reposo puede mentir.

Y lo irónico: `_pantalla_en_reposo` **sí capturaba** si la fila estaba oculta. El dato estaba
ahí; el veredicto no lo miraba.

**Arreglado:** `idle` ahora exige fila oculta **y** los cuatro contadores en cero o vacíos.

### Y tres HIGH que también cambiaban el resultado

| | |
|---|---|
| **Sólo se comparaban 2 de los 4 contadores** | «Ya estaban» y «Descartados» se leían de la pantalla y **no se comparaban con nada**. Ahora los cuatro |
| **`googlemaps.Client` y `time.sleep` no se restauraban** | Son los módulos **reales del proceso**, no copias de `app`. Se restauraba con cuidado el tope de gasto y no estos dos — la asimetría delataba el olvido |
| **`navegador.close()` se saltaba** en el camino `--contra` sin token | El `return` temprano caía entre el `launch()` y el `try/finally` |

Más el parseo de `--contra`, que se tragaba un flag mal escrito en silencio y acababa usando la
URL como nombre de directorio.

### Las tres comprobaciones nuevas, probadas por mutación

| Defecto introducido | |
|---|---|
| La fila de contadores se queda **visible en reposo** | ✅ `MIENTE idle` |
| «Ya estaban» pinta el contador equivocado | ✅ `MIENTE done` |
| El notificador de Telegram **se cae** (regresión simulada) | ✅ **6 estados en rojo** |

El último cerraba un hueco propio: `app.py` **se traga las excepciones del notificador** y sólo
las imprime. Sin esa comprobación, una regresión ahí se leía igual que *«este estado no avisa»*.
Y hubo que acotarla: `idle`, `running` y `recarga_tras_reinicio` **no terminan ninguna corrida**,
así que exigirles aviso habría sido inventar un fallo.

### El resultado no cambia, pero ahora significa algo

**9 escenarios, 0 afirmaciones falsas** — con nueve veredictos que de verdad comprueban algo,
y con el auditor puesto a prueba **seis veces** en total.

### 4bis.1 La trampa de la evidencia compartida, otra vez

Volvió a pasar, y merece quedar escrito dos veces: la corrida de mutación del notificador
sobrescribió `estados.json`, y la siguiente corrida contra producción leyó **esos** estados
—todos sin aviso— y reportó **6 falsos positivos**.

No era producción: era mi propia evidencia contaminada. Se regeneró con una corrida limpia y
entonces dio 0. **El banco de pruebas y la evidencia siguen sin poder compartir carpeta**, y
esta vez el aviso estaba escrito en §6 de este mismo documento.

---

## 5. Dos correcciones al plan

### 5.1 Los estados son SIETE, no seis

El plan enumera *«reposo, corriendo, completado, detenido, error y tope de presupuesto»*. El
código tiene uno más:

```
idle · running · done · cancelado · interrumpido · error · presupuesto_agotado
```

**`interrumpido` no estaba en la lista**, y no es un sinónimo de `cancelado`: uno es el operador
pulsando *Detener*, el otro es un `SIGTERM` —un redespliegue— matando la corrida. `app.py:3466`
los distingue a propósito, y la interfaz y el registro persistido también.

Es justamente el estado que aparece al recargar tras un reinicio, o sea el caso que el paso 4
del plan mandaba mirar con lupa. Auditar seis lo habría dejado fuera.

### 5.2 Y hay un OCTAVO canal: Telegram

Los seis (siete) estados son de la UI. **Telegram es un canal aparte**, con su propio texto y
sus propios modos de mentir — los dos hallazgos de agosto ocurrieron ahí, no en la pantalla. Se
audita aquí porque para el owner *es* el canal principal: recibe el aviso en el teléfono y no
vuelve a abrir el panel.

---

## 6. Una trampa que casi me hace reportar un bug muerto

Las corridas de mutación **escriben en el mismo directorio de evidencia** que la corrida limpia.
Al leer `estados.json` después de mutar, encontré `presupuesto_agotado` anunciado como
**«❌ Importador FALLÓ»** y estuve a punto de reportar #17826 como vivo.

Era la salida de la corrida **mutada**, que había sobrescrito la limpia.

Se borró el directorio y se repitió la auditoría sobre código limpio —`git status` vacío en
`app.py` y en `importador.js` antes de empezar— y la evidencia de §3 es la de esa corrida.

**La evidencia y el banco de pruebas no pueden compartir carpeta.**

### 6.1 Y una peor: el arnés de mutación dejó `app.py` mutado

La segunda mutación reventó **leyendo su propia salida** —`stdout` en cp1252 contra un emoji— y
la excepción se llevó por delante la línea que restauraba el archivo. `app.py` se quedó
**modificado en el árbol de trabajo**, con el título de Telegram cambiado.

Se detectó con `git diff` y se restauró desde git; la suite volvió a 1,208. El arnés ahora
restaura en `finally` y lee la salida con `encoding="utf-8", errors="replace"`.

**Una mutación que no se deshace pasa a ser un cambio.** Restaurar en el camino feliz no basta:
el arnés tiene que sobrevivir a su propio fallo.

---

## 7. Estado

| | |
|---|---|
| Escenarios recorridos | **9** (7 estados + ciudad vacía + recarga tras reinicio) |
| Afirmaciones falsas | **0** |
| Auditor verificado en la otra dirección | **3 defectos reales reintroducidos, los 3 detectados** |
| Capturas | 9 PNG, sin un solo dato de cliente |
| **T3.6** | **Se salta.** Los estados coinciden; no hay mentira que corregir |

**CE4 cumplido en local.** Su mitad de producción sigue en T3.7, junto con CE3 y CE5.

**Lo que esta tarea NO cierra:** el recorrido se hizo contra el backend real pero **en local**, y
lo que llega al operador es lo que sirve el VPS. La comprobación equivalente contra producción
—y la corrida real que compara el número de la UI contra la hoja— es T3.7, y arrastra el gate de
credenciales que agosto dejó abierto.
