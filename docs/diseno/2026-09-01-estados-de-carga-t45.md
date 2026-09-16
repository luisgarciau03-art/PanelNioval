# Estados de carga del panel — Plan 4, T4.5

**Fecha:** 2026-09-01 · **Rama:** `feat/rediseno-panel` · **Criterios:** CE4 (CLS < 0.1),
CE5 (cero spinners genéricos), y la regla de celebración del
[ADR de dirección visual](../adr/2026-08-31-direccion-visual-panel.md).

---

## 1. De qué se partía

Un solo estado no-feliz para tres situaciones distintas:

| Situación | Lo que veía el operador |
|---|---|
| Cargando | `<div class="loading"><div class="spinner"></div><br>Cargando…</div>` |
| Sin filas | `<div class="empty">No hay datos</div>` — gris, sin explicación |
| La lectura falló | el mismo `.empty` gris, con el texto en rojo |
| Cargó a medias | no existía |

**16 apariciones** de `class="loading"`: 15 en el marcado del tablero y 1 inyectada
desde `dashboard.js`. Todas **sustituían** el contenido, así que al llegar los datos
el bloque pasaba de ~100 px a varios cientos y todo lo de abajo saltaba.

### El caso que costaba operación real

`get_contacto_pendiente` capturaba `Exception` y devolvía `None`
—exactamente igual que "la hoja se leyó bien y no quedan pendientes"—, el endpoint
traducía ese `None` a `{'fin': True}` y el formulario remataba con:

> 🎉 **¡Lista completada!** No hay más contactos pendientes por llamar.

Con Google caído, el operador leía que había terminado su jornada y dejaba de llamar.
Es el caso que el voto del Crítico anticipó en el ADR: **un estado que solo puede
afirmar "no recibí datos" no puede vestirse de éxito.**

---

## 2. Qué hay ahora

### 2.1 El sistema

| Pieza | Dónde | Qué hace |
|---|---|---|
| `.esqueleto*` | `static/css/componentes.css` | La forma del contenido que viene, **con su altura**, para que nada se mueva al llegar |
| `.estado--vacio` | ídem | Gris, borde punteado. No pasó nada malo |
| `.estado--error` | ídem | Banda roja, **siempre** con botón de reintento |
| `.estado--parcial` | ídem | Ámbar, al margen. Lo demás cargó; esta pieza no |
| `Estados.*` | `static/js/estados.js` | Módulo compartido por las tres superficies |

Vacío, error y parcial usan **paletas distintas a propósito**: el ADR lo exige porque
hasta ahora los tres se veían igual. Un test lo fija
(`test_vacio_y_error_no_comparten_vocabulario_visual`).

### 2.2 El umbral de parpadeo

`UMBRAL_ESQUELETO = 200 ms`. Por debajo de eso, un esqueleto aparece y desaparece antes
de que el ojo lo lea: se ve como un parpadeo, no como una espera. El temporizador se
**cancela** si los datos llegan antes; sin ese `clearTimeout` el esqueleto se pintaría
*después* de los datos y los borraría.

**La primera carga es distinta:** su esqueleto viene ya en la plantilla, no del JS.
Pintarlo desde JavaScript llegaría tarde —después del primer render— y provocaría
justo el salto que viene a evitar. El umbral aplica a las **recargas** (cambio de
sección ya visitada, botón Actualizar), que es donde ya hay contenido en pantalla.

### 2.3 El formulario ya distingue las dos cosas

`get_contacto_pendiente` relanza la excepción; `/api/formulario/siguiente` responde
**503** con un mensaje genérico —sin arrastrar la excepción de gspread, que puede
traer contenido de la fila, o sea datos del cliente, a una pantalla que se comparte—;
y el formulario tiene un `step-error` propio, con reintento, separado de `step-fin`.

La celebración de `step-siguiente` (✅ Contacto Guardado) **se conserva**: ahí el
backend sí confirmó la escritura. Es un estado verificado.

---

## 3. CE4 — salto de layout, medido

Herramienta: `python tools/medir_cls.py`. Levanta el panel sin credenciales de Google,
intercepta `/api/*` con cargas **sintéticas** tras 1,200 ms de retardo y suma las
entradas `layout-shift` sin `hadRecentInput`. El observador se instala con
`add_init_script`, antes de que corra un solo script de la página.

El "antes" se midió sobre un `git worktree` del commit `d890cde`, con **la misma
versión de la herramienta**, para que la comparación sea justa.

| Superficie | Ancho | Antes | Después | |
|---|---:|---:|---:|---|
| dashboard | 320 | 0.0990 | **0.0010** | |
| dashboard | 768 | **0.5586** | **0.0103** | ✗ → ✓ |
| dashboard | 1440 | **0.1941** | **0.0253** | ✗ → ✓ |
| formulario | 320 | 0.0000 | 0.0000 | |
| formulario | 768 | 0.0014 | 0.0014 | |
| formulario | 1440 | 0.0000 | 0.0005 | |
| importador | 320 | 0.0342 | 0.0286 | |
| importador | 768 | 0.0611 | 0.0217 | |
| importador | 1440 | 0.0219 | 0.0099 | |

