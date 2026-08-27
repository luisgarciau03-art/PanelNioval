# PLAN 4 — REDISEÑO PROFESIONAL DEL PANEL

**Fecha de diseño:** 2026-08-27
**Proyecto:** PanelNioval — `C:\Users\PC 1\PanelNioval`
**Superficies:** `/` (dashboard), `/formulario` (encuesta de llamadas), `/importador`
**Rama de trabajo:** `feat/rediseno-panel` (desde `main` actualizado — **NUNCA `main`**)
**Decisión del owner (2026-08-27):** las **3 superficies**, **sin cambiar de stack**
**Baseline verificado el 2026-08-27:** `python -m pytest tests/ -q` → **230 passed**, exit 0

---

## 1. DE QUÉ SE PARTE

### 1.1 El HTML vive dentro de `app.py`

Tres cadenas gigantes de Python contienen las tres superficies enteras — marcado, CSS y JS:

| Constante | Línea | Superficie |
|---|---|---|
| `HTML` | `app.py:968` | dashboard `/` |
| `FORMULARIO_HTML` | `app.py:3618` | encuesta de llamadas `/formulario` |
| `IMPORTADOR_HTML` | `app.py:4595` | importador `/importador` |

`app.py` tiene **4,948 líneas**. Las reglas globales fijan el límite en 800 y `CLAUDE.md` ya
registra la violación como mejora M2 pendiente. Las tres superficies son ~3,000 de esas
líneas. **Sacarlas no es limpieza opcional: es la condición para poder rediseñar**, porque
hoy no hay forma de tocar el CSS sin editar un literal de Python de mil líneas.

### 1.2 Qué tiene hoy la interfaz

Leyendo el CSS embebido:

- **Paleta**: `--blue:#0047CC`, `--blue2:#003399`, `--green:#00CC47`, `--orange:#e67e22`.
  Existe, es la de la marca, y está repetida a mano en las tres superficies con valores
  sueltos fuera de las variables.
- **Tipografía**: `'Segoe UI', sans-serif`. Es la pila por defecto de Windows, elegida por
  omisión, no por decisión.
- **Estados de carga**: **16 apariciones** de `class="loading"` con el mismo spinner
  genérico solo en el dashboard (`app.py:1193`, `1214`, `1221`, `1229`, `1259`, `1277`,
  `1285`, `1295`, `1307`, `1321`, `1333`, `1352`, `1372`, `1380`, `1429`, `2725`), más
  `spinner-box` en el formulario (`app.py:3682`) y el texto suelto "Cargando ciudades…"
  del importador (`app.py:4676`). El spinner **reemplaza** el contenido, así que el
  layout salta cuando llegan los datos.
- **Movimiento**: `transition:width .5s ease` en la barra de progreso y `transition:all .2s`
  en botones y chips. `transition: all` anima cualquier propiedad que cambie, incluidas las
  que fuerzan layout. No hay tokens de movimiento ni respeto a `prefers-reduced-motion`.
- **Composición**: tarjeta blanca centrada sobre degradado azul, `border-radius` uniforme,
  una sola sombra. Es el patrón de plantilla que las reglas globales del entorno prohíben
  explícitamente ("hero centrado + blob de degradado + CTA genérico").
- **Accesibilidad**: sin auditar. Hay `onclick` en `div`s (`app.py:1154`, `1158`,
  `app.py:4840`), que no son alcanzables por teclado. Contraste sin verificar.
- **Responsive**: `grid-template-columns:1fr 1fr 1fr` fijo en las stats del importador
  (`app.py:4627`); en móvil se aprieta.

### 1.3 Lo que el owner pidió

*"Necesita ese panel un rediseño profesional… agrega movimientos, display, pantallas de
carga."* Tres cosas concretas: **movimiento**, **presentación** y **estados de carga**, sobre
las tres superficies, sin cambiar de stack.

### 1.4 Relación con el Plan 3

**El Plan 3 arregla el comportamiento de las pantallas de carga; este plan les cambia el
aspecto.** Son tareas distintas sobre el mismo código:

| Plan 3 | Plan 4 |
|---|---|
| La barra refleja el progreso real y no retrocede | La barra tiene animación, ritmo y jerarquía |
| Al recargar se restaura el estado del trabajo | Lo restaurado se presenta con esqueleto, no con spinner |
| El contador dice la verdad | El contador tiene tipografía y peso visual acordes a su importancia |

**Rediseñar antes de arreglar el Plan 3 sería rediseñar sobre un blanco móvil**, y con el bug
de los dos workers ni siquiera se podría distinguir un estado de carga mal hecho de un sondeo
que cayó en el worker equivocado. Por eso este plan va al final.

---

## 2. OBJETIVO Y ALCANCE

**Objetivo.** Un panel que parezca un producto y no una utilidad interna: dirección visual
elegida a propósito, sistema de diseño con tokens, estados de carga que no salten, movimiento
que aclare el flujo, y accesibilidad verificada — todo sin salir de Flask.

