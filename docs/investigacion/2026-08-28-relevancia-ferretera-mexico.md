# QUÉ HACE RELEVANTE A UNA CIUDAD EN EL RAMO FERRETERO MEXICANO

**Tarea:** Plan 1 · T1.2 · **Fecha:** 2026-08-28 · **Rama:** `feat/relevancia-ciudades-nacional`
**Regla que gobierna este documento:** *no inventar cifras*. Cada número de abajo se obtuvo
descargando y procesando el archivo citado en esta misma sesión. Lo que no se pudo obtener
con fuente verificable está en la §5, **descartado y con el motivo escrito**.

---

## 1. Resumen ejecutivo

Se evaluaron **8 indicadores candidatos**. **5 quedaron aprobados** con fuente pública,
granularidad municipal y ruta de descarga comprobada; **3 se descartaron**.

Todos los aprobados salen de **dos programas del INEGI** (DENUE y Censo de Población 2020),
ambos bajo los *Términos de Libre Uso de la Información del INEGI*, y **los cuatro archivos
se descargaron por URL directa con `curl`, sin token y sin aplicación de escritorio**. Eso
es lo que hace viable el script reproducible que pide T1.4.

⚠️ **Riesgo R1 del plan, cerrado.** El plan preveía que *"DENUE no dé detalle municipal para
el SCIAN ferretero"*. **No se materializó:** DENUE trae `cve_ent`, `cve_mun` y `municipio`
por establecimiento, y el ramo ferretero tiene código propio.

---

## 2. Tabla de indicadores aprobados

| # | Indicador | Fuente | Año / edición | Granularidad | Peso propuesto | Cómo se obtiene |
|---|---|---|---|---|---|---|
| **I1** | **Ferreterías y tlapalerías** (SCIAN **467111**) | INEGI · DENUE | **05_2026** (`Modified: 2026-05-20`) | **Municipal** | **45 %** | `denue_00_46591-46911_csv.zip` → filtrar `codigo_act == 467111` → contar por `cve_ent+cve_mun` |
| **I2** | **Masa del ramo** — personal ocupado estimado de I1 | INEGI · DENUE | 05_2026 | Municipal | **20 %** | Mismo archivo; convertir el estrato `per_ocu` a punto medio y sumar |
| **I3** | **Mayoreo de materiales de construcción** (SCIAN 434211, 434219, 434221, 434224, 434225, 434226) | INEGI · DENUE | 05_2026 | Municipal | **15 %** | `denue_00_43_csv.zip` → filtrar esos 6 códigos → contar por municipio |
| **I4** | **Empresas de construcción** (sector SCIAN **23** completo) | INEGI · DENUE | 05_2026 | Municipal | **10 %** | `denue_00_23_csv.zip` → filtrar `codigo_act` que empiece con 23 → contar por municipio |
| **I5** | **Población total** | INEGI · Censo de Población y Vivienda **2020** (ITER) | 2020 | **Municipal** | **10 %** | `iter_00_cpv2020_csv.zip` → filas con `LOC == 0000` y `MUN != 000` → campo `POBTOT` |

Los pesos son **propuesta de esta tarea**. Quien los congela es **T1.3** en el ADR, tras el
panel de decisión. Aquí solo se justifica por qué cada indicador merece estar.

**Por qué estos cinco y no otros.** I1 cuenta al prospecto literal: el negocio al que NIOVAL
le vende. I2 lo pesa, porque veinte ferreterías de mostrador no son veinte de bodega. I3 mide
el canal mayorista instalado: donde hay mayoristas de material hay volumen que sostiene
mayoristas. I4 mide la demanda que arrastra al ramo — el ferretero compra cuando hay obra.
I5 es el proxy de demanda de fondo, y entra con peso bajo a propósito: sin él, un municipio
dormitorio con muchas ferreterías pequeñas empataría con una plaza industrial.

---

## 3. Rutas de descarga, comprobadas hoy

Las cuatro se ejecutaron en esta sesión. Tamaño y SHA-256 son de los archivos descargados,
no de la documentación.

| Archivo | URL | Bytes | SHA-256 (16 primeros) |
|---|---|---|---|
| Comercio al por menor, ramas 46591-46911 | `https://www.inegi.org.mx/contenidos/masiva/denue/denue_00_46591-46911_csv.zip` | 60,209,960 | `dd37519ac10f46af` |
| Comercio al por mayor (sector 43) | `https://www.inegi.org.mx/contenidos/masiva/denue/denue_00_43_csv.zip` | 18,345,491 | `0b57798429caccdc` |
| Construcción (sector 23) | `https://www.inegi.org.mx/contenidos/masiva/denue/denue_00_23_csv.zip` | 2,716,967 | `8f93eb74daf8b832` |
| Censo 2020 · ITER nacional | `https://www.inegi.org.mx/contenidos/programas/ccpv/2020/datosabiertos/iter/iter_00_cpv2020_csv.zip` | 36,615,814 | `9342fdbd45bda589` |

**El SCIAN ferretero cae en el archivo `46591-46911`** porque `4671*` está dentro de ese
rango de ramas. No es obvio y costó dos intentos:

