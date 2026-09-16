# RELEVO ACTUAL — PanelNioval · tanda 2026-09-15

> **Archivo único que se SOBRESCRIBE al cerrar CADA tarea.** Siempre contiene el mensaje
> completo para arrancar una sesión nueva.
>
> **Estado: sesión 2 EN CURSO. Última tarea cerrada: Plan 1 · T1.3.** Umbral de relevo: 1 de 3
> tareas hechas en esta sesión, no toca cerrar todavía.

---

Continúas el proyecto **PanelNioval**. **Sesión 2.** NO empieces de cero: el diseño ya está
hecho, **dos de los cuatro planes ya están construidos en PR abiertos**, y van cerradas
T1.0, T1.1, T1.2 y T1.3.

**PROYECTO:** `C:\Users\PC 1\PanelNioval`
**RAMA DE TRABAJO:** `feat/relevancia-nacional-produccion` — estás en ella. Árbol limpio, sin pushear.
**ÚLTIMO COMMIT:** `89f9ca8` — *feat(catalogo): el corte baja a >=10 ferreterias y cierra la brecha del Sureste (Plan 1, T1.3)*
**ÚLTIMO COMMIT DE `main`:** `82995c3` — sin cambios; **nada se ha mergeado todavía.**

---

## ⚠️ LO PRIMERO, PORQUE CAMBIÓ LA BASE DE LA RAMA