### 2.1 En alcance
- Extraer las tres superficies de `app.py` a `templates/` + `static/`.
- Sistema de diseño: tokens, componentes, estados de interacción.
- Estados de carga: esqueletos por sección, sin salto de layout.
- Sistema de movimiento con tokens y `prefers-reduced-motion`.
- Rediseño de las tres superficies.
- Accesibilidad WCAG 2.2 AA, responsive y presupuesto de rendimiento.

### 2.2 Fuera de alcance
- Cambiar de stack (Vite, React). **Decisión del owner**: se queda en Flask.
- Comportamiento de los estados de carga → **Plan 3**.
- Filtro por macro-región del importador → **Plan 1** (este plan le da forma visual a lo que
  el Plan 1 construye).

### 2.3 Criterios de éxito (medibles)

| # | Criterio | Cómo se mide |
|---|---|---|
| CE1 | `app.py` baja de 800 líneas | `wc -l app.py` < 800 |
| CE2 | Cero HTML embebido en Python | Ningún `render_template_string` en `app.py` |
| CE3 | Tokens, no valores sueltos | Ningún color hex literal fuera del archivo de tokens |
| CE4 | Cero salto de layout al cargar | CLS < 0.1 medido en las tres superficies |
| CE5 | Esqueletos, no spinners | Cero apariciones de `class="loading"` con spinner genérico |
| CE6 | Movimiento sobre propiedades del compositor | Ningún `transition: all`; solo `transform`, `opacity`, `filter` |
| CE7 | `prefers-reduced-motion` respetado | Con la preferencia activa no hay movimiento no esencial |
| CE8 | Accesibilidad AA | Auditoría automática sin violaciones críticas; todo interactivo alcanzable por teclado |
| CE9 | Contraste verificado | Todo par texto/fondo cumple 4.5:1 (3:1 en texto grande) |
| CE10 | Responsive sin desborde | 320, 375, 768, 1024, 1440 px sin scroll horizontal |
| CE11 | No parece plantilla | Cumple ≥4 de las 10 cualidades requeridas por las reglas de calidad de diseño del entorno |
| CE12 | Comportamiento idéntico | Toda la funcionalidad actual sigue funcionando: baseline ≥230 passed + verificación en navegador |

**CE12 es un gate duro.** Un rediseño que rompe el formulario de llamadas destruye la
operación diaria de NIOVAL. La extracción de T4.3 es explícitamente **preservadora de
comportamiento**.

---

## 3. TAREAS

> **Formato blueprint.** Cada tarea es autocontenida.

### T4.0 — Tarea Cero: rama y **evidencia del antes** *(bloquea todo)*

**Depende de:** nada. **Bloquea a:** T4.1–T4.11.

**Contexto autocontenido.** Un rediseño sin capturas del antes no se puede evaluar ni
defender. El proyecto es `C:\Users\PC 1\PanelNioval`; `main` tiene auto-deploy.

**Qué hacer.**
1. Crear `feat/rediseno-panel` desde `main` actualizado.
2. Levantar el panel local y capturar las **tres** superficies en 320, 768 y 1440 px.
   Guardar en `docs/diseno/antes/`. Las capturas del formulario y del dashboard llevan datos
   de clientes: **anonimizar antes de commitear** o no commitearlas y dejar solo la ruta.
3. Medir el estado de partida: `wc -l app.py`, Core Web Vitals de las tres superficies,
   auditoría de accesibilidad automática. Anotar los números.
4. Registrar el baseline de tests.

**Criterio de cierre.** Capturas y métricas del antes en disco, sin datos de clientes
visibles.

---

### T4.1 — Auditoría del estado actual y ADN de marca

**Depende de:** T4.0.

**Contexto autocontenido.** NIOVAL ya tiene identidad: el logo está en Cloudinary
(`app.py:4651`) y la paleta azul/verde está en el CSS. El rediseño **parte de esa marca**, no
inventa una nueva; el owner no pidió cambiar de identidad.

**Qué hacer.**
1. Extraer el ADN visual de la marca a partir del logo y de las superficies actuales: paleta
   real, relaciones de contraste, carácter tipográfico, tono. Producir un `brand-profile`
   estructurado.
2. Auditar la interfaz actual: qué funciona, qué se lee mal, dónde se pierde el operador.
   El formulario de llamadas es la superficie de uso más intensivo — recibe la mayor
   atención.
3. Recuperar de la memoria del proyecto cualquier decisión visual previa para no
   contradecirla.

**Salida.** `docs/diseno/2026-08-27-auditoria-y-adn-marca.md` + `brand-profile.json`.

**Criterio de cierre.** Paleta con valores y ratios de contraste medidos, no estimados.

---

### T4.2 — Dirección visual (decisión, no deriva)

**Depende de:** T4.1.

