# GATE DEL OWNER — dirección visual del rediseño

**Tarea:** Plan 4 · T4.2 · **Fecha:** 2026-09-16
**Por qué existe este gate:** 28,582 líneas ya están escritas y **nadie del negocio ha dicho
todavía si le sirve**. El plan lo coloca aquí a propósito: *«rediseñar sin aprobación es la
forma más cara de equivocarse»*. Se pregunta **antes** de gastar esfuerzo en pulir.

---

## 1. Qué se aprueba y qué no

**Se aprueba la DIRECCIÓN VISUAL**, no el acabado. La auditoría de T4.1 dejó 4 huecos
bloqueantes; **ninguno bloquea este gate**, porque los cuatro son deuda de implementación sobre
una dirección que la auditoría respalda. Se cierran en T4.3.

**La dirección, en una frase:** *editorial / Swiss disciplinado* — denso, callado y escaneable,
sin fuente web, sin profundidad ni textura, con el color usado como **significado** y no como
adorno.

Y con un criterio declarado por encima de la estética: **«un rediseño que se vea mejor y
capture más lento es un retroceso»**.

---

## 2. Comparación antes / después

### 2.1 Aviso de método, para que la comparación se lea bien

Las capturas del PR (`docs/diseno/antes/` y `docs/diseno/despues/`) se toman **sin
credenciales de Google a propósito**, para que ninguna imagen del repo lleve datos de clientes
(riesgo R8). Su herramienta **aborta si detecta que el panel sí puede autenticarse**.

Consecuencia: **las dos caras salen con los contadores a cero**. Eso es equivalente y justo
—ceros contra ceros—, pero tiene un límite que conviene saber:

- En el **tablero** la comparación se lee bien igualmente: la diferencia es de **estructura**,
  no de cifras.
- En el **formulario** no: sin datos, la pantalla muestra su estado de error en vez del
  formulario. **Ahí no hay layout que comparar** en estas capturas.

Por eso se añaden también mis capturas de T4.0, tomadas **de producción real**, para que veas
lo que el operador tiene hoy delante.

### 2.2 TABLERO — el cambio más visible

| | Antes | Después |
|---|---|---|
| Tarjetas de KPI | **8, todas del mismo tamaño** (6 + 2) | **3 grandes + 5 pequeñas** |
| Tamaño de la cifra | uno solo | **tres**: 56 px · ~30 px · ~22 px |
| Color | azul en todas | **borde izquierdo por significado**: verde aprobados, rojo negados, ámbar buzón, morado marca única |
| Gráficas | sin altura reservada → la página saltaba al llegar los datos | **altura fija**, la caja existe antes del primer dato |

**Archivos:** `docs/diseno/antes/dashboard-1440.png` → `docs/diseno/despues/dashboard-1440.png`
· producción hoy: `docs/diseno/antes-2026-09-15/dashboard-1440.png`

**Lo que esto significa para ti:** hoy los ocho números pesan lo mismo, así que tu ojo no sabe
dónde ir primero. El rediseño decide por ti que **Aprobados, Llamadas y Total** son la primera
línea y el resto es desglose.

⚠️ Y ahí hay un supuesto que el propio PR anota como **no confirmado por nadie**:
*«SUPUESTO: que Aprobados es lo que el owner mira primero»*. **Si miras otra cosa primero, este
es el momento de decirlo** — cambiarlo después cuesta mucho más.

### 2.3 IMPORTADOR — de un muro a una lista con orden

| | Antes | Después |
|---|---|---|
| Las ciudades | lista plana de chips | **agrupadas por macro-región, con su conteo**: «CENTRO-SUR · 127 ciudades» |
| Orden | por prioridad | igual, y **con el número de puesto a la vista** («42. Pachuca de Soto») |
| Teclado | **ninguna alcanzable** | todas, con **una sola parada de tabulación** |
| Mientras carga | hueco vacío | **esqueleto con la forma de los chips** |
| Coste de una pulsación al filtrar | **713 ms** | **3.1 ms** |

**Archivos:** `docs/diseno/antes/importador-1440.png` → `docs/diseno/despues/importador-1440.png`
· producción hoy: `docs/diseno/antes-2026-09-15/importador-1440.png`

⚠️ **Ojo:** el rediseño se construyó cuando el catálogo tenía **606** ciudades. Hoy producción
sirve **1,004**, así que las agrupaciones son más largas de lo que muestran esas capturas.

### 2.4 FORMULARIO — la pantalla donde pasas el día

Aquí la comparación visual **no se puede hacer** con las capturas del PR (muestran el estado de
error). Lo que sí hay es la medición, que en esta superficie importa más que la imagen:

| | Antes | Después |
|---|---|---|
| **Pulsaciones para una captura completa** | **~90** | **11** |
| ¿Se puede capturar sin ratón? | **No** | **Sí** |
| Animaciones | — | **ninguna, a propósito** — registro «denso y quieto» |

**Producción hoy:** `docs/diseno/antes-2026-09-15/formulario-1440.png` (anonimizada).

---

## 3. Estados de carga — la tercera cosa que pediste

Antes había **uno** (o funciona, o pantalla en blanco). Ahora hay **cuatro**, con tres reglas:

