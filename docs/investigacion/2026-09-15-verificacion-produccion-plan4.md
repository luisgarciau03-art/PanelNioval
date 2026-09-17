# VERIFICACIÓN EN PRODUCCIÓN — Plan 4

**Tarea:** Plan 4 · T4.7 · **Fecha:** 2026-09-16 · **Desplegado:** `8bac782` → **`edda166`**
**Por qué aquí y no en local:** el trabajo de agosto midió accesibilidad y responsive **en
local**. Lo que llega al operador es lo que sirve el VPS.

---

## 1. La respuesta, en una línea

> **Desplegado y verificado. CE4, CE5 y CE8 en verde. CE6 es un intercambio, no una victoria
> limpia, y se cuenta con los dos números delante:** el CLS —lo que de verdad sufre el
> operador— mejora en todo, y el del tablero baja de **0.1924 a 0.0358**. Pero el **LCP del
> tablero se triplicó** (132 → 416 ms), y la causa es la propia extracción. Sigue **6× por
> debajo** del objetivo de 2.5 s.

---

## 2. El despliegue: tres pasos, y uno no estaba en el comando

| Paso | Por qué |
|---|---|
| 1. Repo del servidor a `main` | `git fetch` + `checkout main` + `merge --ff-only` |
| 2. **Copiar la plantilla del compose** | ⚠️ **Un `git pull` NO lo hace.** El compose vivo (`/srv/panel/docker-compose.yml`) es una **copia**, y el healthcheck vive ahí |
| 3. `docker compose up -d --build` | **`--build` no es opcional:** el PR #44 añade `tzdata` y `Flask-Limiter` |

**Alcance real:** 87 commits, 175 archivos, +23,099 / −3,592. **Rollback:** `8bac782`.

### 2.1 Por qué `--build` era obligatorio

`requirements.txt` añade **`tzdata`**, y su propio comentario lo marca como el **riesgo R3** del
Plan 5: sin ella, `zoneinfo.ZoneInfo('America/Mexico_City')` lanza al importar
`nucleo_catalogo.py` y **el panel no arranca**. `python:3.11-slim` no la trae.

Un reinicio sin reconstruir habría dejado el panel **caído**. Instalado y verificado:
`tzdata-2026.4`, `Flask-Limiter-4.1.1`.

### 2.2 El paso que el comando documentado no cubre

El compose del repo es una **plantilla**; la copia viva del servidor es la que manda, y su
propio comentario lo dice: *«`docker compose ps` lee ésta»*.

**Verificado antes de copiar, no después:** quitando comentarios, líneas en blanco y el bloque
del healthcheck, la plantilla y el vivo son **byte a byte idénticos** (mismo MD5). Copiarla
sólo añade el healthcheck; no toca `env_file`, volúmenes, red ni `mem_limit`. El compose vivo
quedó respaldado antes (`docker-compose.yml.respaldo-20260917-0251`) y se validó con
`docker compose config` después.

---

## 3. CE8 · Healthcheck — **verde**

```
panel   Up 56 seconds (healthy)
Health=healthy   RestartCount=0   Running=true
```

Arranque limpio con `gthread`, **0 errores**, y ni rastro de `ZoneInfoNotFound`.

**Smoke:** `Todo OK ✅`. Y lo que el smoke **no** cubre, comprobado aparte:
`/api/importador/ciudades` sirve **1,004 ciudades**, las 8 regiones cuadran y el mínimo de
`potencial_mercado` es **14.1**.

---

## 4. CE4 · Accesibilidad — **verde, 0 hallazgos**

| Superficie | Contenido | Desborde (5 anchos) | Foco |
|---|---|---|---|
| Tablero | sin hallazgos | OK en los 5 | 0 paradas sin indicador |
| Formulario | sin hallazgos | OK en los 5 | **7** paradas, 0 sin indicador |
| Importador | sin hallazgos | OK en los 5 | **6** paradas, 0 sin indicador |

**TOTAL: 0 hallazgos.**

⚠️ **Dicho con precisión:** `tools/verificar_accesibilidad.py` levanta un servidor **local**, no
apunta al VPS. Es válido aquí **porque el contraste y el desborde los determinan el HTML y el
CSS**, y son los mismos bytes: el servidor corre `edda166`, verificado en él. Lo que no cubre
—lectores de pantalla reales y zoom al 200 %— sigue siendo gate humano, como ya declaraba el
trabajo de agosto.

Y el método importa: el auditor **compone la opacidad acumulada** y mide contra el primer fondo
opaco, degradados incluidos. La T4.9 demostró que el fallo más caro de la tanda —un token
válido con `opacity:.55` que da 2.97:1— **no lo veía ningún guarda de patrones**, porque el
color declarado sí era un token.

---

## 5. CE5 · Responsive — **verde, 0 desbordes en 18 combinaciones**

3 superficies × **6 anchos** (320, 375, 768, 1024, 1440, **1920**), medido contra producción:

> **`scrollWidth - clientWidth` = 0 en las 18.**

La prueba de CE5 es esa medición, no una imagen: «sin scroll horizontal» es un número.

---

## 6. CE6 · Rendimiento — **un intercambio, contado entero**

### 6.1 CLS — mejora en todo

