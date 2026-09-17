# RELEVO ACTUAL — PanelNioval · tanda 2026-09-15 · **CIERRE**

> **La tanda está ejecutada: 4 / 4 planes, 34 / 34 tareas.** Lo que queda **no es trabajo de
> código**: son dos criterios que sólo se cierran con una corrida real, y son del owner.

---

## LO PRIMERO, SI LLEGAS NUEVO

**PROYECTO:** `C:\Users\PC 1\PanelNioval` · **Baseline en `main`: 1,208 passed, 2 skipped**
**Rama viva:** `perf/gasto-places-minimo` (Plan 2, **1,221 tests**) — pendiente de merge.

### 1. NO hay auto-deploy. Mergear a `main` NO publica nada.

Railway se eliminó el 2026-08-19; el VPS no tiene webhook ni workflow. **Y ese es el bug más
caro de toda la tanda**: el arreglo del conteo se mergeó el 27-ago y llegó a producción el
16-sep, de rebote. Tres semanas con el operador viendo el bug.

```bash
ssh root@155.138.200.66 'cd /srv/panel/app && git fetch origin && git checkout main && git merge --ff-only origin/main && cd /srv/panel && docker compose up -d --build'
```

⚠️ `--build` **no es opcional** (sin `tzdata` el panel no arranca) y el healthcheck vive en
`/srv/panel/docker-compose.yml`, que es una **copia**: un `git pull` no lo actualiza.

**Antes de diagnosticar cualquier síntoma del importador**, comprueba qué versión sirve el VPS:

```bash
PANEL_DASHBOARD_TOKEN=<valor> python tools/huella_despliegue.py https://panelnioval.duckdns.org
```

Exit **0** al día · **1** rancio · **2** no interpretable · **3** **no se pudo medir** — y ese 3
**no es un verde**.

### 2. 🪤 `__pycache__` viejo produce fallos falsos, y de los que asustan

`find . -name __pycache__ -exec rm -rf {} +` antes de creerte un rojo raro.

---

## 🔴 LO ÚNICO QUE QUEDA, Y ES DEL OWNER

**Una corrida real de UNA ciudad pequeña y YA TRABAJADA** cierra **tres** cosas a la vez:

| | Qué cierra | Abierto desde |
|---|---|---|
| **CE3** (Plan 3) | Que el número de la UI **sea** el de la hoja: contar filas antes, correr, contar después | **2026-08-27** |
| **CE1** (Plan 2) | La **tasa real de sin-teléfono en Google** (hoy sólo hay proxy del DENUE: 58.6 %) | T2.1 |
| **Fase 0** del ADR | Si la clave de deduplicación casa ≥ 99 % con la API New — `tools/comparar_places_new.py`, **no escribe nada**, ≈ $0.46 | T2.4 |

⚠️ **Pequeña Y ya trabajada.** Pequeña acota el gasto; ya trabajada hace que `nuevos` y
`aprobados` sean **distintos**, que es lo único que prueba que se distinguen. Una ciudad virgen
los deja iguales y la comprobación no prueba nada.

⚠️ **Respaldo de hojas ANTES** (`python tools/respaldar_hojas.py`): escribe en producción.

**Receta completa:** `docs/investigacion/2026-09-15-gate-owner-gasto-en-pesos.md`.

### Y tres cosas más que no cuestan dinero

1. **Confirmar si el tope está puesto** en el `.env` del VPS. `PLACES_MAX_LLAMADAS_CORRIDA` no
   tiene valor por defecto: si no está, **no hay freno**, y ningún endpoint lo expone.
2. **Decidir sobre la PII en `sin_clasificar`**: el endpoint publica **8 teléfonos y 1 correo**
   contra lo que promete su docstring. Tras token; no lo introdujo esta tanda.
3. **Rotar `TELEGRAM_TOKEN`** (~14 copias en el historial) y la **API key de Places**.

---

## QUÉ PASÓ, EN RESULTADOS

| Plan | |
|---|---|
| **1 · Relevancia nacional** | 606 → **1,004 municipios**. Masa ferretera **86.3 % → 93.7 %**; Sureste **65.7 % → 80.6 %**. **En producción** |
| **4 · Rediseño** | `app.py` **6,368 → 3,182**. CLS del tablero **0.1924 → 0.0358**. **En producción** |
| **3 · Bug de conteo** | **No era código**: llevaba arreglado desde agosto y **nadie lo desplegó** |
| **2 · Gasto de Places** | **No migrar** (ADR con consejo de 2 voces). Antes, 13 llamadas que compran la decisión |
| **Baseline** | 388 → **1,208** en `main` (1,221 en la rama del Plan 2) |

