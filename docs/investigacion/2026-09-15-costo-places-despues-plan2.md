# T2.6 — A/B: los recortes ahorran sin tirar prospectos

**Plan:** 2 · **Tarea:** T2.6 · **Fecha:** 2026-09-17
**Rama:** `perf/gasto-places-minimo` · **Baseline:** 1,221 passed, 2 skipped
**Herramienta:** `tools/verificar_ab_recortes.py`

---

## 1. Una aclaración de alcance, antes de los números

El plan escribió esta tarea suponiendo que T2.4 implementaría una optimización. **El ADR de
T2.3 decidió no migrar**, y T2.4 entregó la Fase 0 —una herramienta que mide y no escribe—, así
que **el camino de Places no cambió en este plan**. No hay «configuración nueva» contra la
«vieja».

Lo que sí hay, y no estaba verificado así, son **los dos recortes que agosto introdujo** — y
T2.0 destapó que uno de ellos **no ahorra nada**. El A/B se aplica a ellos, con el método de
agosto **sin inventar otro**.

---

## 2. El resultado

| Configuración | Text Search | Details | Aprobados | **Perdidos** |
|---|---:|---:|---:|---:|
| Sin recortes *(referencia)* | 18 | 80 | 80 | — |
| Sólo el recorte por página | **13** | 80 | **80** | **0** |
| **Los dos recortes** *(la config real)* | **13** | 80 | **80** | **0** |
| **CONTRAPRUEBA**: 1 página por consulta | 6 | 40 | 40 | **40** |

> **Los recortes ahorran 5 Text Search por corrida y no cuestan un solo prospecto.**
> **CE2 y CE3 verdes.**

### 2.1 Y el cero significa algo, porque el chequeo sabe dar distinto de cero

Es la mitad que hace válida la otra. Con un recorte absurdo —una sola página por consulta— el
mismo diff marca **40 prospectos perdidos**, con sus claves.

Un diff vacío sólo vale si el mismo diff puede no estarlo. Éste puede.

### 2.2 El segundo recorte sigue aportando cero, confirmado por otra vía

Fila 2 contra fila 3: **añadir `MAX_VARIACIONES_SIN_APORTE` no cambia ni una llamada ni un
aprobado**. Es el mismo hallazgo de T2.0, ahora por un camino distinto — allí se midió
desactivándolo, aquí activándolo sobre una referencia sin recortes.

**Todo el ahorro de Text Search lo hace el corte por página.** El de variación es, en este
escenario, código que no se ejecuta. No se retira —podría ejercitarse en una ciudad real, donde
las tres consultas traigan cosas distintas— pero **cualquier cifra de ahorro que se le atribuya
hoy está sin respaldo**.

---

## 3. La caché sigue sirviendo

| | Details |
|---|---:|
| 1.ª corrida de la ciudad | **80** |
| 2.ª corrida de la misma ciudad | **0** |

---

## 4. La primera versión de este informe decía que la caché no ahorraba nada

Y era **mi arnés**, no el producto.

`corrida()` aplicaba la configuración y **después** pisaba `PLACES_CACHE_FILE` con un temporal
nuevo, siempre. Así que las dos corridas encadenadas estrenaban caché y la segunda volvía a
pagar los 80 Details. El informe decía, con todas las letras, *«⚠ NO AHORRÓ NADA»* — sobre una
caché que funciona perfectamente y que T2.0 ya había medido en 0.

Se arregló respetando la ruta cuando la configuración la trae. **Es la cuarta vez en esta tanda
que el instrumento estaba mal antes que el código**, y la que más cerca estuvo de publicarse como
hallazgo: el número era plausible, el aviso salía en rojo, y contradecía una medición previa —
que es exactamente la señal que hay que perseguir en lugar de apuntar.

---

## 5. Estado de los criterios

| | Criterio | Estado |
|---|---|---|
| **CE2** | Menos llamadas | ✅ **18 → 13** Text Search (−28 %) |
| **CE3** | Mismos prospectos | ✅ **diff vacío**, con la detección demostrada (40 perdidos en la contraprueba) |
| Caché | Sigue dando aciertos | ✅ **80 → 0** en la segunda corrida |

**Lo que este A/B NO cubre**, y hay que decirlo: **se mide sobre dobles**. El doble devuelve el
mismo conjunto de negocios para las tres variaciones, que es justo el escenario donde el corte
por variación no se ejercita. En una ciudad real podría comportarse distinto — y sólo se sabrá
con la corrida real que sigue siendo gate del owner.