| Estado | Tratamiento | Regla |
|---|---|---|
| **Cargando** | esqueleto con la forma y la **altura** del contenido que viene | no se pinta si tarda menos de 200 ms, para no parpadear |
| **Vacío** | gris, borde punteado | *«no pasó nada malo»* |
| **Error** | banda roja | **siempre** con botón de reintento |
| **Parcial** | ámbar, al margen | *«lo demás cargó; esta pieza no»* |

Y una regla que merece señalarse: **«nada celebra sin verificar»** — no hay confeti ni verde de
éxito hasta que el resultado está confirmado.

**Ejemplo real, en la captura del formulario del PR:** título *«No se pudo leer la lista de
contactos»*, explicación en llano —*«suele ser un límite temporal de Google; reintenta en unos
segundos»*— y **botón de reintento con su atajo de teclado**. Eso es lo que verías hoy en vez
de una pantalla muerta.

---

## 4. Lo que la auditoría encontró mal, para que decidas informado

**No bloquean este gate**, pero tienes derecho a saberlos antes de aprobar:

| | Hueco | Efecto para ti |
|---|---|---|
| **B5** | 🔍 El buscador de ciudades **no ignora los acentos** | Tecleas `leon` y **no encuentra León**. Afecta a **319 de las 1,004 ciudades** y a 39 de las 100 más importantes. El fallo es **mudo**: la lista sale vacía y no sabes si la ciudad no está o el buscador te la esconde |
| **B4** | El desplazamiento de la página está medido **al cargar**, no **al interactuar** | Al pulsar «Buscar» en el importador aparecen cuatro bloques que empujan lo de abajo. Nadie lo ha medido |
| **B2** | El tablero y el formulario **no usan el sistema de diseño** que el propio PR construyó | No se ve hoy; se paga mañana, cuando alguien toque esas pantallas y la coherencia se rompa |
| **B3** | Tarjetas dentro de tarjetas en Mensajes | Detalle visual. Prohibido por las reglas del proyecto |

---

## 5. LAS TRES PREGUNTAS

### (a) ¿Se aprueba la dirección visual?

- **Tal cual** → T4.3 cierra los 4 huecos y el plan sigue.
- **Con ajustes menores** → dime cuáles; se aplican en T4.3 junto con los huecos.
- **Se replantea** → ⚠️ **el plan se detiene aquí.** No se sigue puliendo algo rechazado, y se
  rediseña el alcance. Es la salida cara, pero es más barata ahora que después.

### (b) ¿Alguna superficie **empeoró** respecto a la que usas hoy?

Tablero · Formulario · Importador · Ninguna.

### (c) ¿Los estados de carga transmiten lo que deben?

En concreto: cuando algo falla, ¿la pantalla te dice **qué pasó y qué hacer**, en vez de
quedarse en blanco?

---

## 6. Respuesta del owner

*(Registrada literal, sin interpretar. 2026-09-16.)*

| Pregunta | Respuesta del owner |
|---|---|
| **(a)** ¿Se aprueba la dirección visual? | **«Tal cual»** |
| **(b)** ¿Alguna superficie empeoró? | **«Ninguna»** |
| **(c)** ¿Los estados de carga transmiten? | **«Sí, transmiten bien»** |

## 6.1 Qué cierra esta respuesta, y qué NO

**Cierra:**
- **CE1 y CE2.** La dirección editorial/Swiss queda aprobada **sin ajustes**, así que no hay
  nada que reabrir en T4.3 por parte del negocio.
- El **supuesto que el PR había dejado colgando** —*«que Aprobados es lo que el owner mira
  primero»*— queda confirmado por omisión: se presentó explícitamente como el momento barato de
  cambiarlo y el owner no lo cambió. **Deja de ser supuesto.**
- Las tres superficies quedan validadas contra lo que el operador usa hoy: **ninguna empeora**.
- Los cuatro estados de carga quedan aprobados tal como están.

**NO cierra, y conviene no confundirlo:**
- **No es una aprobación del acabado.** Los 4 huecos bloqueantes de T4.1 siguen vivos y
  **bloquean el merge**, no el gate. Se cierran en T4.3.
- **No es una validación de la jornada del operador.** El gate se resolvió sobre capturas y
  mediciones, no sobre un turno real de trabajo. El gate de `ux-researcher` en T4.1 lo dejó
  dicho: *«cumple el encargo» no es lo mismo que «validado para las repeticiones diarias»*.
- **No valida el importador a 1,004 ciudades.** Lo aprobado se construyó con 606, y las
  capturas lo muestran así.

## 6.2 Vía libre para T4.3

Con la dirección aprobada y sin ajustes pedidos, **T4.3 arranca con el alcance ya conocido**:
los 4 bloqueantes de T4.1, sin nada añadido por el negocio.

**Prioridad sugerida, por daño al operador:**

1. **B5** — el buscador y los acentos. Es el único que le cuesta algo **hoy, en cada uso**, y
   el arreglo es una función de normalización que el proyecto ya tiene escrita en Python.
2. **B4** — medir el CLS de interacción. Sin ese número, CE6 no se puede firmar.
3. **B2** — que el tablero y el formulario usen el sistema. Es el más grande y el que menos se
   ve; también el que más cuesta si se deja.
4. **B3** — quitar la sombra de la tarjeta anidada. Minutos.
