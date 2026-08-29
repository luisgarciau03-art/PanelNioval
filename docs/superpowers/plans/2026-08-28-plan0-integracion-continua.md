# PLAN 0 — INTEGRACIÓN CONTINUA: EL GATE DEJA DE DEPENDER DE LA MEMORIA

**Fecha de diseño:** 2026-08-28
**Proyecto:** PanelNioval — `C:\Users\PC 1\PanelNioval`
**Superficie afectada:** `.github/workflows/` (no existe hoy), `pytest.ini`, `CLAUDE.md`
**Rama de trabajo:** `ci/pytest-en-cada-pr` (desde `main` actualizado — **NUNCA `main`**)
**Baseline verificado en disco el 2026-08-28:** `python -m pytest tests/` → **357 passed, 1 skipped**, exit 0
**Origen:** mejora **M1** del índice de la tanda 2026-08-27, §4.1. Recomendada allí como
"la única mejora que se hace antes que todo lo demás" y nunca redactada como plan.

---

## 1. EL PROBLEMA, CON EVIDENCIA

```
$ ls -d .github
ls: cannot access '.github': No such file or directory
```

El proyecto tiene **357 tests** y una regla que dice "nada se mergea con la suite en rojo".
Esa regla **solo se cumple si alguien se acuerda de correr pytest a mano**. No hay
mecanismo: hay intención.

Tres agravantes verificados en este repo:

1. **El comando oficial es contraintuitivo.** `pytest.ini` trae `addopts = -q`; añadir otro
   `-q` lo convierte en `-qq`, que **suprime la línea del resumen**. Se ven los puntos y
   `exit 0`, pero nunca el número. Los cuatro planes de la tanda 2026-08-27 citaban
   `pytest tests/ -q` justo por eso. Un runner de CI no se olvida de la bandera.
2. **Importar `app.py` en frío tarda ~100 s** en la máquina del owner (googleapiclient +
   Defender). Eso desincentiva correr la suite antes de cada commit. En CI el coste es del
   runner, no de la persona.
3. **`main` tiene auto-deploy** a Railway y a Vultr. Un merge en rojo llega a producción
   sin escala intermedia.

**Este plan convierte el gate en mecanismo.** Es corto a propósito: 4 tareas, sin tocar
`app.py`, sin riesgo de regresión funcional.

---

## 2. OBJETIVO Y ALCANCE

**Objetivo.** Que ningún PR pueda mergearse a `main` sin que la suite haya corrido en verde
en una máquina limpia, y que ningún PR pueda introducir una credencial o un teléfono de
cliente sin que un barrido lo marque.

### En alcance
- Workflow de GitHub Actions que corre `pytest` en cada PR y en cada push a `main`.
- Barrido de secretos y de datos personales sobre el **diff** del PR.
- Documentación del gate en `CLAUDE.md`.

### Fuera de alcance
- Despliegue continuo. Railway ya auto-despliega desde `main` y **apagarlo es gate del
  owner**; este plan no lo toca.
- Cobertura mínima obligatoria como gate bloqueante. Se **mide y se reporta**, no se
  bloquea: convertir 80 % en gate duro sin haber medido primero rompería todos los PR el
  primer día. Se decide con el número delante, en T0.3.
- Linters nuevos (ruff, black). Introducirlos ahora generaría cientos de hallazgos sobre
  código que funciona. Merecen su propio plan.

### Criterios de éxito (medibles)

| # | Criterio | Cómo se mide |
|---|---|---|
| CE1 | El workflow existe y corre | `gh run list` muestra al menos una ejecución del workflow |
| CE2 | El workflow **falla** cuando debe | Se introduce un test que falla a propósito en una rama de prueba; el check queda en rojo. **Verificación en las dos direcciones**: un CI que solo se ha visto en verde no está probado |
| CE3 | El número de tests es visible en el log | El resumen `357 passed` aparece en la salida, no solo los puntos |
| CE4 | El barrido de secretos encuentra un positivo conocido | Se le da a probar una cadena con la forma de un token; la marca. Y no marca un negativo conocido (base64 de una imagen) |
| CE5 | El workflow no consume la cuota de Google | Ningún test toca red: la suite ya corre con `conftest.py` que sustituye los clientes |
| CE6 | Tiempo de la corrida < 5 min | Log del workflow |
| CE7 | Baseline sin regresiones | `python -m pytest tests/` → ≥ 357 passed |

