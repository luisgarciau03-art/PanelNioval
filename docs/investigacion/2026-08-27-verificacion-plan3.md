# Verificación de extremo a extremo — Plan 3

**Tarea:** T3.8 · **Fecha:** 2026-08-27
**Rama:** `fix/conteo-importador-y-estados-carga`

> Nada se declara resuelto por inspección visual. Cada punto lleva su salida de
> comando. Lo que no se puede verificar aquí se marca como gate del owner, no se
> da por bueno.

---

## 1. Baseline sin regresiones — ✅

```
python -m pytest tests/
314 passed in 15.24s
```

**230 → 314.** 84 tests nuevos, ninguno de los previos roto.

| Tarea | Baseline al cerrar |
|---|---|
| Partida | 230 |
| T3.2 contadores | 237 |
| T3.4 fallo visible | 247 |
| T3.3 dedup | 252 |
| T3.5 estado compartido | 275 |
| T3.6 progreso | 288 |
| T3.7 frontend | 314 |

**Nota sobre el comando documentado:** `pytest.ini` ya trae `addopts = -q`, así
que `python -m pytest tests/ -q` se convierte en `-qq` y **suprime la línea del
resumen**. El número real solo aparece sin el `-q` extra. Corregido en T3.9.

---

## 2. El número que ve el operador es el que hay en la hoja — ⚠️ gate del owner

**Verificado con dobles, de forma determinista y repetible:**

```
python tools/reproducir_bugs_importador.py conteo

UI dice 'Encontrados'            : 14
Filas REALMENTE escritas en hoja : 10
VEREDICTO: B1/B2/B3 CORREGIDOS (T3.2) — nuevos_en_sheet=10 es el numero grande
```

`nuevos_en_sheet` (10) == filas escritas (10). Y los cuatro números cuadran:
`nuevos_en_sheet(10) + duplicados(4) == encontrados(14)`.

**Lo que falta, y por qué no lo hice:** el plan pide una corrida real sobre una
ciudad con duplicados conocidos, contando a mano las filas de la hoja. Eso
(a) factura Google Places, que la regla 10 del índice prohíbe a los scripts de
análisis, y (b) **escribe filas en `LISTA DE CONTACTOS` de producción**, una
mutación difícil de revertir sobre datos vivos de clientes.

**CE1 queda pendiente de autorización del owner.** Es la única forma de cerrarlo
del todo.

---

## 3. Estado correcto con varios procesos — ✅ medido antes y después

El mismo experimento, con la configuración anterior y con la actual:

```
=== ANTES (2 procesos, config anterior) ===
  Respuestas con status 'idle' mientras el trabajo corre: 10 de 20

=== DESPUES (1 proceso, config actual) ===
  Respuestas con status 'idle' mientras el trabajo corre: 0 de 20
```

**10/20 → 0/20.** Es la medición de la causa raíz, antes y después.

**Salvedad honesta:** son procesos Flask, no gunicorn. `gunicorn` no corre en
Windows (necesita `fcntl`) y no está instalado en esta máquina. El modelo es el
mismo —pre-fork, procesos separados, sin memoria compartida—, pero **la
comprobación con gunicorn real sobre el VPS sigue siendo gate del owner**.

Además hay tres tests que impiden que la configuración se deshaga sola: comparan
`Procfile`, `Dockerfile` y `nixpacks.toml` y fallan si vuelven a declarar más de
un worker o si dejan de coincidir entre sí.

---

## 4. Un fallo de escritura llega al operador — ✅

```
python tools/reproducir_bugs_importador.py conteo

get_worksheet lanza  : RuntimeError('cuota de Sheets agotada')
Filas escritas       : 0
status final         : error
campo error          : 'Ferreterías: fallo al escribir en Google Sheets — cuota…'
VEREDICTO: B4 CORREGIDO (T3.4)
```

Antes: `status: done`, campo `error` vacío, palomita verde y cero filas escritas.

Cubierto también el gemelo del lado de la **lectura** (B14): con Places fallando
en todas las consultas, la corrida termina en `error` en vez de informar "0
aprobados" con palomita. Y en la otra dirección: una ciudad legítimamente vacía
sigue terminando en `done`, porque un barrido que marca como fallo un negativo
conocido engaña igual que uno que se traga un positivo.

---

## 5. Los contadores, comprobados en las dos direcciones — ✅

| Dirección | Test | Resultado |
|---|---|---|
| Cuenta un duplicado que sé que existe | `test_duplicados_se_reportan_por_separado_de_descartados` | 2 duplicados, 3 descartados, distintos |
| No cuenta como duplicado algo nuevo | `test_los_cuatro_numeros_cuadran` | `nuevos + duplicados == encontrados` |
| Un negocio en dos categorías es uno | `test_mismo_place_id_en_dos_categorias_cuenta_una_vez` | 14, no 20 |
| Un rechazado se cuenta una vez | `test_un_negocio_rechazado_se_cuenta_una_sola_vez` | 1, no 6 |
| Un fallo no se disfraza de duplicado | `test_fallo_de_escritura_no_se_cuenta_como_duplicados` | `duplicados == 0` |
| Cero por error ≠ cero por nada nuevo | `test_cero_filas_por_error_se_distingue_de_cero_filas_por_nada_nuevo` | `done` vs `error` |

