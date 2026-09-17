# RELEVO ACTUAL — PanelNioval · tanda 2026-09-15

> **Archivo único que se SOBRESCRIBE al cerrar CADA tarea.** Siempre contiene el mensaje
> completo para arrancar una sesión nueva.
>
> **Estado: ✅ PLANES 1 y 4 CERRADOS Y EN PRODUCCIÓN.** Siguiente: **Plan 3 · T3.0**.

---

Continúas **PanelNioval**. **NO empieces de cero.**

**PROYECTO:** `C:\Users\PC 1\PanelNioval`
**`main`:** **`13e2cdb`** · **0 PR abiertos** · baseline en `main`: **1,193 passed, 2 skipped**
**En la rama viva `fix/conteo-importador-reincidencia`: 1,199 passed, 2 skipped** (+6 de T3.3)
**El VPS sirve `edda166`**, que es `main` **menos el commit de documentacion del T4.8**. No hay
codigo sin desplegar: `git diff edda166..main --stat -- '*.py' '*.js' '*.css' '*.html'` da vacio.
Comprueba eso mismo antes de dar por buena cualquier afirmacion de «esta desplegado».
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

- **2 / 4 planes (50 %)** · **22 / 34 tareas (64.7 %)** — Plan 3 en **5 / 9**
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

**Plan 3, Tarea T3.5 — Auditoria de las pantallas de carga: ¿cual miente?**
**T3.0, T3.1, T3.2, T3.3 y T3.4 CERRADAS.** Rama `fix/conteo-importador-reincidencia`, sin PR.

```
ANCLA - Plan 3 Tarea T3.5 - importador nacional barato veraz profesional - avance 22/34 -
 gates: a11y/ux + silent-failure-hunter - CE4 con captura de los 6 estados -
 baseline: python -m pytest tests/  -> 1,199 passed, 2 skipped
```

### 🔴 EL BUG DE CONTEO ESTA CERRADO. No se vuelve a diagnosticar ni a "arreglar".

> **Causa (CE1, con prueba directa):** el arreglo se mergeo el 27-ago y **nadie lo desplego**.
> El VPS sirvio `51520f3` —cuyo `app.py` es **byte a byte** el de la reproduccion de agosto—
> hasta el 16-sep, y llego a produccion como **efecto colateral** del despliegue del Plan 1.

`git merge-base --is-ancestor ae0e1c9 51520f3` = **falso** · `nuevos_en_sheet` = **0 apariciones**
en el `app.py` desplegado · su linea 4918 rotulaba `encontrados` como **«Guardados en Google
Sheets»**, que es el sintoma literal. **H2 descartada** (la repro pasa identica en `ae0e1c9` y en
`main`). **H3 no hace falta.**

**T3.3/T3.4 entregaron la guarda que faltaba**, que no era de conteo —hay 80 tests vigilandolo—
sino **de despliegue rancio**: `tools/huella_despliegue.py` con `veredicto()` pura + 6 tests
probados **por mutacion**, y la seccion nueva del RUNBOOK «Como saber que version sirve el VPS».

### Lo que T3.5 tiene que hacer

Los **seis estados** del importador: reposo, corriendo, completado, detenido, error y
**`presupuesto_agotado`**. Cazar el que **afirme algo que no es** — no el que sea feo (eso era
Plan 4). Capturar cada uno. **CE4.**

**Tres pistas que ya estan sobre la mesa, no hay que buscarlas:**

1. **Telegram es un SEPTIMO canal de estado** que el plan no cuenta entre los seis de la UI. Y
   claude-mem tiene dos hallazgos de agosto sin verificar hoy: **#17575** «Completado» enviado en
   corridas **canceladas**, y **#17826** «❌ Importador FALLÓ» cuando solo se alcanzo el **tope de
   gasto** — un corte por tope **no es un fallo**.
2. **`presupuesto_agotado`** (`app.py:3509`) no estaba en la lista de rutas del plan y si toca
   los contadores. Merece su propio escenario.
3. **`_estado_catalogo`** (`app.py:895-897`) es cache de proceso que **no se invalida**: un fallo
   transitorio al arrancar serviria `catalogo_cargado: false` hasta el reinicio.

### Deuda anotada que NO bloquea T3.5

`app.py:3238` devuelve `len(nuevos)` — filas **enviadas** a `append_rows`, no las que Google
confirmo (`updates.updatedRows` se tira sin mirarlo). **Ningun doble puede verlo**, porque todos
hacen `self.escrituras += len(filas)`. No es la causa del sintoma; es un fallo silencioso
latente. ⚠️ Si se le escribe test, **el doble TIENE QUE PODER MENTIR**.

⚠️ **T3.7 sigue necesitando la corrida real**, con **respaldo de hojas antes** — y esta maquina
**no tiene credenciales de Google**. Es el gate CE1 que agosto dejo abierto y nunca se cerro.

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
