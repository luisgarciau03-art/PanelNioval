# T2.0 — El gasto de Places, antes de tocar nada

**Plan:** 2 · **Tarea:** T2.0 (Tarea Cero) · **Fecha:** 2026-09-17
**Rama:** `perf/gasto-places-minimo`, desde `main` en **`47df48b`**
**Baseline anotado:** **1,208 passed, 2 skipped**, exit 0
**Respaldo:** `docs/auditoria/respaldos/2026-09-15-plan2/` (7 archivos)

---

## 1. Las dos respuestas

> **1. Los planes 1, 4 y 3 NO tocaron la ruta de Places.** Los cuatro escenarios dan
> **exactamente** los mismos números que la línea de agosto. Era lo que el paso 5 mandaba
> comprobar, y sale limpio.
>
> **2. Pero el medidor destapó algo del código, no de los planes:** de los dos cortes de gasto
> que el Plan 2 de agosto introdujo, **uno no ahorra nada** en el escenario de referencia. Todo
> el ahorro de Text Search lo hace el corte **por página**; el corte **por variación** es inerte.

---

## 2. La medición de hoy

2 categorías × 3 variaciones × hasta 3 páginas. Caché aislada por escenario.

| Escenario | Text Search | Place Details | Filas nuevas |
|---|---:|---:|---:|
| Ciudad nueva (nada en la hoja) | **13** | **80** | 80 |
| Ciudad a medio trabajar (30 ya en la hoja) | **13** | **60** | 60 |
| Ciudad ya trabajada (90 ya en la hoja) | **13** | **0** | 0 |
| Segunda corrida, misma ciudad (caché caliente) | **13** | **0** | 80 |

### 2.1 Contra la línea de agosto: idénticos

| Escenario | Agosto (Text / Details) | Hoy | |
|---|---|---|---|
| Ciudad nueva | 13 / 80 | **13 / 80** | = |
| Ciudad a medio trabajar | 13 / 60 | **13 / 60** | = |
| Ciudad ya trabajada | 13 / 0 | **13 / 0** | = |
| Segunda corrida (caché) | 13 / 0 | **13 / 0** | = |

**Ningún plan de esta tanda movió el gasto.** Es un resultado negativo, y era exactamente lo que
había que descartar antes de empezar a optimizar: si los números hubieran cambiado, el Plan 2
estaría midiendo el efecto de otro plan.

---

## 3. La contraprueba del medidor, y lo que destapó

Un medidor que imprime siempre el mismo número no mide: **recuerda**. Antes de fiarme de los
13, comprobé que se mueve cuando el código cambia.

| Palanca tocada | Text Search | |
|---|---:|---|
| *(limpio)* | **13** | — |
| `MAX_PAGINAS_POR_CONSULTA = 1` | **6** | ✅ lo ve |
| `CORTAR_PAGINAS_SIN_APORTE = False` | **18** | ✅ lo ve |
| `MAX_PAGINAS_POR_CONSULTA = 5` | 13 | *(correcto: el corte por aporte ya para antes)* |
| **`MAX_VARIACIONES_SIN_APORTE = 99`** | **13** | 🔴 **no se mueve** |

**El medidor está sano:** dos palancas lo mueven, y la tercera no lo mueve por una razón
correcta —subir el tope de páginas no sirve cuando el corte por aporte ya paró antes—.

### 3.1 El hallazgo: uno de los dos cortes no está ahorrando nada

`MAX_VARIACIONES_SIN_APORTE = 2` debería omitir las variaciones que no traen nada nuevo.
Ponerlo en **99** —o sea, desactivarlo— **no cambia una sola llamada**.

La explicación está en el orden: el corte **por página** (`CORTAR_PAGINAS_SIN_APORTE`) dispara
**antes**, y deja tan pocas páginas por variación que el contador de variaciones sin aporte
**nunca llega a 2**. El corte por variación existe, está probado, y en este escenario **no se
ejecuta**.