**Contexto autocontenido.** Las reglas globales del entorno prohíben explícitamente el
resultado genérico: nada de rejillas de tarjetas uniformes, hero centrado con degradado, ni
"clean minimal" como dirección. Exigen **elegir una dirección concreta** y que la superficie
cumpla al menos 4 de 10 cualidades: jerarquía por contraste de escala, ritmo intencional de
espaciado, profundidad, tipografía con criterio de emparejamiento, color semántico, estados
de interacción diseñados, composición editorial o bento, textura, movimiento que aclare, y
visualización de datos como parte del sistema.

**Qué hacer.**
1. Proponer **3 direcciones** compatibles con el ADN de NIOVAL, no una. Candidatas
   razonables para un panel operativo B2B: editorial/Swiss disciplinado, bento con
   jerarquía, o luz con profundidad real.
2. Someterlas a decisión estructurada. Elegir **una** y escribir por qué se descartaron las
   otras dos.
3. Definir el sistema: escala tipográfica, escala de espaciado, elevaciones, radios, y la
   paleta semántica (qué significa el verde, qué el naranja, qué el rojo).
4. **Decisión tipográfica explícita**: `'Segoe UI'` está ahí por omisión. Si se cambia, la
   fuente se auto-hospeda (nada de peticiones a un CDN externo) y se justifica el peso extra
   contra el presupuesto de rendimiento.
5. **No** poner modo oscuro por defecto sin decidirlo: si se implementan ambos temas, los dos
   deben sentirse intencionales.

**Salida.** `docs/diseno/2026-08-27-direccion-visual.md` + `docs/adr/2026-08-27-direccion-visual-panel.md`.

**Criterio de cierre.** Dirección elegida y justificada, con las 4 cualidades objetivo
nombradas.

---

### T4.3 — Extraer el HTML de `app.py` *(refactor preservador de comportamiento)*

**Depende de:** T4.2. **Bloquea a:** T4.4–T4.9.

**Contexto autocontenido.** Es la tarea que habilita todas las demás y **la de mayor riesgo
del plan**: mueve ~3,000 líneas de las tres superficies operativas de NIOVAL. No cambia ni un
píxel: solo cambia dónde vive el código.

Estructura destino:

```
templates/
  base.html            layout, cabecera, carga de assets
  dashboard.html       de HTML (app.py:968)
  formulario.html      de FORMULARIO_HTML (app.py:3618)
  importador.html      de IMPORTADOR_HTML (app.py:4595)
static/
  css/tokens.css       tokens de diseño (T4.4)
  css/base.css
  css/componentes.css
  js/comun.js          fetch, formato, utilidades compartidas
  js/dashboard.js
  js/formulario.js
  js/importador.js
```

**Qué hacer.**
1. Mover el marcado a `templates/` y sustituir `render_template_string(X)` por
   `render_template('x.html')`.
2. Mover CSS y JS a `static/`, **sin reescribirlos todavía**. En esta tarea se copia, no se
   mejora.
3. Extraer lo compartido entre las tres superficies (helper de `fetch`, formato de números,
   escape de HTML) a `js/comun.js`. El escape existe hoy en el dashboard (`app.py:2064`) y
   **falta** en el importador: al centralizarlo se cierra esa brecha.
4. Configurar Flask para servir estáticos y verificar que el `Dockerfile` los copia — el
   `COPY . .` actual sí lo hace, pero hay que confirmarlo en un contenedor construido de
   verdad, no por lectura.
5. **Comprobar que el cambio está en el archivo**, no que la herramienta dijo "aplicado". Un
   reemplazo por patrón que no casa no lanza error: devuelve el texto igual.

**Verificación — es el corazón de la tarea.**
- `python -m pytest tests/ -q` → ≥ 230 passed.
- Las tres superficies cargan y **se ven idénticas** a las capturas de T4.0. Comparación
  visual explícita, captura contra captura.
- Recorrido funcional completo: guardar una respuesta del formulario, ordenar una tabla del
  dashboard, arrancar una búsqueda en el importador.
- `wc -l app.py` — se anota la reducción (CE1).

**Gate.** `python-reviewer` + `code-reviewer` + `refactoring-specialist`. **Commit
independiente**, sin ningún cambio visual mezclado, para poder revertirlo solo.

---

### T4.4 — Sistema de diseño: tokens y componentes

**Depende de:** T4.3.

**Qué hacer.**
1. `tokens.css` con la escala completa de la dirección de T4.2: color (semántico, no
   decorativo), tipografía, espaciado, radios, elevaciones, duraciones y curvas.
2. Componentes reutilizados por las tres superficies: botón, tarjeta, chip, recuadro de
   estadística, tabla, campo de formulario, insignia, barra de progreso.
3. **Estados de interacción diseñados**: hover, focus, active y disabled para cada elemento
   interactivo. El focus visible es requisito de accesibilidad, no adorno.
