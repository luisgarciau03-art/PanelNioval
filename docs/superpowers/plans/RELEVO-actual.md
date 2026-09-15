# RELEVO ACTUAL — PanelNioval · tanda 2026-09-15

> **Archivo único que se SOBRESCRIBE al cerrar CADA tarea.** Siempre contiene el mensaje
> completo para arrancar una sesión nueva.
>
> **Estado: sesión 1 CERRADA por umbral de relevo (3 tareas cerradas). Última tarea: Plan 1 · T1.2.**

---

Continúas el proyecto **PanelNioval**. **Sesión 2.** NO empieces de cero: el diseño ya está
hecho, **dos de los cuatro planes ya están construidos en PR abiertos**, y la sesión 1 cerró
T1.0, T1.1 y T1.2.

**PROYECTO:** `C:\Users\PC 1\PanelNioval`
**RAMA DE TRABAJO:** `feat/relevancia-nacional-produccion` — **ya creada y con 3 commits**. Estás en ella. Árbol limpio.
**ÚLTIMO COMMIT (en la rama):** `3b4c4de` — *docs(plan1): T1.2 cerrada — la brecha de cobertura medida y D4 resuelta en >=10*
**ÚLTIMO COMMIT (en `main`):** `82995c3` — sin cambios; nada se ha mergeado todavía.

---

## LEE PRIMERO, EN ESTE ORDEN (de disco, completo, antes de tocar nada)

1. `C:\Users\PC 1\.claude\BIBLIOTECA-HERRAMIENTAS.md` — 653 herramientas (229 agentes + 424 skills), 6 fuentes: `catalogo-agentes`, `ECC`, `claude-ads`, `community`, `claude-mem`, `superpowers`.
2. `C:\Users\PC 1\PanelNioval\CLAUDE.md` — reglas del proyecto.
3. `docs/superpowers/plans/2026-09-15-indice-tanda.md` — orden y dependencias. **D4 ya está RESUELTA** (§8); D1, D2, D3 y D5 siguen abiertas y se avanza con la recomendada.
4. `docs/superpowers/plans/2026-09-15-plan1-relevancia-ciudades-nacional-produccion.md` — **bloque INVARIANTES + bloque de T1.3**.
5. **`docs/investigacion/2026-09-15-cobertura-catalogo-ciudades.md`** — ⚠️ **imprescindible**: trae el umbral decidido, el test RED a escribir y las tres condiciones que acompañan al cambio.
6. `docs/auditoria/2026-09-15-estado-de-partida-plan1.md` — corrige el baseline y la §0 del plan.

---

## INVARIANTES (copiados literales del plan, no resumidos)

