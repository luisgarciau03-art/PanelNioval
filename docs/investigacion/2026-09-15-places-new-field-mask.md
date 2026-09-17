# T2.2 — ¿Viene el teléfono en el `searchText` de Places API (New)?

**Plan:** 2 · **Tarea:** T2.2 · **Fecha:** 2026-09-17
**Rama:** `perf/gasto-places-minimo` · **Baseline:** 1,208 passed, 2 skipped

> **Regla que gobierna este documento:** *ningún dato de tarifa ni de agrupación de campos sale
> de la memoria del modelo.* Todo lo de abajo se consultó hoy y lleva su fuente.

---

## 0. Fuentes consultadas (2026-09-17)

| # | Fuente | Qué aportó |
|---|---|---|
| 1 | `developers.google.com/maps/documentation/places/web-service/text-search` | Qué campos admite el field mask de `places:searchText` y en qué SKU cae cada grupo |
| 2 | `developers.google.com/maps/billing-and-pricing/pricing#places-pricing` — **«Last updated 2026-09-16 UTC»** | Precio por 1,000 llamadas de cada SKU y los topes gratuitos |
| 3 | `developers.google.com/maps/documentation/places/web-service/usage-and-billing` | Crédito mensual |
| 4 | **El cliente instalado**, `googlemaps 4.10.0` — inspeccionado en disco, no de memoria | Qué puede pedir *este* proyecto |

---

## 1. La respuesta a la pregunta de la tarea

> **Sí. `places.nationalPhoneNumber` se puede pedir en el field mask de `searchText`.**
>
> Y lo mejor no es eso: **el teléfono sale gratis**, porque el importador ya necesita
> `places.rating` y `places.userRatingCount`, que están **en el mismo SKU**. Pedir el teléfono no
> sube ni un escalón de tarifa.

Según la fuente 1, el SKU **Text Search Enterprise** incluye:

```
places.nationalPhoneNumber     places.internationalPhoneNumber
places.rating                  places.userRatingCount
places.websiteUri              places.priceLevel        (y horarios)
```

Los tres filtros de calidad del importador —**≥ 5 reseñas, ≥ 3.5 ⭐, con teléfono**— caben
enteros en **una sola llamada de búsqueda**. Hoy los dos primeros salen del Text Search y el
tercero cuesta un Place Details por candidato.

---

## 2. Los números, con su tarifa citada

Fuente 2, precios por **1,000 llamadas**, banda 0–100,000 (la única que aplica a este proyecto):

| SKU | Precio | Tope gratis mensual |
|---|---:|---:|
| Text Search Pro (`4FDA-34B1-A910`) | **$32.00** | 5,000 |
| **Text Search Enterprise** (`E967-44BC-B44D`) | **$35.00** | **1,000** |
| Place Details Pro (`4ED6-464A-2AFC`) | $17.00 | 5,000 |
| **Place Details Enterprise** (`2D9A-3DE0-3766`) | **$20.00** | **1,000** |
| Text Search / Place Details Essentials (IDs Only) | sin tarifa listada | **ilimitado** |

### 2.1 Una corrida de ciudad nueva, medida en T2.0/T2.1: **13 Text Search + 80 Place Details**

| Opción | Llamadas | Coste por ciudad |
|---|---|---:|
| **B — migrar «tal cual»**: búsqueda Pro + un Details por candidato | 13 TS Pro + 80 PD Enterprise | **$2.016** |
| **C — migrar con el teléfono en la búsqueda** | **13 TS Enterprise + 0 Details** | **$0.455** |

> **−77 % del gasto de una ciudad nueva**, y **−$1.56 por ciudad**.
> Sobre las **1,004 ciudades** del catálogo: **≈ $1,567 de una sola vez** en el barrido nacional.

El salto de Pro a Enterprise en la búsqueda cuesta **$3 por 1,000** — o sea **$0.039 por ciudad**.
Los 80 Details que desaparecen valen **$1.60**. **La aritmética no está ajustada: es 40 a 1.**

### 2.2 El tope gratuito cambia de sitio, y eso hay que decirlo

Text Search Enterprise trae **1,000 llamadas gratis al mes**, no 5,000 como el Pro. A 13
búsquedas por ciudad, son **~77 ciudades al mes gratis**. Hoy, con Pro (5,000), serían ~384 —
pero las 80 Details por ciudad se comen el tope de Details (1,000 → **12 ciudades**) mucho antes.

**Incluso mirando sólo los topes gratuitos, la opción C cubre 6 veces más ciudades que la actual.**

⚠️ **El crédito de $200 al mes ya no aplica.** La fuente 3 dice: *«You receive a $200 monthly
credit that automatically applies to eligible SKUs **until February 28, 2025**»*. Esa fecha pasó.
Si alguien en el proyecto sigue contando con ese colchón, **no está**.

---

## 3. El cliente instalado NO puede hacerlo, y eso es el coste real