4. Sustituir todo hex literal por su token (CE3).

**Verificación.** Auditoría de consistencia visual: mismo componente igual en las tres
superficies. Ningún hex fuera de `tokens.css`.

**Gate.** `code-reviewer` + auditoría del sistema de diseño.

---

### T4.5 — Estados de carga: esqueletos en vez de spinners

**Depende de:** T4.4.

**Contexto autocontenido.** Hoy hay nueve `<div class="loading"><div class="spinner"></div>
<br>Cargando...</div>` que **sustituyen** el contenido: cuando llegan los datos, el layout
salta. Las secciones tardan lo que tarde Google Sheets, que no es poco.

**Qué hacer.**
1. Esqueleto por sección, **con la forma y el tamaño del contenido real**, para que al
   llegar los datos nada se mueva (CE4).
2. Estados por sección, no por página: el dashboard no se bloquea entero porque una tabla
   tarde.
3. Los **tres** estados que faltan hoy, además del de carga:
   - **Vacío**: "no hay contactos en esta ciudad" no es lo mismo que estar cargando.
   - **Error**: con qué falló y un botón de reintentar, no un espacio en blanco.
   - **Parcial**: cargó el dashboard pero falló una tabla.
4. Barra de progreso del importador con la granularidad que el **Plan 3 (T3.6)** ya expone.
   Si el Plan 3 aún no corrió, se implementa contra la interfaz que define y se marca la
   dependencia.
5. Un límite: por debajo de ~200 ms no se muestra esqueleto — un parpadeo se ve peor que la
   espera.

**Verificación.** CLS < 0.1 en las tres superficies con la red ralentizada. Los cuatro
estados capturados.

**Gate.** `code-reviewer` + verificación en navegador con red lenta simulada.

---

### T4.6 — Sistema de movimiento

**Depende de:** T4.4.

**Contexto autocontenido.** Hoy: `transition:all .2s` en botones y chips y
`transition:width .5s ease` en la barra. `transition: all` anima también propiedades que
fuerzan recálculo de layout. No hay tokens ni respeto a `prefers-reduced-motion`.

**Qué hacer.**
1. Tokens de movimiento: duraciones (rápida/normal/lenta) y curvas, en `tokens.css`.
2. **Solo propiedades del compositor**: `transform`, `opacity`, `filter` con moderación.
   Prohibido animar `width`, `height`, `top`, `left`, `margin`, `padding`, `font-size`.
   Fuera todo `transition: all`.
3. Movimiento que **aclare el flujo**, no que decore: entrada escalonada de filas al cargar
   una tabla, transición entre secciones que indique de dónde vienes, avance de la barra de
   progreso que se lea como avance.
4. **`prefers-reduced-motion: reduce` respetado**: sin movimiento no esencial. Es
   accesibilidad, no preferencia.
5. `will-change` solo donde haga falta y retirado al terminar.

**Verificación.** Ningún `transition: all` en el CSS. Con la preferencia de movimiento
reducido activa, nada no esencial se mueve. Sin caídas de fotogramas en el recorrido
principal.

**Gate.** `code-reviewer` + revisión específica de animaciones.

---

### T4.7 — Rediseño del dashboard `/`

**Depende de:** T4.4, T4.5, T4.6.

**Contexto autocontenido.** El dashboard (`app.py:968-3617`) tiene barra lateral con grupos
de navegación, barra superior con badge de caché y botón de actualizar, tarjetas de KPI,
tres gráficas y **once** `table-box` con controles de orden y paginación.

**Qué hacer.**
1. Jerarquía real: hoy todas las tarjetas pesan lo mismo. Lo que el owner mira primero debe
   verse primero.
2. Las tablas son el trabajo de verdad: densidad legible, encabezados fijos, orden y
   paginación con estados claros, zebra o separación que no canse.
3. Las tres gráficas como parte del sistema de diseño, no como salida por defecto de la
   librería: colores del sistema semántico, ejes y leyendas legibles, comportamiento
   responsive.
4. Navegación: los `div` con `onclick` (`app.py:1154`, `1158`) pasan a ser elementos
   alcanzables por teclado, con estado activo visible.
5. El badge de caché dice algo útil: cuándo se actualizó y qué significa.

**Verificación.** Las once tablas funcionan (orden, filtro, paginación). Captura del
antes/después. Recorrido por teclado completo.

**Gate.** `code-reviewer` + verificación funcional en navegador.

---

### T4.8 — Rediseño del formulario de llamadas `/formulario`

**Depende de:** T4.4, T4.5, T4.6.

**Contexto autocontenido.** `FORMULARIO_HTML` (`app.py:3618-4305`). Es la superficie de uso
más intensivo: se usa llamada tras llamada, durante horas. **Aquí la velocidad de captura
importa más que la belleza.** Un rediseño que se vea mejor y se capture más lento es un
retroceso.

