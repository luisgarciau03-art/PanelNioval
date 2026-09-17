# EXPEDIENTE — el bug de conteo del importador, lo que YA se cerró

**Plan:** 3 · **Tarea:** T3.0 (Tarea Cero) · **Fecha:** 2026-09-17
**Rama:** `fix/conteo-importador-reincidencia`, desde `main` en **`13e2cdb`**
**Baseline anotado:** **1,193 passed, 2 skipped**, exit 0

> **Para qué existe este documento.** El síntoma que se reporta —*«dice agregados al sheet 20
> pero realmente nomás aparecen 10»*— **ya se cerró una vez**, en agosto, con un plan entero y
> quince defectos. Entrar a diagnosticar sin este expediente es garantizar que se vuelvan a
> descubrir cosas resueltas. **Lo que esté en la tabla del §2 no se re-diagnostica.**
>
> Este documento **no diagnostica nada**. No dice cuál de H1/H2/H3 es cierta — eso es T3.1 y
> T3.2. Sólo fija qué está cerrado, con qué commit y con qué guarda.

---

## 1. El commit: uno solo, y eso cambia cómo se bisecta

| | |
|---|---|
| Commit | **`ae0e1c9`** — *«el numero que ve el operador es el que hay en la hoja»* |
| Fecha | 2026-08-27 19:30 |
| Padre | **`034dd42`** |
| Volumen | 21 archivos, **+5,972 / −200**; `app.py` solo, **+1,060** |
| PR | #36 |

⚠️ **`ae0e1c9` tiene UN solo padre: el PR #36 se aterrizó en squash.** Los 15 defectos entraron
en un único commit. Consecuencia directa para **T3.2**: no hay granularidad dentro del fix, así
que una bisección *hacia atrás* no puede señalar «qué parte del fix falla». La bisección útil es
la que el plan pide — **`ae0e1c9` contra el `main` de hoy**— y son **24 commits que tocan
`app.py`** en ese rango (113 en total).

---

## 2. LOS 15 DEFECTOS CERRADOS — esto es lo que NO hay que volver a diagnosticar

Los 9 del plan original (B1–B9), los 4 hallados recorriendo rutas de clic (B10–B13) y los 2
hallados de paso durante el arreglo (B14–B15).

**Todos llevan el mismo commit `ae0e1c9`.** Lo que los distingue —y lo que los hace verificables
hoy, mes y medio y una extracción de HTML después— es **la guarda que los vigila**.

| # | Defecto | Cerrado en | Guarda viva hoy |
|---|---|---|---|
| **B1** | El contador cuenta aprobados, no filas escritas | T3.2 | `TestCuatroContadores`, `TestEstadoExponeLosContadores` |
| **B2** | Duplicados contra la hoja | T3.2 | `TestCuatroContadores` (`nuevos + duplicados == encontrados`) |
| **B3** | El mismo negocio contado en dos categorías | T3.3 | `TestDedupEntreCategorias` · `test_importador_conteo.py:432` |
| **B4** | Fallo de ESCRITURA en Sheets silenciado | T3.4 | `TestFalloDeEscrituraVisible` |
| **B5** | Estado en memoria de proceso (2 workers, sondeos `idle`) | T3.5 | `TestArranqueConsistente`, `TestDockerfileArrancable` |
| **B6** | Barra de progreso con tres valores (0/50/100) | T3.6 | `TestProgresoContinuo`, `TestProgresoConPaginacion` |
| **B7** | Recargar la página pierde el trabajo | T3.7 | `TestRestauraAlCargar` |
| **B8** | Botón trabado / sondeo eterno | T3.7 | `TestSondeoYBoton` |
| **B9** | Nombre de ciudad sin escapar — **XSS almacenado** | T3.7 | `TestCiudadEscapada` **+** `TestB9ElNombreDeCiudadSigueEscapado` |
| **B10** | Guard por proceso + Enter siempre vivo → **doble corrida, doble factura** | T3.5 + T3.7 | `TestEntradaBloqueadaDuranteLaCorrida` |
| **B11** | Filtrar ciudades renumera el ranking (la medalla miente) | T3.7 | `TestB11ElRangoNoSeRenumeraAlFiltrar` |
| **B12** | Insignias y stats rancios entre corridas | T3.7 | `TestReinicioEntreCorridas` |
| **B13** | Estado muerto (`ciudadSeleccionada`, `resultados` nunca expuesto) | T3.7 | `TestSinEstadoMuerto` |
| **B14** | Fallo de **LECTURA** de Places silenciado (el gemelo de B4) | T3.4 | `TestFalloDeLecturaVisible`, `GmapsQueFalla` / `GmapsVacio` |
| **B15** | `descartados` inflado hasta **6×** | T3.3 | `test_importador_conteo.py:504` |

