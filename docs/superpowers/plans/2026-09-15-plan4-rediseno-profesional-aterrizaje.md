# PLAN 4 — Rediseño profesional del panel: cerrar la brecha y aterrizarlo

**Diseñado:** 2026-09-15 · **Proyecto:** PanelNioval — `C:\Users\PC 1\PanelNioval`
**Superficies:** `/` (tablero) · `/formulario` · `/importador`
**Orden de ejecución dentro de la tanda:** **2.º** (ver índice)

---

## INVARIANTES — releer al iniciar CADA tarea (no continuar sin esto)

- **OBJETIVO DEL PROYECTO:** que el importador de PanelNioval ordene ciudades por relevancia ferretera **nacional**, cueste lo mínimo en Places, cuente la verdad y se vea profesional — **en producción**, no en una rama.
- **DEFINICIÓN DE TERMINADO:** los 4 planes cerrados, sus PRs mergeados a `main`, el VPS sirviendo ese código y `python tools/smoke_panel.py https://panelnioval.duckdns.org --token <valor>` imprimiendo `Todo OK ✅`.
- **RAMA:** una por plan, creada desde `main` actualizado · **NUNCA `main`** (el VPS auto-deploya `main`) · commits convencionales en español.
- **BASELINE (nada avanza si falla):** `cd "C:\Users\PC 1\PanelNioval" && python -m pytest tests/` → **≥ 626 passed, 1 skipped**, exit 0. **SIN `-q`**: `pytest.ini` ya lo trae; el segundo lo convierte en `-qq` y **oculta la línea del resumen**.
- **GATES POR TAREA:** `python-reviewer` + `code-reviewer` [+ `security-reviewer` si toca auth, token, entrada de usuario, Places o Sheets] [+ `silent-failure-hunter` si toca `try/except` o fallbacks] [+ `typescript-reviewer` si toca `static/js/*`].
- **PROHIBIDO:** (1) trabajar en `main`; (2) **borrar** — lo retirado va a `docs/auditoria/respaldos/<fecha>/`; (3) mergear con la suite en rojo o con CRITICAL/HIGH abierto; (4) commitear teléfonos o nombres de clientes — anonimizar a `+52…XXXX`; (5) rebasar, cerrar o reordenar los PR #42/#43/#44 fuera del orden de aterrizaje del índice.
- **DECISIONES YA TOMADAS (no reabrir):** modelo de relevancia = logarítmico × `factor_nioval` (ADR `2026-08-28`, tres candidatos medidos sobre 589 municipios); HTML extraído a `templates/`+`static/` (PR #43); estado del importador compartido en disco (ADR `2026-08-27`); Places con `fields` explícitos + caché 30 d (PR #38, mergeado).
- **SECUENCIA:** **Plan 1 → Plan 4 → Plan 3 → Plan 2.** Es dependencia real: PR #43 está **apilado sobre** PR #42, y el bug del Plan 3 debe arreglarse una sola vez, en la estructura final (`static/js/importador.js`).

---

## 0. ESTADO DE PARTIDA VERIFICADO EN DISCO (2026-09-15)

### 0.1 El rediseño ya está construido — y no está desplegado

| Hecho | Valor | Cómo se comprobó |
|---|---|---|
| **PR #43** | **OPEN · MERGEABLE** · *feat(plan4): rediseno profesional del panel — las 3 superficies, 12/12 tareas* | `gh pr view 43` |
| Tamaño | **+28,582 / −3,308** | ídem |
| Efecto en `app.py` | **−3,240 líneas** (el HTML y el JS salen del monolito) | `git diff --stat main..feat/rediseno-panel -- app.py` |
| Apilado sobre PR #42 | **SÍ** | `git merge-base --is-ancestor feat/relevancia-ciudades-nacional feat/rediseno-panel` → 0 |
| Conflicto con PR #44 | **SÍ, 5 hunks** | `git merge-tree` entre ambas ramas |
| Abierto desde | **2026-08-31** | `gh pr view 43` |

**Estructura nueva que entrega el PR #43** (verificada con `git ls-tree`):

```
templates/        dashboard.html   formulario.html   importador.html
static/css/       tokens.css  base.css  componentes.css
                  dashboard.css  formulario.css  importador.css
static/js/        dashboard.js  formulario.js  importador.js
                  estados.js  dialogo.js  vendor/chart.umd.min.js
```

**Documentación de diseño ya producida** (12 documentos + capturas a 320 / 768 / 1440 px):

| Documento | Cubre lo que pediste |
|---|---|
| `docs/adr/2026-08-31-direccion-visual-panel.md` | La dirección visual, decidida y escrita |
| `docs/diseno/2026-08-31-auditoria-y-adn-marca.md` | ADN de marca NIOVAL |
| `docs/diseno/2026-09-01-estados-de-carga-t45.md` + 7 capturas | ← **«pantallas de carga»** |
| `docs/diseno/2026-09-01-sistema-de-movimiento-t46.md` | ← **«movimientos»** |
| `docs/diseno/2026-09-01-rediseno-tablero-t47.md` + 9 capturas | ← **«display»** (tablero) |
| `docs/diseno/2026-09-02-rediseno-formulario-t48.md` | ← «display» (formulario) |
| `docs/diseno/2026-09-02-rediseno-importador-t49.md` + 9 capturas | ← «display» (importador) |
| `docs/diseno/2026-09-03-accesibilidad-responsive-t410.md` | Accesibilidad y responsive |

**Las tres cosas que pediste —movimientos, display y pantallas de carga— tienen documento y
capturas.** Lo que **no** tienen es (a) tu visto bueno y (b) presencia en producción.

### 0.2 La brecha real contra lo que se pidió

| Lo pedido | Estado | Qué falta |
|---|---|---|
| «rediseño profesional» de las 3 superficies | ✅ Construido, 12/12 tareas | **Tu aprobación** (T4.2) |
| «agrega movimientos» | ✅ Sistema de movimiento documentado | Verificar que respeta `prefers-reduced-motion` y que anima solo propiedades de compositor (T4.6) |
| «display» | ✅ 3 superficies rediseñadas con capturas | Revisión contra la política anti-plantilla (T4.2) |
| «pantallas de carga» | ✅ Esqueletos y 6 estados | **Ojo:** que sean bonitas no es que sean **ciertas** — eso lo arregla el **Plan 3** |
| Que el operador lo vea | ❌ **PR abierto desde hace 15 días** | **T4.4, T4.5, T4.7** |
| PR #44 no se queda varado | ❌ **5 conflictos** contra #43 | **T4.6** |

### 0.3 El nudo que este plan tiene que desatar

Tres PR abiertos sobre el mismo archivo, con dependencias cruzadas:

```
   main (82995c3)
     │
     ├── PR #42  relevancia ciudades       ──┐ apilado
     │                                       │
     ├── PR #43  rediseño (saca 3,240 líneas de app.py)
     │                                       │
     └── PR #44  endurecimiento (mete 535 líneas en app.py)  ✗ 5 conflictos con #43
```

`SUPUESTO: PR #44 (endurecimiento: rate limiting, escape de fórmulas, zona horaria,
healthcheck, cierre limpio ante SIGTERM) se conserva y se rebasa sobre el rediseño — no se
descarta. Son cinco mejoras de seguridad y operación ya construidas y revisadas.
— afecta Plan 4, Tarea T4.6. Ver decisión D4 del índice.`

`SUPUESTO: el orden de aterrizaje es #42 → #43 → #44, porque #43 está apilado sobre #42 y
rebasar #44 sobre el HTML ya extraído es más barato que lo contrario (sus 535 líneas viven en
rutas de Flask, no en el HTML que #43 mueve). — afecta Plan 4, Tareas T4.4 y T4.6.`

---

## 1. OBJETIVO, ALCANCE Y CRITERIOS DE ÉXITO

### 1.1 Objetivo

Que las tres superficies de PanelNioval se vean y se sientan como un producto profesional
—con movimiento intencionado, jerarquía real y estados de carga que acompañan— **en el panel
que el operador abre todos los días**, y que los tres PR abiertos queden cerrados sin perder
trabajo.

### 1.2 Alcance

**Dentro:** auditoría de calidad del rediseño construido, cierre de la brecha detectada,
aterrizaje de #43, rebase y aterrizaje de #44, despliegue y verificación en vivo
(accesibilidad, responsive, rendimiento).

**Fuera:** que los contadores digan la verdad (Plan 3 — este plan arregla cómo se ven, no qué
afirman), el modelo de ciudades (Plan 1) y el gasto de Places (Plan 2).

### 1.3 Criterios de éxito medibles

| # | Criterio | Cómo se mide | Gate |
|---|---|---|---|
| **CE1** | El rediseño **no parece plantilla** | Checklist anti-plantilla de las reglas del entorno: ≥4 de las 10 cualidades requeridas, verificadas superficie por superficie | T4.2 |
| **CE2** | El owner aprueba la dirección visual | Revisión de las capturas del antes/después de las 3 superficies | T4.2 · **gate del owner** |
| **CE3** | El movimiento es accesible y barato | 100 % de las animaciones sobre `transform`/`opacity`/`clip-path`; `prefers-reduced-motion` respetado en todas | T4.3 |
| **CE4** | Accesibilidad AA | Contraste ≥ 4.5:1 en texto normal; navegación completa por teclado; foco visible en los 3 flujos | T4.7 |
| **CE5** | Responsive sin desbordes | 320 / 375 / 768 / 1024 / 1440 / 1920 px sin scroll horizontal en las 3 superficies | T4.7 |
| **CE6** | Rendimiento no empeora | LCP y CLS medidos antes/después; **sin regresión** | T4.7 |
| **CE7** | **Los tres PR cerrados sin perder trabajo** | #42, #43 y #44 mergeados; los 5 conflictos resueltos con test que lo demuestra | T4.6 |
| **CE8** | Está en producción | Smoke verde + las 3 superficies servidas con el diseño nuevo | T4.7 |
| **CE9** | Sin regresiones | `pytest tests/` ≥ 626 passed tras cada tarea | todas |

---

## 2. TAREAS

---

### T4.0 — Tarea Cero: rama, respaldo y evidencia del «antes»

**Depende de:** cierre del Plan 1 (PR #42 ya en `main`).

**Contexto autocontenido.** PanelNioval sirve tres superficies desde un Flask de una pieza. El
PR #43 las rediseña y de paso saca el HTML y el JS de `app.py` a `templates/` y `static/`. Un
rediseño sin evidencia del «antes» es imposible de evaluar después: las capturas son el
instrumento de medición, no decoración.

**Qué hacer.**
1. Rama `feat/rediseno-aterrizaje` desde `main` actualizado (ya con el Plan 1).
2. Baseline: `python -m pytest tests/`. Anotar el número exacto.
3. **Capturas del «antes»** de las 3 superficies a 320, 768 y 1440 px, desde el panel en
   producción, a `docs/diseno/antes-2026-09-15/`.
4. Medir LCP y CLS del «antes» (línea base de CE6).
5. Reverificar `gh pr view 43` y `gh pr view 44`: estado, mergeable, CI.
6. Respaldo a `docs/auditoria/respaldos/2026-09-15-plan4/`.

**Salida.** `docs/auditoria/2026-09-15-estado-de-partida-plan4.md` + capturas + métricas.

**Criterio de cierre.** 9 capturas del «antes» y las métricas base **existen antes** de tocar
nada. Sin ellas, CE6 no se puede evaluar y el plan queda sin instrumento.

---

### T4.1 — Auditoría del rediseño construido: ¿cumple lo que pediste?

**Depende de:** T4.0.

**Contexto autocontenido.** El PR #43 cerró sus 12 tareas y produjo 12 documentos de diseño
con capturas. Nadie externo al ejecutor los ha revisado. Tu encargo nombra tres cosas —
**movimientos, display, pantallas de carga** — y esta tarea comprueba, una por una, que
existen de verdad y no solo en el título de un documento.

**Qué hacer.**
1. Leer los 12 documentos de `docs/diseno/` y el ADR de dirección visual **de la rama del PR #43**.
2. Construir una **matriz de cobertura**: por cada superficie (tablero, formulario, importador)
   × cada eje (movimiento, display, estados de carga) × cada breakpoint → ¿hay captura y
   decisión escrita? Marcar huecos.
3. Contrastar contra la **política anti-plantilla** de las reglas del entorno: ¿el resultado
   demuestra ≥4 de las 10 cualidades requeridas (jerarquía por contraste de escala, ritmo
   intencionado, profundidad, tipografía con carácter, color semántico, estados de
   interacción diseñados, composición editorial, textura, movimiento que aclara, datos como
   parte del sistema)? Nombrar **cuáles**, con la captura que lo prueba.
4. Revisar específicamente los defectos que las reglas prohíben: rejilla de tarjetas uniforme
   sin jerarquía, radio y sombra idénticos en todo, gris sobre blanco con un acento decorativo.

**Salida.** `docs/diseno/2026-09-15-auditoria-rediseno.md` con la matriz y la lista de huecos.

**Criterio de cierre.** Matriz completa. Cada hueco con severidad (bloqueante / mejora) y la
superficie donde está.

---

### T4.2 — Gate del owner: aprobar la dirección visual antes de invertir más

**Depende de:** T4.1.

**Contexto autocontenido.** Rediseñar sin aprobación es la forma más cara de equivocarse: 28k
líneas ya están escritas y todavía nadie del negocio ha dicho si le gusta. Esta tarea es un
gate humano deliberado, colocado **antes** de gastar esfuerzo en pulir.

**Qué hacer.**
1. Preparar una comparación **antes/después** de las 3 superficies (capturas de T4.0 contra las
   del PR #43), en un solo documento navegable.
2. Presentarla al owner con tres preguntas cerradas:
   (a) ¿la dirección visual se aprueba tal cual, con ajustes menores, o se replantea?
   (b) ¿hay alguna superficie que empeoró respecto a la actual?
   (c) ¿los estados de carga transmiten lo que debe transmitir?
3. Registrar la respuesta literal. **Si la respuesta es «replantear»**, el plan se detiene aquí
   y se rediseña el alcance: no se sigue puliendo algo rechazado.

**Salida.** `docs/diseno/2026-09-15-gate-owner-direccion-visual.md`.

**Criterio de cierre.** **CE1 y CE2.** Respuesta del owner registrada. Sin ella, T4.3 no
arranca.

---

### T4.3 — Cerrar la brecha: movimiento accesible y estados de carga

**Depende de:** T4.2 (aprobado o aprobado con ajustes).

**Contexto autocontenido.** El sistema de movimiento existe (`docs/diseno/2026-09-01-sistema-de-movimiento-t46.md`).
Las reglas del entorno son estrictas y no negociables: se anima **solo** `transform`, `opacity`,
`clip-path` y `filter` con moderación; **nunca** `width`, `height`, `top`, `left`, `margin`,
`padding` ni `font-size`, porque sacan el trabajo del compositor y provocan reflow. Y
`prefers-reduced-motion` no es un extra: es accesibilidad.

**Qué hacer.**
1. Barrer `static/css/*.css` buscando `transition` y `@keyframes` sobre propiedades
   **prohibidas**. Cada hallazgo se corrige o se justifica por escrito.
2. Verificar que existe un bloque `@media (prefers-reduced-motion: reduce)` que **de verdad**
   desactiva el movimiento, y probarlo activando la preferencia en el navegador.
3. Aplicar los ajustes menores que salieron de T4.2 y los huecos bloqueantes de T4.1.
4. Revisar los estados de carga: que los esqueletos tengan la **forma** del contenido que
   sustituyen (un esqueleto genérico es peor que nada porque provoca CLS al llegar el dato).

**Salida.** CSS/JS corregidos + `docs/diseno/2026-09-15-cierre-brecha.md`.

**Criterio de cierre.** **CE3 verde**, con la lista de propiedades animadas como evidencia.

---

### T4.4 — Aterrizar el PR #43

**Depende de:** T4.3.

**Contexto autocontenido.** PR #43 está apilado sobre #42, que el Plan 1 ya mergeó. Tras ese
merge, la base de #43 quedó en `main` y el PR debería seguir `MERGEABLE`; si no, hay que
rebasarlo. Es el PR más grande de la tanda (+28,582) y el que más superficie cambia.

**Qué hacer.**
1. Empujar el trabajo de T4.3 a la rama del PR #43 (**preferido**: un solo PR, no descuelga nada).
2. Verificar CI verde.
3. Gates sobre el diff **nuevo** (el de agosto ya fue revisado): `typescript-reviewer` para el
   JS extraído, `code-reviewer`, y `security-reviewer` — **obligatorio**: extraer HTML a
   plantillas cambia cómo se escapan los valores, y el proyecto ya tuvo un XSS almacenado en
   el nombre de ciudad (B9).
4. Mergear con `gh pr merge 43 --squash` solo si: suite verde, CI verde, 0 CRITICAL/HIGH.
5. Correr la suite sobre `main` y confirmar ≥ baseline.

**Criterio de cierre.** #43 mergeado, SHA anotado, `pytest` sobre `main` ≥ 626.

---

### T4.5 — Verificar que la extracción no rompió nada funcional

**Depende de:** T4.4.

**Contexto autocontenido.** Sacar 3,240 líneas de HTML y JS de `app.py` a archivos separados es
un refactor **enorme** con superficie de error baja pero consecuencia alta: si un `id`, una
ruta de `fetch` o un escape se perdió en el camino, el panel se ve bien y no funciona. Los
tests cubren mucho, pero el panel es una aplicación de navegador.

**Qué hacer.**
1. Recorrer las 3 superficies en el navegador y ejercitar **cada botón y cada flujo**: cargar
   el tablero, filtrar, ordenar la tabla, abrir el formulario, cerrar una llamada, abrir el
   importador, cargar ciudades, filtrar por región, lanzar y detener una corrida.
2. **`click-path-audit`**: trazar cada botón por su secuencia completa de cambios de estado.
   El riesgo típico de una extracción es el manejador que quedó apuntando a un `id` que cambió.
3. Verificar que los escapes siguen puestos: probar una ciudad con comilla (`O'Brien`) y otra
   con `<img onerror=...>`. Este agujero ya existió (B9); una extracción es el momento clásico
   para reabrirlo.
4. Consola del navegador **sin errores** en ninguna de las 3 superficies.

**Salida.** `docs/investigacion/2026-09-15-verificacion-extraccion.md`.

**Criterio de cierre.** Todos los flujos ejercitados, consola limpia, los dos casos de escape
probados y bloqueados.

---

### T4.6 — Rebasar el PR #44 y resolver los 5 conflictos

**Depende de:** T4.4.

**Contexto autocontenido.** PR #44 (*endurecimiento del panel*) trae cinco mejoras de seguridad
y operación ya construidas y revisadas: **rate limiting** en todas las rutas, **escape de
fórmulas** en todas las escrituras a Sheets, **zona horaria explícita** en las dos capas,
**healthcheck** del contenedor y **cierre ordenado** del hilo del importador ante `SIGTERM`.
Sus 535 líneas nuevas viven en rutas de Flask y en el arranque de la app; el PR #43 sacó el
HTML de en medio. De ahí los **5 conflictos** — y de ahí que rebasar #44 **después** sea el
camino barato.

**Qué hacer.**
1. `git rebase main` sobre `fix/endurecimiento-panel` (con `main` ya con #42 y #43).
2. Resolver los 5 conflictos **uno por uno**, y por cada uno dejar escrito qué se conservó de
   cada lado. Un conflicto resuelto «a ojo» en código de seguridad es un agujero.
3. **Riesgo específico:** el escape de fórmulas del PR #44 se aplicó a todas las escrituras
   cuando el HTML estaba en `app.py`. Verificar que **sigue cubriendo** las escrituras después
   de la extracción, con test.
4. Correr `tools/verificar_endurecimiento.py` (existe en el repo) y las suites
   `test_endurecimiento_*.py` (son 4).
5. Gates completos. Mergear.

**Salida.** PR #44 mergeado + `docs/investigacion/2026-09-15-resolucion-conflictos-44.md` con
los 5 conflictos y su resolución.

**Criterio de cierre.** **CE7.** Las 4 suites de endurecimiento en verde y los 5 conflictos
documentados.

---

### T4.7 — Desplegar y verificar en vivo: accesibilidad, responsive y rendimiento

**Depende de:** T4.5 y T4.6.

**Contexto autocontenido.** Ya existe `docs/diseno/2026-09-03-accesibilidad-responsive-t410.md`
del trabajo de agosto, pero se hizo **en local**. Lo que llega al operador es lo que sirve el
VPS, y es ahí donde se mide.

**Qué hacer.**
1. Desplegar y correr `python tools/smoke_panel.py https://panelnioval.duckdns.org --token <valor>` → `Todo OK ✅`.
2. **CE4 — Accesibilidad:** chequeo automático en las 3 superficies; recorrido completo por
   teclado (tab, enter, escape) de los 3 flujos principales; foco visible en todo control;
   contraste verificado con medición, no a ojo.
3. **CE5 — Responsive:** 320, 375, 768, 1024, 1440 y 1920 px en las 3 superficies. **Sin scroll
   horizontal.** Captura de cada combinación.
4. **CE6 — Rendimiento:** LCP y CLS contra la línea base de T4.0. Atención especial al CLS:
   los esqueletos de carga son la causa clásica de salto de layout cuando no tienen la forma
   del contenido real. Verificar también que `chart.umd.min.js` está **auto-hospedado** (lo
   está, `static/js/vendor/`) y no se pide a un CDN.
5. Capturas del «después» a `docs/diseno/despues-2026-09-15/`.

**Salida.** `docs/investigacion/2026-09-15-verificacion-produccion-plan4.md` + capturas.

**Criterio de cierre.** **CE4, CE5, CE6 y CE8 verdes**, con medición. Si el despliegue falla,
la tarea queda **BLOQUEADA**.

---

### T4.8 — Cierre: sistema de diseño documentado, PROGRESO y relevo

**Depende de:** T4.7.

**Qué hacer.**
1. Documentar el sistema de diseño de forma que el siguiente que toque el panel **no lo
   reinvente**: dónde viven los tokens, cómo se añade un componente, qué duraciones y curvas
   usa el movimiento, cómo se hace un estado de carga nuevo.
2. `CLAUDE.md`: la estructura ya no es un monolito — `templates/` y `static/` son parte del
   mapa del proyecto. `RUNBOOK.md`: cómo tocar el panel sin romper el diseño.
3. Cerrar PROGRESO, actualizar el índice a **2/4**, sobrescribir `RELEVO-actual.md` →
   **Plan 3, T3.0**.

**Criterio de cierre.** Índice en 2/4 y relevo apuntando al Plan 3.

---

## 3. TABLA DE ASIGNACIÓN DE HERRAMIENTAS, POR ETAPA

| Etapa | Tarea | Herramienta asignada | Tipo | Fuente | Por qué es la mejor |
|---|---|---|---|---|---|
| **A** | T4.0 | `claude-mem:mem-search` | skill | claude-mem | Recupera las decisiones visuales previas y el ADN de marca de NIOVAL de sesiones pasadas, antes de juzgar el rediseño. |
| **A** | T4.1 | `Explore` | agente | built-in | Recorrer 12 documentos de diseño y 6 archivos CSS sin cargarlos todos al contexto. |
| **A** | T4.1 | `ux-researcher` | agente | catalogo-agentes | La matriz de cobertura es una evaluación de experiencia por flujo, no una opinión estética. |
| **A** | T4.0 | `web-perf` | skill | skills-local | Mide LCP/CLS del «antes» con Chrome DevTools: sin esta línea base, CE6 no es evaluable. |
| **B** | T4.1 | `frontend-design-direction` | skill | community | Fija el criterio con el que se juzga el rediseño **antes** de mirarlo, para no racionalizar lo ya construido. |
| **B** | T4.1 | `design-system` | skill | ECC | Audita consistencia visual y revisa PR que tocan estilos: exactamente la matriz de T4.1. |
| **B** | T4.2 | `council` | skill | community | Si el owner responde «con ajustes», hay que decidir cuáles entran: tradeoff real entre esfuerzo y ganancia. |
| **B** | T4.1, T4.3 | `ui-ux-pro-max` | skill | skills-local | Catálogo de estilos, paletas y pares tipográficos para nombrar los huecos con vocabulario concreto, no con «se ve genérico». |
| **C** | T4.3 | `impeccable` | skill | community | **La herramienta central de esta tarea:** cubre pulido, jerarquía visual, carga cognitiva, motion, estados vacíos y de error. Está hecha para «mejorar una interfaz existente», que es exactamente el caso. |
| **C** | T4.3 | `make-interfaces-feel-better` | skill | community | Los detalles de ingeniería de diseño —espaciado, bordes, sombras, áreas de toque— que separan «funciona» de «se siente bien». |
| **C** | T4.3 | `motion-ui` | skill | ECC | Sistema de movimiento con tokens y duraciones, en vez de transiciones sueltas por componente. |
| **C** | T4.3 | `motion-foundations` | skill | skills-local | **Reglas duras de CE3:** qué propiedades se animan, adaptación por dispositivo y `prefers-reduced-motion`. |
| **C** | T4.3 | `frontend-patterns` | skill | ECC | Patrones de estado de UI para los esqueletos de carga. |
| **C** | T4.6 | `resolving-merge-conflicts` | skill | skills-local | Los 5 conflictos de #44 son un merge en curso sobre código de seguridad: procedimiento, no improvisación. |
| **C** | T4.4, T4.6 | `git-workflow` | skill | ECC | Rebase, apilado de PR y orden de aterrizaje sin perder trabajo. |
| **D** | T4.3, T4.4 | `typescript-reviewer` | agente | catalogo-agentes | **Reviewer del stack para el front.** Cubre JavaScript; los 6 archivos de `static/js/` son JS puro. Se suma a `code-reviewer`. |
| **D** | T4.4, T4.6 | `python-reviewer` | agente | catalogo-agentes | **Reviewer del stack para el backend:** las rutas de Flask que quedan en `app.py` y las 535 líneas de #44. |
| **D** | T4.4, T4.5, T4.6 | `code-reviewer` | agente | catalogo-agentes | Gate general obligatorio. |
| **D** | T4.4, T4.6 | `security-reviewer` | agente | catalogo-agentes | **Obligatorio.** Extraer HTML a plantillas cambia el escape; el proyecto ya tuvo XSS almacenado en el nombre de ciudad (B9). Y #44 **es** el PR de seguridad. |
| **D** | T4.3 | `review-animations` | skill | skills-local | Revisa el movimiento contra un listón de artesanía alto; por defecto marca en vez de aprobar. Cierra CE3 con criterio, no con buena voluntad. |
| **D** | T4.7 | `a11y-architect` | agente | catalogo-agentes | WCAG 2.2 AA en el diseño de componentes: ARIA semántico y orden de foco. |
| **D** | T4.7 | `accessibility-tester` | agente | catalogo-agentes | Verificación de soporte de tecnología asistida — se suma al chequeo automático, que solo atrapa un tercio de los problemas. |
| **D** | T4.7 | `frontend-a11y` | skill | community | Patrones concretos: etiquetado de formularios, navegación por teclado y gestión de foco. El `/formulario` es el flujo con más entradas. |
| **D** | T4.7 | `web-design-guidelines` | skill | skills-local | Revisión del código de UI contra las guías de interfaz web. |
| **D** | T4.5 | `click-path-audit` | skill | community | Una extracción de 3,240 líneas rompe manejadores en silencio. Esta skill traza cada botón por su secuencia de estados. |
| **D** | T4.5, T4.7 | `webapp-testing` | skill | skills-local | Recorrido en navegador con capturas de los 3 flujos y los 6 breakpoints. |
| **D** | T4.7 | `browser-qa` | skill | ECC | Verificación visual e interactiva **después de desplegar**, que es donde se mide CE8. |
| **D** | T4.7 | `canary-watch` | skill | ECC | Verifica el URL desplegado: consola sin errores, assets estáticos, regresiones de rendimiento. |
| **D** | T4.7 | `web-perf` | skill | skills-local | CE6: LCP y CLS del «después» contra la línea base de T4.0. |
| **D** | T4.5 | `silent-failure-hunter` | agente | catalogo-agentes | El `catch` de `cargarCiudades()` cae a la lista estática sin avisar: tras la extracción, un fallo ahí se vería como «funciona». |
| **D** | T4.7 | `superpowers:verification-before-completion` | skill | superpowers | CE4–CE6 exigen medición. Prohíbe declararlos verdes sin la salida. |
| **E** | T4.4, T4.6 | `github-ops` | skill | ECC | Merge de dos PR grandes con checks verificados. |
| **E** | T4.6 | `claude-mem:babysit` **[OPCIONAL]** | skill | claude-mem | **Condición de uso:** si el CI del #44 rebasado tarda o falla de forma intermitente. |
| **E** | T4.8 | `doc-updater` | agente | catalogo-agentes | `CLAUDE.md` y `RUNBOOK.md`: la estructura ya no es un monolito. |
| **E** | T4.8 | `technical-writer` | agente | catalogo-agentes | El documento del sistema de diseño lo va a leer alguien que no estuvo aquí: tiene que sostenerse solo. |
| **E** | T4.8 | `superpowers:finishing-a-development-branch` | skill | superpowers | Cierre ordenado de tres ramas a la vez. |
| **E** | T4.8 | `handoff` | skill | skills-local | Relevo hacia el Plan 3. |
| **Transversal** | todo | `blueprint` | skill | community | Formato de tareas autocontenidas. |
| **Transversal** | T4.1 | **`ads-dna`** | skill | claude-ads | **Uso literal, no forzado.** Extrae el ADN de marca de un sitio —paleta, tipografía, tono, estilo de imagen— y lo deja en `brand-profile.json`. El repo ya tiene `docs/diseno/...auditoria-y-adn-marca.md`; esta skill lo formaliza en un artefacto que las herramientas de diseño consumen, en vez de en prosa. |
| **Transversal** | T4.7 | `dataviz` **[OPCIONAL]** | skill | anthropic/built-in | **Condición de uso:** solo si T4.1 marca las gráficas del tablero (Chart.js) como hueco. Trata la visualización como parte del sistema de diseño, que es la cualidad nº 10 de la política anti-plantilla. |

**Fuentes usadas en el Plan 4: 6 de 6 canónicas** + built-in.

---

## 4. GATES DE VERIFICACIÓN POR TAREA

| Tarea | Tests | Reviewers | Baseline | Gate extra |
|---|---|---|---|---|
| T4.0 | — | — | **≥ 626** | 9 capturas del «antes» + LCP/CLS base |
| T4.1 | — | `ux-researcher` + `design-system` | — | **CE1:** matriz completa, ≥4 cualidades nombradas con captura |
| T4.2 | — | `council` si hay ajustes | — | **CE2 = gate del owner.** Sin respuesta, T4.3 no arranca |
| T4.3 | — | `typescript-reviewer` + `code-reviewer` + `review-animations` | ≥ 626 | **CE3** con la lista de propiedades animadas |
| T4.4 | CI verde | `typescript-reviewer` + `python-reviewer` + `code-reviewer` + `security-reviewer` | ≥ 626 sobre `main` | 0 CRITICAL/HIGH |
| T4.5 | — | `click-path-audit` + `silent-failure-hunter` | ≥ 626 | Consola limpia · 2 casos de escape bloqueados |
| T4.6 | 4 suites `test_endurecimiento_*` | `python-reviewer` + `code-reviewer` + `security-reviewer` | ≥ 626 sobre `main` | **CE7:** 5 conflictos documentados uno por uno |
| T4.7 | — | `a11y-architect` + `accessibility-tester` | — | **CE4, CE5, CE6, CE8** con medición |
| T4.8 | — | `doc-updater` + `technical-writer` | ≥ 626 | Índice 2/4 · relevo → Plan 3 |

---

## 5. RIESGOS Y PLAN DE ROLLBACK

| # | Riesgo | Prob. | Impacto | Mitigación | Rollback |
|---|---|---|---|---|---|
| R1 | El owner **rechaza** la dirección visual con 28k líneas ya escritas | Media | **Crítico** — se tira el trabajo de 12 tareas | T4.2 es un gate **antes** de pulir; y las capturas del PR ya existen, así que la decisión se toma sobre algo visible, no sobre una promesa | El `main` actual sigue sirviendo; el PR queda abierto sin mergear |
| R2 | La extracción de 3,240 líneas rompe un manejador **en silencio** | **Alta** — es el modo de fallo típico de un refactor así | Alto — el panel se ve bien y no funciona | T4.5 es tarea propia con `click-path-audit` y recorrido manual completo | `git revert` del merge de #43 |
| R3 | Se pierde el escape de fórmulas o el anti-XSS al mover el HTML | Media | **Crítico** — el proyecto ya tuvo XSS almacenado (B9) | `security-reviewer` obligatorio en T4.4 y T4.6 + los dos casos de prueba explícitos (`O'Brien` y `<img onerror>`) en T4.5 | `git revert`; el escape vive en `main` hoy |
| R4 | Los 5 conflictos de #44 se resuelven mal y se pierde una mejora de seguridad | Media | Alto — se cree que está y no está | T4.6 obliga a documentar los 5 uno por uno + las 4 suites de endurecimiento + `verificar_endurecimiento.py` | Rebase se rehace desde cero: la rama original no se borra |
| R5 | Los esqueletos de carga **empeoran el CLS** | Media | Medio | T4.3 exige que el esqueleto tenga la forma del contenido; T4.7 lo mide contra la línea base | Se quitan los esqueletos: es CSS, no arquitectura |
| R6 | El movimiento marea o ignora `prefers-reduced-motion` | Media | Alto — accesibilidad | CE3 con barrido de propiedades y prueba activando la preferencia | El bloque de `reduced-motion` desactiva todo: una regla CSS |
| R7 | #43 deja de ser `MERGEABLE` tras el merge del Plan 1 | Media | Medio | T4.0 lo reverifica; T4.4 contempla el rebase | La rama local existe; se rebasa sobre el nuevo `main` |
| R8 | Se declara CE8 sin desplegar, como pasó con los tres gates del owner del Plan 3 | **Alta** | Crítico — el operador no ve nada | T4.7 obliga a **BLOQUEADA** si el smoke no pasa | El PR no cierra hasta que el smoke esté verde |

**Rollback del plan completo:** `git revert` de los merges de #43 y #44, en ese orden inverso.
El VPS vuelve al panel anterior en el siguiente deploy. Las tres ramas (`feat/rediseno-panel`,
`fix/endurecimiento-panel`) **no se borran**. Las capturas del «antes» de T4.0 son la
referencia de qué se restaura.

---

## 6. PROGRESO

| # | Tarea | Estado | Evidencia (commit/test/PR) | Fecha |
|---|---|---|---|---|
| T4.0 | Tarea Cero: rama, respaldo y evidencia del «antes» | **HECHO** | commit `2ed61e7` · `docs/auditoria/2026-09-15-estado-de-partida-plan4.md` · rama `feat/rediseno-aterrizaje` desde `main` `a97b494` · baseline **525 passed, 1 skipped** (el «≥626» es del PR #44, sin mergear) · respaldo antes de tocar nada · **9 capturas** de producción en `docs/diseno/antes-2026-09-15/` · ⚠️ **las del formulario traían nombre y teléfono de un cliente real**: rehechas anonimizando en el ORIGEN (interceptando el endpoint), la PII nunca llegó a disco · **línea base CE6**: dashboard 1440 **CLS 0.1924** e importador 320 **CLS 0.1073**, los dos sobre el umbral; LCP máximo 548 ms, con margen · ⚠️ **la primera medición dio todo 0.0 por un observador mal registrado** (`add_init_script` ejecuta el string: una flecha suelta no se llama) — corregido y con guarda contra el cero · `.gitignore` dejaba `metricas-base.json` fuera del repo en silencio: excepción explícita · PR #43 y #44 **CONFLICTING** (riesgo R7 materializado), su CI verde es del 4-6 sep y no vale para hoy | 2026-09-16 |
| T4.1 | Auditoría del rediseño construido (matriz de cobertura) | **HECHO** | commit `87fdbea` + correcciones · `docs/diseno/2026-09-15-auditoria-rediseno.md` · **criterio fijado y commiteado ANTES de mirar** (`4212917`) · matriz 3 superficies × 3 ejes × 5 anchos · **CE1 cumplido: 5 cualidades anti-plantilla probadas con evidencia** (mínimo 4); 3 renunciadas a propósito por tensión con el CLS · **validación cruzada del CLS**: el PR midió 0.1941 y T4.0 midió 0.1924 con otra herramienta y otro entorno (0.9 % de diferencia) · **5 BLOQUEANTES**: B1 capturas del «después» a cero, B2 la pantalla principal no usa el sistema (espaciado 9/86 y 0/31 contra 29/29 y 50/52), B3 tarjetas dentro de tarjetas, B4 el CLS de interacción sin medir, **B5 el buscador no normaliza acentos → 319 de 1,004 ciudades inalcanzables** · 8 mejoras · gates `ux-researcher` + `design-system`: el primero **corrigió el veredicto** y destapó B5 | 2026-09-16 |
| T4.2 | Gate del owner: aprobar la dirección visual | **HECHO** | `docs/diseno/2026-09-15-gate-owner-direccion-visual.md` · **(a) «Tal cual» · (b) «Ninguna» empeoró · (c) «Sí, transmiten bien»** · **CE1 y CE2 cerrados** · sin ajustes pedidos por el negocio, así que T4.3 arranca con el alcance ya conocido: los 4 bloqueantes de T4.1 · **el supuesto «Aprobados es lo que el owner mira primero» queda confirmado** (se presentó como el momento de cambiarlo y no se cambió) | 2026-09-16 |
| T4.3 | Cerrar la brecha: movimiento accesible y estados de carga | **HECHO (parcial, declarado)** | commit `066ed9d` · rama **`feat/plan4-cierre-brecha`** (desde `feat/rediseno-panel`, porque los CSS/JS sólo existen ahí) · `docs/diseno/2026-09-15-cierre-brecha.md` · 🆕 **la rama del PR #43 tenía la suite EN ROJO** y nadie lo veía: el sha256 del Chart.js fallaba **sólo en Windows** porque `.gitattributes` no exceptuaba `.js` (blob LF → checkout CRLF, 20 bytes). Arreglado con `static/js/vendor/** binary` · **CE3 VERDE** con la lista: los 4 `@keyframes` animan sólo `transform` y `opacity`; cero prohibidas, cero `transition: all` · **B5 corregido** (`sinAcentos()` en las dos puntas; TDD con 3 RED; verificado con Node contra el catálogo real: 12/12 y control negativo en 0) · **B3 corregido** con control negativo · **B4 MEDIDO Y RETIRADO**: CLS de interacción **0.0000**, no reproduce porque los 4 bloques están debajo del buscador · ⏳ **B2 abierto y declarado sin hacer** (~160 sustituciones no mecánicas; plan de 4 pasos escrito) · baseline **907 passed, 2 skipped** | 2026-09-16 |
| T4.4 | Aterrizar el PR #43 | **HECHO** | **PR #43 MERGEADO** el 2026-09-16 · `main` `a97b494` → **`752fe2a`** · ⚠️ **NO se usó `--squash` pese a que el plan lo pedía**: la rama trae **29 commits** cuyos mensajes son la documentación de cómo se encontró cada defecto; se comprobó antes que el método es indiferente para el #44 (conflictúa en los mismos 4 archivos con squash y con merge) · **B2 cerrado antes del merge** por decisión del owner: 45 sustituciones seguras + la tipografía del ADR, **15/15 capturas idénticas píxel a píxel** · conflicto de `CLAUDE.md` resuelto **línea por línea**, conservando la corrección del auto-deploy del Plan 1 · gates `typescript-reviewer` + `security-reviewer` sin CRITICAL ni HIGH, 4 MEDIUM aplicados · CI verde · `pytest` sobre `main` → **955 passed, 2 skipped** · `app.py` **6,368 → 3,182 líneas** · ⚠️ el **PR #44 sigue `CONFLICTING`** en los mismos 4 archivos (T4.6) | 2026-09-16 |
| T4.5 | Verificar que la extracción no rompió nada funcional | PENDIENTE | | |
| T4.6 | Rebasar el PR #44 y resolver los 5 conflictos | PENDIENTE | | |
| T4.7 | Desplegar y verificar: a11y, responsive y rendimiento | PENDIENTE | | |
| T4.8 | Cierre: sistema documentado, PROGRESO y relevo | PENDIENTE | | |

**Avance del plan: 0 / 9 tareas (0 %)**

**Supuestos vivos de este plan:**
- `SUPUESTO: PR #44 se conserva y se rebasa, no se descarta. — afecta Plan 4, Tarea T4.6. Ver D4 del índice.`
- `SUPUESTO: el orden de aterrizaje es #42 → #43 → #44. — afecta Plan 4, Tareas T4.4 y T4.6.`
