# ADR — No migrar todavía: primero 13 llamadas que compran la decisión

**Fecha:** 2026-09-17 · **Estado:** ACEPTADA
**Plan:** 2 — Gasto de Places al mínimo · **Tarea:** T2.3
**Decisión tomada con:** `council`, dos voces (riesgo operativo y coste de cambio · dinero y
valor de negocio)
**Anexa a:** `docs/adr/2026-08-28-places-legacy-vs-new.md` — **no lo contradice**: aquel dijo
*«no migrar **en este plan**»*, y este dice cuándo sí.

> Ningún dato de tarifa ni de agrupación de campos sale de la memoria del modelo. Todo lo de
> abajo se consultó el 2026-09-17 y lleva su fuente en `docs/investigacion/2026-09-15-places-new-field-mask.md`.

---

## Contexto

T2.2 contestó que sí: **`places.nationalPhoneNumber` se puede pedir en el field mask de
`searchText`**, y además **en el mismo SKU** que `places.rating` y `places.userRatingCount`, que
el importador ya necesita. El teléfono sale gratis, y los 80 Place Details por ciudad nueva
desaparecen: **$2.016 → $0.455 por ciudad (−77 %)**, ≈ **$1,567** sobre las 1,004 del catálogo.

El caso parecía cerrado. El consejo lo abrió.

---

## Decisión

**No migrar todavía. Antes, una Fase 0 de trece llamadas que no escribe nada y que compra los
dos números que le faltan a la decisión.**

`tools/comparar_places_new.py` — sobre **una ciudad ya trabajada**, hace las 13 búsquedas contra
la API New, **no toca la hoja ni `_buscar_negocios`**, y mide:

1. **¿La clave de deduplicación construida desde la respuesta New casa contra las claves que la
   hoja ya tiene?** Tasa de coincidencia.
2. **¿Qué porcentaje de negocios trae `nationalPhoneNumber`?** — que es **CE1**, el gate que
   T2.1 dejó en rojo.

Coste: **≈ $0.46**. Riesgo: **cero escrituras**.

### Por qué esto y no migrar ya

**1. La decisión se estaba tomando sobre dos números que nadie ha visto.** CE1 está en rojo: la
tasa real de sin-teléfono en Google **no está medida** —el 58.6 % del DENUE es otra fuente, y su
propio documento lo marca—. Y T2.2 §6 dice, literal, que *«la tarifa legacy actual no se pudo
citar»*: la comparación es **New-contra-New**, así que **no sabemos cuánto se paga hoy**.

**2. Hay un modo de fallo que tumbaría la hoja entera, y no tiene guarda.** `_clave_contacto`
(`app.py:3104`) es una concatenación cruda `f"{nombre}|{direccion}"`, y se calcula en **tres
sitios que deben coincidir carácter a carácter**: el prefiltro (`app.py:2969`), la exportación
(`app.py:3202`) y la reconstrucción desde las columnas de la hoja (`app.py:3252`). Su propio
docstring avisa: *«si divergen, o se paga el detalle de duplicados, o peor, **se descartan
negocios buenos creyendo que ya estaban**»*.

Si la API New devuelve el nombre o la dirección con **cualquier** diferencia de formateo, la
clave nueva no casa con ninguna vieja: **cero excepciones, cero tests rojos, y la hoja se llena
de duplicados de todo lo ya importado.** No hay ninguna guarda que lo detecte — el operador se
entera marcando teléfonos repetidos.

**La Fase 0 mide exactamente eso, y es la única forma de saberlo sin arriesgar la hoja.**

**3. El ahorro está acotado por arriba; el coste del fallo no.** $1,567 es el techo, es **un
evento único** —en ciudad ya trabajada la fuga es **cero**, medido en T2.1— y es proporcional a
ciudades que aún no se han corrido. Del otro lado está el único activo del panel: la lista de
prospectos.

**4. La urgencia no existe.** La página de *legacy* de Google (*«Last updated 2026-09-16 UTC»*)
dice: *«there is no date yet for when this will happen»*, que *«Legacy-marked services will
retain full support»*, y que darán *«at least a 12-month notice prior to the decommission»*.
**Deuda sin reloj**, confirmado en la fuente. El argumento estructural del ADR de agosto sigue
vivo: *«migrar y optimizar a la vez es peor que optimizar ahora y migrar después»*.

**5. Y migrar hoy destruiría el instrumento que mide el ahorro.** Las cuatro herramientas de
medición de este plan hablan legacy. T2.0 pudo afirmar *«ningún plan movió el gasto»* porque los
cuatro escenarios daban **13/80, 13/60, 13/0, 13/0**, idénticos a agosto. Después de migrar esa
comparación deja de existir: instrumento nuevo, API nueva, SKU nuevos. **Se pierde la capacidad
de demostrar que el ahorro ocurrió.**

---

## Alternativas consideradas, y por qué se descartaron

| Opción | Descartada porque |
|---|---|
| **Migrar ya, con el teléfono en el field mask** | Es la correcta *después* de la Fase 0. Hoy apuesta la hoja de contactos contra un ahorro único y acotado, sobre dos números sin medir y con `_clave_contacto` sin guarda |
| **Migrar «tal cual»** (búsqueda Pro + un Details por candidato) | Paga el coste entero de la migración y no compra nada: ~$0 de ahorro. Existe sólo para nombrarla |
| **Prefiltrar con el DENUE**, que el repo ya tiene con teléfono de 31,383 ferreterías | El DENUE **no es Google**. Saltarse el Details de quien el INEGI no registró cambia gasto por **prospectos perdidos**, que es justo lo que el plan prohíbe |
| **Ordenar los candidatos para que los sin-teléfono caigan fuera del tope** | Circular: no se sabe quién no tiene teléfono **antes** de pagar el Details |
| **Cachear los negativos** | **Ya está hecho** — y por eso no sirve. La caché amortiza la *segunda* corrida de una ciudad, y el barrido nacional corre cada ciudad **una vez** |
| **No migrar nunca** | La API está en *Legacy status*. Sin fecha, pero con dirección |