**80 tests** vigilan esto hoy: conteo **22**, estado compartido **19**, frontend **26**,
progreso **13**. Todos verdes en el baseline de esta rama.

### 2.1 Las guardas sobrevivieron a la extracción del Plan 4

Es lo primero que había que comprobar, porque el PR #43 **sacó 3,240 líneas de HTML y JS de
`app.py`** y los tests de frontend de agosto se escribieron contra el monolito.

| | |
|---|---|
| Los 4 archivos de test de agosto | **siguen en `main`**, y dos más se les sumaron (`test_importador_ciudades.py`, `test_importador_ui_ciudades.py`) |
| `nuevos_en_sheet` en `static/js/importador.js` | **5 usos** — el número grande se pinta desde el archivo extraído |
| `nuevos_en_sheet` en `app.py` | **10 apariciones** |

**B9 y B11 tienen guarda doble**, y no por casualidad: `test_importador_ui_ciudades.py:8` dice
que sus dos últimos bloques **re-verifican** defectos que ya estaban arreglados antes de ese
trabajo. Alguien ya pensó en esto.

---

## 3. DOS HIPÓTESIS DESCARTADAS EN AGOSTO — no reabrir sin evidencia nueva

| Hipótesis | Por qué se descartó |
|---|---|
| **`_import_job` se inicializa dos veces → carrera** | El reset ocurre **dentro** de `with _import_lock:` y **estrictamente antes** de `Thread(...).start()`. El hilo resuelve el global en ejecución. No hay carrera |
| **`if lugares: break` corta las variaciones** | Por indentación corta el bucle de **reintentos**, no el de variaciones: **las 3 variaciones siempre corren**. Esto corrigió una afirmación contraria que estaba en la memoria del proyecto |

El segundo descarte dejó dos consecuencias que siguen vivas: el gasto de Places es **3 consultas
de texto por categoría, 6 por corrida**, y una consulta legítimamente vacía **se repite 3 veces
sin backoff** (el `2 ** intento` sólo está en la rama `except`). Es insumo del **Plan 2**.

---

## 4. TRES CORRECCIONES AL PLAN, encontradas leyendo el disco

El plan se escribió el 2026-09-15, **antes** de que los Planes 1 y 4 aterrizaran. Tres de sus
referencias ya no son ciertas. Se corrigen aquí para que T3.1 y T3.2 no persigan fantasmas.

### 4.1 `nuevos_en_sheet` se actualiza en **DOS** sitios, no en tres

El plan (T3.2, paso 2) dice: *«hay tres en `app.py`: la normal ~5781, la de parada ~5873, y la de
error ~5918»*. Esos números son **pre-extracción** — `app.py` tenía 6,368 líneas y hoy tiene menos
de 3,800.

Verificado sobre el `main` de hoy: de las **10 apariciones** de `nuevos_en_sheet` en `app.py`,
sólo **dos son escrituras**:

| Línea | Camino |
|---:|---|
| **3417** | El camino normal, por categoría |
| **3509** | El camino de **`presupuesto_agotado`**, que guarda lo ya pagado antes de cortar |

Las demás son: comentarios (2562, 3397), la inicialización a 0 (2580), la lista de claves (2717),
tres **lecturas** hacia el resumen de Telegram (3451, 3529, 3554) y el endpoint (3659).

**Los caminos de parada y de error no escriben el contador: sólo lo leen.** T3.2 debe enumerar
**dos** rutas, no tres — y `presupuesto_agotado` merece atención propia porque **no estaba en la
lista del plan**.

### 4.2 `saltados` NO entra en `nuevos_en_sheet`

El plan pide *«prestar atención especial a `saltados`: si además se sumara en algún camino a
`nuevos_en_sheet`, ahí está el 20 vs 10»*. En `app.py:3417-3419` el reparto es explícito:

```python
_import_job['encontrados']     += len(resultados) + saltados
_import_job['nuevos_en_sheet'] += nuevos
_import_job['duplicados']      += (len(resultados) - nuevos) + saltados
```

`saltados` va a `encontrados` y a `duplicados`; **`nuevos_en_sheet` sale de `nuevos`**, que es el
valor de retorno de `_exportar_a_sheets`. El mismo reparto en el camino de tope (3509-3512).

