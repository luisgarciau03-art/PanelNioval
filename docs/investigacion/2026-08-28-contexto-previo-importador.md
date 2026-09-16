# CONTEXTO PREVIO DEL IMPORTADOR — LO QUE YA SE DECIDIÓ

**Tarea:** Plan 1 · T1.1 · **Fecha:** 2026-08-28 · **Rama:** `feat/relevancia-ciudades-nacional`
**Fuente:** memoria persistente de claude-mem (`mcp-search`) + verificación contra el código en disco.

> Propósito: que el Plan 1 no vuelva a litigar lo ya decidido ni re-descubra lo ya
> diagnosticado. Todo lo de abajo **está respaldado por una observación con ID**, y los
> anclajes `archivo:línea` se **reverificaron hoy** contra `app.py` (6,098 líneas), porque
> los de las observaciones son de cuando el archivo tenía 4,948.

---

## 1. Observaciones recuperadas (8, con ID)

| ID | Fecha | Qué fija |
|---|---|---|
| **#17365** | 2026-08-27 | *City Relevance Algorithm Uses Only Existing Contact Sheet Data — Not Industry Importance.* La observación que el plan pedía localizar. |
| **#17405** | 2026-08-27 | *City Relevance Root Cause: Fully Endogenous Scoring.* Causa raíz con los seis hechos medidos. |
| **#17391** | 2026-08-27 | *Fórmula de relevancia basada en datos CRM internos.* Establece que **hay dos sistemas de orden distintos**, no uno. |
| **#17374** | 2026-08-27 | Arquitectura completa del importador: Places → Sheets con hilo daemon, filtros y dedupe. |
| **#17366** | 2026-08-27 | Arquitectura de la UI del importador: chips, medallas, polling cada 3 s. |
| **#17452** | 2026-08-27 | `LISTA DE CONTACTOS`: 7,145 registros; los nombres de columna de la hoja **no** son los internos del código. |
| **#17407** | 2026-08-27 | Creación del propio Plan 1: fórmula de dos factores y 10 tareas. |
| **#7109** | 2026-07-17 | Estacionalidad del ramo ferretero/construcción en México (proyecto SistemaLanzamiento). Contexto sectorial reutilizable. |

---

## 2. Lo que YA está decidido y no se re-litiga

### 2.1 El diagnóstico está cerrado (#17365, #17405, #17391)

La fórmula de `relevancia` es **totalmente endógena**: sus tres términos salen de
`LISTA DE CONTACTOS` y del formulario de llamadas. Verificado hoy en **`app.py:913-919`**
(las observaciones dicen `848-855`, anclaje de antes de los planes 0 y 2):

```python
r['relevancia'] = round(
    r['interes_pct'] * 1.5 +          # aprobados/llamados — endógeno
    (r['total'] / max_total) * 40 +   # contactos ya en la hoja — endógeno
    min(r['llamados'] * 2, 20), 1     # llamadas ya hechas — endógeno
)
```

Consecuencia ya demostrada, **no hay que volver a probarla**: toda ciudad virgen puntúa 0 y
el `sort` estable las deja en el orden de inserción del array escrito a mano.

### 2.2 Son DOS sistemas de orden, no uno (#17391) — es el hallazgo más caro de olvidar

- **Dashboard de prospectos:** `/api/prospectos/ciudades` → `getSortedCiudades()`
  (**`app.py:2213`**), tabla ordenable con `ciudadesSortCol = 'relevancia'` (**`app.py:2199`**).
- **Importador:** array JS `CIUDADES_MX` (**`app.py:5679`**) fusionado en el navegador con
  el endpoint anterior dentro de `cargarCiudades()` (**`app.py:5750-5780`**).

El Plan 1 toca **los dos**, y por eso T1.6 conserva el campo `relevancia`: quitarlo rompe la
lectura del dashboard aunque el importador quede perfecto.

### 2.3 El importador escribe por POSICIÓN, no por nombre de columna (#17452)

`LISTA DE CONTACTOS` tiene 7,145 registros. La columna 1 se llama `TIENDA` (el código la
trata como «Nombre»), la 7 `Domicilio` («Dirección») y la 4 `CONTACTO` (el teléfono). La
llave de deduplicación es `fila[1]|fila[7]`.

**Qué significa para T1.5:** la reconciliación de ciudad se hace contra el valor que ya lee
`str_val(c.get('CIUDAD', ...))`, no contra un nombre de columna que se pueda suponer. El
nombre de la hoja y el nombre interno **no coinciden** y suponerlo ya sería un error.

