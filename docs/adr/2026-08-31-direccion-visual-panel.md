# ADR — Direccion visual del panel NIOVAL

- **Fecha:** 2026-08-31
- **Estado:** Aceptada
- **Contexto:** Plan 4 (rediseno profesional del panel), Tarea T4.2
- **Decide:** direccion visual de las tres superficies (`/`, `/formulario`, `/importador`)
- **Metodo:** skill `council` (community) — cuatro voces independientes, sin historial compartido

---

## Contexto

El owner pidio *"un rediseno profesional: movimiento, presentacion y pantallas de carga"*
sobre las tres superficies, **sin cambiar de stack** (Flask, HTML servido, CSS y JS a mano).

Las reglas globales del entorno prohiben de forma explicita el resultado generico —
rejillas de tarjetas uniformes, hero centrado con degradado, y *"clean minimal"* como
direccion— y exigen cumplir **>= 4 de 10 cualidades** de calidad de diseno.

El estado de partida, medido en `docs/diseno/2026-08-31-auditoria-y-adn-marca.md`: tarjeta
blanca centrada sobre degradado azul, `'Segoe UI'` por omision, radio uniforme, una sombra,
**0** `aria-*`, **0** landmarks, 16 spinners genericos, 12 `transition: all`, y una paleta
donde el verde de marca da **2.16:1**.

## Opciones consideradas

| # | Direccion | Por que era candidata |
|---|---|---|
| **A** | **Editorial / Swiss disciplinado** | Jerarquia por escala tipografica, rejilla y ritmo de espaciado; tradicion construida para densidad informativa y tablas |
| B | Bento con jerarquia | Bloques de tamano desigual que dan peso distinto a cada dato; de moda y visualmente rotundo |
| C | Luz con profundidad real | Capas, sombras y superficies; sensacion de producto pulido |

## Decision

**Se elige A — editorial / Swiss disciplinado**, con dos matices que salieron del consejo y
que forman parte de la decision, no son adornos:

1. **Un solo sistema, tres registros.** No se aplica la misma densidad ni el mismo
   movimiento a las tres pantallas. Los tokens, la escala y la paleta son unicos; la
   calibracion por superficie es distinta:

   | Superficie | Registro | Por que |
   |---|---|---|
   | `/formulario` | **Denso y quieto.** Movimiento minimo, solo el imprescindible para confirmar el guardado | Se usa hora tras hora; la velocidad de captura manda sobre la estetica. Un rediseno que se vea mejor y capture mas lento es un retroceso (riesgo R2) |
   | `/` dashboard | **Jerarquico.** Contraste de escala fuerte entre lo que se mira primero y el resto | 8 KPI y 14 tablas hoy pesan todos lo mismo |
   | `/importador` | **Narrativo.** El movimiento cuenta el avance de la corrida | Es una operacion larga que gasta dinero: el operador necesita leer progreso, fase y costo |

2. **La paleta accesible es precondicion, no consecuencia.** Las tres voces externas
   coincidieron, de forma independiente, en que el verde a 2.16:1 y el naranja a 2.85:1
   son un bloqueante que **cualquiera** de las tres direcciones heredaba igual. Se corrige
   antes de componer nada.

### Por que se descartan B y C

- **B (bento):** el contenido dominante son 14 tablas densas y un formulario de captura
  lineal. El bento no resuelve tablas: las distorsiona metiendolas en celdas de tamano
  desigual, y agrava el desborde horizontal que el importador **ya tiene** a 320 px.
  Es defendible para los 8 KPI del dashboard; no para el resto. Se conserva la idea
  acotada —jerarquia de bloques solo en la franja de KPI— sin adoptar la direccion.
- **C (profundidad real):** sombras en capas y superficies translucidas en CSS escrito a
  mano es justo donde nacen los repaints, con 606 chips que refluyen y tablas con orden y
  filtro. **CE4 exige CLS < 0.1 como gate duro.** Ademas cada capa nueva es un par
  texto/fondo mas que verificar sobre una paleta que ya falla. Coste alto, beneficio que
  el operador que captura 8 horas no percibe.

## Paleta corregida

Los sustitutos bajan **solo la luminosidad en HLS**: conservan tono y saturacion, y por
tanto el caracter de la marca. El valor original se conserva para rellenos y elementos
**no textuales**, donde el requisito es 3:1 contra el fondo adyacente y no 4.5:1.

