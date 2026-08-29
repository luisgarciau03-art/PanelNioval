# GASTO DE GOOGLE PLACES: LA MEDICIÓN DESPUÉS

**Fecha:** 2026-08-28 · **Proyecto:** PanelNioval · **Plan 2 · T2.7**
**Rama:** `perf/gasto-places-importador` · **Antes:** [`2026-08-28-costo-places-antes.md`](2026-08-28-costo-places-antes.md)
**Baseline de la rama:** `python -m pytest tests/` → **388 passed, 1 skipped**

---

## 1. LO QUE ESTE DOCUMENTO PUEDE Y NO PUEDE AFIRMAR

**Puede** afirmar cuántas llamadas hace una corrida, por SKU, y cómo cambió ese número.
Está medido con dobles instrumentados sobre el código real del importador, es exacto y es
repetible.

**No puede** afirmar el importe en pesos. Eso exige el consumo por SKU de la consola de
facturación de Google Cloud (proyecto `bubbly-subject-412101`), que es **gate del owner** y
sigue abierto. Sin el multiplicador no hay pesos, y sin pesos no hay porcentaje de costo.

Por eso **CE6 se evalúa en reducción de llamadas**, no en dinero, conforme a la decisión
**D2 (opción A)** del índice de la tanda. El importe se calcula después aplicando la tarifa
sobre estos conteos, sin tocar una línea de código.

Tampoco hay **corrida real** contra Google: factura la API y escribe en `LISTA DE CONTACTOS`
de producción. Es el gate 2 del owner. Todo lo de aquí sale de respuestas grabadas.

---

## 2. EL INSTRUMENTO ESTABA MINTIENDO, Y SE ARREGLÓ ANTES DE MEDIR

La primera ejecución de `tools/medir_llamadas_places.py` en esta sesión devolvió esto:

```
  ciudad nueva (nada en la hoja)                   13       62       80
    -> pagados y tirados   : -18  (-30 % del gasto de Details)
```

**Un "pagados y tirados" negativo es imposible**: dice que se obtuvieron más filas que
Details pagados. Eso disparó la revisión en vez del apunte del número.

**Causa.** `PLACES_CACHE_FILE` vive por defecto en el **temp del sistema**, así que
sobrevive entre invocaciones del script. La medición arrastraba **108 entradas cacheadas**
de corridas anteriores:

```
PLACES_CACHE_FILE = C:\Users\PC 1\AppData\Local\Temp\places_detalles.json
existe: True | tamano: 16960 | entradas cacheadas: 108
```

`tests/conftest.py` aísla esa caché para la suite —con un comentario que dice exactamente
por qué— pero el CLI no lo hacía.

**Segundo defecto, más sutil.** Aun con caché limpia, los tres escenarios corrían
**compartiendo caché entre sí** dentro del mismo proceso: el escenario 1 cacheaba los 80
detalles y los escenarios 2 y 3 reportaban 0 Details. Eso sumaba en un solo número el
ahorro de la **caché** y el de **deduplicar contra la hoja**, sin forma de atribuir cuál
hizo qué. Era la diferencia entre "el código evita la llamada" y "la llamada ya estaba
pagada de antes".

**Arreglo.** `medir()` acepta ahora un parámetro `cache`: por defecto estrena una caché
vacía y desechable, y admite una ruta explícita para encadenar dos corridas sobre la misma.
Se añadió el escenario **"segunda corrida, misma ciudad"**, que es el único que aísla el
efecto del cacheo.

> Es el aviso de `CLAUDE.md` §3 al pie de la letra: *medir mal produce veredictos falsos*.
> Un instrumento que reporta un ahorro que en realidad es una caché heredada habría
> cerrado el Plan 2 con una cifra inventada.

---

## 3. ANTES Y DESPUÉS, POR SKU

Todo con **2 categorías × 3 variaciones × 3 páginas**, caché aislada por escenario.

| Escenario | Text Search | | Place Details | | Total llamadas | |
|---|---|---|---|---|---|---|
| | antes | después | antes | después | antes | después |
| Ciudad nueva | 18 | **13** | 80 | 80 | 98 | **93** (−5 %) |
| Ciudad a medio trabajar | 18 | **13** | 80 | **60** | 98 | **73** (−26 %) |
| Ciudad ya trabajada | 18 | **13** | 80 | **0** | 98 | **13** (−87 %) |
| Segunda corrida, misma ciudad | 18 | **13** | 80 | **0** | 98 | **13** (−87 %) |

La última fila **no existía antes**: sin caché, repetir una ciudad costaba lo mismo que la
primera vez.

### 3.1 El ahorro que no sale en el conteo

