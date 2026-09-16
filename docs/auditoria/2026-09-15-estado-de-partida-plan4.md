# ESTADO DE PARTIDA — Plan 4 (rediseño profesional)

**Tarea:** Plan 4 · T4.0 · **Fecha:** 2026-09-16 · **Rama:** `feat/rediseno-aterrizaje`
**Base:** `main` `a97b494` (Plan 1 cerrado, mergeado y desplegado)

**Para qué existe este documento:** un rediseño sin evidencia del «antes» no se puede evaluar
después. Las capturas y las métricas de aquí **son el instrumento de medición** de CE6, no
decoración. Si faltan, el plan se queda sin forma de demostrar que no empeoró nada.

---

## 1. Lo verificado, en una tabla

| Comprobación | Resultado |
|---|---|
| Rama `feat/rediseno-aterrizaje` desde `main` actualizado | ✅ `a97b494` |
| Baseline `python -m pytest tests/` | ✅ **525 passed, 1 skipped** |
| Respaldo **antes** de tocar nada | ✅ `docs/auditoria/respaldos/2026-09-15-plan4/` |
| 9 capturas del «antes» (3 superficies × 320/768/1440) | ✅ `docs/diseno/antes-2026-09-15/` |
| LCP y CLS del «antes» | ✅ `docs/diseno/antes-2026-09-15/metricas-base.json` |
| PR #43 y #44 reverificados | ✅ §5 |