| Token | Hoy | Ratio | Para texto | Ratio |
|---|---|---|---|---|
| `--azul` | `#0047CC` | 7.57:1 | *(sin cambio)* | 7.57:1 |
| `--azul-profundo` | `#003399` | 10.86:1 | *(sin cambio)* | 10.86:1 |
| `--verde` | `#00CC47` | **2.16:1** | **`#008930`** | 4.54:1 |
| `--naranja` | `#e67e22` | **2.85:1** | **`#b56015`** | 4.52:1 |
| `--rojo` | `#e74c3c` | **3.82:1** | **`#e22e1c`** | 4.52:1 |
| gris texto | `#888` `#aaa` `#777` | 3.54 / 2.32 / 4.48 | **`#767676`** | 4.54:1 |

## Tipografia — decision explicita

`'Segoe UI'` estaba por omision. **Se decide conservar una pila de sistema**, ampliada a
una pila multiplataforma real, y **no** descargar ninguna fuente web.

Razon: es un panel interno que se usa a jornada completa sobre maquinas Windows; una fuente
web anade bytes y un `font-display: swap` que provoca reflow en la superficie donde la
velocidad de captura es el criterio de exito. El presupuesto de rendimiento se gasta mejor
en no gastarlo.

Lo que **si** es una decision tipografica y no una omision:

- **Cifras tabulares** (`font-variant-numeric: tabular-nums`) en KPI, tablas y contadores.
  Con cifras proporcionales las columnas de numeros bailan al reordenar; es el defecto
  tipografico mas visible de un panel de datos, y cuesta cero bytes.
- **Pila monoespaciada declarada** para la consola de log del importador, que hoy dice
  `monospace` a secas y queda a merced del navegador.
- **Escala tipografica con saltos reales**, no tres tamanos casi iguales: el contraste de
  escala es la primera de las diez cualidades y es lo que separa "jerarquia" de "todo pesa
  igual".

Si mas adelante se quiere una tipografia con mas caracter, la condicion es: auto-hospedada,
subconjunto, y medida contra el presupuesto — nunca una peticion a un CDN externo.

## Cualidades de diseno comprometidas (CE11 pide >= 4)

Se comprometen **7 de 10**:

1. **Jerarquia por contraste de escala** — el KPI que importa domina; `nuevos_en_sheet` es
   el numero grande del importador.
2. **Ritmo intencional de espaciado** — escala de espaciado, no `padding` uniforme.
3. **Tipografia con criterio** — cifras tabulares, pila mono declarada, escala con saltos.
4. **Color semantico** — verde/naranja/rojo/morado significan resultado de llamada, no
   decoran; el azul es navegacion y accion.
5. **Estados de interaccion disenados** — hover, focus, active y disabled para cada
   elemento interactivo. El foco visible es requisito, no adorno.
6. **Movimiento que aclara** — entrada escalonada de filas, progreso que se lee como
   avance, y `prefers-reduced-motion` respetado.
7. **Visualizacion de datos dentro del sistema** — las tres graficas con la paleta
   semantica corregida, no la salida por defecto de la libreria.

Se renuncia de forma consciente a: textura/atmosfera, composicion rompe-rejilla agresiva y
profundidad por capas — las tres estan en tension directa con CLS < 0.1 y con la velocidad
de captura del formulario.

## Consecuencia que hereda la T4.5 — del voto del Critico

El vocabulario festivo **es parte** de por que hoy no se distingue un fallo de un exito: con
las hojas caidas, el formulario muestra *"¡Lista completada!"* sobre un emoji de confeti.

**Regla que adopta el sistema:** la celebracion (confeti, verde de exito, marcas de
verificacion) queda **reservada a estados verificados de forma explicita**. Un estado que
solo puede afirmar *"no recibi datos"* no puede vestirse de exito. La T4.5 implementa los
cuatro estados —cargando, vacio, error, parcial— con vocabulario visual distinto para
"vacio" y para "error", que hoy son el mismo.

## Consecuencias

- **Positivas:** implementable en CSS a mano por una sola persona, en incrementos
  verificables por superficie; minima superficie para violar CE4 (CLS) y CE6 (propiedades
  del compositor); arregla el bloqueante de contraste de una vez y para las tres pantallas.
- **Negativas:** Swiss mal ejecutado se degrada a *"plano otra vez"* y no se notaria el
  salto. La contramedida es la escala tipografica con saltos reales y la jerarquia de KPI:
  si al terminar el dashboard las 8 tarjetas siguen pesando igual, la direccion no se
  aplico.
- **Ninguna direccion visual arregla la accesibilidad por si sola.** Con 21 de 34 controles
  sin `label` y 15 `onclick` sobre `div`, la semantica y el ARIA son trabajo aparte
  (T4.10), no un efecto secundario del rediseno.