**Esto es una observación de lectura, no un veredicto.** Que el reparto esté bien escrito en esas
dos líneas no prueba que `nuevos` valga lo que debe. **T3.2 sigue teniendo que medirlo.**

### 4.3 El invariante de despliegue del plan es falso

Los INVARIANTES del Plan 3 dicen, literal: *«**NUNCA `main`** (el VPS auto-deploya `main`)»*.

**El VPS no auto-deploya nada.** Railway se eliminó el 2026-08-19 y el VPS de Vultr no tiene
webhook ni workflow; costó el diagnóstico entero del Plan 1 · T1.6. La conclusión de no trabajar
en `main` **sigue siendo correcta**, pero por otro motivo, y el motivo importa: significa que
**mergear el fix de este plan no lo publica**. Desplegar es un paso aparte, y verificarlo otro.

Consecuencia concreta para **T3.1**: la hipótesis **H1 (despliegue rancio) es más plausible de lo
que el plan supone**, porque no hay ningún mecanismo automático que la impida.

---

## 5. LO QUE AGOSTO DEJÓ ABIERTO — y por qué es el primer sitio donde mirar

La verificación de agosto cerró **8 de 11 criterios**. **Tres quedaron esperando al owner, y
ninguno de los tres se cerró nunca.**

| Gate de agosto | Qué faltaba | Estado hoy |
|---|---|---|
| **CE1 · corrida real** | Correr una ciudad de verdad y **contar a mano** las filas de la hoja | ⚠️ **Abierto.** Sigue listado como pendiente en `2026-08-28-validacion-tanda.md` |
| **CE5 · gunicorn real** | 20 sondeos contra el VPS, cero `idle` con el trabajo corriendo | 🟡 **Parcial** (ver abajo) |
| **CE7 · navegador** | Recargar a media corrida y ver la restauración | ⚠️ **Abierto** |

**Y eso es lo que hace este expediente útil para T3.1:** *todo lo que se verificó en agosto se
verificó con dobles de prueba.* `tools/reproducir_bugs_importador.py` **no toca la red, ni la
hoja, ni Places** — por diseño, y era la decisión correcta. Pero significa que **el único criterio
que compara el número de la UI contra la hoja de verdad nunca se ejecutó**. Si el síntoma sigue
vivo, el hueco entre «verde con dobles» y «verde contra la hoja» es el primer sitio donde mirar,
antes que cualquier regresión.

### 5.1 CE5, lo que sí se puede afirmar hoy

`Dockerfile:69` declara **`--workers 1 --threads 4 --worker-class gthread`**, que es la Opción A
del ADR `2026-08-27`. Con un solo proceso, la ceguera entre workers de B5 y la doble corrida de
B10 quedan cerradas **por construcción**. T4.7 verificó que el VPS sirve el código de `main` y que
el contenedor arranca `healthy`.

**Lo que NO se ha hecho:** los 20 sondeos contra el VPS. Se afirma la **configuración**
desplegada, no el **comportamiento** medido. La distinción es justo la que este proyecto ya pagó
cara tres veces.

*Nota:* `Procfile` y `nixpacks.toml` **ya no existen** — se fueron con Railway. El test de
consistencia de agosto comparaba los tres archivos; hoy queda `Dockerfile` como única fuente.

---

## 6. `claude-mem` — lo que devolvió, y hasta dónde llega

El relevo advertía que `mem-search` estaba caído desde el 2026-09-05. **Se comprobó, y no lo está:
la herramienta responde.** Lo que tiene límite es el **corpus**, que termina alrededor del
**2026-09-01** — o sea que **sí cubre entera la ventana del Plan 3 de agosto**, que es lo que esta
tarea necesitaba.

Se comprobó en las dos direcciones, como manda la regla: una consulta con filtro de proyecto
devolvió **cero** y podría haberse leído como «no hay nada»; la misma consulta sin el filtro
devolvió **15 resultados**. **El cero era del filtro, no del corpus.**

Dos hallazgos que el expediente escrito no recoge y conviene llevar a T3.5:

| ID | Hallazgo | Por qué importa |
|---|---|---|
| **#17575** | *Telegram Importador: «Completado» sent even for cancelled runs* | El aviso de Telegram es un **séptimo** canal de estado que el plan no cuenta entre los seis de la UI |
| **#17826** | *Telegram muestra «❌ Importador FALLÓ» para `PresupuestoAgotado`* | Un corte por tope **no es un fallo**. Y `presupuesto_agotado` es justo el camino que el §4.1 destapa |