### 2.4 La arquitectura del importador no cambia en este plan (#17374, #17366)

Hilo daemon, estado global bajo `_import_lock`, polling cada 3 s, categorías fijas
`['Ferreterías', 'Distribuidoras Ferreterías']`, filtros de ≥5 reseñas / ≥3.5 estrellas /
con teléfono. **El Plan 1 no toca nada de esto**: cambia de dónde sale la lista de ciudades
y en qué orden se muestra. El rediseño de la UI es del **Plan 4**.

### 2.5 Ya hay una hipótesis sectorial escrita, y hay que tratarla como hipótesis (#17391, #7109)

#17391 propone que Monterrey, Querétaro, León, Aguascalientes y San Luis Potosí deberían
subir por perfil industrial-manufacturero. #7109 aporta estacionalidad del ramo (temporada
de lluvias, aguinaldo, Buen Fin).

⚠️ **Ninguna de las dos es un dato con fuente citable.** Entran a T1.2 como hipótesis a
verificar contra DENUE/INEGI, **no** como pesos del modelo. La regla del entorno manda: un
número plausible sin fuente no es un dato.

---

## 3. Lo que ya está HECHO en el código y T1.7 solo verifica

Reverificado hoy con `grep` sobre `app.py`, no con los números de línea de los documentos:

| Punto del plan | Estado | Evidencia en disco |
|---|---|---|
| **B9** — escapar el nombre de ciudad | ✅ **HECHO** | `escaparHtml` en `app.py:5787-5791`; `data-ciudad="${nombre}"` en `app.py:5810`; listener delegado en `app.py:5817-5824`. `seleccionarCiudad` ya no existe. |
| **B11** — rank fijo al filtrar | ✅ **HECHO** | `c.rank` se fija una vez sobre el catálogo completo en `app.py:5768`; `renderChips` lo lee con `(c.rank != null) ? c.rank : 0` en `app.py:5799`. |

**Reimplementarlos es trabajo duplicado y riesgo de regresión.** T1.7 los cubre con un test.

---

## 4. Medición del catálogo actual (hecha hoy, no heredada)

Extraído del array `CIUDADES_MX` (`app.py:5679`) por script, no a ojo:

| Métrica | Valor |
|---|---|
| Entradas literales | **293** |
| Únicas por cadena exacta | **238** (55 repeticiones sobrantes en 50 nombres) |
| Únicas normalizadas (minúsculas, sin acentos) | **237** |
| Con sufijo desambiguador que viaja a Places | **9** |

Los 9 con sufijo, textualmente: `Allende NL`, `Cuauhtémoc Chih`, `Guadalupe NL`,
`Juárez NL`, `La Paz BCS`, `Loreto Zac`, `Santiago Ixc`, `Tonalá Chis`, `Tula Tamps`.
`_worker_importador` los concatena en la query, o sea que hoy se le pide a Google Places
literalmente `"Ferreterías en Santiago Ixc"`.

**Matiz que corrige al plan original:** `[...new Set(CIUDADES_MX)]` (`app.py:5760`) colapsa
por cadena exacta, así que **sí** elimina las 55 repeticiones. Lo que **no** colapsa es la
diferencia de acento o de sufijo — 238 exactas contra 237 normalizadas prueba que al menos
un par difiere solo por acentuación, y los pares tipo `Los Mochis`/`Mochis` o
`La Paz`/`La Paz BCS` sobreviven como dos entradas y **dos consultas facturables a Places**.

---

## 5. Decisiones vigentes del owner que condicionan el Plan 1

| Decisión | Contenido | Efecto |
|---|---|---|
| Alcance geográfico (2026-08-27) | México completo agrupado por macro-región | 8 macro-regiones en T1.4 |
| **D3** (abierta, se asume **A**) | Catálogo de **400-600 ciudades** con presencia ferretera relevante | Tamaño objetivo de T1.4; sin paginación en T1.7 |
| **E4** (2026-08-28) | El Plan 1 arranca en sesión nueva | Esta sesión |
| Gate del owner #6 | Validación humana del top-20 | T1.8 no cierra sin él |

---

## 6. Lo que la memoria NO tiene, y por eso T1.2 existe

No hay ninguna observación con **datos de mercado ferretero mexicano con fuente citable**.
Lo único cercano es #7109, que es estacionalidad para una campaña de anuncios de otro
proyecto y no tiene granularidad municipal. **El indicador exógeno hay que ir a buscarlo**;
no está en la memoria del proyecto.