---

## 3. TAREAS

> **Formato blueprint.** Cada tarea es autocontenida: un subagente de Opus en sesión fría la
> ejecuta leyendo solo su bloque.

### T0.0 — Tarea Cero: rama, respaldo y baseline *(bloquea todo)*

**Depende de:** nada. **Bloquea a:** T0.1–T0.3.

**Contexto autocontenido.** El proyecto es `C:\Users\PC 1\PanelNioval`, panel Flask sobre
Google Sheets. `main` tiene auto-deploy a Railway y a Vultr: **nunca se trabaja ahí**.

**Qué hacer.**
1. `git checkout main && git pull` y crear `ci/pytest-en-cada-pr`.
2. `python tools/respaldar_hojas.py docs/auditoria/respaldos/2026-08-28`. Aunque este plan no
   escribe en Sheets, la regla del entorno no admite excepciones por criterio propio.
   **Confirmar que los archivos existen en disco antes de seguir**, listándolos con tamaño.
3. Registrar el baseline: `python -m pytest tests/` (**sin `-q`**: `pytest.ini` ya lo trae y
   el segundo lo vuelve `-qq`, que oculta el número). Anotar el número exacto.
4. Comprobar el estado de partida: `ls -d .github` debe fallar. Si ya existe, este plan
   cambia de "crear" a "auditar" y se documenta.

**Criterio de cierre.** Rama creada, respaldo listado con tamaño > 0, baseline anotado en la
tabla PROGRESO.

---

### T0.1 — Workflow de tests en cada PR

**Depende de:** T0.0.

**Contexto autocontenido.** No existe `.github/`. El repo es Python 3.11; las dependencias
del panel están en `requirements.txt` y las de test en `requirements-dev.txt` (que además
trae selenium y demás runtime de `envio_catalogo.py`, no instalado en el contenedor del
panel). `pytest.ini` ancla el rootdir al proyecto y trae `addopts = -q`.

`tests/conftest.py` define la fixture `entorno`, que **sustituye los clientes externos**;
por eso la suite no necesita credenciales de Google ni de Telegram. Esto hay que
**verificarlo, no suponerlo**: el workflow no debe recibir ningún secreto.

**Qué hacer.**
1. Crear `.github/workflows/tests.yml`:
   - Dispara en `pull_request` contra `main` y en `push` a `main`.
   - `runs-on: ubuntu-latest`, Python 3.11, caché de pip.
   - Instala `requirements.txt` y `requirements-dev.txt`.
   - Corre `python -m pytest tests/ -p no:cacheprovider` — **sin `-q` adicional**, para que
     el resumen con el número aparezca en el log (CE3).
   - Publica el resumen en el `$GITHUB_STEP_SUMMARY`.
2. Fijar `PANEL_AUTH_DESACTIVADA=1` en el entorno del job **solo si la suite lo exige**.
   Comprobar primero: `conftest.py` ya lo hace por su cuenta. Añadir una variable que no
   hace falta es superficie de riesgo gratuita.
3. **No** dar al workflow ningún secreto del repositorio. Si algún test los pide, el test
   está mal aislado y se corrige el test, no el workflow.

**Verificación — es el corazón de la tarea (CE2).**
- Abrir un PR de prueba con **un test que falla a propósito** y confirmar que el check queda
  **en rojo**. Después quitarlo y confirmar que queda en verde.
- Un CI que solo se ha visto en verde no está probado: la regla del entorno sobre barridos
  en las dos direcciones aplica igual a los gates.

**Gate.** `code-reviewer`. `security-reviewer` porque el workflow define permisos y podría
exponer secretos: verificar `permissions: contents: read` explícito y que no hay
`pull_request_target`.

---

### T0.2 — Barrido de secretos y de datos personales sobre el diff

**Depende de:** T0.1.

**Contexto autocontenido.** El proyecto tiene historia real en esto: el `TELEGRAM_TOKEN`
sigue vivo en el historial de git (~14 copias) y su rotación es gate del owner. Además,
teléfonos y nombres de clientes **no se commitean**: la regla del proyecto exige enmascarar
a `+52…XXXX`. Hoy nada lo comprueba.

