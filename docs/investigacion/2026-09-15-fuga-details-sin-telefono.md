# T2.1 — La fuga: Place Details pagados que nunca llegan a la hoja

**Plan:** 2 · **Tarea:** T2.1 · **Fecha:** 2026-09-17
**Rama:** `perf/gasto-places-minimo` · **Baseline:** 1,208 passed, 2 skipped
**Herramienta:** `tools/medir_fuga_details.py`

> **Esta tarea decide si el resto del plan vale la pena.** Su CE1 pide *«un porcentaje medido
> sobre 3 ciudades, no una estimación»*, y con **< 10 % se saltan T2.2 y T2.3**.

---

## 1. Las tres respuestas

> **1. El mecanismo está probado y es 1:1.** Cada negocio sin teléfono cuesta **exactamente un
> Place Details**, y no hay ninguna amortiguación: los Details pagados **no bajan** cuando sube
> la proporción de descartes. Lo que baja son las filas que compras.
>
> **2. La tasa real de Google NO se puede medir desde aquí**, y decir un número inventado sería
> peor que no darlo. Se entrega como **curva**: en cuanto exista una tasa medida, el ahorro se
> lee de su fila.
>
> **3. Hay un dato real, gratis y de fuente independiente que orienta la decisión: en el DENUE,
> el 58.6 % de las 75,726 ferreterías del país NO tiene teléfono registrado** — y la tasa es
> **plana** entre metrópolis, ciudades medias y municipios chicos. No es la tasa de Google, pero
> hace muy improbable que la de Google esté por debajo del 10 % del umbral.

**Veredicto formal: CE1 no se cierra.** La tarea queda **parcialmente bloqueada**, igual que
T3.7, y por la misma razón: hace falta una corrida real.

---

## 2. Lo primero: el fixture mentía, y se arregló

T2.0 dejó el aviso y era exacto. El doble de `medir_llamadas_places.py` **aprueba a todos**:
devuelve `formatted_phone_number` en el 100 % de los casos. Medir la fuga con él habría dado
**cero**, y ese cero habría cancelado el plan por un defecto del instrumento.

`GmapsConSinTelefono` añade lo que faltaba: una fracción de negocios **sin teléfono**,
determinista por `place_id` —la misma corrida repetida da lo mismo— que **paga su Details igual**,
porque eso es justamente lo que hace Google.

---

## 3. La medición del mecanismo

Ciudad virgen, 2 categorías × 3 variaciones × 3 páginas:

| Sin teléfono (fixture) | Details pagados | Tirados | Tasa de desperdicio | Filas nuevas |
|---:|---:|---:|---:|---:|
| 0 % | 80 | 0 | 0.0 % | **80** |
| 10 % | 80 | 10 | 12.5 % | 70 |
| 20 % | 80 | 20 | 25.0 % | 60 |
| 40 % | 80 | 30 | 37.5 % | 50 |
| 50 % | 80 | 40 | 50.0 % | 40 |
| **58 %** *(proxy DENUE)* | **80** | **48** | **60.0 %** | **32** |
| 70 % | 80 | 60 | 75.0 % | 20 |

**Lo que hay que leer en esta tabla es la columna que NO se mueve.** `Details pagados` es **80
siempre**. La tasa de descartes no ahorra ni una llamada: sólo convierte filas en dinero tirado.

En una corrida de **93 llamadas** (13 Text Search + 80 Details), la fuga pesa:

| Tirados | % del gasto total de la corrida |
|---:|---:|
| 10 | 10.8 % |
| 20 | 21.5 % |
| **48** | **51.6 %** |
| 60 | 64.5 % |

### 3.1 La ciudad ya trabajada no tiene fuga, y eso importa

| | Details pagados | Tirados |
|---|---:|---:|
| Ciudad ya trabajada, sin teléfono 0 % | **0** | 0 |
| Ciudad ya trabajada, sin teléfono 58 % | **0** | 0 |

**Cero en los dos casos.** El prefiltro contra la hoja corta *antes* de pagar, así que la fuga
**sólo existe en ciudades nuevas o a medio trabajar**. Y es coherente con lo que ya decía el
RUNBOOK: *«a quien más ahorra la caché es al negocio rechazado»*.

**Consecuencia para el plan:** el ahorro que persigue T2.2/T2.3 **se cobra una vez por ciudad
nueva**. Con 1,004 ciudades en el catálogo y la mayoría sin trabajar, sigue siendo mucho — pero
no es un ahorro recurrente por corrida, y presentarlo así sería inflarlo.

