/* ============================================================================
   NIOVAL - Importador  ·  Plan 4, T4.9
   Registro del ADR: NARRATIVO. Una corrida dura minutos y gasta dinero, asi
   que la pantalla cuenta lo que pasa: en que fase va, cuanto lleva escrito en
   la hoja, cuanto lleva gastado y como acabo.

   Lo que esta tarea cambia sobre lo que ya funcionaba (Planes 1, 2 y 3):

     - Los 606 chips se construyen UNA vez y se filtran ocultando, no
       reconstruyendo el HTML en cada pulsacion.
     - Van agrupados por macro-region, con el conteo de cada grupo en su
       cabecera y actualizado en vivo al filtrar.
     - Son un `listbox` de verdad: antes eran 606 `<span>` con manejador de
       clic, o sea inalcanzables con teclado.
     - El registro se ANADE linea a linea en vez de reescribirse entero, asi
       que ya no parpadea ni roba el scroll a quien esta leyendo.
     - Cancelado y tope de gasto son estados de primera clase: banda, titulo y
       texto propios. Solo `done` celebra.
     - Ni un `alert()` ni un `confirm()`: bloquean la pagina y roban el foco.
   ============================================================================ */

const CATS = ["Ferreterías","Distribuidoras Ferreterías"];
let polling = null;

// Se consulta una vez y se escucha el cambio en caliente: quien activa la
// preferencia a media corrida no tiene por que recargar.
const MOVIMIENTO_REDUCIDO = window.matchMedia('(prefers-reduced-motion: reduce)');

// Render categoria badges
// El estado de cada categoria se veia SOLO por el color de fondo. Quien usa
// lector leia "Ferreterias" y "Distribuidoras Ferreterias" sin saber cual esta
// en curso ni cual termino, asi que el estado viaja tambien en texto.
document.getElementById('cats-list').innerHTML = CATS.map((c,i) =>
  `<div class="cat-badge" id="cat-${i}">${c}<span class="solo-lectores" id="cat-estado-${i}"></span></div>`
).join('');

// Aqui vivia el array estatico: 293 entradas escritas a mano, 50 nombres
// duplicados y 9 con la abreviatura del estado pegada, que viajaba literal a
// Google Places ("Ferreterias en Santiago Ixc"). Lo sustituye el catalogo
// nacional de datos/ciudades_mx.json, que sirve /api/importador/ciudades ya
// ordenado y con la explicacion de cada posicion armada en el servidor.
let todasCiudades = [];
let sinClasificar = [];

// Indice de los chips ya construidos. Filtrar es recorrer esto y ocultar, no
// volver a generar 606 nodos: la version anterior rehacia el innerHTML entero
// en cada tecla (46 ms medidos con el catalogo completo).
let CHIPS = [];
let GRUPOS = [];
let chipElegido = null;
let sinResultadosPintado = false;

async function cargarCiudades() {
  const cont = document.getElementById('ciudades-chips');
  try {
    const r = await fetch('/api/importador/ciudades');
    if (!r.ok) throw new Error('HTTP ' + r.status);
    const d = await r.json();
    // Un 200 con JSON valido pero SIN las claves esperadas —una pagina de error
    // del proxy inverso, o un cambio futuro del backend— no lanza nada, y con
    // `|| []` acababa en dos listas vacias indistinguibles de "no hay resultados".
    // Es el estado mas silencioso de los tres, porque no dispara ni el catch ni
    // el aviso de sin_clasificar.
    if (!Array.isArray(d.ciudades)) throw new Error('respuesta inesperada del catalogo');

    todasCiudades = d.ciudades;
    sinClasificar = Array.isArray(d.sin_clasificar) ? d.sin_clasificar : [];
    if (d.catalogo_cargado === false) {
      // El catalogo no se pudo leer en el servidor. Sin este aviso, el operador
      // ve el mismo listado vacio que si simplemente no hubiera casado nada.
      // `role="alert"`: es un fallo de lectura y bloquea la eleccion por chip.
      // Sin rol, aparecia en silencio para quien no ve la pantalla.
      document.getElementById('sin-clasificar').innerHTML =
        '<div class="aviso-catalogo aviso-catalogo--error" role="alert">'
        + '⚠ El servidor no pudo leer el catalogo de ciudades. Escribe la ciudad a mano.</div>';
      todasCiudades = [];
    }

    // El rango se fija UNA vez sobre el catalogo completo. Si se calculara en
    // renderChips sobre la lista recibida, al escribir en el filtro la ciudad
    // numero 47 apareceria con medalla de oro.
    todasCiudades.forEach((c, i) => { c.rank = i + 1; });

    // Si el foco estaba dentro de la caja -o sea en el boton "Reintentar" que
    // el estado de error acaba de pintar-, `renderChips` va a destruir ese nodo
    // y el foco caeria a <body>. Se recuerda antes y se recoloca despues.
    const veniaDeLaCaja = cont.contains(document.activeElement);
    pintarRegiones(d.regiones || []);
    document.getElementById('ciudades-count').textContent = `(${todasCiudades.length})`;
    renderChips(todasCiudades);
    pintarSinClasificar();
    if (veniaDeLaCaja) {
      const primero = chipsVisibles()[0] || document.getElementById('region-filter');
      if (primero) primero.focus();
    }
  } catch (e) {
    // Sin catalogo NO se inventa una lista: se dice que no se pudo cargar y se
    // deja el campo de texto, que sigue aceptando cualquier ciudad. Un fallback
    // silencioso a una lista vieja seria peor que no tener lista.
    todasCiudades = [];
    CHIPS = [];
    GRUPOS = [];
    document.getElementById('ciudades-count').textContent = '';
    document.getElementById('chips-resumen').textContent = '';
    Estados.error(cont, {
      titulo: 'No se pudo cargar el catalogo de ciudades',
      detalle: 'El campo de texto sigue funcionando: escribe la ciudad a mano.',
      reintentar: cargarCiudades,
    });
  }
}

