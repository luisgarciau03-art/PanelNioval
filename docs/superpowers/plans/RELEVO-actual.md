# RELEVO ACTUAL — PanelNioval · tanda 2026-09-15

> **Archivo único que se SOBRESCRIBE al cerrar CADA tarea.** Siempre contiene el mensaje
> completo para arrancar una sesión nueva.
>
> **Estado: sesión 2 EN CURSO. Última tarea cerrada: Plan 1 · T1.4.** Umbral de relevo: **2 de
> 3** tareas gastadas en esta sesión.

---

Continúas el proyecto **PanelNioval**. **Sesión 2.** NO empieces de cero: el diseño ya está
hecho, **dos de los cuatro planes ya están construidos en PR abiertos**, y van cerradas
T1.0, T1.1, T1.2, T1.3 y T1.4.

**PROYECTO:** `C:\Users\PC 1\PanelNioval`
**RAMA DE TRABAJO:** `feat/relevancia-nacional-produccion` — estás en ella. Árbol limpio, **sin pushear**.
**ÚLTIMO COMMIT:** `e7acf6e` — *fix(importador): el endpoint desempata por clave INEGI, como manda el ADR (Plan 1, T1.4)*
**ÚLTIMO COMMIT DE `main`:** `82995c3` — sin cambios; **nada se ha mergeado todavía.**

---

## ⚠️ DECISIÓN QUE TE ESPERA NADA MÁS EMPEZAR

**T1.5 mergea el PR #42 a `main`, y `main` auto-despliega al VPS.** Es la primera acción
irreversible y de cara al exterior de toda la tanda. Antes de ejecutarla hay una tensión real
que el owner tiene que resolver, y está desarrollada abajo en «LA TENSIÓN DE T1.5». **No la
resuelvas tú por omisión.**

---

## ⚠️ LA BASE DE LA RAMA CAMBIÓ EN T1.3