- **OBJETIVO DEL PROYECTO:** que el importador de PanelNioval ordene ciudades por relevancia ferretera **nacional**, cueste lo mínimo en Places, cuente la verdad y se vea profesional — **en producción**, no en una rama.
- **DEFINICIÓN DE TERMINADO:** los 4 planes cerrados, sus PRs mergeados a `main`, el VPS sirviendo ese código y `python tools/smoke_panel.py https://panelnioval.duckdns.org --token <valor>` imprimiendo `Todo OK ✅`.
- **RAMA:** una por plan, creada desde `main` actualizado · **NUNCA `main`** (el VPS auto-deploya `main`) · commits convencionales en español.
- **BASELINE (nada avanza si falla):** `cd "C:\Users\PC 1\PanelNioval" && python -m pytest tests/`. ⚠️ **CORREGIDO EN T1.0:** el gate real sobre ramas basadas en `main` es **≥ 388 passed, 1 skipped**, exit 0. El **≥ 626** del plan es el baseline de `fix/endurecimiento-panel` (PR #44) y vuelve a aplicar en cuanto #44 aterrice (Plan 4, T4.6). **SIN `-q`**: `pytest.ini` ya lo trae; el segundo lo convierte en `-qq` y **oculta la línea del resumen**.
- **GATES POR TAREA:** `python-reviewer` + `code-reviewer` [+ `security-reviewer` si toca auth, token, entrada de usuario, Places o Sheets] [+ `silent-failure-hunter` si toca `try/except` o fallbacks] [+ `typescript-reviewer` si toca `static/js/*`].
- **PROHIBIDO:** (1) trabajar en `main`; (2) **borrar** — lo retirado va a `docs/auditoria/respaldos/<fecha>/`; (3) mergear con la suite en rojo o con CRITICAL/HIGH abierto; (4) commitear teléfonos o nombres de clientes — anonimizar a `+52…XXXX`; (5) rebasar, cerrar o reordenar los PR #42/#43/#44 fuera del orden de aterrizaje del índice.
- **DECISIONES YA TOMADAS (no reabrir):** modelo de relevancia = logarítmico × `factor_nioval` (ADR `2026-08-28`); HTML extraído a `templates/`+`static/` (PR #43); estado del importador compartido en disco (ADR `2026-08-27`); Places con `fields` explícitos + caché 30 d (PR #38, mergeado); `/salud` no revela versión ni commit.
- **SECUENCIA:** **Plan 1 → Plan 4 → Plan 3 → Plan 2.** Dependencia real: PR #43 está **apilado sobre** PR #42 (verificado en disco en T1.0).

---

## AVANCE

- **Global: 0 / 4 planes** · **Plan en curso: 1** · Tareas **3 / 8 (37.5 %)** · Tareas de la tanda: **3 / 34 (8.8 %)**
- **Planes cerrados y mergeados:** ninguno todavía. **Nada ha llegado a producción.**

---

## HECHO EN LA SESIÓN 1 (con evidencia, no narrativa)

| Tarea | Qué quedó | Evidencia |
|---|---|---|
| **T1.0** | Rama creada desde `origin/main` (`82995c3`); respaldo hecho **antes** de tocar nada | commit `a9938ed` · `docs/auditoria/respaldos/2026-09-15/` |
| **T1.0** | **Baseline corregido a 388 passed, 1 skipped.** El 626 del plan es de otra rama; se demostró que no es regresión (0 failed, 0 errors, ningún test borrado; las 5 suites de endurecimiento sólo existen en PR #44) | `docs/auditoria/2026-09-15-estado-de-partida-plan1.md` §2 |
| **T1.0** | PR #42 revalidado **OPEN · MERGEABLE · CLEAN**, head `499d41b`, ambos checks SUCCESS; apilamiento #43→#42 confirmado con `git merge-base` | `gh pr view 42` |
| **T1.0** | **R6 despejado:** el generador descarga DENUE/Censo del INEGI en runtime | `tools/generar_catalogo_ciudades.py` |
| **T1.1** | **9 decisiones cerradas con fuente** (pedía ≥5); lo abierto = A1/A2/A3, coincide con §0.2 | commit `53aa56a` · `docs/investigacion/2026-09-15-contexto-plan1.md` |
| **T1.1** | ⚠️ **`claude-mem` caído** desde 2026-09-05 (`CAPTURE_BROKEN`, issue #2188). Sustitución **declarada**: se usó la transcripción de agosto con las 8 observaciones y su ID | `~/.claude-mem/CAPTURE_BROKEN` |
| **T1.2** | **La brecha, en números:** 1,621 municipios fuera, **ninguno llega a 20** (el mayor excluido del país tiene 19). **13.7 % de la masa ferretera nacional fuera; Sureste al 65.6 % contra 97.2 % del Valle de México** | commit `3b4c4de` · `docs/investigacion/2026-09-15-cobertura-catalogo-ciudades.md` |
| **T1.2** | Verificación en las dos direcciones: pipeline independiente **reproduce exactamente** las 4 cifras de agosto (75,726 / 2,227 / 995 / 589) y 0 del catálogo caen fuera del universo | `tools/auditar_cobertura_ciudades.py` |
| **T1.2** | **Discrepancia 589 vs 606 resuelta** (era hipótesis en T1.1): 589 por umbral + 17 por herencia legacy vía `resolver_array_viejo()` | §3 del documento |
| **T1.2** | **D4 RESUELTA: umbral ≥10.** Vía `council`; el Arquitecto cambió su posición inicial de ≥5 a ≥10 | índice §8 · documento §6-7 |
| **T1.2** | Gate `data-analyst` levantó **3 objeciones y las 3 se aplicaron** (non-sequitur de la métrica, hecho vs juicio, y el 75 % elegido post-hoc) | §12 del documento |

---

## ESTADO DE VERIFICACIÓN AHORA MISMO

- **Baseline:** `python -m pytest tests/` → **PASA** — **388 passed, 1 skipped**, exit 0 (medido dos veces: T1.0 y T1.2).
- **Gates de la última tarea (T1.2):** **cerrados.** `data-analyst` ejecutado, sus 3 objeciones aplicadas al documento; la brecha es un número.
- **Árbol de trabajo:** **limpio**, 3 commits sobre `origin/main`, sin pushear.
- **CI:** PR #42 con los dos checks en verde, remedidos el 2026-09-15.
- ⚠️ **Nada mergeado, nada desplegado.** El operador todavía no ve ningún cambio.

---

## SIGUIENTE PASO EXACTO

**Plan 1, Tarea T1.3 — Cerrar la brecha de cobertura (TDD).** **NO se salta:** T1.2 midió
brecha real (13.7 % de la masa nacional fuera).

```
ANCLA · Plan 1 Tarea T1.3 · importador nacional barato veraz profesional · avance 3/8 ·
 gates: TDD RED antes que GREEN + python-reviewer + code-reviewer + security-reviewer + CE1 y CE3 verdes ·
 baseline: python -m pytest tests/
```

**Qué hacer, en este orden (TDD, literal del plan):**

1. **RED** — test en `tests/test_catalogo_ciudades.py`:
   *«ninguna macro-región cubre menos del **75 %** de la masa ferretera de su región»*.
   Hoy el Sureste da **65.6 %** → **debe fallar**. Con ≥10 da **80.4 %** → pasa.
   ⚠️ El 75 % es un umbral **normativo**, elegido después de ver los datos (declarado como
   tal en §10 del documento de T1.2). No lo presentes como derivado del dato.
2. **GREEN** — cambiar `minimo_ferreterias` de **20** a **10** en
   `tools/generar_catalogo_ciudades.py:391-393` y **regenerar** el catálogo.
   ⚠️ **Regenerar descarga ~117 MB del INEGI** (ferreterías 60 MB + mayoreo 18 MB +
   construcción 2.7 MB + Censo 36 MB). Requiere red. **No quitar la validación de tamaño
   mínimo**: el INEGI sirve `denue_00_46_csv.zip` con **HTTP 200 y 0 bytes**.
3. **Verificar CE3** — `min(potencial_mercado) > 5`. Riesgo bajo: el catálogo ya contiene un
   municipio de **1 sola ferretería** (Ejutla) que puntúa **14.1**, 2.8× por encima del piso.
4. **Condición del consejo, no opcional:** verificar que las **~406 ciudades nuevas tienen
   nombre de búsqueda resuelto** (homónimos: `Benito Juárez`, `Hidalgo`, `Juárez`,
   `Zaragoza`, `Morelos`). El nombre viaja literal a Places y ese fallo ya costó dinero.
5. **Anexar al ADR** `docs/adr/2026-08-28-modelo-relevancia-ciudades.md` una sección
   «Revisión 2026-09-15». **Anexo, no reescritura.**
6. Correr la suite completa: las 4 suites del catálogo deben seguir verdes.

**Número objetivo:** ~995 municipios por umbral + los heredados que queden por debajo.
**El modelo de puntuación NO se toca** (decisión cerrada).

**Herramientas asignadas a T1.3:** `superpowers:test-driven-development` (superpowers) ·
`tdd-guide` (catalogo-agentes) · `python-pro` (catalogo-agentes) · `python-patterns` (ECC) ·
`architecture-decision-records` (ECC) · `django-build-resolver` [OPCIONAL, sólo si rompe
imports o pip] · gates `python-reviewer` + `code-reviewer` + `security-reviewer`.

---

## PENDIENTES Y BLOQUEOS

| Asunto | Qué falta | Qué lo desbloquea |
|---|---|---|
| **PR #42** (Plan 1) | Verificar orden nacional (T1.4), mergear (T1.5), desplegar (T1.6) | T1.3 → T1.6 |
| **PR #43** (Plan 4) | Aprobación de la dirección visual + aterrizaje | Plan 4, T4.2 y T4.4 |
| **PR #44** (endurecimiento) | 5 conflictos **contra #43** (contra `main` está MERGEABLE) | Plan 4, T4.6 |
| **Bug de conteo** | Diagnóstico H1/H2/H3 — **sin hacer** | Plan 3, T3.1 y T3.2 |
| **T1.3 necesita red** | ~117 MB del INEGI para regenerar | Conectividad (verificada OK el 2026-09-15) |
| **`claude-mem` caído** | Captura rota desde 2026-09-05 (issue #2188) | **El relevo es la única persistencia.** Acción de entorno |
| **Gasto en pesos de Places** | Sin acceso a Google Cloud billing | Gate del owner — **D5** |
| **Rotar el token de Telegram** | Heredado (~14 copias) | **Acción del owner**, no automatizable |
| **Decisiones D1, D2, D3, D5** | Respuesta del owner | Se avanza con la recomendada. **D4 ya resuelta** |

---

## SUPUESTOS VIVOS

- `SUPUESTO: el trabajo va sobre PanelNioval, no sobre BruceWhatsapp. — afecta los 4 planes.`
- `SUPUESTO: el gate «≥ 626» se reinterpreta como «≥ baseline de la rama base», hoy 388 sobre main. — afecta los 4 planes. (T1.0)`
- `SUPUESTO: «todas las ciudades de la región» = municipio con presencia ferretera real. RESUELTO en T1.2: el corte queda en ≥10 ferreterías.`
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
- **`/salud` no revela versión ni commit** — decisión de seguridad; no se revierte.
- **NUEVA (T1.2) · D4 → umbral ≥10 ferreterías.** Ni ≥5 ni ≥20. Revocable por el owner (es un parámetro de una línea), pero **no se re-litiga sin dato nuevo**.

---

## TRAMPAS DESCUBIERTAS (lo que costó tiempo y no está en ningún otro documento)

- **El baseline es por rama, y el 626 no es el de `main`:** ahí son **388**. Comprobar siempre contra la rama base y demostrar que la diferencia son tests *añadidos* por otra rama (`git diff --diff-filter=D -- tests/`), no tests rotos.
- **`pytest -q` oculta el resultado.** `pytest.ini` ya trae `addopts = -q`; otro lo vuelve `-qq`. Correr `python -m pytest tests/` a secas.
- **`docs/auditoria/respaldos/` está en `.gitignore`** (`.gitignore:22`). Los respaldos viven en disco y **no se commitean**; no hay que forzarlos.
- **`claude-mem` no está disponible y su captura lleva rota desde el 2026-09-05.** No confíes en que la sesión se guarde sola.
- **El heredoc de bash se atraganta con estos documentos largos** (acentos, `«»`): usa la herramienta de escritura directa, no `cat <<'EOF'`. Falló una vez; verifica con `wc -c` antes de suponer escritura parcial.
- **No pases rutas MSYS (`/c/Users/…`) a Python**: es un Python de Windows (`C:\Python314`) y da `FileNotFoundError`. Usa `C:/Users/…`.
- **Las URLs de DENUE tienen trampa:** `denue_00_46_csv.zip` responde **HTTP 200 con 0 bytes** y `denue_00_467_csv.zip` responde **HTTP 200 con HTML**. Validar tamaño mínimo, nunca el status code.
- **El ZIP de ferreterías pesa 60,209,960 bytes exactos** (igual que en agosto) y tarda ~2 min. Es la comprobación barata de integridad.
- **`app.py` tiene 6,098 líneas en `main`, no 6,610.**
- **La caché de Places falsea la medición del ahorro.** Medir siempre ciudad virgen y ciudad trabajada por separado.
- **Los planes 1 y 4 ya están construidos.** Quien no lea esto va a rediseñar ~40,000 líneas que ya existen con CI en verde.

---

## REGLAS QUE SIGUEN VIGENTES

Anclaje al iniciar cada tarea · test de deriva al cerrarla · umbrales de relevo · dudas
acumuladas y presentadas juntas al cerrar cada plan · **herramientas de la tabla de asignación
(no colapsar a Superpowers: son 14 de 653)** · merge solo con gates en verde · **nunca
trabajar en `main`**.