function pintarRegiones(regiones) {
  const sel = document.getElementById('region-filter');
  const total = regiones.reduce((s, r) => s + r.total, 0);
  // El conteo va en cada opcion a proposito: sin el, una region vacia y un
  // filtro roto se ven exactamente igual.
  sel.innerHTML = `<option value="">Todas (${total})</option>`
    + regiones.map(r =>
        `<option value="${escaparHtml(r.region)}">${escaparHtml(r.region)} (${r.total})</option>`
      ).join('');
}

function pintarSinClasificar() {
  const caja = document.getElementById('sin-clasificar');
  if (!sinClasificar.length) { caja.innerHTML = ''; return; }
  const n = sinClasificar.reduce((s, c) => s + c.total, 0);
  const nombres = sinClasificar.slice(0, 12).map(c => escaparHtml(c.ciudad)).join(', ');
  const resto = sinClasificar.length > 12 ? ` y ${sinClasificar.length - 12} mas` : '';
  // Visible a proposito: son contactos reales de la hoja cuya ciudad no casa con
  // ninguna del catalogo. Esconderlos los haria desaparecer del ranking sin que
  // nadie se entere.
  // `role="status"`: informa, no bloquea. La lista sigue siendo usable.
  caja.innerHTML = `<div class="aviso-catalogo" role="status">`
    + `⚠ ${n} contactos en ${sinClasificar.length} ciudades que no estan en el catalogo: `
    + `${nombres}${resto}.</div>`;
}