⚠️ **El gate del plan dice «≥ 626»** y el baseline real es **525**. No es una regresión: el 626
es de `fix/endurecimiento-panel` (PR #44), que **no está mergeado**. Se reinterpreta como
«≥ el baseline de la rama base», igual que en el Plan 1. Vuelve a aplicar cuando el #44
aterrice en T4.6.

---

## 2. Las capturas del «antes»

Tomadas **de producción**, no de un servidor local: es lo que el operador ve hoy.

| Superficie | 320 px | 768 px | 1440 px |
|---|---|---|---|
| Dashboard (`/`) | ✅ | ✅ | ✅ |
| Formulario (`/formulario`) | ✅ | ✅ | ✅ |
| Importador (`/importador`) | ✅ | ✅ | ✅ |

### 2.1 ⚠️ El formulario traía datos de un cliente real, y hubo que rehacerlo

La primera tanda de capturas del formulario mostraba, **a tamaño legible**, el nombre comercial
y el teléfono de un cliente real — el teléfono **dos veces**, en `TELÉFONO` y en `CONTACTO`.
Commitearlas habría violado la regla del proyecto de no versionar datos de clientes.

**No se difuminaron píxeles: se anonimizó en el origen.** Se interceptó
`/api/formulario/siguiente` con Playwright y se sustituyeron los valores **antes de que la
página pintara**, así que la PII nunca llegó a existir en disco. Las tres capturas del
formulario se rehicieron y muestran `Ferreteria de Ejemplo` y `+52 … XXXX`.

**El layout se conserva intacto**, que es lo único que estas capturas tienen que medir.

### 2.2 Lo que se comprobó mirando, no suponiendo

Se abrieron las capturas una por una antes de commitear:

- **Dashboard:** sólo agregados (7,180 contactos, 6,148 llamadas, gráficas). **Sin PII.**
- **Importador:** el aviso amarillo de «sin clasificar» lista 12 nombres y **ninguno es un
  teléfono**. ⚠️ **Es suerte, no diseño:** `pintarSinClasificar` ordena por número de contactos
  y muestra los 12 primeros; los 8 teléfonos tienen 1 contacto cada uno y caen en el «y 20 más».
  **Si alguno acumulara contactos, aparecería.** Ver el hallazgo de privacidad del Plan 1
  (`2026-09-15-verificacion-produccion-plan1.md` §10).
- **Formulario:** anonimizado, verificado a 1440 y a 320.

### 2.3 Regalo del Plan 1 que estas capturas documentan

La captura `importador-1440.png` muestra **«CIUDADES (1004) — ORDENADAS POR PRIORIDAD»** y el
desplegable en **«Todas (1004)»**. Es evidencia visual en producción de dos de los tres puntos
de **CE5** del Plan 1, que estaba pendiente de capturas del owner.

---

## 3. Línea base de rendimiento (CE6)

Medido contra producción (`8bac782`), **3 corridas por punto, se reporta la mediana**. Una sola
muestra sobre una red real es ruido, no una medición.

| Superficie | Ancho | **LCP** | **CLS** | FCP | TTFB |
|---|---:|---:|---:|---:|---:|
| Dashboard | 1440 | 148.0 ms | **0.1924** ⚠️ | 148.0 ms | 95.7 ms |
| Formulario | 1440 | 548.0 ms | 0.0000 | 548.0 ms | 82.0 ms |
| Importador | 1440 | 428.0 ms | 0.0289 | 136.0 ms | 80.3 ms |
| Dashboard | 320 | 132.0 ms | 0.0952 | 132.0 ms | 92.9 ms |
| Formulario | 320 | 536.0 ms | 0.0000 | 336.0 ms | 82.2 ms |
| Importador | 320 | 460.0 ms | **0.1073** ⚠️ | 128.0 ms | 81.0 ms |

### 3.1 Lo que dice esta línea base

- **El LCP no es el problema.** El peor es 548 ms, muy por debajo del objetivo de 2.5 s. El
  rediseño tiene margen de sobra; lo que no puede es dilapidarlo.
- **El CLS sí lo es, y ya lo era antes del rediseño.** El **dashboard a 1440 da 0.1924**, casi
  el doble del umbral de «bueno» (0.1). El importador a 320 da 0.1073, también por encima.
- **El formulario está en 0.0000** en los dos anchos: es la superficie estable.

**Consecuencia para CE6:** el criterio es «no empeorar». Sobre el dashboard eso sería un
listón muy bajo, porque parte de un valor malo. **Lo honesto es apuntar a bajar de 0.1**, y si
el rediseño no lo consigue, decirlo con el número delante en vez de esconderse tras un «no
empeoró». El plan ya avisa en T4.7 de prestar atención especial al CLS: esta medición explica
por qué.

### 3.2 ⚠️ La primera medición dio todo en cero, y era el instrumento

La primera corrida devolvió **LCP 0.0 y CLS 0.0000 en las seis combinaciones**. No era una
página instantánea: era un fallo mío. `add_init_script` **ejecuta el string como script**, y yo
le pasaba una función flecha suelta —`() => {...}`—, que sólo se define y se descarta. El
`PerformanceObserver` nunca llegó a registrarse.

**No dio ningún error**: devolvió un número plausible y falso, que es la peor clase de
resultado. Corregido envolviendo en IIFE, y se añadió una guarda que declara un `LCP = 0` como
**fallo de medición**, no como valor.

---

## 4. Respaldo

`docs/auditoria/respaldos/2026-09-15-plan4/` — `app.py`, `CLAUDE.md`, `RUNBOOK.md` y
`COMMIT-BASE.txt` con el SHA exacto. Creado **antes** de tocar nada, como manda la regla. El
directorio está en `.gitignore`: vive en disco y no se versiona.

---

## 5. PR #43 y #44, reverificados hoy

| PR | Estado | Mergeable | Tamaño | Última actualización |
|---|---|---|---:|---|
| **#43** (rediseño) | OPEN | ⚠️ **CONFLICTING / DIRTY** | +28,582 / −3,308 | 2026-09-04 |
| **#44** (endurecimiento) | OPEN | ⚠️ **CONFLICTING / DIRTY** | +4,403 / −74 | 2026-09-06 |

**El riesgo R7 del plan se materializó**, y el plan lo anticipaba: *«#43 deja de ser
`MERGEABLE` tras el merge del Plan 1 — T4.0 lo reverifica; T4.4 contempla el rebase»*.

### 5.1 Qué conflictúa, medido en local

- **#43 → sólo `CLAUDE.md`.** Un archivo.
- **#44 → 4 archivos:** `CLAUDE.md`, `app.py`, `docs/RUNBOOK.md` y el índice de agosto.

### 5.2 🚨 El conflicto del #43 es una defensa, no un estorbo

El #43 **reescribe las mismas líneas de `CLAUDE.md`** que el cierre del Plan 1 corrigió, y su
versión **reintroduce dos afirmaciones falsas**: que los secretos van en Railway y que `main`
tiene auto-deploy. Las dos dejaron de ser ciertas el **2026-08-19**.

Si el #43 se mergeara limpio, **borraría la corrección en silencio** y devolvería a `main` el
invariante que costó el diagnóstico entero de T1.6.

**Al resolver el conflicto en T4.4:** conservar la versión actual de `main` en las líneas de
Railway, despliegue, secretos y baseline; tomar del #43 lo suyo (arquitectura de
`templates/`+`static/`, Chart.js auto-hospedado, sistema de diseño, `.gitattributes`,
`test_pii_repositorio.py`).

### 5.3 Su CI está en verde, pero es un verde viejo

Los dos PR tienen los dos checks en `pass`, **de corridas del 4 y el 6 de septiembre** —
anteriores a los merges del Plan 1. **Ese verde no dice nada del estado de hoy.** Hay que
revalidarlos después del rebase, no antes.

### 5.4 El baseline del #43 no se copia

El #43 declara **900 passed, 2 skipped**, medidos sobre la rama del Plan 1, no sobre `main`.
Tras el rebase hay que **remedirlo**, no heredarlo.

---

## 6. Qué entrega T4.0 a T4.1

- **El instrumento existe:** 9 capturas y 6 mediciones, ambas de producción real.
- **Una advertencia con número:** el dashboard parte de un CLS de **0.1924**. CE6 no puede
  conformarse con «no empeoró».
- **Dos conflictos a resolver**, uno de ellos deliberado y con instrucciones escritas.
- **Una trampa nueva documentada:** un observador de rendimiento mal registrado devuelve ceros
  sin avisar.
