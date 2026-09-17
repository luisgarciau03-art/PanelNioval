# RELEVO ACTUAL — PanelNioval · tanda 2026-09-15

> **Archivo único que se SOBRESCRIBE al cerrar CADA tarea.** Siempre contiene el mensaje
> completo para arrancar una sesión nueva.
>
> **Estado: PLANES 1 y 4 CERRADOS Y EN PRODUCCIÓN · PLAN 3 en 8/9 (T3.7 bloqueada en CE3).** Siguiente: **Plan 2 · T2.0**.

---

Continúas **PanelNioval**. **NO empieces de cero.**

**PROYECTO:** `C:\Users\PC 1\PanelNioval`
**`main`:** **`13e2cdb`** · **0 PR abiertos** · baseline en `main`: **1,193 passed, 2 skipped**
**En la rama viva `fix/conteo-importador-reincidencia`: 1,199 passed, 2 skipped** (+6 de T3.3)
**El VPS sirve `edda166`**, que es `main` **menos el commit de documentacion del T4.8**. No hay
codigo sin desplegar: `git diff edda166..main --stat -- '*.py' '*.js' '*.css' '*.html'` da vacio.
Comprueba eso mismo antes de dar por buena cualquier afirmacion de «esta desplegado».
**RAMA A CREAR:** `perf/gasto-places-minimo`, desde `main`.

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

- **2 / 4 planes (50 %)** · **25 / 34 tareas (73.5 %)** — Plan 3 en **8 / 9**, con **T3.7 BLOQUEADA**
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

**Plan 2, Tarea T2.0 — Tarea Cero: rama, respaldo y medicion del gasto actual de Places.**
**Plan 3 cerrado en 8 / 9: T3.7 queda BLOQUEADA en CE3** (ver abajo). Es el ultimo plan.

```
ANCLA - Plan 2 Tarea T2.0 - importador nacional barato veraz profesional - avance 25/34 -
 baseline: python -m pytest tests/  -> 1,208 passed, 2 skipped
```

1. Rama `perf/gasto-places-minimo` desde `main` actualizado (ya con los planes 1, 4 y 3).
2. Baseline. Anotar el numero exacto.
3. `tools/medir_llamadas_places.py` sobre **una ciudad virgen y otra ya trabajada**, con
   desglose por tipo de llamada.
4. Respaldo a `docs/auditoria/respaldos/2026-09-15-plan2/`.
5. **Comparar contra `docs/investigacion/2026-08-28-costo-places-despues.md`.** Si los numeros
   cambiaron, los planes 1/4/3 tocaron la ruta de Places sin querer. **Eso es un hallazgo.**

**Criterio de cierre.** Dos mediciones con desglose, comparadas contra la linea de agosto.

**Insumos que el Plan 3 le deja, y que NO hay que redescubrir:**

- El `break` de `app.py` corta **reintentos**, no variaciones: **las 3 variaciones siempre
  corren** -> 3 consultas de texto por categoria, **6 por corrida**.
- Una consulta que devuelve legitimamente cero **se repite 3 veces sin backoff**: el
  `2 ** intento` solo esta en la rama `except`. Gasto pequeño pero real.
- `presupuesto_agotado` guarda lo ya pagado antes de cortar (`app.py:3509`). El plan no lo
  listaba entre las rutas que tocan contadores.

---

## 🔴 LO QUE EL PLAN 3 DEJA ABIERTO, Y ES DEL OWNER

**CE3: la corrida real.** Contar las filas de `LISTA DE CONTACTOS` antes, correr una ciudad,
contarlas despues, y comprobar que **la diferencia es exactamente el `nuevos_en_sheet` de la
UI**. Receta exacta en `docs/investigacion/2026-09-15-verificacion-produccion-plan3.md` §5.1.

Necesita tres cosas que esta maquina no tiene: **credenciales de Google**, **confirmacion del
coste** de Places, y **respaldo de hojas previo** (que tampoco se puede hacer sin credenciales).

⚠️ **La ciudad tiene que ser pequeña Y YA TRABAJADA.** Pequeña acota el gasto; ya trabajada hace
que `nuevos` y `aprobados` sean **distintos**, que es lo unico que prueba que se distinguen. Una
ciudad virgen los deja iguales y la comprobacion no prueba nada.

**Lleva bloqueado desde el 2026-08-27**, y es la razon de que exista el Plan 3 entero.

---

## LO QUE EL PLAN 3 DESCUBRIO (no reabrir)

> **La causa del «dice 20 y aparecen 10»: el arreglo se mergeo el 27-ago y nadie lo desplego.**
> El VPS sirvio `51520f3` —cuyo `app.py` es **byte a byte** el de la reproduccion de agosto—
> hasta el 16-sep, y llego a produccion como **efecto colateral** del despliegue del Plan 1.

- **H2 descartada** (la repro pasa identica en `ae0e1c9` y en `main`). **H3 no hace falta.**
- **Los estados son SIETE**, no seis: `interrumpido` (SIGTERM) no estaba en la lista. Y
  **Telegram es un octavo canal**. Los 9 escenarios COINCIDEN, en local **y contra el desplegado**.
- **Guardas nuevas:** `tools/huella_despliegue.py` (15 tests; `exit 3` = «no pude medir», que
  **no es un verde») y `tools/auditar_estados_importador.py` (modo `--contra <url>`).
- **Este plan no cambia nada de lo que el VPS sirve**, medido con `git diff`. No hay que desplegar.

**Deuda anotada:** `app.py:3238` devuelve `len(nuevos)` — filas **enviadas** a `append_rows`, no
las que Google confirmo. **Ningun doble puede verlo** porque todos hacen
`self.escrituras += len(filas)`. No es la causa; es un fallo silencioso latente. ⚠️ Si se le
escribe test, **el doble TIENE QUE PODER MENTIR**.

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