**Qué hacer.**
1. Optimizar para el uso real: campos grandes, orden que siga el guion de la llamada,
   recorrido por teclado sin tocar el ratón, foco automático donde toca.
2. El estado de carga entre contactos (`app.py:3682`, `3941`) con esqueleto: el operador debe
   ver que viene el siguiente, no un hueco.
3. Confirmación de guardado inequívoca. En una llamada no hay tiempo de dudar si se guardó.
4. Errores de guardado visibles y con reintento: perder una respuesta capturada es perder
   una llamada.
5. Datos personales en pantalla: mantener el criterio del proyecto sobre qué se muestra
   completo y qué se enmascara.

**Verificación.** Captura completa de una llamada **solo con teclado**, cronometrada contra
el flujo actual. Si tarda más, se ajusta.

**Gate.** `code-reviewer` + `security-reviewer` (muestra datos de clientes) + verificación
funcional.

---

### T4.9 — Rediseño del importador `/importador`

**Depende de:** T4.4, T4.5, T4.6. **Coordina con:** Plan 1 (T1.7), Plan 3 (T3.6, T3.7).

**Contexto autocontenido.** `IMPORTADOR_HTML` (`app.py:4595-4947`). Es la superficie donde
convergen los cuatro planes.

**Qué hacer.**
1. Presentar los **cuatro contadores** del Plan 3 con jerarquía correcta: `nuevos_en_sheet`
   es el número grande; los otros tres, secundarios.
2. Dar forma al filtro por macro-región del Plan 1: cientos de chips necesitan agrupación,
   contador por grupo y buscador que se sienta instantáneo.
3. La consola de log (`app.py:4632`, fondo `#1a1a2e` con texto verde) es hoy lo más honesto
   de la pantalla. Conservar su función y darle forma dentro del sistema.
4. Barra de progreso con la granularidad del Plan 3 y la etiqueta de fase visible.
5. El medidor de costo del **Plan 2 (T2.6)**, si ya existe, tiene su sitio en esta pantalla.
6. Estado de cancelación y estado de presupuesto agotado, presentados como estados de primera
   clase y no como errores.

**Verificación.** Corrida completa con la UI nueva; los números coinciden con la hoja (es
CE1 del Plan 3, verificado otra vez aquí sobre la interfaz nueva).

**Gate.** `code-reviewer` + `security-reviewer` (chips con nombres de la hoja) +
verificación funcional.

---

### T4.10 — Accesibilidad, responsive y rendimiento

**Depende de:** T4.7, T4.8, T4.9.

**Qué hacer.**
1. **WCAG 2.2 AA**: auditoría automática de las tres superficies, sin violaciones críticas.
   HTML semántico (`header`, `nav`, `main`, `section`), etiquetas asociadas a cada campo,
   ARIA solo donde el elemento nativo no alcanza.
2. **Teclado**: todo lo interactivo alcanzable y operable; orden de tabulación lógico; foco
   siempre visible.
3. **Contraste**: todo par texto/fondo medido, 4.5:1 (3:1 en texto grande). Ojo con el verde
   `#00CC47` sobre blanco, que es el candidato más probable a fallar.
4. **Responsive**: 320, 375, 768, 1024, 1440 px sin desborde horizontal. La rejilla fija
   `1fr 1fr 1fr` del importador (`app.py:4627`) pasa a ser adaptativa.
5. **Rendimiento**: CSS y JS dentro de presupuesto; imágenes con dimensiones explícitas
   (el logo de Cloudinary hoy no las tiene, `app.py:4651`); fuentes auto-hospedadas con
   `font-display: swap`.

**Verificación.** Auditoría de accesibilidad con salida pegada. Capturas en los cinco anchos.
Core Web Vitals medidos contra los de T4.0.

**Gate.** `a11y-architect` + `accessibility-tester` + revisión de directrices de interfaz web.

---

### T4.11 — Cierre

**Depende de:** T4.10.

**Qué hacer.** Documentar el sistema de diseño en `docs/diseno/sistema.md` para que futuros
cambios no lo erosionen. Actualizar `CLAUDE.md` (la arquitectura cambió: ya no hay HTML en
`app.py`; M2 queda resuelta o parcialmente resuelta — decir cuál con el `wc -l` delante).
Capturas del después junto a las del antes. Commits convencionales en español. PR con
`gh pr create --base main`. Handoff.

**Gate de merge.** Baseline verde + reviews sin CRITICAL/HIGH abiertos + CE12 verificado en
navegador.

---

## 4. TABLA DE ASIGNACIÓN DE HERRAMIENTAS POR ETAPA

