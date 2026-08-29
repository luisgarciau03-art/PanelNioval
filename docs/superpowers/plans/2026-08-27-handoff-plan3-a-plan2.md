# Handoff — Plan 3 cerrado, arranca el Plan 2

**Fecha:** 2026-08-27 · **Para:** la sesión que ejecute el Plan 2
**Estado global:** 10 / 41 tareas (24 %) · **1 de 4 planes completado**

---

## Lo que quedó hecho

**Plan 3 completo (10/10).** PR **#36** mergeado a `main` (`ae0e1c9`).
Baseline **230 → 314 passed**.

La rama `fix/conteo-importador-y-estados-carga` **sigue en origin** (`a3e6d78`)
a propósito: el merge fue squash, y esos diez commits —uno por defecto— son la
única forma de revertir un arreglo sin perder los otros. No borrarla todavía.

Quince defectos corregidos: los nueve del plan (B1–B9) más seis que aparecieron
al confirmarlos con experimento (B10–B15), y dos hipótesis descartadas con su
razón. Detalle en `docs/investigacion/2026-08-27-reproduccion-bugs-importador.md`
y `docs/investigacion/2026-08-27-verificacion-plan3.md`.

---

## Lo que el Plan 2 hereda, y no debe rehacer

El índice ya lo anticipaba; esto concreta **dónde** está cada cosa.

### T2.3 — el dedup por corrida ya existe

`_buscar_negocios(gmaps_client, categoria, ciudad, vistos=None, con_detalle=None, avisar=None)`

`_worker_importador` crea **dos** conjuntos por corrida y los pasa a cada
categoría:

- `vistos_corrida` — todos los `place_id` ya procesados. El salto ocurre
  **antes** del `gmaps_client.place(pid)`, que es donde está el dinero.
- `con_detalle_corrida` — solo los que **ya costaron** un Place Details.

**Son dos números distintos y la diferencia importa para el Plan 2.** Un negocio
rechazado por reseñas se descarta *antes* de pedir el detalle, así que saltárselo
después no ahorra nada. `incidencias` devuelve los dos por separado:

```python
{'ya_vistos_otra_cat': N,   # se saltaron
 'detalles_evitados': M,    # de esos, los que SÍ habrían costado dinero
 'detalles_fallidos': ..., 'paginas_fallidas': ..., 'consultas_fallidas': ...}
```

**Para reportar ahorro, usa `detalles_evitados`, no `ya_vistos_otra_cat`.** Una
review marcó exactamente esa confusión como MEDIO.

### T2.4 — el denominador de progreso ya es ajustable

`_avanzar_progreso(job, hechos=None, total=None, fase=None)` mantiene `fraccion`
monótona no decreciente. **Ampliar el total nunca hace retroceder la barra;
recortarlo sí puede adelantarla.** Hay cuatro tests que lo fijan
(`TestDenominadorAjustable`).

El presupuesto actual es `BASE_POR_CATEGORIA = 1 + 3 + 1` (preparar, 3
variaciones, guardar) más 1 reservado para el cierre. Las páginas son trabajo
descubierto en marcha: hacen crecer numerador **y** denominador. Si el Plan 2
recorta variaciones, solo hay que bajar la base; la barra se ajusta sola.

---

## Correcciones a lo que el Plan 2 da por supuesto

**`if lugares: break` NO corta las variaciones.** Corta los **reintentos**. Las
tres variaciones se ejecutan **siempre**. Verificado por indentación:

```
4338|    for query in variaciones:        <- indent 4
4339|        for intento in range(3):     <- indent 8
4392|                if lugares: break    <- indent 16, dentro del intento
```

Consecuencia: el gasto de Places es **mayor** de lo estimado — **3 consultas de
texto por categoría, 6 por corrida**, cada una con hasta 3 páginas. Esto corrige
una observación previa de la memoria del proyecto que decía lo contrario.

**Gasto adicional ya localizado, sin arreglar:** cuando una consulta devuelve
legítimamente cero resultados (sin excepción, lista vacía), `if lugares` es falso
y **se repite la misma consulta vacía hasta 3 veces**, sin backoff — el
`2 ** intento` solo está en la rama `except`. Es dinero pequeño pero real.

