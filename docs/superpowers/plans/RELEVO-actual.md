# RELEVO ACTUAL — PanelNioval · tanda 2026-09-15

> **Archivo único que se SOBRESCRIBE al cerrar CADA tarea.** Siempre contiene el mensaje
> completo para arrancar una sesión nueva. Si la sesión muere de golpe, se pierde una tarea,
> no el hilo del proyecto.
>
> **Estado: sesión 1 en curso · última tarea cerrada: Plan 1 · T1.0.**

---

Continúas el proyecto **PanelNioval**. **Sesión 1.** NO empieces de cero: el diseño ya está
hecho y **dos de los cuatro planes ya están construidos en PR abiertos**.

**PROYECTO:** `C:\Users\PC 1\PanelNioval`
**RAMA DE TRABAJO:** `feat/relevancia-nacional-produccion` — **ya creada** desde `main` (T1.0). Estás en ella.
**ÚLTIMO COMMIT (en `main`):** `82995c3` — *docs(tanda): decisiones E1-E4 del owner y handoff del Plan 1 (#41)*

---

## LEE PRIMERO, EN ESTE ORDEN (de disco, completo, antes de tocar nada)

1. `C:\Users\PC 1\.claude\BIBLIOTECA-HERRAMIENTAS.md` — 653 herramientas (229 agentes + 424 skills), 6 fuentes: `catalogo-agentes`, `ECC`, `claude-ads`, `community`, `claude-mem`, `superpowers`.
2. `C:\Users\PC 1\PanelNioval\CLAUDE.md` — reglas del proyecto.
3. `docs/superpowers/plans/2026-09-15-indice-tanda.md` — orden, dependencias y las **5 decisiones pendientes** (D1–D5, todas abiertas; se avanza con la recomendada).
4. `docs/superpowers/plans/2026-09-15-plan1-relevancia-ciudades-nacional-produccion.md` — **bloque INVARIANTES + bloque de T1.1**.
5. **`docs/auditoria/2026-09-15-estado-de-partida-plan1.md`** — ⚠️ **NUEVO, léelo**: corrige el baseline y la §0 del plan con medidas reales sobre `main`.

---

## INVARIANTES (copiados literales del plan, no resumidos)

- **OBJETIVO DEL PROYECTO:** que el importador de PanelNioval ordene ciudades por relevancia ferretera **nacional**, cueste lo mínimo en Places, cuente la verdad y se vea profesional — **en producción**, no en una rama.
- **DEFINICIÓN DE TERMINADO:** los 4 planes cerrados, sus PRs mergeados a `main`, el VPS sirviendo ese código y `python tools/smoke_panel.py https://panelnioval.duckdns.org --token <valor>` imprimiendo `Todo OK ✅`.
- **RAMA:** una por plan, creada desde `main` actualizado · **NUNCA `main`** (el VPS auto-deploya `main`) · commits convencionales en español.
- **BASELINE (nada avanza si falla):** `cd "C:\Users\PC 1\PanelNioval" && python -m pytest tests/`. ⚠️ **CORREGIDO EN T1.0:** el gate real sobre ramas basadas en `main` es **≥ 388 passed, 1 skipped**, exit 0. El **≥ 626** de este bloque es el baseline de `fix/endurecimiento-panel` (PR #44) y vuelve a aplicar en cuanto #44 aterrice (Plan 4, T4.6). **SIN `-q`**: `pytest.ini` ya lo trae; el segundo lo convierte en `-qq` y **oculta la línea del resumen**.
- **GATES POR TAREA:** `python-reviewer` + `code-reviewer` [+ `security-reviewer` si toca auth, token, entrada de usuario, Places o Sheets] [+ `silent-failure-hunter` si toca `try/except` o fallbacks] [+ `typescript-reviewer` si toca `static/js/*`].
- **PROHIBIDO:** (1) trabajar en `main`; (2) **borrar** — lo retirado va a `docs/auditoria/respaldos/<fecha>/`; (3) mergear con la suite en rojo o con CRITICAL/HIGH abierto; (4) commitear teléfonos o nombres de clientes — anonimizar a `+52…XXXX`; (5) rebasar, cerrar o reordenar los PR #42/#43/#44 fuera del orden de aterrizaje del índice.
- **DECISIONES YA TOMADAS (no reabrir):** modelo de relevancia = logarítmico × `factor_nioval` (ADR `2026-08-28`, tres candidatos medidos sobre 589 municipios); HTML extraído a `templates/`+`static/` (PR #43); estado del importador compartido en disco (ADR `2026-08-27`); Places con `fields` explícitos + caché 30 d (PR #38, mergeado); `/salud` no revela versión ni commit.
- **SECUENCIA:** **Plan 1 → Plan 4 → Plan 3 → Plan 2.** Es dependencia real: PR #43 está **apilado sobre** PR #42 (verificado en disco en T1.0), y el bug del Plan 3 debe arreglarse una sola vez, en la estructura final (`static/js/importador.js`).

---

## AVANCE

- **Global: 0 / 4 planes** · **Plan en curso: 1** · Tareas **1 / 8 (12.5 %)** · Tareas de la tanda: **1 / 34 (2.9 %)**
- **Planes cerrados y mergeados:** ninguno todavía.

---

## HECHO EN ESTA SESIÓN (con evidencia, no narrativa)

| Tarea | Qué quedó | Evidencia |
|---|---|---|
| **T1.0** | Rama `feat/relevancia-nacional-produccion` creada desde `origin/main` (`82995c3`) | `git branch --show-current` |
| **T1.0** | Baseline medido y **corregido**: **388 passed, 1 skipped**, exit 0 (49.4 s) | `docs/auditoria/respaldos/2026-09-15/baseline-T1.0-rama-produccion.txt` |
| **T1.0** | Demostrado que el hueco 388→626 **no es regresión**: 0 failed, 0 errors, ningún test borrado; las 5 suites de endurecimiento (2,447 líneas) sólo existen en PR #44 | `git diff --diff-filter=D … -- tests/` → vacío |
| **T1.0** | PR #42 revalidado: **OPEN · MERGEABLE · CLEAN**, head `499d41b`, 17 archivos, +12,345/−138, **ambos checks SUCCESS** | `gh pr view 42` |
| **T1.0** | Apilamiento **#43 sobre #42 confirmado en disco** (no asumido) | `git merge-base --is-ancestor` → 0 |
| **T1.0** | **R6 despejado:** el generador descarga DENUE/Censo del INEGI en runtime; el umbral es un solo parámetro (`minimo_ferreterias`, `tools/generar_catalogo_ciudades.py:391-393`) | lectura del generador en la rama del PR |
| **T1.0** | Respaldo creado **antes** de tocar código: `app.py`, `ciudades_mx.json`, salida del baseline | `docs/auditoria/respaldos/2026-09-15/` |
| **T1.0** | Documento de estado de partida con los 5 números | `docs/auditoria/2026-09-15-estado-de-partida-plan1.md` |

---

## ESTADO DE VERIFICACIÓN AHORA MISMO

- **Baseline:** `python -m pytest tests/` → **PASA** — **388 passed, 1 skipped**, exit 0, medido el 2026-09-15 sobre `feat/relevancia-nacional-produccion` (base `main` `82995c3`).
- **Gates de la última tarea (T1.0):** cerrados. T1.0 no lleva reviewers ni tests; su gate era *respaldo antes de tocar nada* (cumplido) y *baseline medido y anotado* (cumplido).
- **Árbol de trabajo:** en `feat/relevancia-nacional-produccion`, con el commit de T1.0 hecho.
- **CI:** PR #42 con los dos checks en verde, **remedidos hoy** (no heredados de agosto).

---

## SIGUIENTE PASO EXACTO

**Plan 1, Tarea T1.1 — Recuperar el contexto previo y no re-litigar lo cerrado.**

```
ANCLA · Plan 1 Tarea T1.1 · importador nacional barato veraz profesional · avance 1/8 ·
 gates: >=5 decisiones cerradas con fuente (ADR o ID de observacion) · baseline: python -m pytest tests/
```

Qué hacer, literal del plan:
1. `claude-mem:mem-search` sobre: importador, ciudades, relevancia, DENUE, Places, PanelNioval.
   Buscar en particular la observación *"City Relevance Algorithm Uses Only Existing Contact
   Sheet Data — Not Industry Importance"*, origen de todo esto.
2. Leer, **de la rama `origin/feat/relevancia-ciudades-nacional`** (no están en `main`):
   `docs/adr/2026-08-28-modelo-relevancia-ciudades.md`,
   `docs/investigacion/2026-08-28-relevancia-ferretera-mexico.md`,
   `docs/investigacion/2026-08-29-verificacion-plan1.md`.
   (También existe `docs/investigacion/2026-08-28-contexto-previo-importador.md`.)
3. Producir `docs/investigacion/2026-09-15-contexto-plan1.md` con **qué está decidido y no se
   reabre** y **qué quedó abierto** (debe coincidir con §0.2 del plan).

**Herramientas asignadas a T1.1:** `claude-mem:mem-search` (claude-mem) · `claude-mem:timeline-report` [OPCIONAL, sólo si mem-search devuelve fragmentos sueltos].

---

## PENDIENTES Y BLOQUEOS

| Asunto | Qué falta | Qué lo desbloquea |
|---|---|---|
| **PR #42** (Plan 1) | Verificar cobertura por región, mergear, desplegar | Plan 1, T1.2 → T1.6 |
| **PR #43** (Plan 4) | Aprobación de la dirección visual + aterrizaje | Plan 4, T4.2 y T4.4 |
| **PR #44** (endurecimiento) | 5 conflictos **contra #43** (contra `main` está MERGEABLE) | Plan 4, T4.6 (rebase tras mergear #43) |
| **Bug de conteo** | Diagnóstico H1/H2/H3 — **sin hacer** | Plan 3, T3.1 y T3.2 |
| **Gasto en pesos de Places** | Sin acceso a Google Cloud billing | **Gate del owner** — decisión D5 |
| **Rotar el token de Telegram** | Heredado de la tanda anterior (~14 copias) | **Acción del owner**, no automatizable |
| **5 decisiones (D1–D5)** | Respuesta del owner | Mientras tanto, los planes avanzan con la opción recomendada |
| **Descarga DENUE (T1.3)** | Requiere red hacia INEGI; ~50 MB el archivo de ferreterías | Conectividad en la sesión que ejecute T1.3 |

---

## SUPUESTOS VIVOS (se asumieron sin confirmar; siguen vigentes salvo indicación contraria)

- `SUPUESTO: el trabajo va sobre PanelNioval, no sobre BruceWhatsapp (la ruta dada en el encargo). — afecta los 4 planes.`
- `SUPUESTO: el gate «≥ 626» de INVARIANTES se reinterpreta como «≥ baseline de la rama base», hoy 388 sobre main. No se relaja el criterio: se corrige la referencia. — afecta los 4 planes. NUEVO en T1.0.`
- `SUPUESTO: «todas las ciudades de la región» = todo municipio con presencia ferretera real según umbral DENUE, no los 2,469 del país. — afecta Plan 1, T1.2.`
- `SUPUESTO: «tokens de la API» = consumo facturable de Google Places (PanelNioval no usa ningún LLM). — afecta Plan 2 completo. Ver D2.`
- `SUPUESTO: si la fuga de Details medida en T2.1 es < 10 %, la migración no se paga sola y T2.2–T2.4 se saltan. — afecta Plan 2, T2.2–T2.4.`
- `SUPUESTO: el síntoma del conteo se observó en producción, no en una rama local. — afecta Plan 3, T3.1.`
- `SUPUESTO: PR #44 se conserva y se rebasa tras #43, no se descarta. — afecta Plan 4, T4.6. Ver D3.`

---

## DECISIONES CERRADAS (NO reabrir ni re-discutir)

- **Modelo de relevancia = logarítmico × `factor_nioval`** — tres candidatos calculados de verdad sobre 589 municipios; los lineales dejaban 2 de cada 3 ciudades empatadas.
- **HTML fuera de `app.py`, en `templates/`+`static/`** — el monolito es insostenible.
- **Estado del importador compartido en disco** — el `council` eligió A sobre la B del plan: la premisa de B era falsa (`daemon=True` muere igual).
- **Places legacy con `fields` explícitos, no migrar «en ese plan»** — se pagaban 50 campos para leer 3. La migración es materia del Plan 2.
- **`/salud` no revela versión ni commit** — decisión de seguridad; complica el diagnóstico del Plan 3 y aun así **no se revierte**.

---

## TRAMPAS DESCUBIERTAS (lo que costó tiempo y no está en ningún otro documento)

- **El baseline es por rama, y el 626 no es el de `main`.** Un gate absoluto («≥ 626») es inalcanzable desde una rama basada en `main`: el número real ahí es **388**. Comprobar siempre contra la rama base, y demostrar que la diferencia son tests *añadidos* por otra rama, no tests rotos (`--diff-filter=D` sobre `tests/`).
- **`pytest -q` oculta el resultado.** `pytest.ini` ya trae `addopts = -q`; añadir otro lo vuelve `-qq` y **suprime la línea del resumen**. Correr `python -m pytest tests/` a secas.
- **`docs/auditoria/respaldos/` está en `.gitignore`** (`.gitignore:22`). Los respaldos viven en disco, **no** se commitean: `git add` no los mete y no hay que forzarlos. Hay 10 fechas previas ahí, ninguna trackeada.
- **`app.py` tiene 6,098 líneas en `main`, no 6,610.** El 6,610 de la §0 del plan se midió sobre `fix/endurecimiento-panel`.
- **El generador de catálogo descarga del INEGI en runtime**, no lee fuentes del repo; y valida tamaño mínimo porque *«el INEGI sirve archivos vacíos con HTTP 200»*.
- **El heredoc de bash se atraganta con estos documentos largos** (acentos, `«»`, viñetas): usa la herramienta de escritura de archivos directa, no `cat <<'EOF'`. Falló una vez y dejó el archivo intacto — verifícalo siempre con `wc -c` antes de suponer escritura parcial.
- **`grep -ril` sobre la raíz de estos repos tarda minutos.** Usar `Grep` (ripgrep) con `--glob`.
- **La caché de Places falsea la medición del ahorro.** Medir siempre ciudad virgen y ciudad trabajada por separado.
- **Los planes 1 y 4 ya están construidos.** Quien no lea esto va a rediseñar ~40,000 líneas que ya existen con CI en verde.

---

## REGLAS QUE SIGUEN VIGENTES

Anclaje al iniciar cada tarea · test de deriva al cerrarla · umbrales de relevo · dudas
acumuladas y presentadas juntas al cerrar cada plan · **herramientas de la tabla de asignación
(no colapsar a Superpowers: son 14 de 653)** · merge solo con gates en verde · **nunca
trabajar en `main`**.