**Los nueve puntos por debajo de 0.1.** Peor caso: importador a 320 px, 0.0286.

Las cifras oscilan unas milésimas entre corridas (dependen de cuándo resuelve el
navegador las fuentes); el orden de magnitud es estable.

### 3.1 Lo que de verdad estaba saltando

Los esqueletos **no** eran la causa principal. Con `--detalle`, la herramienta señaló
tres cosas que nada tenían que ver con ellos, todas dentro de CE4:

1. **Chart.js redimensionaba los `<canvas>`** (0.30 de CLS a 768 px). El atributo
   `height="180"` del marcado no sobrevivía: la librería es responsive por defecto y
   ajustaba la altura a la relación de aspecto de cada tipo de gráfica. Corregido
   reservando el alto en `.chart-lienzo` y poniendo `maintainAspectRatio: false`.
2. **La cabecera crecía sola** (0.11 de CLS, a los 477 ms, *antes* de que llegara
   ningún dato). `.actions` era un item flexible que la barra encogía por debajo de su
   contenido, y el botón «Actualizar» envolvía a dos líneas: la cabecera ganaba 24 px
   y empujaba todo. Corregido con `flex-shrink: 0`, alto mínimo propio y título que se
   recorta con puntos suspensivos en vez de envolver.
3. **La caja de ciudades tenía techo pero no suelo.** `max-height: 220px` sin
   `min-height`: con 12 chips de esqueleto medía menos que con las 606 ciudades reales.

Ninguna de las tres se habría encontrado leyendo el código. La herramienta con
`--detalle` dice **qué elemento** se movió y de qué caja a qué caja; sin eso se acaba
corrigiendo a ciegas el elemento equivocado — que es lo que pasó en el primer intento,
donde se retocó la insignia de caché y el CLS no se movió ni una milésima.

### 3.2 Un fallo del propio medidor, y cómo se vio

La primera versión de `_cuerpo()` comparaba la **URL completa** contra rutas tipo
`/api/prospectos/stats`. No casaba nunca, así que devolvía `[]` para todo: la medición
parecía funcionar y en realidad cronometraba la transición esqueleto → **vacío**, que es
la barata. Se descubrió al mirar una captura y ver `undefined` en un indicador que
debía traer un número.

Las cifras de la tabla son posteriores a esa corrección, y por eso el "antes" se volvió
a medir en lugar de reutilizar la primera pasada.

---

## 4. Los cuatro estados, capturados

`python tools/capturar_estados.py docs/diseno/2026-09-01-estados-t45`

| Archivo | Qué fuerza |
|---|---|
| `carga.png` | `/api/*` colgado: el esqueleto en vuelo |
| `vacio-tabla.png` | `/api/*` responde bien y sin filas, en «Lista de Contactos» |
| `error-tabla.png` | `/api/*` responde 500, misma sección |
| `error.png` | El mismo 500 sobre el tablero |
| `parcial.png` | Los datos llegan; se bloquea el CDN de Chart.js |
| `formulario-error.png` | El fallo de lectura que antes salía como «¡Lista completada!» |
| `importador-carga.png` | Chips de ciudad en esqueleto |

Vacío y error se capturan **en una tabla** a propósito: en el tablero no hay ninguna, y
ahí es donde los dos estados eran indistinguibles.

El caso «parcial» no es inventado: Chart.js se carga desde jsdelivr **sin SRI y sin
copia local** (deuda anotada para el Plan 5). Si ese CDN no responde, los indicadores
llegan y las gráficas no.

---

## 5. Lo que encontraron los reviewers (y que la verificación propia no vio)

Tres gates: `code-reviewer`, `python-reviewer` y `a11y-architect`. `python-reviewer`
aprobó sin CRITICAL ni HIGH. Los otros dos encontraron, **de forma independiente**, el
mismo fallo grave — y ninguna de las 58 pruebas escritas para la tarea podía verlo,
porque todas leen el código fuente y ninguna ejecuta JavaScript.

### 5.1 El esqueleto borraba los datos que ya habían llegado

`terminar()` hacía `el.innerHTML = ''` sin mirar qué había dentro. Quien lo llama cierra
el esqueleto en un `finally`, que corre **después** de que la sección pintó su
contenido. Secuencia en el camino más usado del panel:

1. El operador pulsa «↻ Actualizar».
2. `refreshData` borra `state.loaded` pero no `state.pintada`, así que el JS pinta su
   esqueleto.