// El nombre de la ciudad viene de LISTA DE CONTACTOS, escrito a mano, y antes de
// eso lo tecleo un operador en el campo de texto sin validacion. Se interpolaba
// crudo en DOS sitios de la misma linea: dentro del atributo onclick y como
// texto del chip. Una ciudad llamada O'Brien rompia el handler y dejaba el chip
// muerto; una con <img onerror=...> ejecutaba.
function escaparHtml(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function renderChips(lista) {
  const cont = document.getElementById('ciudades-chips');
  CHIPS = [];
  GRUPOS = [];
  chipElegido = null;
  sinResultadosPintado = false;

  if (!lista.length) {
    Estados.vacio(cont, {
      titulo: 'No hay ciudades en el catalogo',
      detalle: 'El campo de texto sigue funcionando: escribe la ciudad a mano.',
    });
    return;
  }

  // Agrupacion por macro-region. El orden de los grupos sale del ORDEN DE
  // LLEGADA, que es el de prioridad del Plan 1: la region que contiene la
  // ciudad numero 1 del pais va primera, y dentro de cada grupo se conserva
  // el mismo orden. Asi la agrupacion no destruye el ranking: lo indexa.
  const porRegion = new Map();
  lista.forEach((c) => {
    const region = c.region || 'Sin region';
    if (!porRegion.has(region)) porRegion.set(region, []);
    porRegion.get(region).push(c);
  });

  let html = '<div id="chips-lista" role="listbox" aria-labelledby="tit-ciudades">';
  porRegion.forEach((ciudades, region) => {
    const r = escaparHtml(region);
    html += `<div class="grupo" role="group" aria-label="${r}" data-region="${r}">`
      + `<div class="grupo__cabecera"><span>${r}</span>`
      + `<span class="grupo__conteo" data-conteo>${ciudades.length} ciudades</span></div>`
      + `<div class="grupo__chips">`
      + ciudades.map((c) => {
          const rank   = (c.rank != null) ? c.rank : 0;
          const medal  = rank === 1 ? '🥇 ' : rank === 2 ? '🥈 ' : rank === 3 ? '🥉 ' : `${rank}. `;
          const isTop  = rank >= 1 && rank <= 3;
          // El conteo CRUDO de ferreterias, no el puntaje. El puntaje va en escala
          // logaritmica y comprime: un 86.7 frente a un 89.8 no significa lo que el
          // operador leeria que significa. El conteo si es interpretable y auditable.
          const badge  = c.interes_pct > 0
            ? `<span class="pct">${c.interes_pct}%</span>`
            : `<span class="pct">${c.unidades_ferreteras}</span>`;
          const nombre = escaparHtml(c.ciudad);
          const porque = escaparHtml(c.explicacion || '');
          // `title` queda como DESCRIPCION accesible y `aria-label` como nombre:
          // sin el nombre explicito, un lector leia "1. Guadalajara 21%" y el
          // porcentaje sonaba a parte del nombre de la ciudad.
          const etiqueta = c.interes_pct > 0
            ? `${nombre}, posicion ${rank}, ${c.interes_pct}% de interes`
            : `${nombre}, posicion ${rank}, ${c.unidades_ferreteras} ferreterias`;
          return `<span class="chip-ciudad ${isTop ? 'top' : ''}" role="option"`
            + ` tabindex="-1" aria-selected="false" aria-label="${etiqueta}"`
            + ` data-ciudad="${nombre}" title="${porque}">${medal}${nombre} ${badge}</span>`;
        }).join('')
      + `</div></div>`;
  });
  html += '</div><div id="chips-sin-resultados" hidden></div>';
  cont.innerHTML = html;

  const raiz = document.getElementById('chips-lista');
  GRUPOS = Array.prototype.map.call(raiz.querySelectorAll('.grupo'), (g) => {
    const grupo = {
      el: g,
      conteo: g.querySelector('[data-conteo]'),
      chips: Array.prototype.slice.call(g.querySelectorAll('.chip-ciudad')),
      visibles: 0,
    };
    grupo.chips.forEach((el) => CHIPS.push({
      el: el,
      grupo: grupo,
      // En minusculas UNA vez, al construir. Hacerlo dentro del filtro son 606
      // `toLowerCase` por cada tecla pulsada.
      buscable: (el.dataset.ciudad || '').toLowerCase(),
      region: g.dataset.region || '',
    }));
    return grupo;
  });

  filtrarCiudades();
}

// Listener delegado: el nombre viaja por dataset, nunca dentro de un atributo de
// codigo. Se registra una sola vez sobre el contenedor, asi que sobrevive a cada
// re-render de los chips.
document.getElementById('ciudades-chips').addEventListener('click', (ev) => {
  const chip = ev.target.closest('.chip-ciudad');
  if (!chip) return;
  elegirChip(chip);
});

// Teclado. Antes NO habia ninguno: 606 opciones y ni una alcanzable sin raton.
// Con `tabindex` movil el conjunto es UNA sola parada de tabulacion, no 606, y
// las flechas recorren solo lo que esta visible tras el filtro.
document.getElementById('ciudades-chips').addEventListener('keydown', (ev) => {
  const chip = ev.target.closest && ev.target.closest('.chip-ciudad');
  if (!chip) return;
  if (ev.key === 'Enter' || ev.key === ' ' || ev.key === 'Spacebar') {
    ev.preventDefault();
    elegirChip(chip);
    return;
  }
  const visibles = chipsVisibles();
  const i = visibles.indexOf(chip);
  let destino = null;
  if (ev.key === 'ArrowRight' || ev.key === 'ArrowDown')     destino = visibles[i + 1];
  else if (ev.key === 'ArrowLeft' || ev.key === 'ArrowUp')   destino = visibles[i - 1];
  else if (ev.key === 'Home')                                destino = visibles[0];
  else if (ev.key === 'End')                                 destino = visibles[visibles.length - 1];
  else return;
  ev.preventDefault();
  if (!destino) return;
  chip.tabIndex = -1;
  destino.tabIndex = 0;
  destino.focus();
});

function chipsVisibles() {
  const salida = [];
  for (let i = 0; i < CHIPS.length; i++) {
    if (!CHIPS[i].el.hidden) salida.push(CHIPS[i].el);
  }
  return salida;
}

function elegirChip(chip) {
  document.getElementById('input-ciudad').value = chip.dataset.ciudad || '';
  // Antes esto recorria los 606 chips con querySelectorAll en cada clic. Se
  // recuerda cual estaba elegido y se apaga solo ese.
  if (chipElegido && chipElegido !== chip) {
    chipElegido.setAttribute('aria-selected', 'false');
  }
  chip.setAttribute('aria-selected', 'true');
  chipElegido = chip;
  // La parada de tabulacion se reparte aqui y no a mano: poner `tabIndex = 0`
  // en el elegido sin apagar el que ya la tenia dejaba la lista con DOS
  // paradas -la del primer chip visible y la del recien elegido-.
  fijarParadaDeTabulacion();
  limpiarAvisoInicio();
}

// La marca de seleccion tiene que decir la verdad sobre lo que se va a buscar.
// Si el operador escribe otra ciudad a mano, el chip anterior deja de
// corresponder con el campo, y dejarlo marcado afirma algo que ya no es cierto.
document.getElementById('input-ciudad').addEventListener('input', () => {
  if (!chipElegido) return;
  const escrito = document.getElementById('input-ciudad').value.trim();
  if (escrito === (chipElegido.dataset.ciudad || '')) return;
  chipElegido.setAttribute('aria-selected', 'false');
  chipElegido = null;
  fijarParadaDeTabulacion();
});

// El chip que se lleva la parada de tabulacion es el elegido si sigue visible, y
// si no el primero de la lista filtrada. Sin esto, filtrar dejaba el `tabindex`
// en un chip oculto y el teclado no entraba a la lista.
function fijarParadaDeTabulacion() {
  const visibles = chipsVisibles();
  const activo = (chipElegido && !chipElegido.hidden) ? chipElegido : visibles[0];
  for (let i = 0; i < CHIPS.length; i++) {
    const el = CHIPS[i].el;
    const valor = (el === activo) ? 0 : -1;
    if (el.tabIndex !== valor) el.tabIndex = valor;
  }
}

function filtrarCiudades() {
  const q = document.getElementById('ciudad-filter').value.toLowerCase().trim();
  const region = document.getElementById('region-filter').value;
  // Los dos filtros se COMBINAN. Aplicar solo el ultimo que se toco haria que
  // escribir en el buscador ignorara la region elegida, y al reves.
  let visibles = 0;
  for (let g = 0; g < GRUPOS.length; g++) GRUPOS[g].visibles = 0;

  for (let i = 0; i < CHIPS.length; i++) {
    const c = CHIPS[i];
    const casa = (!region || c.region === region) && (!q || c.buscable.includes(q));
    // Se escribe SOLO si cambia: asignar `hidden` a los 606 en cada pulsacion
    // invalida el estilo de todos aunque el valor sea el mismo.
    if (c.el.hidden === casa) c.el.hidden = !casa;
    if (casa) { visibles++; c.grupo.visibles++; }
  }

  // Contador por grupo, en vivo. Un grupo sin coincidencias se retira entero,
  // cabecera incluida: dejar la cabecera de una region vacia es ruido.
  for (let g = 0; g < GRUPOS.length; g++) {
    const grupo = GRUPOS[g];
    const oculto = grupo.visibles === 0;
    if (grupo.el.hidden !== oculto) grupo.el.hidden = oculto;
    const texto = (grupo.visibles === grupo.chips.length)
      ? `${grupo.chips.length} ciudades`
      : `${grupo.visibles} de ${grupo.chips.length}`;
    if (grupo.conteo && grupo.conteo.textContent !== texto) grupo.conteo.textContent = texto;
  }

  pintarResumenChips(visibles, region, q);
  pintarSinResultados(visibles);
  fijarParadaDeTabulacion();
}

let temporizadorResumen = null;
const RETARDO_ANUNCIO = 600;

function pintarResumenChips(visibles, region, q) {
  const caja = document.getElementById('chips-resumen');
  if (!caja) return;
  if (!CHIPS.length) { caja.textContent = ''; return; }
  const partes = [`${visibles} de ${CHIPS.length} ciudades`];
  if (region) partes.push(region);
  if (q) partes.push(`filtro "${q}"`);
  const texto = partes.join(' · ');
  if (caja.textContent !== texto) caja.textContent = texto;

  // El anuncio va aparte y con retardo. `filtrarCiudades` corre en el `oninput`
  // del buscador, asi que una region viva ahi dentro interrumpe al lector una
  // vez por cada letra tecleada, encima del eco de la propia tecla. El texto
  // VISIBLE si se actualiza al instante, que es lo que el operador espera ver.
  const vivo = document.getElementById('chips-resumen-lectores');
  if (!vivo) return;
  clearTimeout(temporizadorResumen);
  temporizadorResumen = setTimeout(() => {
    if (vivo.textContent !== texto) vivo.textContent = texto;
  }, RETARDO_ANUNCIO);
}

function pintarSinResultados(visibles) {
  const caja = document.getElementById('chips-sin-resultados');
  if (!caja) return;
  const vacio = (visibles === 0 && CHIPS.length > 0);
  if (vacio && !sinResultadosPintado) {
    Estados.vacio(caja, {
      titulo: 'Ninguna ciudad coincide',
      detalle: 'Cambia el texto del filtro o elige otra region.',
    });
    sinResultadosPintado = true;
  } else if (!vacio) {
    sinResultadosPintado = false;
  }
  if (caja.hidden !== !vacio) caja.hidden = !vacio;
}

cargarCiudades();

// ── Sondeo ────────────────────────────────────────────────────────────────
// Antes: setInterval fijo de 3 s que solo paraba en 'done' o 'error'. Si el
// contenedor se reiniciaba, el estado llegaba 'idle' para siempre y el sondeo
// seguia latiendo indefinidamente contra un trabajo que ya no existia.
let intervaloSondeo = 3000;
let ciclosIdle = 0;          // el panel responde, pero dice que no hay trabajo
let ciclosSinRespuesta = 0;  // el panel no responde
const MAX_CICLOS_IDLE = 5;
const MAX_CICLOS_SIN_RESPUESTA = 5;

function arrancarSondeo(ms) {
  clearInterval(polling);          // sin esto quedaban dos intervalos vivos
  intervaloSondeo = ms || 3000;
  polling = setInterval(actualizarEstado, intervaloSondeo);
}

function pararSondeo() {
  clearInterval(polling);
  polling = null;
}

// La barra avanza con `scaleX`, no con `width`. Animar el ancho obliga al
// navegador a recalcular layout en cada cuadro, y una corrida del importador
// son minutos de barra moviendose sin parar. `will-change` se pone solo
// mientras hay corrida y se RETIRA al acabar: dejarlo puesto reserva una capa
// de composicion permanente para un elemento que el resto del tiempo no se
// mueve.
function ponerAvance(pct) {
  const fill = document.getElementById('prog-fill');
  const v = Math.max(0, Math.min(100, Number(pct) || 0));
  fill.style.setProperty('--avance', (v / 100).toFixed(4));
  // El valor tambien va al ARIA: sin `aria-valuenow` la barra no expone
  // ningun avance a un lector de pantalla, y una corrida son minutos. No se
  // usa `aria-live`: con sondeo cada pocos segundos serian decenas de
  // anuncios. `role=progressbar` se lee cuando el operador navega al control.
  const pista = document.getElementById('prog-track');
  if (pista) pista.setAttribute('aria-valuenow', String(Math.round(v)));
  if (v > 0 && v < 100) fill.style.willChange = 'transform';
  else fill.style.willChange = '';
}

// La corrida termino, acabe como acabe. `ponerAvance` solo suelta la capa de
// composicion en 0 y en 100, y una corrida cancelada al 42 % no pasa por
// ninguno de los dos: `fraccion` es monotona y el backend NO la normaliza a
// 100 al cancelar, al agotarse el presupuesto, al interrumpirse ni al fallar.
// El `will-change` se quedaba puesto hasta la siguiente busqueda.
function soltarAvance() {
  const fill = document.getElementById('prog-fill');
  if (fill) fill.style.willChange = '';
}

// ── Fase, registro y avisos ───────────────────────────────────────────────

function ponerFase(texto, tono) {
  const el = document.getElementById('prog-fase');
  if (!el) return;
  el.textContent = texto;
  el.className = 'insignia insignia--' + (tono || 'info');
}

// El registro se ANADE. Reescribir el innerHTML entero en cada sondeo hacia
// parpadear el bloque, reiniciaba la animacion de todas las lineas y devolvia
// el scroll al final aunque el operador estuviera leyendo mas arriba.
let logPintado = [];
const MAX_LINEAS_LOG = 200;

// Se pidio detener y el backend todavia no lo ha confirmado.
let detencionPedida = false;

function pintarLog(lineas) {
  const caja = document.getElementById('log-box');
  if (!caja) return;
  lineas = lineas || [];

  // El backend manda SOLO las diez ultimas, asi que la ventana se desplaza. Se
  // busca cuanto del bloque anterior sigue al principio del nuevo y se anade
  // unicamente el resto.
  let comunes = 0;
  for (let k = Math.min(logPintado.length, lineas.length); k > 0; k--) {
    const cola = logPintado.slice(logPintado.length - k).join('\u0000');
    if (cola === lineas.slice(0, k).join('\u0000')) { comunes = k; break; }
  }
  const nuevas = lineas.slice(comunes);
  logPintado = lineas.slice();
  if (!nuevas.length) return;

  // Solo se sigue al final si el operador YA estaba al final. Si se subio a
  // leer una linea, arrastrarlo abajo cada tres segundos es hostil.
  const alFinal = (caja.scrollHeight - caja.scrollTop - caja.clientHeight) < 8;

  nuevas.forEach((l, i) => {
    const linea = document.createElement('div');
    linea.className = 'entry';
    // textContent, no innerHTML: la linea trae nombres que vienen de Places y
    // de la hoja.
    linea.textContent = l;
    if (!MOVIMIENTO_REDUCIDO.matches) {
      linea.style.setProperty('--retardo-fila', (i * 25) + 'ms');
      linea.classList.add('fila-entra');
      // La clase se retira al terminar: si se queda puesta, el elemento sigue
      // marcado como "recien llegado" para siempre.
      linea.addEventListener('animationend',
        () => linea.classList.remove('fila-entra'), { once: true });
    }
    caja.appendChild(linea);
  });

  while (caja.childElementCount > MAX_LINEAS_LOG) caja.removeChild(caja.firstElementChild);
  if (alFinal) caja.scrollTop = caja.scrollHeight;
}

// Lo que antes eran cuatro `alert()`. Un alert bloquea la pagina, roba el foco
// y al aceptarlo no deja rastro de lo que dijo.
function avisoInicio(titulo, detalle, opciones) {
  const caja = document.getElementById('aviso-inicio');
  if (!caja) return;
  opciones = opciones || {};
  if (typeof opciones.reintentar === 'function') {
    Estados.error(caja, {
      titulo: titulo,
      detalle: detalle,
      reintentar: opciones.reintentar,
    });
    return;
  }
  // Sin accion de reintento no se usa `Estados.error`, que exige salida: se
  // pinta el bloque de aviso con el rol que corresponde a su gravedad.
  const rol = opciones.rol || 'alert';
  const clase = opciones.clase || 'estado--error';
  caja.innerHTML = '<div class="estado ' + clase + '" role="' + rol + '">'
    + '<div class="estado__titulo">' + Estados.escapar(titulo) + '</div>'
    + (detalle ? '<div class="estado__detalle">' + Estados.escapar(detalle) + '</div>' : '')
    + '</div>';
}

function limpiarAvisoInicio() {
  const caja = document.getElementById('aviso-inicio');
  if (caja) caja.innerHTML = '';
  const campo = document.getElementById('input-ciudad');
  if (campo) campo.removeAttribute('aria-invalid');
}

// ── Paneles ───────────────────────────────────────────────────────────────

function limpiarPantalla() {
  // La corrida anterior dejaba sus numeros y sus insignias puestos: la segunda
  // busqueda de la sesion arrancaba con todo marcado como completado.
  ['s-nuevos','s-encontrados','s-duplicados','s-descartados'].forEach(id => {
    document.getElementById(id).textContent = '0';
  });
  document.getElementById('s-progreso').textContent = '0/0';
  ponerAvance(0);
  document.getElementById('prog-pct').textContent = '0%';
  document.getElementById('prog-label').textContent = 'Preparando la búsqueda…';
  ponerFase('Iniciando…', 'info');
  document.getElementById('log-box').innerHTML = '';
  logPintado = [];
  // El medidor conservaba las llamadas y el costo de la corrida ANTERIOR hasta
  // que llegaba el primer sondeo: unos segundos afirmando un gasto que no es
  // el de esta busqueda.
  ['m-llamadas','m-ahorro','m-costo'].forEach(id => {
    document.getElementById(id).textContent = '';
  });
  detencionPedida = false;
  CATS.forEach((_, i) => document.getElementById('cat-'+i).className = 'cat-badge');
  ciclosIdle = 0;
  ciclosSinRespuesta = 0;
}

const PANELES = ['progress-box', 'stats-row', 'progreso-row', 'medidor-box', 'log-seccion'];

function mostrarPaneles() {
  PANELES.forEach((id) => {
    const el = document.getElementById(id);
    if (!el) return;
    const estaba = el.hidden;
    el.hidden = false;
    // Movimiento narrativo: la seccion entra cuando aparece por primera vez, no
    // en cada sondeo. Es lo que hace legible que la corrida acaba de arrancar.
    if (estaba && !MOVIMIENTO_REDUCIDO.matches) {
      el.classList.add('seccion-entra');
      el.addEventListener('animationend',
        () => el.classList.remove('seccion-entra'), { once: true });
    }
  });
  const resultado = document.getElementById('result-box');
  if (resultado) resultado.hidden = true;
}

function llevarALaCorrida() {
  const caja = document.getElementById('progress-box');
  if (!caja || caja.hidden || !caja.scrollIntoView) return;
  // `smooth` solo si el operador no pidio lo contrario: un desplazamiento
  // animado es justo el tipo de movimiento que la preferencia retira.
  caja.scrollIntoView({
    behavior: MOVIMIENTO_REDUCIDO.matches ? 'auto' : 'smooth',
    block: 'start',
  });
}

function ponerEnMarcha(enMarcha) {
  const btn = document.getElementById('btn-iniciar');
  btn.disabled = enMarcha;
  btn.textContent = enMarcha ? '⏳ Buscando...' : '🔍 Buscar';
  // El campo nunca se deshabilitaba, asi que pulsar Enter a media corrida
  // relanzaba iniciar() y podia arrancar una SEGUNDA importacion.
  document.getElementById('input-ciudad').disabled = enMarcha;
  document.getElementById('btn-cancelar').hidden = !enMarcha;
  if (!enMarcha) cerrarConfirmacionDetener();
}

async function iniciar() {
  const campo = document.getElementById('input-ciudad');
  const ciudad = campo.value.trim();
  if (!ciudad) {
    // Antes: alert('Ingresa una ciudad'). Ahora el error vive junto al campo,
    // se anuncia, y el foco vuelve a donde hay que escribir.
    campo.setAttribute('aria-invalid', 'true');
    avisoInicio('Escribe o elige una ciudad', 'Sin ciudad no hay nada que buscar.');
    campo.focus();
    return;
  }
  limpiarAvisoInicio();
  ponerEnMarcha(true);
  limpiarPantalla();
  mostrarPaneles();

  try {
    const r = await fetch('/api/importador/iniciar', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ciudad})
    });
    const d = await r.json();
    if (!d.ok) {
      avisoInicio('No se pudo iniciar la búsqueda', d.error || '', { reintentar: iniciar });
      ponerFase('Sin arrancar', 'error');
      ponerEnMarcha(false);
      return;
    }
    arrancarSondeo(3000);
    actualizarEstado();
    // El relato queda debajo de la caja de ciudades, que mide 240 px: sin
    // esto, el operador pulsa Buscar y no ve arrancar nada. Se lleva la vista
    // a la barra, que es donde empieza a pasar algo.
    llevarALaCorrida();
  } catch (e) {
    // Sin este catch la promesa reventaba y el boton se quedaba en
    // "Buscando..." deshabilitado para siempre: hacia falta recargar.
    document.getElementById('prog-label').textContent =
      'No se pudo contactar con el panel: ' + e;
    ponerFase('Sin contacto', 'error');
    avisoInicio('No se pudo contactar con el panel', String(e), { reintentar: iniciar });
    ponerEnMarcha(false);
  }
}

