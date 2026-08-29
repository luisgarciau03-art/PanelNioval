# PLAN 1 — RELEVANCIA DE CIUDADES A NIVEL NACIONAL (RAMO FERRETERO)

**Fecha de diseño:** 2026-08-27
**Proyecto:** PanelNioval — `C:\Users\PC 1\PanelNioval`
**Superficie afectada:** `https://panelnioval.duckdns.org/importador` y `/api/prospectos/ciudades`
**Rama de trabajo:** `feat/relevancia-ciudades-nacional` (desde `main` actualizado — **NUNCA `main`**, Railway y Vultr despliegan de ahí)
**Decisión del owner (2026-08-27):** alcance geográfico = **México completo agrupado por macro-región**
**Baseline verificado el 2026-08-27:** `python -m pytest tests/ -q` → **230 passed**, exit 0

---

## 0. VALIDACIÓN AL 2026-08-28 (revisión contra el código en disco)

Este plan se diseñó el 2026-08-27 y se **validó contra el código en disco el 2026-08-28**,
después de que el Plan 3 (10/10) y el Plan 2 (7/9) movieran `app.py` de 4,948 a 6,098
líneas. Lo de abajo **manda** sobre cualquier número de línea del resto del documento.

### 0.1 Anclajes corregidos

| Lo que dice el plan | Realidad verificada el 2026-08-28 |
|---|---|
| Cálculo de `relevancia` en `app.py:848-855` | **`app.py:913-919`** |
| `const CIUDADES_MX` en `app.py:4727` | **`app.py:5679`** |
| Fusión JS catálogo + panel en `app.py:4795-4816` | **`app.py:5750-5779`** (`cargarCiudades`) |
| Chips de ciudad en `app.py:4830-4843` | **`app.py:5795-5812`** (`renderChips`) |
| `str_val(c.get('CIUDAD'...))` en `app.py:807` | **`app.py:870`** (hay otro en `app.py:597`) |
| `getSortedCiudades()` en `app.py:2150-2157` | **`app.py:2213`** |
| "array de ~250 entradas" | **293 entradas · 238 únicas · 50 duplicados exactos** (medido) |
| Baseline `230 passed` | **357 passed, 1 skipped** (verificado en disco el 2026-08-28) |

### 0.2 Dos puntos del plan que YA ESTÁN HECHOS — verificar, no reimplementar

**T1.7 punto 5 (escapado del nombre de ciudad, defecto B9): HECHO.** `app.py:5810-5823` ya
usa `escaparHtml(c.ciudad)`, mete el nombre en `data-ciudad` y engancha un **listener
delegado** sobre el contenedor. No queda interpolación dentro de `onclick`. El plan pedía
exactamente eso. **T1.7 lo verifica con un test y sigue adelante**; reimplementarlo es
trabajo duplicado y riesgo de regresión.

**B11 (el filtro renumeraba el ranking): HECHO.** `app.py:5767` fija `c.rank` una sola vez
sobre el catálogo completo y `app.py:5802` lo lee con `(c.rank != null) ? c.rank : 0`.

### 0.3 Corrección al diagnóstico

El plan dice que `new Set` colapsa los duplicados. Es cierto pero incompleto: el
`[...new Set(CIUDADES_MX)]` de `app.py:5759` colapsa por **cadena exacta**, mientras la
comparación contra el panel de `app.py:5757` normaliza a minúsculas. Resultado: los 50
duplicados exactos se colapsan, pero `Tehuacán`/`Tehuacan`, `Los Mochis`/`Mochis` o
`La Paz`/`La Paz BCS` **siguen siendo dos entradas y dos consultas a Places**. El
diagnóstico del plan se confirma; la cifra sube de "~250" a **293**.

### 0.4 Supuestos vigentes

`SUPUESTO: el catálogo objetivo es de 400-600 ciudades (los municipios ferreteros
relevantes), no todo municipio con al menos una ferretería en DENUE (serían miles) — afecta
Plan 1, Tareas T1.4 y T1.7.` Ver **D3** en DECISIONES PENDIENTES del índice.

`SUPUESTO: el gate humano de T1.8 lo resuelve el owner sobre el top-20 escrito, sin
herramienta intermedia — afecta Plan 1, Tarea T1.8.`

---

## 1. EL PROBLEMA, CON EVIDENCIA

### 1.1 El orden actual mide a NIOVAL, no al mercado

`app.py:848-855` calcula la relevancia así:

```python
max_total = max((r['total'] for r in result), default=1)
for r in result:
    r['relevancia'] = round(
        r['interes_pct'] * 1.5 +          # % de aprobados sobre llamados por NIOVAL
        (r['total'] / max_total) * 40 +   # contactos que NIOVAL ya tiene en la hoja
        min(r['llamados'] * 2, 20), 1     # llamadas que NIOVAL ya hizo
    )
```

