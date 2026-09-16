# VERIFICACIÓN DEL ORDEN NACIONAL Y DEL FILTRO POR REGIÓN

**Tarea:** Plan 1 · T1.4 · **Fecha:** 2026-09-15 · **Rama:** `feat/relevancia-nacional-produccion`
**Pregunta que responde:** el modelo puede ser correcto en el código y absurdo en la lista.
¿Lo es? ¿Y el filtro por región lista **todas** las ciudades de su región?

**Regla que gobierna este documento:** todo lo que aquí se afirma o está en un test
automatizado, o va con el comando que lo produjo. La única excepción declarada es CE4, que es
un juicio humano y por eso es un gate del owner, no una medición.

---

## 1. La respuesta, en una línea

> **CE2 y CE3 quedan verdes y automatizados.** Y la verificación encontró algo que nadie
> buscaba: **el endpoint no desempataba como manda el ADR**. Servía la lista con 100
> posiciones distintas de las del catálogo, en 103 empates exactos que involucran 232
> ciudades. No era aleatorio —por eso llevaba invisible desde agosto— pero tampoco era lo
> decidido. **Corregido.** Y **CE4 quedó APROBADO por el owner**: los cuatro criterios de
> la tarea están cerrados.

---

## 2. Qué se verificó y con qué

| Criterio | Qué exige | Cómo se comprobó | Estado |
|---|---|---|---|
| **CE2** | Cada macro-región lista **todas** sus ciudades del catálogo | `tests/test_ce2_filtro_por_region.py` — 28 tests, 8 regiones parametrizadas | ✅ |
| **CE3** | Una ciudad sin historial de NIOVAL **no** puntúa 0; mínimo > 5 | `tests/test_ce2_filtro_por_region.py` + `tests/test_catalogo_ciudades.py` | ✅ |
| **Orden** | El listado servido == el orden canónico del ADR | `tests/test_orden_nacional.py` — 6 tests | ✅ *(tras corregir)* |
| **CE4** | El top-10 nacional es defendible ante el dueño | §7 y §8 de este documento | ✅ **APROBADO** por el owner, 2026-09-15 |

**Suite completa: 525 passed, 1 skipped.** Baseline de la rama al empezar T1.4: 491.

---

## 3. CE2 — el filtro por región, medido en los tres eslabones

Un test que sólo mire el endpoint da verde con un `renderChips` que corte a 100 chips. Uno que
sólo mire el JSON da verde aunque el endpoint trunque. Por eso el contraste va por los tres:

```
datos/ciudades_mx.json  →  /api/importador/ciudades  →  filtrarCiudades()
   la verdad del              lo que el servidor           lo que el
   catálogo                   entrega                      navegador muestra
```

### 3.1 Resultado, región por región

| Región | Ciudades en el catálogo | Las que entrega el endpoint | Las que lista el filtro | Lo que anuncia el desplegable |
|---|---:|---:|---:|---:|
| Centro-Sur | 227 | 227 | 227 | 227 |
| Sureste | 213 | 213 | 213 | 213 |
| Occidente | 145 | 145 | 145 | 145 |
| Valle de México | 115 | 115 | 115 | 115 |
| Centro-Norte | 112 | 112 | 112 | 112 |
| Noreste | 95 | 95 | 95 | 95 |
| Noroeste | 57 | 57 | 57 | 57 |
| Península | 40 | 40 | 40 | 40 |
| **Suma** | **1,004** | **1,004** | **1,004** | **1,004** |

La cuarta columna no es redundante: el desplegable dice «Sureste (213)», y ese número es lo
único que distingue *una región vacía* de *un filtro roto*. Si anunciara 213 y listara 180,
nadie se enteraría.

### 3.2 Por qué el filtro del JS se prueba replicando su predicado

El JavaScript vive embebido en `app.py` (la extracción a `templates/`+`static/` es el PR #43,
sin mergear) y la suite no tiene navegador. El test replica el predicado real
—`lista.filter(c => c.region === region)`, igualdad exacta de cadena— sobre la carga útil
**real** del endpoint, y **un test aparte fija que el predicado del JS sigue siendo ése**. Si
alguien lo cambia a `includes` o a comparar normalizado, ese test rompe y avisa de que la
réplica dejó de representar al original.

### 3.3 Verificación en la dirección contraria