// Detener es una decision, y una decision no se pide con un `confirm()` del
// navegador: bloquea la pagina y no se puede leer con el estado de la corrida
// delante. La confirmacion vive en la pagina, junto al boton.
function pedirDetener() {
  const caja = document.getElementById('aviso-inicio');
  if (!caja) return;
  // `role="group"`, NO `alertdialog`. Un `alertdialog` es por definicion modal:
  // exige `aria-modal`, trampa de foco y el resto de la pagina inerte. Aqui no
  // hay ninguna de las tres a proposito -el ADR descarta el bloqueo del
  // `confirm()`-, asi que anunciarlo como dialogo modal seria decirle al lector
  // algo que no es cierto.
  //
  // OJO al tocar esto: el HTML se arma a mano y hoy no interpola NINGUN dato
  // externo. Si algun dia lleva la ciudad o un mensaje del backend, tiene que
  // pasar por `Estados.escapar` como el resto.
  caja.innerHTML =
    '<div class="estado estado--parcial" role="group" aria-labelledby="detener-titulo"'
    + ' aria-describedby="detener-detalle">'
    + '<div class="estado__titulo" id="detener-titulo">¿Detener la búsqueda?</div>'
    + '<div class="estado__detalle" id="detener-detalle">Lo que ya se guardó en la hoja se queda, '
    + 'y volver a correr la misma ciudad no lo duplica.</div>'
    + '<div class="estado__accion">'
    + '<button type="button" class="btn btn--error" id="btn-detener-si">Sí, detener</button>'
    + '<button type="button" class="btn btn--secundario" id="btn-detener-no">Seguir buscando</button>'
    + '</div></div>';
  const si = document.getElementById('btn-detener-si');
  const no = document.getElementById('btn-detener-no');
  if (si) si.addEventListener('click', cancelar);
  if (no) no.addEventListener('click', () => {
    cerrarConfirmacionDetener();
    const volver = document.getElementById('btn-cancelar');
    if (volver && !volver.hidden) volver.focus();
  });
  // El foco arranca en la opcion SEGURA. Con el foco en "Sí, detener", un
  // Enter reflejo -el operador viene de pulsar un boton- cancela la corrida sin
  // haber leido la pregunta.
  if (no) no.focus();
}

