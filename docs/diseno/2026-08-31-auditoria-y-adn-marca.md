# Auditoria del panel y ADN de marca — Plan 4, T4.0 y T4.1

**Fecha:** 2026-08-31
**Rama:** `feat/rediseno-panel`, creada desde `feat/relevancia-ciudades-nacional`
**Baseline de la rama:** `python -m pytest tests/` → **482 passed, 1 skipped**, exit 0 (133.66 s)

> Todos los numeros de este documento estan **medidos sobre el codigo en disco** el
> 2026-08-31, no copiados de documentos previos. Los anclajes `archivo:linea` se
> localizaron con `grep`, no con los numeros que traian los planes: `app.py` crecio a
> **6,368 lineas** en esta rama y todos los anclajes del Plan 4 estaban desplazados.

---

## 0. Por que la rama sale del Plan 1 y no de `main`

El Plan 1 (PR #42) esta terminado pero **sin mergear**: su criterio CE10 es un gate humano
del owner. Ese PR cambia `app.py` en 389 lineas, y **164 caen dentro de los dos literales
HTML que la T4.3 tiene que sacar del archivo**:

| Zona | Lineas que cambia el Plan 1 |
|---|---|
| Dentro de `HTML` (dashboard) | 65 |
| Dentro de `IMPORTADOR_HTML` | 99 |
| Python puro (endpoints) | 225 |

Git no puede automergear *"contenido borrado de `app.py` y movido a `templates/`"* contra
*"ese mismo contenido editado en `app.py`"*. Ramificar de `main` habria obligado a
reaplicar esas 164 lineas **a mano** dentro de las plantillas nuevas — el selector de
macro-region, los chips con conteo y las tres columnas nuevas de la tabla de ciudades —
con riesgo de perderlas en silencio.

El propio Plan 4 ya lo anticipaba en su riesgo **R6**: *"este plan va el ultimo… rebase
sobre `main` ya con 1 y 3 mergeados"*. Decision del owner el 2026-08-31: **apilar el Plan 4
sobre la rama del Plan 1**.

**Consecuencia declarada:** el PR del Plan 4 arrastra los 8 commits del Plan 1, asi que
mergear el Plan 4 mergea tambien el Plan 1. El gate CE10 del owner pasa a cubrir los dos.

---

## 1. Correccion: el Plan 4 midio mal las superficies

El documento de validacion de la tanda afirma que las tres superficies suman **5,067
lineas**. **No es correcto.** Ese numero sale de medir *"del inicio de una constante al
inicio de la siguiente"*, que cuenta como HTML el codigo Python que vive **entre** las
constantes.

Medido de verdad, del inicio de cada literal `r"""` a su terminador:

| Superficie | El plan dice | Real en `main` | Real en esta rama |
|---|---|---|---|
| `HTML` (dashboard) | 2,651 | **1,992** | **2,012** |
| `FORMULARIO_HTML` | 1,852 | **687** | **687** |
| `IMPORTADOR_HTML` | 564 | **549** | **536** |
| **Total HTML** | **5,067** | **3,228** | **3,235** |
| **Python restante tras extraer** | *1,031* | **2,871** | **3,134** |

Reproducible en las dos ramas; el error de medicion es de **1,839 lineas**.

### Lo que esto le hace a CE1 y a la decision D1

CE1 pide `app.py` **< 800 lineas**. La §0.3 del Plan 4 ya lo daba por inalcanzable y
proponia el supuesto D1-A: reescribir CE1 como *"< 1,100 lineas"*.

**Ese supuesto tambien es inalcanzable.** Tras la T4.3 `app.py` no queda en 1,031 lineas
sino en **~3,134**. Para bajar de 1,100 no basta con sacar el HTML: hay que trocear el
Python en modulos, que es justamente la opcion **D1-B** que el plan descarto.

`SUPUESTO: la T4.3 se ejecuta con su alcance original (solo HTML) y CE1 se reporta con el`
`numero real alcanzado (~3,134), declarando que el troceo del Python queda fuera de este`
`plan — afecta Plan 4, T4.3 y criterio CE1.` Ver **DECISIONES PENDIENTES** al final.

---

## 2. Estado de partida, medido

### 2.1 Estructura

| Metrica | Valor |
|---|---|
| `app.py` | **6,368** lineas |
| HTML embebido | **3,235** lineas (**50.8 %** del archivo) |
| `render_template_string` | 4 llamadas |
| Constantes HTML | `HTML` (1294), `FORMULARIO_HTML` (3965), `IMPORTADOR_HTML` (5817) |

### 2.2 Color: los tokens existen y aun asi se escriben a mano

Las variables CSS estan **declaradas tres veces**, una por superficie, y el importador solo
tiene 3 de las 7. Pese a existir `--blue`, el valor `#0047cc` aparece **17 veces como
literal**.

| Valor | Apariciones como literal |
|---|---|
| `#fff` | 54 |
| `#888` | 17 |
| `#0047cc` | **17** (existiendo `--blue`) |
| `#dde` | 13 |
| `#e74c3c` | 11 |
| `#aaa` | 9 |

### 2.3 Contraste — medido con la formula WCAG 2.2

**Este es el hallazgo mas serio de la auditoria.** El riesgo R4 del plan (*"el verde
`#00CC47` sobre blanco no pasa AA"*) se cumple, y es peor de lo previsto: falla tambien en
texto grande, y el ratio es **simetrico**, asi que texto blanco sobre relleno verde falla
igual — que es exactamente como se usa hoy en los botones del formulario.

| Color | Sobre blanco | AA texto (4.5) | AA grande (3.0) | Mas claro que SI pasa AA |
|---|---|---|---|---|
| `--blue` `#0047CC` | 7.57:1 | PASA | PASA | — |
| `--blue2` `#003399` | 10.86:1 | PASA | PASA | — |
| `--purple` `#8e44ad` | 5.87:1 | PASA | PASA | — |
| `--red` `#e74c3c` | 3.82:1 | **FALLA** | PASA | `#e22e1c` (4.52:1) |
| `--orange` `#e67e22` | 2.85:1 | **FALLA** | **FALLA** | `#b56015` (4.52:1) |
| `--green` `#00CC47` | **2.16:1** | **FALLA** | **FALLA** | `#008930` (4.54:1) |
| gris `#888` (×17) | 3.54:1 | **FALLA** | PASA | `#767676` (4.54:1) |
| gris `#aaa` (×9) | 2.32:1 | **FALLA** | **FALLA** | `#767676` |
| gris `#777` (×4) | 4.48:1 | **FALLA** | PASA | `#767676` |

Los sustitutos se calcularon bajando **solo la luminosidad en HLS**, conservando tono y
saturacion: mantienen el caracter de la marca. El `#00CC47` original se conserva para
rellenos y elementos **no textuales**, donde el requisito es 3:1 contra el fondo adyacente.

### 2.4 Accesibilidad: no esta sin auditar, esta ausente

| Metrica | Valor | Lectura |
|---|---|---|
| Atributos `aria-*` | **0** | ninguno en 3,235 lineas de HTML |
| Landmarks (`<main>`, `<nav>`, `<header>`, `<section>`) | **0** | ninguno |
| `tabindex` | **0** | ninguno |
| `<label>` frente a controles de formulario | **13** frente a **34** | **21 controles sin etiqueta** |
| `onclick` totales | **104** | de ellos **15 sobre `<div>`**: inalcanzables por teclado |
| Reglas `:focus` | 9 | existe algo de foco, sin sistema |
| `prefers-reduced-motion` | **0** | no se respeta |
| Logo Cloudinary | 3 apariciones | **ninguna** con `width`/`height`; **2 de 3** sin `alt` |

### 2.5 Movimiento y carga

| Metrica | Valor |
|---|---|
| `class="loading"` (spinner generico) | **16** |
| `transition: all` | **12** |
| `grid-template-columns` fijas | 6 × `1fr 1fr`, 1 × `1fr 1fr 1fr 1fr` |
| `innerHTML` | **60** asignaciones, con **1** sola funcion `escaparHtml` (`app.py:6052`, del Plan 3) |

---

## 3. Los estados de error mienten — hallazgo de las capturas

Las capturas del antes se tomaron con el panel arrancado **sin credenciales de Google**, a
proposito: asi ninguna imagen lleva datos de clientes y, de paso, se ve como se comporta la
interfaz cuando el backend falla. El resultado es el hallazgo funcional mas importante de
la T4.1:

**El formulario de llamadas celebra el error.** Con las hojas caidas muestra
*"¡Lista completada! — No hay mas contactos pendientes por llamar"* sobre un emoji de
confeti, con "TOTAL PROCESADOS 0". Un operador cuya conexion falle concluiria que termino
su lista de llamadas. Ademas la cabecera sigue diciendo *"Cargando contacto…"* mientras el
cuerpo dice completado: **dos estados contradictorios en pantalla a la vez**.

**El dashboard hace lo mismo, mas callado.** Con el backend caido pinta los ocho KPI en
**0** y las tres graficas con ejes vacios — indistinguible de un dia real sin actividad.

Esto no es un defecto estetico: es el estado **Error** que la T4.5 pide anadir, y confirma
con evidencia por que hace falta. No se puede distinguir *"fallo"* de *"vacio"* en ninguna
de las dos superficies.

**El importador desborda a 320 px.** El selector de macro-region del Plan 1 y el campo de
ciudad manual quedan cortados por el borde derecho. CE10 falla hoy.

---

## 4. Que funciona y hay que conservar

No todo esta mal, y un rediseno que tire esto seria un retroceso:

- **La consola de log del importador** (fondo oscuro, texto verde) es lo mas honesto de la
  pantalla: dice que esta pasando, en orden, sin adornos. Conservar su funcion.
- **Los cuatro contadores del Plan 3** ya dicen la verdad y su invariante se sostiene.
- **El escape de HTML del Plan 3** (`escaparHtml` + `data-ciudad` + listener delegado) es el
  patron correcto; hay que **extenderlo**, no rehacerlo.
- **Los chips de prioridad del Plan 1** con conteo crudo y explicacion en tooltip resuelven
  bien un problema dificil. El puntaje va en escala logaritmica y **no debe mostrarse como
  decimal**.
- **La paleta azul** (`--blue`, `--blue2`) pasa AA con holgura y es reconociblemente NIOVAL.

---

## 5. Capturas del antes

Nueve capturas en `docs/diseno/antes/`: tres superficies × tres anchos (320, 768, 1440).

**Sin datos de clientes.** El script `tools/capturar_superficies.py` corta las **dos** vias
de credencial de `app.py` (`GOOGLE_CREDENTIALS_JSON` y `GOOGLE_CREDENTIALS_FILE`) y aborta
si el panel **si** logra autenticarse — no se confia en que el corte funcione, se comprueba
en la direccion util.

Una primera corrida **si** cargo datos reales, porque el codigo cae por defecto a un archivo
`.json` de credencial en la raiz del proyecto. Esas 9 capturas llevaban nombre de negocio y
telefono real, y estan apartadas en
`docs/auditoria/respaldos/2026-08-31/capturas-con-pii-NO-COMMITEAR/`, cubierto por
`.gitignore:26` — verificado con `git check-ignore -v`, no por lectura. **Nada se borro.**

---

## 6. DECISIONES PENDIENTES

### D6 — CE1 tras la correccion de medicion · afecta: **Plan 4, T4.3 y criterio CE1**

Sacar el HTML deja `app.py` en **~3,134** lineas, no en 1,031. Ni el CE1 original (< 800) ni
el supuesto D1-A (< 1,100) son alcanzables extrayendo solo HTML.

- **A)** Mantener el alcance de la T4.3 (solo HTML) y **reescribir CE1** como *"`app.py`
  baja al menos un 45 % y ningun archivo nuevo supera 800 lineas"*. **(recomendada)** — la
  T4.3 ya es la tarea de mayor riesgo del plan; anadirle el troceo del Python duplica la
  superficie de fallo sobre el formulario que NIOVAL usa horas al dia.
- **B)** Ampliar la T4.3 con el troceo del Python en modulos (`rutas_*.py`, `sheets.py`,
  `importador.py`) y conservar CE1 < 800.
- **Impacto:** si B, la T4.3 se parte en dos, el Plan 4 pasa de 12 a 13 tareas y su riesgo
  R1 sube de Media a Alta. Si A, CE1 queda anotado con el numero real alcanzado.
- Mientras no haya respuesta, se asume **A**.