### 3.2 Una arruga del fixture, dicha para que nadie lea de más

Al 20 % y al 30 % la tabla da **los mismos 20 tirados**. No es un hallazgo: es la granularidad
del doble —los `place_id` no cubren todos los restos módulo 100—. La curva es correcta en su
forma y en sus extremos; **no la uses para interpolar al 1 %**.

---

## 4. El dato real: el DENUE, 75,726 ferreterías

Lo mejor disponible sin gastar un peso, y es una fuente **independiente de Google**: el DENUE del
INEGI publica el teléfono de cada unidad económica. Filtrado a **SCIAN 467111** (ferreterías y
tlapalerías), que es exactamente el universo del importador:

| | |
|---|---|
| Unidades | **75,726** |
| Con teléfono registrado | 31,383 — **41.4 %** |
| **Sin teléfono** | 44,343 — **58.6 %** |

### 4.1 Los tres perfiles de ciudad que pedía el paso 3, con datos reales

| Perfil | Municipios | Unidades | Sin teléfono |
|---|---:|---:|---:|
| Metrópoli (≥ 300 ferreterías) | 53 | 29,853 | **58.8 %** |
| Ciudad media (60–299) | 185 | 23,627 | **59.1 %** |
| Municipio chico (5–59) | 1,202 | 20,403 | **58.0 %** |

**La hipótesis del plan era que la tasa dependería de lo bien catalogados que estén los negocios
locales. No depende: 58.0 – 59.1 %, un punto de rango sobre 1,440 municipios.** Eso es un
resultado en sí mismo, y simplifica el resto del plan: no hace falta segmentar por tamaño de
ciudad.

### 4.2 ⚠️ Por qué esto NO cierra CE1

**El DENUE no es Google.** Son dos catálogos distintos, construidos de forma distinta:

- Google tiene teléfono de negocios que el INEGI no registró —fichas reclamadas por el dueño,
  datos de terceros—, así que la tasa de Google **debería ser mejor** que 58.6 %.
- Y al revés: el INEGI censa establecimientos que no tienen ficha en Google.

Usar el 58.6 % como si fuera la tasa de Google sería exactamente el tipo de número plausible y
equivocado contra el que este proyecto ya se estrelló. **Se reporta como referencia de otra
fuente, y nada más.**

Lo que sí soporta: para que la fuga quedara por debajo del **10 %** que manda saltarse T2.2/T2.3,
Google tendría que tener teléfono de **más del 90 %** de las ferreterías mexicanas — seis veces
mejor que el censo oficial. **Posible, pero improbable.**

---

## 5. Estado de CE1 y qué falta

| | |
|---|---|
| Mecanismo (1 sin teléfono = 1 Details) | ✅ **medido** |
| Fuga en ciudad ya trabajada | ✅ **cero, medido** |
| Tasa por 3 perfiles de ciudad | ✅ **medida en el DENUE** (58.0 / 59.1 / 58.8 %) |
| **Tasa real en Google Places** | 🔴 **falta — corrida real, gate del owner** |
| **CE1** | 🔴 **NO cerrado** |

**La receta, y es barata:** una sola ciudad, una sola corrida. El panel ya publica los cuatro
contadores, y `descartados` incluye los sin-teléfono. Con `descartados / (aprobados +
descartados)` de una corrida real sale la tasa. **No hace falta instrumentar nada nuevo** — sólo
correr el importador una vez y leer la pantalla.

⚠️ Con un matiz que hay que respetar: `descartados` agrupa **tres** motivos —pocas reseñas,
calificación baja y sin teléfono— y sólo el tercero paga Details. Para aislarlo hace falta el
log de la corrida, que sí los desglosa, o una corrida con los otros dos filtros relajados.

---

## 6. Recomendación sobre T2.2 y T2.3

**No se saltan todavía, y tampoco se dan por justificadas.** El plan condiciona ese salto a una
tasa **medida**, y no la hay.

Lo que sí se puede afirmar con lo medido:

1. **Si la tasa real ≥ 10 %**, la fuga es **el gasto más grande y más recortable** del importador
   — al 58 % serían 48 de 93 llamadas por ciudad nueva.
2. **El techo del ahorro es conocido:** los Details tirados. Nunca más que eso.
3. **Sólo se cobra una vez por ciudad**, no en cada corrida.

**T2.2 (evaluar Places API New) puede avanzar igual**, porque su pregunta —*¿el `searchText`
puede devolver el teléfono en el field mask?*— es **independiente de la tasa**: si la respuesta
es no, la migración no sirve por mucha fuga que haya.