3. Google responde en más de 200 ms → el esqueleto llega a pintarse.
4. Los datos lo sustituyen. Todo correcto en pantalla.
5. El `finally` cierra el esqueleto → **vacía el contenedor y borra los datos.**

Pantalla en blanco, sin error que lo explique. Corregido: `terminar()` retira **el nodo
que él mismo insertó**, y solo si sigue puesto.

### 5.2 Los otros cuatro

| Hallazgo | Severidad | Corrección |
|---|---|---|
| El error usaba `role="status"` (*polite*): puede perderse. Un fallo de lectura bloquea la tarea | HIGH | `role="alert"` solo para el error; vacío y parcial siguen en `status` |
| En el formulario, el texto del error se escribía con el paso todavía en `display:none`, y revelarlo después no cuenta como mutación: **no se anunciaba nunca** | HIGH | `showStep('error')` primero, texto después; y el foco va al botón de reintento |
| `Estados.parcial('dash-charts')` sustituía el contenedor y con él los `<canvas>`: el siguiente intento moría buscando un elemento inexistente, y el fallo pasaba de temporal a **permanente** | MEDIUM | El aviso vive en un contenedor propio, fuera de la caja de gráficas |
| El reintento no repintaba esqueleto (`pintada` solo se marcaba tras un éxito): el botón parecía no hacer nada | MEDIUM | `pintada` se marca en el `finally`, pase lo que pase |

Además, dos notas menores atendidas: el `role="status"` estático de las plantillas no se
anuncia en la primera carga —los lectores anuncian *mutaciones*, no contenido
preexistente—, así que la plantilla deja el nodo vacío y `estados.js` escribe el texto
tras el primer render; y el `h1` recortado con elipsis lleva ahora su texto completo en
`title`, para quien amplía la página sin lector de pantalla.

**No** se mueve el foco automáticamente al reintentar en el tablero: ahí pueden
aparecer dos bloques de error a la vez (indicadores y tabla) y se pelearían por el foco.
En el formulario sí, porque muestra un paso cada vez.

### 5.3 Y un fallo que se coló al corregir

Al extraer las gráficas de ventas a su propia función, el `replace` que insertaba la
llamada **no casó y no se quejó** —el patrón incluía un texto que la extracción acababa
de retirar—, así que las tres gráficas de ventas quedaron sin pintarse. Lo atrapó uno de
los tests nuevos, no la lectura del diff. Es la misma trampa que el CLAUDE.md ya
documenta: *una operación que no encuentra nada tampoco se queja*. Ahora la verificación
se hace **sobre el archivo**, no sobre lo que devolvió la función.

### 5.4 Verificación en navegador

Como ninguna prueba estática podía ver el fallo de 5.1, se añadió
`python tools/verificar_estados.py`, que conduce el panel con Playwright:

| Comprobación | Resultado |
|---|---|
| «Actualizar» con red lenta conserva los indicadores | ✅ |
| El fallo de gráficas avisa sin borrar los lienzos | ✅ |
| El error se anuncia como `alert` | ✅ |
| El error ofrece reintento | ✅ |
| El reintento recupera los datos | ✅ |

Comprobada **en las dos direcciones**: con el `terminar()` original restaurado a
propósito sobre una copia, la primera comprobación se pone en rojo con
`antes=8 despues=0`. Un verde que no sabe ponerse rojo no vale nada.

---

## 6. Lo que esta tarea NO hace

- **No arregla la accesibilidad del panel.** Introduce los primeros `role="status"` del
  proyecto, pero los 12 `div` con `onclick`, los campos sin nombre accesible y los 10
  modales sin trampa de foco siguen siendo trabajo de la **T4.10**.
- **No rediseña ninguna superficie.** El alto fijo de las gráficas es estructural, para
  reservar espacio; su tratamiento visual es la **T4.7**.
- **No pone SRI a Chart.js.** Es deuda del Plan 5; aquí solo se cubre el caso de que
  falle.
- **No valida `?skip=`** en `/api/formulario/siguiente`. Un valor no numérico sigue
  dando 500 — que ahora, al menos, el formulario presenta como error legible en vez de
  quedarse cargando para siempre.

---

## 7. Verificación

| Qué | Resultado |
|---|---|
| Suite completa | **637 passed, 1 skipped** (baseline de la rama: 564; +73 de la T4.5) |
| Verificación en navegador | 5/5 (`tools/verificar_estados.py`), comprobada en las dos direcciones |
| CE4 · CLS < 0.1 | 9/9 puntos, peor caso 0.0288 |
| CE5 · `class="loading"` | 16 → **0** |
| `.spinner` / `@keyframes spin` | retirados de `dashboard.css` y `formulario.css` |
| Capturas de los cuatro estados | 7 PNG, sin datos de clientes (app arrancada sin credenciales, comprobado) |

El respaldo previo al cambio está en
`docs/auditoria/respaldos/2026-09-01/t45-antes/` (10 archivos).