Cada Place Details facturaba **los tres grupos de campos** —Basic (26), Contact (3) y
Atmosphere (18)—. Tras T2.2 se pide **solo Contact**, que es el único que el código lee.
Los Details que quedan cuestan menos por llamada, y eso **no aparece** en la tabla de
arriba: es una reducción de precio unitario, no de cantidad. El importe real de la mejora
está por encima del porcentaje de llamadas, y cuánto exactamente depende de la tarifa por
SKU que trae el owner.

### 3.2 CE6, con honestidad

CE6 pedía **≥ 60 % de reducción de costo**. En llamadas, lo medido va del **5 %** (ciudad
nueva, donde el gasto es legítimo: son prospectos que no se tenían) al **87 %** (ciudad ya
trabajada o segunda corrida).

**El 60 % no se alcanza en el peor escenario, y se dice.** El gate del plan lo contempla:
*"si la reducción no llega al 60 %, no se bloquea el merge: se documenta el número real
alcanzado"*. Un 5 % medido en el peor caso y un 87 % en el repetido valen más que un 60 %
declarado sin método detrás.

Y hay un matiz que la métrica no captura: en una ciudad nueva **el gasto es el producto**.
Los 80 Details compran 80 prospectos nuevos. Lo que el Plan 2 elimina es el gasto que **no
compraba nada**: repetir lo que ya está en la hoja, repagar lo ya consultado y facturar
campos que nadie lee.

---

## 4. CE7 — LA OPTIMIZACIÓN NO PIERDE PROSPECTOS

CE7 es **gate duro**: una optimización que ahorra dinero perdiendo prospectos no es una
optimización, es un recorte de producto.

Se comparó el conjunto de negocios aprobados con el recorte activo y con el recorte
desactivado por sus dos válvulas documentadas, que **no exigen tocar código**:

```python
MAX_VARIACIONES_SIN_APORTE = 99     # no corta variaciones
CORTAR_PAGINAS_SIN_APORTE  = False  # no corta paginas
```

| Configuración | Aprobados | Text Search | Perdidos |
|---|---|---|---|
| Sin recorte (referencia) | 80 | 18 | — |
| **Recorte real del código** | **80** | **13** | **0** |

**Diff vacío: CE7 se cumple.** El recorte ahorra 5 Text Search por corrida y no pierde ni
un negocio.

### 4.1 El chequeo sabe ponerse en rojo

Un diff vacío solo significa algo si el método puede detectar una pérdida. Se forzó un
recorte absurdo (`MAX_VARIACIONES_SIN_APORTE = 0`) y el diff dejó de ser vacío:

| Configuración | Aprobados | Perdidos |
|---|---|---|
| Recorte absurdo (`=0`) | 0 | **80** |

El "0 perdidos" del recorte real es un **resultado**, no un artefacto de un chequeo que
siempre pasa.

### 4.2 Los cuatro contadores cuadran

Se cumple `nuevos_en_sheet + duplicados == encontrados` en las dos configuraciones:
80 + 0 = 80 frente a 80 encontrados.

---

## 5. EL MEDIDOR, EN LAS DOS DIRECCIONES

Un contador plausible y equivocado engaña igual que ninguno. Se comprobó que **suma una
llamada que sí ocurrió** y que **no suma un cache hit**, encadenando dos corridas sobre la
misma caché:

| Corrida | Llamadas reales al doble | Lo que dice el medidor |
|---|---|---|
| 1.ª (caché frío) | 13 Text Search, 80 Details | `text_search=13`, `place_details=80`, `cache_hits=0` |
| 2.ª (caché caliente) | 13 Text Search, **0** Details | `text_search=13`, `place_details=0`, **`cache_hits=80`** |

El medidor **no infla** el gasto contando los cache hits como llamadas, y **no los pierde**:
los reporta en su propio contador. Coincide exactamente con lo que el doble registró.

---

## 6. QUÉ QUEDA ABIERTO

| # | Qué | Por qué no se puede cerrar aquí |
|---|---|---|
| 1 | **Importe en pesos y % de reducción de costo** | Necesita el consumo por SKU de la consola de facturación. **Gate 1 del owner.** Los conteos ya están; falta solo el multiplicador |
| 2 | **Corrida real de la ciudad de referencia** | Factura la API y escribe en `LISTA DE CONTACTOS` de producción. **Gate 2 del owner** |
| 3 | **Las 5 variables en `.env.example`** | El entorno de Claude no puede escribir archivos `.env*`. **Gate 5 del owner**; el bloque exacto está en el índice §7.1 |

Riesgo aceptado y anotado: los cortes de variaciones y páginas se validaron contra
respuestas grabadas, no contra Google. Si una corrida real mostrara pérdida de prospectos,
las dos válvulas de §4 la revierten **sin desplegar código**.
