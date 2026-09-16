# AUDITORÍA DE COBERTURA DEL CATÁLOGO DE CIUDADES

**Tarea:** Plan 1 · T1.2 · **Fecha:** 2026-09-15 · **Rama:** `feat/relevancia-nacional-produccion`
**Pregunta que responde:** ¿los 606 municipios del catálogo son «todas las ciudades de la región»?

**Regla que gobierna este documento:** la brecha se responde con un **número**, no con un
adjetivo. Todas las cifras se obtuvieron procesando el ZIP del INEGI descargado en esta
sesión; ninguna se transcribió de otro documento.

---

## 1. La respuesta, en una línea

> **Quedan fuera 1,621 municipios con al menos una ferretería, y ninguno de ellos llega a
> 20: el excluido más grande de todo el país tiene 19.** El catálogo está completo respecto
> de su propio umbral. Lo que **no** está equilibrado es la cobertura regional: el Sureste
> alcanza el **65.6 %** de la masa ferretera de su región, contra el **97.2 %** del Valle de
> México.

La brecha, por tanto, **no es un olvido del catálogo**: es una consecuencia del umbral
`≥20 ferreterías`. La decisión no es «arreglar un error», es **elegir dónde poner el corte**.

---

## 2. Cómo se midió (reproducible)

| Paso | Detalle |
|---|---|
| Fuente | `denue_00_46591-46911_csv.zip` — INEGI, DENUE **05_2026** |
| Descarga | `https://www.inegi.org.mx/contenidos/masiva/denue/denue_00_46591-46911_csv.zip` |
| **Bytes obtenidos** | **60,209,960** — **idéntico** al registrado en agosto (`docs/investigacion/2026-08-28-relevancia-ferretera-mexico.md` §3). No es la trampa del ZIP de 0 bytes |
| Encoding | `latin-1` (si se lee como utf-8 se rompen los acentos de `municipio`) |
| Filas leídas | **638,861** |
| Filtro | `codigo_act == "467111"` (ferreterías y tlapalerías) |
| Agregación | por `cve_ent` + `cve_mun`; región por `REGION_POR_ENTIDAD`, **copiado literal** del generador (`tools/generar_catalogo_ciudades.py:77-88`) |
| Script | `docs/auditoria/respaldos/2026-09-15/` (medición cruda en `cobertura-t12-medicion.json`) |

### 2.1 Verificación en las dos direcciones

La regla del entorno manda comprobar que el método **encuentra un positivo conocido** antes
de creerle un cero. Este pipeline es independiente del de agosto y **reproduce sus cifras
exactamente**:

| Métrica | Agosto (`2026-08-28`) | **Esta medición** | ¿Coincide? |
|---|---|---|---|
| Establecimientos SCIAN 467111 | 75,726 | **75,726** | ✅ |
| Municipios con ≥1 ferretería | 2,227 | **2,227** | ✅ |
| Municipios con ≥10 | 995 | **995** | ✅ |
| Municipios con ≥20 | 589 | **589** | ✅ |

Y en la dirección contraria: **0 de los 606 municipios del catálogo caen fuera del universo
DENUE**. Si alguna clave INEGI estuviera mal formada, aparecería aquí; no aparece ninguna.

---

## 3. La discrepancia 589 vs 606, explicada con código (ya no es hipótesis)

El ADR §5.2 fija el corte en **≥20 → 589 municipios**, pero el catálogo tiene **606**.
T1.1 dejó la explicación como hipótesis. **Queda confirmada:**

- **589** municipios entran **por umbral** (≥20 ferreterías).
- **17** entran **por herencia del array legacy**, y tienen entre **1 y 16** ferreterías.

La función responsable es `resolver_array_viejo()`
(`tools/generar_catalogo_ciudades.py:336-341`), cuyo comentario dice el porqué:

> *«Se resuelve ANTES de recortar el catálogo: una ciudad que el operador ya podía elegir no
> puede desaparecer porque no llegue al corte de ferreterías. Quitarle una opción es
> irreversible para él; dejarla abajo en el ranking, no.»*

589 + 17 = **606**. No hay nada que arreglar aquí.

---

## 4. Cobertura por macro-región

### 4.1 Situación actual (umbral ≥20 + los 17 heredados)

