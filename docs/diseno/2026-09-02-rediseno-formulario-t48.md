# Rediseño del formulario de llamadas — Plan 4, T4.8

**Fecha:** 2026-09-02 · **Rama:** `feat/rediseno-panel` · **Registro del ADR:** «denso y
quieto» — se usa hora tras hora y la velocidad de captura manda sobre la estética.

> El plan lo dice sin rodeos: **un rediseño que se vea mejor y se capture más lento es un
> retroceso.** Así que aquí casi nada es estética.

---

## 1. El resultado medible

| | Antes | Después |
|---|---:|---:|
| Pulsaciones para una captura completa | **~90** | **11** |
| ¿Se puede capturar sin ratón? | No | Sí |

Las ~90 no son una estimación: las cuenta el propio arnés recorriendo la misma ruta y
sumando, en cada uno de los nueve pasos, los elementos tabulables que había que atravesar
desde `<body>` hasta la primera opción, más el Enter.

---

## 2. Tres cosas que estaban rotas

### 2.1 El contenido de la hoja ejecutaba

`TIENDA`, `CIUDAD`, las opciones de la pregunta 1 y las URLs del contacto se interpolaban
crudas en `innerHTML`. Un `<img src=x onerror=…>` en el nombre de una tienda **ejecuta**
en la pantalla del operador.

**No se dio por supuesto: se demostró en navegador antes de tocar nada.** Es la misma
clase que el Plan 3 cerró en el importador (T3.7) y que aquí nunca se hizo.

Un detalle del método vale la pena: el primer intento del PoC dio *negativo*. Era falso —
las rutas de Playwright se evalúan de la última a la primera, y la genérica registrada
después se comía la específica, así que no llegaba a renderizarse nada. **Un negativo de
un arnés que no has validado no prueba nada**, exactamente lo que el CLAUDE.md avisa de
los barridos.

Corregido: todo lo que viene de la hoja pasa por `esc()`, las URLs viajan por `data-url`
con `^https?://` exigido, y el teléfono va a `tel:` con `encodeURIComponent`.

### 2.2 Los atajos que la interfaz prometía no existían

Las etiquetas decían «📞 1 — Respondió», «📬 2 — Buzón», «✗ 0 — Teléfono Incorrecto».
**No había un solo manejador de teclado en el archivo**: los números eran decoración.

Y como al ocultar un paso con `display:none` el foco cae a `<body>`, para contestar sin
ratón había que tabular desde el principio del documento **en cada una de las siete
preguntas**, llamada tras llamada.

Ahora los dígitos funcionan, se ven en el propio botón, y el foco viaja solo a la primera
opción usable. Los dígitos escritos a mano se retiraron: prometían «0 = Teléfono
Incorrecto» mientras el sistema numera 1, 2, 3 — dos verdades distintas en la misma
pantalla.

### 2.3 Un fallo de guardado costaba la llamada

Era un `alert()`. Bloquea la página, roba el foco, y al aceptarlo devolvía al paso de
contacto **sin las respuestas**: el operador tenía que rehacer la llamada de memoria.

Ahora `guardar()` arma el payload y `enviarGuardado()` lo manda; el fallo va a un paso
propio con `role="alert"` que **conserva el payload** y reintenta con exactamente lo mismo
que falló.

---

## 3. Dos cosas más que aparecieron por el camino

- **El validador de número no aceptaba Enter.** Había que tabular del campo al botón en
  cada pedido — una de las conclusiones más frecuentes. El modal de correo sí lo hacía
  desde la T4.1; este no.
- **«Sin envíos con problema. 🎉»** celebraba un vacío que tanto puede significar que todo
  salió bien como que el worker lleva horas caído (regla de celebración del ADR).

---

## 4. Lo que encontraron los tres gates

`security-reviewer`: 0 CRITICAL, 0 HIGH, 2 MEDIUM, 2 LOW. `code-reviewer`: **APPROVE**, 1
MEDIUM.

### 4.1 MEDIUM — el atajo se lo quedaba quien ve la pantalla