function cerrarConfirmacionDetener() {
  const caja = document.getElementById('aviso-inicio');
  if (caja && caja.querySelector('#btn-detener-si')) caja.innerHTML = '';
}

async function cancelar() {
  cerrarConfirmacionDetener();
  // `cerrarConfirmacionDetener` acaba de destruir el boton que tenia el foco.
  // Sin esto el foco cae a <body> y quien navega con teclado pierde su sitio;
  // se lleva al registro, que es donde va a aparecer la respuesta ("Cancelación
  // pedida; terminando el paso en curso…").
  const registro = document.getElementById('log-box');
  const seccion = document.getElementById('log-seccion');
  if (registro && seccion && !seccion.hidden) registro.focus();

  // El worker comprueba la bandera ENTRE pasos, asi que hasta el siguiente
  // sondeo el backend sigue diciendo 'running' con su fase real. Sin esta
  // bandera, "Deteniendo…" aparecia y desaparecia en menos de tres segundos.
  detencionPedida = true;
  ponerFase('Deteniendo…', 'aviso');
  try {
    const r = await fetch('/api/importador/cancelar', {method: 'POST'});
    const d = await r.json();
    if (!d.ok) {
      detencionPedida = false;
      avisoInicio('No se pudo detener', d.error || 'No hay ninguna búsqueda en curso.');
    }
  } catch (e) {
    detencionPedida = false;
    avisoInicio('No se pudo contactar con el panel', String(e));
  }
}

