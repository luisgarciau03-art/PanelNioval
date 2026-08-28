# Costo de Places antes de optimizar — y la mitad que no pude medir

**Plan:** 2 — Optimización del gasto de Places · **Tarea:** T2.0
**Fecha:** 2026-08-28 · **Rama:** `perf/gasto-places-importador`

---

## 1. La mitad BLOQUEADA: el importe en pesos

T2.0 pide el consumo por SKU desde la consola de Google Cloud del proyecto dueño
de la `GMAPS_API_KEY`. **No puedo obtenerlo.** Comprobado, no supuesto:

| Vía | Resultado |
|---|---|
| `gcloud` CLI | `command not found` — no está instalado |
| Cuenta de servicio del proyecto | `bubbly-subject-412101`, alcances solo `spreadsheets` y `drive` |
| Alcances de facturación en el código | ninguno: no hay `cloud-billing` ni `cloud-platform` |
| Navegador | no hay |

**Estado: BLOQUEADA. Escalada al owner.**

Lo que hace falta es el consumo del periodo actual de las SKU de Places —Text
Search, Place Details y sus grupos de campos Basic/Contact/Atmosphere— con
llamadas y costo. Con el precio por SKU, los conteos de la §2 se convierten en
pesos directamente.

> **Por qué esto no detiene el plan.** La razón que da T2.0 para exigir el número
> es *"sin un número de partida no se puede demostrar ninguna mejora"*. Ese
> requisito se cumple con la §2: hay número de partida, es exacto y es repetible.
> Lo único que falta es el **multiplicador**, y se aplica al final sin rehacer
> nada. Avanzar así no es avanzar a ciegas.

---

## 2. La mitad que sí se puede medir: llamadas por corrida

`tools/medir_llamadas_places.py` corre el importador contra un cliente de Places
instrumentado que **cuenta** lo que se le pide. No toca la red, no toca la hoja de
producción y no cuesta nada.

**Es mejor evidencia del efecto del código que un recibo mensual**, porque el
recibo mezcla este consumo con el resto del proyecto, mientras que el conteo
aísla exactamente lo que cambió.

### Escenario de referencia

2 categorías × 3 variaciones × 3 páginas, 20 negocios por página. Tres estados de
la ciudad, que es lo que de verdad cambia el gasto:

### ANTES (`main`, antes del Plan 2)

| Escenario | Text Search | Place Details | Filas nuevas | Pagados y tirados |
|---|---|---|---|---|
| Ciudad nueva | 18 | 80 | 80 | 0 |
| Ciudad a medio trabajar | 18 | 80 | 60 | **20 (25 %)** |
| **Ciudad ya trabajada** | 18 | 80 | **0** | **80 (100 %)** |

Y **cada uno de esos 80 Details facturaba los tres grupos de campos** —Basic (26),
Contact (6) y Atmosphere (18)— porque la llamada iba sin `fields`. Cincuenta
campos facturados para leer tres.

### DESPUÉS (T2.2 + T2.3)

| Escenario | Text Search | Place Details | Filas nuevas | Ahorro en Details |
|---|---|---|---|---|
| Ciudad nueva | 18 | 80 | 80 | 0 % |
| Ciudad a medio trabajar | 18 | **60** | 60 | **25 %** |
| **Ciudad ya trabajada** | 18 | **0** | 0 | **100 %** |

Más, en las llamadas que quedan: se dejan de facturar **Basic y Atmosphere**.

### Cómo reproducirlo

```bash
python tools/medir_llamadas_places.py          # tabla legible
python tools/medir_llamadas_places.py --json   # para comparar corridas
```

---

## 3. De dónde sale cada ahorro

**T2.2 — `fields` explícitos.** La documentación de Place Details legacy,
consultada el 2026-08-28, es literal:

> *"If you don't specify at least one field with a request, or if you omit the
> `fields` parameter from a request, ALL possible fields will be returned, and you
> will be billed accordingly."*

Se piden ahora los tres campos que el código lee, todos del grupo Contact.
`rating` y `user_ratings_total`, que sí se usan, vienen del **Text Search** y ya
estaban pagados.

**T2.3 — no pagar el detalle de lo que ya está en la hoja.** La clave de
deduplicación es `Nombre|Dirección`, y **los dos campos vienen del Text Search**.
Se pueden comparar sin pagar nada. Antes se pagaba el detalle, se filtraba por
teléfono, se exportaba, y solo ahí se descubría que ya estaba.

De paso, la hoja se lee **una vez por corrida** en vez de una vez por categoría.
Son ~7,000 filas.

---

## 4. Baseline de tests

```
python -m pytest tests/
324 passed
```

Partida del Plan 2: 314. Los 10 nuevos son de `tests/test_costo_places.py`.

---

## 5. Lo que el owner tiene que aportar para cerrar T2.0

1. Consumo por SKU de Places del periodo actual, en la consola de Google Cloud del
   proyecto `bubbly-subject-412101`.
2. Con eso, multiplicar los conteos de la §2 y obtener el ahorro en pesos.
3. Opcionalmente, una **corrida real** sobre una ciudad de referencia para
   contrastar los conteos sintéticos contra el consumo observado. Esa corrida
   factura y escribe en producción, así que también es decisión suya.


---

## 6. T2.4 — los cortes, y el riesgo que no pude cerrar

Tres cortes, **todos disparados por un aporte MEDIDO de cero**, nunca por
predicción. Efecto: Text Search por corrida **18 → 13**.

| # | Corte | Riesgo |
|---|---|---|
| 1 | Una consulta que responde bien y **vacía** no se reintenta | **Ninguno.** Misma consulta, mismos parámetros, misma respuesta vacía |
| 2 | Se deja de paginar tras una página que no aportó ningún `place_id` nuevo | Bajo. Asume que Places pagina por relevancia decreciente |
| 3 | Se dejan de pedir variaciones tras 2 seguidas que **trajeron resultados y ninguno nuevo** | **El único real.** Ver abajo |

Una variación **vacía no cuenta** para el corte 3, a propósito. Vacío no es
saturación: significa que esa fraseología no casó, y otra puede casar. Contar los
vacíos habría dejado que dos consultas sin resultados cancelaran una tercera que
sí funcionaba, perdiendo la categoría entera.

### El riesgo que queda abierto

El corte 3 asume que si *"Ferreterías en X"* y *"Ferreterías cerca de X"* se
saturan, *"Ferreterías X"* también. Las tres son casi la misma frase, así que es
razonable — **pero no está probado**, y la búsqueda de texto de Google no
garantiza monotonía entre fraseologías parecidas.

**El plan exige verificarlo (CE7): correr la ciudad de referencia y comparar el
conjunto de negocios aprobados contra el de T2.0. Esa corrida factura la API y
escribe en producción, así que es gate del owner y no se pudo hacer.**

Se documenta como **riesgo aceptado y no verificado**, no como algo resuelto.

### Cómo revertir cada corte sin tocar código

```python
MAX_VARIACIONES_SIN_APORTE = 99     # desactiva el corte 3 (el de riesgo)
CORTAR_PAGINAS_SIN_APORTE  = False  # desactiva el corte 2
```

El corte 1 no tiene interruptor porque no tiene riesgo que revertir.

### Nota de diseño

Dentro de la **primera** categoría el corte 3 no puede dispararse: en la
variación 1 el conjunto de vistos está vacío, así que todo cuenta como nuevo. El
ahorro es **entre categorías**, que es justo el caso de este proyecto —
`Distribuidoras Ferreterías` se solapa fuerte con `Ferreterías`.