| Región | Universo (≥1 ferr.) | En catálogo | Cobertura de **municipios** | Cobertura de **ferreterías** |
|---|---:|---:|---:|---:|
| Valle de México | 141 | 88 | **62.4 %** | **97.2 %** |
| Centro-Norte | 188 | 72 | 38.3 % | 89.6 % |
| Noroeste | 109 | 41 | 37.6 % | 92.4 % |
| Occidente | 245 | 81 | 33.1 % | 84.9 % |
| Noreste | 220 | 67 | 30.5 % | 91.5 % |
| Centro-Sur | 459 | 127 | 27.7 % | 79.5 % |
| Península | 129 | 24 | 18.6 % | 82.7 % |
| **Sureste** | **736** | **106** | **14.4 %** | **65.7 %** |
| **Nacional** | **2,227** | **606** | **27.2 %** | **86.3 %** |

**La hipótesis del plan era correcta:** el Sureste está sub-representado. Es la región con más
municipios del país (736, casi un tercio del universo) y la que menos cubre.

### 4.2 ⚠️ Nota de método: las dos columnas responden preguntas distintas

- Por **municipios**, el desequilibrio Sureste↔Valle de México es de **4.4×**.
- Por **ferreterías**, es de **1.48×**.

**Ninguna de las dos es «la métrica honesta» y la otra un engaño** — decirlo así sería un
*non-sequitur*, y una versión previa de este documento lo cometió. Son dos preguntas:

| Pregunta | La responde | Sureste vs VM |
|---|---|---|
| ¿En cuántas plazas puede operar el vendedor? | **municipios** | 4.4× |
| ¿Qué parte del mercado potencial alcanza? | **ferreterías (masa)** | 1.48× |

**Las dos importan.** Lo que sí es cierto es que el 4.4× **sobredimensiona el impacto de
negocio**, porque está inflado por la fragmentación rural del Sureste: en esa razón un
municipio de 3 ferreterías pesa igual que uno de 300. Por eso el documento **decide con la
masa** —es la que se traduce en ingresos— y **reporta ambas**: el problema real es que
**13.7 % del mercado ferretero nacional está fuera del catálogo**, no «dos tercios de los
municipios».

Corrección nacida de la objeción del Escéptico (§6) y **afinada por el gate de
`data-analyst`**, que señaló el non-sequitur de la redacción original.

---

## 5. Los tres umbrales, medidos

| Umbral | Ciudades | Añade sobre las 589 | Masa ferretera cubierta | Masa **fuera** | Ciudad más pequeña que entra |
|---|---:|---:|---:|---:|---|
| **≥20** (vigente) | 589 | — | 86.3 % | **13.7 %** | Asientos (20) |
| **≥10** | 995 | +406 | 93.6 % | **6.4 %** | Seybaplaya (10) |
| **≥5** | 1,440 | +851 | 97.6 % | **2.4 %** | San José de Gracia (5) |
| *(≥1, referencia)* | *2,227* | *+1,638* | *100 %* | *0 %* | *Abasolo (1)* |

### 5.1 Cobertura de **masa ferretera** por región y umbral

| Región | ≥20 | ≥10 | ≥5 |
|---|---:|---:|---:|
| Valle de México | 97.2 % | 99.3 % | 99.8 % |
| Noroeste | 92.4 % | 96.3 % | 98.7 % |
| Noreste | 91.0 % | 95.5 % | 97.6 % |
| Centro-Norte | 89.5 % | 96.2 % | 98.9 % |
| Occidente | 84.7 % | 94.3 % | 98.5 % |
| Península | 81.8 % | 89.6 % | 94.4 % |
| Centro-Sur | 79.3 % | 91.0 % | 97.3 % |
| **Sureste** | **65.6 %** | **80.4 %** | **91.6 %** |
| **Peor región ÷ mejor** | **1.48×** | **1.24×** | **1.09×** |

### 5.2 Los excluidos más grandes de cada región

Ninguno llega a 20. Esto confirma que el umbral vigente **no está dejando fuera ninguna plaza
grande** — el recorte es limpio en ese sentido:

| Región | Los 5 excluidos con más ferreterías |
|---|---|
| Centro-Norte | Villa de Ramos (19) · Cerritos (19) · Villa de Arista (18) · Tamasopo (18) · Cárdenas (18) |
| Centro-Sur | Yehualtepec (19) · Tochtepec (19) · Puente de Ixtla (19) · Huitzilac (19) · San Agustín Tlaxiaca (19) |
| Noreste | Meoqui (19) · Jiménez (19) · Parras (19) · Arteaga (19) · Cuencamé (18) |
| Noroeste | Etchojoa (17) · Elota (17) · Magdalena (16) · Jala (15) · Eldorado (14) |
| Occidente | Pajacuarán (19) · Zapotiltic (19) · Tomatlán (19) · Turicato (18) · El Grullo (18) |
| Península | Hunucmá (17) · José María Morelos (17) · Oxkutzcab (16) · Calakmul (14) · Bacalar (13) |
| Sureste | Nanchital (19) · San Pablo Huixtepec (19) · Pijijiapan (19) · Soteapan (18) · Misantla (18) |
| Valle de México | Ixtapan de la Sal (19) · Axapusco (19) · San Martín de las Pirámides (18) · Nopaltepec (18) · Morelos (18) |

⚠️ **Matiz que hay que decir:** que el excluido más grande tenga 19 **no es un argumento a
favor de ≥20**. Todo umbral tiene, por definición, brecha cero contra sí mismo; el excluido
más grande siempre estará justo debajo del corte. Lo que sí dice el dato es que el corte
**parte una distribución continua**, no una frontera natural del mercado.

---

## 6. Consejo de cuatro voces sobre el umbral

Convocado porque los tres umbrales tienen defensores legítimos y el tradeoff es real.

**Arquitecto (posición inicial, formada antes de leer a los demás):** ≥5 — el requisito nuevo
es completitud regional y el riesgo de ceros está empíricamente descartado.

**Escéptico:** ≥5, pero el umbral es la variable equivocada: debería ser un filtro por
defecto de la UI, no una frontera dura del catálogo.
*Y demolió el 4.4 %: cuenta municipios, no mercado. La métrica honesta es masa.*

**Pragmático:** **≥10** — la unidad económica es la corrida (~80 llamadas facturables), no el
catálogo. Un municipio de 10+ justifica esas llamadas; uno de 5 devuelve media corrida.

**Crítico:** **≥10**, y solo si antes se verifica la desambiguación de nombres. ≥5 compra
4 puntos de cobertura pagando 445 ciudades que el sistema no puede cosechar.

### 6.1 Veredicto

- **Consenso:** los cuatro coinciden en que **≥20 se queda corto** y en que el objetivo
  «400-600 ciudades» de la decisión D3 **está obsoleto**: se dimensionó antes del requisito
  nuevo del dueño y para una UI que el Plan 4 está reemplazando.
- **Disenso más fuerte:** el Escéptico sostiene que ningún umbral duro es la respuesta
  correcta, y que el corte pertenece a la capa de presentación.
- **Revisión de premisa:** sí. El Escéptico invalidó la métrica con la que yo estaba
  argumentando (municipios en vez de masa). El documento se corrigió (§4.2).
- **Cambio de recomendación, declarado:** **mi posición inicial era ≥5 y la cambio a ≥10.**
  Dos voces independientes convergieron en el mismo argumento económico que yo había
  subestimado: *el costo por corrida es fijo (~80 llamadas) sin importar el tamaño de la
  ciudad*. Tras los filtros del importador (≥5 reseñas, ≥3.5 estrellas, con teléfono), un
  municipio de 5 ferreterías entrega del orden de 0-2 prospectos. Yo trataba el tamaño del
  catálogo como gratis: lo es en pesos, **no** en confianza del operador.

---

## 7. RECOMENDACIÓN: bajar el umbral de ≥20 a **≥10**

**Catálogo resultante: ~995 municipios por umbral + los heredados** (hoy 17, algunos de los
cuales quedarán absorbidos por el nuevo corte).

### 7.1 Por qué ≥10 y no ≥20

| Efecto | ≥20 → ≥10 |
|---|---|
| Masa ferretera nacional fuera del catálogo | **13.7 % → 6.4 %** (se recupera más de la mitad) |
| Sureste, la región peor cubierta | **65.6 % → 80.4 %** de su masa |
| Desequilibrio regional (peor ÷ mejor, por masa) | **1.48× → 1.24×** |
| Ciudades añadidas | +406 |

### 7.2 Por qué ≥10 y no ≥5

