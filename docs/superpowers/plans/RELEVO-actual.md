# RELEVO ACTUAL — PanelNioval · tanda 2026-09-15

> **Archivo único que se SOBRESCRIBE al cerrar CADA tarea.** Siempre contiene el mensaje
> completo para arrancar una sesión nueva.
>
> **Estado: ✅ PLANES 1 y 4 CERRADOS Y EN PRODUCCIÓN.** Siguiente: **Plan 3 · T3.0**.

---

Continúas **PanelNioval**. **NO empieces de cero.**

**PROYECTO:** `C:\Users\PC 1\PanelNioval`
**`main`:** **`edda166`** · **0 PR abiertos** · baseline **1,193 passed, 2 skipped**
**El VPS sirve `edda166`:** lo desplegado y lo mergeado coinciden **por primera vez en la tanda**.
**RAMA A CREAR:** `fix/conteo-importador-reincidencia`, desde `main`.

---

## ⚠️ LO PRIMERO, QUE NO ES OBVIO

### 1. NO hay auto-deploy. Mergear a `main` NO publica nada.

Railway se eliminó el 2026-08-19; el VPS no tiene webhook ni workflow. Costó el diagnóstico
entero de T1.6. **«Mergeado» y «desplegado» son dos estados distintos aquí.**

```bash
ssh root@155.138.200.66 'cd /srv/panel/app && git fetch origin && git checkout main && git merge --ff-only origin/main && cd /srv/panel && docker compose up -d --build'
```

⚠️ **Y ese comando tampoco basta.** Dos cosas más, aprendidas en T4.7:
- **`--build` no es opcional:** sin `tzdata` el panel **no arranca**.
- **El healthcheck vive en `/srv/panel/docker-compose.yml`, que es una COPIA.** Un `git pull`
  no lo actualiza. Si cambias `despliegue/docker-compose.yml`, **cópialo a mano**.

### 2. 🪤 `__pycache__` viejo produce fallos falsos, y de los que asustan

A un gate le salió uno que **parecía una regresión de seguridad**. Antes de creerte un rojo raro
tras cambiar de rama: `find . -name __pycache__ -exec rm -rf {} +`.

### 3. Una sola muestra puede ser 15× la mediana

Un LCP dio **6,064 ms** donde la mediana de 3 era **416**. Las herramientas del repo usan
mediana de 3 por esto. **No reportes una regresión sobre una muestra suelta.**

---

## AVANCE

- **2 / 4 planes (50 %)** · **17 / 34 tareas (50 %)**
- **Planes 1 y 4 cerrados y en producción.** La tanda de **agosto** quedó en **53/53**.

---

## LO QUE ESTÁ HECHO, EN RESULTADOS

