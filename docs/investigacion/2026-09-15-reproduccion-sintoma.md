# T3.1 — Reproducir el síntoma, y H1 (despliegue rancio)

**Plan:** 3 · **Tarea:** T3.1 · **Fecha:** 2026-09-17
**Rama:** `fix/conteo-importador-reincidencia` · **Baseline:** 1,193 passed, 2 skipped
**Regla que gobierna esta tarea:** *ninguna línea de código se toca antes de cerrarla.* Se
cumplió: este documento y `tools/huella_despliegue.py` son lo único que se escribió.

---

## 1. Las dos respuestas, arriba

> **H1 (despliegue rancio) queda DESCARTADA con evidencia.** El VPS sirve el fix de agosto y
> algo posterior, y su front-end es **byte a byte el de `main`** salvo saltos de línea.
>
> **El síntoma NO se reproduce con ningún instrumento disponible.** Eso es un resultado, no un
> fracaso, y el plan lo contempla: *«si el síntoma no reproduce, decirlo; es un resultado, y el
> plan pasa a T3.5 sin inventar un bug»*.
>
> **Pero queda un punto ciego, y es exacto.** El número que el panel publica es *«filas que le
> mandé a Google en un `append_rows` que no lanzó excepción»*, **no** *«filas que Google confirmó
> haber añadido»*. Ningún test puede verlo, porque **todos los dobles escriben exactamente lo que
> se les da**. Y el único criterio que lo habría visto —la corrida real de agosto— **nunca se
> ejecutó**.

---

## 2. H1 · La huella de despliegue

`/salud` es deliberadamente mudo: no dice versión, ni commit, ni hostname. Es decisión de
seguridad del Plan 5 y **no se revierte**. Así que H1 se resuelve preguntándole al panel por
**rasgos que sólo existen después del fix**.

Se construyó `tools/huella_despliegue.py`, que no fecha el despliegue con un número de versión
sino con **siete marcadores de comportamiento**, cada uno atado al commit que lo introdujo.

### 2.1 Resultado contra producción

```
GET https://panelnioval.duckdns.org/api/importador/estado -> HTTP 200   (14 claves)

  SI  encontrados      (pre-ae0e1c9)   el contador único que ya existía antes del fix
  SI  nuevos_en_sheet  (ae0e1c9)       B1: filas REALMENTE escritas
  SI  duplicados       (ae0e1c9)       B2/B3: los que ya estaban en la hoja
  SI  descartados      (ae0e1c9)       B15: rechazados por filtros, sin inflar
  SI  fraccion         (ae0e1c9)       B6: progreso continuo, no 0/50/100
  SI  fase             (ae0e1c9)       B6: qué está haciendo ahora mismo
  SI  medidor          (PR #38)        tope de gasto de Places — POSTERIOR al fix

VEREDICTO: H1 DESCARTADA
```

Los **cinco** marcadores del fix están, **y además uno posterior**. Eso es más fuerte que un
sí/no: el código servido no es «igual o posterior a `ae0e1c9`», es **estrictamente posterior**.

### 2.2 La contraprueba, porque un instrumento que sólo sabe decir que sí no vale

Antes de creerle el verde, se comprobó que **sabe decir que no**. Se levantó un doble local que
responde como un panel **pre-fix** —un solo contador— y se le pasó el mismo instrumento:

```
  SI  encontrados        NO  nuevos_en_sheet    NO  duplicados
  NO  descartados        NO  fraccion           NO  fase          NO  medidor

VEREDICTO: H1 CONFIRMADA — el VPS sirve codigo ANTERIOR a ae0e1c9.
  Faltan del fix de agosto: nuevos_en_sheet, duplicados, descartados, fraccion, fase
exit = 1
```

**El instrumento detecta el positivo que sabe que existe.** Sin esta contraprueba, el verde de
§2.1 no valdría nada — es la regla que este proyecto ya pagó cara dos veces.

### 2.3 Y el front-end, que es lo que el operador de verdad VE

La huella fecha **la API**. El síntoma es visual, así que se comprobó también lo servido:

| Archivo | Servido | En `main` | |
|---|---:|---:|---|
| `/static/js/importador.js` | 43,026 B | 44,001 B | **idéntico** |
| `/static/css/componentes.css` | 18,817 B | 19,385 B | **idéntico** |

Los bytes difieren en **exactamente 975**, que son los saltos CRLF del checkout de Windows: el
sha256 que casó es el **normalizado a LF**. Contenido, el mismo.

Y el JS servido contiene `nuevos_en_sheet` **5 veces**, `s-nuevos` 2, `duplicados` 6 y
`descartados` 5. **La lógica de conteo corregida está en el navegador del operador.**

---

## 3. El síntoma, contra el `main` de hoy

`tools/reproducir_bugs_importador.py conteo` —la herramienta de agosto, sin tocar— sobre el
`main` de hoy:

```
UI dice 'Encontrados'            : 14
Filas REALMENTE escritas en hoja : 10
status final                     : done

Mensaje final que lee el operador:
  "De 14 candidatos de Google, 14 pasaron los filtros de calidad: 10 se guardaron
   y 4 ya estaban en la lista. Los otros 0 se descartaron por reseñas,
   calificación o falta de teléfono."

VEREDICTO: B1/B2/B3 CORREGIDOS — nuevos_en_sheet=10 es el numero grande.
```

