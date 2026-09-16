# VERIFICACIÓN EN PRODUCCIÓN — Plan 1

**Tarea:** Plan 1 · T1.6 · **Fecha:** 2026-09-15/16 · **`main`:** `8bac782`
**Pregunta que responde:** el PR #42 está mergeado. ¿Lo está sirviendo el panel?

---

## 1. La respuesta, en una línea

> **Al principio no, y por una razón que nadie sabía: no existe ningún auto-deploy.** El
> invariante que repiten los cuatro planes —«el VPS auto-deploya `main`»— **es falso desde el
> 2026-08-19**, cuando se eliminó Railway. Tras desplegar a mano con autorización del owner,
> **el trabajo ESTÁ en producción y verificado**: 1,004 ciudades, las 8 regiones con sus
> conteos exactos y CE3 verde.
>
> Y la verificación destapó algo más: **el endpoint publica 8 teléfonos y 1 correo de clientes**
> en `sin_clasificar`, contradiciendo su propio docstring. **No lo introdujo este despliegue**
> —el endpoint viejo ya lo hacía— y está detrás del token, pero la promesa del código es falsa.
> Ver §10.

---

## 2. Lo que sí quedó verificado

| Comprobación | Resultado |
|---|---|
| El servidor está arriba | ✅ `/` responde |
| El gate fail-closed funciona | ✅ **HTTP 401** sin token en `/` |
| Smoke autenticado (`tools/smoke_panel.py`) | ✅ **`Todo OK ✅`, exit 0** — los 5 chequeos |
| `pytest` sobre `main` | ✅ **525 passed, 1 skipped** |

El token se leyó de `tokens-panelnioval.txt` a memoria y **no se escribió en ninguna línea de
comando ni en ninguna salida**. Es la regla del entorno y aquí importaba: una línea de comando
queda en el historial del shell y en la transcripción de la sesión.

---

## 3. Lo que NO estaba en producción — medición ANTES de desplegar

Sondeo autenticado contra `https://panelnioval.duckdns.org`:

| Ruta | Código | Qué significa |
|---|---:|---|
| `/` | 200 | el panel vive |
| `/importador` | 200 | la página existe… |
| **`/api/importador/ciudades`** | **404** | **…pero el endpoint del PR #42 NO está** |
| `/api/prospectos/ciudades` | 200 | el endpoint **viejo** sigue siendo el que responde |
| `/salud` | 404 | ⚠️ **no es síntoma**: `/salud` tampoco existe en `main` |

Y el HTML que sirve `/importador` lo confirma sin lugar a duda:

