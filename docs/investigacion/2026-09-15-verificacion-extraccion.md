# VERIFICACIÓN DE LA EXTRACCIÓN — el rediseño no rompió nada funcional

**Tarea:** Plan 4 · T4.5 · **Fecha:** 2026-09-16 · **`main`:** `752fe2a`
**Qué se verifica:** sacar 3,240 líneas de HTML y JS de `app.py` es un refactor con superficie
de error baja y **consecuencia alta**: si un `id`, una ruta de `fetch` o un escape se perdió por
el camino, **el panel se ve bien y no funciona**. Los tests cubren mucho, pero esto es una
aplicación de navegador.

---

## 1. La respuesta, en una línea

> **Nada se rompió.** Las tres superficies cargan con la consola limpia, los dos casos de
> escape quedan bloqueados —con control positivo que demuestra que el detector sirve—, y los
> flujos responden: navegación, filtro, clic en chip y orden de tabla con ratón **y con
> teclado**. El único error de consola que apareció es un **hueco del fixture de datos
> sintéticos**, no del código, y está capturado.

---

## 2. Consola limpia en las tres superficies

| Superficie | Errores | Avisos |
|---|---:|---:|
| Tablero (`/`) | **0** | 0 |
| Formulario (`/formulario`) | **0** | 0 |
| Importador (`/importador`) | **0** | 0 |

---

## 3. Los dos casos de escape — y por qué su verde significa algo

El plan los pide por su nombre porque **este agujero ya existió**: B9 fue un XSS almacenado en
el nombre de ciudad, y una extracción es el momento clásico para reabrirlo.

Se inyectaron en la respuesta de `/api/importador/ciudades`:

| Caso | Carga | Resultado |
|---|---|---|
| Comilla | `O'Brien` | ✅ Se pinta como texto: `🥇 O'Brien 100`, y `data-ciudad` vale exactamente `O'Brien`. **No rompe el manejador** |
| XSS | `<img src=x onerror="window.__XSS=1">` | ✅ **No se ejecuta.** `window.__XSS` sin definir, **0** etiquetas `<img>` inyectadas en la lista |

### 3.1 Control positivo: el detector encuentra un XSS que sí se ejecuta

Un detector que nunca ha detectado nada no prueba nada. Se inyectó **la misma carga sin
escapar**, con `innerHTML` directo:

```
con innerHTML SIN escapar, window.__XSS === 1  ->  True
```

**El detector funciona.** Por tanto su `False` de la prueba real significa que el escape
aguanta, no que el instrumento esté ciego.

---

## 4. Flujos ejercitados

| Flujo | Resultado |
|---|---|
| **Navegación** entre secciones | ✅ 6 clics → 6 secciones distintas activas (`sec-frecuentes`, `sec-ventas-dash`, `sec-ventas`, `sec-dashboard`, `sec-contactos`, `sec-pendientes`). Ninguno deja el panel sin sección |
| **Clic en un chip** de ciudad | ✅ escribe el nombre en el campo. El manejador delegado sobrevivió a la mudanza |
| **Filtro de texto** | ✅ un filtro imposible deja 0 visibles; al limpiarlo vuelven los 20. Oculta **y** restaura |
| **Desplegable de región** | ✅ presente y poblado |
| **Ordenar una tabla** (50 filas, 7 columnas) | ✅ ver §4.1 |
| **Diálogos** | ✅ 4 encontrados, **los 4 con botón de cerrar** |
| Gráficas del tablero | ✅ 6 `<canvas>` · 8 tarjetas de KPI · 24 botones · 14 elementos de navegación |
| Formulario | ✅ 19 botones de resultado · 6 teclas de atajo · 6 `aria-keyshortcuts` · 15 pasos |

### 4.1 El orden de tabla, incluido el teclado

| | `aria-sort` | Flecha | Primera fila |
|---|---|---|---|
| Inicial | `none` | ⇅ | Ferretería Ejemplo 1 |
| Clic 1 | **`ascending`** | ▲ | — |
| Clic 2 | **`descending`** | ▼ | **Ferretería Ejemplo 9** |
| **Enter** con el foco en la cabecera | **`ascending`** | ▲ | — |

Funciona con ratón **y con teclado**, que es exactamente para lo que la T4.10 convirtió la
cabecera en un `<button>`: *«el `<th>` con `onclick` no era alcanzable con Tab»*.

---

## 5. El único error de consola, y por qué NO es un defecto

Al entrar en la sección **Dashboard de Ventas**:

```
loadSection error: ventas-dash TypeError: Cannot convert undefined or null to object
    at Object.entries (<anonymous>)
```

**Causa, comprobada:** el generador de datos sintéticos (`tools/medir_cls.py::_cuerpo`)
**no cubre las rutas `/api/ventas/*`** — devuelve una lista vacía. El JS hace
`Object.entries(m.por_esquema)` sobre ese `[]`, y `por_esquema` es `undefined`.

**Es un hueco del fixture, no del código.** Y el propio panel lo trata bien: el error va
**capturado y registrado** (`loadSection error:`), así que la sección degrada en vez de tumbar
la página.

⚠️ **Lo que sí deja anotado:** ninguna verificación de este plan —ni las capturas responsive de
T4.10, ni ésta— ha ejercitado **la sección de Ventas con datos**. Queda fuera de cobertura por
falta de fixture, y conviene saberlo antes de afirmar que «todo está probado».

---

## 6. Lo que esta verificación enseñó sobre sí misma

**Tres de mis instrumentos estaban mal antes que el código.** Merece anotarse porque es el
patrón que más tiempo ha costado en toda la tanda:

1. Buscaba las secciones con un selector inventado (`section:not([hidden])`) cuando el panel
   usa `.section.active`. Conclusión falsa: *«la navegación no cambia de sección»*.
2. Pulsaba el `<th>` para ordenar, cuando el manejador vive en un `<button>` dentro — y el
   comentario del código **explica por qué** está ahí.
3. Leía `aria-sort` de una referencia al DOM **capturada antes del repintado**, o sea de un
   nodo ya desechado.

Las tres veces el primer resultado fue un «no funciona» que era mío. **Un instrumento que no se
ha probado contra un positivo conocido no vale su cero** — y por eso el control positivo del §3.1
no es un adorno: es lo único que hace creíble el resto.

---

## 7. Criterio de cierre

| Exigencia del plan | Estado |
|---|---|
| Todos los flujos ejercitados | ✅ §4 |
| Consola limpia en las 3 superficies | ✅ §2 (el de §5 es del fixture, y aparece al navegar, no al cargar) |
| Los dos casos de escape probados **y bloqueados** | ✅ §3, con control positivo |

**T4.5 cerrada.** Sin defectos atribuibles a la extracción.
