# VERIFICACIÓN INTEGRAL DEL PLAN 1

**Tarea:** T1.8 · **Fecha:** 2026-08-29 · **Rama:** `feat/relevancia-ciudades-nacional`
**Baseline:** `python -m pytest tests/` → **482 passed, 1 skipped** (en `main` eran 388 + 1)

---

## 1. Criterios de éxito

| # | Criterio | Estado | Evidencia |
|---|---|---|---|
| **CE1** | Cero duplicados en el catálogo | ✅ | `test_sin_duplicados_por_clave_inegi`. Medido: **0** nombres repetidos tras normalizar (sin acentos, minúsculas) |
| **CE2** | Cero sufijos desambiguadores en el nombre que va a Places | ✅ | `test_ningun_nombre_lleva_sufijo_desambiguador`. Encontró uno **en la propia fuente** (`Villa de Pozos SLP`, así lo publica el INEGI) y ahora se recorta |
| **CE3** | Toda ciudad tiene estado y macro-región | ✅ | `test_toda_ciudad_tiene_estado_y_region` + `test_las_regiones_son_las_ocho_declaradas` |
| **CE4** | Cobertura nacional (≥1 ciudad de las 32 entidades) | ✅ | `test_las_32_entidades_estan_representadas`. **32/32** |
| **CE5** | El top-20 nuevo difiere del actual en ≥8 posiciones | ✅ | **Difiere en 15 de 20** (§2), medido con la hoja de producción real |
| **CE6** | Ninguna ciudad virgen queda en 0 | ✅ | `test_todo_potencial_es_mayor_que_cero`. Potencial mínimo del catálogo: **14.1** |
| **CE7** | El desempeño ajusta pero no domina | ✅ | `test_el_desempeno_ajusta_pero_no_domina` + `test_una_llamada_al_100_pct_apenas_mueve_el_factor`. Comprobado en las dos direcciones (§4) |
| **CE8** | El dashboard no se rompe; los tests existentes siguen verdes sin modificarse | ⚠️ **matizado** | **No existía ni un test** de `/api/prospectos/ciudades`. Se escribieron 11 de caracterización *antes* de tocar nada. De esas 11, **una** cambió una línea, y por cambio deliberado de contrato (§3) |
| **CE9** | Baseline sin regresiones | ✅ | 388 → **482 passed**, 1 skipped. 94 tests nuevos, cero regresiones |
| **CE10** | El owner reconoce el top-20 | ⛔ **GATE DEL OWNER** | Material listo en §2. **No se puede cerrar desde una sesión de Claude** |

---

## 2. El cambio de ranking, con la hoja de producción real

Reproducido sobre el respaldo de `2026-08-28-plan1`: **7,145 contactos** y **4,434
respuestas** del formulario. Tasa de interés global de NIOVAL: **34.4 %**.

### 2.1 Lo que el operador ve HOY

| # | Ciudad | | # | Ciudad |
|---|---|---|---|---|
| 1 | Cd Guzmán | | 11 | Rosarito |
| 2 | Chilpancingo De Los Bravo | | 12 | **Morelos** |
| 3 | Tuxpan | | 13 | Mexicali |
| 4 | Victoria De Durango | | 14 | Torreón |
| 5 | **Guerrero** | | 15 | Escobedo |
| 6 | Guamúchil | | 16 | **Chiapas** |
| 7 | San Nicolás De Los Garza | | 17 | San Luis Río Colorado |
| 8 | Apodaca | | 18 | Cuernavaca |
| 9 | Hermosillo | | 19 | Chihuahua |
| 10 | Ensenada | | 20 | Zapopan |