Los **tres** términos son endógenos: salen de `LISTA DE CONTACTOS` y de las respuestas del
formulario. Ninguno mide qué tan importante es la ciudad **en el ramo de ferretería y
distribución ferretera en México**.

Consecuencias medibles y reproducibles:

| Síntoma | Causa exacta |
|---|---|
| Una ciudad donde NIOVAL nunca ha trabajado tiene `relevancia = 0` | `interes_pct=0`, `total=0`, `llamados=0` → los tres términos valen 0 |
| Todas las ciudades vírgenes empatan en 0 y se ordenan de forma arbitraria | `sort` de Python es estable: conservan el orden de inserción, que en el importador viene del array JS escrito a mano |
| Un pueblo con 3 contactos y 1 aprobado supera a Guadalajara sin tocar | `interes_pct` de 33.3 × 1.5 = 50 pts contra 0 |
| El ranking se vuelve circular | Ordenar por "donde ya trabajamos" hace que solo se trabaje donde ya se trabajaba |

El importador además **no usa** ese ranking para las ciudades sin datos: las inyecta con
`relevancia: 0` desde el frontend (`app.py:4801-4806`) y las manda al fondo de la lista.

### 1.2 El catálogo de ciudades está escrito a mano y está sucio

`app.py:4727` abre `const CIUDADES_MX = [...]`, un array JS de ~250 entradas tecleadas a
mano. Problemas verificados leyendo el array:

- **Duplicados exactos**: `Tepic`, `Mazatlán`, `Culiacán`, `Los Mochis`, `Colima`,
  `Guadalajara`, `Zapopan`, `Tlaquepaque`, `Tonalá`, `Tlajomulco`, `Puerto Vallarta`,
  `Ensenada`, `Tijuana`, `Mexicali`, `Hermosillo`, `Ciudad Obregón`, `Navojoa`,
  `Fresnillo`, `Jerez`, `Pachuca`, `Monclova`, `Piedras Negras`, `Acuña`, `Irapuato`,
  `Celaya`, `León`, `Ecatepec`, `Tlalnepantla`, `Naucalpan`, `Cuernavaca`, `Oaxaca`,
  `Chilpancingo`, `Acapulco`, `Campeche`, `Mérida`, `Cancún`, `Durango`, `Zacatecas`,
  `Aguascalientes`, `Saltillo`, `Torreón`, `Villahermosa`, `Apodaca`, `Escobedo`.
  El `new Set` de `app.py:4800` los colapsa, pero solo si la cadena es idéntica.
- **Variantes que el `Set` NO colapsa**: `Tehuacán` / `Tehuacan`, `Los Mochis` / `Mochis`,
  `La Paz` / `La Paz BCS`, `Guadalupe` / `Guadalupe NL` / `Guadalupe Zacatecas`,
  `San Nicolás de los Garza` / `San Nicolás`, `Victoria de Durango` / `Durango`.
  Son la **misma ciudad contada dos veces**, y generan dos búsquedas distintas en Places.
- **Sufijos desambiguadores que viajan a Google Places**: `Cuauhtémoc Chih`,
  `Tonalá Chis`, `Allende NL`, `Juárez NL`, `Tula Tamps`, `Loreto Zac`, `Santiago Ixc`,
  `La Paz BCS`, `Guadalupe NL`. `_worker_importador` los concatena tal cual en la query
  (`app.py:4332-4336`: `f"{categoria} en {ciudad}"`), o sea que se le pide a Places
  `"Ferreterías en Santiago Ixc"`. Nadie escribe eso; los resultados degradan en silencio.
- **Cobertura sin criterio**: faltan municipios ferreteros reales y sobran localidades sin
  relevancia para el ramo. No hay regla que diga qué entra y qué no.

### 1.3 Lo que el owner pidió

Dos cosas, y son independientes:

1. **Ordenar por relevancia nacional en el ramo ferretero**, no por historial de NIOVAL.
2. **Contemplar todas las ciudades de la región** — el catálogo debe ser exhaustivo y
   agrupado por macro-región, no una lista tecleada a mano.

---

## 2. OBJETIVO Y ALCANCE

**Objetivo.** Que el importador ordene las ciudades por un puntaje de **dos factores
explícitos y auditables**:

```
prioridad = potencial_mercado_ferretero  (exógeno, nacional, 0-100)
          × factor_desempeno_nioval      (endógeno, 0.5-1.5, ajusta pero no domina)
```

sobre un **catálogo canónico, deduplicado y agrupado por macro-región** que cubra México
completo.

