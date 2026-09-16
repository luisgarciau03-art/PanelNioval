# Estado de partida — Plan 1 (Tarea T1.0)

**Fecha de medición:** 2026-09-15 · **Rama:** `feat/relevancia-nacional-produccion`
(creada desde `origin/main`) · **Tanda:** 2026-09-15 · **Tarea:** T1.0

> Todo lo de este documento se **midió ejecutando comandos**, no leyendo documentos.
> Sustituye a la §0 del plan, que fue medida sobre otra rama.

---

## 1. Los cinco números

| # | Hecho | Valor medido | Comando |
|---|---|---|---|
| 1 | **Baseline de la suite** | **388 passed, 1 skipped**, exit 0 (49.4 s) | `python -m pytest tests/` |
| 2 | **`app.py`** | **6,098 líneas** | `wc -l app.py` |
| 3 | **SHA de `main`** | **`82995c3`** (`docs(tanda): decisiones E1-E4 del owner y handoff del Plan 1 (#41)`) | `git log --oneline origin/main -1` |
| 4 | **PR #42** | **OPEN · MERGEABLE · CLEAN** · head `499d41b` · 17 archivos · +12,345 / −138 · **ambos checks SUCCESS** | `gh pr view 42` |
| 5 | **Catálogo del PR #42** | **606 municipios** | `grep -c '"nombre"' ciudades_mx.json` |

Salida cruda del baseline: `docs/auditoria/respaldos/2026-09-15/baseline-T1.0-rama-produccion.txt`.

---

## 2. CORRECCIÓN DEL BASELINE — el 626 no aplica a esta rama

El bloque INVARIANTES de los cuatro planes fija el gate en **≥ 626 passed, 1 skipped**, y
T1.0 ordena *«si da menos de 626, parar y reportar — algo se rompió antes de empezar»*.

**No se rompió nada.** El 626 se midió sobre `fix/endurecimiento-panel` (PR #44), que va
**28 commits por delante de `main`**. Esa rama aporta cinco suites que en `main` **no
existen todavía**:

| Suite que sólo existe en `fix/endurecimiento-panel` | Líneas |
|---|---|
| `tests/test_endurecimiento_escape_formulas.py` | 663 |
| `tests/test_endurecimiento_limites.py` | 553 |
| `tests/test_endurecimiento_parada.py` | 415 |
| `tests/test_endurecimiento_salud.py` | 346 |
| `tests/test_endurecimiento_zona_horaria.py` | 462 |
| **Total añadido** | **2,447 líneas** |

Evidencia diferencial de que es un efecto por rama y no una regresión:

- `0 failed, 0 errors` en la corrida (exit 0).
- `git diff --diff-filter=D --name-only origin/main...origin/fix/endurecimiento-panel -- tests/`
  → **vacío**: no se borró ni un archivo de test.
- El hueco 388 → 626 lo explican íntegramente las 5 suites de arriba.

Esto es literalmente el **riesgo R5** del plan (*«`main` avanzó y el baseline ya no es 626»*),
cuya mitigación escrita es **medir y fijar el número real**, no detenerse. Y es la trampa que
`CLAUDE.md` ya documenta: *«El baseline es por rama… comparar siempre contra el baseline de la
rama base, no contra un número absoluto.»*

### Baseline vigente para esta tanda

| Rama base | Baseline | Vigencia |
|---|---|---|
| **`main` (`82995c3`)** | **388 passed, 1 skipped** | Planes 1 y 4 hasta que aterrice el PR #44 |
| `fix/endurecimiento-panel` | 626 passed, 1 skipped | Se recupera al mergear #44 (Plan 4, T4.6) |

**Gate operativo a partir de ahora:** `python -m pytest tests/` **≥ 388 passed, 1 skipped,
exit 0** sobre ramas basadas en `main`, más los tests que cada tarea añada. El ≥ 626 vuelve a
ser el gate en cuanto el PR #44 esté en `main`.

`SUPUESTO: el gate «≥ 626» de INVARIANTES se reinterpreta como «≥ baseline de la rama base», que hoy es 388. No se relaja el criterio: se corrige la referencia. — afecta los 4 planes.`

---

## 3. Otras diferencias contra la §0 del plan

| Dato | §0 del plan | Medido en `main` | Causa |
|---|---|---|---|
| `app.py` | 6,610 líneas | **6,098 líneas** | Las 512 de diferencia son del endurecimiento (PR #44), no de `main` |
| Baseline | 626 | **388** | Ver §2 |

El resto de la §0 se confirma sin cambios.

---

## 4. Estado de los tres PR abiertos

| PR | Rama | Commits sobre `main` | Estado | Nota |
|---|---|---|---|---|
| **#42** | `feat/relevancia-ciudades-nacional` | 8 | OPEN · MERGEABLE · CLEAN · CI verde | Lo aterriza este plan (T1.5) |
| **#43** | `feat/rediseno-panel` | 33 | OPEN · MERGEABLE | **Apilado sobre #42** — verificado con `git merge-base --is-ancestor` → contiene a #42 |
| **#44** | `fix/endurecimiento-panel` | 28 | OPEN · MERGEABLE **contra `main`** | Sus 5 conflictos son **contra #43**, no contra `main`. Se rebasa en Plan 4, T4.6 |

El apilamiento de #43 sobre #42 queda **confirmado en disco**, no asumido: es la razón del
orden de aterrizaje 1 → 4 → 3 → 2.

---

## 5. Riesgo R6 despejado por adelantado

R6 temía que regenerar el catálogo (T1.3) exigiera fuentes DENUE que no estuvieran en disco.
**No es el caso:** `tools/generar_catalogo_ciudades.py` **descarga las fuentes del INEGI en
tiempo de ejecución** y las cachea:

- DENUE 05_2026 ramas `46591-46911` (ferreterías y tlapalerías), sector `43` (mayoreo de
  materiales) y sector `23` (construcción).
- Censo 2020 ITER nacional (población municipal).

Además valida tamaño mínimo por archivo, porque *«el INEGI sirve archivos vacíos con HTTP
200»* — guarda ya escrita en el generador. El umbral de corte es el parámetro
`minimo_ferreterias` de `construir_catalogo()` (`tools/generar_catalogo_ciudades.py:391-393`),
un solo valor: bajarlo es cambiar un argumento y regenerar, tal como T1.3 supone.

**Consecuencia:** T1.3 es viable. La condición que queda es conectividad con el INEGI y el
tiempo de descarga (~50 MB el archivo de ferreterías).

---

## 6. Respaldo (existe ANTES de tocar código)

`docs/auditoria/respaldos/2026-09-15/`:

| Archivo | Qué es |
|---|---|
| `app.py` | Copia de `app.py` en `main` (6,098 líneas) |
| `ciudades_mx.json` | Catálogo de 606 municipios, extraído de la rama del PR #42 |
| `baseline-T1.0-rama-produccion.txt` | Salida cruda de `pytest` con su exit code |

**Nada se borró.** Criterio de cierre de T1.0 cumplido: el documento y el respaldo existen
antes de que ninguna tarea toque código.

---

## 7. Ancla de la tarea siguiente

```
ANCLA · Plan 1 Tarea T1.1 · importador nacional barato veraz profesional · avance 1/8 ·
 gates: >=5 decisiones cerradas con fuente (ADR o ID de observacion) · baseline: python -m pytest tests/
```