async function restaurarEstado() {
  // Al abrir la pagina se pregunta si hay algo corriendo. Antes solo iniciar()
  // arrancaba el sondeo, asi que recargar a media corrida dejaba la pantalla
  // inerte y el operador encerrado fuera de su propio trabajo.
  try {
    const d = await (await fetch('/api/importador/estado')).json();
    if (d.status === 'running') {
      mostrarPaneles();
      ponerEnMarcha(true);
      pintarEstado(d);
      arrancarSondeo(3000);
    } else if (d.status !== 'idle') {
      // done, error, cancelado e interrumpido: la corrida anterior sigue en
      // memoria y el operador tiene derecho a verla al volver a la pagina.
      // Antes solo se contemplaban 'running' e 'interrumpido', asi que recargar
      // tras un fallo dejaba la pantalla en blanco, sin rastro del error.
      mostrarPaneles();
      pintarEstado(d);
      rematar(d);
    }
  } catch (e) {
    // Que falle la restauracion no puede impedir usar la pagina.
    console.warn('No se pudo restaurar el estado del importador:', e);
  }
}

function pintarEstado(d) {
  const pct = d.fraccion || 0;
  ponerAvance(pct);
  document.getElementById('prog-pct').textContent   = pct + '%';
  // La FASE va en su propia insignia junto a la barra; la linea de abajo dice
  // que ciudad y que categoria, que antes se perdian.
  if (detencionPedida && d.status === 'running') {
    ponerFase('Deteniendo…', 'aviso');
  } else {
    ponerFase(d.fase || (d.categoria ? `Buscando: ${d.categoria}` : 'Procesando…'),
              d.status === 'running' ? 'info' : 'aviso');
  }
  document.getElementById('prog-label').textContent =
    [d.ciudad, d.categoria].filter(Boolean).join(' · ') || 'Preparando la búsqueda…';

  document.getElementById('s-nuevos').textContent      = d.nuevos_en_sheet;
  document.getElementById('s-encontrados').textContent = d.encontrados;
  document.getElementById('s-duplicados').textContent  = d.duplicados;
  document.getElementById('s-descartados').textContent = d.descartados;
  document.getElementById('s-progreso').textContent    = `${d.progreso}/${d.total}`;

  const m = d.medidor || {};
  document.getElementById('m-llamadas').textContent =
    `Llamadas a Google: ${m.text_search || 0} búsquedas + ${m.place_details || 0} detalles`;
  const evitadas = (m.cache_hits || 0) + (m.duplicados_evitados || 0);
  document.getElementById('m-ahorro').textContent = evitadas ? ` · ${evitadas} evitadas` : '';
  // Sin tarifas configuradas no se inventa un importe: un 0.00 se leeria como
  // "esta corrida salio gratis", que no es lo mismo que "no lo sé".
  document.getElementById('m-costo').textContent =
    (m.costo === null || m.costo === undefined) ? '' : ` · costo estimado ${m.costo.toFixed(2)}`;

  CATS.forEach((c, i) => {
    const el = document.getElementById('cat-'+i);
    if (i < d.progreso) el.className = 'cat-badge done';
    else if (d.categoria === c) el.className = 'cat-badge active';
    else el.className = 'cat-badge';       // sin esta rama se quedaban rancias
    // El estado se veia SOLO por el color de fondo. Ahora tambien es texto y
    // `aria-current`, que es lo unico que llega a un lector de pantalla.
    const estado = document.getElementById('cat-estado-'+i);
    if (estado) {
      estado.textContent = (i < d.progreso) ? ' (completada)'
        : (d.categoria === c ? ' (en curso)' : '');
    }
    if (d.categoria === c) el.setAttribute('aria-current', 'step');
    else el.removeAttribute('aria-current');
  });

  pintarLog(d.log);
}

