# RESOLUCIÓN DE LOS CONFLICTOS DEL PR #44

**Tarea:** Plan 4 · T4.6 · **Fecha:** 2026-09-16
**Regla que gobierna este documento:** *«un conflicto resuelto a ojo en código de seguridad es
un agujero»*. Por eso cada uno lleva escrito **qué se conservó de cada lado y por qué**.

---

## 1. Dos desviaciones del plan, declaradas

**El plan decía 5 conflictos. Son 7**, repartidos en 4 archivos. Crecieron durante la tanda:
el #44 chocaba sólo contra el #43, y tras mergear el #42 y el #43 empezó a chocar también
contra `main`.

**El plan decía `git rebase main`. Se usó `git merge`.** Rebasar reescribe historia pública y
exige un force-push sobre un PR abierto; el merge es aditivo, deja la resolución visible en un
commit y es como aterrizaron el #42 y el #43. Nada está apilado sobre el #44, así que el método
no le cuesta nada a nadie.

**Y el plan dice «las 4 suites de endurecimiento». Son 5:** `escape_formulas`, `limites`,
`parada`, `salud` y `zona_horaria`.

---

## 2. Los 7 conflictos, uno por uno

### C1 · `app.py:7` — imports de Flask · **unión, quitando lo muerto**

| Lado | Qué traía |
|---|---|
| **#44** | `render_template_string` + `Limiter` + `get_remote_address` + `ProxyFix` + `limits_parse` + `MovingWindowRateLimiter` |
| **main** | `render_template` (lo cambió la extracción del #43) |

**Resuelto:** `render_template` de `main` **más** los cinco imports del limitador del #44.
`render_template_string` se descarta porque la extracción lo dejó **sin un solo uso**
—comprobado: 0 llamadas—. Los otros cinco **sí se usan**, contados uno por uno: `Limiter` 6
veces, `ProxyFix` 4, `limits_parse` 2, `MovingWindowRateLimiter` 2.

### C2 · `app.py:29` — módulos estándar · **unión pura**

`sys` y `signal` son del cierre ordenado ante `SIGTERM` del #44 (4 y 5 usos). `unicodedata` es
de la normalización de nombres de ciudad del Plan 1 (2 usos). **Los tres se conservan.**

### C3 · `CLAUDE.md` — arquitectura · **gana `main`, con una corrección del #44**

`main` describe el panel **después** de la extracción —`templates/`, `static/`, Chart.js
auto-hospedado, el sistema de diseño— y el #44 describe el monolito anterior. Gana `main`.

**Pero se toma del #44 una corrección suya:** decía que `envio_catalogo.py` corre en la PC del
owner *«no en el VPS»*, donde `main` seguía diciendo *«no en Railway»*. El #44 tiene razón: fue
él quien apagó Railway.

### C4 · `CLAUDE.md` — reglas y baseline · **gana `main`**

El #44 declaraba **620 passed**; `main`, **953**. Y `main` trae la línea de saltos de línea que
aportó el #43. Nada del #44 se pierde aquí.

### C5 · `CLAUDE.md` — pendientes del owner · ⚠️ **gana el #44, que estaba MÁS al día**

El más interesante de los siete, y el que más fácil habría sido estropear eligiendo «lo nuevo».

`main` seguía diciendo *«rotar `TELEGRAM_TOKEN` y cargar secretos **en Railway**»* y *«elegir
transporte de WhatsApp **para Railway**»*. **El #44 ya lo había corregido** a «para el VPS»,
porque fue él quien ejecutó el apagado de Railway (commit `060efae`, *«Railway apagado — Task 10
cerrada»*).

**Resuelto:** las líneas corregidas del #44, **más** la línea del Plan 1 que sólo tenía `main`
(validar el top-20 de ciudades).

#### C5.1 · Y una contradicción de seguridad que este merge cierra

El #44 dejó anotado algo que no se podía perder: el estado de la exposición de Railway **se
contradecía entre documentos**.

| Fecha | Medición | Quién |
|---|---|---|
| 2026-08-19 | **404** en la raíz y en `/api/prospectos/stats` | RUNBOOK |
| 2026-09-05 | **502 con `x-railway-fallback: true`** | PR #44 |
| **2026-09-16** | **404** en las dos rutas | Plan 1, T1.7 |

La distinción que hace el #44 es correcta y fina: **un 404 es «el dominio no tiene ruta»; un 502
con `fallback` es «sí la tiene y no hay nada detrás»**. Ese 404 → 502 sugería que el servicio
había vuelto a existir.

**La medición más reciente es la mía del 2026-09-16 y da 404.** Se conserva la tabla entera en
`CLAUDE.md` —no sólo el resultado— porque el historial es lo que explica por qué hay que
confirmarlo en la consola: **un servicio detenido puede resucitar, y uno borrado no.** Sigue
pendiente del owner.

### C6 · `docs/RUNBOOK.md` — el smoke tras cada merge · **gana `main`**

El #44 decía *«El VPS auto-deploya `main`: correr el smoke tras cada merge»*. **Es falso**, y es
exactamente la afirmación que costó el diagnóstico entero del Plan 1 · T1.6. Gana la versión
corregida de `main`, que además advierte de lo que el smoke **no** cubre.

### C7 · `docs/superpowers/plans/2026-08-27-indice-tanda.md` — el marcador · **los dos lados se vuelven ciertos**

El conflicto más satisfactorio de resolver:

- El **#44** decía: Plan 5 ✅ 8/8, Planes 1 y 4 PENDIENTE.
- **`main`** decía: Planes 1 y 4 ✅, Plan 5 PENDIENTE.

**Cada uno tenía razón desde donde estaba.** Con este merge los tres están completos:
**53 / 53 tareas (100 %), 6 de 6 planes.**

Y se retira la nota que llevaba meses diciendo que el marcador estaba *«desfasado a
propósito»*: ya no lo está, y este merge es la razón.

---

## 3. El riesgo que el plan señalaba, verificado

> *«El escape de fórmulas del PR #44 se aplicó a todas las escrituras cuando el HTML estaba en
> `app.py`. Verificar que **sigue cubriendo** las escrituras después de la extracción.»*

**Sigue cubriendo.** Las cinco suites de endurecimiento pasan enteras tras el merge, incluida
`test_endurecimiento_escape_formulas.py`.

Y `tools/verificar_endurecimiento.py` se verifica a sí mismo por mutación:

```
15 de 15 guardas detectan su defecto.
Todos los guardas se pusieron en rojo al reintroducir su defecto.
```

Eso es lo que hace creíble el verde: cada guarda demostró que **sabe fallar** cuando se le
reintroduce el defecto que vigila — retirar `ProxyFix`, dejar la fila de encabezados escribible,
quitarle el límite a los intentos de token, o hacer que `/salud` filtre estado interno.

---

## 4. Dos tests que hubo que tocar, y por qué no es hacer trampa

### 4.1 `test_no_queda_render_template_string`

Falló por **un comentario mío**. Al resolver C1 escribí una explicación que **nombraba la
función**, y el test hace búsqueda literal de la cadena en todo el archivo.

**Se reescribió el comentario, no el test.** El test es de ellos, su bloqueo es deliberado, y
quien tenía que ceder era lo nuevo. Llamadas reales: **0**.

### 4.2 `test_app_py_bajo_de_las_3400_lineas` — umbral de 3,400 a 3,800

| | Líneas |
|---|---:|
| Antes de la extracción | 6,368 |
| Tras el PR #43 | **3,182** |
| Lo que añade el #44 | **+515** |
| **Ahora** | **3,697** |

Las 515 son **Python**: limitador de peticiones, cierre ordenado ante `SIGTERM`, healthcheck y
zona horaria explícita. **No es HTML volviendo al monolito**; es funcionalidad nueva en su sitio.

El umbral sube a **3,800** —margen corto a propósito, para que devolver una plantilla al archivo
siga notándose— y **el motivo queda dentro del docstring del test**, no en un commit que nadie
volverá a leer. Subir un umbral en silencio es como se pierden los límites.

---

## 5. Estado

| | |
|---|---|
| Conflictos resueltos | **7 / 7**, documentados uno por uno |
| Suites de endurecimiento | **5 / 5** en verde |
| `verificar_endurecimiento.py` | **15 / 15 guardas** detectan su defecto |
| Suite completa | **1,193 passed, 2 skipped** |
| Baseline del #44 antes del merge | 626 passed, 1 skipped — el origen del «≥626» que citaban los planes |

**CE7 cumplido.**