| Superficie | Antes (T4.0) | Ahora | |
|---|---:|---:|---|
| **Tablero 1440** | **0.1924** | **0.0358** | **5.4× mejor** |
| Tablero 320 | 0.0952 | 0.0010 | mejora |
| Importador 320 | 0.1073 | 0.0405 | mejora |
| Importador 1440 | 0.0289 | 0.0185 | mejora |
| Formulario (ambos) | 0.0000 | 0.0000 | igual |

**Peor CLS de las 18 combinaciones: 0.0858. Ninguna por encima de 0.1.**

En T4.0 escribí que CE6 pedía «no empeorar» y que sobre un 0.1924 ese listón era demasiado
bajo — que había que **apuntar a bajar de 0.1**. Se consiguió: el tablero queda en **0.0358**.

### 6.2 LCP — el tablero se triplicó, y hay que decirlo

Medido con **mediana de 3 corridas**, igual que la línea base:

| Punto | Antes | Ahora | |
|---|---:|---:|---|
| **Tablero 320** | 132 ms | **416 ms** | **×3.2** |
| **Tablero 1440** | 148 ms | **416 ms** | **×2.8** |
| Formulario 320 | 536 ms | 520 ms | similar |
| Importador 320 | 460 ms | 524 ms | similar |

**La causa es la propia extracción.** El tablero ahora pide **12 recursos** —cinco JS y seis
CSS— donde antes todo iba en línea dentro del HTML. Más peticiones, LCP más tardío. Es el
precio estructural de sacar 3,240 líneas del monolito.

**Lo que no cambia el veredicto:** 416 ms está **6× por debajo** del objetivo de 2.5 s. En
términos absolutos el tablero sigue pintando rapidísimo.

**Lo que sí hay que decir:** en términos relativos **es una regresión**, y CE6 dice «sin
regresión». Presentarlo como victoria limpia sería esconder la mitad del dato.

**El juicio, declarado como tal:** el intercambio vale la pena. El CLS es lo que el operador
*sufre* —contenido que salta bajo el cursor mientras captura— y mejora 5.4× en la pantalla
principal; el LCP empeora dentro de un margen que nadie percibe a 416 ms. Pero es un **juicio**,
no una medición, y si alguien lo discute tiene los dos números para hacerlo.

### 6.3 Un valor atípico que merece contarse

La primera pasada, con **una sola muestra por punto**, dio **6,064 ms** de LCP en el tablero a
320. Con mediana de 3 son **416** (muestras: 496 / 416 / 400).

**Una sola muestra puede ser 15× la mediana.** Casi lo reporto como una regresión catastrófica.
La línea base de T4.0 ya usaba mediana de 3 precisamente por esto, y compararla contra una
muestra suelta habría sido comparar dos cosas distintas.

### 6.4 Chart.js — auto-hospedado, verificado

> **Peticiones a un CDN durante las 18 cargas: 0.**

Venía de jsdelivr en `<head>` y sin `defer`: el tablero no pintaba **nada** hasta que el CDN
contestara, y contestar le costó **15.1 s** medidos.

---

## 7. Las capturas, y una decisión que no tomé solo

Las 18 capturas contra producción mostraban **datos reales de negocio** —1,494 aprobados, 7,180
contactos, el ranking de ciudades—. Sin PII, pero **contra el estándar que el propio proyecto se
puso**: `capturar_superficies.py` corta las credenciales y **aborta si el panel consigue
autenticarse**, *«para que ninguna captura lleve datos de clientes»*.

Ya hay una pregunta abierta al owner por las 9 capturas equivalentes de T4.0. **Agravarla con 18
más habría sido decidir por él.**

- Las 18 de producción están **apartadas**, no borradas, en
  `docs/auditoria/respaldos/2026-09-16-capturas-produccion/` (el directorio está en
  `.gitignore`).
- Las **15 que se versionan** se regeneraron con la herramienta del proyecto y sus datos
  sintéticos, en `docs/diseno/despues-2026-09-15/`.

**CE5 no pierde nada:** su prueba es la medición de desborde, no la imagen.

---

## 8. Estado de los criterios

| | Criterio | Estado |
|---|---|---|
| **CE4** | Accesibilidad | ✅ **0 hallazgos**, foco visible en todas las paradas |
| **CE5** | Responsive, 6 anchos, sin scroll horizontal | ✅ **0 desbordes en 18 combinaciones** |
| **CE6** | Rendimiento sin regresión | ⚠️ **Intercambio declarado:** CLS mejora en todo (peor 0.0858, 0 sobre 0.1); **LCP del tablero ×3**, dentro del objetivo |
| **CE8** | Healthcheck | ✅ contenedor `healthy`, `RestartCount=0` |

---

## 9. Lo que esta tarea NO cierra

- **Lectores de pantalla reales y zoom al 200 %** — gate humano, ya declarado en agosto.
- **La sección de Ventas sigue sin ejercitarse con datos** (no hay fixture para `/api/ventas/*`).
- **La decisión del owner sobre las capturas con datos de producción**, ahora con dos juegos
  afectados (T4.0 y T4.7).
- **El LCP del tablero.** Si alguien quiere recuperarlo, la palanca no es volver al monolito:
  es agrupar o precargar los 12 recursos. Queda anotado, no hecho.