La aritmética, con `CORTAR_PAGINAS_SIN_APORTE = False` como referencia sin cortes:

| | Text Search |
|---|---:|
| Sin ningún corte | **18** |
| Sólo con el corte por página | **13** |
| Con los dos cortes | **13** |

**El corte por página ahorra 5. El de variación, 0.**

⚠️ **Y una salvedad honesta:** esto se mide sobre el doble de prueba, donde todas las
variaciones devuelven el mismo conjunto de negocios. No demuestra que el corte por variación sea
inútil **en una ciudad real**, donde las tres consultas pueden traer cosas distintas. Lo que sí
demuestra es que **el escenario de referencia del propio proyecto no lo ejercita**, así que
cualquier cifra de ahorro que se le atribuya hoy está sin respaldo.

**Para el Plan 2 esto es material de T2.1 en adelante**, y la pregunta correcta ya no es *«cuánto
ahorra el corte por variación»* sino *«¿se ejecuta alguna vez?»*.

---

## 4. Un número imposible que el propio proyecto ya había marcado

El escenario de caché caliente imprime:

```
segunda corrida, misma ciudad (cache caliente):
    Details pagados        : 0
    filas nuevas obtenidas : 80
    -> pagados y tirados   : -80  (0 % del gasto de Details)
```

**−80.** Y el documento de agosto dice, sobre un −18 anterior: *«un "pagados y tirados" negativo
es imposible; dice que se obtuvieron más filas que Details pagados. Eso disparó la revisión en
vez del apunte del número»*.

Aquel −18 **sí** era un defecto de medición y se arregló aislando las cachés. Éste **no**: con la
caché caliente se obtienen 80 filas pagando 0 Details, que es justo el ahorro que la caché
existe para producir. Lo que falla es **la fórmula**, que no aplica a este escenario y aun así se
imprime.

**Queda anotado, no arreglado** — es cosmético y T2.0 no toca código. Pero un proyecto que ya
escribió *«un negativo es imposible»* no debería seguir imprimiendo uno: la próxima vez que
aparezca, nadie sabrá si es el bueno o el malo.

---

## 5. Dónde está el gasto, para orientar el plan

| | |
|---|---|
| **Place Details domina** | 80 de 93 llamadas en una ciudad nueva (**86 %**) |
| **Text Search es un suelo fijo** | 13 por corrida, no depende de cuántos negocios haya |
| **La caché y la hoja ya hacen casi todo** | Una ciudad ya trabajada paga **0 Details** |
| **El caso caro es la ciudad NUEVA** | Y es el que no tiene ahorro posible sin perder prospectos |

Los 80 Details de una ciudad nueva **compran 80 filas**: no hay desperdicio que recortar ahí. El
desperdicio que el Plan 2 persigue —Details pagados por negocios que se descartan luego— **no
aparece en este fixture**, porque su doble aprueba a todos. Cuantificarlo es T2.1, y de eso
depende que el resto del plan valga la pena.

---

## 6. Estado

| | |
|---|---|
| Rama desde `main` `47df48b` | ✅ |
| Baseline | ✅ **1,208 passed, 2 skipped** |
| Dos mediciones pedidas (virgen / trabajada) | ✅ y dos más |
| Comparación con la línea de agosto | ✅ **idénticas: ningún plan tocó Places** |
| Medidor verificado en la otra dirección | ✅ 2 palancas lo mueven |
| Respaldo | ✅ `docs/auditoria/respaldos/2026-09-15-plan2/` |

**Criterio de cierre cumplido.**

**Lo que T2.1 hereda:** el corte por variación **no se ejecuta** en el escenario de referencia, y
el desperdicio de Details **no es medible con el doble actual** — su Places aprueba a todos, así
que `sin_telefono` nunca descarta a nadie. **El fixture necesita negocios que fallen los filtros
después de pagar su Details**, o T2.1 medirá cero y concluirá que no hay fuga.
