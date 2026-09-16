# CONTEXTO DEL PLAN 1 — QUÉ ESTÁ DECIDIDO Y QUÉ SIGUE ABIERTO

**Tarea:** Plan 1 · T1.1 · **Fecha:** 2026-09-15 · **Rama:** `feat/relevancia-nacional-produccion`
**Propósito:** que esta tanda no vuelva a litigar lo que agosto ya cerró con datos, ni
re-descubra lo ya diagnosticado.

---

## 0. Nota de herramienta: `claude-mem` está caído, y con qué se sustituyó

La tarea asigna **`claude-mem:mem-search`** (fuente `claude-mem`) como herramienta principal.
**No está disponible en esta sesión.** Dos invocaciones devolvieron
`Error calling Worker API: fetch failed`. Diagnóstico en disco:

| Evidencia | Valor |
|---|---|
| `~/.claude-mem/CAPTURE_BROKEN` | `[bun-runner] empty stdin payload received — issue #2188`, `payload byte length: 0`, `platform: win32`, sello **2026-09-05T16:14:18Z** |
| Ruta del script en el marcador | `…/claude-mem/**13.24.1**/scripts/worker-service.cjs` |
| Versión realmente instalada en caché | **13.24.23** |
| Última escritura de `claude-mem.db` | **2026-09-06 08:40** (86 MB) |

**Consecuencia operativa que hay que saber:** la captura de memoria lleva ~10 días rota, así
que **el trabajo de esta tanda no se está guardando en `claude-mem`**. El relevo
(`docs/superpowers/plans/RELEVO-actual.md`) y estos documentos son, por ahora, la **única**
persistencia entre sesiones. Es un pendiente del entorno, no del proyecto; queda anotado
entre las dudas del cierre del plan.