**`place()` sigue sin `fields`** (`app.py`, dentro de `_buscar_negocios`): se
factura el objeto completo y solo se usan `formatted_phone_number`, `website` y
`opening_hours`. Sigue siendo el ahorro más grande disponible.

---

## Antes de tocar código

1. **Rama nueva desde `main` actualizado:** `perf/gasto-places-importador`.
   Nunca en `main`: Railway y Vultr auto-despliegan.
2. **Respaldo antes del cambio:** `python tools/respaldar_hojas.py docs/auditoria/respaldos/<fecha>`
   y confirmar que los archivos existen en disco.
3. **Baseline:** `python -m pytest tests/` → **314 passed**.
   **Sin `-q`**: `pytest.ini` ya trae `addopts = -q` y el segundo lo convierte en
   `-qq`, que suprime la línea del resumen. Se ven los puntos y `exit 0`, pero
   nunca el número.
4. **Importar `app.py` en frío tarda ~100 s** (googleapiclient + Defender). Tras
   modificar `app.py`, la primera corrida de pytest vuelve a pagarlo. No es un
   cuelgue.

---

## Gates del owner, abiertos

Ninguno se puede cerrar desde una sesión de Claude.

| # | Gate | Por qué |
|---|---|---|
| 1 | **Plan 2 · T2.0 — acceso a la consola de facturación de Google Cloud** | El plan **no avanza a ciegas**: sin la línea base de gasto no hay con qué comparar el ahorro. **Escalar antes de empezar.** |
| 2 | Corrida real de Places contra la hoja (CE1 del Plan 3) | Factura la API y escribe en `LISTA DE CONTACTOS` de producción |
| 3 | Comprobación con gunicorn real en el VPS (CE5) | gunicorn no corre en Windows (necesita `fcntl`) |
| 4 | Recargar a media corrida en un navegador (CE7) | Requiere navegador contra el VPS |
| 5 | Rotar `TELEGRAM_TOKEN` | Expuesto en el historial de git (~14 copias). Quitarlo del código no lo rota |
| 6 | Apagar el despliegue de Railway | Sigue vivo sin `PANEL_DASHBOARD_TOKEN` |

---

## Trampas de este entorno, aprendidas a golpes

- **Un `\n` escrito a mano en un heredoc no llega como `\n`.** Los reemplazos por
  patrón que incluían `\\n` no casaban y devolvían el texto igual, sin error. Usa
  coincidencia por línea o `chr(92) + "n"`, y **verifica siempre que el cambio
  está en el archivo**, no que la herramienta dijo "aplicado".
- **`git add -A docs/`** se lleva los ocho archivos de la tanda `2026-08-15-*`,
  que son de otro proyecto (mejora M11). Añadir por ruta explícita.
- **No edites `app.py` mientras un reviewer lo está leyendo.** Un
  `python-reviewer` reportó que el árbol se movió a media review.
- **Un test que afirma la FORMA del arreglo y no su efecto se rompe solo.** Dos
  de los míos fallaron por comprobar `disabled = false` cuando el código llamaba
  a `ponerEnMarcha(false)`.
- **La fixture `entorno` sustituye `_enviar_telegram_importador` por un no-op.**
  Un test que quiera ejercitar el notificador de verdad tiene que usar
  `monkeypatch` pelado, o estará midiendo el doble en vez del código.

---

## Orden restante

**2 → 1 → 4.** El Plan 2 va ahora porque reutiliza lo que el Plan 3 construyó.
El Plan 1 hereda además **B11** (filtrar ciudades renumeraba el ranking); ya está
corregido en el cliente con `c.rank` fijado una sola vez sobre el catálogo
completo — **verificar y no duplicar**.


---

# Actualización 2026-08-28 — Plan 2 va 5 de 9

**PR #38 (borrador)**, rama `perf/gasto-places-importador`. **No mergeado**: el
plan no está cerrado. Baseline **314 → 326 passed**.

## Hecho

| Tarea | Estado |
|---|---|
| T2.0 | 🚫 **BLOQUEADA** en su mitad monetaria · sustituida por conteo de llamadas |
| T2.1 | ✅ ADR `docs/adr/2026-08-28-places-legacy-vs-new.md` |
| T2.2 | ✅ `fields` explícitos en `place()` |
| T2.3 | ✅ prefiltro antes de pagar Details |
| T2.4 | ✅ cortes por aporte cero · ⚠️ CE7 sin verificar |