Inspeccionado en disco, no de memoria:

```
googlemaps 4.10.0
metodos: find_place · place · places · places_autocomplete · places_nearby · places_photo
busqueda de 'places.googleapis.com', 'v1/places', 'searchText', 'X-Goog-FieldMask'
  -> NINGUNA coincidencia en todo el paquete
```

**El cliente sólo habla la API legacy.** Es exactamente lo que el ADR de agosto estableció, y
sigue siendo cierto: migrar significa **HTTP directo** con `requests`, cabecera
`X-Goog-FieldMask`, y un formato de respuesta distinto (`places[]` con `displayName.text`,
`userRatingCount`, `nationalPhoneNumber`) frente al legacy (`results[]` con `name`,
`user_ratings_total`, y el teléfono en otra llamada).

### 3.1 Superficie de código que hay que tocar

| Qué | Dónde | Tamaño |
|---|---|---|
| La llamada de búsqueda y su paginación | `_buscar_negocios` en `app.py` | el bucle de variaciones y páginas |
| El mapeo de campos | mismo sitio | `name`→`displayName.text`, `user_ratings_total`→`userRatingCount`, `place_id`→`id` |
| La llamada de Details | `_buscar_negocios` | **desaparece** en la opción C |
| La caché de Details | `_leer/_guardar_cache_places` | queda **sin objeto** si no hay Details |
| El medidor de gasto | `_cobrar(medidor, sku)` | los SKU cambian de nombre y de tarifa |
| Los dobles de prueba | `reproducir_bugs_importador.py`, `medir_llamadas_places.py`, `medir_fuga_details.py`, y las suites que los usan | **formato de respuesta distinto** |

**El coste no es la llamada: son los dobles.** Todo el andamiaje de medición de este plan —y los
80 tests del importador— habla el formato legacy. Cambiarlo es donde está el riesgo.

---

## 4. La alternativa más barata que pedía el paso 4

**Ya está implementada, y por eso no es la respuesta.** La caché de Place Details guarda también
al negocio **rechazado**, así que un candidato sin teléfono se paga **una vez por ciudad**, no en
cada corrida. T2.1 lo midió: **ciudad ya trabajada → 0 Details pagados**.

El problema es que eso no ayuda al caso que importa. El objetivo del proyecto es un **barrido
nacional**: 1,004 ciudades que se corren **una vez**. La caché amortiza la segunda corrida de una
ciudad, y la segunda corrida es justamente la que no va a pasar.

**Otras dos, evaluadas y descartadas:**

| Alternativa | Por qué no |
|---|---|
| **Prefiltrar con el DENUE**, que el repo ya tiene con teléfono de 31,383 ferreterías | El DENUE **no es Google**: saltarse el Details de quien el INEGI no registró perdería prospectos que Google sí tiene. Cambia el gasto por prospectos perdidos, que es justo lo que el plan prohíbe |
| **Ordenar los candidatos para que los sin-teléfono caigan fuera del tope** | **No se puede saber quién no tiene teléfono antes de pagar el Details.** Es circular |

---

## 5. Las tres opciones, con ahorro y coste

| | Opción | Ahorro por ciudad nueva | Coste de implementación | Riesgo |
|---|---|---:|---|---|
| **A** | **No migrar.** Seguir en legacy | $0 | ninguno | La API está en **Legacy status**: deuda con fecha |
| **B** | Migrar a New **sin** pedir teléfono en la búsqueda | ~$0 | alto | Todo el riesgo, nada del premio |
| **C** | **Migrar a New con `nationalPhoneNumber` en el field mask** | **$1.56 (−77 %)** | **alto** — HTTP directo, mapeo de campos y **reescribir los dobles** | Cambiar la ruta que produce todo el valor del importador |

**La opción B existe sólo para nombrarla y descartarla:** migrar sin aprovechar el field mask
paga el coste entero y no compra nada.

---

## 6. Lo que este documento NO decide, y no debe

**La decisión es T2.3**, con `council`, y este documento le entrega los insumos sin
prejuzgarlos. Pero dos cosas tienen que viajar con ellos:

1. **El ahorro de $1,567 depende de una tasa que no está medida.** Los 80 Details por ciudad son
   reales; lo que no se sabe es cuántos de ellos se tiran. **Si Google tuviera teléfono de casi
   todos, la opción C seguiría ahorrando los $1.56** —porque elimina los Details, se tiren o
   no— pero el argumento de la *fuga* dejaría de aplicar. El ahorro no depende de CE1; el
   **relato** sí.
2. **La tarifa legacy actual no se pudo citar.** La página de precios enumera los SKU de la API
   New; no encontré los de legacy con la misma fuente. Así que **la comparación de arriba es
   New-contra-New**, que es la decisión de migración, pero **no dice cuánto se paga hoy**. Ese
   número está en la consola de facturación del owner, y es el mismo gate que arrastra el plan.