| Efecto | ≥10 → ≥5 |
|---|---|
| Masa ferretera adicional recuperada | solo **+4.0 puntos** (6.4 % → 2.4 %) |
| Ciudades añadidas para conseguirlo | **+445** |
| Rendimiento esperado de esas 445 | un municipio de 5-9 ferreterías, tras los filtros del importador, entrega del orden de **0-2 prospectos** por corrida que cuesta lo mismo que una de Monterrey |

**El hecho medido:** el costo marginal por punto de cobertura **se duplica**. Los primeros
7.3 puntos cuestan 406 ciudades (**55.6 ciudades por punto**); los siguientes 4.0 cuestan
445 (**111.3 ciudades por punto**).

**El juicio de negocio, declarado como tal:** que ese segundo tramo «no se paga». Los datos
dicen *cuesta el doble*; **no** dicen *deja de valer*. Afirmar lo segundo exige un modelo de
margen por prospecto y de costo fijo por ciudad que **este proyecto todavía no tiene** — lo
construye el **Plan 2**, que es quien mira costo por prospecto. Hasta entonces, la
recomendación de ≥10 se apoya en el hecho (el costo se duplica) más el argumento operativo
del consejo (un municipio de 5-9 ferreterías rinde 0-2 prospectos tras los filtros), y se
marca como **revisable cuando el Plan 2 entregue el modelo de costo**.

Distinción exigida por el gate de `data-analyst`.

### 7.3 Lo que NO cambia

- **El modelo de puntuación no se toca** (decisión cerrada, ADR `2026-08-28`).
- **Los 17 heredados se conservan** — su lógica es correcta y no depende del umbral.
- **Bajar el umbral es un parámetro**, `minimo_ferreterias` (`tools/generar_catalogo_ciudades.py:391-393`). Es reversible en una línea.

---

## 8. Riesgo CE3: medido, no supuesto

CE3 exige que **ninguna ciudad quede en 0** y que el mínimo supere 5 puntos. El riesgo era que
al bajar el umbral entraran municipios diminutos y la normalización logarítmica los aplastara
contra el cero.

**El catálogo ya contiene el experimento natural.** Los 17 heredados incluyen municipios muy
por debajo de cualquier umbral propuesto:

| Ferreterías | Municipio | `potencial_mercado` |
|---:|---|---:|
| **1** | Ejutla | **14.1** |
| 3 | San Nicolás | 14.7 |
| 4 | Juchitán | 25.7 |
| 4 | Tlalnepantla | 24.3 |
| **5** | Miahuatlán | **23.1** |

**El mínimo de todo el catálogo es 14.1 — el de un municipio con UNA ferretería.** Está
**2.8× por encima** del piso de 5 que exige CE3. Un corte en ≥10 entra muy por encima de ese
caso, así que **CE3 no corre peligro**. Aun así, T1.3 lo verifica con test, no con este
argumento.

⚠️ **Lo que esta evidencia NO prueba** (objeción del Escéptico, aceptada): que no haya ceros
**no** demuestra que el *orden* de las 406 ciudades nuevas sea correcto. El modelo se calibró
en un mundo de ≥20. Queda anotado como material de verificación para **T1.4**.

---

## 9. Condiciones que acompañan a la recomendación

Tres, salidas del consejo. No son opcionales:

1. **Desambiguación de nombres antes de ampliar** (Crítico). Los homónimos municipales
   —`Benito Juárez`, `Hidalgo`, `Juárez`, `Zaragoza`, `Morelos`— abundan entre los municipios
   chicos, y el nombre viaja literalmente a la consulta de Places. El fallo ya ocurrió antes.
   **T1.3 debe verificar que las 406 ciudades nuevas tienen nombre de búsqueda resuelto**, no
   solo que el catálogo creció. Es la decisión D-6 aplicada a la cola nueva.
2. **Esto sale con el rediseño de la UI, no antes** (Pragmático). 995 chips sin búsqueda ni
   filtro por estado es peor que 606. El Plan 4 entrega ese filtro, y el orden de ejecución
   de la tanda (**1 → 4**) ya lo contempla: el catálogo ampliado llega a producción junto con
   la UI que lo hace usable.
