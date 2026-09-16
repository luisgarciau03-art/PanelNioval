# RELEVO ACTUAL — PanelNioval · tanda 2026-09-15

> **Archivo único que se SOBRESCRIBE al cerrar CADA tarea.** Siempre contiene el mensaje
> completo para arrancar una sesión nueva.
>
> **Estado: Plan 1 CERRADO Y EN PRODUCCIÓN (8/8) · Plan 4 EN CURSO (T4.0 y T4.1 hechas).** Siguiente: **T4.2 — gate del owner**.

---

Continúas el proyecto **PanelNioval**. **Sesión 3.** NO empieces de cero: el diseño está hecho,
**el Plan 1 está cerrado, mergeado y desplegado**, y los Planes 4 y 3 ya están construidos en
PR abiertos.

**PROYECTO:** `C:\Users\PC 1\PanelNioval`
**`main`:** **`28eacfe`** — Plan 1 completo (PR #42) + su cierre documental (PR #45).
**En el VPS corre `8bac782`**, y está bien: el PR #45 es sólo documentación, no hay nada que redesplegar.
**RAMA DEL PLAN 1:** `feat/relevancia-nacional-produccion` — **mergeada dos veces y agotada.** No sigas en ella.
**RAMA DE TRABAJO:** **`feat/rediseno-aterrizaje`** — ya creada desde `main` `a97b494` y empujada. Último commit `59df79f`.

---

## ⚠️ LO PRIMERO: EL INVARIANTE DE LOS CUATRO PLANES ES FALSO

Los cuatro planes repiten: *«nunca `main`, el VPS auto-deploya `main`»*.

**NO HAY AUTO-DEPLOY.** Railway se eliminó el **2026-08-19** (404 reverificado el 2026-09-16) y
el VPS de Vultr **no tiene webhook ni workflow**. `.github/workflows/` sólo trae `tests.yml`.

- **Mergear a `main` NO publica nada.** «Mergeado» y «desplegado» son **dos estados distintos**
  en este proyecto, y la tanda los trataba como uno.
- **Sigue vigente no trabajar en `main`**, pero por otro motivo: `main` es lo que el owner
  desplegará, así que un rojo ahí sale al VPS en el siguiente `git pull`.
- **Cada plan que diga «en producción» necesita su paso de despliegue explícito.** Los Planes
  2, 3 y 4 llevan el invariante falso escrito.

**El comando real** (corregido: el del RUNBOOK llevaba `git pull` y el repo del servidor estaba
en **HEAD desacoplado**, donde no avanza nada):

```bash
ssh root@155.138.200.66 'cd /srv/panel/app && git fetch origin && git checkout main && git merge --ff-only origin/main && cd /srv/panel && docker compose up -d --build'
```

Verifica siempre después: `ssh root@155.138.200.66 'cd /srv/panel/app && git log -1 --oneline'`.

---

## LEE PRIMERO, EN ESTE ORDEN (de disco, completo, antes de tocar nada)

1. `C:\Users\PC 1\.claude\BIBLIOTECA-HERRAMIENTAS.md` — 653 herramientas, 6 fuentes.
2. `C:\Users\PC 1\PanelNioval\CLAUDE.md` — reglas del proyecto (**actualizado en T1.7**).
3. `docs/superpowers/plans/2026-09-15-indice-tanda.md` — orden y dependencias. **1/4 planes**.
4. `docs/superpowers/plans/2026-09-15-plan4-rediseno-profesional-aterrizaje.md` — **INVARIANTES + bloque de T4.0**.
5. `docs/auditoria/2026-09-15-verificacion-produccion-plan1.md` — **el hallazgo del auto-deploy y el de privacidad.**

---

## INVARIANTES (literales del plan, con la corrección de T1.6 marcada)

- **OBJETIVO:** que el importador ordene ciudades por relevancia ferretera **nacional**, cueste lo mínimo en Places, cuente la verdad y se vea profesional — **en producción**.
- **DEFINICIÓN DE TERMINADO:** los 4 planes cerrados, sus PRs en `main`, el VPS sirviendo ese código y `python tools/smoke_panel.py https://panelnioval.duckdns.org --token <valor>` imprimiendo `Todo OK ✅`. ⚠️ **El smoke NO cubre ninguna ruta del importador**: puede dar verde con un despliegue incompleto. Verifica aparte lo que hayas desplegado.
- **RAMA:** una por plan, desde `main` actualizado · **NUNCA `main`** (motivo corregido arriba) · commits convencionales en español.
- **BASELINE:** `python -m pytest tests/` → **525 passed, 1 skipped** sobre `main`. Histórico: 388 → 482 → 491 → **525**. **SIN `-q`**: `pytest.ini` ya lo trae y el segundo lo vuelve `-qq`, ocultando el resumen.
- **GATES POR TAREA:** `python-reviewer` + `code-reviewer` [+ `security-reviewer` si toca auth, token, entrada de usuario, Places o Sheets] [+ `silent-failure-hunter` si toca `try/except` o fallbacks] [+ `typescript-reviewer` si toca `static/js/*` — **el Plan 4 SÍ lo toca**].
- **PROHIBIDO:** (1) trabajar en `main`; (2) **borrar** — lo retirado va a `docs/auditoria/respaldos/<fecha>/`; (3) mergear con la suite en rojo o con CRITICAL/HIGH abierto; (4) commitear teléfonos o nombres de clientes; (5) reordenar los PR #43/#44 fuera del orden del índice.
- **SECUENCIA:** Plan 1 ✅ → **Plan 4** → Plan 3 → Plan 2.

---

## AVANCE

- **Global: 1 / 4 planes (25 %)** · Tareas **10 / 34 (29.4 %)** · **Plan 4 en curso (2/12)**
- **Plan 1: CERRADO, MERGEADO Y DESPLEGADO.** El operador ve **1,004 ciudades** donde había 606.

---

## EL PLAN 1, EN RESULTADOS (no en narrativa)

| Qué | Evidencia |
|---|---|
| **606 → 1,004 municipios**, 32/32 entidades, **0 perdidas** | corte ≥10, ADR §9 |
| Masa ferretera nacional **86.3 % → 93.7 %**; Sureste **65.7 % → 80.6 %** | `docs/investigacion/2026-09-15-cobertura-catalogo-ciudades.md` |
| **CE1** 0 de 995 fuera · **CE2** 8 regiones exactas · **CE3** mínimo 14.1 · **CE4** aprobado por el owner | tests permanentes + §8.1 del doc de T1.4 |
| **En producción y verificado:** `/api/importador/ciudades` 404 → 200, 1,004 servidas, 398/398 nuevas vivas | `docs/auditoria/2026-09-15-verificacion-produccion-plan1.md` §9 |
| Baseline **388 → 525** | 43 tests nuevos en T1.3/T1.4 |
| **11 gates** en 5 tareas, **ninguno con CRITICAL ni HIGH** | — |

**Defectos reales encontrados y corregidos por el camino:** el endpoint desempataba por nombre
contra el ADR (103 empates, 232 ciudades); el relleno de espacios del DENUE viajaba literal a
Places; el RUNBOOK y `tests.yml` afirmaban un auto-deploy inexistente; el comando de despliegue
del RUNBOOK no funcionaba sobre HEAD desacoplado.

---

## ESTADO DE VERIFICACIÓN AHORA MISMO

- **`main` = `8bac782`.** `pytest` sobre `main`: **525 passed, 1 skipped**.
- **Producción = `8bac782`**, verificado en el servidor. `RestartCount=0`. Smoke `Todo OK ✅`.
- **PR #42: MERGED** (`8bac782`). **PR #45: MERGED** (`28eacfe`, cierre documental).
- ⚠️ **PR #43: `CONFLICTING`** — sólo en `CLAUDE.md`, **a propósito** (ver abajo).
- ⚠️ **PR #44: `CONFLICTING`** en 4 archivos: `CLAUDE.md`, `app.py`, `docs/RUNBOOK.md` y `docs/superpowers/plans/2026-08-27-indice-tanda.md`.
- Árbol limpio, todo empujado.

---

## HECHO EN T4.0 (commit `2ed61e7`)

| Qué | Evidencia |
|---|---|
| Rama desde `main` `a97b494`, respaldo **antes** de tocar nada, baseline **525** | `docs/auditoria/2026-09-15-estado-de-partida-plan4.md` |
| **9 capturas** del «antes», de producción, 3 superficies × 320/768/1440 | `docs/diseno/antes-2026-09-15/` |
| ⚠️ **Las del formulario traían nombre y teléfono de un cliente real.** Rehechas anonimizando **en el origen** (interceptando el endpoint): la PII nunca llegó a disco | §2.1 del informe |
| **Línea base CE6:** dashboard 1440 **CLS 0.1924**, importador 320 **CLS 0.1073** — los dos sobre el umbral de 0.1. LCP máximo 548 ms | `docs/diseno/antes-2026-09-15/metricas-base.json` |
| PR #43 y #44 reverificados: **los dos CONFLICTING** (riesgo R7, que el plan anticipaba) | §5 del informe |

**Lo más útil que dejó T4.0:** el dashboard **ya falla CLS antes del rediseño**. CE6 dice «no
empeorar», y sobre 0.1924 ese listón es demasiado bajo. **Apunta a bajar de 0.1**, y si no se
consigue, dilo con el número delante en vez de esconderte tras un «no empeoró».

---

## HECHO EN T4.1 (commits `4212917` · `87fdbea` · `7ae544b`)

**El criterio se fijó y se commiteó ANTES de mirar** (`4212917`), así que `git log` demuestra
que la auditoría no es una racionalización de lo ya construido.

**Veredicto:** el rediseño **cumple el encargo** y supera el criterio anti-plantilla — 5
cualidades probadas de 10, sobre un mínimo de 4 — con **5 huecos bloqueantes**.

| Lo mejor que encontró | |
|---|---|
| La dirección visual acierta el dominio | editorial/Swiss, con el argumento correcto: *«un rediseño que se vea mejor y capture más lento es un retroceso»* |
| El formulario se midió donde importa | de **~90 a 11 pulsaciones** por captura |
| **Validación cruzada del CLS** | el PR midió **0.1941** y T4.0 midió **0.1924** con otra herramienta, otro entorno y otros datos. **0.9 % de diferencia** |
| El rediseño arregla el CLS de carga | 9/9 por debajo de 0.1 |

**Los 5 bloqueantes:**

- **B1** · Las capturas del «después» del tablero están **a cero**. T4.2 compararía un panel con
  7,180 contactos contra uno vacío. **Es el único que bloquea el gate del owner.**
- **B2** · La pantalla principal **no usa el sistema** que el PR declara, y el dato es binario:
  espaciado con token **29/29** en `componentes.css` y **50/52** en `importador.css`, contra
  **9/86** en `dashboard.css` y **0/31** en `formulario.css`.
- **B3** · Tarjetas dentro de tarjetas. Bloquea **por regla**, no por coste al operador.
- **B4** · **Las 9 mediciones de CLS son de CARGA, no de interacción.** Cuatro bloques del
  importador empujan al pulsar «Buscar», una vez por corrida, y nadie lo midió.
- **B5** · 🔍 **El buscador no normaliza acentos.** `toLowerCase()` y nada más, así que teclear
  `leon` no encuentra `León`. **319 de las 1,004 ciudades (31.8 %)** llevan acento, y **39 del
  top-100**. El fallo es **mudo**: la lista queda vacía y el operador no distingue «no está» de
  «me la esconde».

**El gate de `ux-researcher` corrigió el veredicto**, y eso es lo que más valor dio: encontró
una contradicción dentro del propio documento, subió dos huecos de severidad y planteó B5 como
hipótesis, que yo confirmé y medí en la rama.

---

## SIGUIENTE PASO EXACTO

**Plan 4, Tarea T4.2 — Gate del owner: aprobar la dirección visual antes de invertir más.**

```
ANCLA · Plan 4 Tarea T4.2 · importador nacional barato veraz profesional · avance 10/34 ·
 baseline: python -m pytest tests/  -> 525 passed, 1 skipped
```

⚠️ **NO presentes el gate sin cerrar B1 primero.** Las capturas del «después» del tablero están
a cero: el owner compararía «con datos» contra «sin datos» y lo que juzgaría no sería el
rediseño. **Recapturar las tres superficies con datos**, con el procedimiento de anonimización
de T4.0 (interceptar `/api/formulario/siguiente`; el script está en el informe de T4.0 §2.1).

Después, lee el bloque de T4.2 en el plan y presenta al owner **la dirección**, no los huecos:
*editorial/Swiss, denso y escaneable, sin fuente web, sin profundidad ni textura, con el color
como significado*. La auditoría la respalda. B2–B5 son deuda de implementación y su sitio es
T4.3, no el juicio del owner.

---

## PENDIENTES Y BLOQUEOS

| Asunto | Qué falta | De quién |
|---|---|---|
| **CE5 del Plan 1** | ⚠️ **Dos de los tres puntos ya están cubiertos sin querer:** `docs/diseno/antes-2026-09-15/importador-1440.png` (de T4.0) muestra «CIUDADES (1004) — ORDENADAS POR PRIORIDAD» y el desplegable en «Todas (1004)». Falta el tercero: una ciudad sin historial puntuando > 0 y no al final | **Owner**, o una captura más |
| 🔒 **PII en `sin_clasificar`** | El endpoint publica **8 teléfonos y 1 correo** de clientes contra lo que promete su docstring. Tras token; **no lo introdujo el Plan 1** (el endpoint viejo ya lo hacía). O se sanea la salida conservando el aviso, o se corrige la promesa | **Owner decide**; ver RUNBOOK § «Ciudades sin clasificar» |
| **El smoke no cubre el importador** | Dio `Todo OK ✅` contra un panel sin desplegar. Añadirle `/api/importador/ciudades` | Tarea pendiente, sin asignar |
| **El smoke revienta en Windows** | `UnicodeEncodeError` al imprimir el `✅`; **sale con código ≠ 0 aunque los 5 chequeos pasen**. Se sortea con `PYTHONIOENCODING=utf-8` | Tarea pendiente, sin asignar |
| **PR #43** (Plan 4) | ⚠️ **`CONFLICTING` en `CLAUDE.md`** (era `MERGEABLE`). Provocado a propósito por el PR #45: sin él, el #43 borraba la corrección del auto-deploy en silencio. **Al resolver, conservar la versión de T1.7** | Plan 4, T4.2 y T4.4 |
| **PR #44** | `CONFLICTING` contra `main` en **4 archivos** (`CLAUDE.md`, `app.py`, `RUNBOOK`, índice de agosto) **y** contra el #43 | Plan 4, T4.6 |
| **Caché `_estado_catalogo`** | `app.py:895-897` no se invalida: un fallo transitorio al arrancar serviría `catalogo_cargado: false` hasta el reinicio. No es silencioso | Insumo del Plan 3 |
| **Bug de conteo** | Diagnóstico H1/H2/H3 — sin hacer | Plan 3 |
| **`claude-mem` caído** | Desde 2026-09-05 (issue #2188) | **El relevo es la única persistencia** |
| **Rotar `TELEGRAM_TOKEN`** y la Places key | Heredado (~14 copias) | **Owner**, no automatizable |
| **Decisiones D1, D2, D3, D5** | Respuesta del owner. **D4 resuelta y aplicada** | Se avanza con la recomendada |

---

## SUPUESTOS VIVOS

- `SUPUESTO: el trabajo va sobre PanelNioval, no sobre BruceWhatsapp. — afecta los 4 planes.`
- `SUPUESTO: el gate «≥ 626» se reinterpreta como «≥ baseline de la rama base». Hoy 525 sobre main. — afecta Planes 2, 3 y 4.`
- `SUPUESTO: los fixtures del universo ferretero se regeneran junto con el catálogo si alguien usa un corte del DENUE más nuevo. Hoy ambos salen de DENUE 05_2026.`
- `SUPUESTO: CE4 aprueba el orden EXÓGENO del top-30, NO la cola larga (las 398 nuevas arrancan en el #428) ni el orden final en producción, donde factor_nioval reordena (73 valores, de 0.65 a 1.102). — no citar esa aprobación de más.`
- `SUPUESTO: «tokens de la API» = consumo facturable de Google Places. — afecta Plan 2. Ver D2.`
- `SUPUESTO: si la fuga de Details medida en T2.1 es < 10 %, T2.2–T2.4 se saltan. — afecta Plan 2.`
- `SUPUESTO: el síntoma del conteo se observó en producción, no en una rama local. — afecta Plan 3, T3.1.`
- `SUPUESTO: PR #44 se conserva y se rebasa tras #43. — afecta Plan 4, T4.6. Ver D3.`

---

## DECISIONES CERRADAS (NO reabrir)

- **Modelo = logarítmico × `factor_nioval`** · **HTML a `templates/`+`static/`** (PR #43) ·
  **estado del importador en disco** · **Places con `fields` explícitos** · **`/salud` no
  revela versión ni commit** (⚠️ y **`/salud` no existe en `main`**: su 404 no es síntoma).
- **D4 → corte ≥10 ferreterías**, aplicado y en producción (ADR §9).
- **El 75 % del test de cobertura es NORMATIVO**, elegido tras ver los datos y declarado.
- **El desempate final es la CLAVE INEGI, no el nombre** (ADR §7). Y **la clave sigue sin
  publicarse en el payload**: son dos decisiones distintas, las dos en pie.
- **CE4 aprobado por el owner**, sin reservas.
- **El PR #42 se mergeó con MERGE COMMIT, no con squash.** Motivo medido: el squash rompía el
  #43 en 11 archivos.
- **El owner decidió aterrizar sin esperar al Plan 4.** No se re-litiga.

---

## TRAMPAS DESCUBIERTAS (lo que costó tiempo y no está en ningún otro documento)

- **🆕 NO hay auto-deploy.** Ver arriba. Es la más cara de todas: el merge parecía terminado y
  el operador no veía nada.
- **🆕 El smoke puede dar `Todo OK ✅` con el despliegue a medias.** No cubre ninguna ruta del
  importador. **Un smoke que no toca lo que acabas de desplegar no verifica tu despliegue.**
- **🆕 El repo del servidor estaba en HEAD desacoplado.** El `git pull` documentado no avanzaba
  nada. Usa `checkout main` + `merge --ff-only`, y **comprueba el commit servido después**.
- **🆕 Con PRs apilados, simula el método de merge ANTES de elegirlo.** El `--squash` que pedía
  el plan rompía el #43 en 11 archivos; el merge commit no. Costó un minuto comprobarlo.
- **🆕 Aterrizar un PR mueve el estado de los demás.** El #44 pasó de `MERGEABLE` a
  `CONFLICTING`. Anota el estado de **todos** los PR abiertos, antes y después.
- **🆕 El heredoc de bash SE COME UN BACKSLASH en este entorno.** Una secuencia de escape llega
  a Python como salto de línea real. Rompió un archivo de test y un ancla de búsqueda. **Usa
  `chr(92)`** o escribe el archivo con la herramienta de escritura.
- **🆕 `git checkout -- app.py` para deshacer una mutación se lleva también lo no commiteado.**
  Pasó: revirtió un arreglo sin commitear. **Commitea antes de mutar.**
- **🆕 El stdout de Python aquí es cp1252** y corrompe acentos al redirigir a archivo. Escribe
  con `pathlib.write_text(..., encoding="utf-8")`, no con `>`.
- **🆕 La app es fail-closed:** sin `PANEL_DASHBOARD_TOKEN` no arranca. Para un script suelto,
  `PANEL_AUTH_DESACTIVADA=1` (lo que hace `tests/conftest.py`).
- **🆕 `normalizar()` colapsa espacios y eso ESCONDE bugs.** Un nombre con 70 espacios pasaba
  todos los tests de duplicados. Mira el nombre **crudo**.
- **🆕 Un guard por subcadena se engaña con un comentario.** Limpia comentarios antes de buscar.
- **🆕 Prueba las guardas por mutación.** Planta el defecto y comprueba que falla; si no, su
  verde no vale nada.
- **🆕 `add_init_script` EJECUTA el string, no lo llama.** Pasarle `() => {...}` define una
  función y la tira: el `PerformanceObserver` nunca se registra y **LCP y CLS salen 0.0 sin un
  solo error**. Envuelve en IIFE, y trata un `LCP = 0` como fallo de medición, no como valor.
- **🆕 Las capturas de producción llevan PII.** El formulario muestra nombre y teléfono de un
  cliente real, el teléfono dos veces. Anonimiza **en el origen** interceptando el endpoint;
  difuminar después ya es tarde. Y **abre las capturas antes de commitearlas**.
- **🆕 El `.gitignore` volvió a morder:** `metricas-base.json` quedaba fuera del repo por la
  regla global `*.json`, en silencio. Ya tiene excepción. **Cualquier `.json` nuevo que deba
  versionarse la necesita** — compruébalo con `git check-ignore -v`.
- **El baseline es por rama:** 388 / 482 / 491 / 525.
- **`pytest -q` oculta el resultado.** Correr `python -m pytest tests/` a secas.
- **`.gitignore` ignora `*.json` global** con excepción por ruta exacta para
  `datos/ciudades_mx.json`. Los fixtures de test son `.csv`/`.txt` **a propósito**.
- **La caché del INEGI ya está poblada** en `C:\Users\PC 1\.cache\inegi` (ferreterías:
  **60,209,960 bytes exactos**). Regenerar no baja 117 MB.
- **Las URLs de DENUE tienen trampa:** `denue_00_46_csv.zip` responde **HTTP 200 con 0 bytes**.
  Validar tamaño mínimo, nunca el status code. **No le quites esa validación al generador.**
- **No pases rutas MSYS (`/c/Users/…`) a Python**: es un Python de Windows. Usa `C:/Users/…`.
- **La caché de Places falsea la medición del ahorro.** Mide ciudad virgen y trabajada aparte.
- **Los planes 4 y 3 ya están construidos.** Quien no lea esto rediseñará lo que ya existe.

---

## EL TOKEN, PARA CUANDO LO NECESITES EN T4.0

**No se pega en la conversación**: quedaría permanente en la transcripción. Vive en
`tokens-panelnioval.txt` (ignorado por git), como `PANEL_DASHBOARD_TOKEN=…`. Léelo a una
variable desde el archivo y pásalo en memoria; **no lo imprimas, ni entero ni en fragmentos**.

---

## REGLAS QUE SIGUEN VIGENTES

Anclaje al iniciar cada tarea · test de deriva al cerrarla · umbrales de relevo (3 tareas, 50 %
del plan, compactación o fin de plan) · dudas acumuladas y presentadas juntas al cerrar cada
plan · **herramientas de la tabla de asignación (no colapsar a Superpowers: son 14 de 653)** ·
merge sólo con gates en verde · **nunca trabajar en `main`** · **y ahora también: desplegar es
un paso aparte, y verificarlo es otro.**