**Corroboración con datos reales de producción** (respaldo del 2026-08-27,
7,145 filas de `LISTA DE CONTACTOS`): **12 `place_id` están bajo las dos
categorías del importador**. El solape que B3 describe no es teórico.

---

## 6. La barra avanza de verdad — ✅

Secuencia real, caso común sin paginación:

```
  9%  Preparando Ferreterías…
 18%  Ferreterías — variación 1 de 3
 27%  Ferreterías — variación 2 de 3
 36%  Ferreterías — variación 3 de 3
 45%  Guardando Ferreterías en Google Sheets…
 55%  Preparando Distribuidoras Ferreterías…
 ...
 91%  Guardando Distribuidoras Ferreterías en Google Sheets…
100%  Completado
```

Antes: **0 %, 50 %, 100 %** y nada más. Tramos parejos de 9 puntos, monótona, y
el 100 % solo cuando de verdad terminó.

---

## 7. Frontend — ✅ parcial, con gate de navegador

Verificado desde la suite:

- El JS embebido **parsea**: `node --check` sobre el bloque extraído. Un error de
  sintaxis ahí no lo ve ni pytest ni el import de `app.py`; la página se serviría
  rota y en silencio.
- Los seis estados del servidor (`idle`, `running`, `done`, `error`, `cancelado`,
  `interrumpido`) están cubiertos por el cliente.
- `POST /api/importador/cancelar` detiene la corrida conservando lo escrito
  (8 filas de la primera categoría) y **no** la marca como completada.
- No queda interpolación del nombre de ciudad en atributos de código.

**Gate del owner:** recargar la página a media corrida y confirmar visualmente
la restauración pide un navegador real. La lógica está cubierta por tests y por
el gate de seguridad, pero la comprobación visual no la hice.

---

## 8. Resumen de gates

| # | Criterio | Estado |
|---|---|---|
| CE1 | El número de la UI == filas en la hoja | ✅ con dobles · ⚠️ **corrida real: gate del owner** |
| CE2 | Cuatro números rotulados sin ambigüedad | ✅ |
| CE3 | Ningún negocio contado dos veces | ✅ |
| CE4 | Un fallo de escritura llega al operador | ✅ (y también los de lectura) |
| CE5 | Estado correcto con varios procesos | ✅ 10/20 → 0/20 · ⚠️ **gunicorn real en VPS: gate del owner** |
| CE6 | Barra continua y monótona | ✅ |
| CE7 | Recargar no pierde el trabajo | ✅ lógica · ⚠️ **navegador: gate del owner** |
| CE8 | El botón nunca queda trabado | ✅ |
| CE9 | El sondeo termina | ✅ |
| CE10 | Nombres de ciudad escapados | ✅ **security-reviewer: PASS** |
| CE11 | Baseline sin regresiones | ✅ **314 passed** |

**8 de 11 cerrados del todo. Tres esperan al owner**, y ninguno de los tres se
puede cerrar desde aquí sin facturar la API, escribir en producción o abrir un
navegador contra el VPS.

---

## 9. Defectos: los nueve del plan y los seis que aparecieron

| # | Defecto | Estado |
|---|---|---|
| B1 | Contador cuenta aprobados, no filas | ✅ T3.2 |
| B2 | Duplicados contra la hoja | ✅ T3.2 |
| B3 | Duplicados entre categorías | ✅ T3.3 |
| B4 | Fallo silencioso de escritura | ✅ T3.4 |
| B5 | Estado en memoria de proceso | ✅ T3.5 |
| B6 | Barra con tres valores | ✅ T3.6 |
| B7 | Recargar pierde el trabajo | ✅ T3.7 |
| B8 | Botón trabado / sondeo eterno | ✅ T3.7 |
| B9 | Ciudad sin escapar (XSS almacenado) | ✅ T3.7 |
| **B10** | Guard por proceso → doble corrida y doble factura | ✅ T3.5 + T3.7 |
| **B11** | Filtrar renumera el ranking | ✅ T3.7 |
| **B12** | Insignias y stats rancios | ✅ T3.7 |
| **B13** | Estado muerto con datos personales | ✅ T3.7 |
| **B14** | Fallo de LECTURA de Places silenciado | ✅ T3.4 |
| **B15** | `descartados` inflado hasta 6× | ✅ T3.3 |

Y dos hipótesis **descartadas** con su razón: la doble inicialización de
`_import_job` (no hay carrera: el reset ocurre bajo lock y antes del `start()`) y
`if lugares: break` (corta reintentos, no variaciones — las tres siempre corren).