Dos trampas documentadas de este entorno, que este barrido debe evitar por construcción:

- **`grep` sin `-a`** trata como binario cualquier volcado con bytes raros y **suprime las
  coincidencias sin avisar de forma evidente**. Un token de Telegram quedó invisible en un
  barrido de 356 commits hasta que se repitió con `-a`.
- **El ruido por exceso engaña igual que el silencio.** Un barrido previo dio 2,179
  hallazgos de los que 2,156 eran base64 de imágenes PNG. Al filtrar ruido se usa
  **conteo absoluto** de caracteres distintos, nunca un ratio sobre la longitud: con
  alfabeto de 64 caracteres, un token largo y legítimo da ratio bajo por pura aritmética.

**Qué hacer.**
1. Añadir un job al workflow que corra **solo sobre el diff del PR** (`git diff origin/main...HEAD`),
   no sobre todo el repo: el historial ya tiene el token y bloquearía todos los PR.
2. Patrones a marcar: forma de token de Telegram, `AIza…` de Google, `sk-…`, bloques
   `PRIVATE KEY`, y teléfonos mexicanos de 10 dígitos sin enmascarar.
3. El job **avisa**, no bloquea, en su primera versión. Bloquear el día uno con patrones sin
   calibrar convierte el gate en algo que la gente aprende a saltarse.
4. **Verificación bidireccional obligatoria** (CE4): un fixture con una cadena que **debe**
   marcarse y otro con una que **no** debe marcarse (base64 de PNG). Los dos en el test.

**Salida.** `.github/workflows/tests.yml` con el job, y `tools/barrer_secretos.py` con sus
tests en `tests/test_barrido_secretos.py`.

**TDD — estos tests se escriben ANTES del script:**
- `test_marca_un_token_con_forma_de_telegram`
- `test_marca_una_clave_con_forma_de_google_api`
- `test_no_marca_base64_de_imagen_png`
- `test_no_marca_un_hash_de_commit`
- `test_marca_un_telefono_de_diez_digitos_sin_enmascarar`
- `test_no_marca_un_telefono_ya_enmascarado`

**Gate.** `security-reviewer` + `python-reviewer` + `code-reviewer` +
`silent-failure-hunter` (un barrido que se traga su propio error devuelve cero hallazgos y
parece éxito).

---

### T0.3 — Cierre: cobertura medida, documentación y PR

**Depende de:** T0.1, T0.2.

**Qué hacer.**
1. Medir la cobertura real con `pytest --cov` **una vez**, y anotar el número. Con ese dato
   se decide si 80 % es un gate realista o una aspiración; se documenta la decisión, no se
   impone a ciegas.
2. Actualizar `CLAUDE.md`: el baseline pasa a tener un mecanismo, no solo un número. Anotar
   el comando exacto (**sin `-q`**) y la ruta del workflow.
3. Actualizar `docs/RUNBOOK.md` con qué hacer cuando el check queda en rojo.
4. PR con `gh pr create --base main`. Commits convencionales en español.
5. **Gate del owner, reportado y no intentado:** activar la protección de rama en `main`
   (Settings → Branches → Require status checks). Sin eso, el check informa pero no impide
   el merge. Requiere permisos de administrador del repositorio.

**Gate de merge.** Baseline verde + reviews sin CRITICAL/HIGH abiertos + el propio workflow
en verde sobre su PR (que es la primera prueba real de que funciona).

---

## 4. TABLA DE ASIGNACIÓN DE HERRAMIENTAS POR ETAPA