| Etapa | Tarea | Herramienta asignada | Tipo | Fuente | Por qué es la mejor |
|---|---|---|---|---|---|
| A | T4.1 | `ads-dna` | skill | **claude-ads** | Extractor de ADN de marca: escanea una URL y saca identidad visual, paleta, tipografía y tono a un `brand-profile.json`. NIOVAL **ya tiene** marca (logo en Cloudinary, azul/verde en el CSS); esto la formaliza en vez de inventar una nueva. Uso literal de la herramienta. |
| A | T4.1 | `ux-researcher` | agente | catalogo-agentes | Audita el uso real antes de rediseñar. El formulario de llamadas se usa horas al día: rediseñarlo sin entender su uso es apostar. |
| A | T4.1 | `claude-mem:mem-search` | skill | claude-mem | Recupera decisiones visuales previas del proyecto para no contradecirlas. |
| A | T4.1 | `claude-mem:design-is` **[OPCIONAL]** | skill | claude-mem | *Condición:* si se quiere auditar la interfaz actual contra los diez principios de Dieter Rams antes de decidir dirección. |
| A | T4.0 | `Explore` | agente | built-in | Barrido de las tres cadenas HTML para inventariar componentes repetidos sin quemar contexto. |
| A | T4.0 | `web-perf` **[OPCIONAL]** | skill | skills-local (ver nota §4.1) | *Condición:* para medir los Core Web Vitals del antes con Chrome DevTools y tener contra qué comparar. |
| B | T4.2 | `frontend-design-direction` | skill | community | Fija una dirección de diseño explícita para trabajo de UI en producción. Es la contramedida directa a la política anti-plantilla de las reglas del entorno. |
| B | T4.2 | `council` | skill | community | Elegir entre 3 direcciones visuales válidas es un tradeoff genuino: panel de 4 voces en vez de la primera que suene bien. |
| B | T4.2 | `ui-ux-pro-max` | skill | ECC | 67 estilos, 96 paletas y 57 emparejamientos tipográficos con criterio de selección: material para proponer 3 direcciones fundamentadas, no improvisadas. |
| B | T4.2 | `superpowers:brainstorming` | skill | superpowers | Explorar intención y requisitos antes de fijar el diseño. |
| B | T4.2 | `architecture-decision-records` | skill | ECC | Congela la dirección elegida y las descartadas. |
| B | todas | `blueprint` | skill | community | Brief autocontenido por paso para ejecución en frío. |
| B | T4.3 | `code-architect` | agente | catalogo-agentes | Diseña la estructura de `templates/` y `static/` analizando los patrones que ya existen en el repo, con archivos y orden de construcción concretos. |
| C | T4.3 | `refactoring-specialist` | agente | catalogo-agentes | Transformar 3,000 líneas **preservando el comportamiento** es su definición exacta. La tarea de mayor riesgo del plan. |
| C | T4.3 | `orch-refine-code` | skill | ECC | Pipeline de refactor preservador: tests verdes → reestructurar → tests verdes → review → commit con gate. La forma exacta de T4.3. |
| C | T4.4 | `design-system` | skill | ECC | Generar y auditar el sistema de diseño y revisar los cambios que tocan estilo. |
| C | T4.4, T4.7–T4.9 | `impeccable` | skill | community | Cubre jerarquía visual, carga cognitiva, estados vacíos y de error, tipografía, espaciado y micro-interacciones — el rango completo de estas cuatro tareas. |
| C | T4.4, T4.7–T4.9 | `make-interfaces-feel-better` | skill | community | Los detalles concretos de ingeniería de diseño que separan "funciona" de "se siente pulido": espaciado, bordes, sombras. Es el pedido del owner. |
| C | T4.6 | `motion-ui` | skill | ECC | Sistema de movimiento de producción con tokens, presets y reglas de rendimiento. |
| C | T4.5, T4.6 | `frontend-patterns` | skill | ECC | Patrones de estados de carga, error y vacío del lado cliente. |
| C | T4.7–T4.9 | `ui-designer` | agente | catalogo-agentes | Diseño visual, sistemas de componentes y refinamiento estético de cara al usuario. |
| C | T4.7–T4.9 | `frontend-developer` | agente | catalogo-agentes | Implementación del frontend; aquí sin framework, HTML/CSS/JS sobre plantillas Flask. |
| C | T4.7 | `dataviz` | skill | built-in | Las tres gráficas del dashboard como parte del sistema de diseño y no como salida por defecto de Chart.js: paleta accesible, ejes y leyendas legibles. |
| C | T4.3 | `python-pro` | agente | catalogo-agentes | El lado Flask de la extracción: `render_template`, configuración de estáticos. |
| D | T4.3–T4.9 | `code-reviewer` | agente | catalogo-agentes | Obligatorio tras escribir o modificar código. |
| D | T4.3 | `python-reviewer` | agente | catalogo-agentes | Reviewer del stack para el lado Flask de la extracción. |
| D | T4.8, T4.9 | `security-reviewer` | agente | catalogo-agentes | Obligatorio: el formulario muestra datos de clientes y el importador interpola nombres de la hoja en HTML. |
| D | T4.10 | `a11y-architect` | agente | catalogo-agentes | Arquitectura de accesibilidad WCAG 2.2: ARIA semántico, no parches. |
| D | T4.10 | `accessibility-tester` | agente | catalogo-agentes | Verificación de cumplimiento y soporte de tecnología asistiva; complementa al arquitecto. |
| D | T4.10 | `accessibility` | skill | ECC | Referencia WCAG 2.2 AA al implementar y al auditar. |
| D | T4.10 | `frontend-a11y` | skill | community | Etiquetado de formularios, gestión de foco y navegación por teclado: justo lo que le falta al formulario de llamadas. |
| D | T4.6 | `review-animations` | skill | skills-local (ver nota §4.1) | Revisa el código de movimiento contra un listón alto de artesanía; por defecto marca en vez de aprobar. |
| D | T4.10 | `web-design-guidelines` | skill | skills-local (ver nota §4.1) | Revisión del código de UI contra las Web Interface Guidelines. |
| D | T4.3, T4.7–T4.9 | `webapp-testing` | skill | skills-local (ver nota §4.1) | CE12 solo se verifica en navegador real: que el formulario siga guardando y las tablas sigan ordenando. |
| D | T4.10 | `browser-qa` | skill | ECC | Verificación visual e interactiva tras el despliegue. |
| D | T4.3 | `pr-test-analyzer` | agente | catalogo-agentes | ¿Los tests cubren de verdad la extracción, o solo que el módulo importa? |
| D | T4.10, T4.11 | `superpowers:verification-before-completion` | skill | superpowers | Gate final: la salida del comando delante antes de declarar nada terminado. |
| D | T4.10 | `verification-loop` | skill | ECC | Verificación de sesión completa antes del PR. |
| D | T4.11 | `ui-demo` **[OPCIONAL]** | skill | ECC | *Condición:* si el owner quiere un video de recorrido del panel nuevo para el equipo. |
| E | T4.11 | `doc-updater` | agente | catalogo-agentes | `CLAUDE.md` cambia de verdad: ya no hay HTML en `app.py`. |
| E | T4.11 | `technical-writer` | agente | catalogo-agentes | El documento del sistema de diseño tiene que ser usable por quien venga después. |
| E | T4.11 | `github-ops` | skill | ECC | PR con historial completo y formato convencional. |
| E | T4.11 | `superpowers:finishing-a-development-branch` | skill | superpowers | Decide merge / PR / cleanup con los gates puestos. |
| E | T4.11 | `content-quality-editor` **[OPCIONAL]** | agente | catalogo-agentes | *Condición:* para pulir los textos de interfaz nuevos (estados vacíos, mensajes de error) antes de publicarlos. |
| E | T4.11 | `handoff` | skill | skills-local (ver nota §4.1) | Contexto comprimido para la siguiente sesión. |