**La rama se rebasó sobre `feat/relevancia-ciudades-nacional` (PR #42).** No es higiene: el
generador `tools/generar_catalogo_ciudades.py` **no existía** en la rama —vive en el PR #42,
sin mergear— y T1.3 no se podía ejecutar sin él.

- Es la **opción 1 del bloque T1.5 del plan**, no una invención.
- **El rebase NO reescribe los commits del #42**: los de esta rama van ENCIMA de `499d41b`.
  **El PR #43 sigue apilado y no se descolgó.** Verificado con `git merge-base`.
- Respaldo: tag `respaldo/pre-rebase-t13-20260915` y rama `respaldo/nacional-produccion-pre-t13`.
- **Consecuencia para T1.5:** la rama ya contiene el #42 entero, así que aterrizarla es
  **empujar estos commits a `feat/relevancia-ciudades-nacional`** (fast-forward), no un merge.

---

## LEE PRIMERO, EN ESTE ORDEN (de disco, completo, antes de tocar nada)

1. `C:\Users\PC 1\.claude\BIBLIOTECA-HERRAMIENTAS.md` — 653 herramientas, 6 fuentes.
2. `C:\Users\PC 1\PanelNioval\CLAUDE.md` — reglas del proyecto.
3. `docs/superpowers/plans/2026-09-15-indice-tanda.md` — orden y dependencias. **D4 RESUELTA**; D1, D2, D3 y D5 abiertas, se avanza con la recomendada.
4. `docs/superpowers/plans/2026-09-15-plan1-relevancia-ciudades-nacional-produccion.md` — **INVARIANTES + bloque de T1.5**.
5. `docs/investigacion/2026-09-15-verificacion-orden-nacional.md` — **T1.4**: CE2/CE3/CE4 y el hallazgo del desempate.
6. `docs/adr/2026-08-28-modelo-relevancia-ciudades.md` — **§9 es de T1.3**: el corte ≥10 y por qué.

---

## INVARIANTES (copiados literales del plan, no resumidos)

- **OBJETIVO DEL PROYECTO:** que el importador de PanelNioval ordene ciudades por relevancia ferretera **nacional**, cueste lo mínimo en Places, cuente la verdad y se vea profesional — **en producción**, no en una rama.
- **DEFINICIÓN DE TERMINADO:** los 4 planes cerrados, sus PRs mergeados a `main`, el VPS sirviendo ese código y `python tools/smoke_panel.py https://panelnioval.duckdns.org --token <valor>` imprimiendo `Todo OK ✅`.
- **RAMA:** una por plan, creada desde `main` actualizado · **NUNCA `main`** (el VPS auto-deploya `main`) · commits convencionales en español.
- **BASELINE (nada avanza si falla):** `cd "C:\Users\PC 1\PanelNioval" && python -m pytest tests/`. ⚠️ **El baseline de esta rama es hoy 525 passed, 1 skipped.** Ha cambiado cuatro veces: 388 (`main` pelado) → 482 (tras el rebase sobre el #42) → 491 (T1.3) → **525** (T1.4). **SIN `-q`**: `pytest.ini` ya lo trae; el segundo lo vuelve `-qq` y **oculta la línea del resumen**.
- **GATES POR TAREA:** `python-reviewer` + `code-reviewer` [+ `security-reviewer` si toca auth, token, entrada de usuario, Places o Sheets] [+ `silent-failure-hunter` si toca `try/except` o fallbacks] [+ `typescript-reviewer` si toca `static/js/*`].
- **PROHIBIDO:** (1) trabajar en `main`; (2) **borrar** — lo retirado va a `docs/auditoria/respaldos/<fecha>/`; (3) mergear con la suite en rojo o con CRITICAL/HIGH abierto; (4) commitear teléfonos o nombres de clientes; (5) rebasar, cerrar o reordenar los PR #42/#43/#44 fuera del orden de aterrizaje del índice.
- **DECISIONES YA TOMADAS (no reabrir):** modelo = logarítmico × `factor_nioval` (ADR `2026-08-28`); HTML a `templates/`+`static/` (PR #43); estado del importador en disco (ADR `2026-08-27`); Places con `fields` explícitos + caché 30 d (PR #38); `/salud` no revela versión ni commit; **corte del catálogo en ≥10** (D4, ADR §9); **desempate por clave INEGI** (ADR §7, aplicado al endpoint en T1.4).
- **SECUENCIA:** **Plan 1 → Plan 4 → Plan 3 → Plan 2.**

---

## AVANCE

- **Global: 0 / 4 planes** · **Plan en curso: 1** · Tareas **5 / 8 (62.5 %)** · Tanda: **5 / 34 (14.7 %)**
- **Nada mergeado, nada desplegado.** El operador todavía no ve ningún cambio.

---

## HECHO EN ESTA SESIÓN (con evidencia, no narrativa)

### T1.3 — el corte baja a ≥10 · commit `89f9ca8`

| Qué quedó | Evidencia |
|---|---|
| **TDD real:** el test RED falló con `Sureste: 65.7 % (6287 de 9564)` ANTES de tocar el generador | salida de pytest |
| **606 → 1,004 municipios**, 32/32 entidades, **0 ciudades perdidas** | comparación de claves contra el respaldo |
| Masa nacional **86.3 % → 93.7 %** · Sureste **65.7 % → 80.6 %** · desequilibrio **1.48× → 1.23×** | medición sobre el catálogo nuevo |
| **CE1** 0 de 995 fuera · **CE3** mínimo 14.1 · 0 nombres ambiguos en las 398 nuevas contra 82 homónimos | tests permanentes con fixture |
| **Defecto preexistente:** el DENUE rellena `municipio` con espacios y viajaban literales a Places | `generar_catalogo_ciudades.py:240-247` |
| ADR **§9 anexada**, 93 líneas, **0 borradas** | `git diff --numstat` |

### T1.4 — el orden nacional verificado · commit `e7acf6e`

| Qué quedó | Evidencia |
|---|---|
| **CE2 verde:** 8 regiones parametrizadas por los 3 eslabones; catálogo, endpoint, filtro y desplegable cuadran en **1,004** | `tests/test_ce2_filtro_por_region.py` |
| **CE3 verde por los dos extremos:** mínimo 14.1; peor caso imaginable 14.1 × 0.60 = **8.46** | `tests/test_ce2_filtro_por_region.py` |
| **CE4 APROBADO por el owner, sin reservas** (2026-09-15) | §8.1 del documento de T1.4 |
| **HALLAZGO: el endpoint desempataba por NOMBRE; el ADR §7 dice CLAVE INEGI.** 103 empates, 232 ciudades, 100 posiciones distintas. Corregido **sin publicar la clave** | §4 del documento · `app.py` |
| **34 tests nuevos, los tres grupos probados por mutación** | recorte `[:200]`/`slice(0,100)` → 12 fallos; `sort` por nombre → 43 empates; predicado disfrazado → falla |
| 4 gates **sin CRITICAL ni HIGH**; los **4 MEDIUM aplicados** | uno era un falso verde real (§8.2) |
| El «flake» que reportó un gate **no lo era**: corrió durante la ventana RED | 4 corridas completas + ambos órdenes de emparejamiento |

---

## ESTADO DE VERIFICACIÓN AHORA MISMO

- **Baseline:** `python -m pytest tests/` → **525 passed, 1 skipped**, exit 0. Medido **4 veces seguidas**, estable.
- **Integridad del catálogo:** `python tools/generar_catalogo_ciudades.py --cache "C:/Users/PC 1/.cache/inegi" --verificar` → *«El catalogo en disco coincide con las fuentes»*, exit 0.
- **Árbol:** limpio, 6 commits sobre `origin/feat/relevancia-ciudades-nacional`, **sin pushear**.
- **Gates de T1.3 y T1.4:** los 7 cerrados, 0 CRITICAL / 0 HIGH.
- **CE1, CE2, CE3, CE4:** los cuatro verdes. **CE5 (smoke en producción) es de T1.6.**

---

## LA TENSIÓN DE T1.5 — resuélvela con el owner, no por omisión

**Lo que dice el plan:** T1.5 aterriza el PR #42 y T1.6 despliega y verifica en producción.

**Lo que dice la condición 2 del consejo de T1.2:** *«1,004 chips sin búsqueda ni filtro por
estado son peores que 606. Este catálogo llega a producción junto con la UI que lo hace
usable»* — la del **Plan 4**.

**El dato que hace falta para resolverlo, y que el consejo no tuvo delante:** la UI de esta
rama **ya tiene** un buscador de texto (`ciudad-filter`, `app.py:5903`) **y** un desplegable de
macro-región con su conteo (`region-filter`, `app.py:5899`), y `filtrarCiudades()` los combina.
Lo que **no** tiene es filtro por **estado**. Así que el escenario que temía el consejo —1,004
chips a pelo— **no es el escenario real**. Queda decidir si «región + texto» basta para
producción o si hay que esperar al Plan 4.

Tres salidas, y la decisión es del owner:

| Salida | Qué implica |
|---|---|
| **Aterrizar ya** (lo que dice el plan) | T1.5 → T1.6. El operador gana 398 plazas con el filtro que ya existe |
| **Aterrizar el código y esperar al Plan 4 para desplegar** | Requiere desacoplar merge de despliegue; `main` auto-deploya, así que **no es gratis** |
| **Esperar al Plan 4 entero** | Cumple la condición 2 al pie de la letra, pero retrasa todo Plan 1 y contradice la secuencia 1 → 4 |

---

## SIGUIENTE PASO EXACTO

**Plan 1, Tarea T1.5 — Aterrizar el PR #42.** ⚠️ **Resuelve antes la tensión de arriba.**

```
ANCLA · Plan 1 Tarea T1.5 · importador nacional barato veraz profesional · avance 5/8 ·
 gates: python-reviewer + code-reviewer sobre el diff NUEVO · CI del PR en verde · 0 CRITICAL/HIGH ·
 baseline: python -m pytest tests/  -> 525 passed, 1 skipped
```

**Qué hacer, en este orden:**

1. **Empujar** los commits de T1.3/T1.4 a `feat/relevancia-ciudades-nacional`. **Es un
   fast-forward**, porque la rama ya se rebasó sobre el #42 en T1.3. **No hagas squash que
   cambie los SHA del #42: descolgaría el PR #43.**
2. Confirmar **CI verde** en el PR #42 actualizado.
3. Gates sobre el **diff nuevo** (no sobre los 12k de agosto, ya revisados): `python-reviewer`
   + `code-reviewer`. `security-reviewer` ya pasó sobre el diff de T1.3.
4. `gh pr merge 42 --squash` **sólo si**: suite verde, CI verde, 0 CRITICAL/HIGH.
   ⚠️ **Ojo con el `--squash`:** el plan lo pide, pero también avisa de que cambiar los SHA
   descuelga al #43. **Comprueba las dos cosas antes de ejecutarlo**, no después.
5. **Inmediatamente después:** verificar que `feat/rediseno-panel` (PR #43) sigue `MERGEABLE`
   contra el nuevo `main`. Si no, anotarlo: es el primer insumo del Plan 4.

**Salida.** PR #42 mergeado; SHA anotado en PROGRESO.
**Criterio de cierre.** `git log main -1` contiene el merge y `pytest` sobre `main` ≥ 525.

**Herramientas asignadas a T1.5:** `python-reviewer` + `code-reviewer` (catalogo-agentes) ·
`superpowers:finishing-a-development-branch` (superpowers) · `git-workflow` (ECC) ·
`django-build-resolver` [OPCIONAL, sólo si rompe imports o pip].

---

## PENDIENTES Y BLOQUEOS

| Asunto | Qué falta | Qué lo desbloquea |
|---|---|---|
| **PR #42** (Plan 1) | Aterrizar (T1.5) y desplegar (T1.6) | **La tensión de arriba** |
| **PR #43** (Plan 4) | Aprobación de la dirección visual + aterrizaje | Plan 4, T4.2 y T4.4 |
| **PR #44** (endurecimiento) | 5 conflictos **contra #43** (contra `main` está MERGEABLE) | Plan 4, T4.6 |
| **Caché `_estado_catalogo`** | `app.py:895-897` se fija en la primera llamada y no se invalida: un fallo transitorio al arrancar serviría `catalogo_cargado: false` hasta el reinicio. **No es silencioso** (el banner rojo sale), pero es un falso positivo persistente | Insumo del **Plan 3** |
| **Ratio de compresión de los ZIP** | Sin tope al leer los del INEGI. Mitigado: URL fija por HTTPS, no input de terceros | Anotado, **no bloquea** |
| **Bug de conteo** | Diagnóstico H1/H2/H3 — **sin hacer** | Plan 3, T3.1 y T3.2 |
| **`claude-mem` caído** | Captura rota desde 2026-09-05 (issue #2188) | **El relevo es la única persistencia** |
| **Gasto en pesos de Places** | Sin acceso a Google Cloud billing | Gate del owner — **D5** |
| **Rotar el token de Telegram** | Heredado (~14 copias) | **Acción del owner**, no automatizable |
| **Decisiones D1, D2, D3, D5** | Respuesta del owner | Se avanza con la recomendada |

---

## SUPUESTOS VIVOS

- `SUPUESTO: el trabajo va sobre PanelNioval, no sobre BruceWhatsapp. — afecta los 4 planes.`
- `SUPUESTO: el gate «≥ 626» se reinterpreta como «≥ baseline de la rama base». Hoy son 525. — afecta los 4 planes.`
- `SUPUESTO: unir la rama con el PR #42 por rebase (opción 1 de T1.5) en vez de esperar a T1.5. Forzado: sin el generador T1.3 no se podía ejecutar. — afecta T1.5.`
- `SUPUESTO: los fixtures del universo ferretero se regeneran junto con el catálogo si alguien usa un corte del DENUE más nuevo. Hoy ambos salen de DENUE 05_2026. — afecta T1.3 y T1.4.`
- `SUPUESTO: CE4 aprueba el orden EXÓGENO del top-30, no la cola larga (las 398 nuevas arrancan en el #434 y nadie las miró una por una) ni el orden final en producción, donde factor_nioval reordena. — afecta T1.4 y cualquier cita futura de esa aprobación.`
- `SUPUESTO: «tokens de la API» = consumo facturable de Google Places. — afecta Plan 2. Ver D2.`
- `SUPUESTO: si la fuga de Details medida en T2.1 es < 10 %, T2.2–T2.4 se saltan. — afecta Plan 2.`
- `SUPUESTO: el síntoma del conteo se observó en producción, no en una rama local. — afecta Plan 3, T3.1.`
- `SUPUESTO: PR #44 se conserva y se rebasa tras #43. — afecta Plan 4, T4.6. Ver D3.`

---

## DECISIONES CERRADAS (NO reabrir)

- **Modelo = logarítmico × `factor_nioval`.**
- **HTML fuera de `app.py`, en `templates/`+`static/`.**
- **Estado del importador compartido en disco.**
- **Places legacy con `fields` explícitos**; la migración es del Plan 2.
- **`/salud` no revela versión ni commit.**
- **D4 → umbral ≥10 ferreterías** (T1.2), **aplicado en T1.3**, ADR §9.
- **El 75 % del test de cobertura es NORMATIVO**, elegido tras ver los datos y declarado.
- **NUEVA (T1.4) · El desempate final es la CLAVE INEGI, no el nombre** (ADR §7). El endpoint
  ya lo cumple. **La clave sigue sin publicarse en el payload**: son dos decisiones distintas
  y las dos siguen en pie.
- **NUEVA (T1.4) · CE4 aprobado por el owner**, sin reservas y sin ciudades señaladas.

---

## TRAMPAS DESCUBIERTAS (lo que costó tiempo y no está en ningún otro documento)

- **🆕 El heredoc de bash SE COME UN BACKSLASH en este entorno.** `"\\n"` dentro de un heredoc
  `<<'EOF'` llega a Python como `"\n"` (salto real), no como los dos caracteres. Rompió un
  archivo de test y luego un ancla de búsqueda. **Usa `chr(92)` para construir backslashes**, o
  escribe el archivo con la herramienta de escritura.
- **🆕 `git checkout -- app.py` para deshacer una mutación SE LLEVA TAMBIÉN lo no commiteado.**
  Pasó: revirtió el arreglo del desempate junto con la mutación de prueba. **Commitea antes de
  mutar, o respalda el archivo a mano.**
- **🆕 El generador no estaba en esta rama.** Vive en el PR #42. Antes de planear una tarea que
  toque un archivo, **comprueba que existe en disco**, no que un documento lo cite con línea.
- **🆕 La app es fail-closed:** sin `PANEL_DASHBOARD_TOKEN` no arranca. Para un script suelto,
  `PANEL_AUTH_DESACTIVADA=1` (es lo que hace `tests/conftest.py`).
- **🆕 El stdout de Python en esta consola es cp1252** y corrompe acentos al redirigir a
  archivo. Escribe con `pathlib.write_text(..., encoding="utf-8")`, no con `>`.
- **🆕 La caché del INEGI ya está poblada** en `C:\Users\PC 1\.cache\inegi` (ferreterías:
  **60,209,960 bytes exactos**). Regenerar **no descarga 117 MB**: tarda ~1 min.
- **🆕 `normalizar()` colapsa espacios, y eso ESCONDE bugs.** Un nombre con 70 espacios pasaba
  todos los tests de duplicados. Para ver lo que viaja a Places, mira el nombre **crudo**.
- **🆕 Un guard por subcadena se engaña con un comentario.** El test que fijaba el predicado del
  filtro buscaba en todo el recorte del JS, comentarios incluidos. Limpia comentarios antes.
- **🆕 Las guardas nuevas hay que probarlas por mutación.** Planta el defecto y comprueba que
  falla; si no, su verde no vale nada.
- **El baseline es por rama:** 388 / 482 / 491 / 525. Comprueba siempre contra la rama base.
- **`pytest -q` oculta el resultado.** Correr `python -m pytest tests/` a secas.
- **`.gitignore` ignora `*.json` global** con excepción por ruta exacta para
  `datos/ciudades_mx.json`. Los fixtures nuevos son `.csv`/`.txt` **a propósito**.
- **`docs/auditoria/respaldos/` está en `.gitignore`.** No se commitea.
- **No pases rutas MSYS (`/c/Users/…`) a Python**: es un Python de Windows. Usa `C:/Users/…`.
- **Las URLs de DENUE tienen trampa:** `denue_00_46_csv.zip` responde **HTTP 200 con 0 bytes**.
  Validar tamaño mínimo, nunca el status code. **No le quites esa validación al generador.**
- **La caché de Places falsea la medición del ahorro.** Medir ciudad virgen y trabajada aparte.
- **Los planes 1 y 4 ya están construidos.** Quien no lea esto va a rediseñar ~40,000 líneas
  que ya existen con CI en verde.

---

## REGLAS QUE SIGUEN VIGENTES

Anclaje al iniciar cada tarea · test de deriva al cerrarla · umbrales de relevo (**2 de 3
tareas gastadas en esta sesión**) · dudas acumuladas y presentadas juntas al cerrar cada plan ·
**herramientas de la tabla de asignación (no colapsar a Superpowers: son 14 de 653)** · merge
sólo con gates en verde · **nunca trabajar en `main`**.