**Ahorro medido** (`python tools/medir_llamadas_places.py`), Place Details por
corrida: ciudad nueva 80→80, a medio trabajar 80→60, **ya trabajada 80→0**. Más,
en las que quedan, se deja de facturar Basic (26 campos) y Atmosphere (18).

## Lo que falta, y lo que ya no hace falta

**T2.4 — cortar variaciones y páginas sin aporte.** Sigue pendiente y sigue
valiendo la pena: son 18 Text Search por corrida, invariables en los tres
escenarios. Ojo: el plan dice que `if lugares: break` corta variaciones. **No**:
corta reintentos. Las tres variaciones corren siempre.

El denominador de progreso ya es ajustable (Plan 3 · T3.6), así que recortar
variaciones solo pide bajar `BASE_POR_CATEGORIA`; la barra se ajusta sola y no
retrocede.

**T2.5 — caché persistente `place_id` → detalle.** Ojo con dos cosas que el plan
da por supuestas y ya no son ciertas:
- Dice que gunicorn corre `--workers 2` y que por eso hace falta caché fuera del
  proceso. **Ya no**: desde el Plan 3 corre `--workers 1 --threads 4`. La razón
  para persistir sigue siendo sobrevivir al reinicio, no compartir entre workers.
- El archivo llevaría **teléfonos de negocios**, que son datos personales. Va a
  `.gitignore` y `.dockerignore` **en el mismo commit que lo crea**.

**T2.6 — medidor de costo y tope.** Para reportar ahorro use
`incidencias['detalles_evitados']`, **no** `ya_vistos_otra_cat`: el segundo
incluye negocios rechazados por reseñas, que nunca costaron un `place()`.

**T2.7 — verificación A/B.** `tools/medir_llamadas_places.py --json` da la salida
comparable entre corridas.

## Gate del owner que sigue abierto y bloquea el cierre

Sin el **consumo por SKU de la consola de Google Cloud** (proyecto
`bubbly-subject-412101`) no se puede expresar el ahorro en pesos. Los conteos ya
están; falta solo el multiplicador.

## Trampa que volví a pisar

`git add docs/superpowers/plans/` arrastra otra vez los ocho archivos de la tanda
`2026-08-15-*`, que son de otro proyecto. **Añadir siempre por ruta explícita.**
Ya me pasó en el Plan 3 y volvió a pasar aquí.


---

## T2.4 cerrada — lo que la siguiente sesión tiene que saber

**Text Search por corrida: 18 → 13.** Tres cortes, todos por aporte **medido** de
cero, nunca por predicción. Cada uno se registra en el log con su motivo.

**El riesgo abierto.** El corte de variaciones asume que si dos fraseologías casi
idénticas se saturan, la tercera también. Es razonable y no está probado. El plan
exige verificarlo corriendo la ciudad de referencia (CE7) y **esa corrida es gate
del owner**. Se documenta como riesgo aceptado, no como resuelto.

Si el owner corre la ciudad de referencia y falta algún negocio respecto de T2.0,
el corte se desactiva **sin tocar código**:

```python
MAX_VARIACIONES_SIN_APORTE = 99     # desactiva el corte de variaciones
CORTAR_PAGINAS_SIN_APORTE  = False  # desactiva el corte de páginas
```

**Dos lecciones de esta tanda que conviene no repetir:**

- Escribir el test que documenta un riesgo **encontró un riesgo peor**: contar las
  variaciones vacías como saturación dejaba que dos consultas sin resultados
  cancelaran una tercera que sí funcionaba, perdiendo la categoría entera. Vacío
  no es saturado.
- Un test que pasa con y sin el arreglo no vale nada. El del HIGH de T2.4 se
  comprobó reintroduciendo el bug a propósito: falla con él, pasa sin él.

## Lo que queda del Plan 2

**T2.5** caché persistente de detalles, **T2.6** medidor con tope de presupuesto,
**T2.7** verificación A/B, **T2.8** cierre. Recordatorios ya anotados arriba:
`--workers` ya es 1 (no 2), el archivo de caché lleva teléfonos y va a
`.gitignore` y `.dockerignore` en el mismo commit, y para reportar ahorro se usa
`detalles_evitados`, no `ya_vistos_otra_cat`.