---

## La forma de migrar, cuando toque: por fases, y el orden importa

Las dos voces coincidieron en que la sustitución de golpe es lo peligroso, **y en que por fases
es MÁS trabajo total** —un adaptador con dos implementaciones es más código que un reemplazo—.
Lo que compra no es menos esfuerzo: es que **cada paso sea desplegable y reversible por
separado**, en una caja donde el despliegue es un `ssh` a mano y el operador es uno solo.

| Fase | Qué | Por qué en ese orden |
|---|---|---|
| **0** | Comparador que no escribe | Compra los dos números. **Si la coincidencia de claves no es ≥ 99 %, la migración se cancela aquí** |
| **1** | Extraer el transporte a un adaptador, **con la sola implementación legacy** | Los 14 dobles siguen sirviendo porque la firma no cambia. Suite verde, comportamiento idéntico, desplegable solo |
| **2** | Segunda implementación que **normaliza hacia la forma legacy** | El importador, `_clave_contacto`, el exportador y los tests **no se tocan**. Los tests nuevos son del adaptador: ~15 de mapeo campo a campo, uno por cada acceso con `.get()` |
| **3** | Interruptor `PLACES_API=legacy\|new`, **default `legacy`** | Revertir pasa a ser una variable de entorno y un `docker restart` |
| **4** | Quitar Details del camino New y cobrar el ahorro | La implementación legacy se retira **meses después**, no el mismo día |

**La clave de la fase 2:** normalizar hacia legacy es la diferencia entre **reescribir 141 tests
y escribir 15**.

### Dos cosas que hay que arreglar antes de la fase 3, no después

1. **Recalibrar `PLACES_MAX_LLAMADAS_CORRIDA` y las tarifas** (`app.py:2388-2394`), que son
   **variables de entorno del VPS, no del repo**. El tope está calibrado contra una corrida de
   **93 llamadas**; migrada son **13**. Un tope de 120 dejaba pasar una ciudad — después dejaría
   pasar nueve. Es un cambio que vive fuera de git y hay que hacerlo **en el mismo despliegue**.
2. **Escribir un procedimiento de rollback en el RUNBOOK.** Hoy no existe. En una caja con
   despliegue manual, sin CI de despliegue, y con precedente de código rancio sirviendo tres
   semanas, tocar la ruta de Places sin rollback escrito no es arquitectura: es una apuesta.

---

## Consecuencias

**A favor**
- La decisión de migrar se toma con **datos propios**, no con un proxy de otra fuente.
- **CE1 se cierra de paso**, con 13 llamadas en vez de una corrida completa.
- La hoja de contactos no se arriesga mientras tanto.
- El ahorro no se pierde: las ciudades vírgenes siguen ahí, y hoy es el momento **más barato**
  de pagar esta deuda porque la mayoría del catálogo está sin trabajar.

**En contra, y hay que decirlo**
- **Se aplaza un ahorro real y ya cuantificado.** Cada mes de barrido en legacy cuesta de más.
- La Fase 0 **necesita una clave de Google y ~$0.46**: sigue siendo gate del owner, aunque
  mucho más pequeño que el anterior.
- Por fases es **más trabajo total** que sustituir de golpe. Se acepta a cambio de
  reversibilidad.

---

## Qué evidencia haría reversible esta decisión

**A «migrar ahora», si se cumplen las dos:**

- **(a)** La Fase 0 mide **≥ 99 %** de coincidencia de `_clave_contacto` contra las claves que ya
  están en la hoja. **Por debajo, la migración no se discute: se cancela** hasta resolver la
  clave.
- **(b)** Esa misma corrida da una tasa de sin-teléfono en Google **≥ 30 %**, cerrando CE1 con
  dato propio.

**A «migrar ya, sin esperar»**, con una sola: **Google publica fecha de retirada a menos de 9
meses.** Deja de ser deuda y pasa a ser una caída programada.

**A «no migrar en este plan, punto»:** si **el barrido de las 1,004 ciudades no está
calendarizado**. El ahorro es estrictamente proporcional a ciudades nuevas corridas: a 5 ciudades
al mes son **$7.80/mes**, y la migración sería riesgo puro con retorno decorativo.

**Y una condición de proceso, innegociable en cualquier escenario:** no se toca la ruta de Places
hasta que el rollback esté **escrito y probado** en el RUNBOOK.

---

## Nota sobre el desacuerdo, porque no lo hubo y eso también informa

Las dos voces llegaron a **«migrar después»** por caminos distintos —una por el riesgo sobre la
hoja, la otra por coste de oportunidad frente a T3.7 y a la PII expuesta— y **coincidieron en la
condición**: medir antes de decidir.

La voz del negocio añadió algo que este ADR adopta: **CE1 (tasa de fuga) y CE3 (la corrida real
del conteo, de T3.7) piden la misma llave** —una ciudad pequeña, credenciales del owner, una
corrida—. **Son dos gates distintos pidiendo lo mismo.** La Fase 0 puede resolver CE1 sin
escribir nada; si el owner va a correr CE3 de todos modos, hacerlas juntas sale casi gratis.