### En alcance
- Catálogo versionado `datos/ciudades_mx.json` (nombre canónico, estado, macro-región,
  clave INEGI, alias, indicadores del potencial).
- Modelo de puntuación documentado, con las fuentes de cada indicador citadas.
- Endpoint nuevo `/api/importador/ciudades` que fusiona catálogo + métricas del panel.
- Cambio del cálculo en `/api/prospectos/ciudades` **sin romper el dashboard**.
- Filtro por macro-región y explicación por ciudad de por qué quedó donde quedó.
- Eliminación del array `CIUDADES_MX` de `app.py`.

### Fuera de alcance
- Rediseño visual del importador → **Plan 4**.
- Bugs de conteo y pantallas de carga → **Plan 3**.
- Reducción del costo de Google Places → **Plan 2**.

### Criterios de éxito (medibles)

| # | Criterio | Cómo se mide |
|---|---|---|
| CE1 | Cero duplicados en el catálogo | Test: `len(claves) == len(set(claves_inegi))` sobre `ciudades_mx.json` |
| CE2 | Cero sufijos desambiguadores en el nombre que va a Places | Test: ningún nombre canónico casa `/ (NL\|Chih\|Chis\|Tamps\|Zac\|BCS\|Ixc)$/` |
| CE3 | Toda ciudad tiene estado y macro-región | Test: ningún registro con `estado` o `region` vacíos |
| CE4 | Cobertura nacional | El catálogo incluye ≥1 ciudad de las 32 entidades federativas |
| CE5 | El ranking cambia respecto al actual | Snapshot: el top-20 nuevo difiere del actual en ≥8 posiciones |
| CE6 | Ninguna ciudad virgen queda en 0 | Test: toda ciudad del catálogo tiene `potencial_mercado > 0` |
| CE7 | El desempeño NIOVAL ajusta pero no domina | Test: una ciudad con `interes_pct=100` y `total=1` no supera a una de potencial alto sin historial |
| CE8 | El dashboard no se rompe | Los tests existentes de `/api/prospectos/ciudades` siguen en verde **sin modificarse** |
| CE9 | Baseline sin regresiones | `python -m pytest tests/` ≥ 357 passed |
| CE10 | El owner reconoce el top-20 | Gate humano: el owner valida la lista contra su conocimiento del mercado |

---

## 3. TAREAS

> **Formato blueprint.** Cada tarea es autocontenida: un subagente de Opus en sesión fría
> la ejecuta leyendo solo su propio bloque, sin haber visto el resto del documento.

### T1.0 — Tarea Cero: rama y respaldo *(bloquea todo)*

**Depende de:** nada. **Bloquea a:** T1.1–T1.9.

**Contexto autocontenido.** El proyecto es `C:\Users\PC 1\PanelNioval`, un panel Flask que
lee y escribe Google Sheets. `main` tiene auto-deploy: **nunca se trabaja ahí**. Antes de
tocar nada, las hojas se respaldan porque los cambios de este plan afectan cómo se ordenan
y consultan los contactos.

**Qué hacer.**
1. `git checkout main && git pull` y crear `feat/relevancia-ciudades-nacional`.
2. Ejecutar `python tools/respaldar_hojas.py`. El respaldo cae en
   `docs/auditoria/respaldos/`, que está en `.gitignore` porque lleva datos de clientes.
3. Confirmar que el respaldo **existe antes de seguir**: listar el archivo y su tamaño.
   Regla del entorno: el respaldo existe antes del cambio, no después.
4. Registrar el baseline: `python -m pytest tests/ -q`, anotar el número exacto de passed.

**Criterio de cierre.** Rama creada, respaldo listado en disco con tamaño > 0, baseline
anotado en la tabla PROGRESO.

---

### T1.1 — Recuperar el contexto histórico del importador

**Depende de:** T1.0.

**Contexto autocontenido.** El importador de prospectos tiene historia previa en este
proyecto: se migró desde un script suelto, se le agregó escape de fórmulas de Sheets, se
corrigió la columna CONTACTO y se desplegó la `GMAPS_API_KEY` en el VPS el 2026-08-27. Esa
historia vive en la memoria persistente de claude-mem, no en el repo.

**Qué hacer.** Recuperar de claude-mem todo lo relacionado con: el importador, la lista de
ciudades, el algoritmo de relevancia y decisiones previas sobre territorio. Buscar en
particular la observación que ya registra que *"City Relevance Algorithm Uses Only Existing
Contact Sheet Data — Not Industry Importance"*. Producir un resumen de una página con lo que
ya se decidió y no debe re-litigarse.

**Salida.** `docs/investigacion/2026-08-27-contexto-previo-importador.md`.