La regla del entorno manda comprobar que el barrido encuentra un positivo conocido antes de
creerle un cero. Se insertó un recorte a propósito en dos sitios:

```python
ciudades = ciudades[:200]        # en el endpoint
lista = lista.slice(0, 100);     // en renderChips
```

**Fallaron 12 tests**, incluidas **las 8 regiones por separado** y el test del `renderChips`.
`app.py` quedó restaurado con `git checkout --` y la suite volvió a verde. Estos tests
detectan un recorte real; su verde significa algo.

---

## 4. El hallazgo: el desempate no era el del ADR

### 4.1 Qué se encontró

Con la hoja vacía todos los `factor_nioval` valen 1.00, así que la prioridad **es** el
potencial y los dos órdenes tendrían que coincidir. No coincidían:

| Medición | Valor |
|---|---:|
| Posiciones distintas entre el catálogo y lo que sirve el endpoint | **100** de 1,004 |
| Desplazamiento máximo | **4** puestos |
| Grupos en empate exacto (mismo potencial **y** mismas ferreterías) | **103** |
| Ciudades implicadas | **232** |

### 4.2 La causa

Las dos ordenaciones coincidían en las dos primeras claves y divergían en la tercera:

| | Desempate final |
|---|---|
| **ADR §7** (la decisión) | ascendente por **clave INEGI** |
| `tools/generar_catalogo_ciudades.py` | ascendente por **clave INEGI** ✅ |
| `app.py::api_importador_ciudades` | ascendente por **nombre** ❌ |

El comentario del propio endpoint decía *«Desempate del ADR: prioridad, luego ferreterias,
luego nombre»* — **citaba mal al ADR**, que dice clave INEGI. Ejemplo real:

```
potencial 54.6, 58 ferreterías:
  catálogo : Sahuayo (16076) · Puerto Escondido (20318)
  endpoint : Puerto Escondido · Sahuayo
```

### 4.3 Por qué llevaba invisible desde agosto

**Ninguno de los dos órdenes era aleatorio.** Esto *no* era un fallo de reproducibilidad: dos
peticiones daban siempre el mismo resultado, y por eso ningún test de determinismo podía
verlo. Era una divergencia entre una decisión cerrada y el código.

Y con 606 ciudades apenas se notaba. Con las 1,004 de T1.3 los empates se multiplican, porque
el potencial se redondea a un decimal y hay muchas más ciudades compartiendo tramo.

### 4.4 Cómo se resolvió, y por qué a favor del ADR

Se alineó el código con la decisión, no al revés: el ADR es una **decisión cerrada** y
reabrirla necesitaría dato nuevo. Además la clave INEGI es la mejor de las dos por mérito
propio: **es estable y el nombre no** — hoy «Juárez, Chihuahua», mañana lo que decida la
desambiguación de nombres.

La corrección respeta la otra decisión que toca aquí: **el endpoint sigue sin publicar la
clave INEGI**. Se lleva al lado durante la ordenación y no entra en la respuesta
(`tests/test_importador_ciudades.py:216` lo sigue exigiendo, y hay un test nuevo que lo
reafirma después del cambio).

### 4.5 Impacto real, dicho sin inflarlo

Máximo 4 puestos, y sólo entre ciudades con **idéntico** potencial e **idénticas**
ferreterías. Para el operador es invisible. **El valor de arreglarlo no es el orden: es que el
archivo del catálogo y la lista servida vuelvan a ser la misma lista**, que es lo que permite
depurar el ranking mirando el JSON. Un `diff` entre ambos vuelve a significar «algo cambió».

---

## 5. CE3 — verde por los dos extremos

| Dónde | Qué se comprueba | Valor |
|---|---|---:|
| Catálogo | `min(potencial_mercado)` | **14.1** (Ejutla, 1 ferretería) |
| Salida del endpoint | `min(potencial_mercado)` servido | **14.1** |
| Salida del endpoint | `min(prioridad)` = potencial × factor | **14.1** *(factores neutros)* |
| Ninguna prioridad en 0 | el empate arbitrario que el Plan 1 vino a quitar | **0 ceros** |

El caso peor imaginable es la ciudad más chica con el factor en su suelo (`FACTOR_MIN = 0.60`,
`app.py:943`): 14.1 × 0.60 = **8.46**, todavía por encima del piso de 5. El test lo comprueba
sobre el dato servido, no sobre esa cuenta.