Los dos números **siguen siendo distintos, y eso es lo correcto**: 14 candidatos, 10 filas
nuevas, 4 que ya estaban. Lo que cambió en agosto no fue la aritmética: fue que **ahora los dos
están a la vista y rotulados**. El «20 vs 10» era que sólo se publicaba uno, rotulado como si
fuera el otro.

B4 también sigue cerrado: con la escritura fallando, la corrida termina en `error` con la causa
a la vista, no en `done` con palomita.

### 3.1 Y la pantalla tampoco produce el síntoma

`templates/importador.html:99-115`. **«Nuevos en la hoja» es el recuadro principal** —clase
`stat--principal`, que en `componentes.css:122` sube a `--texto-3xl` y ocupa la fila entera
(`importador.css:318`)— y el otro número está rotulado **«Aprobados por filtros»**, no
«guardados».

Para que el operador lea hoy «20» tendría que estar mirando el recuadro pequeño rotulado
*Aprobados por filtros*. No es el número grande.

---

## 4. EL PUNTO CIEGO, que es el hallazgo de esta tarea

Todo lo anterior dice que el camino **desde `_exportar_a_sheets` hasta los ojos del operador**
está bien. Lo que **ningún instrumento de este repo comprueba** es el eslabón anterior:

```python
# app.py:3231-3238
if nuevos:
    nuevos = [[_escapar_formula(v) for v in fila] for fila in nuevos]
    ws.append_rows(nuevos, value_input_option='USER_ENTERED')
    nombres_existentes.update(claves_nuevas)
    _cache_pop('contactos')
return len(nuevos)
```

`return len(nuevos)` es **el número de filas que se enviaron**, no el que Google confirmó. La
respuesta de `append_rows` trae `updates.updatedRows`, y **se descarta sin mirarla**. Una
escritura **parcial** —la API responde 200 y añade menos filas de las pedidas— haría que el panel
publicara de más **sin que nada lanzara una excepción**.

### 4.1 Por qué esto es invisible para los 80 tests

Porque **todos los dobles escriben exactamente lo que se les da**:

```python
def append_rows(self, filas, **kw):
    self.escrituras += len(filas)
    self.filas.extend(filas)
```

Bajo ese doble, `len(nuevos)` **es correcto por construcción**: no existe un escenario en la
suite donde el número enviado y el aterrizado difieran. Los 80 tests no están mal escritos —
vigilan bien lo que vigilan—, pero **ninguno puede ver este fallo**, ni aunque estuviera vivo.

### 4.2 Y aquí es donde encaja el gate que nunca se cerró

Esto es lo que el T3.0 ya había marcado y ahora tiene nombre concreto. De los 11 criterios de
agosto, **CE1 —comparar el número de la UI contra la hoja de verdad— quedó esperando al owner y
no se ejecutó nunca.** Es el **único** criterio que habría mirado este eslabón.

**Dicho con precisión, porque importa:** no estoy afirmando que sea la causa. Estoy afirmando
que, tras descartar H1 y ver la repro pasar, **es el único sitio donde el síntoma puede seguir
vivo sin que nada lo note** — y que el instrumento que lo detectaría no existe todavía.

---

## 5. Lo que esta tarea NO pudo hacer, dicho como falta

El plan pide *«anotar qué número mostró la UI y qué número tenía la hoja, con captura»*.

**No hay tal captura, porque no hubo corrida real.** Esta máquina no tiene credenciales de
Google —`GOOGLE_CREDENTIALS_JSON` ausente, ni `credentials.json` ni `.env` en disco; comprobada
la **presencia**, nunca el valor— y una corrida real además **factura Places** y **escribe en
`LISTA DE CONTACTOS` de producción**, que es gate del owner desde agosto.

Una captura del panel en producción no sustituye nada: el importador está en `idle` y la fila de
contadores va `hidden`. Fotografiar ceros no es evidencia de un conteo.

---

## 6. Estado de las hipótesis

| | Hipótesis | Estado tras T3.1 |
|---|---|---|
| **H1** | Despliegue rancio | ❌ **DESCARTADA.** 5 marcadores del fix + 1 posterior; front-end idéntico al de `main`; instrumento verificado en las dos direcciones |
| **H2** | Regresión posterior a `ae0e1c9` | 🟡 **Sin indicio.** La repro de agosto pasa entera sobre el `main` de hoy — en los caminos que cubre |
| **H3** | Caso residual no cubierto | 🟢 **La que queda viva**, y con dos candidatos concretos para T3.2: la **escritura parcial** del §4, y el camino **`presupuesto_agotado`** (`app.py:3509`) que el plan no listaba |

**CE1 no se cierra aquí** — sigue siendo el gate de la corrida real.

---

## 7. Lo que T3.2 hereda

1. **No rehacer H1.** Está cerrada con instrumento reutilizable: `tools/huella_despliegue.py`.
2. **Los dos candidatos de H3**, por orden de sospecha: la escritura parcial silenciosa (§4) y
   `presupuesto_agotado`.
3. **La bisección de H2 sigue disponible** pero baja de prioridad: `ae0e1c9` contra `main` son
   24 commits que tocan `app.py`, y la repro ya pasa en los dos extremos.
4. **Una advertencia sobre el método:** si T3.2 escribe un test para la escritura parcial, el
   doble **tiene que poder mentir** — devolver menos filas de las que recibe. Un doble honesto no
   puede reproducir un fallo de honestidad.
