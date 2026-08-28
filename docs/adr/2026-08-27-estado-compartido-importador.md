# ADR — Estado del importador compartido entre procesos

**Fecha:** 2026-08-27 · **Estado:** ACEPTADA
**Plan:** 3 — Bug de conteo y pantallas de carga · **Tarea:** T3.5 (defecto B5)
**Decisión tomada con:** `council` (community), panel de 4 voces · **Formaliza:**
`architecture-decision-records` (ECC)

---

## Contexto

`_import_job` (`app.py`) y `_cache` (`app.py:112`) son diccionarios a nivel de módulo.
gunicorn arranca con `--workers 2`, que en su modelo pre-fork son **dos procesos del
sistema operativo sin memoria compartida**. Declarado en tres sitios:

```
Procfile:1       --workers 2
Dockerfile:17    --workers 2
nixpacks.toml:8  --workers 2
```

**Medido** (`tools/reproducir_bugs_importador.py workers`): con el trabajo corriendo en
el proceso 20460, 10 de 20 sondeos alternados cayeron en el proceso 16972 y devolvieron
`status: 'idle'`, `progreso: 0`, `encontrados: 0`.

El mismo defecto afecta a `_cache` en **16 sitios de invalidación**: `POST /api/refresh`
hace `_cache.clear()` solo en el worker que atendió esa petición; el otro sigue sirviendo
datos viejos hasta 300 s.

Y tiene una consecuencia que cuesta dinero (**B10**): el guard de
`if _import_job['status'] == 'running'` es por proceso, así que un `POST` que cae en el
worker B no ve el trabajo del worker A y **arranca una segunda importación**, con su
segunda factura de Google Places.

---

## Opciones consideradas

| Opción | Cómo | A favor | En contra |
|---|---|---|---|
| **A** | `--workers 1 --threads 4` | Un proceso: los globales vuelven a ser lo que el código ya supone. Tres líneas | Un solo proceso es un único punto de fallo |
| **B** | Estado en archivo/SQLite con lock | Sobrevive al reinicio; sirve también a `_cache` | Hay que escribir el lock bien; escribe datos personales a disco |
| **C** | Redis | La solución de libro | Un servicio más que operar y asegurar en el VPS |

El plan de trabajo llegaba con **B recomendada**. El panel la descartó.

---

## Decisión

**Opción A**, más tres piezas que el panel destapó y que A por sí sola no cubre.

### Por qué no B, que era la recomendación de partida

**1. Su principal argumento a favor es falso.** El plan sostiene que B "sobrevive a
reinicios". No sobrevive: el hilo del importador es `daemon=True` (`app.py`), así que un
reinicio del contenedor lo mata igual. B no preserva el **trabajo**, preserva el
**registro** de un trabajo que ya no corre. Un `status: 'running'` persistido cuyo hilo
está muerto no es una recuperación: es un **cerrojo**. Cambiaría "arrancan dos corridas"
por "no puede arrancar ninguna" hasta que alguien borre un archivo a mano.

**2. "El repo ya tiene el patrón" es un falso amigo.** Es cierto que
`worker_catalogo_run.py:43-44` y `app.py:3553-3586` resuelven bien el problema entre
procesos. Pero existen porque el worker del catálogo corre **en la PC del owner**, una
máquina genuinamente distinta del panel. Dentro de un solo contenedor no hay dos máquinas
que reconciliar: hay un default de plantilla que nadie eligió. Copiar el patrón importaría
su costo entero —contención, detección de huérfanos, serializar el estado en cada
actualización, reescribir 16 sitios de `_cache`— para arreglar algo que quita una bandera.

**3. Este repo ya se quemó con un lock huérfano.** Un worker cerrado con Ctrl+C dejó el
archivo puesto y bloqueó los reintentos 30 minutos sin ninguna corrida en curso
(`worker_catalogo_run.py:143-150`, y 10 tests en la suite sobre eso). Poner ese mismo
mecanismo en la ruta de lectura de una caché con 16 invalidaciones multiplica esa
superficie.

**4. Escribiría datos personales a disco.** `_import_job['resultados']` acumula filas
completas con **nombre, domicilio y teléfono** de prospectos. Las reglas del proyecto
prohíben volcarlos completos en logs, y un archivo de estado es un log con otro nombre.
Agravante: ningún endpoint lo lee — `/api/importador/estado` no lo devuelve. Sería
persistir datos personales para un campo que nadie consume.