**La rama se rebasó sobre `feat/relevancia-ciudades-nacional` (PR #42) en T1.3.** No es un
detalle de higiene: **el generador `tools/generar_catalogo_ciudades.py` NO EXISTÍA** en la rama
—vive en el PR #42, que no está mergeado— y T1.3 no se podía ejecutar sin él. T1.2 lo había
leído vía git, no de disco, y por eso el relevo anterior no lo vio venir.

- Es la **opción 1 del bloque T1.5 del plan**, así que no inventa nada.
- **El rebase NO reescribe los commits del #42**: los 4 commits de esta rama van ENCIMA de
  `499d41b`. **El PR #43 sigue apilado y no se descolgó.** Verificado.
- Respaldo previo: tag `respaldo/pre-rebase-t13-20260915` y rama
  `respaldo/nacional-produccion-pre-t13`, ambos en `f5c81a1`.
- **Consecuencia para T1.5:** la rama ya contiene el #42 entero, así que aterrizarla es
  empujar estos commits a `feat/relevancia-ciudades-nacional` (un fast-forward), no un merge.

---

## LEE PRIMERO, EN ESTE ORDEN (de disco, completo, antes de tocar nada)

1. `C:\Users\PC 1\.claude\BIBLIOTECA-HERRAMIENTAS.md` — 653 herramientas (229 agentes + 424 skills), 6 fuentes.
2. `C:\Users\PC 1\PanelNioval\CLAUDE.md` — reglas del proyecto.
3. `docs/superpowers/plans/2026-09-15-indice-tanda.md` — orden y dependencias. **D4 RESUELTA** (§8); D1, D2, D3 y D5 siguen abiertas y se avanza con la recomendada.
4. `docs/superpowers/plans/2026-09-15-plan1-relevancia-ciudades-nacional-produccion.md` — **bloque INVARIANTES + bloque de T1.4**.
5. `docs/adr/2026-08-28-modelo-relevancia-ciudades.md` — **§9 es nueva (T1.3)**: el corte y por qué.
6. `docs/investigacion/2026-09-15-cobertura-catalogo-ciudades.md` — la medición de la brecha.

---

## INVARIANTES (copiados literales del plan, no resumidos)

- **OBJETIVO DEL PROYECTO:** que el importador de PanelNioval ordene ciudades por relevancia ferretera **nacional**, cueste lo mínimo en Places, cuente la verdad y se vea profesional — **en producción**, no en una rama.
- **DEFINICIÓN DE TERMINADO:** los 4 planes cerrados, sus PRs mergeados a `main`, el VPS sirviendo ese código y `python tools/smoke_panel.py https://panelnioval.duckdns.org --token <valor>` imprimiendo `Todo OK ✅`.
- **RAMA:** una por plan, creada desde `main` actualizado · **NUNCA `main`** (el VPS auto-deploya `main`) · commits convencionales en español.
- **BASELINE (nada avanza si falla):** `cd "C:\Users\PC 1\PanelNioval" && python -m pytest tests/`. ⚠️ **CORREGIDO OTRA VEZ EN T1.3:** tras el rebase el baseline de esta rama es **491 passed, 1 skipped** (era 482 antes de los 9 tests de T1.3; y 388 antes del rebase, que era el de `main` pelado). **SIN `-q`**: `pytest.ini` ya lo trae; el segundo lo convierte en `-qq` y **oculta la línea del resumen**.
- **GATES POR TAREA:** `python-reviewer` + `code-reviewer` [+ `security-reviewer` si toca auth, token, entrada de usuario, Places o Sheets] [+ `silent-failure-hunter` si toca `try/except` o fallbacks] [+ `typescript-reviewer` si toca `static/js/*`].
- **PROHIBIDO:** (1) trabajar en `main`; (2) **borrar** — lo retirado va a `docs/auditoria/respaldos/<fecha>/`; (3) mergear con la suite en rojo o con CRITICAL/HIGH abierto; (4) commitear teléfonos o nombres de clientes — anonimizar a `+52…XXXX`; (5) rebasar, cerrar o reordenar los PR #42/#43/#44 fuera del orden de aterrizaje del índice.
- **DECISIONES YA TOMADAS (no reabrir):** modelo de relevancia = logarítmico × `factor_nioval` (ADR `2026-08-28`); HTML extraído a `templates/`+`static/` (PR #43); estado del importador compartido en disco (ADR `2026-08-27`); Places con `fields` explícitos + caché 30 d (PR #38, mergeado); `/salud` no revela versión ni commit; **corte del catálogo en ≥10** (D4, ADR §9).
- **SECUENCIA:** **Plan 1 → Plan 4 → Plan 3 → Plan 2.**

---

## AVANCE

- **Global: 0 / 4 planes** · **Plan en curso: 1** · Tareas **4 / 8 (50 %)** · Tareas de la tanda: **4 / 34 (11.8 %)**
- **Planes cerrados y mergeados:** ninguno. **Nada ha llegado a producción**; el operador aún no ve ningún cambio.

---

## HECHO EN T1.3 (con evidencia, no narrativa)

| Qué quedó | Evidencia |
|---|---|
| **Rama rebasada sobre el PR #42.** Sin conflictos; el #43 no se descolgó | `git log`: 4 commits sobre `499d41b` · tag `respaldo/pre-rebase-t13-20260915` |
| **TDD real.** El test RED falló con `Sureste: 65.7 % (6287 de 9564 ferreterias)` ANTES de tocar el generador | salida de pytest en la sesión |
| **Umbral 20 → 10** (una línea: `--min-ferreterias`), catálogo regenerado | `tools/generar_catalogo_ciudades.py:512` |
| **606 → 1,004 municipios**, 32/32 entidades, **0 ciudades perdidas** (las 606 viejas siguen todas) | comparación de claves contra el respaldo de T1.2 |
| **Masa ferretera nacional: 86.3 % → 93.7 %.** Sureste **65.7 % → 80.6 %**. Desequilibrio **1.48× → 1.23×** | medición sobre el catálogo nuevo |
| **CE1 verde:** 0 de los 995 municipios con ≥10 quedan fuera | test permanente, no script |
| **CE3 verde:** potencial mínimo **14.1** (Ejutla, 1 ferretería), 2.8× sobre el piso de 5 | test permanente |
| **Condición 1 del consejo:** 0 nombres ambiguos entre las 398 ciudades nuevas, contra 82 homónimos del DENUE | test permanente con fixture |
| **Fixtures medidos del ZIP por camino independiente**, que reprodujo T1.2 exactamente: 638,861 filas · 75,726 estab. · 2,227 municipios | `tests/datos/*.csv` con la procedencia en su cabecera |
| **Las 3 guardas nuevas probadas por mutación** (Juárez sin estado, potencial 3.0, municipio relevante ausente): las tres fallan cuando deben | salida de pytest |
| **Defecto preexistente destapado y corregido:** el DENUE rellena `municipio` con espacios y el relleno viajaba literal a Places (`"Ferreterias en Dzitbalche" + 70 espacios`). `normalizar()` colapsa espacios, por eso ningún test de duplicados lo veía | `tools/generar_catalogo_ciudades.py:240-247` + test |
| **ADR anexado, §9.** 93 líneas añadidas, **0 borradas** | `git diff --numstat` |
| **Gates: los 3 sin CRITICAL ni HIGH.** El MEDIUM (RUNBOOK desincronizado) cerrado en el mismo commit | `python-reviewer`, `code-reviewer`, `security-reviewer` |

**El LOW del `code-reviewer` se atendió, no se archivó:** avisó de que la cobertura agregada
por región puede dar 75 % y tapar un municipio grande excluido, así que subir el corte dejaría
la suite verde mientras CE1 regresa en silencio. De ahí salió el test municipio-por-municipio.

---

## ESTADO DE VERIFICACIÓN AHORA MISMO

- **Baseline:** `python -m pytest tests/` → **491 passed, 1 skipped**, exit 0.
- **Las 4 suites del catálogo:** verdes.
- **Integridad del catálogo:** `python tools/generar_catalogo_ciudades.py --cache "C:/Users/PC 1/.cache/inegi" --verificar` → *«El catalogo en disco coincide con las fuentes»*, exit 0.
- **Árbol:** limpio, 5 commits sobre `origin/feat/relevancia-ciudades-nacional`, **sin pushear**.
- **Gates de T1.3:** cerrados, 0 CRITICAL / 0 HIGH.

---

## SIGUIENTE PASO EXACTO

**Plan 1, Tarea T1.4 — Verificar el orden nacional y el filtro por región, de verdad.**

```
ANCLA · Plan 1 Tarea T1.4 · importador nacional barato veraz profesional · avance 4/8 ·
 gates: python-reviewer + code-reviewer + silent-failure-hunter + CE2 y CE3 verdes · CE4 = gate del owner ·
 baseline: python -m pytest tests/  -> 491 passed, 1 skipped
```

**Qué hacer, en este orden (literal del plan):**

1. **Top-30 nacional** con los indicadores a la vista (ferreterías, mayoreo, construcción,
   población) en tabla legible.
2. Por cada una de las 8 regiones: **su top-10 y su conteo total**.
3. **CE2 programático:** para cada región, las ciudades del JSON == las que la UI lista con
   ese filtro. **Test automatizado, no inspección visual.**
4. **CE3:** `min(potencial_mercado)` sobre el catálogo completo. *(Ya hay test permanente de
   esto desde T1.3: da 14.1. Vale como cumplido; confírmalo, no lo dupliques.)*
5. **Gate del owner (CE4):** presentar el top-30 y preguntar si el orden es defendible.
   ⚠️ **Si el owner señala una ciudad fuera de lugar, NO ajustar el modelo:** se registra el
   caso en el ADR como dato para una revisión futura y se continúa. Cambiar la fórmula por un
   caso suelto es sobreajuste.

**Ojo con esto en T1.4:** `cargarCiudades()` del importador tiene un `catch` que cae a la
lista estática. Un fallo silencioso ahí haría que **CE2 pase en test y falle en vivo** — por eso
el plan asigna `silent-failure-hunter` a esta tarea.

**Salida.** `docs/investigacion/2026-09-15-verificacion-orden-nacional.md` + tests de CE2/CE3.
**Criterio de cierre.** CE2 y CE3 automatizados y verdes; CE4 con la respuesta del owner
anotada (aprobado / aprobado con reservas / bloqueado).

**Herramientas asignadas a T1.4:** `python-testing` (ECC) · `silent-failure-hunter`
(catalogo-agentes) · `superpowers:verification-before-completion` (superpowers) ·
gates `python-reviewer` + `code-reviewer`.

**Dato útil que ya está medido:** el top-10 del catálogo nuevo es idéntico al que reporta el
ADR de agosto (Puebla 90.7, Guadalajara 90.2, León 89.0, Monterrey 88.7…). Bajar el umbral
**no movió la cabeza del ranking**, sólo añadió cola. Eso simplifica el gate del owner.

---

## PENDIENTES Y BLOQUEOS

| Asunto | Qué falta | Qué lo desbloquea |
|---|---|---|
| **PR #42** (Plan 1) | Verificar orden nacional (T1.4), aterrizar (T1.5), desplegar (T1.6) | T1.4 → T1.6 |
| **PR #43** (Plan 4) | Aprobación de la dirección visual + aterrizaje | Plan 4, T4.2 y T4.4 |
| **PR #44** (endurecimiento) | 5 conflictos **contra #43** (contra `main` está MERGEABLE) | Plan 4, T4.6 |
| **⚠️ 1,004 chips sin filtro son PEORES que 606** | Condición 2 del consejo: el catálogo ampliado **sale con la UI del Plan 4**, no antes. El orden 1 → 4 ya lo contempla | Plan 4 |
| **Bug de conteo** | Diagnóstico H1/H2/H3 — **sin hacer** | Plan 3, T3.1 y T3.2 |
| **MEDIUM de seguridad (preexistente)** | Sin tope de ratio de compresión al leer los ZIPs del INEGI. Mitigado: URL fija del INEGI por HTTPS, no input de terceros. **No bloquea** | Anotado; revisarlo si la fuente deja de ser confiable |
| **`claude-mem` caído** | Captura rota desde 2026-09-05 (issue #2188) | **El relevo es la única persistencia.** Acción de entorno |
| **Gasto en pesos de Places** | Sin acceso a Google Cloud billing | Gate del owner — **D5** |
| **Rotar el token de Telegram** | Heredado (~14 copias) | **Acción del owner**, no automatizable |
| **Decisiones D1, D2, D3, D5** | Respuesta del owner | Se avanza con la recomendada. **D4 ya resuelta** |

---

## SUPUESTOS VIVOS

- `SUPUESTO: el trabajo va sobre PanelNioval, no sobre BruceWhatsapp. — afecta los 4 planes.`
- `SUPUESTO: el gate «≥ 626» se reinterpreta como «≥ baseline de la rama base». Hoy, tras el rebase sobre el PR #42, son 491. — afecta los 4 planes. (T1.0, revisado en T1.3)`
- `SUPUESTO: unir la rama con el PR #42 por rebase (opción 1 de T1.5) en vez de esperar a T1.5. Forzado: sin el generador T1.3 no se podía ejecutar. — afecta T1.5.`
- `SUPUESTO: el fixture del universo ferretero se regenera junto con el catálogo si alguien usa un corte del DENUE más nuevo. Hoy ambos salen de DENUE 05_2026. — afecta T1.3 y T1.4.`
- `SUPUESTO: «tokens de la API» = consumo facturable de Google Places. — afecta Plan 2. Ver D2.`
- `SUPUESTO: si la fuga de Details medida en T2.1 es < 10 %, T2.2–T2.4 se saltan. — afecta Plan 2.`
- `SUPUESTO: el síntoma del conteo se observó en producción, no en una rama local. — afecta Plan 3, T3.1.`
- `SUPUESTO: PR #44 se conserva y se rebasa tras #43. — afecta Plan 4, T4.6. Ver D3.`

---

## DECISIONES CERRADAS (NO reabrir)

- **Modelo = logarítmico × `factor_nioval`** — tres candidatos medidos sobre 589 municipios.
- **HTML fuera de `app.py`, en `templates/`+`static/`**.
- **Estado del importador compartido en disco**.
- **Places legacy con `fields` explícitos**; la migración es materia del Plan 2.
- **`/salud` no revela versión ni commit**.
- **D4 → umbral ≥10 ferreterías** (T1.2). **APLICADO en T1.3**, anexado al ADR como §9.
  Revocable por el owner en una línea, pero **no se re-litiga sin dato nuevo**.
- **El 75 % del test de cobertura es NORMATIVO**, elegido tras ver los datos y declarado como
  tal. Se defiende como compromiso de servicio, no como hallazgo estadístico.

---

## TRAMPAS DESCUBIERTAS (lo que costó tiempo y no está en ningún otro documento)

- **🆕 El generador no estaba en esta rama.** `tools/generar_catalogo_ciudades.py`, `datos/ciudades_mx.json` y las suites del catálogo viven en el PR #42. Antes de planear una tarea que toque un archivo, **comprueba que existe en disco**, no que un documento lo cite con número de línea.
- **🆕 La caché del INEGI ya está poblada** en `C:\Users\PC 1\.cache\inegi` con los 4 ZIPs (el de ferreterías con **60,209,960 bytes exactos**). Regenerar **no descarga 117 MB**: tarda ~1 min. Pasa `--cache "C:/Users/PC 1/.cache/inegi"` con barras normales.
- **🆕 `normalizar()` colapsa espacios, y eso ESCONDE bugs.** Un nombre con 70 espacios de relleno pasaba todos los tests de duplicados porque para `normalizar()` era idéntico al limpio. Para mirar lo que de verdad viaja a Places hay que mirar el nombre **crudo**.
- **🆕 Las guardas nuevas hay que probarlas por mutación.** Un test de cobertura contra un fixture puede pasar porque el fixture está vacío o no se cruza con el dato. Planta el defecto y comprueba que falla.
- **El baseline es por rama.** `main` pelado = 388. Con el PR #42 = 482. Con T1.3 = 491. Comprueba siempre contra la rama base.
- **`pytest -q` oculta el resultado.** `pytest.ini` ya trae `addopts = -q`; otro lo vuelve `-qq`. Correr `python -m pytest tests/` a secas.
- **`.gitignore` ignora `*.json` global** con excepción por ruta exacta para `datos/ciudades_mx.json`. Los fixtures nuevos son `.csv`/`.txt` **a propósito**: un `.json` en `tests/datos/` se ignoraría en silencio y reventaría en CI. Verificado con `git check-ignore`.
- **`docs/auditoria/respaldos/` está en `.gitignore`.** Los respaldos viven en disco y no se commitean.
- **`claude-mem` no está disponible** desde el 2026-09-05. No confíes en que la sesión se guarde sola.
- **El heredoc de bash se atraganta con los documentos largos** (acentos, `«»`): escribe a un archivo aparte y concaténalo, o usa la herramienta de escritura. Verifica con `wc -c`.
- **No pases rutas MSYS (`/c/Users/…`) a Python**: es un Python de Windows. Usa `C:/Users/…`.
- **Las URLs de DENUE tienen trampa:** `denue_00_46_csv.zip` responde **HTTP 200 con 0 bytes**. Validar tamaño mínimo, nunca el status code. El generador ya lo hace: **no le quites esa validación**.
- **La caché de Places falsea la medición del ahorro.** Medir ciudad virgen y ciudad trabajada por separado.
- **Los planes 1 y 4 ya están construidos.** Quien no lea esto va a rediseñar ~40,000 líneas que ya existen con CI en verde.

---

## REGLAS QUE SIGUEN VIGENTES

Anclaje al iniciar cada tarea · test de deriva al cerrarla · umbrales de relevo (**1 de 3
tareas gastada en esta sesión**) · dudas acumuladas y presentadas juntas al cerrar cada plan ·
**herramientas de la tabla de asignación (no colapsar a Superpowers: son 14 de 653)** · merge
solo con gates en verde · **nunca trabajar en `main`**.