**Sustitución, declarada como manda la regla de herramientas.** No se reemplazó por una skill
de proceso de Superpowers. Se usó la **misma información que `mem-search` habría devuelto**,
ya transcrita y verificada en el repositorio: el documento
`docs/investigacion/2026-08-28-contexto-previo-importador.md` (rama del PR #42) es
literalmente el producto de la T1.1 de agosto, que **sí** corrió `mcp-search` y dejó las **8
observaciones con su ID**. Esa transcripción es fuente citable y verificable; lo que se
pierde frente a la búsqueda viva es la posibilidad de encontrar observaciones *posteriores*
al 2026-08-28 — y como la captura murió el 2026-09-05, el hueco real es de una semana en la
que no hubo trabajo sobre el importador.

---

## 1. Fuentes leídas (las tres que pide el plan, más una)

| Documento | Rama | Qué aporta |
|---|---|---|
| `docs/adr/2026-08-28-modelo-relevancia-ciudades.md` | `feat/relevancia-ciudades-nacional` | El modelo, los 3 candidatos medidos, el consejo de 4 voces |
| `docs/investigacion/2026-08-28-relevancia-ferretera-mexico.md` | idem | Los 5 indicadores con fuente, URLs con hash, cobertura medida |
| `docs/investigacion/2026-08-29-verificacion-plan1.md` | idem | Los 10 criterios de éxito de agosto y el gate del owner |
| `docs/investigacion/2026-08-28-contexto-previo-importador.md` | idem | **Sustituto de `mem-search`**: las 8 observaciones con ID |

---

## 2. LO QUE ESTÁ DECIDIDO Y NO SE REABRE

Nueve decisiones, cada una con fuente. El criterio de cierre pedía ≥5.

### D-1 · El modelo es `potencial_mercado × factor_nioval`, logarítmico
**Fuente:** ADR `2026-08-28-modelo-relevancia-ciudades.md` §2 · observación **#17407**

Tres candidatos **calculados de verdad** sobre 589 municipios, no comparados de sobremesa:

| Candidato | Medido | Veredicto |
|---|---|---|
| A — Lineal | mediana 3.0; **399 de 589 bajo 5 puntos** | ❌ el empate arbitrario original con otro nombre |
| **B — Logarítmico** | mín 36.9 · mediana 53.9 · máx 98.5; **cero bajo 5** | ✅ **elegido** |
| C — Geométrico de dos ejes | mediana 2.8; **407 bajo 5** | ❌ hereda el defecto de A y penaliza dos veces el desbalance |

La distribución es de cola pesada: el primer municipio vale **185 veces la mediana**. Por eso
el logaritmo no es preferencia estética, es lo que evita el empate.

### D-2 · El diagnóstico original está cerrado: la fórmula vieja era 100 % endógena
**Fuente:** observaciones **#17365**, **#17405**, **#17391** · verificado en `app.py:913-919`

Los tres términos salían de `LISTA DE CONTACTOS` y del formulario. Toda ciudad virgen puntúa
**0** y el `sort` estable las dejaba en el orden de inserción de un array escrito a mano. El
ranking era circular: recomendaba donde ya se trabajó. **No hay que volver a demostrarlo.**

### D-3 · `factor_nioval` es multiplicativo y acotado a [0.60, 1.25], neutro en 1.00
**Fuente:** ADR §2.2 y §4.4

Con historial cero el factor es **1.000**: no se penaliza no haber ido. Con suma habría que
decidir *cuántos puntos vale «sin datos»*, y ese número no existe. Se rechazó el rango
`0.5-1.5` del plan original porque a ±50 % el término endógeno volvería a dominar — justo lo
que el ADR viene a impedir.

### D-4 · `f_saturacion` existe, y sale de una objeción del consejo
**Fuente:** ADR §4.2

Places devuelve ~60 resultados por búsqueda; una plaza ya cosechada rinde duplicados y sigue
siendo #1 para siempre. Medido contra producción: **Chihuahua 448 contactos sobre 651
ferreterías (69 % cosechado)**, **Puebla 425 sobre 1,357**. El potencial útil es **lo que
queda por cosechar**, no lo que existe. No estaba en ninguno de los tres candidatos.

### D-5 · `personal ocupado` se reexpresa como tamaño medio, y su peso baja de 20 % a 10 %
**Fuente:** ADR §4.1 (matriz de correlación de Pearson, 589 municipios)

En crudo era **colineal con el conteo (r = 0.971)**: pesaba 20 % sin aportar. Como
`ocupados / ferreterías` la correlación cae a **r = 0.152** y empieza a decir algo propio: si
la plaza es de mostrador (3.0 personas) o de bodega (15.1). Es el caso más limpio de una
objeción que se comprobó antes de aceptarse.

### D-6 · El nombre canónico es el COMERCIAL; el de INEGI viaja como alias
**Fuente:** investigación `2026-08-28` §4.4a · ADR §4.5

El municipio `23005` se llama **Benito Juárez** en INEGI y **Cancún** para quien vende ahí.
Buscar `"Ferreterías en Benito Juárez"` traería la alcaldía de la CDMX: **~80 Place Details
facturados en el lugar equivocado**. El ranking no es el gasto; **el string sí**.
⚠️ Trampa registrada: el ejemplo del plan de agosto traía `Los Mochis / 25006`, y **`25006`
es Culiacán**; Los Mochis es Ahome, **`25001`**.

### D-7 · La ZMVM NO se fusiona en el dato
**Fuente:** ADR §5.1

Seis de las diez primeras plazas son ZMVM contadas por separado. Agrupar en el **dato**
destruiría la clave INEGI, que es lo que permite deduplicar y regenerar. Los municipios se
conservan íntegros; **la agrupación, si se hace, es de presentación y es del Plan 4**. Queda
como riesgo abierto: el operador puede gastar seis corridas sobre rutas solapadas.

### D-8 · El chip muestra posición y conteo crudo, nunca el decimal del puntaje
**Fuente:** ADR §4.3

Con logaritmo, León (1,137 ferreterías) y Querétaro (824) quedan a pocos puntos. Un `86.7`
frente a un `89.8` **no significa lo que el operador va a leer que significa**. El puntaje
ordena; el conteo explica. Es decisión de **presentación**, y por tanto insumo directo del
Plan 4.

### D-9 · El campo `relevancia` se conserva aunque esté obsoleto
**Fuente:** observación **#17391** · verificación `2026-08-29` §3

Son **dos sistemas de orden, no uno**: el dashboard (`/api/prospectos/ciudades` →
`getSortedCiudades()`) y el importador (array `CIUDADES_MX` fusionado en el navegador).
Quitar `relevancia` rompe la lectura del dashboard aunque el importador quede perfecto. Está
marcado obsoleto con fecha de retiro **no antes del 2026-12-01** y protegido por
`test_relevancia_conserva_su_formula_historica`.

### Además — dos cosas que ya están HECHAS en el código y no se reimplementan
**Fuente:** contexto previo §3, reverificado con `grep` sobre `app.py`

| Punto | Estado | Evidencia |
|---|---|---|
| **B9** — escapar el nombre de ciudad (XSS) | ✅ hecho | `escaparHtml`, listener delegado; `seleccionarCiudad` ya no existe |
| **B11** — rank fijo al filtrar | ✅ hecho | `c.rank` se fija una vez sobre el catálogo completo |

---

## 3. LO QUE QUEDÓ ABIERTO

Coincide con §0.2 del plan, punto por punto.

| # | Lo pedido | Estado | Quién lo cierra |
|---|---|---|---|
| **A1** | «ordenar por relevancia a nivel país México, ramo ferretero» | ✅ **construido** — modelo exógeno DENUE, `potencial_mercado` 0-100 | Falta **verificarlo en vivo**: T1.4 y T1.6 |
| **A2** | «debe contemplar **todas las ciudades de la región**» | ⚠️ **sin verificar** — hay 606 municipios y el campo `region` existe, pero **nadie midió si 606 es "todas"** | **T1.2** (auditar) y **T1.3** (cerrar la brecha) |
| **A3** | Que el operador lo vea | ❌ **no desplegado** — PR #42 abierto desde 2026-08-29 | **T1.5** (mergear) y **T1.6** (desplegar y verificar) |

### 3.1 Los cuatro pendientes del owner que agosto dejó escritos
**Fuente:** verificación `2026-08-29` §7

1. **Validar el top-20** — es su conocimiento del mercado (es el **CE4/gate de T1.4**).
2. **Decidir si el ranking premia el mercado o lo que queda por cosechar** — hoy hace lo
   segundo. Cambiarlo es una línea (`DESCUENTO_MAX_SATURACION = 0`), pero es decisión de
   negocio, no de código.
3. **Abrir `/importador` en un navegador** y probar el filtro por región → **T1.6**.
4. **Una corrida real de Places** con una ciudad del catálogo nuevo — factura la API y
   escribe en producción.

### 3.2 La ambigüedad de CE10/CE4 que sigue viva, y que T1.4 hereda

El criterio del owner está redactado como *«¿reconoce esas plazas como las relevantes del
ramo?»*, pero **el ranking no responde esa pregunta**. Son dos preguntas distintas:

| Pregunta | La responde | Top real |
|---|---|---|
| *¿Dónde está el mercado ferretero de México?* | `potencial_mercado` | Puebla · Guadalajara · León · Monterrey |
| *¿A qué ciudad le dedico la próxima corrida?* | `prioridad` (= potencial × factor) | Zapopan · Hermosillo · Iztapalapa · Mexicali |

Puebla es **#1 por potencial** y **#33 por prioridad**, porque ya está cosechada a un tercio.
**T1.4 debe presentar las dos listas**, no una: con una sola, el owner juzga la pregunta
equivocada. Está así previsto en el plan (T1.4 pide top-30 con indicadores a la vista).

### 3.3 Un hueco de datos que T1.2 tiene que llenar

La investigación de agosto midió la cobertura **nacional**, no **por región**:

| Umbral | Municipios | ¿Medido en agosto? |
|---|---|---|
| ≥ 1 ferretería | 2,227 | ✅ |
| ≥ 5 | — | ❌ **no medido** (T1.2 lo pide) |
| ≥ 10 | 995 | ✅ |
| **≥ 20 (umbral vigente)** | **589** | ✅ |
| ≥ 30 | 443 | ✅ |
| ≥ 50 | 276 | ✅ |
| Municipios con población en Censo 2020 | 2,469 | ✅ |

**Dos huecos reales para T1.2:** (1) el corte **≥5** nunca se calculó; (2) **ninguna de estas
cifras está desagregada por macro-región**, que es justo lo que el requisito «todas las
ciudades de la región» obliga a mirar — un umbral pensado para el Bajío puede
sub-representar al Sureste.

**Y una discrepancia a explicar:** el ADR §5.2 fija el corte en **≥20 → 589 municipios**,
pero el catálogo construido tiene **606**. Los 17 de diferencia hay que explicarlos en T1.2
antes de tocar el umbral (probablemente altas por alias/nombre comercial, pero **eso es una
hipótesis, no un dato**).

---

## 4. Lo que la memoria NO tiene, y por eso T1.2 sigue siendo necesaria
**Fuente:** contexto previo §6

No existe ninguna observación con **datos de mercado ferretero mexicano con fuente citable**.
Lo más cercano es **#7109** (estacionalidad del ramo para una campaña de otro proyecto, sin
granularidad municipal). El indicador exógeno **hubo que ir a buscarlo** — y por eso la
investigación de agosto vale: trae URLs con tamaño y SHA-256 comprobados.

