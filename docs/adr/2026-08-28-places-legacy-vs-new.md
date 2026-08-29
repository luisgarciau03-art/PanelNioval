# ADR — Places legacy optimizada, no migrar a Places API (New)

**Fecha:** 2026-08-28 · **Estado:** ACEPTADA
**Plan:** 2 — Optimización del gasto de Places · **Tarea:** T2.1

> Ningún dato de tarifa ni de agrupación de campos sale de la memoria del modelo.
> Todo lo de abajo se consultó en esta sesión, y se dice de dónde salió.

---

## Fuentes consultadas (2026-08-28)

1. **Documentación oficial de Place Details (legacy)** —
   `developers.google.com/maps/documentation/places/web-service/details`
2. **El cliente Python instalado**, que es la autoridad sobre qué acepta *este*
   proyecto: `googlemaps 4.10.0`, módulo `googlemaps.places`.

---

## Lo que dice la documentación

Sobre el parámetro `fields`, textualmente:

> *"If you don't specify at least one field with a request, or if you omit the
> `fields` parameter from a request, **ALL possible fields will be returned, and
> you will be billed accordingly**."*

Sobre cómo se factura:

> *"Basic, Contact, and Atmosphere SKUs are charged **in addition to** the base
> SKU (Places Details, Find Place, Nearby Search, or Text Search) for the request
> that triggered them."*

Y sobre el estado del producto:

> *"This product or feature is in Legacy status."* — con indicación de migrar a
> Places API (New).

---

## Lo que hace hoy el código

`app.py`, dentro de `_buscar_negocios`:

```python
det = gmaps_client.place(pid, language='es')['result']
```

**Sin `fields`.** Según la cita de arriba, eso factura **los tres grupos** en cada
llamada. Confirmado contra el cliente instalado:

| Grupo | Campos | ¿Los usamos? |
|---|---|---|
| `PLACES_DETAIL_FIELDS_BASIC` | 26 | **No.** Nombre, dirección y geometría salen del Text Search, que ya está pagado |
| `PLACES_DETAIL_FIELDS_CONTACT` | 6 | **Sí, tres**: `formatted_phone_number`, `website`, `opening_hours` |
| `PLACES_DETAIL_FIELDS_ATMOSPHERE` | 18 | **No.** `reviews`, `editorial_summary`, `price_level`, `serves_*`… |

De los 50 campos que se pagan, se leen **tres**. Y `rating` y `user_ratings_total`
—que sí se usan— vienen del **Text Search** (`lugar`), no del Details: se leen de
`lugar.get('rating')` y `lugar.get('user_ratings_total')` antes de llamar a
`place()`. No hay ninguna razón para pagar Atmosphere.

---

## Decisión

**Quedarse en la API legacy y optimizarla.** No migrar a Places API (New) en este
plan.

### Por qué no migrar ahora

- El cliente `googlemaps` 4.10.0 que fija `requirements.txt` implementa la API
  **legacy**: `client.places()` es Text Search legacy y `client.place()` es Place
  Details legacy. Places API (New) es otro endpoint, con cabecera `FieldMask` y
  tarificación propia; usarla desde este proyecto exigiría **HTTP directo**, no el
  cliente que ya está probado.
- Migrar cambiaría a la vez el transporte, el formato de respuesta y el modelo de
  facturación. Sería imposible atribuir un ahorro al cambio de `fields` si todo se
  mueve junto.
- El ahorro grande de este plan **no depende de la API nueva**: sale de pedir tres
  campos en vez de cincuenta y de dejar de pagar detalles de negocios que ya están
  en la hoja. Las dos cosas se hacen en legacy.

### Riesgo asumido, dicho en voz alta

La API está en **Legacy status**. Esto es deuda con fecha: en algún momento habrá
que migrar. Lo que este ADR sostiene es que **migrar y optimizar a la vez es peor
que optimizar ahora y migrar después**, con el gasto ya bajo y una medición limpia
de por medio.

**Recomendación para el owner:** abrir un plan aparte para la migración, y
consultar antes las fechas de retirada que anuncie Google. Este ADR no las fija
porque cambiarían sin que nadie actualizara el documento.

---

## Qué se implementa, en consecuencia

**T2.2** — `place()` pasa a pedir exactamente:

```python
fields=['formatted_phone_number', 'website', 'opening_hours']
```

Los tres están en `PLACES_DETAIL_FIELDS_CONTACT` del cliente instalado, así que
la petición factura **base + Contact**, y deja de facturar **Basic + Atmosphere**.

Ninguno de los tres está en `DEPRECATED_FIELDS`, que son `permanently_closed` y
`review` (singular) — comprobado en el cliente, no supuesto.

**T2.3** — no pagar Details de negocios que ya están en la hoja. La clave de
deduplicación es `Nombre|Dirección` y **los dos campos vienen del Text Search**,
así que se pueden comparar **antes** de llamar a `place()`.

Medido con `tools/medir_llamadas_places.py` sobre la configuración actual:

| Escenario | Details pagados | Filas nuevas | Pagados y tirados |
|---|---|---|---|
| Ciudad nueva | 80 | 80 | 0 |
| Ciudad a medio trabajar | 80 | 60 | **20 (25 %)** |
| **Ciudad ya trabajada** | 80 | 0 | **80 (100 %)** |

Volver a correr una ciudad ya trabajada paga **ochenta** Place Details y escribe
**cero** filas.

---

## Nota sobre T2.0

La medición **en pesos** requiere la consola de facturación de Google Cloud del
proyecto `bubbly-subject-412101`. No hay acceso: no hay navegador, no hay `gcloud`
instalado, y la cuenta de servicio del proyecto solo tiene alcances de
`spreadsheets` y `drive`. **T2.0 queda BLOQUEADA y escalada al owner.**

Lo que sí hay es el conteo exacto de llamadas por corrida, que es la base sobre la
que se multiplica el precio por SKU cuando el owner lo aporte. Un conteo de
llamadas es además **mejor evidencia del efecto del código** que un recibo
mensual, porque el recibo mezcla este consumo con el del resto del proyecto.
