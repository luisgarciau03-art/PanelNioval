# AUDITORÍA DEL REDISEÑO CONSTRUIDO (PR #43)

**Tarea:** Plan 4 · T4.1 · **Fecha:** 2026-09-16 · **Rama auditada:** `feat/rediseno-panel` (`35a7a50`)
**Auditor:** sesión externa al ejecutor del PR #43. Nadie lo había revisado desde fuera.

---

## 0. EL CRITERIO, FIJADO ANTES DE MIRAR

> Esta sección se escribió y se commiteó **antes** de abrir un solo documento del rediseño.
> El plan lo exige por un motivo concreto: si el criterio se formula después de ver el
> resultado, la auditoría deja de serlo y se convierte en una racionalización de lo que ya
> está construido. Lo que sigue es contra qué se juzga, no qué se encontró.

### 0.1 El dominio manda, y este dominio es una herramienta de trabajo

PanelNioval **no es una landing**. Es un panel interno que **una persona usa todos los días**
para cerrar llamadas: abre el formulario, lee un contacto, marca un resultado, pasa al
siguiente. Cientos de veces.

Eso fija el tono antes que cualquier gusto: **denso, callado y escaneable**. La regla de
`frontend-design-direction` es explícita — *«no fuerces una composición de landing sobre una
herramienta de uso diario repetido»*. Un rediseño que llegue con héroe centrado, degradados
decorativos y tarjetas enormes habrá fallado **aunque se vea bonito**, porque le cobra al
operador un peaje de lectura en cada repetición.

**Corolario que se aplicará sin piedad:** cualquier elemento que sea bonito y no ayude a
escanear cuenta como **coste**, no como mérito.

### 0.2 Lo que el dueño pidió por su nombre

El encargo nombra tres cosas. La auditoría comprueba que **existen de verdad**, no que
aparezcan en el título de un documento:

| Eje | Qué se exige para darlo por hecho |
|---|---|
| **Movimientos** | Un sistema declarado (duraciones, curvas, qué se anima y qué no) **y** respeto a `prefers-reduced-motion` |
| **Display** | Jerarquía visual y tipográfica decidida a propósito, no heredada del navegador |
| **Pantallas de carga** | Los **cuatro** estados —cargando, vacío, error, parcial— en cada superficie que pide datos |

### 0.3 La matriz de cobertura

3 superficies (tablero · formulario · importador) × 3 ejes (movimiento · display · estados de
carga) × los breakpoints declarados. Cada celda: **¿hay captura y decisión escrita?** Un hueco
es una celda sin una de las dos cosas.

### 0.4 La política anti-plantilla: ≥4 de 10, con la prueba delante

De las reglas del entorno. Se exige nombrar **cuáles** y con **qué captura** se prueban. Decir
«tiene buena jerarquía» sin señalar dónde no cuenta.

1. Jerarquía por contraste de escala · 2. Ritmo intencionado en el espaciado · 3. Profundidad
o capas · 4. Tipografía con carácter y estrategia de pares · 5. Color semántico, no decorativo
· 6. Estados de interacción diseñados · 7. Composición editorial o que rompe la rejilla ·
8. Textura o atmósfera · 9. Movimiento que aclara el flujo · 10. Visualización de datos como
parte del sistema.

### 0.5 Los cuatro defectos que descalifican

Prohibidos por las reglas del entorno. Se buscan **a propósito**, no se espera a tropezarlos:

- Rejilla de tarjetas uniforme sin jerarquía.
- Radio y sombra idénticos en todos los componentes.
- Gris sobre blanco con un único acento decorativo.
- Tarjetas dentro de tarjetas.

### 0.6 Qué puede fallar y quiero atrapar

- Un documento que **declara** un sistema que el CSS no implementa.
- Capturas que prueban el caso feliz y **ningún estado degradado**.
- `prefers-reduced-motion` citado en prosa y ausente del CSS.
- Los cuatro estados cubiertos en el tablero y **olvidados en el importador**, que es la
  superficie con la espera más larga (una corrida de Places tarda minutos).

### 0.7 Dato de T4.0 que esta auditoría ya trae encima

La línea base mide **CLS 0.1924 en el tablero a 1440**, casi el doble del umbral. Si el
rediseño no aborda el desplazamiento de layout, es un hueco **aunque todo lo demás esté bien**:
el CLS es exactamente lo que el operador sufre cuando el panel le mueve un botón bajo el dedo.

---

*(El resultado de la auditoría continúa abajo, escrito después de leer los documentos.)*