**Tres de las veinte primeras posiciones son ESTADOS, no ciudades** — `Guerrero` (#5),
`Morelos` (#12), `Chiapas` (#16). Son valores escritos a mano en la columna CIUDAD que la
fórmula endógena premia porque acumulan muchos contactos. Y el #1 es **Ciudad Guzmán**, un
municipio con **56 ferreterías**, por delante de Guadalajara, que tiene 1,119.

### 2.2 Lo que verá con el cambio

| # | Ciudad | Región | Prioridad | Ferreterías | Contactos |
|---|---|---|---|---|---|
| 1 | Zapopan | Occidente | 90.7 | 788 | 33 |
| 2 | Hermosillo | Noroeste | 88.0 | 424 | 84 |
| 3 | Iztapalapa | Valle de México | 86.9 | 1,255 | 0 |
| 4 | Mexicali | Noroeste | 85.0 | 369 | 39 |
| 5 | Ecatepec de Morelos | Valle de México | 84.7 | 1,478 | 31 |
| 6 | Cuauhtémoc, Ciudad de México | Valle de México | 82.9 | 887 | 56 |
| 7 | Apodaca | Noreste | 82.9 | 304 | 38 |
| 8 | Gustavo A. Madero | Valle de México | 82.8 | 872 | 0 |
| 9 | Nezahualcóyotl | Valle de México | 81.3 | 840 | 0 |
| 10 | León | Centro-Norte | 80.6 | 1,137 | 150 |
| 11 | Aguascalientes | Centro-Norte | 79.7 | 642 | 159 |
| 12 | Tlalnepantla de Baz | Valle de México | 78.7 | 459 | 0 |
| 13 | Naucalpan de Juárez | Valle de México | 78.5 | 524 | 0 |
| 14 | Cancún | Península | 78.4 | 449 | 0 |
| 15 | Querétaro | Centro-Norte | 78.2 | 824 | 233 |
| 16 | Tuxtla Gutiérrez | Sureste | 78.2 | 386 | 5 |
| 17 | San Nicolás de los Garza | Noreste | 77.8 | 223 | 50 |
| 18 | Toluca | Valle de México | 77.4 | 824 | 116 |
| 19 | Morelia | Occidente | 76.9 | 676 | 136 |
| 20 | Chimalhuacán | Valle de México | 76.5 | 672 | 0 |

**CE5 cumplido: 15 de 20 posiciones cambian.** Los estados desaparecen del ranking (van al
aviso de "sin clasificar") y entran plazas con mercado medido.

### 2.3 ⚠️ Lo que el owner tiene que decidir, y no lo decide una fórmula

**Puebla, Guadalajara, Monterrey y Mérida NO están en el top-20**, y eso es deliberado:

| Ciudad | Potencial (mercado) | Contactos / ferreterías | Factor | Prioridad | Posición |
|---|---|---|---|---|---|
| Puebla | **90.7** (el #1 nacional) | 425 / 1,357 | 0.819 | 74.3 | **#33** |
| Guadalajara | 90.2 | 307 / 1,119 | 0.824 | 74.3 | **#34** |
| Monterrey | 88.7 | 278 / 764 | 0.786 | 69.7 | **#63** |
| Chihuahua | 84.4 | 448 / 651 | 0.724 | 61.1 | **#125** |
| Oaxaca de Juárez | 74.3 | 263 / 281 | 0.678 | 50.4 | **#289** |

Bajan **porque NIOVAL ya las cosechó**. Oaxaca tiene 263 contactos sobre 281 ferreterías
existentes: está prácticamente agotada, y una corrida nueva ahí gastaría en Places para
traer duplicados.

**Son dos preguntas distintas, y el ranking solo responde una:**

- *"¿Dónde está el mercado ferretero de México?"* → lo responde **`potencial_mercado`**, y
  ahí Puebla es #1, Guadalajara #2, León #3, Monterrey #4 (§2.4).
- *"¿A qué ciudad le dedico la próxima corrida?"* → lo responde **`prioridad`**, que es lo
  que ordena los chips, y ahí Puebla cae al #33 por estar a un tercio de agotarse.

El criterio CE10 está redactado como la primera pregunta (*"reconoce esas plazas como las
relevantes del ramo"*) pero el ranking ordena por la segunda. **Las dos listas están abajo
para que el owner juzgue con las dos delante.**

### 2.4 Top-20 por potencial de mercado puro (sin historial)

| # | Ciudad | Estado | Potencial | Ferreterías |
|---|---|---|---|---|
| 1 | Puebla | Puebla | 90.7 | 1,357 |
| 2 | Guadalajara | Jalisco | 90.2 | 1,119 |
| 3 | León | Guanajuato | 89.0 | 1,137 |
| 4 | Monterrey | Nuevo León | 88.7 | 764 |
| 5 | Ecatepec de Morelos | México | 87.8 | 1,478 |
| 6 | Mérida | Yucatán | 87.3 | 757 |
| 7 | Iztapalapa | Ciudad de México | 86.9 | 1,255 |
| 8 | Querétaro | Querétaro | 86.0 | 824 |
| 9 | Zapopan | Jalisco | 85.4 | 788 |
| 10 | Cuauhtémoc, Ciudad de México | Ciudad de México | 85.0 | 887 |
| 11 | Tijuana | Baja California | 84.6 | 644 |
| 12 | Chihuahua | Chihuahua | 84.4 | 651 |
| 13 | Aguascalientes | Aguascalientes | 83.5 | 642 |
| 14 | Toluca | México | 83.2 | 824 |
| 15 | Gustavo A. Madero | Ciudad de México | 82.8 | 872 |
| 16 | Morelia | Michoacán de Ocampo | 82.5 | 676 |
| 17 | Hermosillo | Sonora | 81.9 | 424 |
| 18 | Nezahualcóyotl | México | 81.3 | 840 |
| 19 | Juárez, Chihuahua | Chihuahua | 81.2 | 574 |
| 20 | San Luis Potosí | San Luis Potosí | 81.2 | 502 |

---

## 3. CE8: el criterio no se podía cumplir tal como estaba escrito

CE8 pide que *"los tests existentes de `/api/prospectos/ciudades` sigan en verde sin
modificarse"*. **No existía ninguno.** El endpoint que ordena la tabla del dashboard y, de
rebote, los chips del importador, estaba sin una sola línea de cobertura.

Lo que se hizo: escribir **11 tests de caracterización antes de tocar el endpoint**, para
fijar lo que hacía. De esas 11, **una cambió una línea**: la que afirmaba que el payload
viene ordenado de mayor a menor, porque ahora hay `null` para las ciudades fuera del
catálogo. El contrato cambió a propósito y se documenta; no se ajustó un test para tapar un
fallo.

La fórmula `relevancia` **sigue intacta**, con su cálculo histórico verificado por
`test_relevancia_conserva_su_formula_historica`, y marcada obsoleta con fecha de retiro
(no antes del 2026-12-01).

---

## 4. Verificación en las dos direcciones

Regla del entorno: *un barrido que no encuentra nada no demuestra que no hay nada*.

### 4.1 El catálogo (T1.8 punto 3)

| Comprobación | Esperado | Obtenido |
|---|---|---|
| León presente (positivo conocido) | sí | **sí** ✅ |
| `Los Mochis` aparece **una** vez (estaba duplicado en el array viejo) | 1 | **1**, clave `25001`, con alias `Ahome` y `Mochis` ✅ |
| Nombres duplicados tras normalizar | 0 | **0** ✅ |
| Ciudades con potencial 0 | 0 | **0** ✅ |

### 4.2 Los tests saben ponerse en rojo

Se reintrodujo cada defecto y se comprobó que la suite lo caza:

| Defecto reintroducido | Resultado |
|---|---|
| Clave INEGI duplicada | 🔴 detectado |
| Nombre repetido por acento | 🔴 detectado |
| Sufijo desambiguador en el nombre | 🔴 detectado |
| Una entidad fuera del catálogo | 🔴 detectado |
| Una ciudad con potencial 0 | 🔴 detectado |
| Un alias del array viejo perdido | 🔴 detectado |
| Región inventada | 🔴 detectado |
| Alias apuntando a dos ciudades | 🔴 detectado |
| Quitar el encogimiento por tamaño de muestra | 🔴 detectado |
| Quitar el descuento por saturación | 🔴 detectado |
| Desacotar el desempeño al 0.5-1.5 original | 🔴 detectado |
| Reintroducir el salto de `Sin ciudad` (el CRITICAL) | 🔴 detectado |
| Quitar el escape de la tabla del dashboard (el XSS) | 🔴 detectado |
| Quitar la validación de forma del JS | 🔴 detectado |
| Volver la caché a dos variables separadas | 🔴 detectado |

**Tres de estos no los detectaba nadie hasta que se comprobó.** El encogimiento y la
saturación pasaban por un fixture mal construido, y la validación de forma del JS no tenía
test. Los tres se arreglaron antes de dar nada por bueno.

### 4.3 El generador avisa cuando la fuente cambia

Quitando del mapa el estrato de personal ocupado más común, el contador nuevo reporta
**67,924 registros con estrato desconocido**. El aviso funciona; no es un contador decorativo.

---

## 5. El modelo hace lo que promete

| Escenario | Factor | Prioridad |
|---|---|---|
| Ciudad virgen con mercado real (Puebla, hoja vacía) | **1.000** — no se penaliza no haber ido | = potencial |
| Pueblo con 1 aprobado de 1 llamada (100 % de interés) | **< 1.10** — una llamada no es evidencia | muy por debajo de cualquier plaza grande |
| Plaza cosechada al 61 % (Chihuahua, 400 de 651) | **< 0.85** | baja del potencial |

**Una ciudad de potencial alto y cero historial rankea por encima de una de potencial bajo
con un aprobado.** Es lo que pedía el punto 4 de T1.8, y es exactamente lo que la fórmula
vieja hacía al revés.

---

## 6. Lo que NO se verificó, y por qué

- **Verificación funcional en navegador real.** El JS se comprueba con `node --check` (las
  dos superficies parsean) y con 22 tests sobre el string de la plantilla, que es el patrón
  del proyecto para JavaScript embebido en `app.py`. **No se abrió un navegador contra el
  panel desplegado**: exige el panel corriendo con credenciales de Google reales, que es
  entorno del owner.
- **Corrida real de Google Places con un nombre del catálogo nuevo.** Factura la API y
  escribe en `LISTA DE CONTACTOS` de producción. **Gate del owner** (§7).

---

## 7. Lo que le queda al owner

| # | Qué | Por qué no se puede cerrar aquí |
|---|---|---|
| 1 | **Validar el top-20** (§2.2 y §2.4) | Es su conocimiento del mercado. Si no lo reconoce, se vuelve a T1.3 y se reajustan pesos |
| 2 | **Decidir si el ranking debe premiar el mercado o lo que queda por cosechar** (§2.3) | Hoy hace lo segundo. Cambiarlo es una línea (`DESCUENTO_MAX_SATURACION = 0`), pero es una decisión de negocio |
| 3 | **Abrir `/importador` en un navegador** y probar el filtro por región | Requiere el panel desplegado |
| 4 | **Una corrida real con una ciudad del catálogo nuevo** | Factura Places y escribe en producción |

Los **1,168 contactos en 35 valores sin clasificar** (`San Luis`, `Mexico`, `Chiapas`,
`Heroica Matamoros`, `Morelos`, `Tabasco`, `Ciudad Victoria`…) se ven en el aviso amarillo
del importador. Reducir ese grupo es añadir cada valor como `alias` en el generador y
regenerar; no hace falta tocar código.