---

## 6. Gate `silent-failure-hunter`: la sospecha del plan, desmentida con evidencia

El plan asignaba este gate por una razón concreta:

> *«`cargarCiudades()` tiene un `catch` que cae a la lista estática: un fallo silencioso ahí
> haría que CE2 pase en test y falle en vivo.»*

**Desmentida para el código actual**, y no leyendo el comentario que lo dice: se comprobó que
`CIUDADES_MX` no existe en ningún camino ejecutable, que el commit `01ea2b0` lo retiró
(`git log -S`), y que no hay un `static/` paralelo con una copia vieja del JS.

Las tres defensas que el plan temía que faltaran ya están:

- `app.py:5987` valida `Array.isArray(d.ciudades)` — cierra el caso «200 con JSON válido pero
  forma inesperada», que es el más silencioso de los tres.
- La bandera `catalogo_cargado` distingue «el servidor no pudo leer el archivo» de «no hay
  resultados».
- `renderChips` y `filtrarCiudades` no tienen `.slice(` ni límite.

**Anotado, no bloqueante:** `_estado_catalogo` (`app.py:895-897`) es una caché de proceso que
se fija en la primera llamada y no se invalida. Si esa primera lectura fallara de forma
transitoria, el proceso serviría `catalogo_cargado: false` hasta el siguiente reinicio. **No
es silencioso** —el banner rojo sigue saliendo— pero es un falso positivo persistente. Queda
como insumo del Plan 3.

---

## 7. CE4 — el material del gate del owner

**Esto no es una medición: es un juicio de negocio, y por eso se pregunta.**

Dos avisos antes de leer las tablas, para que la pregunta sea honesta:

1. **El orden que se muestra es el exógeno** (`potencial_mercado`), el que sale del DENUE y el
   Censo sin mirar el historial de NIOVAL. En producción el operador ve
   `prioridad = potencial × factor_nioval`, y ese factor sube o baja según lo ya trabajado en
   la hoja. La cabeza del ranking se mueve poco; la cola sí se reordena.
2. **Bajar el corte a ≥10 en T1.3 no movió la cabeza.** La ciudad **nueva** mejor rankeada de
   todo el país es Jalpa de Méndez, en el puesto **#434**. Las 398 nuevas entran de la mitad
   de la tabla hacia abajo. Lo que el dueño juzgue del top-30 juzga el **modelo**, no el
   cambio de umbral.

### 7.1 Lo más probable que salte a la vista

Ocho de las treinta primeras son del Valle de México, y varias son **alcaldías de la CDMX o
municipios conurbados**, no ciudades: Iztapalapa, Gustavo A. Madero, Cuauhtémoc,
Nezahualcóyotl, Ecatepec, Tlalnepantla de Baz, Naucalpan.

**Es una decisión tomada, no un descuido:** el ADR §5.1 resolvió **no fusionar la Zona
Metropolitana del Valle de México en el dato**, porque el importador consulta Places por
nombre y «Ferreterías en Iztapalapa» es una consulta que funciona, mientras que «Ferreterías
en Zona Metropolitana del Valle de México» no lo es. Si al dueño le estorba, el arreglo es de
presentación —agrupar en la UI— y es materia del **Plan 4**, no del modelo.

### 7.2 Top-30 nacional