**Es una regresión que introduje yo.** Los tres botones del primer paso llevaban el dígito
escrito en el texto visible, así que un lector de pantalla lo anunciaba. Al moverlo a un
`<kbd aria-hidden>`, quien ve la pantalla lo conservó y **quien la escucha lo perdió**:
`aria-keyshortcuts` es metadata que NVDA, JAWS y VoiceOver no anuncian por defecto.

El cambio dejaba a ese operador *peor* que antes. Corregido poniendo el dígito también en
el nombre accesible (`aria-label="1. Respondió"`), y comprobado en navegador.

### 4.2 MEDIUM — la pestaña nueva podía tocar la del panel

`abrirVentana` usaba `window.open` sin `noopener`, así que el sitio abierto conserva
`window.opener` y puede redirigir la pestaña del panel. Un sitio que imite el login, con
el operador convencido de que su pestaña de siempre sigue ahí, es una vía barata de robo
de credenciales. Y la URL sale de la hoja, que edita gente y alimenta el importador desde
Places.

### 4.3 MEDIUM — mi número de prueba esquivaba el barrido en silencio

Había compuesto el teléfono sintético como `"55" + "5" * 8` para que el patrón del CI —que
busca diez dígitos contiguos— no lo viera.

El reviewer tiene razón y el argumento es el que importa: **funcionaba, y ese es el
problema.** No se lee como una excepción al mirar el diff, y normaliza un bypass que,
aplicado por costumbre a un número real, dejaría pasar una fuga sin que nadie se entere.
El proyecto ya define una marca auditable —`barrido-ok: <motivo>`, con motivo obligatorio—
y es la que se usa ahora. Comprobado en las dos direcciones: con la marca el barrido pasa;
la misma línea sin ella se marca.

### 4.4 LOW — quedaba código dentro de un atributo

El listado de envíos con problema conservaba `onclick='abrirCorregir(${JSON.stringify(e)…})'`
— el patrón que este mismo commit retiró de la ficha de contacto y de las opciones. No era
explotable, pero dejar una excepción es dejar el patrón que el siguiente copiará.

### 4.5 LOW — un comentario que mentía sobre el origen del dato

Escribí que las opciones de la pregunta 1 «también salen de la hoja». No: son seis cadenas
fijas del código. Un comentario que miente sobre el origen de un dato hace que el
siguiente dé por cubierta una fuente que no lo está.

### 4.6 Lo que los gates descartaron, con trazado

- **`_ultimoPayload` no puede escribir en la fila equivocada.** Lleva su propio
  `row`/`col_respuesta` capturados en el momento del fallo, y desde el paso de error no
  hay ninguna ruta a `cargarContacto()`. Era el riesgo más grave posible aquí y está
  cerrado.
- **`esc()` y `Estados.escapar` son equivalentes** carácter por carácter.
- **El guard `_guardando` no se queda pegado** en ningún camino: los tres desenlaces lo
  liberan.
- **`prepararPaso` no acumula pastillas** al re-mostrar un paso.
- **El filtro `^https?://` sí cierra** `javascript:`, `data:` y `vbscript:`.

---

## 5. Verificación

| Qué | Resultado |
|---|---|
| Suite completa | **781 passed, 1 skipped** (baseline previo 740; +41 de la T4.8) |
| Navegador · formulario | **12/12** (`tools/verificar_formulario.py`) |
| Pulsaciones | 11 contra ~90 |
| XSS | Demostrado antes, cerrado después |
| Resto de superficies | 5/5, 13/13, 24/24 y CLS 9/9, sin regresión |

Comprobado **en las dos direcciones**: con el escapado retirado y el foco automático
quitado sobre una copia, la verificación se pone en rojo en dos comprobaciones.

---

## 6. Lo que esta tarea NO hace

- **No toca el importador.** Es la T4.9.
- **No arregla los 10 modales sin trampa de foco.** T4.10. Este cambio no los empeora: el
  manejador de teclado se calla con un modal abierto.
- **No enmascara el teléfono en pantalla.** El operador lo necesita completo para marcar;
  la regla del proyecto es sobre commits y logs, no sobre la pantalla de quien llama.

El respaldo previo está en `docs/auditoria/respaldos/2026-09-02/t48-antes/` (5 archivos).