**Fuentes canónicas usadas: 6 de 6** — catalogo-agentes, ECC, claude-ads, community,
claude-mem, superpowers, más built-in.

### 4.1 Nota sobre `skills-local`

El Nivel 2 de la biblioteca usa la etiqueta `skills-local`, que no es una de las 6 fuentes
canónicas de la tabla de Fuentes. Se reporta tal cual y **no cuenta** para el mínimo de
diversidad; el plan lo cumple sin ella.

---

## 5. GATES DE VERIFICACIÓN POR TAREA

| Tarea | Tests | Reviewer del stack | code-reviewer | security-reviewer | a11y | Baseline |
|---|---|---|---|---|---|---|
| T4.0 | — (captura y mide) | — | — | — | — | ✅ anota el número |
| T4.1 | — (documental) | — | — | — | — | — |
| T4.2 | — (ADR) | — | — | — | — | — |
| T4.3 | ✅ **suite completa + comparación visual antes/después** | python-reviewer | ✅ | — | — | ✅ ≥230, gate duro |
| T4.4 | ✅ auditoría de consistencia | — | ✅ | — | — | ✅ sin regresiones |
| T4.5 | ✅ CLS < 0.1 con red lenta | — | ✅ | — | — | ✅ sin regresiones |
| T4.6 | ✅ cero `transition: all` + reduced-motion | — | ✅ | — | ✅ | ✅ sin regresiones |
| T4.7 | ✅ 11 tablas funcionando + teclado | — | ✅ | — | ✅ | ✅ sin regresiones |
| T4.8 | ✅ captura completa solo con teclado, cronometrada | — | ✅ | ✅ datos de clientes | ✅ | ✅ sin regresiones |
| T4.9 | ✅ corrida completa, números == hoja | — | ✅ | ✅ nombres de la hoja | ✅ | ✅ sin regresiones |
| T4.10 | ✅ auditoría a11y + 5 anchos + CWV | — | ✅ | — | ✅ **obligatorio** | ✅ sin regresiones |
| T4.11 | ✅ suite completa antes del merge | — | ✅ | — | — | ✅ verde para mergear |

---

## 6. RIESGOS Y ROLLBACK