| Etapa | Tarea | Herramienta asignada | Tipo | Fuente | Por qué es la mejor |
|---|---|---|---|---|---|
| A | T0.0 | `claude-mem:mem-search` | skill | claude-mem | El proyecto ya tiene observaciones sobre la trampa del `-qq`, el arranque en frío de 100 s y el barrido de 356 commits. Recuperarlas evita volver a pisarlas. |
| A | T0.0 | `Explore` | agente | built-in | Barrido de `tests/conftest.py` y `pytest.ini` para confirmar qué necesita la suite, sin quemar contexto de la sesión principal. |
| A | T0.1 | `documentation-lookup` | skill | ECC | Sintaxis **vigente** de GitHub Actions vía Context7. Las claves de `permissions` y el caché de `setup-python` han cambiado; escribirlas de memoria es cómo se generan workflows que no corren. |
| B | T0.1 | `deployment-patterns` | skill | ECC | Patrones de pipeline CI/CD, health checks y checklists de preparación para producción. |
| B | todas | `blueprint` | skill | community | Brief autocontenido por paso para ejecución en frío. Estándar de esta plantilla. |
| B | T0.1 | `deployment-engineer` | agente | catalogo-agentes | Diseño de pipelines CI/CD: es su especialidad exacta y el plan entero es un pipeline. |
| C | T0.1 | `devops-engineer` | agente | catalogo-agentes | Implementación del workflow, caché de dependencias y tiempos de ejecución. |
| C | T0.2 | `superpowers:test-driven-development` | skill | superpowers | Los seis tests del barrido se escriben antes del script: RED antes de tocar. |
| C | T0.2 | `tdd-guide` | agente | catalogo-agentes | Hace cumplir tests-primero; se suma a la skill de proceso, no la sustituye. |
| C | T0.2 | `python-pro` | agente | catalogo-agentes | El barrido es Python del stack real del proyecto. |
| C | T0.2 | `python-patterns` | skill | ECC | Idiomas Python y type hints al escribir `tools/barrer_secretos.py`. |
| C | T0.1 | `git-workflow` | skill | ECC | Convenciones de rama, commit y PR ya fijadas por el proyecto. |
| C | T0.1 | `django-build-resolver` **[OPCIONAL]** | agente | catalogo-agentes | *Condición:* si el runner falla instalando `requirements.txt`/`requirements-dev.txt` o con un `ImportError`. **El catálogo no tiene build-resolver de Flask puro**; este es el único especializado en errores de pip, Poetry e importación en Python y su parte de Django simplemente no se usa. Se prefiere al genérico `build-error-resolver`, que es de TypeScript. |
| D | T0.1–T0.2 | `code-reviewer` | agente | catalogo-agentes | Obligatorio tras escribir o modificar código. |
| D | T0.2 | `python-reviewer` | agente | catalogo-agentes | Reviewer del stack. Se **suma** al code-reviewer, no lo reemplaza. |
| D | T0.1, T0.2 | `security-reviewer` | agente | catalogo-agentes | Obligatorio: el workflow define permisos sobre el repositorio y el barrido manipula patrones de credencial. |
| D | T0.2 | `silent-failure-hunter` | agente | catalogo-agentes | Un barrido que traga su excepción devuelve cero hallazgos y **parece un éxito**. Es exactamente su especialidad. |
| D | T0.2 | `python-testing` | skill | ECC | pytest, fixtures y parametrización de los seis casos del barrido. |
| D | T0.1 | `pr-test-analyzer` | agente | catalogo-agentes | Confirma que CE2 se probó de verdad (rojo **y** verde), no solo que el YAML es válido. |
| D | T0.3 | `superpowers:verification-before-completion` | skill | superpowers | Gate final: el workflow se declara funcional con la URL de la corrida delante, no de memoria. |
| D | T0.3 | `verification-loop` | skill | ECC | Verificación de sesión completa antes del PR. |
| D | T0.3 | `production-audit` **[OPCIONAL]** | skill | community | *Condición:* si al activar la protección de rama se quiere revisar qué más falta antes de que `main` sea la única puerta a producción. |
| E | T0.3 | `github-ops` | skill | ECC | PR con historial completo, formato convencional y operación del check desde `gh`. |
| E | T0.3 | `doc-updater` | agente | catalogo-agentes | `CLAUDE.md` y RUNBOOK al día con el gate nuevo. |
| E | T0.3 | `superpowers:finishing-a-development-branch` | skill | superpowers | Decide merge / PR / cleanup con los gates puestos. |
| E | T0.3 | `claude-mem:babysit` **[OPCIONAL]** | skill | claude-mem | *Condición:* vigilar el PR hasta que el check nuevo pase, que es su primera corrida real. |
| E | T0.3 | `handoff` | skill | skills-local (ver §4.1) | Contexto comprimido para la siguiente sesión. |