**Defectos reales que aparecieron verificando, no programando:**

- 🔴 **El arreglo del conteo vivió 3 semanas en `main` sin desplegarse.** `51520f3` no contenía
  `ae0e1c9`, y su `app.py` era **byte a byte** el de la reproducción de agosto.
- 🔍 **El buscador no normalizaba acentos**: `leon` no encontraba `León`. **319 de 1,004**
  inalcanzables, y el fallo era **mudo**.
- **`MAX_VARIACIONES_SIN_APORTE` no ahorra nada** — desactivarlo no cambia una sola llamada.
- **Los estados son SIETE**, no seis: `interrumpido` no estaba en la lista. Y **Telegram es un
  octavo canal**.
- El endpoint **desempataba por nombre** contra el ADR. El DENUE rellena `municipio` con
  espacios y **viajaban literales a Places**.

---

## GUARDAS NUEVAS (lo que esta tanda deja vigilando)

| | |
|---|---|
| `tools/huella_despliegue.py` | Fecha el código servido **por comportamiento**. 15 tests |
| `tools/auditar_estados_importador.py` | **COINCIDE / MIENTE** por estado, y el medidor de gasto. Modo `--contra <url>` |
| `tools/comparar_places_new.py` | La Fase 0: mide sin escribir. 13 tests |
| `tools/verificar_ab_recortes.py` | A/B de los recortes, **con la detección de pérdida demostrada** |
| `tools/medir_fuga_details.py` | La fuga de Details, con el fixture que **sí** puede descartar |

---

## DECISIONES CERRADAS (NO reabrir)

Modelo logarítmico × `factor_nioval` · HTML en `templates/`+`static/` · corte del catálogo **≥10**
· desempate por **clave INEGI** · el **75 %** del test de cobertura es **normativo** · dirección
visual **aprobada «tal cual»** · **no migrar a Places API (New)** hasta que la Fase 0 mida ≥ 99 %
de coincidencia de clave **y** ≥ 30 % de sin-teléfono · los topes **sin valor por defecto**, a
propósito.

---

## TRAMPAS (lo que costó tiempo y no está en ningún otro sitio)

- **El heredoc de bash SE COME UN BACKSLASH.** Usa `chr(92)` o escribe el archivo aparte.
- **Una sustitución que no encuentra su patrón NO da error**: devuelve el texto igual. Verifica
  en el archivo, no en el valor de retorno. Y **la misma afirmación puede estar dos veces**.
- **El stdout de Python aquí es cp1252**: `encoding="utf-8", errors="replace"` al leer salidas.
- **Un arnés de mutación tiene que restaurar en `finally`.** Uno reventó leyendo su propia
  salida y dejó `app.py` **mutado** en el árbol de trabajo.
- **La evidencia y el banco de pruebas no pueden compartir carpeta.** Pasó **dos veces**: una
  corrida de mutación sobrescribió la evidencia y estuve a punto de reportar un bug muerto.
- **CUATRO veces en esta tanda mi instrumento estaba mal antes que el código.** Selector
  inventado, clic en el `<th>`, un test que probaba el campo *ausente* creyendo probar el
  *vacío*, y un arnés que pisaba la ruta de caché y dijo «la caché no ahorra nada».
  **Antes de declarar «no funciona», comprueba que sabes mirarlo.**
- **Prueba las guardas por mutación.** Si no encuentra un positivo, su cero no vale.
- **Un escenario donde dos números coinciden por casualidad no prueba que se distingan.**
- **`.gitignore` ignora `*.json` global.** Cualquier `.json` nuevo necesita su excepción.
- **`pytest -q` oculta el resultado** (`pytest.ini` ya lo trae).
- **Las capturas de producción llevan datos de negocio.** Anonimiza **en el origen**.

---

## EL TOKEN

**No se pega en la conversación.** Vive en `tokens-panelnioval.txt` (ignorado por git). Léelo a
una variable o al entorno; **no lo imprimas**.

---

## REGLAS VIGENTES

Anclaje al iniciar cada tarea · relevo al cerrarla · **nunca trabajar en `main`** · merge sólo
con gates en verde · **desplegar es un paso aparte, y verificarlo es otro.**