Tres rutas que **no** hay que reintentar (§5.1 de la investigación):

- **API del DENUE** — exige token de desarrollador: sería un gate del owner y ataría el
  generador a una credencial. La descarga masiva no necesita ninguna.
- **Portal de descarga masiva** — entrega un `DescargaMasivaApp.exe`, inservible para script y CI.
- **CONAPO, proyecciones municipales** — las tres URLs candidatas dan **HTTP 404**. Se
  sustituyó por el Censo 2020 (ITER).

⚠️ **Trampa heredada, vigente para T1.3:** `denue_00_46_csv.zip` responde **HTTP 200 con 0
bytes**, y `denue_00_467_csv.zip` responde **HTTP 200 con HTML**. Un script que confíe en el
código de estado se traga un archivo vacío sin enterarse. El generador ya valida tamaño
mínimo; **no quitar esa validación**.

---

## 5. Qué entrega esta tarea a T1.2

1. Las **nueve decisiones de arriba están cerradas**: T1.2 no evalúa el modelo, evalúa la
   **cobertura**. Bajar el umbral es cambiar `minimo_ferreterias` y regenerar; **los pesos y
   la fórmula no se tocan**.
2. Los cortes nacionales ya medidos (≥1, ≥10, ≥20, ≥30, ≥50) — **no hay que recalcularlos**.
3. Los dos huecos que sí son trabajo nuevo: **el corte ≥5** y **la desagregación por
   macro-región**.
4. La discrepancia **589 (ADR) vs 606 (catálogo)** por explicar.
5. La restricción que no se puede romper: **CE3 — ninguna ciudad en 0**. Al bajar el umbral
   entran municipios chicos y la normalización logarítmica podría acercarlos a cero. El
   potencial mínimo actual del catálogo es **14.1** (verificación de agosto, CE6).