| # | Ciudad | Estado | Región | Potencial | Ferreterías | Mayoreo | Constructoras | Población |
|---:|---|---|---|---:|---:|---:|---:|---:|
| 1 | **Puebla** | Puebla | Centro-Sur | **90.7** | 1,357 | 784 | 641 | 1,692,181 |
| 2 | **Guadalajara** | Jalisco | Occidente | **90.2** | 1,119 | 885 | 663 | 1,385,629 |
| 3 | **León** | Guanajuato | Centro-Norte | **89.0** | 1,137 | 810 | 398 | 1,721,215 |
| 4 | **Monterrey** | Nuevo León | Noreste | **88.7** | 764 | 871 | 864 | 1,142,994 |
| 5 | **Ecatepec de Morelos** | México | Valle de Mexico | **87.8** | 1,478 | 581 | 107 | 1,645,352 |
| 6 | **Mérida** | Yucatán | Peninsula | **87.3** | 757 | 606 | 777 | 995,129 |
| 7 | **Iztapalapa** | Ciudad de México | Valle de Mexico | **86.9** | 1,255 | 561 | 128 | 1,835,486 |
| 8 | **Querétaro** | Querétaro | Centro-Norte | **86.0** | 824 | 650 | 442 | 1,049,777 |
| 9 | **Zapopan** | Jalisco | Occidente | **85.4** | 788 | 576 | 406 | 1,476,491 |
| 10 | **Cuauhtémoc, Ciudad de México** | Ciudad de México | Valle de Mexico | **85.0** | 887 | 632 | 226 | 545,884 |
| 11 | **Tijuana** | Baja California | Noroeste | **84.6** | 644 | 459 | 420 | 1,922,523 |
| 12 | **Chihuahua** | Chihuahua | Noreste | **84.4** | 651 | 432 | 433 | 937,674 |
| 13 | **Aguascalientes** | Aguascalientes | Centro-Norte | **83.5** | 642 | 418 | 424 | 948,990 |
| 14 | **Toluca** | México | Valle de Mexico | **83.2** | 824 | 360 | 186 | 910,608 |
| 15 | **Gustavo A. Madero** | Ciudad de México | Valle de Mexico | **82.8** | 872 | 377 | 123 | 1,173,351 |
| 16 | **Morelia** | Michoacán de Ocampo | Occidente | **82.5** | 676 | 404 | 292 | 849,053 |
| 17 | **Hermosillo** | Sonora | Noroeste | **81.9** | 424 | 381 | 630 | 936,263 |
| 18 | **Nezahualcóyotl** | México | Valle de Mexico | **81.3** | 840 | 382 | 57 | 1,077,208 |
| 19 | **Juárez, Chihuahua** | Chihuahua | Noreste | **81.2** | 574 | 311 | 236 | 1,512,450 |
| 20 | **San Luis Potosí** | San Luis Potosí | Centro-Norte | **81.2** | 502 | 405 | 448 | 911,908 |
| 21 | **Torreón** | Coahuila de Zaragoza | Noreste | **81.0** | 519 | 284 | 350 | 720,848 |
| 22 | **Culiacán** | Sinaloa | Noroeste | **81.0** | 394 | 391 | 403 | 1,003,530 |
| 23 | **Saltillo** | Coahuila de Zaragoza | Noreste | **79.0** | 459 | 247 | 263 | 879,958 |
| 24 | **Tlalnepantla de Baz** | México | Valle de Mexico | **78.7** | 459 | 312 | 135 | 672,202 |
| 25 | **Tuxtla Gutiérrez** | Chiapas | Sureste | **78.7** | 386 | 332 | 388 | 604,147 |
| 26 | **Mexicali** | Baja California | Noroeste | **78.6** | 369 | 322 | 287 | 1,049,792 |
| 27 | **Naucalpan de Juárez** | México | Valle de Mexico | **78.5** | 524 | 242 | 126 | 834,434 |
| 28 | **Cancún** | Quintana Roo | Peninsula | **78.4** | 449 | 249 | 165 | 911,503 |
| 29 | **Veracruz** | Veracruz de Ignacio de la Llave | Sureste | **77.4** | 415 | 244 | 189 | 607,209 |
| 30 | **Durango** | Durango | Noreste | **77.3** | 360 | 212 | 317 | 688,697 |

### 7.3 Top-10 de cada región

### Centro-Sur — 227 ciudades · 10,744 ferreterías

| # | Ciudad | Estado | Potencial | Ferreterías |
|---:|---|---|---:|---:|
| 1 | Puebla | Puebla | 90.7 | 1,357 |
| 2 | Acapulco | Guerrero | 77.0 | 391 |
| 3 | Pachuca de Soto | Hidalgo | 74.0 | 324 |
| 4 | Cuernavaca | Morelos | 72.5 | 308 |
| 5 | Chilpancingo | Guerrero | 70.7 | 273 |
| 6 | Tehuacán | Puebla | 70.5 | 239 |
| 7 | Jiutepec | Morelos | 65.8 | 185 |
| 8 | Mineral de la Reforma | Hidalgo | 65.7 | 179 |
| 9 | Tulancingo de Bravo | Hidalgo | 65.5 | 196 |
| 10 | Cholula | Puebla | 65.3 | 177 |

