# Reproducción documentada de los bugs del importador

**Plan:** 3 — Bug de conteo y pantallas de carga · **Tarea:** T3.0 (Tarea Cero)
**Fecha:** 2026-08-27
**Rama:** `fix/conteo-importador-y-estados-carga` (desde `main` en `034dd42`)
**Herramientas asignadas y usadas:** `claude-mem:mem-search` (claude-mem),
`superpowers:systematic-debugging` (superpowers).

> Un arreglo sin reproducción previa no se puede verificar. Este documento fija los
> números de **antes**, para poder comparar contra los de después en T3.8.

---

## 0. Estado de partida

| Hecho | Valor | Cómo se comprobó |
|---|---|---|
| Rama base | `main` @ `034dd42` | `git log --oneline -1` |
| Baseline de tests | **230 passed in 5.68s**, exit 0 | `python -m pytest tests/` |
| Respaldo previo al cambio | 5 XLSX + `huellas.json`, 65 hojas | `tools/respaldar_hojas.py` → `docs/auditoria/respaldos/2026-08-27/` |

Respaldo confirmado **en disco** antes de tocar nada:

```
bruce-seguimiento-...xlsx        105,337 bytes
contactos-frecuentes-...xlsx   2,183,435 bytes
huellas.json                      19,641 bytes
mensajes-...xlsx                 764,820 bytes
respuestas-...xlsx             1,734,576 bytes
ventas-...xlsx                   220,837 bytes
```

El directorio `docs/auditoria/respaldos/` está en `.gitignore` (contiene datos de
clientes), así que el respaldo existe pero no se versiona. Es lo correcto.

### 0.1 Hallazgo lateral: el comando de baseline no imprime su propio número

`pytest.ini` ya trae `addopts = -q`. El comando documentado en `CLAUDE.md`,
`python -m pytest tests/ -q`, suma el segundo `-q` y se convierte en `-qq`, que
**suprime la línea de resumen**. Se ven 230 puntos y `exit 0`, pero nunca la frase
`230 passed`. Un baseline que no imprime su número obliga a contar puntos a mano.

El número real se obtiene con `python -m pytest tests/` (sin el `-q` extra).
Se corrige la documentación en T3.9.

---

## 1. Cómo se reprodujo, y por qué así

`tools/reproducir_bugs_importador.py` reproduce los defectos de forma **determinista
y repetible**, con dobles de prueba en las dos fronteras externas (Places y Sheets).

Dos decisiones que hay que dejar por escrito, porque se apartan de la letra del plan:

**No se hizo una corrida real de Places.** El plan pedía correr el importador sobre
una ciudad real. Eso (a) factura Google Places, que la regla 10 del índice prohíbe a
los scripts de análisis, y (b) **escribe filas en `LISTA DE CONTACTOS` de producción**,
que es una mutación difícil de revertir sobre datos vivos de clientes. El repro con
dobles produce los mismos números y además es repetible. La corrida real contra la hoja
sigue siendo necesaria para cerrar **CE1** en T3.8, y **requiere autorización explícita
del owner**: queda marcada como gate en la tabla PROGRESO.

**No se usó gunicorn.** `gunicorn` no corre en Windows (depende de `fcntl`) y no está
instalado en esta máquina. Se levantan **dos procesos Flask independientes**, que es
exactamente el modelo de `gunicorn --workers 2`: pre-fork, procesos separados, sin
memoria compartida. La verificación con gunicorn real sobre el VPS queda para T3.8.

---

## 2. Síntoma A — "dice 20 y aparecen 10"

**Escenario:** ciudad ya trabajada. 12 ferreterías + 8 distribuidoras, de las cuales
6 son las mismas de la primera categoría, sobre una hoja que ya tenía 4 de ellas.

```
UI dice 'Encontrados'            : 20
Filas REALMENTE escritas en hoja : 10
Diferencia                       : 10
status final                     : done
```

Mensaje que lee el operador al terminar:

> "20 contactos encontrados · 0 descartados · **Guardados en Google Sheets**"

**El síntoma reportado por el owner queda reproducido con sus mismos números.**

Desglose de los 10 que faltan:

| Defecto | Cuántos se pierden | Por qué |
|---|---|---|
| **B2** ya estaban en la hoja | 4 | `_exportar_a_sheets` deduplica por `Nombre\|Dirección` (`app.py:4425-4432`) **después** de que se contó |
| **B3** contados dos veces | 6 | `vistos` es local a `_buscar_negocios` (`app.py:4329`), o sea por categoría |
| **B1** el contador no usa `nuevos` | — | `app.py:4525` suma `len(resultados)`; `nuevos` (`app.py:4519`) solo va al log |

El log interno **sí** tiene el número correcto — y nadie lo mira:

```
> ✓ Ferreterías: 12 aprobados, 0 descartados, 8 nuevos en Sheet
> ✓ Distribuidoras Ferreterías: 8 aprobados, 0 descartados, 2 nuevos en Sheet
> ✅ Completado en 0.0 min — 20 contactos encontrados
```

8 + 2 = 10 filas escritas. El titular dice 20.

---

## 3. Síntoma A bis — B4: la escritura falla y se reporta éxito

Se fuerza `get_worksheet` a lanzar `RuntimeError('cuota de Sheets agotada')`:

```
Filas escritas        : 0
status final          : done
campo error           : ''            <-- vacío
UI dice 'Encontrados' : 12
Última línea del log  : ✅ Completado en 0.0 min — 12 contactos encontrados
```

**Cero filas escritas, `status: done`, palomita verde y contador en 12.** El único
rastro del fallo es `[importador] sheets error: ...` por stdout del contenedor, donde
el owner no mira. Es un fallo abierto de libro: el `except` de `app.py:4471-4474`
devuelve `0`, que es indistinguible de "no había nada nuevo que escribir".

---

## 4. Síntoma B — B5: el estado vive en memoria de proceso

Dos procesos Flask en 5061 y 5062. Se lanza el trabajo **solo** en 5061 y se sondea
alternando:

```
POST /iniciar -> worker 5061: {"ok":true}

#   puerto  status   progreso  encontrados
1   5061    running  0         0
2   5062    idle     0         0  <-- MIENTE
3   5061    running  0         0
4   5062    idle     0         0  <-- MIENTE
...
20  5062    idle     0         0  <-- MIENTE

Respuestas con status 'idle' mientras el trabajo corre: 10 de 20
```

**El proceso que no lanzó el trabajo no sabe que existe.** Devuelve `idle`,
`progreso 0` y `encontrados 0`. Eso es exactamente el parpadeo que reporta el owner:
la barra salta a 0 %, "Encontrados" parpadea a 0 y la corrida "nunca termina", porque
el `done` del worker A solo lo ve la mitad de los sondeos.

**Honestidad sobre el 50 %:** esa proporción es **por construcción** — el repro alterna
a propósito. Lo que el experimento prueba es que el proceso B **no tiene el estado**,
no cuál es el reparto real del balanceador de gunicorn en producción.

**B6 aparece de regalo en la misma tabla:** durante los 20 sondeos, `progreso` se
mantuvo en `0` en el worker que sí tenía el trabajo. Con `progreso = i` (`app.py:4510`)
e `i` el índice de categoría, la barra está en 0 % durante toda la primera categoría.

---

## 5. Veredicto por defecto

Los nueve defectos de §1 del plan, con su estado tras esta tarea. T3.1 completa los
que aquí quedan como confirmados solo por lectura de código.

| # | Defecto | Estado | Evidencia |
|---|---|---|---|
| B1 | El contador cuenta aprobados, no filas escritas | **REPRODUCIDO** | §2 — 20 vs 10 |
| B2 | Duplicados contra la hoja | **REPRODUCIDO** | §2 — 4 de los 10 |
| B3 | Duplicados entre categorías | **REPRODUCIDO** | §2 — 6 de los 10 |
| B4 | Fallo silencioso de escritura | **REPRODUCIDO** | §3 — 0 filas, `done`, ✅ |
| B5 | Estado en memoria de proceso | **REPRODUCIDO** | §4 — 10 de 20 sondeos `idle` |
| B6 | Barra con tres valores | **REPRODUCIDO** | §4 — `progreso` fijo en 0 |
| B7 | Recargar pierde el trabajo | Confirmado por código | Solo `iniciar()` arranca el sondeo (`app.py:4878`); no hay restauración al cargar |
| B8 | Botón trabado / sondeo eterno | Confirmado por código | `await fetch` sin `try/catch` (`app.py:4870-4874`); `setInterval` sin corte en `idle` |
| B9 | Nombre de ciudad sin escapar | Confirmado por código | `onclick="seleccionarCiudad('${c.ciudad}',this)"` (`app.py:4840`) |

B7, B8 y B9 se cierran en T3.1 con experimento propio (recorrido de rutas de clic).

---

## 6. Corrección de una cita del plan

El documento del Plan 3 sitúa el `--workers 2` del Dockerfile en `Dockerfile:22`.
La línea real es **`Dockerfile:17`**:

```
17:CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "120"]
```

`Procfile:1` sí es correcto. El defecto es el mismo; solo se corrige la referencia.

---

## 7. Reproducir esto otra vez

```bash
python tools/reproducir_bugs_importador.py conteo    # B1, B2, B3, B4
python tools/reproducir_bugs_importador.py workers   # B5, B6
```

Ninguno de los dos toca la red, la hoja de producción ni la API de Places.