async function actualizarEstado() {
  let d;
  try {
    const r = await fetch('/api/importador/estado');
    d = await r.json();
  } catch (e) {
    // Un corte de red no puede dejar el sondeo latiendo a ciegas: se espacia y,
    // si no vuelve, se para solo.
    ciclosSinRespuesta++;
    if (ciclosSinRespuesta >= MAX_CICLOS_SIN_RESPUESTA) {
      pararSondeo();
      document.getElementById('prog-label').textContent =
        'Se perdió el contacto con el panel.';
      ponerFase('Sin contacto', 'error');
      avisoInicio('Se perdió el contacto con el panel',
                  'Recarga la página: lo que ya se guardó en la hoja sigue ahí.');
      ponerEnMarcha(false);
    } else if (intervaloSondeo < 15000) {
      arrancarSondeo(intervaloSondeo * 2);
    }
    return;
  }

  if (d.status === 'idle') {
    // El contenedor se reinicio a media corrida: el trabajo ya no existe.
    ciclosIdle++;
    if (ciclosIdle >= MAX_CICLOS_IDLE) {
      pararSondeo();
      document.getElementById('prog-label').textContent =
        'La corrida ya no está en curso (el panel se reinició).';
      ponerFase('Sin corrida', 'aviso');
      avisoInicio('La corrida ya no está en curso',
                  'El panel se reinició. Lo que ya se guardó en la hoja sigue ahí.',
                  { rol: 'status', clase: 'estado--parcial' });
      ponerEnMarcha(false);
    }
    return;
  }
  ciclosIdle = 0;
  ciclosSinRespuesta = 0;

  pintarEstado(d);

  // El sondeo se espacia si la corrida se alarga, en vez de 3 s eternos.
  if (intervaloSondeo < 10000 && (d.fraccion || 0) > 0 && (d.fraccion || 0) < 90) {
    const deseado = Math.min(10000, intervaloSondeo + 1000);
    if (deseado !== intervaloSondeo) arrancarSondeo(deseado);
  }

  if (d.status !== 'running') rematar(d);
}