La última de la región: **San Nicolás** (Guerrero), potencial 14.7, 3 ferreterías.

### Sureste — 213 ciudades · 7,707 ferreterías

| # | Ciudad | Estado | Potencial | Ferreterías |
|---:|---|---|---:|---:|
| 1 | Tuxtla Gutiérrez | Chiapas | 78.7 | 386 |
| 2 | Veracruz | Veracruz de Ignacio de la Llave | 77.4 | 415 |
| 3 | Villahermosa | Tabasco | 76.4 | 257 |
| 4 | Oaxaca de Juárez | Oaxaca | 74.3 | 281 |
| 5 | Xalapa | Veracruz de Ignacio de la Llave | 73.5 | 263 |
| 6 | Coatzacoalcos | Veracruz de Ignacio de la Llave | 69.7 | 198 |
| 7 | Tapachula | Chiapas | 67.2 | 154 |
| 8 | San Cristóbal de las Casas | Chiapas | 65.0 | 154 |
| 9 | Córdoba | Veracruz de Ignacio de la Llave | 64.8 | 152 |
| 10 | Comitán | Chiapas | 63.8 | 152 |

La última de la región: **Miahuatlán** (Veracruz de Ignacio de la Llave), potencial 23.1, 5 ferreterías.

### Occidente — 145 ciudades · 8,397 ferreterías

| # | Ciudad | Estado | Potencial | Ferreterías |
|---:|---|---|---:|---:|
| 1 | Guadalajara | Jalisco | 90.2 | 1,119 |
| 2 | Zapopan | Jalisco | 85.4 | 788 |
| 3 | Morelia | Michoacán de Ocampo | 82.5 | 676 |
| 4 | San Pedro Tlaquepaque | Jalisco | 76.3 | 413 |
| 5 | Tlajomulco de Zúñiga | Jalisco | 71.5 | 304 |
| 6 | Tonalá, Jalisco | Jalisco | 71.3 | 335 |
| 7 | Uruapan | Michoacán de Ocampo | 71.0 | 267 |
| 8 | Puerto Vallarta | Jalisco | 67.3 | 190 |
| 9 | Colima | Colima | 65.2 | 100 |
| 10 | Zamora | Michoacán de Ocampo | 64.6 | 152 |

La última de la región: **Ejutla** (Jalisco), potencial 14.1, 1 ferreterías.

### Valle de Mexico — 115 ciudades · 18,811 ferreterías

| # | Ciudad | Estado | Potencial | Ferreterías |
|---:|---|---|---:|---:|
| 1 | Ecatepec de Morelos | México | 87.8 | 1,478 |
| 2 | Iztapalapa | Ciudad de México | 86.9 | 1,255 |
| 3 | Cuauhtémoc, Ciudad de México | Ciudad de México | 85.0 | 887 |
| 4 | Toluca | México | 83.2 | 824 |
| 5 | Gustavo A. Madero | Ciudad de México | 82.8 | 872 |
| 6 | Nezahualcóyotl | México | 81.3 | 840 |
| 7 | Tlalnepantla de Baz | México | 78.7 | 459 |
| 8 | Naucalpan de Juárez | México | 78.5 | 524 |
| 9 | Chimalhuacán | México | 76.5 | 672 |
| 10 | Tlalpan | Ciudad de México | 74.6 | 394 |

La última de la región: **Temamatla** (México), potencial 31.5, 11 ferreterías.

### Centro-Norte — 112 ciudades · 8,321 ferreterías

| # | Ciudad | Estado | Potencial | Ferreterías |
|---:|---|---|---:|---:|
| 1 | León | Guanajuato | 89.0 | 1,137 |
| 2 | Querétaro | Querétaro | 86.0 | 824 |
| 3 | Aguascalientes | Aguascalientes | 83.5 | 642 |
| 4 | San Luis Potosí | San Luis Potosí | 81.2 | 502 |
| 5 | Irapuato | Guanajuato | 74.9 | 358 |
| 6 | Celaya | Guanajuato | 72.8 | 274 |
| 7 | San Juan del Río, Querétaro | Querétaro | 68.7 | 211 |
| 8 | Soledad de Graciano Sánchez | San Luis Potosí | 67.6 | 188 |
| 9 | Salamanca | Guanajuato | 65.6 | 148 |
| 10 | Corregidora | Querétaro | 65.0 | 138 |