| Marcador | En producción | Qué prueba |
|---|---|---|
| `CIUDADES_MX` (el array de 293 entradas escrito a mano) | **PRESENTE** | el PR #42 lo **borró**: lo desplegado es anterior |
| `id="region-filter"` (filtro por macro-región, PR #42 T1.7) | **AUSENTE** | |
| `/api/importador/ciudades` | **AUSENTE** | |

El operador seguía viendo el array viejo: **293 entradas escritas a mano, con 50 nombres
duplicados y 9 con la abreviatura del estado pegada**. Ni las 606 de agosto, ni las 1,004 de
T1.3. **Esto es lo que el despliegue de §9 corrigió.**

---

## 4. La causa: no hay auto-deploy, y la documentación decía que sí

| Fuente | Qué decía | Realidad |
|---|---|---|
| Invariante de los 4 planes | «el VPS auto-deploya `main`» | **falso** |
| `docs/RUNBOOK.md:109` | «Railway auto-deploya `main`» | **falso desde el 2026-08-19** |
| `.github/workflows/tests.yml` (comentario) | «`main` tiene auto-deploy a Railway y a Vultr» | **falso** |
| `docs/RUNBOOK.md:476` | «~~Eliminar el servicio de Railway~~ — **HECHO** (2026-08-19)» | ✅ cierto |
| `docs/RUNBOOK.md`, «Operación en el VPS» | despliegue = `ssh` manual | ✅ **cierto, y es el único camino** |

**El RUNBOOK se contradecía a sí mismo**: afirmaba el auto-deploy de Railway 370 líneas antes
de registrar que Railway se había eliminado. `.github/workflows/` contiene **sólo** `tests.yml`;
no hay ningún workflow de despliegue.

**Comprobación empírica que cierra la duda:** el merge entró en `main` a las 02:26:52 UTC. A
las 02:38:56 UTC —**12 minutos después**— el VPS seguía sirviendo el array viejo. No es latencia.

### 4.1 Por qué nadie lo había notado

Porque **nada obligaba a mirarlo**. Desde el 2026-08-19 no se había verificado un merge contra
producción, y la creencia del auto-deploy se propagó de documento en documento sin que ningún
paso la contrastara. Es deriva documental pura: la afirmación sobrevivió al hecho que la
sostenía.

---

## 5. El smoke daba verde igualmente, y eso es un defecto del smoke

`tools/smoke_panel.py` imprimió **`Todo OK ✅`** contra un panel que **no tiene nada del PR #42**.
No es un fallo del script: comprueba `/`, `/formulario`, `/api/formulario/siguiente`,
`/api/catalogo/envios` y `/api/catalogo/worker-estado` — **ninguna ruta del importador**.

**La lección, que vale más que el incidente:** un smoke que no cubre lo que acabas de desplegar
no verifica tu despliegue; verifica que el servidor sigue encendido. Y su verde es peor que no
tener smoke, porque **da por comprobado lo que nadie comprobó**.

⚠️ El RUNBOOK ya lo advierte a partir de hoy, justo donde se lee el comando del smoke.

---

## 6. Un segundo defecto del smoke, menor pero real

En una consola Windows (cp1252) el script **revienta con `UnicodeEncodeError` en su última
línea**, al imprimir el `✅`, y **sale con código distinto de 0 aunque los 5 chequeos hayan
pasado**. El RUNBOOK manda correrlo tras cada merge; en la máquina del owner parecería fallar
siempre.

Se sortea con `PYTHONIOENCODING=utf-8`, que es como se obtuvo el `Todo OK ✅` de §2. **Queda
anotado, no corregido**: T1.6 es una tarea de verificación y tocar la herramienta sin su gate
sería colar un cambio por la puerta de atrás. Va al relevo como pendiente de T1.7.

---

## 7. Correcciones aplicadas aquí

Las dos afirmaciones falsas se corrigieron **donde viven**, no en este informe:

- `docs/RUNBOOK.md` — la línea del auto-deploy dice ahora lo contrario, con el motivo y la
  fecha; y el bloque del smoke advierte de lo que **no** cubre.
- `.github/workflows/tests.yml` — el comentario de cabecera, corregido. Se deja dicho que la
  ausencia de auto-deploy **no rebaja** el gate: `main` es lo que el operador desplegará.

**El invariante de los cuatro planes queda anotado en el relevo como FALSO.** No se reescriben
los planes: son documentos fechados, y lo que corresponde es que el relevo lo diga.

---

## 8. Qué desbloqueaba CE5, y por qué el comando del RUNBOOK no bastaba

```bash
ssh root@155.138.200.66 'cd /srv/panel/app && git pull && cd /srv/panel && docker compose up -d --build'
```

⚠️ **Bruce corre en el mismo servidor y lee las mismas hojas.** El RUNBOOK avisa de que antes de
escribir filas de prueba hay que pausar su scheduler. Este despliegue **no** escribe filas, pero
reconstruye contenedores en un servidor compartido: es una acción con consecuencias, no un
`git pull` inocuo.

⚠️ **Y el comando del RUNBOOK, tal cual, NO habría funcionado:** el repo del servidor estaba en
**HEAD desacoplado**, donde `git pull` no avanza nada. Hizo falta `checkout main` +
`merge --ff-only`. El RUNBOOK debería decirlo; queda como pendiente.

**Después del despliegue, y sólo entonces**, CE5 se cierra con:

1. El smoke → `Todo OK ✅`.
2. **La comprobación que el smoke no hace:** que `/api/importador/ciudades` responda **200**
   con **1,004** ciudades y las 8 regiones con sus conteos
   (227 / 213 / 145 / 115 / 112 / 95 / 57 / 40). El script queda listo para reejecutarse.
3. Las **3 capturas** que pide el plan, que son del owner.

---

## 9. El despliegue, ejecutado y verificado (2026-09-16)

El owner autorizó ejecutarlo. **Lo que apareció al abrir el servidor cambió el alcance:**

| Hecho | Detalle |
|---|---|
| Último despliegue real | **2026-08-24** — tres semanas antes, no «el del PR #42» |
| Commit desplegado | `51520f3` (rollback documentado) |
| Lo que salía a producción | **24 commits**, 66 archivos, 35,102 inserciones — PRs #34 a #42 |
| Estado del repo del servidor | **HEAD desacoplado** en `FETCH_HEAD`: el `git pull` del RUNBOOK **no habría funcionado** |
| `Dockerfile` | cambia (`--workers 2` → `--workers 1 --threads 4 --worker-class gthread`, ADR `2026-08-27`), así que `--build` era necesario de verdad |
| Variables nuevas | `CATALOGO_CIUDADES_FILE`, `PLACES_CACHE_FILE`, `IMPORT_ESTADO_FILE` — **las tres con valor por defecto**; ninguna obligatoria nueva |
| Alcance del compose | un solo servicio, `panel`. El `web:` que aparecía es una **red externa**, no un servicio: **Bruce no se tocó** |

**Ejecución:** `git fetch` + `checkout main` + `merge --ff-only` (`51520f3` → `8bac782`), y
`docker compose up -d --build`. Arranque limpio: gunicorn con `gthread`, **RestartCount=0**.

### Verificación post-despliegue

| Comprobación | Resultado |
|---|---|
| Smoke | ✅ **`Todo OK ✅`** |
| `/api/importador/ciudades` | ✅ **HTTP 200**, 290,869 bytes (antes: **404**) |
| Ciudades servidas | ✅ **1,004**, idéntico a `main` · `catalogo_cargado: true` |
| Las 8 regiones | ✅ **227 / 213 / 145 / 115 / 112 / 95 / 57 / 40**, suma 1,004 |
| Ciudades nuevas de T1.3 | ✅ **398 de 398** vivas. La mejor, Jalpa de Méndez, en el **#428** |
| CE3 en vivo | ✅ mínimo **14.1** (Ejutla), **ninguna en 0** |
| `clave_inegi` en la respuesta | ✅ **0 apariciones** — la decisión de T1.4 se respeta en producción |
| `factor_nioval` real | 73 valores distintos, de **0.65 a 1.102**: la hoja tiene historial y el orden se separa del catálogo **por diseño** |

**CE5: la parte automatizable, VERDE.** Faltan las **3 capturas**, que son del owner.

---

## 10. ⚠️ HALLAZGO DE PRIVACIDAD — el endpoint contradice su propio docstring

`api_importador_ciudades` promete, literalmente:

> *«Devuelve SOLO agregados por ciudad. **Ningun telefono ni nombre de contacto sale de aqui**,
> aunque el origen sea la hoja de clientes.»*

**Es falso.** De las 32 entradas de `sin_clasificar`, **9 son datos personales**:

| Qué | Cuántos | Ejemplos enmascarados |
|---|---:|---|
| Teléfonos | **8** | `614…19`, `614…90`, `526…44`, `771…45`, `558…73` |
| Correos | **1** | `Cop…@…` |
| Valores legítimos (estados, «Sin ciudad») | 23 | `Chiapas`, `Nayarit`, `San Luis`, `Sin ciudad` |

**Causa:** son celdas de la columna CIUDAD donde alguien tecleó un teléfono o un correo. El
camino de `sin_clasificar` los pasa **verbatim**, sin sanear, y `pintarSinClasificar()` los
muestra en la UI.

### 10.1 Lo que este hallazgo NO es

- **No lo introdujo este despliegue.** El endpoint **viejo** `/api/prospectos/ciudades` —que
  llevaba semanas vivo— publica exactamente los mismos 8 patrones y la misma arroba.
  Comprobado.
- **No es una fuga pública.** Sin token, el endpoint responde **401**. Es el owner viendo sus
  propios datos.
- **No es un fallo de la decisión de mostrarlos.** Que `sin_clasificar` sea visible es
  deliberado y correcto: esconderlo haría desaparecer contactos reales del ranking sin que
  nadie se entere.

### 10.2 Lo que sí es

**Una promesa falsa en el código**, y eso es lo peligroso: alguien decidirá mañana que este
endpoint es seguro para un contexto nuevo —un panel compartido, un log, una captura en un
documento— apoyándose en un docstring que no se cumple.

**Severidad: MEDIA.** No obliga a revertir el despliegue. Pero el docstring **miente hoy**, y
lo que corresponde es o sanear la salida (enmascarar lo que parezca teléfono o correo,
conservando el aviso al operador) o corregir la promesa. **Es decisión del owner**, y queda
como pendiente en el relevo.

---

---

## 11. Lo que estos hallazgos significan para el resto de la tanda

- **El riesgo de mergear a `main` era menor de lo que creíamos** — no publica nada. Pero el
  precio es el simétrico: **el trabajo no llega al operador solo**, y los Planes 4, 3 y 2 tienen
  el mismo invariante falso escrito.
- **«Mergeado» y «desplegado» son dos estados distintos en este proyecto**, y la tanda los
  trataba como uno. Cada plan que declare «en producción» necesita su paso de despliegue
  explícito.
- La **DEFINICIÓN DE TERMINADO** de la tanda exige el smoke en verde sobre el VPS. Con el smoke
  actual, **ese criterio se puede cumplir sin que nada del trabajo esté desplegado**. Es el
  criterio el que hay que endurecer, no el resultado el que hay que celebrar.