**Fuentes canónicas usadas: 5 de 6** — catalogo-agentes, ECC, community, claude-mem,
superpowers, más built-in.

**Descarte explícito de claude-ads.** La suite (`ads-google`, `ads-meta`, `ads-tiktok`,
`ads-audit`, la familia `audit-*`, `copy-writer`, `creative-strategist`, `visual-designer`,
`format-adapter`, `ads-math`) opera sobre cuentas publicitarias, píxeles, creatividades y
presupuesto de medios. Este plan es un workflow de CI: **no hay sujeto publicitario sobre el
que operar**, ni siquiera para `ads-math`, que en el Plan 2 sí encaja porque allí hay un
costo por prospecto que calcular. Esta es la constancia por escrito exigida por la regla 4
de la biblioteca.

### 4.1 Nota sobre `skills-local`

El Nivel 2 de la biblioteca usa la etiqueta `skills-local`, que no es una de las 6 fuentes
canónicas. Se reporta tal cual y **no cuenta** para el mínimo de diversidad; el plan lo
cumple sin ella.

---

## 5. GATES DE VERIFICACIÓN POR TAREA

| Tarea | Tests | Reviewer del stack | code-reviewer | security-reviewer | Baseline |
|---|---|---|---|---|---|
| T0.0 | — (registra baseline) | — | — | — | ✅ anota el número |
| T0.1 | ✅ **CE2: rojo y verde comprobados** | — | ✅ | ✅ permisos del workflow | ✅ 357 passed |
| T0.2 | ✅ TDD, 6 tests + `silent-failure-hunter` | python-reviewer | ✅ | ✅ patrones de credencial | ✅ sin regresiones |
| T0.3 | ✅ suite completa + el propio workflow en verde | — | ✅ | — | ✅ verde para mergear |

---

## 6. RIESGOS Y ROLLBACK

| # | Riesgo | Prob. | Impacto | Mitigación | Rollback |
|---|---|---|---|---|---|
| R1 | La suite necesita credenciales que el runner no tiene y el check queda en rojo permanente | Media | Alto — el gate nace roto y se aprende a ignorarlo | T0.1 verifica **primero** que `conftest.py` aísla los clientes; si algún test toca red, se corrige el test, no se le dan secretos al CI | Borrar el workflow: no toca código de producto |
| R2 | El barrido de secretos marca todos los PR y se vuelve ruido | **Alta** | Medio — un gate que siempre grita no se lee | Corre **solo sobre el diff**, no sobre el historial (que ya tiene el token). Avisa, no bloquea, en su primera versión | Desactivar el job dejando el de tests |
| R3 | El barrido no encuentra lo que debe encontrar | Media | **Alto** — cero hallazgos se lee como "está limpio" | CE4 exige verificación bidireccional con fixtures: un positivo conocido y un negativo conocido | — |
| R4 | El workflow tarda tanto que estorba | Baja | Bajo | La suite corre en ~10 s en caliente; el coste real es instalar dependencias, y se cachea | Reducir el trigger a solo `pull_request` |
| R5 | Activar la protección de rama bloquea al owner en una urgencia | Baja | Medio | Es gate del owner y se le explica que puede saltarla con permisos de administrador | Desactivar la protección desde Settings |

**Rollback general.** Este plan **no toca `app.py`**. Todo su producto son archivos nuevos
bajo `.github/` y `tools/`. Revertir es borrar el workflow, y el proyecto queda exactamente
como estaba. Es el plan de menor riesgo de la tanda y por eso va primero. Si aun así hubiera
que retirarlo, los archivos se **apartan** al respaldo fechado, no se borran (regla 4 del
entorno).

---

## 7. PROGRESO