La última de la región: **Pueblo Nuevo, Guanajuato** (Guanajuato), potencial 30.7, 11 ferreterías.

### Noreste — 95 ciudades · 9,190 ferreterías

| # | Ciudad | Estado | Potencial | Ferreterías |
|---:|---|---|---:|---:|
| 1 | Monterrey | Nuevo León | 88.7 | 764 |
| 2 | Chihuahua | Chihuahua | 84.4 | 651 |
| 3 | Juárez, Chihuahua | Chihuahua | 81.2 | 574 |
| 4 | Torreón | Coahuila de Zaragoza | 81.0 | 519 |
| 5 | Saltillo | Coahuila de Zaragoza | 79.0 | 459 |
| 6 | Durango | Durango | 77.3 | 360 |
| 7 | Guadalupe, Nuevo León | Nuevo León | 75.4 | 347 |
| 8 | Apodaca | Nuevo León | 75.2 | 304 |
| 9 | Reynosa | Tamaulipas | 74.4 | 373 |
| 10 | San Nicolás de los Garza | Nuevo León | 73.3 | 223 |

La última de la región: **Gustavo Díaz Ordaz** (Tamaulipas), potencial 31.3, 11 ferreterías.

### Noroeste — 57 ciudades · 5,150 ferreterías

| # | Ciudad | Estado | Potencial | Ferreterías |
|---:|---|---|---:|---:|
| 1 | Tijuana | Baja California | 84.6 | 644 |
| 2 | Hermosillo | Sonora | 81.9 | 424 |
| 3 | Culiacán | Sinaloa | 81.0 | 394 |
| 4 | Mexicali | Baja California | 78.6 | 369 |
| 5 | Mazatlán | Sinaloa | 73.4 | 249 |
| 6 | Tepic | Nayarit | 73.2 | 305 |
| 7 | Cabo San Lucas | Baja California Sur | 72.5 | 230 |
| 8 | Ciudad Obregón | Sonora | 71.9 | 233 |
| 9 | Los Mochis | Sinaloa | 71.6 | 202 |
| 10 | Ensenada | Baja California | 71.3 | 200 |

La última de la región: **Juan José Ríos** (Sinaloa), potencial 25.7, 11 ferreterías.

### Peninsula — 40 ciudades · 2,611 ferreterías

| # | Ciudad | Estado | Potencial | Ferreterías |
|---:|---|---|---:|---:|
| 1 | Mérida | Yucatán | 87.3 | 757 |
| 2 | Cancún | Quintana Roo | 78.4 | 449 |
| 3 | Campeche | Campeche | 66.7 | 119 |
| 4 | Ciudad del Carmen | Campeche | 66.6 | 152 |
| 5 | Playa del Carmen | Quintana Roo | 66.0 | 161 |
| 6 | Chetumal | Quintana Roo | 65.3 | 110 |
| 7 | Kanasín | Yucatán | 60.1 | 92 |
| 8 | Tulum | Quintana Roo | 52.5 | 51 |
| 9 | Valladolid | Yucatán | 52.2 | 41 |
| 10 | Progreso, Yucatán | Yucatán | 52.0 | 52 |

La última de la región: **Dzitbalché** (Campeche), potencial 26.0, 12 ferreterías.

---

## 8. La pregunta al dueño (CE4)

> Mirando el top-30 de §7.2: **¿reconoces esas plazas como las relevantes de tu ramo?**

Tres respuestas posibles, y lo que hace cada una:

| Respuesta | Qué pasa |
|---|---|
| **Aprobado** | CE4 verde, T1.4 cierra, se sigue a T1.5 (aterrizar el PR #42) |
| **Aprobado con reservas** | Las ciudades señaladas se anotan en el ADR como material para una revisión futura. **No se ajusta el modelo por casos sueltos: eso es sobreajuste**, y así lo manda el plan. T1.4 cierra igual |
| **Bloqueado** | Se vuelve al ADR y se reajustan los pesos. Es la única salida que reabre una decisión cerrada, y necesita el motivo por escrito |

### 8.1 Respuesta del owner — **APROBADO** (2026-09-15)

El dueño reconoce el top-30 como las plazas relevantes de su ramo. **Sin reservas y sin
ciudades señaladas**, así que no hay nada que anotar en el ADR para una revisión futura.

Lo que esto cierra y lo que NO cierra:

- **Cierra:** CE4, y con él T1.4 entera. El modelo de relevancia queda validado por el negocio,
  no sólo por los tests. Se puede seguir a T1.5 (aterrizar el PR #42).
- **NO cierra:** el juicio recae sobre el **orden exógeno del top-30**. No es una aprobación
  de la cola larga —las 398 ciudades nuevas empiezan en el puesto #434 y nadie las ha mirado
  una por una—, ni del orden final en producción, donde `factor_nioval` reordena según lo ya
  trabajado en la hoja. Decirlo ahora evita que dentro de tres meses esta aprobación se cite
  como algo más amplio de lo que fue.
- **Sigue en pie** lo del ADR §8: si un día el dueño deja de reconocer el top, el ADR se
  enmienda, no se sustituye en silencio.

⚠️ **Lo dice el plan y se respeta:** si el dueño señala *una* ciudad fuera de lugar, **no se
toca la fórmula**. Se registra. Cambiar un modelo calibrado sobre 2,227 municipios por un caso
suelto es sobreajuste, y el ADR §8 ya fija qué sí lo invalidaría.

---

### 8.2 Los cuatro gates de T1.4

| Gate | Veredicto | Qué aportó |
|---|---|---|
| `silent-failure-hunter` | Sin CRITICAL/HIGH | **Desmintió la sospecha del plan** con `git log -S`: el fallback a la lista estática ya no existe. Anotó la caché `_estado_catalogo` |
| `code-reviewer` | **APPROVE** | 0 CRITICAL / 0 HIGH / 0 MEDIUM. Verificó que la refactorización no pierde ni duplica ciudades y que la clave sigue sin viajar |
| `python-reviewer` (orden) | **Approve** | Validó mi agrupado contra `itertools.groupby` (0 discrepancias) y **revirtió el `sort` por su cuenta** para confirmar que el test detecta los 43 empates. 2 MEDIUM, ambos aplicados |
| `python-reviewer` (CE2) | Aprobado | 2 MEDIUM, ambos aplicados. El M-1 era real y valía la pena |

**El M-1 merece contarse**, porque era un falso verde de verdad: el guard que sostiene toda la
réplica del filtro buscaba `c.region === region` **en todo el recorte, comentarios incluidos**.
Alguien podía cambiar el predicado vivo y dejar el viejo de comentario, y los ocho tests de CE2
habrían seguido en verde midiendo un predicado que ya no existía. Ahora el recorte se limpia de
comentarios antes de buscar, y **se probó plantando exactamente ese engaño**: predicado cambiado
a `toLowerCase()` con `// ... c.region === region` debajo → el test falla.

### Nota sobre un flake que no lo era

El gate de `python-reviewer` reportó haber visto 2 fallos en `tests/test_orden_nacional.py` en
una corrida, sin poder reproducirlos en seis más, y sospechó de la caché global
`_estado_catalogo`.

**No era un flake: el gate corrió la suite durante la ventana RED de esta misma tarea**, entre
que se escribió el test del orden y se corrigió el endpoint. Los dos tests que vio fallar son
*exactamente* los dos que estaban en rojo a propósito en ese momento.

Comprobado, no supuesto: **4 corridas completas seguidas, 525 passed** cada una; los dos
archivos emparejados en **ambos órdenes** (34 passed) y `test_orden_nacional.py` en solitario
(6 passed). La caché `_estado_catalogo` sigue siendo una fragilidad preexistente de `app.py`
—queda anotada en §6— pero no produce este síntoma.

---

## 9. Qué entrega esta tarea a T1.5

- **CE2 y CE3 automatizados y verdes**, con prueba de mutación que demuestra que detectan un
  recorte real.
- **Un defecto de producción corregido** en `app.py`: el desempate ahora es el del ADR. Va en
  el diff nuevo que T1.5 tiene que pasar por `python-reviewer` y `code-reviewer`.
- **CE4 APROBADO por el owner** (§8.1), sin reservas. Ya no bloquea el merge del PR #42.
- **Recordatorio que no se puede perder:** 1,004 chips sin búsqueda ni filtro por estado son
  peores que 606. La condición 2 del consejo de T1.2 sigue en pie — **este catálogo llega a
  producción junto con la UI del Plan 4**, y el orden 1 → 4 de la tanda ya lo contempla.
