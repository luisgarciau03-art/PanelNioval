# CE6 — Qué hace falta para leer el gasto en pesos, y qué número esperar

**Plan:** 2 · **Tarea:** T2.7 · **Fecha:** 2026-09-17
**Estado:** 🔴 **GATE DEL OWNER.** Nada de esto se puede hacer desde una sesión de código.

> Este documento existe para que el gasto real deje de estar repartido en cuatro sitios. **Es
> el único lugar donde mirar** cuando haya acceso a la consola de facturación.

---

## 1. Lo que falta, en una frase

**Acceso a Google Cloud Billing del proyecto que emite la `GMAPS_API_KEY`.** Sin él no hay
importe en pesos: sólo conteos de llamadas, que es lo que este plan midió.

Por qué no se puede desde aquí: no hay navegador, no hay `gcloud`, y **la cuenta de servicio del
proyecto sólo tiene alcances de Sheets y Drive**. No es una limitación de esta sesión: es que
esa credencial no puede leer facturación aunque quisiera.

---

## 2. Los tres pasos, en orden

1. **Consola de Google Cloud → Billing → Reports.** Filtrar por el proyecto de la
   `GMAPS_API_KEY` y agrupar **por SKU**.
2. **Anotar el importe por SKU del último mes completo.** Los SKU que importan tienen nombre
   propio: *Places API Text Search*, *Places API Place Details* y sus grupos de campos.
3. **Poner las tarifas en el `.env` del VPS** para que el medidor del panel publique importes en
   vez de sólo llamadas:

```
PLACES_COSTO_TEXT_SEARCH=<USD por llamada>
PLACES_COSTO_DETAILS=<USD por llamada>
PLACES_PRESUPUESTO_CORRIDA=<USD por corrida>
```

⚠️ **Ninguna tiene valor por defecto, y es a propósito.** Sin tarifa el panel **no publica
importe** — un precio inventado sería peor que ninguno. Y mientras no estén, el único freno
utilizable es `PLACES_MAX_LLAMADAS_CORRIDA`.

---

## 3. Qué número esperar, para que el recibo se pueda contrastar

Todo esto está medido, no estimado. Una corrida de **ciudad nueva** son **93 llamadas**:

| | Cantidad |
|---|---:|
| Text Search | **13** |
| Place Details | **80** |

| Escenario | Text Search | Details |
|---|---:|---:|
| Ciudad nueva | 13 | 80 |
| Ciudad a medio trabajar (30 ya en la hoja) | 13 | 60 |
| **Ciudad ya trabajada** | 13 | **0** |
| Segunda corrida de la misma ciudad (caché) | 13 | **0** |

**Cómo contrastarlo con el recibo:** divide el importe de Place Details del mes entre el número
de corridas de ciudades nuevas. Si no da alrededor de **80 llamadas por corrida**, hay algo que
este plan no vio — y eso sería un hallazgo, no un error de cuentas.

### 3.1 La referencia para el día de la migración

Si algún día se migra —hoy el ADR `2026-09-15-ruta-de-telefono-places` dice que **no**—, la misma
corrida pasa a **13 llamadas y 0 Details**. Con las tarifas citadas de la API New (página de
pricing de Google, *«Last updated 2026-09-16 UTC»*, banda 0–100,000):

| | Por ciudad nueva |
|---|---:|
| Migrando «tal cual» (13 TS Pro + 80 PD Enterprise) | $2.016 |
| **Con el teléfono en el field mask** (13 TS Enterprise) | **$0.455** |

⚠️ **El crédito de $200 al mes ya no aplica**: la documentación dice *«until February 28,
2025»*.

---

## 4. Las otras dos llaves que el owner tiene, y son la misma

Tres cosas distintas esperan por el mismo acto —**una corrida real con credenciales**— y
conviene hacerlas juntas:

| Qué | De quién | Qué se obtiene |
|---|---|---|
| **CE3 del Plan 3** | abierto desde el **2026-08-27** | Que el número de la UI **sea** el de la hoja: contar filas antes, correr, contar después |
| **CE1 del Plan 2** | abierto en T2.1 | La **tasa real de sin-teléfono en Google**, que hoy sólo tiene el proxy del DENUE (58.6 %) |
| **La Fase 0 del ADR** | T2.4 | Si la clave de deduplicación casa ≥ 99 % con la API New. `tools/comparar_places_new.py`, **no escribe nada**, ≈ $0.46 |

**Elegir una ciudad pequeña Y YA TRABAJADA.** Pequeña acota el gasto; ya trabajada hace que
`nuevos` y `aprobados` **sean distintos**, que es lo único que prueba que se distinguen. Una
ciudad virgen los deja iguales y la comprobación no prueba nada.

**Antes de la corrida real: respaldo de hojas** (`python tools/respaldar_hojas.py`). No es
opcional — escribe en `LISTA DE CONTACTOS` de producción.

---

## 5. Y una cuarta, que no cuesta dinero

**Confirmar si el tope está puesto.** `PLACES_MAX_LLAMADAS_CORRIDA` vive en el `.env` del VPS y
**ningún endpoint lo expone**. Si no está, **no hay freno**. Es mirar un archivo por `ssh`.