3. **Medir los 17 heredados** (sorpresa del Escéptico). Son un experimento natural que nadie
   ha leído: ¿alguna vez se eligió una de esas ciudades, y qué rindió? El dato responde
   empíricamente la pregunta del umbral y **vale más que este debate**. No bloquea T1.3;
   se propone como insumo del **Plan 2**, que es el que mira costo por prospecto.

---

## 10. Qué entrega esta tarea a T1.3

- **T1.3 NO se salta.** La brecha no es cero en términos del requisito del dueño: **13.7 % de
  la masa ferretera nacional queda fuera**, y el Sureste está al 65.6 %.
- **Cambio a aplicar:** `minimo_ferreterias` de **20** a **10** en el generador, regenerar y
  anexar al ADR (sección «Revisión 2026-09-15», **anexo, no reescritura**).
- **Test RED que debe fallar antes del cambio:** *«ninguna macro-región cubre menos del 75 %
  de la masa ferretera de su región»*. Hoy el Sureste da **65.6 %** → **falla**. Con ≥10 da
  **80.4 %** → pasa.
  ⚠️ **Se declara el sesgo:** el 75 % **se eligió después de ver los datos**, sabiendo que
  deja fuera al ≥20 y dentro al ≥10. Eso es ajuste retrospectivo y el gate de `data-analyst`
  lo marcó. **No se disimula y no se cambia el número, se cambia su justificación:** el 75 %
  no se defiende como hallazgo estadístico sino como **compromiso de servicio** — si la
  promesa al dueño es «cobertura nacional», dejar fuera más de una cuarta parte del mercado
  de una región rompe esa promesa, y un 20-25 % es un tradeoff que sí se puede sostener
  delante de él. Es un umbral **normativo**, no derivado. Cualquiera puede discutirlo; lo que
  no puede es creer que salió del dato.
- **Verificar además:** CE3 (mínimo > 5) y la condición 1 de §9 (nombres resueltos en las
  ciudades nuevas).
- **Número objetivo:** ~995 municipios por umbral, más los heredados que queden por debajo.

---

## 11. Decisión D4, resuelta

El índice deja abierta **D4 — umbral de cobertura del catálogo**, con la opción **A** («que
T1.2 lo decida con datos») como recomendada. **Esta tarea la ejerce:**

> **D4 → ≥10 ferreterías.** No es la opción B del índice (`≥5`, máxima cobertura) ni la C
> (`≥20`, sin cambios). El dato que decide: los primeros 7.3 puntos de cobertura cuestan 406
> ciudades y los siguientes 4.0 cuestan 445.

El owner puede revocarlo; es un parámetro de una línea. Queda listado entre las dudas del
cierre del Plan 1.


---

## 12. Gate de verificación: `data-analyst` (catalogo-agentes)

La tabla de gates de T1.2 exige que `data-analyst` revise la distribución. Se ejecutó sobre
las afirmaciones A-D de este documento. **Veredicto: ≥10 recomendable, sostenido por hechos.**
Tres objeciones, **las tres aceptadas y aplicadas al documento**:

| # | Objeción | Dónde se corrigió |
|---|---|---|
| 1 | *«No hay métrica honesta y otra engañosa: son dos preguntas distintas. Invalidar una con la otra es un non-sequitur»* | **§4.2 reescrita** — ahora reporta ambas y explica qué responde cada una |
| 2 | *«"Muere la utilidad marginal" es especulativo sin modelo de negocio. Los datos dicen que cuesta el doble; no dicen que deje de valer»* | **§7.2 reescrita** — hecho y juicio separados, y el juicio queda marcado como revisable cuando el Plan 2 entregue el modelo de costo |
| 3 | *«El test del 75 % se diseñó después de ver los datos para que ≥10 pasara y ≥20 fallara: ajuste retrospectivo»* | **§10** — el sesgo se declara; el 75 % se re-justifica como umbral normativo de servicio, no como hallazgo del dato |

Confirmó como **correctas** las afirmaciones B (la tautología del umbral) y la aritmética de
A, C y D (62.4/14.4 = 4.33× · 97.2/65.6 = 1.48× · 55.6 vs 111.3 ciudades por punto).

**Métricas que el gate echó en falta**, anotadas para quien siga (no bloquean T1.3):
distribución de ferreterías por tramo de tamaño municipal; modelo de costo fijo por ciudad
contra ingreso por llamada (**Plan 2**); y si el Sureste es un mercado distinto en poder
adquisitivo, no solo más fragmentado.
