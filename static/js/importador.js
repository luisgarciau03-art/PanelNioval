const CATS = ["Ferreterías","Distribuidoras Ferreterías"];
let polling = null;

// Render categoria badges
document.getElementById('cats-list').innerHTML = CATS.map((c,i) =>
  `<div class="cat-badge" id="cat-${i}">${c}</div>`
).join('');

// Aqui vivia el array estatico: 293 entradas escritas a mano, 50 nombres
// duplicados y 9 con la abreviatura del estado pegada, que viajaba literal a
// Google Places ("Ferreterias en Santiago Ixc"). Lo sustituye el catalogo
// nacional de datos/ciudades_mx.json, que sirve /api/importador/ciudades ya
// ordenado y con la explicacion de cada posicion armada en el servidor.
let todasCiudades = [];
let sinClasificar = [];

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
      document.getElementById('sin-clasificar').innerHTML =
        '<div style="font-size:.75em;color:#a94442;background:#f2dede;border:1px solid #ebccd1;'
        + 'border-radius:8px;padding:6px 9px;margin-bottom:10px">'
        + '⚠ El servidor no pudo leer el catalogo de ciudades. Escribe la ciudad a mano.</div>';
      todasCiudades = [];
    }

    // El rango se fija UNA vez sobre el catalogo completo. Si se calculara en
    // renderChips sobre la lista recibida, al escribir en el filtro la ciudad
    // numero 47 apareceria con medalla de oro.
    todasCiudades.forEach((c, i) => { c.rank = i + 1; });

    pintarRegiones(d.regiones || []);
    document.getElementById('ciudades-count').textContent = `(${todasCiudades.length})`;
    renderChips(todasCiudades);
    pintarSinClasificar();
  } catch (e) {
    // Sin catalogo NO se inventa una lista: se dice que no se pudo cargar y se
    // deja el campo de texto, que sigue aceptando cualquier ciudad. Un fallback
    // silencioso a una lista vieja seria peor que no tener lista.
    todasCiudades = [];
    document.getElementById('ciudades-count').textContent = '';
    cont.innerHTML = '<div style="color:#c0392b;font-size:.82em;padding:6px">'
      + 'No se pudo cargar el catalogo de ciudades. Escribe la ciudad a mano.</div>';
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
  caja.innerHTML = `<div style="font-size:.75em;color:#8a6d3b;background:#fcf8e3;`
    + `border:1px solid #faebcc;border-radius:8px;padding:6px 9px;margin-bottom:10px">`
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
  if (!lista.length) { cont.innerHTML = '<div style="color:#aaa;font-size:.82em">Sin resultados</div>'; return; }

  cont.innerHTML = lista.map((c) => {
    const rank   = (c.rank != null) ? c.rank : 0;
    const medal  = rank === 1 ? '🥇 ' : rank === 2 ? '🥈 ' : rank === 3 ? '🥉 ' : `${rank}. `;
    const isTop  = rank >= 1 && rank <= 3;
    // El conteo CRUDO de ferreterias, no el puntaje. El puntaje va en escala
    // logaritmica y comprime: un 86.7 frente a un 89.8 no significa lo que el
    // operador leeria que significa. El conteo si es interpretable y auditable.
    const badge  = c.interes_pct > 0
      ? `<span style="background:rgba(0,204,71,.2);color:#155724;padding:1px 5px;border-radius:8px;font-size:.85em">${c.interes_pct}%</span>`
      : `<span style="opacity:.55;font-size:.85em">${c.unidades_ferreteras}</span>`;
    const nombre = escaparHtml(c.ciudad);
    const porque = escaparHtml(c.explicacion || '');
    return `<span class="chip ${isTop?'top':''}" data-ciudad="${nombre}" title="${porque}">${medal}${nombre} ${badge}</span>`;
  }).join('');
}

// Listener delegado: el nombre viaja por dataset, nunca dentro de un atributo de
// codigo. Se registra una sola vez sobre el contenedor, asi que sobrevive a cada
// re-render de los chips.
document.getElementById('ciudades-chips').addEventListener('click', (ev) => {
  const chip = ev.target.closest('.chip');
  if (!chip) return;
  document.getElementById('input-ciudad').value = chip.dataset.ciudad || '';
  document.querySelectorAll('.chip').forEach(c => c.classList.remove('active'));
  chip.classList.add('active');
});