Los dos son «un estado que dice algo que no es» — exactamente el objeto de **T3.5**.

---

## 7. Respaldo

`docs/auditoria/respaldos/2026-09-15-plan3/` — **13 archivos**, 377 KB (directorio en
`.gitignore`, como todo respaldo de este proyecto):

- `codigo/` — `app.py`, `static/js/importador.js`, `templates/importador.html`
- `tests/` — las 6 suites `test_importador_*.py`
- `evidencia-agosto/` — los dos documentos de agosto y el ADR del estado compartido

⚠️ **Lo que este respaldo NO incluye, y hay que decirlo: una copia de las hojas de Google.** El de
agosto llevaba 5 XLSX. Esta máquina **no tiene credenciales** — `GOOGLE_CREDENTIALS_JSON` ausente,
y ni `credentials.json` ni `.env` en disco (comprobada la **presencia**, nunca el valor).

No bloquea: **T3.0 no toca ni un dato, y T3.1–T3.6 tampoco escriben en la hoja.** Pero **T3.7 sí**
—es la corrida real— y ahí el respaldo de hojas es **requisito previo, no opcional**. Queda
anotado como lo primero de T3.7, con sus credenciales.

---

## 7bis. POR QUÉ EL FIX DE AGOSTO NO BASTÓ

*(Añadido al cerrar el plan, T3.8. Es el dato más valioso de todo el Plan 3.)*

El Plan 3 de agosto cerró **10/10 tareas**, con **15 defectos** arreglados, **84 tests nuevos** y
una medición antes/después en toda regla. Y el operador siguió viendo el bug **tres semanas
más**. No falló ninguna de sus tareas. Falló lo que había **entre** su última tarea y el
operador.

### Las tres cosas que lo explican

**1. El fix nació después del último despliegue, y nadie volvió a desplegar.**
Último despliegue real: **24-ago**. Fix: **27-ago**. Llegó a producción el **16-sep**, y sólo de
rebote, porque el Plan 1 necesitaba publicar sus 1,004 ciudades. Sin ese rebote seguiría sin
llegar.

**2. Tres de sus once criterios quedaron esperando al owner, y ninguno se cerró.**
Corrida real, gunicorn en el VPS, navegador. Los tres eran justamente **los que salían de la
máquina de desarrollo**. Los ocho que se cerraron se cerraron con dobles.

**3. Nada podía notar la diferencia.**
`/salud` es mudo por decisión de seguridad. El smoke no toca ninguna ruta del importador. No hay
auto-deploy. La suite pasa igual de verde con el panel rancio que con el panel al día, porque la
suite no mira producción. **La verificación de agosto era correcta y no podía ver lo que
importaba.**

### Lo que este plan añade para que no se repita

| | |
|---|---|
| `tools/huella_despliegue.py` | Fecha el código servido **por comportamiento**, con 4 códigos de salida — y `exit 3` significa «no pude medir», que **no es un verde** |
| `tests/test_huella_despliegue.py` | 15 tests, y el que importa vigila que los marcadores **no se oxiden**: si alguien renombra un campo, la guarda empieza a mentir y se descubre aquí |
| RUNBOOK, *«Cómo saber qué versión sirve el VPS»* | El procedimiento, con la tabla de qué hacer ante cada salida |
| `tools/auditar_estados_importador.py` | Recorre los estados y dice **COINCIDE / MIENTE**, y funciona también **contra el panel desplegado** |

**La lección, en una frase:** *un plan que cierra todas sus tareas y deja tres gates abiertos no
está cerrado — está esperando, y nadie avisa de que espera.*

---

## 8. Estado de la tarea

| | |
|---|---|
| Rama creada desde `main` `13e2cdb` | ✅ |
| Baseline anotado | ✅ **1,193 passed, 2 skipped** |
| Los cuatro documentos de agosto leídos enteros | ✅ |
| `claude-mem` consultado | ✅ (y comprobado en las dos direcciones) |
| **15 defectos listados con su commit y su guarda** | ✅ |
| Respaldo | ✅ código, tests y evidencia · ⚠️ **hojas: requisito de T3.7** |

**Criterio de cierre cumplido** — el plan pedía los 13; se listan los 15.

**Lo que T3.1 hereda, en una frase:** *no hay auto-deploy que garantice que el fix esté
desplegado, y el único criterio que compara la UI contra la hoja de verdad nunca se ejecutó.*