| | |
|---|---|
| **Plan 1** | 606 → **1,004 municipios**. Masa ferretera nacional **86.3 % → 93.7 %**; Sureste **65.7 % → 80.6 %** |
| **Plan 4** | `app.py` **6,368 → 3,182**; HTML y JS en `templates/`+`static/`. CLS del tablero **0.1924 → 0.0358** |
| **Plan 5** (vía PR #44) | Rate limiting, escape de fórmulas, zona horaria, healthcheck, cierre ante `SIGTERM` |
| **Baseline** | 388 → 482 → 491 → 525 → 955 → **1,193** |
| **Gates** | ~25, **ninguno con CRITICAL ni HIGH** |

**Defectos reales que aparecieron verificando, no programando:**

- 🔍 **El buscador no normalizaba acentos**: `leon` no encontraba `León`. **319 de 1,004**
  inalcanzables, y el fallo era **mudo**.
- 🔴 **La rama del PR #43 llevaba la suite en rojo desde el 4-sep**, sólo en Windows.
- El endpoint **desempataba por nombre** contra el ADR (103 empates, 232 ciudades).
- El DENUE rellena `municipio` con espacios y **viajaban literales a Places**.
- **No existía auto-deploy**, y tres documentos afirmaban que sí.

---

## SIGUIENTE PASO EXACTO

**Plan 3, Tarea T3.0 — Tarea Cero: rama, respaldo y recuperación del expediente de agosto.**

```
ANCLA · Plan 3 Tarea T3.0 · importador nacional barato veraz profesional · avance 17/34 ·
 baseline: python -m pytest tests/  -> 1,193 passed, 2 skipped
```

**El Plan 3 ataca el bug de conteo del importador.** Su T3.0 es **anti-redescubrimiento**: en
agosto se cerró un plan entero sobre exactamente este bug, y entrar sin leer ese expediente
garantiza repetir el trabajo.

1. Rama `fix/conteo-importador-reincidencia` desde `main`.
2. Baseline. **Anota el número exacto** (debe dar 1,193).
3. Leer completos: `docs/investigacion/2026-08-27-reproduccion-bugs-importador.md`,
   `docs/investigacion/2026-08-27-verificacion-plan3.md`, el ADR `2026-08-27` del estado
   compartido, y la sección «Importador de prospectos» del RUNBOOK.
4. `claude-mem:mem-search` — ⚠️ **está caído desde el 2026-09-05** (issue #2188). **Declara la
   sustitución**, como se hizo en T1.1, en vez de saltártelo en silencio.
5. **Listar los 13 defectos ya cerrados (B1–B13) + B14 y B15 con su commit.** Eso es lo que
   **NO** hay que volver a diagnosticar.
6. Respaldo a `docs/auditoria/respaldos/2026-09-15-plan3/`.

**Criterio de cierre.** Los 13 defectos listados con su commit.

**Dato que ya tienes:** `_estado_catalogo` (`app.py:895-897`) es una caché de proceso que **no
se invalida**: un fallo transitorio al arrancar serviría `catalogo_cargado: false` hasta el
reinicio. No es silencioso —el banner rojo sale— pero es candidato del Plan 3.

---

## PENDIENTES DEL OWNER

| Asunto | Qué falta |
|---|---|
| **CE5 del Plan 1** | Falta 1 de 3 capturas: una ciudad sin historial puntuando > 0 y no al final |
| 🔒 **PII en `sin_clasificar`** | El endpoint publica **8 teléfonos y 1 correo** contra lo que promete su docstring. Tras token; no lo introdujo el Plan 1 |
| 📸 **Capturas con datos de producción** | **Dos juegos** (T4.0 y T4.7). Sin PII, pero contra el estándar del propio proyecto. Las de T4.7 están apartadas en el respaldo; las de T4.0 **sí están commiteadas** |
| ☁️ **Railway** | 404 hoy, pero el historial 404 → **502 con `x-railway-fallback`** → 404 sugiere que resucitó una vez. **Confirmar en la consola: ¿borrado o sólo detenido?** |
| 🔑 **Rotar `TELEGRAM_TOKEN`** | ~14 copias en el historial |
| **Gasto de Places** | Sin acceso a billing — D5 |

---

## DEUDA TÉCNICA ANOTADA (ninguna bloquea)

- **B2 parcial**: ~109 sustituciones que **cambiarían el render** de un diseño aprobado. Los
  literales caen fuera de la escala y los `font-size` van en `em` mientras los tokens van en
  `rem`. Explicado en `docs/diseno/sistema.md` §6bis.
- **LCP del tablero ×3** (132 → 416 ms) por la extracción: 12 recursos donde antes iba en línea.
  Sigue 6× bajo el objetivo. La palanca es agrupar o precargar, **no** volver al monolito.
- **Cohesión de `app.py`**: 515 líneas de concerns dispares. Si crece, **extraer, no subir el
  tope otra vez**.
- **La sección de Ventas nunca se ha ejercitado con datos** — sin fixture para `/api/ventas/*`.
- `parse_monto` duplicada; imports y variables sin uso.

---

## DECISIONES CERRADAS (NO reabrir)

Modelo logarítmico × `factor_nioval` · HTML en `templates/`+`static/` · corte del catálogo
**≥10** · **desempate por clave INEGI**, sin publicarla · el **75 %** del test de cobertura es
**normativo** · dirección visual **aprobada «tal cual»** · los tres PR se mergearon con **merge
commit**, cada uno con su motivo medido · pila de sistema, **sin fuente web**.

---

## TRAMPAS (lo que costó tiempo y no está en ningún otro sitio)

- **El heredoc de bash SE COME UN BACKSLASH.** Usa `chr(92)` o escribe el archivo aparte.
- **`git checkout -- app.py` para deshacer una mutación se lleva lo no commiteado.**
- **El stdout de Python aquí es cp1252**: escribe con `write_text(..., encoding="utf-8")`.
- **`add_init_script` EJECUTA el string**: una flecha suelta no se llama y las métricas salen
  **0.0 sin un solo error**.
- **Las capturas de producción llevan datos de negocio.** Anonimiza **en el origen** y
  **ábrelas antes de commitear**.
- **`normalizar()` colapsa espacios y eso ESCONDE bugs.** Mira el nombre crudo.
- **Con PRs apilados, simula el método de merge ANTES de elegirlo.**
- **Prueba las guardas por mutación.** Si no encuentra un positivo, su cero no vale.
- **Tres veces en esta tanda mi instrumento estaba mal antes que el código.** Selector
  inventado, clic en el `<th>` en vez del `<button>`, y leer el DOM de un nodo ya repintado.
  **Antes de declarar «no funciona», comprueba que sabes mirarlo.**
- **`.gitignore` ignora `*.json` global.** Cualquier `.json` nuevo necesita su excepción.
- **`pytest -q` oculta el resultado** (`pytest.ini` ya lo trae).
- **No pases rutas MSYS a Python**: usa `C:/Users/…`.
- **Las URLs del DENUE tienen trampa:** `denue_00_46_csv.zip` responde **200 con 0 bytes**.
- **La caché del INEGI ya está poblada**: regenerar no baja 117 MB.

---

## EL TOKEN

**No se pega en la conversación.** Vive en `tokens-panelnioval.txt` (ignorado por git). Léelo a
una variable y pásalo en memoria; **no lo imprimas**.

---

## REGLAS VIGENTES

Anclaje al iniciar cada tarea · relevo al cerrarla · umbrales de relevo · **herramientas de la
tabla de asignación (no colapsar a Superpowers: son 14 de 653)** · merge sólo con gates en
verde · **nunca trabajar en `main`** · **desplegar es un paso aparte, y verificarlo es otro.**