// El recuadro de resultado traia un `✅` fijo en la plantilla, asi que una
// corrida detenida a mano, agotada por presupuesto, interrumpida por un
// reinicio o caida con error se remataba con una marca de exito verde. El
// icono sale ahora del estado real: la celebracion queda reservada a `done`,
// que es el unico verificado (ADR de direccion visual, voto del Critico).
// Los cuatro llevan selector de variacion (U+FE0F) a proposito. Sin el,
// `⏹` y `⚠` caen en presentacion de TEXTO -medido: 34.5 px de ancho contra
// 54.9 px de los que si son emoji- y se ven como un cuadro negro plano al lado
// de `✅` y `⛔`, que si tienen color. No era tofu: era la otra presentacion
// del mismo caracter, que es peor porque parece un fallo de fuente.
const ICONO_RESULTADO = {
  done: '✅',
  cancelado: '⏹️',
  presupuesto_agotado: '⛔',
  interrumpido: '⚠️',
  error: '⚠️',
};

// Y la misma regla en el color: detenido a mano y tope de gasto NO son
// errores -son decisiones, una del operador y otra del presupuesto- asi que
// no se visten de rojo; pero tampoco de verde, porque no completaron.
const CLASE_RESULTADO = {
  done: 'resultado--exito',
  cancelado: 'resultado--detenido',
  presupuesto_agotado: 'resultado--tope',
  interrumpido: 'resultado--tope',
  error: 'resultado--error',
};

const FASE_FINAL = {
  done: ['Completado', 'exito'],
  cancelado: ['Detenido a mano', 'info'],
  presupuesto_agotado: ['Tope de gasto', 'aviso'],
  interrumpido: ['Interrumpido', 'aviso'],
  error: ['Falló', 'error'],
};

function ponerIconoResultado(status) {
  document.getElementById('result-icono').textContent = ICONO_RESULTADO[status] || '⚠';
}

function vestirResultado(status) {
  const caja = document.getElementById('result-box');
  caja.className = 'resultado ' + (CLASE_RESULTADO[status] || 'resultado--tope');
  // Un fallo INTERRUMPE (alert); los demas finales informan (status). El rol se
  // pone antes de mostrar la caja para que el cambio de contenido posterior sea
  // una mutacion de region viva y llegue al lector.
  caja.setAttribute('role', status === 'error' ? 'alert' : 'status');
  caja.hidden = false;
  ponerIconoResultado(status);
  const fase = FASE_FINAL[status] || FASE_FINAL.interrumpido;
  ponerFase(fase[0], fase[1]);
}

function rematar(d) {
  if (d.status === 'done' || d.status === 'cancelado' || d.status === 'interrumpido'
      || d.status === 'presupuesto_agotado') {
    pararSondeo();
    ponerEnMarcha(false);
    soltarAvance();
    document.getElementById('btn-iniciar').textContent = '🔍 Nueva Búsqueda';
    vestirResultado(d.status);

    if (d.status === 'done') {
      document.getElementById('result-titulo').textContent =
        `${d.nuevos_en_sheet} contactos nuevos en la hoja — ${d.ciudad}`;
      document.getElementById('result-desc').textContent =
        `De ${d.encontrados + d.descartados} candidatos de Google, ${d.encontrados} pasaron los ` +
        `filtros de calidad: ${d.nuevos_en_sheet} se guardaron y ${d.duplicados} ya estaban en la lista. ` +
        `Los otros ${d.descartados} se descartaron por reseñas, calificación o falta de teléfono.`;
    } else {
      const titulos = {
        cancelado: 'Búsqueda detenida — ',
        presupuesto_agotado: 'Se alcanzó el tope de gasto — ',
        interrumpido: 'Búsqueda interrumpida — ',
      };
      document.getElementById('result-titulo').textContent =
        (titulos[d.status] || 'Búsqueda sin completar — ') + d.ciudad;
      document.getElementById('result-desc').textContent =
        (d.status === 'presupuesto_agotado' ? d.error + ' ' : '') +
        `Se alcanzaron a guardar ${d.nuevos_en_sheet} contactos nuevos, y siguen en la hoja. ` +
        `Volver a correr la misma ciudad no los duplica.`;
    }
  }

  if (d.status === 'error') {
    pararSondeo();
    ponerEnMarcha(false);
    soltarAvance();
    document.getElementById('prog-label').textContent = 'Error: ' + d.error;
    document.getElementById('btn-iniciar').textContent = '🔍 Reintentar';
    vestirResultado('error');
    document.getElementById('result-titulo').textContent = 'La búsqueda falló — ' + d.ciudad;
    document.getElementById('result-desc').textContent =
      (d.error || '') + ` Se alcanzaron a guardar ${d.nuevos_en_sheet} contactos nuevos.`;
  }
}

restaurarEstado();
