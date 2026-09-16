# RELEVO ACTUAL — PanelNioval · tanda 2026-09-15

> **Archivo único que se SOBRESCRIBE al cerrar CADA tarea.** Siempre contiene el mensaje
> completo para arrancar una sesión nueva.
>
> **Estado: Plan 1 CERRADO · Plan 4 en T4.0-T4.6 · ✅ LOS TRES PR MERGEADOS.** Siguiente: **T4.7**.

---

Continúas **PanelNioval**. **NO empieces de cero.** El diseño está hecho, el Plan 1 cerrado y
**los tres PR que llevaban meses abiertos —#42, #43 y #44— están en `main`.**

**PROYECTO:** `C:\Users\PC 1\PanelNioval`
**`main`:** **`ba1390f`** · **0 PR abiertos** · baseline **1,193 passed, 2 skipped**
**RAMA:** `feat/plan4-cierre-t46` (documentación de T4.6, sin mergear).

---

## ⚠️ LO QUE HAY QUE SABER ANTES DE TOCAR NADA

### 1. NO hay auto-deploy. Mergear a `main` NO publica nada.

Railway se eliminó el **2026-08-19**; el VPS de Vultr no tiene webhook ni workflow. Costó el
diagnóstico entero de T1.6. **«Mergeado» y «desplegado» son dos estados distintos aquí.**

```bash
ssh root@155.138.200.66 'cd /srv/panel/app && git fetch origin && git checkout main && git merge --ff-only origin/main && cd /srv/panel && docker compose up -d --build'
```

⚠️ El comando del RUNBOOK llevaba `git pull` y **no funcionaba**: el repo del servidor estaba
en HEAD desacoplado. Ya corregido. **Verifica siempre el commit servido después.**

### 2. En el VPS corre `8bac782` — sólo el Plan 1

**El rediseño y el endurecimiento están en `main` pero el operador NO los ve.** Eso es
exactamente lo que hace **T4.7**.

### 3. El smoke puede dar `Todo OK ✅` con el despliegue a medias

No cubre **ninguna** ruta del importador. Verifica aparte lo que hayas desplegado.

### 4. 🪤 `__pycache__` viejo produce fallos falsos, y de los que asustan

Un gate se topó con uno que **parecía una regresión de seguridad** (`inspect.getsource`
devolviendo un cuerpo distinto al del disco). Antes de creerte un rojo raro tras cambiar de
rama: `find . -name __pycache__ -exec rm -rf {} +`.

---

## AVANCE

- **Global: 1 / 4 planes (25 %)** · Tareas **15 / 34 (44.1 %)** · **Plan 4 en 7/12**
- **Los tres PR en `main`.** La tanda de **agosto** quedó en **53/53 (100 %), 6 de 6 planes**.

---

## LO QUE SE CERRÓ, EN RESULTADOS

| | |
|---|---|
| **Plan 1** | 606 → **1,004 municipios**. Masa ferretera nacional **86.3 % → 93.7 %**; Sureste **65.7 % → 80.6 %**. En producción y verificado |
| **PR #43** (rediseño) | `app.py` **6,368 → 3,182 líneas**. HTML y JS en `templates/` y `static/` |
| **PR #44** (endurecimiento) | Rate limiting, escape de fórmulas, zona horaria, healthcheck, cierre ante `SIGTERM` |
| **Baseline** | 388 → 482 → 491 → 525 → 955 → **1,193** |
| **Gates** | ~20, **ninguno con CRITICAL ni HIGH** |

**Defectos reales encontrados verificando, no programando:**

- 🔍 **El buscador de ciudades no normalizaba acentos**: `leon` no encontraba `León`. **319 de
  1,004** inalcanzables, y el fallo era **mudo**. Corregido y verificado con Node.
- 🔴 **La rama del PR #43 tenía la suite en rojo desde el 4 de septiembre**, sólo en Windows: el
  sha256 del Chart.js fallaba porque `.gitattributes` no exceptuaba `.js`.
- El endpoint **desempataba por nombre** contra el ADR (103 empates, 232 ciudades).
- El DENUE rellena `municipio` con espacios y **viajaban literales a Places**.
- **No existía auto-deploy**, y tres documentos afirmaban que sí.

---

## SIGUIENTE PASO EXACTO

**Plan 4, Tarea T4.7 — Desplegar y verificar en vivo: accesibilidad, responsive y rendimiento.**

```
ANCLA · Plan 4 Tarea T4.7 · importador nacional barato veraz profesional · avance 15/34 ·
 gates: a11y-architect + accessibility-tester · CE4, CE5, CE6 y CE8 CON MEDICIÓN ·
 baseline: python -m pytest tests/  -> 1,193 passed, 2 skipped
```

**Lo primero: desplegar.** El VPS corre `8bac782` y `main` va por `ba1390f` — el operador no ha
visto ni el rediseño ni el endurecimiento. ⚠️ **Es una acción de cara al exterior sobre un
servidor compartido con Bruce: confírmala con el owner antes de ejecutarla.**

**Datos que T4.7 ya tiene y no debe volver a generar:**