| # | Riesgo | Prob. | Impacto | Mitigación | Rollback |
|---|---|---|---|---|---|
| R1 | **T4.3 rompe una superficie operativa** | Media | **Crítico** — NIOVAL deja de capturar llamadas | T4.3 es puramente preservadora: copiar, no mejorar. Commit independiente. Comparación visual captura contra captura. Suite completa | `git revert` del commit de T4.3 y solo de ese |
| R2 | El formulario nuevo es más lento de capturar | Media | **Alto** — se usa horas al día | T4.8 cronometra la captura completa solo con teclado contra el flujo actual. Si tarda más, no cierra | Revertir T4.8; el resto del rediseño sobrevive |
| R3 | El rediseño sale genérico y de plantilla | Media | Medio — no cumple lo pedido | CE11 exige nombrar y cumplir ≥4 de las 10 cualidades; T4.2 obliga a elegir dirección y descartar dos por escrito | Volver a T4.2 con el ADR como registro |
| R4 | El verde `#00CC47` sobre blanco no pasa contraste AA | **Alta** | Medio | T4.10 mide **todos** los pares. Si falla, se ajusta el tono conservando el carácter de marca y se documenta la desviación respecto al logo | Usar el verde solo sobre fondo oscuro o en elementos no textuales |
| R5 | Fuente nueva infla la carga | Media | Bajo | Auto-hospedada, subconjunto, `font-display: swap`, dentro de presupuesto. Si no cabe, se queda la pila del sistema y se documenta la decisión | Volver a la pila del sistema |
| R6 | Conflictos con Plan 1 y Plan 3 sobre el mismo importador | **Alta** | Medio | Este plan va **el último**, por eso mismo. T4.9 consume lo que 1 y 3 dejaron, no lo rehace | Rebase sobre `main` ya con 1 y 3 mergeados |
| R7 | Los estáticos no se sirven en el contenedor del VPS | Media | Alto — panel sin CSS en producción | T4.3 verifica en un contenedor **construido de verdad**, no leyendo el `Dockerfile` | Revertir T4.3; volver a `render_template_string` |
| R8 | Capturas con datos de clientes en el repo | Media | **Alto** — dato personal versionado | T4.0 obliga a anonimizar antes de commitear; se prefiere no commitear y dejar solo la ruta | Retirar al respaldo fechado y limpiar el historial con clon completo previo |

**Rollback general.** Rama `feat/rediseno-panel`, **T4.3 en commit aislado** y cada
superficie (T4.7, T4.8, T4.9) en el suyo, para poder revertir una sin perder las otras dos.
Las capturas del antes son la referencia objetiva de qué había que preservar.

---

## 7. EVALUACIÓN DE LA SUITE claude-ads

**Se evalúa y se usa.** `ads-dna` entra con uso literal en T4.1: es un extractor de ADN de
marca que produce paleta, tipografía, tono e identidad visual en un `brand-profile.json`
estructurado. NIOVAL ya tiene identidad — logo en Cloudinary, azul `#0047CC` / verde
`#00CC47` repartidos por el CSS — y el rediseño debe partir de ella, no inventar otra.
`ads-dna` formaliza esa identidad dispersa en un perfil que T4.2 y T4.4 consumen.

`visual-designer` y `format-adapter` quedan **[OPCIONALES]** y no se listan en §4 porque
generan y validan creatividades publicitarias por plataforma, con especificaciones de anuncio
(zonas seguras, dimensiones de feed) que no tienen equivalente en un panel interno. El resto
de la suite (`ads-google`, `ads-meta`, `audit-*`, `copy-writer`, `creative-strategist`)
presupone cuentas de medios pagados, que este proyecto no tiene.

---

## 8. PROGRESO

| # | Tarea | Estado | Evidencia (commit/test/PR) | Fecha |
|---|---|---|---|---|
| T4.0 | Tarea Cero: rama y evidencia del antes | PENDIENTE | | |
| T4.1 | Auditoría del estado actual y ADN de marca | PENDIENTE | | |
| T4.2 | Dirección visual (ADR) | PENDIENTE | | |
| T4.3 | Extraer HTML de `app.py` a templates/static | PENDIENTE | | |
| T4.4 | Sistema de diseño: tokens y componentes | PENDIENTE | | |
| T4.5 | Estados de carga: esqueletos | PENDIENTE | | |
| T4.6 | Sistema de movimiento | PENDIENTE | | |
| T4.7 | Rediseño del dashboard `/` | PENDIENTE | | |
| T4.8 | Rediseño del formulario `/formulario` | PENDIENTE | | |
| T4.9 | Rediseño del importador `/importador` | PENDIENTE | | |
| T4.10 | Accesibilidad, responsive y rendimiento | PENDIENTE | | |
| T4.11 | Cierre: sistema documentado, PR, handoff | PENDIENTE | | |

**Avance del plan: 0 / 12 tareas (0 %)**