function filtrarCiudades() {
  const q = document.getElementById('ciudad-filter').value.toLowerCase().trim();
  const region = document.getElementById('region-filter').value;
  // Los dos filtros se COMBINAN. Aplicar solo el ultimo que se toco haria que
  // escribir en el buscador ignorara la region elegida, y al reves.
  let lista = todasCiudades;
  if (region) lista = lista.filter(c => c.region === region);
  if (q)      lista = lista.filter(c => c.ciudad.toLowerCase().includes(q));
  renderChips(lista);
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

function limpiarPantalla() {
  // La corrida anterior dejaba sus numeros y sus insignias puestos: la segunda
  // busqueda de la sesion arrancaba con todo marcado como completado.
  ['s-nuevos','s-encontrados','s-duplicados','s-descartados'].forEach(id => {
    document.getElementById(id).textContent = '0';
  });
  document.getElementById('s-progreso').textContent = '0/0';
  document.getElementById('prog-fill').style.width = '0%';
  document.getElementById('prog-pct').textContent = '0%';
  document.getElementById('log-box').innerHTML = '';
  CATS.forEach((_, i) => document.getElementById('cat-'+i).className = 'cat-badge');
  ciclosIdle = 0;
  ciclosSinRespuesta = 0;
}

function mostrarPaneles() {
  document.getElementById('progress-box').style.display = 'block';
  document.getElementById('stats-row').style.display = 'grid';
  document.getElementById('progreso-row').style.display = 'grid';
  document.getElementById('medidor-box').style.display = 'block';
  document.getElementById('log-box').style.display = 'block';
  document.getElementById('result-box').style.display = 'none';
}

function ponerEnMarcha(enMarcha) {
  const btn = document.getElementById('btn-iniciar');
  btn.disabled = enMarcha;
  btn.textContent = enMarcha ? '⏳ Buscando...' : '🔍 Buscar';
  // El campo nunca se deshabilitaba, asi que pulsar Enter a media corrida
  // relanzaba iniciar() y podia arrancar una SEGUNDA importacion.
  document.getElementById('input-ciudad').disabled = enMarcha;
  document.getElementById('btn-cancelar').style.display = enMarcha ? 'inline-flex' : 'none';
}

async function iniciar() {
  const ciudad = document.getElementById('input-ciudad').value.trim();
  if (!ciudad) { alert('Ingresa una ciudad'); return; }

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
      alert('Error: ' + d.error);
      ponerEnMarcha(false);
      return;
    }
    arrancarSondeo(3000);
    actualizarEstado();
  } catch (e) {
    // Sin este catch la promesa reventaba y el boton se quedaba en
    // "Buscando..." deshabilitado para siempre: hacia falta recargar.
    document.getElementById('prog-label').textContent =
      '❌ No se pudo contactar con el panel: ' + e;
    ponerEnMarcha(false);
  }
}

async function cancelar() {
  if (!confirm('¿Detener la búsqueda? Lo que ya se guardó en la hoja se queda.')) return;
  try {
    const r = await fetch('/api/importador/cancelar', {method: 'POST'});
    const d = await r.json();
    if (!d.ok) alert(d.error || 'No se pudo cancelar');
  } catch (e) {
    alert('No se pudo contactar con el panel: ' + e);
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
  document.getElementById('prog-fill').style.width  = pct + '%';
  document.getElementById('prog-pct').textContent   = pct + '%';
  document.getElementById('prog-label').textContent =
    d.fase || (d.categoria ? `Buscando: ${d.categoria}...` : 'Procesando...');

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
  });

  const logEl = document.getElementById('log-box');
  logEl.innerHTML = (d.log || []).map(l => `<div class="entry">> ${escaparHtml(l)}</div>`).join('');
  logEl.scrollTop = logEl.scrollHeight;
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
        '❌ Se perdió el contacto con el panel. Recarga la página.';
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
        '⚠ La corrida ya no está en curso (el panel se reinició).';
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

function rematar(d) {
  if (d.status === 'done' || d.status === 'cancelado' || d.status === 'interrumpido'
      || d.status === 'presupuesto_agotado') {
    pararSondeo();
    ponerEnMarcha(false);
    document.getElementById('btn-iniciar').textContent = '🔍 Nueva Búsqueda';
    document.getElementById('result-box').style.display = 'block';

    if (d.status === 'done') {
      document.getElementById('prog-label').textContent = '¡Completado!';
      document.getElementById('result-titulo').textContent =
        `✅ ${d.nuevos_en_sheet} contactos nuevos en la hoja — ${d.ciudad}`;
      document.getElementById('result-desc').textContent =
        `De ${d.encontrados + d.descartados} candidatos de Google, ${d.encontrados} pasaron los ` +
        `filtros de calidad: ${d.nuevos_en_sheet} se guardaron y ${d.duplicados} ya estaban en la lista. ` +
        `Los otros ${d.descartados} se descartaron por reseñas, calificación o falta de teléfono.`;
    } else {
      const titulos = {
        cancelado: '⏹ Búsqueda detenida — ',
        presupuesto_agotado: '⛔ Se alcanzó el tope de gasto — ',
        interrumpido: '⚠ Búsqueda interrumpida — ',
      };
      document.getElementById('result-titulo').textContent =
        (titulos[d.status] || '⚠ ') + d.ciudad;
      document.getElementById('result-desc').textContent =
        (d.status === 'presupuesto_agotado' ? d.error + ' ' : '') +
        `Se alcanzaron a guardar ${d.nuevos_en_sheet} contactos nuevos, y siguen en la hoja. ` +
        `Volver a correr la misma ciudad no los duplica.`;
    }
  }

  if (d.status === 'error') {
    pararSondeo();
    ponerEnMarcha(false);
    document.getElementById('prog-label').textContent = '❌ Error: ' + d.error;
    document.getElementById('btn-iniciar').textContent = '🔍 Reintentar';
    document.getElementById('result-box').style.display = 'block';
    document.getElementById('result-titulo').textContent = '❌ La búsqueda falló — ' + d.ciudad;
    document.getElementById('result-desc').textContent =
      (d.error || '') + ` Se alcanzaron a guardar ${d.nuevos_en_sheet} contactos nuevos.`;
  }
}

restaurarEstado();