| Dato | Dónde |
|---|---|
| Línea base de CE6 (LCP/CLS del «antes») | `docs/diseno/antes-2026-09-15/metricas-base.json` |
| 9 capturas del «antes» de producción | `docs/diseno/antes-2026-09-15/` |
| CLS declarado del rediseño: 9/9 < 0.1 | `docs/diseno/2026-09-01-estados-de-carga-t45.md` |
| **CLS de interacción: 0.0000** (medido en T4.3) | `docs/diseno/2026-09-15-cierre-brecha.md` §5 |

⚠️ **El dashboard partía de CLS 0.1924** —medido por dos herramientas independientes, 0.9 % de
diferencia—. CE6 pide «no empeorar», y sobre ese número ese listón es demasiado bajo: **apunta a
bajar de 0.1**, y si no se consigue, dilo con el número delante.

---

## PENDIENTES DEL OWNER

| Asunto | Qué falta |
|---|---|
| **Desplegar** | El VPS corre `8bac782`; `main` va por `ba1390f` |
| **CE5 del Plan 1** | Falta 1 de las 3 capturas: una ciudad sin historial puntuando > 0 y no al final. Las otras dos ya están en `docs/diseno/antes-2026-09-15/importador-1440.png` |
| 🔒 **PII en `sin_clasificar`** | El endpoint publica **8 teléfonos y 1 correo** contra lo que promete su docstring. Tras token; no lo introdujo el Plan 1. O se sanea la salida conservando el aviso, o se corrige la promesa |
| 📸 **Mis capturas de T4.0** | Llevan datos de producción commiteados. Sin PII, pero el proyecto se puso una regla más estricta (`capturar_superficies.py` **aborta** si detecta credenciales). Decisión del owner |
| ☁️ **Railway** | 404 hoy, pero el historial 404 → **502 con `x-railway-fallback`** → 404 sugiere que resucitó una vez. **Confirmar en la consola si está borrado o sólo detenido** |
| 🔑 **Rotar `TELEGRAM_TOKEN`** | ~14 copias en el historial. No automatizable |
| **Gasto de Places** | Sin acceso a billing — D5 |

---

## DEUDA TÉCNICA ANOTADA (ninguna bloquea)

- **B2 parcial**: ~109 sustituciones de tokens que **cambiarían el render** de un diseño ya
  aprobado. Es decisión de diseño, no limpieza. Las 45 seguras ya están hechas.
- **Cohesión de `app.py`**: 515 líneas de concerns dispares entraron al mismo archivo. Si vuelve
  a crecer, **la palanca es extraer, no subir el tope otra vez**.
- **La sección de Ventas nunca se ha ejercitado con datos** — no hay fixture para `/api/ventas/*`.
- **Caché `_estado_catalogo`** no se invalida (insumo del Plan 3).
- `parse_monto` duplicada; imports y variables sin uso que marca `pyflakes`.

---

## DECISIONES CERRADAS (NO reabrir)

Modelo logarítmico × `factor_nioval` · HTML en `templates/`+`static/` · corte del catálogo
**≥10** · **desempate por clave INEGI**, sin publicarla en el payload · el **75 %** del test de
cobertura es **normativo**, no derivado · dirección visual **aprobada «tal cual»** por el owner ·
los tres PR se mergearon con **merge commit**, no squash ni rebase, cada uno con su motivo
medido.

---

## TRAMPAS (lo que costó tiempo y no está en ningún otro sitio)

- **El heredoc de bash SE COME UN BACKSLASH.** Usa `chr(92)` o escribe el archivo aparte.
- **`git checkout -- app.py` para deshacer una mutación se lleva lo no commiteado.**
- **El stdout de Python aquí es cp1252**: escribe con `write_text(..., encoding="utf-8")`.
- **`add_init_script` EJECUTA el string**: una flecha suelta no se llama y las métricas salen
  **0.0 sin un solo error**.
- **Las capturas de producción llevan PII.** Anonimiza **en el origen**, interceptando el
  endpoint. Y **ábrelas antes de commitear**.
- **`normalizar()` colapsa espacios y eso ESCONDE bugs.** Mira el nombre crudo.
- **Con PRs apilados, simula el método de merge ANTES de elegirlo.**
- **Prueba las guardas por mutación.** Si no puede encontrar un positivo, su cero no vale.
- **`.gitignore` ignora `*.json` global.** Cualquier `.json` nuevo necesita su excepción.
- **`pytest -q` oculta el resultado** (`pytest.ini` ya lo trae).
- **No pases rutas MSYS a Python**: usa `C:/Users/…`.
- **Las URLs del DENUE tienen trampa:** `denue_00_46_csv.zip` responde **200 con 0 bytes**.
- **La caché del INEGI ya está poblada** (`C:\Users\PC 1\.cache\inegi`): regenerar no baja 117 MB.

---

## EL TOKEN

**No se pega en la conversación.** Vive en `tokens-panelnioval.txt` (ignorado por git) como
`PANEL_DASHBOARD_TOKEN=…`. Léelo a una variable y pásalo en memoria; **no lo imprimas**.

---

## REGLAS VIGENTES

Anclaje al iniciar cada tarea · relevo al cerrarla · umbrales de relevo · **herramientas de la
tabla de asignación (no colapsar a Superpowers: son 14 de 653)** · merge sólo con gates en
verde · **nunca trabajar en `main`** · **desplegar es un paso aparte, y verificarlo es otro.**