- `denue_00_46_csv.zip` **existe pero pesa 0 bytes**: responde `HTTP 200`,
  `Content-Type: application/x-zip-compressed` y `Content-Range: bytes */0`.
- `denue_00_467_csv.zip` y `denue_00_4671_csv.zip` responden `HTTP 200` pero devuelven
  **HTML**, no ZIP.

**Un script que confíe en el código HTTP se traga un archivo vacío sin enterarse.** El
generador de T1.4 tiene que verificar tamaño mínimo y que el ZIP abra, no el status code.
Es el mismo patrón que la regla del entorno sobre reemplazos que no casan: la operación que
falla no siempre se queja.

**Encodings, y son distintos entre sí:**

| Archivo | Encoding | Si se lee mal |
|---|---|---|
| DENUE (los tres) | **latin-1** | Acentos rotos en `municipio` y `nombre_act` |
| ITER (Censo) | **utf-8 con BOM** (`utf-8-sig`) | La primera columna se llama `﻿ENTIDAD` y revienta con `KeyError: 'ENTIDAD'` |

Estructura interna de cada ZIP de DENUE: `conjunto_de_datos/*.csv` (42 columnas),
`diccionario_de_datos/` y `metadatos/`.

---

## 4. Cifras medidas (todas de esta corrida)

### 4.1 El universo del ramo

| Código SCIAN | Descripción | Establecimientos |
|---|---|---|
| **467111** | **Comercio al por menor en ferreterías y tlapalerías** | **75,726** |
| 467115 | Comercio al por menor de artículos para la limpieza | 46,582 |
| 467114 | Comercio al por menor de vidrios y espejos | 23,201 |
| 467113 | Comercio al por menor de pintura | 18,918 |
| 467112 | Comercio al por menor de pisos y recubrimientos cerámicos | 5,742 |
| 467117 | Comercio al por menor de artículos para albercas y otros | 4,296 |
| 467116 | Materiales para la construcción en autoservicio especializado | 253 |
| | **Total rama 4671** | **174,718** |

**467115 (limpieza) se excluye del núcleo.** NIOVAL distribuye ferretería y plomería; una
tienda de artículos de limpieza no es su prospecto. Son 46,582 establecimientos: incluirlos
inflaría el indicador principal un 61 % con negocios que no compran el catálogo.

### 4.2 Cobertura

| Métrica | Valor |
|---|---|
| Municipios con al menos un registro en los tres sectores | **2,275** |
| **Entidades federativas representadas** | **32 / 32** ✅ (CE4 alcanzable) |
| Municipios con ≥ 1 ferretería (467111) | 2,227 |
| Municipios con ≥ 10 | 995 |
| Municipios con ≥ 20 | **589** |
| Municipios con ≥ 30 | **443** |
| Municipios con ≥ 50 | 276 |
| Municipios con población en el Censo 2020 | 2,469 |

**Esto resuelve el dimensionamiento de la decisión D3 con un dato, no con una estimación.**
La opción **A** del owner (400-600 ciudades) se obtiene con un corte de **≥ 20 ferreterías
(589 municipios)** o **≥ 30 (443)**. Ambos caen dentro del rango pedido; la elección exacta
es de T1.3/T1.4.

### 4.3 Top-10 nacional por I1, tal como sale del dato crudo

| # | Municipio (nombre INEGI) | Estado | Ferreterías (467111) | Mayoreo constr. | Construcción |
|---|---|---|---|---|---|
| 1 | Ecatepec de Morelos | México | 1,478 | 581 | 107 |
| 2 | Puebla | Puebla | 1,357 | 784 | 641 |
| 3 | Iztapalapa | Ciudad de México | 1,255 | 561 | 128 |
| 4 | León | Guanajuato | 1,137 | 810 | 398 |
| 5 | Guadalajara | Jalisco | 1,119 | 885 | 663 |
| 6 | Cuauhtémoc | Ciudad de México | 887 | 632 | 226 |
| 7 | Gustavo A. Madero | Ciudad de México | 872 | 377 | 123 |
| 8 | Nezahualcóyotl | México | 840 | 382 | 57 |
| 9 | Toluca | México | 824 | 360 | 186 |
| 10 | Querétaro | Querétaro | 824 | 650 | 442 |

El agregado municipal completo quedó en `agregado_municipal.json` y la población en
`poblacion_municipal.json`, ambos generados por el pipeline. **No se transcribe ninguna cifra
a mano**: T1.4 las lee del archivo.

### 4.4 Tres hallazgos que cambian el diseño de T1.3 y T1.4

**a) El dato mide municipios; el operador piensa en ciudades comerciales.**
El municipio `23005` se llama **Benito Juárez** en INEGI y es **Cancún** para cualquiera que
venda ahí. `25001` es **Ahome** y todos dicen **Los Mochis**. Si el nombre canónico que va a
Google Places fuera el de INEGI, el importador buscaría `"Ferreterías en Benito Juárez"` y
traería resultados de la alcaldía homónima de la CDMX — el mismo tipo de degradación
silenciosa que hoy causan los sufijos `Santiago Ixc` o `Tonalá Chis`. **El `nombre` canónico
debe ser el comercial y la clave INEGI el identificador**; el nombre INEGI entra como alias.

