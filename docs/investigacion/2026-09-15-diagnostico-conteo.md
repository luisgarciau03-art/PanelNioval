# T3.2 — Diagnóstico: por qué el conteo seguía mintiendo

**Plan:** 3 · **Tarea:** T3.2 · **Fecha:** 2026-09-17
**Rama:** `fix/conteo-importador-reincidencia` · **Baseline:** 1,193 passed, 2 skipped
**Cierra:** **CE1** — *«la causa está identificada, no supuesta»*.

---

## 1. La causa, en una frase

> **El arreglo se mergeó a `main` el 27 de agosto y nadie lo desplegó: el VPS siguió sirviendo
> `51520f3` —cuyo `app.py` es byte a byte el mismo sobre el que agosto reprodujo el «20 vs 10»—
> durante tres semanas, hasta el 16 de septiembre, y sólo llegó a producción como efecto
> colateral del despliegue del Plan 1.**

**H1 (despliegue rancio) era cierta.** No es una hipótesis que sobreviva por descarte: tiene
prueba directa, y abajo está.

---

## 2. La prueba, en cuatro hechos comprobables

### 2.1 El commit desplegado no contenía el arreglo

```
git merge-base --is-ancestor ae0e1c9 51520f3   ->  falso
git merge-base --is-ancestor ae0e1c9 8bac782   ->  cierto
```

| Commit | Fecha | ¿Lleva el fix? |
|---|---|---|
| `034dd42` | 2026-08-25 | ❌ — es la base sobre la que agosto reprodujo el bug |
| **`51520f3`** | **2026-08-24** | ❌ — **y es lo que el VPS sirvió hasta el 16-sep** |
| `ae0e1c9` | **2026-08-27** | ✅ — el arreglo |
| `8bac782` | 2026-09-15 | ✅ — desplegado el **16-sep** por T1.6 |

### 2.2 El servidor estuvo tres semanas sin actualizarse, y está documentado

La verificación del Plan 1 · T1.6 lo dejó escrito al abrir el servidor:

> *«Último despliegue real: **2026-08-24** — tres semanas antes, no "el del PR #42"»* ·
> *«Commit desplegado: **`51520f3`**»* · *«Lo que salía a producción: 24 commits, 66 archivos»*

**El arreglo es del 27 de agosto. El último despliegue anterior fue del 24.** El fix nació
después del último despliegue y se quedó esperando uno que no llegaba, porque **no hay
auto-deploy**.

### 2.3 El código desplegado no tenía ni el contador

`app.py` en `51520f3`, que es lo que el operador tuvo delante durante tres semanas:

| | |
|---|---|
| `nuevos_en_sheet` | **0 apariciones** — el contador correcto **no existía** |
| `'duplicados'` | **0 apariciones** |

Y la línea que el operador leía al terminar, literal (`51520f3:app.py:4918`):

```js
`${d.encontrados} contactos encontrados · ${d.descartados} descartados · Guardados en Google Sheets`
```

**`encontrados` rotulado como «Guardados en Google Sheets».** Eso *es* el síntoma: el número de
candidatos aprobados, presentado como si fueran filas guardadas.

### 2.4 Y ese código es, byte a byte, sobre el que agosto reprodujo el bug

```
git diff --stat 034dd42 51520f3 -- app.py   ->  sin diferencias (0 lineas +/-)
```

`034dd42` es la base donde el documento de agosto reprodujo **«UI dice 20 · filas reales 10»**.
`51520f3` es lo que el VPS sirvió. **Su `app.py` es idéntico.**

O sea que la reproducción de agosto no es análoga a lo que pasaba en producción: **es
exactamente lo que pasaba en producción**, tres semanas después de estar arreglado en `main`.

---

## 3. Las otras dos hipótesis, descartadas por escrito

### H2 — Regresión posterior a `ae0e1c9` · **DESCARTADA**

La bisección dirigida que pedía el plan, con la herramienta de agosto sin tocar:

| Punto | Resultado |
|---|---|
| **`ae0e1c9`** (justo tras el fix, en worktree aparte) | 14 encontrados · **10 filas** · `done` · *B1/B2/B3 CORREGIDOS* |
| **`main` de hoy** (`13e2cdb`) | 14 encontrados · **10 filas** · `done` · *B1/B2/B3 CORREGIDOS* |

**Pasa en los dos extremos, idéntico.** El patrón de H2 —pasar en el primero y fallar en el
segundo— no se da, así que no hay commit culpable que bisecar entre los 24 que tocan `app.py`.

Y B4 sigue cerrado en los dos: con la escritura fallando, la corrida termina en `error` con la
causa a la vista.