**Criterio de cierre.** El documento cita al menos 5 observaciones previas con su ID.

---

### T1.2 — Investigación: qué hace relevante a una ciudad en el ramo ferretero mexicano

**Depende de:** T1.1.

**Contexto autocontenido.** NIOVAL es una **distribuidora mayorista de ferretería y
plomería**. Sus prospectos son ferreterías y distribuidoras ferreteras. Hay que decidir qué
indicadores públicos y verificables predicen que una ciudad tenga muchos prospectos buenos.

**Qué hacer.**
1. Identificar y documentar indicadores objetivos con fuente citable. Candidatos a evaluar:
   - **DENUE / INEGI**: unidades económicas del ramo (SCIAN 467111 "Comercio al por menor
     en ferreterías y tlapalerías" y los códigos mayoristas 4671\*). Es el indicador más
     directo: cuenta ferreterías reales por municipio.
   - **Población municipal** (Censo INEGI) — proxy de demanda.
   - **Actividad de construcción** (ENEC / valor de producción por entidad) — el ramo
     ferretero sigue a la construcción.
   - **PIB estatal y unidades económicas totales** — tamaño de la economía local.
   - **Corredores logísticos y cabeceras de distribución** — una ciudad puede tener pocas
     ferreterías y aun así ser centro de reparto regional.
2. Para cada indicador: fuente, año, granularidad (municipal o estatal) y si es descargable
   como archivo abierto.
3. **No inventar cifras.** Si un indicador no se obtiene con fuente verificable, se descarta
   y se documenta por qué. Un número plausible sin fuente no es un dato.

**Salida.** `docs/investigacion/2026-08-27-relevancia-ferretera-mexico.md` con una tabla
Indicador · Fuente · Año · Granularidad · Peso propuesto · Cómo se obtiene.

**Criterio de cierre.** Mínimo 3 indicadores con fuente verificable y ruta de descarga
comprobada. Cada cifra del documento tiene su fuente al lado.

---

### T1.3 — Diseñar el modelo de puntuación (decisión con tradeoff)

**Depende de:** T1.2.

**Contexto autocontenido.** Con los indicadores de T1.2 hay que decidir la fórmula. Es una
decisión ambigua con más de una respuesta válida: cuánto pesa el mercado frente al historial
propio, si el historial multiplica o suma, y qué hacer con ciudades donde NIOVAL ya fracasó
(¿bajan de prioridad, o suben porque el mercado es grande y el fallo fue de ejecución?).

**Qué hacer.**
1. Formular al menos 3 modelos candidatos con pesos distintos.
2. Someterlos a un panel de decisión estructurado, con voces contrarias — no consenso fácil.
3. Elegir uno y **escribir por qué se descartaron los otros dos**.
4. Congelar la fórmula en un ADR.

**Restricción de diseño no negociable.** Ninguna ciudad del catálogo puede quedar en
`potencial_mercado = 0`: eso reintroduce el empate arbitrario que este plan corrige.

**Salida.** `docs/adr/2026-08-27-modelo-relevancia-ciudades.md`.

**Criterio de cierre.** ADR con la fórmula, los pesos, los 3 candidatos y el criterio de
desempate documentado.

---

### T1.4 — Construir el catálogo canónico `datos/ciudades_mx.json`

**Depende de:** T1.3.

**Contexto autocontenido.** Hay que reemplazar el array JS de `app.py:4727` por un archivo
de datos versionado. Forma de cada registro:

```json
{
  "nombre": "Los Mochis",
  "estado": "Sinaloa",
  "clave_inegi": "25006",
  "region": "Noroeste",
  "alias": ["Mochis", "Ahome"],
  "potencial_mercado": 62.4,
  "indicadores": { "unidades_ferreteras": 148, "poblacion": 273988 }
}
```

`nombre` es exactamente lo que se le manda a Google Places: **sin sufijos** tipo `NL`,
`Chih`, `BCS`. `alias` sirve para reconciliar los nombres viejos ya escritos en
`LISTA DE CONTACTOS` con el nombre canónico.

**Qué hacer.**
1. Generar el catálogo desde las fuentes de T1.2 con un script reproducible en
   `tools/generar_catalogo_ciudades.py`. El JSON se versiona, pero el script debe poder
   regenerarlo cuando INEGI publique datos nuevos.
2. Deduplicar por clave INEGI, no por cadena.
3. Mapear las ~250 entradas actuales del array a su nombre canónico. **Toda entrada actual
   debe tener destino**; si alguna no mapea, se reporta, no se descarta en silencio.
4. Asignar macro-región a cada municipio. Ocho macro-regiones: Noroeste, Noreste, Occidente,
   Centro-Norte, Centro-Sur, Valle de México, Sureste, Península.

**TDD — estos tests se escriben ANTES del script** (`tests/test_catalogo_ciudades.py`):
- `test_sin_duplicados_por_clave_inegi`
- `test_sin_duplicados_por_nombre_normalizado` (sin acentos, minúsculas)
- `test_ningun_nombre_lleva_sufijo_desambiguador`
- `test_toda_ciudad_tiene_estado_y_region`
- `test_las_32_entidades_estan_representadas`
- `test_todo_potencial_es_mayor_que_cero`
- `test_toda_ciudad_del_array_viejo_mapea_a_una_canonica`

**Criterio de cierre.** Los 7 tests en verde. El JSON carga y valida en < 50 ms.

---

### T1.5 — Endpoint `/api/importador/ciudades`

**Depende de:** T1.4.

**Contexto autocontenido.** Hoy el frontend del importador (`app.py:4795-4816`) llama a
`/api/prospectos/ciudades`, filtra, y fusiona a mano con el array estático. Esa lógica se
mueve al backend, que es donde puede probarse.

**Qué hacer.** Endpoint que devuelve el catálogo completo enriquecido:

```json
[{ "ciudad": "León", "estado": "Guanajuato", "region": "Occidente",
   "potencial_mercado": 84.1, "desempeno_nioval": 1.12, "prioridad": 94.2,
   "total": 37, "llamados": 12, "aprobados": 4, "interes_pct": 33.3,
   "explicacion": "Alto potencial ferretero · 37 contactos · 33% de interés" }]
```

Ordenado por `prioridad` descendente. `explicacion` es texto ya armado en el backend, para
que la UI no tenga que reconstruir el razonamiento y para que el ranking sea auditable.

**Reconciliación obligatoria.** Los nombres de ciudad en `LISTA DE CONTACTOS` están escritos
a mano y llegan por `str_val(c.get('CIUDAD', ...)).title().strip()` (`app.py:807`). Hay que
casarlos contra `nombre` + `alias`. Lo que no case va a un grupo `"Sin clasificar"`
**visible**: nada se pierde en silencio.

**TDD.** Tests de: orden por prioridad; reconciliación por alias; ciudad de la hoja que no
existe en el catálogo; catálogo íntegro cuando la hoja está vacía.

**Gate de verificación.** `python-reviewer` + `code-reviewer`. `security-reviewer` porque el
endpoint deriva de la hoja de clientes: verificar que devuelve solo agregados por ciudad y
no filtra teléfonos ni nombres de contacto.

---

### T1.6 — Nuevo cálculo en `/api/prospectos/ciudades` sin romper el dashboard

**Depende de:** T1.5.

**Contexto autocontenido.** `app.py:848-855` calcula `relevancia`. El dashboard la consume
en `getSortedCiudades()` (`app.py:2150-2157`) y su tabla permite ordenar por cualquier
columna. Cambiar el significado del campo sin avisar rompe la lectura del owner.

**Qué hacer.**
1. Añadir `potencial_mercado`, `desempeno_nioval` y `prioridad` al payload.
2. **Mantener `relevancia`** tal como está, por compatibilidad, marcada obsoleta en un
   comentario con fecha de retiro.
3. En el dashboard, añadir las columnas nuevas y ordenar por `prioridad` por defecto.

**Gate.** Los tests existentes que tocan `/api/prospectos/ciudades` deben pasar **sin
modificarse**. Si alguno hay que tocarlo, es ruptura de contrato: se documenta y se justifica.

---

### T1.7 — UI: filtro por macro-región y transparencia del ranking

**Depende de:** T1.5, T1.6.

**Contexto autocontenido.** El importador (`app.py:4830-4843`) pinta chips de ciudad con
medalla 🥇🥈🥉 y un badge de porcentaje. Con México completo la lista pasa de ~250 a varios
cientos de entradas: sin filtro por región queda inusable.

**Qué hacer.**
1. Selector de macro-región (8 + "Todas") que filtra los chips.
2. Contador por región: "Occidente (87)".
3. El chip muestra al pasar el mouse la `explicacion` que ya viene del backend.
4. Borrar el array `CIUDADES_MX` de `app.py` y su fusión en JS.
5. **Escapar el nombre de ciudad** antes de meterlo en el atributo `onclick`. `app.py:4840`
   lo interpola crudo: `onclick="seleccionarCiudad('${c.ciudad}',this)"`. Un apóstrofo en un
   nombre venido de la hoja rompe el handler. Usar `dataset` y un listener delegado, no
   interpolación de cadenas dentro de HTML.

> El punto 5 es también hallazgo del **Plan 3 (T3.8)**. Si el Plan 3 ya se ejecutó,
> verificar que está aplicado y **no duplicar** el arreglo.

**Gate.** `code-reviewer` + `security-reviewer` (interpolación en HTML con datos de hoja).

---

### T1.8 — Verificación integral

**Depende de:** T1.4–T1.7.

**Qué hacer.**
1. `python -m pytest tests/` → ≥ 357 passed, sin regresiones.
2. Verificación funcional en navegador: cargar `/importador`, confirmar que el filtro por
   región funciona, que no hay ciudades duplicadas visibles y que el chip #1 es defendible.
3. **Comprobar el barrido en las dos direcciones**: buscar en la lista renderizada una
   ciudad que se sabe que debe estar (p. ej. León) **y** confirmar que una que se sabe
   duplicada en el array viejo (p. ej. `Los Mochis`) ahora aparece **una** sola vez. Un
   filtro que no encuentra nada no prueba que no haya nada.
4. Prueba de que el modelo hace lo prometido: una ciudad de potencial alto y cero historial
   debe rankear por encima de una de potencial bajo con un aprobado.

**Gate humano (owner).** El owner revisa el top-20 nacional y confirma que reconoce esas
plazas como las relevantes del ramo. **Si no las reconoce, la tarea no cierra**: se vuelve a
T1.3 a reajustar pesos.

---

### T1.9 — Cierre

**Depende de:** T1.8.

**Qué hacer.** Actualizar `CLAUDE.md` (baseline nuevo de tests, mención del catálogo),
`docs/RUNBOOK.md` (cómo regenerar el catálogo), commits convencionales en español, PR con
`gh pr create --base main`, y guardar contexto para la siguiente sesión.

**Gate de merge.** Baseline verde + reviews sin CRITICAL/HIGH abiertos. Nada se mergea con
la suite en rojo.

---

## 4. TABLA DE ASIGNACIÓN DE HERRAMIENTAS POR ETAPA

| Etapa | Tarea | Herramienta asignada | Tipo | Fuente | Por qué es la mejor |
|---|---|---|---|---|---|
| A | T1.1 | `claude-mem:mem-search` | skill | claude-mem | El proyecto tiene 50+ observaciones previas; una ya diagnostica este mismo problema. Recuperarla evita re-investigar desde cero. |
| A | T1.1 | `claude-mem:timeline-report` | skill | claude-mem | Da la línea de tiempo del importador desde su migración, no hits sueltos. |
| A | T1.1 | `Explore` | agente | built-in | Barrido del codebase para encontrar todos los consumidores de `relevancia` sin quemar contexto de la sesión principal. |
| A | T1.2 | `market-research` | skill | ECC | Investigación de mercado con atribución de fuente obligatoria — exactamente lo que exige "no inventar cifras". |
| A | T1.2 | `market-researcher` | agente | catalogo-agentes | Dimensionamiento de mercado y comportamiento sectorial; aporta criterio de analista sobre la skill. |
| A | T1.2 | `data-researcher` | agente | catalogo-agentes | Descubrir y **validar** datasets (DENUE, Censo) y dejarlos listos para el pipeline de T1.4. |
| A | T1.2 | `deep-research` | skill | ECC | Investigación multi-fuente con citas cuando DENUE no baste para un indicador. |
| A | T1.2 | `ads-math` **[OPCIONAL]** | skill | claude-ads | *Condición:* si el owner quiere dimensionar el **costo por prospecto** de abrir plaza nueva. Es calculadora de break-even/CPA que funciona con datos pegados, sin API. Ver §7 sobre el resto de la suite. |
| B | T1.3 | `council` | skill | community | El peso mercado-vs-historial es un tradeoff real sin respuesta única: panel de 4 voces con desacuerdo estructurado. |
| B | T1.3 | `superpowers:brainstorming` | skill | superpowers | Explorar la intención antes de fijar la fórmula: qué significa "relevante" para el owner. |
| B | T1.3 | `architecture-decision-records` | skill | ECC | Congela decisión y alternativas descartadas en un ADR de formato estable. |
| B | T1.3 | `first-principles-thinking` | agente | catalogo-agentes | Rompe el supuesto heredado de que la relevancia se deriva del historial propio. |
| B | T1.4, T1.5 | `blueprint` | skill | community | Estándar de esta plantilla: brief autocontenido por paso para que un agente frío ejecute cualquiera. |
| B | T1.5 | `api-designer` | agente | catalogo-agentes | Contrato del endpoint diseñado antes de codearlo, no después. |
| C | T1.4 | `superpowers:test-driven-development` | skill | superpowers | Los 7 tests del catálogo se escriben antes del generador (RED-GREEN-REFACTOR). |
| C | T1.4 | `tdd-guide` | agente | catalogo-agentes | Hace cumplir tests-primero y vigila cobertura ≥80%. |
| C | T1.4–T1.6 | `python-pro` | agente | catalogo-agentes | Implementación idiomática del stack real (Flask + Python 3.11). |
| C | T1.4 | `python-patterns` | skill | ECC | Idiomas Python y type hints al escribir el generador del catálogo. |
| C | T1.5, T1.6 | `backend-patterns` | skill | ECC | Patrones de endpoint, forma de respuesta y manejo de error del lado servidor. |
| C | T1.7 | `frontend-patterns` | skill | ECC | Filtro por región y render de chips sin reintroducir interpolación insegura. |
| C | T1.4 | `xlsx` **[OPCIONAL]** | skill | skills-local (ver nota §4.1) | *Condición:* si INEGI entrega el dataset en `.xlsx` y hay que leerlo para generar el JSON. |
| D | T1.4–T1.7 | `python-reviewer` | agente | catalogo-agentes | Reviewer del stack: PEP 8, type hints, idiomas Python. Se suma al code-reviewer, no lo reemplaza. |
| D | T1.4–T1.7 | `code-reviewer` | agente | catalogo-agentes | Review general obligatorio después de escribir o modificar código. |
| D | T1.5, T1.7 | `security-reviewer` | agente | catalogo-agentes | Obligatorio: el endpoint deriva de datos de clientes y la UI interpola nombres en HTML. |
| D | T1.5, T1.7 | `silent-failure-hunter` | agente | catalogo-agentes | La reconciliación de nombres es el sitio ideal para que algo se descarte sin avisar; su trabajo es cazar justo eso. |
| D | T1.4–T1.6 | `python-testing` | skill | ECC | pytest, fixtures, parametrización y cobertura sobre catálogo y endpoint. |
| D | T1.6 | `pr-test-analyzer` | agente | catalogo-agentes | Comprueba que los tests cubren comportamiento real, no solo que el JSON parsea. |
| D | T1.7, T1.8 | `webapp-testing` | skill | skills-local (ver nota §4.1) | Verificación funcional en navegador real con Playwright: el filtro por región funciona de verdad. |
| D | T1.8 | `superpowers:verification-before-completion` | skill | superpowers | Gate final: nada se declara resuelto sin comando ejecutado y salida confirmada. |
| D | T1.8 | `verification-loop` | skill | ECC | Sistema de verificación de sesión completa antes del PR. |
| E | T1.9 | `doc-updater` | agente | catalogo-agentes | Actualiza `CLAUDE.md`, RUNBOOK y codemaps al cerrar. |
| E | T1.9 | `github-ops` | skill | ECC | PR con historial completo y formato convencional. |
| E | T1.9 | `superpowers:finishing-a-development-branch` | skill | superpowers | Decide merge / PR / cleanup con los gates puestos. |
| E | T1.9 | `claude-mem:babysit` **[OPCIONAL]** | skill | claude-mem | *Condición:* si el PR queda abierto esperando CI o review del owner. |
| E | T1.9 | `handoff` | skill | skills-local (ver nota §4.1) | Deja el contexto comprimido para la siguiente sesión. |

**Fuentes canónicas usadas: 6 de 6** — catalogo-agentes, ECC, community, claude-mem,
superpowers y claude-ads (opcional, justificado en §7), más built-in.

### 4.1 Nota de honestidad sobre la etiqueta `skills-local`

El Nivel 2 de la biblioteca usa una etiqueta de fuente más fina que la tabla de Fuentes del
encabezado: `skills-local`, que **no es una de las 6 fuentes canónicas**. Mapearla a una de
las 6 sería inventar el dato. Se reporta tal cual aparece en el inventario y **no cuenta**
para el mínimo de diversidad. El plan cumple el mínimo sin ella.

---

## 5. GATES DE VERIFICACIÓN POR TAREA

| Tarea | Tests | Reviewer del stack | code-reviewer | security-reviewer | Baseline |
|---|---|---|---|---|---|
| T1.0 | — (registra baseline) | — | — | — | ✅ anota el número |
| T1.1 | — (documental) | — | — | — | — |
| T1.2 | — (documental, fuentes citadas) | — | — | — | — |
| T1.3 | — (ADR) | — | — | — | — |
| T1.4 | ✅ TDD, 7 tests nuevos | python-reviewer | ✅ | — | ✅ sin regresiones |
| T1.5 | ✅ TDD, 4 tests nuevos | python-reviewer | ✅ | ✅ datos de clientes | ✅ sin regresiones |
| T1.6 | ✅ los existentes, sin tocar | python-reviewer | ✅ | — | ✅ sin regresiones |
| T1.7 | ✅ webapp-testing | — | ✅ | ✅ interpolación en HTML | ✅ sin regresiones |
| T1.8 | ✅ suite completa + gate humano del owner | ✅ | ✅ | ✅ | ✅ ≥357 passed |
| T1.9 | ✅ suite completa antes del merge | — | ✅ | — | ✅ verde para mergear |

---

## 6. RIESGOS Y ROLLBACK

| # | Riesgo | Prob. | Impacto | Mitigación | Rollback |
|---|---|---|---|---|---|
| R1 | DENUE no da detalle municipal para el SCIAN ferretero | Media | Alto — se cae el indicador principal | T1.2 valida la descarga **antes** de diseñar el modelo; si falla, se usa población + construcción y se documenta la degradación | Ninguno: el riesgo se materializa en investigación, antes de tocar código |
| R2 | Nombres de ciudad de la hoja que no casan con el catálogo | **Alta** | Medio — contactos que desaparecen del ranking | Grupo `"Sin clasificar"` **visible** más `alias` en el catálogo. Nunca descartar en silencio | Revertir el commit del endpoint; el dashboard vuelve a `relevancia` |
| R3 | El ranking nuevo contradice la intuición del owner | Media | Alto — se deja de usar la herramienta | Gate humano en T1.8 antes de mergear; el campo `explicacion` hace auditable cada posición | Volver a T1.3 y reajustar pesos; el ADR documenta el cambio |
| R4 | Cientos de ciudades hacen inusable la lista de chips | Alta | Medio | Filtro por macro-región obligatorio (T1.7) + el buscador que ya existe | Limitar el render a top-N por región |
| R5 | Cambiar `relevancia` rompe el dashboard | Media | Alto | T1.6 **conserva** el campo viejo; los tests existentes no se tocan | `git revert` del commit de T1.6 |
| R6 | El JSON del catálogo crece y ralentiza el arranque | Baja | Bajo | Test de carga en <50 ms; se lee una vez y se cachea | Cargar bajo demanda |

**Rollback general.** Toda la rama es `feat/relevancia-ciudades-nacional`. Si algo sale mal
tras el merge, `git revert` del merge commit devuelve el array estático y la fórmula vieja,
que son autocontenidos. **`datos/ciudades_mx.json` no se borra, se conserva** — apartar, no
borrar (regla 4 del entorno).

---

## 7. EVALUACIÓN DE LA SUITE claude-ads

**Obligatorio evaluarla; esta es la evaluación por escrito.**

`claude-ads` (~60 herramientas: `ads-google`, `ads-meta`, `ads-tiktok`, `ads-linkedin`,
`ads-audit`, la familia `audit-*`, `copy-writer`, `creative-strategist`, `visual-designer`,
`format-adapter`) está construida sobre un supuesto que este plan **no cumple**: que existe
una cuenta publicitaria con campañas, píxeles y creatividades que auditar. NIOVAL no compra
medios pagados en este flujo; el importador es prospección en frío sobre Google Places, no
adquisición pagada. `ads-dna`, `ads-creative`, `ads-competitor` y toda la familia `audit-*`
no tienen sujeto sobre el cual operar aquí.

**La única pieza con encaje real es `ads-math`**, calculadora financiera de PPC que
explícitamente *"no requiere acceso a API y funciona con datos pegados"*. Su modelo de CPA y
break-even se traduce sin forzarlo a "cuánto cuesta abrir una plaza nueva": costo de Places
por ciudad ÷ prospectos aprobados = costo por prospecto. Queda **[OPCIONAL]** con su
condición de uso en §4, y es de uso **obligatorio** en el Plan 2, donde el costo es el
sujeto del plan.

---

## 8. PROGRESO

| # | Tarea | Estado | Evidencia (commit/test/PR) | Fecha |
|---|---|---|---|---|
| T1.0 | Tarea Cero: rama y respaldo | PENDIENTE | | |
| T1.1 | Contexto histórico del importador | PENDIENTE | | |
| T1.2 | Investigación: relevancia ferretera en México | PENDIENTE | | |
| T1.3 | Diseño del modelo de puntuación (ADR) | PENDIENTE | | |
| T1.4 | Catálogo canónico `datos/ciudades_mx.json` | PENDIENTE | | |
| T1.5 | Endpoint `/api/importador/ciudades` | PENDIENTE | | |
| T1.6 | Nuevo cálculo en `/api/prospectos/ciudades` | PENDIENTE | | |
| T1.7 | UI: filtro por macro-región y transparencia | PENDIENTE | | |
| T1.8 | Verificación integral + gate humano del owner | PENDIENTE | | |
| T1.9 | Cierre: docs, PR, handoff | PENDIENTE | | |

**Avance del plan: 0 / 10 tareas (0 %)**