> ⚠️ El ejemplo del propio plan (§T1.4) trae `"nombre": "Los Mochis", "clave_inegi": "25006"`.
> **`25006` es Culiacán** (población 1,003,530, verificada); Los Mochis es Ahome, **`25001`**.
> Es un ejemplo del documento, no código, pero copiarlo tal cual metería un error de clave.

**b) La Zona Metropolitana del Valle de México se cuenta por alcaldías y municipios sueltos.**
Ecatepec, Iztapalapa, Cuauhtémoc, GAM, Nezahualcóyotl y Chimalhuacán aparecen como seis
plazas cuando comercialmente son una sola con rutas de reparto compartidas. Seis de las diez
primeras posiciones son ZMVM. Es una decisión con tradeoff real — agrupar mejora la lectura
pero borra el detalle de reparto — y **va a T1.3**, no se resuelve aquí por decreto.

**c) El conteo crudo tiene un sesgo de tamaño de municipio.** Ecatepec encabeza por número de
establecimientos, pero su personal ocupado estimado (5,957) es menor que el de Guadalajara
(6,239) con 359 ferreterías menos: son muchos negocios pequeños contra menos negocios
grandes. **Por eso I2 existe** y por eso el modelo de T1.3 no puede ser I1 a secas.

---

## 5. Indicadores evaluados y DESCARTADOS, con motivo

| Indicador | Por qué se descarta |
|---|---|
| **Valor de producción de la construcción (ENEC)** | La ENEC publica por **entidad federativa**, no por municipio. Un dato estatal daría el mismo empujón a todos los municipios del estado — justo el empate arbitrario que este plan elimina. **I4 cubre la misma intención con granularidad municipal.** |
| **PIB estatal (ITAEE)** | Mismo problema de granularidad estatal. |
| **Corredores logísticos / cabeceras de distribución** | No se encontró dataset público, municipal y descargable que los defina. Codificarlos a mano sería **exactamente** el criterio subjetivo que el plan busca eliminar. Si el owner quiere reconocer una plaza como centro de reparto, el sitio correcto es el multiplicador de desempeño de T1.3, no el potencial de mercado. |

### 5.1 Tres rutas de acceso que NO funcionan, para que nadie las reintente

- **API del DENUE** (`https://www.inegi.org.mx/servicios/api_denue.html`): funciona por token
  de desarrollador. Obtenerlo exige registro — **sería un gate del owner** — y ataría el
  script de T1.4 a una credencial. La descarga masiva por URL no necesita ninguna.
  **Se eligió la descarga masiva a propósito.**
- **Portal de descarga masiva** (`https://www.inegi.org.mx/app/descarga/?ti=6`): entrega un
  `.zip` que contiene **`DescargaMasivaApp.exe`**, aplicación de escritorio de Windows.
  Inservible para un script reproducible y para el CI. Las URLs directas de la §3 lo evitan.
- **CONAPO, proyecciones municipales**: las tres URLs candidatas bajo
  `conapo.segob.gob.mx/work/models/CONAPO/Datos_Abiertos/` devolvieron **HTTP 404**. Se
  sustituyó por el **Censo 2020 (ITER)** del INEGI, que resuelve y da el mismo dato municipal
  con fuente oficial. Coste asumido: el dato es de 2020, no una proyección a 2026.

---

## 6. Verificación en las dos direcciones

Regla del entorno: *un barrido que no encuentra nada no demuestra que no hay nada*. Hay que
comprobar que el método **encuentra un positivo conocido**.

| Comprobación | Esperado | Obtenido |
|---|---|---|
| Población de Ecatepec (Censo 2020) | 1,645,352 | **1,645,352** ✅ |
| Población de Monterrey (Censo 2020) | 1,142,994 | **1,142,994** ✅ |
| Población de Culiacán (`25006`) | 1,003,530 | **1,003,530** ✅ |
| Cancún = municipio Benito Juárez, Q. Roo (`23005`) | aparece en el ramo | **449 ferreterías** ✅ |
| Entidades presentes | 32 | **32** ✅ |
| ¿El filtro de SCIAN excluye lo que debe? | 467115 fuera del núcleo | 75,726 ≠ 122,308 ✅ |

El pipeline devuelve las cifras exactas del Censo en cuatro comprobaciones independientes y
distingue lo que debe excluir. Su cero, cuando lo dé, vale.

---

## 7. Qué entrega esta tarea a la siguiente

- **T1.3** recibe cinco indicadores medidos, tres decisiones de diseño con tradeoff real
  (§4.4: nombre comercial vs. INEGI · agrupar o no la ZMVM · conteo vs. masa) y el dato duro
  para cerrar D3: 589 municipios con ≥20 ferreterías, 443 con ≥30.
- **T1.4** recibe cuatro URLs comprobadas con su tamaño y hash, la estructura interna de cada
  archivo, los dos encodings distintos y la trampa del ZIP de 0 bytes.