### H3 — Caso residual no cubierto · **NO HACE FALTA, y no se le cuelga el síntoma**

H1 explica el síntoma **entero y con su cadena de texto exacta**. Colgarle además un caso
residual sería inventar un defecto para no dejar la hipótesis vacía.

**Lo que sí se comprobó de los dos candidatos que T3.1 dejó anotados:**

| Candidato | Estado |
|---|---|
| **`saltados` sumándose a `nuevos_en_sheet`** | ❌ **No ocurre.** `app.py:3417-3419` y `3509-3512`: va a `encontrados` y `duplicados`; el contador sale de `nuevos` |
| **`presupuesto_agotado`** (`app.py:3509`) | ✅ Reparte igual que el camino normal. No introduce el síntoma |
| **Escritura parcial silenciosa** (`app.py:3238`) | 🟡 **Sigue siendo un hueco real, pero NO es esta causa** — ver §5 |

---

## 4. Lo que esto corrige de mi propia conclusión de T3.1

T3.1 cerró con *«H1 DESCARTADA con evidencia»*. **Esa medición era correcta y sigue siéndolo: hoy
producción no está rancia.** Lo que le faltaba era la fecha.

La huella se midió el **17 de septiembre**. El despliegue que metió el arreglo en producción fue
el **16**, y lo hizo **esta misma tanda**, en T1.6, por otro motivo: publicar las 1,004 ciudades
del Plan 1. Un día antes, el mismo instrumento habría devuelto **H1 CONFIRMADA**.

**El instrumento acertó; lo que engañaba era medir el presente para explicar un síntoma del
pasado.** La pregunta correcta no era *«¿está rancio ahora?»* sino *«¿lo estaba cuando se
reportó?»* — y el síntoma se reportó al diseñar esta tanda, el 15 de septiembre, con el VPS aún
en `51520f3`.

---

## 5. El hueco que sobrevive al diagnóstico, y que no es la causa

El hallazgo de T3.1 sigue vivo y conviene **no** enterrarlo ahora que hay una causa mejor:

`app.py:3238` devuelve `len(nuevos)` —filas **enviadas** a `append_rows`— y no lo que Google
confirmó; `updates.updatedRows` se descarta sin mirarlo. Y **ningún test puede verlo**, porque
todos los dobles hacen `self.escrituras += len(filas)`.

**No es la causa de este síntoma** —H1 lo explica entero— pero **es un fallo silencioso latente**,
y el criterio del proyecto sobre fallos abiertos no depende de que hoy estén disparando. Queda
como candidato de T3.3, no como diagnóstico cerrado.

---

## 6. Lo que este diagnóstico implica para el resto del Plan 3

El plan asumía un defecto de código que arreglar. **No lo hay: el código lleva arreglado desde
agosto.** Lo que falló fue el camino entre `main` y el operador. Consecuencias:

1. **T3.3 (test RED) cambia de objeto.** El test que falta no es de conteo —hay 80 vigilándolo—
   sino de **detección de despliegue rancio**. `tools/huella_despliegue.py` ya lo hace y ya está
   verificado en las dos direcciones; lo que le falta es ser una **guarda**, no un script que
   alguien recuerde correr.
2. **El plan lo previó.** Su T3.1 dice: *«si el síntoma no reproduce, decirlo: es un resultado, y
   el plan pasa a T3.5 (pantallas de carga) sin inventar un bug»*. Aplica, con el matiz de que
   aquí sí hubo causa: la había, y ya está cerrada.
3. **CE3 y CE5 siguen necesitando la corrida real** (T3.7). Que la causa fuera de despliegue no
   cierra el gate de agosto que nunca se ejecutó — sólo explica el síntoma reportado.

---

## 7. Estado

| | Hipótesis | Veredicto | Evidencia |
|---|---|---|---|
| **H1** | Despliegue rancio | ✅ **CONFIRMADA** | `51520f3` no contiene `ae0e1c9`; su `app.py` es byte a byte el de la reproducción de agosto; la cadena «Guardados en Google Sheets» sobre `encontrados` en `4918` |
| **H2** | Regresión | ❌ Descartada | La repro pasa idéntica en `ae0e1c9` y en `main` |
| **H3** | Caso residual | ❌ No necesaria | Los tres candidatos comprobados; ninguno produce el síntoma |

**CE1 cerrado.** Una causa, con prueba directa, y las otras dos descartadas por escrito.

**La frase que resume el fallo del proyecto, no del código:** *mergear no es desplegar, y durante
tres semanas nadie tuvo forma de notar la diferencia.*