| # | Tarea | Estado | Evidencia (commit/test/PR) | Fecha |
|---|---|---|---|---|
| T0.0 | Tarea Cero: rama, respaldo y baseline | ✅ HECHA | Rama `ci/pytest-en-cada-pr` desde `main` (`393c511`). Respaldo `docs/auditoria/respaldos/2026-08-28/` con 5 XLSX + `huellas.json`, todos > 0. Baseline **314 passed** en `main`. `ls -d .github` fallaba: el plan sigue siendo "crear" | 2026-08-28 |
| T0.1 | Workflow de tests en cada PR (CE2 en las dos direcciones) | ✅ HECHA | `eedf1c8`. **CE2 probado en las dos direcciones sobre corridas reales**: PR #39 con un `assert 1 == 2` dejó el check en **ROJO** (run `33225189306`, `1 failed, 345 passed in 1.87s`); el PR real quedó en **VERDE**. CE3: el número sale en el log. CE6: **22 s**, muy por debajo de los 5 min | 2026-08-28 |
| T0.2 | Barrido de secretos y datos personales sobre el diff | ✅ HECHA | `eedf1c8` + `fe678a3`. `tools/barrer_secretos.py` con **31 tests** (cobertura 98 %). CE4 cumplido: cada regla se verificó desactivándola y su test se pone en rojo sin ella. Ruido medido sobre 15 commits reales: **11 dan cero hallazgos** | 2026-08-28 |
| T0.3 | Cierre: cobertura medida, docs y PR | ✅ HECHA | Cobertura **69 %** global (`app.py` 52 %, barrido 98 %): se reporta y **no** bloquea. `CLAUDE.md` y `docs/RUNBOOK.md` § *Cuando el check de CI sale en rojo*. PR #40 | 2026-08-28 |

**Avance del plan: 4 / 4 tareas (100 %)**

### Hallazgos de la ejecución que no estaban en el diseño

1. **El baseline de 357 no era el de `main`.** Los documentos de la tanda lo daban como
   número absoluto; `main` tiene **314** y los 357 son de `perf/gasto-places-importador`,
   que añade 43 tests. Un gate escrito «≥ 357 passed» era **inalcanzable** desde cualquier
   rama basada en `main`. Corregido en `CLAUDE.md`, en este documento y en el índice: el
   baseline es **por rama**.
2. **El diseño original del workflow tenía un fallo que lo habría dejado inútil.**
   `pytest | tee` devuelve el código de salida de `tee`, que siempre es 0: sin `pipefail`
   el check habría salido **verde con la suite en rojo**. Es justo lo que CE2 existe para
   detectar, y se detectó antes de la primera corrida.
3. **Cuatro falsos negativos del barrido, encontrados en revisión.** El peor: el filtro de
   imágenes miraba la línea entera, así que un secreto que compartiera línea con un
   data-URI desaparecía del informe — el barrido tenía su propio modo de invisibilidad.
   Los otros tres: un corte por largo de 200 se tragaba los tokens de Meta largos, el
   patrón hexadecimal era solo minúsculas, y el teléfono con lada pegada (`52` + 10
   dígitos, el formato de WhatsApp) no lo veía ningún patrón. Los cuatro llevan test que
   **falla contra el código anterior**, comprobado.
4. **El gate gritó sobre su propio PR.** La primera corrida real reportó 4 hallazgos sobre
   el archivo de tests del propio barrido. Corregido en `fe678a3`; sin eso, el mecanismo
   habría empezado su vida enseñando a ignorarlo.

### Decisiones del owner sobre este plan (2026-08-28)

**E1 · El barrido pasa a `--estricto` tras 2-3 semanas sin falsos positivos, no antes.**
Hoy avisa y no bloquea. Revisar el **2026-09-18**. Medido sobre 15 commits reales: 11 dan
cero hallazgos y los 4 restantes son justo los que tocan manejo de teléfonos. **Antes de
activarlo hay que endurecer `barrido-ok`**: con el job bloqueando, esa marca deja de
silenciar un aviso y pasa a saltarse un gate (`security-reviewer`, MEDIUM). Ya exige motivo
escrito; faltaría restringirla a `tests/` o pedir segunda aprobación.

**E2 · La cobertura se reporta y no bloquea.** Medida: **69 %** global, `app.py` 52 %,
`tools/barrer_secretos.py` 98 %. Se descartó el trinquete al 69 % porque congelaría `app.py`
justo cuando el **Plan 4 · T4.3** va a sacar 5,067 líneas de HTML: el porcentaje va a saltar
por reestructuración, no por tests nuevos, y un trinquete lo leería como mérito.
Reconsiderar **después** del Plan 4.


**Gate del owner asociado:** activar la protección de rama en `main` (requiere permisos de
administrador del repositorio). Sin ella, el check informa pero no impide el merge.