### Por qué no C

Un segundo contenedor, su healthcheck, su política de reinicio, su modo de fallo de
conexión y su historia de respaldo, en un VPS cuyo atractivo entero es que es un solo
`docker compose up`, sin CI y con un solo operador. Coste de operación grande, ganancia
visible para el usuario: cero. Además, una evicción de Redis dejaría caer un trabajo a
media corrida en silencio.

### Por qué A, con matices

Un contenedor, un puñado de usuarios internos, tráfico bajo. **Dos procesos no compran
nada aquí**: la concurrencia nunca fue la restricción. El trabajo es I/O contra Google
(gspread y Places), donde el GIL se libera en la espera de socket, así que 4 hilos dan
*más* concurrencia real que 2 workers síncronos.

Confirmado en la documentación oficial de gunicorn, no de memoria:

> *If the 'sync' worker type is used with `threads` greater than 1, Gunicorn will
> automatically switch to the 'gthread' worker type.*

Aun así se pasa `--worker-class gthread` explícito, para que el arranque diga lo que hace.

---

## Lo que A por sí sola NO arregla, y se hace aquí

**1. `_cache` no está protegido por ningún lock.** Verificado: cero coincidencias de lock
sobre `_cache`, y `app.py:4556` lo muta desde el hilo daemon del importador a la vez que
los hilos de petición. Con `--workers 2` cada proceso era monohilo para peticiones y la
carrera era estrecha; con 4 hilos deja de ser un accidente afortunado. Se añade un lock
propio para `_cache`.

**2. Un cambio de configuración es invisible para la suite.** Este es el hallazgo más
accionable del panel: `--workers` vive en **tres** archivos y en dos rutas de despliegue
distintas (Railway y Docker/VPS). Arreglar dos y olvidar el tercero deja el bug vivo en
producción con 252 tests en verde. Se añade un **test que compara los tres** y falla si
declaran cosas distintas o si vuelven a más de un worker.

**3. El gasto es un problema de durabilidad, no de compartición.** Con un solo proceso no
pueden existir dos corridas vivas, así que B10 queda cerrado por construcción. Lo que
queda es que un reinicio a media corrida deje al operador viendo `idle`, como si nunca
hubiera pasado nada. Se persiste un registro **mínimo y sin datos personales** (estado,
contadores, PID, marca de tiempo) con el único fin de poder decir *"la corrida se
interrumpió"*. Lleva comprobación de PID vivo y **nunca bloquea** una corrida nueva: esa
es exactamente la trampa que el panel señaló en B.

---

## Consecuencias

**A favor**
- El estado vuelve a ser correcto sin tocar los 76 puntos de uso de `_import_job`/`_cache`.
- `_cache` deja de mentir en sus 16 invalidaciones.
- B10 (doble corrida, doble factura de Places) queda cerrado por construcción.
- Ningún dato personal nuevo llega a disco.

**En contra, y hay que decirlo en voz alta**
- **Un proceso es un único punto de fallo.** Un cuelgue duro tira el panel entero hasta que
  Docker lo reinicie, donde antes se caía la mitad. Para una herramienta interna de un
  puñado de usuarios es un intercambio aceptable, pero es un intercambio.
- **`--timeout 120` ahora siega el proceso entero.** El árbitro mataría el importador y la
  caché a la vez. Mitigado por `restart: unless-stopped`, que ya está en
  `despliegue/docker-compose.yml`.
- Los globales bajo 4 hilos exigen disciplina de lock. `_import_job` ya la tiene
  (`_import_lock`); `_cache` la gana aquí.

**Reversión.** Volver a `--workers 2` en los tres archivos. El resto de los cambios (lock
de `_cache`, registro de interrupción, test de consistencia) son útiles con cualquier
número de workers y no se revierten.

---

## Cómo se verifica

1. `tools/reproducir_bugs_importador.py workers` sigue documentando el defecto con **dos
   procesos** — es la prueba de que el repro detecta el problema que estamos quitando.
2. Test de consistencia de los tres archivos de despliegue.
3. Prueba real con gunicorn en el VPS (T3.8): 20 sondeos seguidos, **cero** `idle` con el
   trabajo corriendo. `gunicorn` no corre en Windows (necesita `fcntl`), así que esta
   comprobación es del VPS y queda anotada como tal.
