// ─── STATE ──────────────────────────────────────────────────────────────────
const state = {
  currentSection: 'dashboard',
  loaded: {},
  // Secciones que ya se pintaron una vez. La PRIMERA carga trae su esqueleto
  // desde la plantilla; a partir de la segunda lo pinta el JS.
  pintada: {},
  data: {},
  filtered: {},
  page: {},
  pageSize: 50,
  sortCol: {},
  sortDir: {},  // true = asc, false = desc
};

const SECTION_TITLES = {
  dashboard:   '📊 Dashboard Prospectos',
  frecuentes:  '⭐ Dashboard Clientes Frecuentes',
  'ventas-dash': '📈 Dashboard de Ventas',
  ventas:      '💰 Ventas',
  contactos:   '📋 Lista de Contactos',
  pendientes:  '📞 Por Llamar — Sin Respuesta',
  ciudades:    '🗺️ Ciudades por Interés',
  respuestas:  '📝 Respuestas del Formulario',
  mensajes:    '💬 Mensajes Iniciales',
  catalogo:    '📖 Envíos de Catálogo',
  seguimiento: '🔄 Seguimiento',
  bruce:       '🤖 Prospectos Bruce',
};

let charts = {};

// ─── MOVIMIENTO ─────────────────────────────────────────────────────────────
// Chart.js dibuja sobre <canvas>: sus animaciones NO pasan por la cascada CSS,
// asi que el bloque `prefers-reduced-motion` de tokens.css no las toca. Es el
// unico movimiento del panel que hay que apagar desde JavaScript, y son las
// seis graficas. Se comprueba `matchMedia` y se escucha el cambio, porque la
// preferencia del sistema puede activarse con la pagina ya abierta.
const MOVIMIENTO_REDUCIDO = window.matchMedia
  ? window.matchMedia('(prefers-reduced-motion: reduce)')
  : { matches: false, addEventListener: () => {} };

// El valor de fabrica, capturado ANTES de tocarlo. Restaurar con `undefined`
// no restauraba nada: dejaba la configuracion de animacion de la libreria
// borrada. Comprobado en navegador — sin la preferencia activa,
// `Chart.defaults.animation` se quedaba en `undefined` en vez de en su objeto.
const ANIMACION_CHART_FABRICA =
  (typeof Chart !== 'undefined' && Chart.defaults) ? Chart.defaults.animation : undefined;

function aplicarPreferenciaDeMovimiento() {
  if (typeof Chart === 'undefined') return;   // el CDN pudo no responder
  // `false` desactiva la animacion de entrada y las transiciones de datos.
  Chart.defaults.animation = MOVIMIENTO_REDUCIDO.matches ? false : ANIMACION_CHART_FABRICA;
}

if (MOVIMIENTO_REDUCIDO.addEventListener) {
  MOVIMIENTO_REDUCIDO.addEventListener('change', () => {
    aplicarPreferenciaDeMovimiento();
    // Las graficas ya dibujadas conservan la configuracion con la que
    // nacieron, asi que hay que tocarlas. Pero EN SITIO, no recargando la
    // seccion: `loadSection` reconstruye el innerHTML de tarjetas y tabla, lo
    // que (a) descarta el filtro y la pagina que el operador tenia puestos
    // -`loadTableSection` reasigna el dataset completo y vuelve a la pagina 1
    // sin reaplicar `filterTable`- y (b) destruye el nodo con el foco, que cae
    // a <body> sin aviso. Las dos cosas le pasan a quien acaba de pedir MENOS
    // movimiento, que es exactamente a quien no hay que sobresaltar.
    Object.keys(charts).forEach(id => {
      charts[id].options.animation =
        MOVIMIENTO_REDUCIDO.matches ? false : ANIMACION_CHART_FABRICA;
      charts[id].update('none');   // 'none': el propio cambio no se anima
    });
  });
}

// Entrada escalonada de las filas de una tabla. Solo las primeras
// FILAS_ANIMADAS: con 50 filas y un retardo por fila, la ultima entraria mas de
// un segundo despues y el escalonado dejaria de aclarar nada para volverse
// espera. El resto aparece sin retardo.
const FILAS_ANIMADAS = 12;

function escalonarFilas(contenedor) {
  if (MOVIMIENTO_REDUCIDO.matches) return;
  const el = typeof contenedor === 'string' ? document.getElementById(contenedor) : contenedor;
  if (!el) return;
  const filas = el.querySelectorAll('tbody tr');
  for (let i = 0; i < Math.min(filas.length, FILAS_ANIMADAS); i++) {
    filas[i].style.setProperty('--retardo-fila', (i * 25) + 'ms');
    filas[i].classList.add('fila-entra');
  }
}

// ─── NAVIGATION ─────────────────────────────────────────────────────────────
function showSection(name) {
  document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  const seccion = document.getElementById('sec-' + name);
  seccion.classList.add('active');
  // La clase se retira al terminar para que la animacion pueda repetirse en el
  // siguiente cambio de seccion: una clase de animacion que se queda puesta
  // solo corre la primera vez.
  if (!MOVIMIENTO_REDUCIDO.matches) {
    seccion.classList.remove('seccion-entra');
    void seccion.offsetWidth;   // fuerza reinicio de la animacion
    seccion.classList.add('seccion-entra');
    // Se comprueba que la animacion VA a correr antes de esperar su final. Si
    // una hoja la anula, `animationend` no llega nunca y el listener se queda
    // registrado sin disparar. Salir de la seccion antes de que termine
    // (display:none cancela la animacion sin evento) tiene el mismo efecto,
    // pero ahi la clase ya se retira en la siguiente visita.
    if (getComputedStyle(seccion).animationName !== 'none') {
      seccion.addEventListener('animationend',
        () => seccion.classList.remove('seccion-entra'), { once: true });
    } else {
      seccion.classList.remove('seccion-entra');
    }
  }
  document.querySelectorAll('.nav-item').forEach(n => {
    if (n.textContent.trim().toLowerCase().includes(SECTION_TITLES[name].slice(2,10).toLowerCase().trim()))
      n.classList.add('active');
  });
  // simpler: mark by onclick
  event.currentTarget.classList.add('active');
  state.currentSection = name;
  const titulo = document.getElementById('topbar-title');
  titulo.textContent = SECTION_TITLES[name];
  // El h1 se recorta con puntos suspensivos para que la barra no cambie de
  // alto (ver dashboard.css). El lector de pantalla anuncia el textContent
  // completo igual, pero quien amplía la página y no usa lector se quedaba
  // sin forma de leer el resto.
  titulo.title = SECTION_TITLES[name];
  if (!state.loaded[name]) loadSection(name);
}

// ─── CONTENEDORES POR SECCIÓN ───────────────────────────────────────────────
// Dónde va el esqueleto al recargar y dónde aterriza el estado de error.
// Antes el catch genérico adivinaba el id concatenando cadenas
// (`name.replace('-','') + '-cards'`), que acertaba en unas secciones y en
// otras no: 'ventas-dash' salía como 'ventasdash-cards', que no existe, así
// que el fallo se quedaba sin pintar y la sección se veía cargando para
// siempre. El número de tarjetas es el que pinta cada `load*`: si el esqueleto
// lleva otro, la rejilla cambia de alto al llegar los datos (CE4).
const CONTENEDORES = {
  dashboard:     { tarjetas: 'dash-cards',  n: 8, graficas: 'dash-charts', avisoGraficas: 'dash-charts-aviso' },
  frecuentes:    { tarjetas: 'frec-cards',  n: 4, tabla: 'frec-top-table' },
  'ventas-dash': { tarjetas: 'vdash-cards', n: 5, tabla: 'vdash-table', graficas: 'vdash-charts', avisoGraficas: 'vdash-charts-aviso' },
  ventas:        { tabla: 'ventas-table' },
  contactos:     { tabla: 'contactos-table' },
  pendientes:    { tarjetas: 'pend-cards',  n: 2, tabla: 'pendientes-table' },
  ciudades:      { tabla: 'ciudades-table' },
  respuestas:    { tabla: 'respuestas-table' },
  mensajes:      { tabla: 'mensajes-table' },
  catalogo:      { tabla: 'catalogo-table' },
  seguimiento:   { tarjetas: 'seg-cards',   n: 4, tabla: 'seguimiento-table' },
  bruce:         { tabla: 'bruce-table' },
};

// Esqueletos de una sección al RE-cargarla (cambio de sección ya visitada o
// botón Actualizar). En la primera carga el esqueleto ya viene en la plantilla:
// pintarlo desde JS llegaría tarde y provocaría justo el salto que evita.
// Devuelve la función que los retira.
function pintarEsqueletos(name) {
  const c = CONTENEDORES[name];
  if (!c || typeof Estados === 'undefined') return function () {};
  const cierres = [];
  if (c.tarjetas) cierres.push(Estados.esqueleto(c.tarjetas, 'tarjetas', { tarjetas: c.n }));
  if (c.tabla)    cierres.push(Estados.esqueleto(c.tabla, 'tabla'));
  return function () { cierres.forEach(f => f()); };
}

// ─── LOAD SECTION ───────────────────────────────────────────────────────────
async function loadSection(name) {
  state.loaded[name] = true;
  const quitarEsqueletos = state.pintada[name] ? pintarEsqueletos(name) : function () {};
  const graficas = CONTENEDORES[name] && CONTENEDORES[name].graficas
    ? document.getElementById(CONTENEDORES[name].graficas) : null;
  if (graficas) graficas.hidden = false;
  // El aviso de la carga anterior se limpia SIEMPRE al empezar: si no, un
  // reintento correcto dejaría en pantalla el "las gráficas no se pudieron
  // dibujar" de la vez anterior.
  const avisoGraficas = CONTENEDORES[name] && CONTENEDORES[name].avisoGraficas
    ? document.getElementById(CONTENEDORES[name].avisoGraficas) : null;
  if (avisoGraficas) avisoGraficas.innerHTML = '';
  try {
  switch(name) {
    case 'dashboard':   await loadDashboard(); break;
    case 'frecuentes':  await loadFrecuentes(); break;
    // filterTable('frecuentes') → frec-top-table / frec-pag manejado en loadFrecuentes
    case 'ventas-dash': await loadVentasDash(); break;
    case 'ventas':      await loadVentas(); break;
    case 'contactos':   await loadContactos(); break;
    case 'pendientes':  await loadPendientes(); break;
    case 'ciudades':    await loadCiudades(); break;
    case 'respuestas':
      await loadTableSection('respuestas', '/api/prospectos/respuestas', 'respuestas-table', 'respuestas-pag', ['resp-search','resp-conclusion']);
      // Poblar dropdown de Conclusión con valores únicos del dataset
      { const concSel = document.getElementById('resp-conclusion');
        if (concSel) {
          const vals = [...new Set((state.data['respuestas'] || [])
            .map(r => String(r['Conclusión'] || r['Conclusion'] || '').trim())
            .filter(Boolean))].sort();
          vals.forEach(v => { const o = document.createElement('option'); o.value = v; o.textContent = v; concSel.appendChild(o); });
        }
      }
      break;
    case 'mensajes':    await loadMensajes(); break;
    case 'catalogo':    await loadCatalogo(); break;
    case 'seguimiento': await loadSeguimiento(); break;
    case 'bruce':       await loadBruce(); break;
  }
  } catch(e) {
    console.error('loadSection error:', name, e);
    const c = CONTENEDORES[name] || {};
    const reintentar = () => { state.loaded[name] = false; loadSection(name); };
    // El error va donde estaba el contenido, en las DOS piezas de la sección:
    // dejar la rejilla de indicadores con su esqueleto girando mientras la
    // tabla dice "falló" es contarle al operador dos cosas distintas.
    if (c.tabla) Estados.error(c.tabla, {
      titulo: 'No se pudo cargar esta tabla',
      detalle: mensajeDeFallo(e),
      reintentar,
    });
    if (c.tarjetas) Estados.error(c.tarjetas, {
      titulo: 'No se pudieron cargar los indicadores',
      detalle: mensajeDeFallo(e),
      reintentar,
    });
    // Las tarjetas de gráfica se retiran: sin datos quedan como tres cajas
    // blancas con título y nada dentro, que se leen como "sigue cargando".
    // El bloque de error de arriba ya dice lo que pasó; repetirlo tres veces
    // más no informa, y dejarlas vacías desinforma.
    // Se OCULTAN, no se borran: vaciar el contenedor se llevaria por delante
    // los <canvas>, y el reintento moriria buscando un elemento que ya no
    // existe. `loadSection` las vuelve a mostrar al empezar.
    if (c.graficas) {
      const g = document.getElementById(c.graficas);
      if (g) g.hidden = true;
    }
    state.loaded[name] = false; // permitir reintento
  } finally {
    quitarEsqueletos();
    state.pintada[name] = true;
  }
}

// ─── FETCH ──────────────────────────────────────────────────────────────────
async function fetchAPI(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

// Un `TypeError: Failed to fetch` no le dice nada a quien opera el panel, y un
// 500 crudo de Google tampoco. Se traduce lo que se puede y se conserva el
// resto para la consola.
function mensajeDeFallo(e) {
  const m = String((e && e.message) || e || '');
  if (/HTTP 401|HTTP 403/.test(m)) return 'La sesión del panel caducó. Recarga la página para volver a entrar.';
  if (/HTTP 429/.test(m))          return 'Google está limitando las peticiones. Espera unos segundos y reintenta.';
  if (/HTTP 5\d\d/.test(m))        return 'El panel no pudo leer la hoja de Google. Suele resolverse reintentando.';
  if (/Failed to fetch|NetworkError/i.test(m)) return 'Sin conexión con el panel. Revisa la red y reintenta.';
  return m || 'Fallo no identificado.';
}

// Las gráficas fallan APARTE del resto: los indicadores ya están en pantalla y
// siguen siendo válidos. Chart.js viene de un CDN sin SRI (deuda del Plan 5), así
// que "no cargó la librería" es un caso real, no teórico.
//
// El aviso va en un contenedor PROPIO, nunca dentro de `.charts`: pintarlo ahí
// con innerHTML borraría los <canvas>, y el siguiente intento moriría buscando
// un elemento que ya no existe — el fallo pasaría de temporal a permanente,
// recuperable solo recargando la página entera.
function pintarGraficasConAviso(pintar, idGraficas, idAviso) {
  const caja = document.getElementById(idGraficas);
  try {
    if (caja) caja.hidden = false;
    pintar();
  } catch (e) {
    console.error('graficas:', idGraficas, e);
    if (caja) caja.hidden = true;
    Estados.parcial(idAviso, {
      titulo: 'Las gráficas no se pudieron dibujar',
      detalle: 'Los indicadores de arriba sí están completos. Recargar la página suele bastar.',
    });
  }
}

// ─── DASHBOARD ──────────────────────────────────────────────────────────────
async function loadDashboard() {
  const stats = await fetchAPI('/api/prospectos/stats');
  state.data.dashStats = stats;
  updateCacheBadge();

  const res = stats.resultados || {};
  const aprobados = res['APROBADO'] || 0;
  const negados   = res['NEGADO'] || 0;
  const nc        = res['NO COMPATIBLE'] || 0;
  const mu        = res['MARCA UNICA'] || 0;

  const estados = stats.estados_llamada || {};
  const buzon   = estados['BUZON'] || estados['BUZÓN'] || 0;
  const telInc  = estados['TELEFONO INCORRECTO'] || estados['TELÉFONO INCORRECTO'] || 0;

  const totalResp = stats.total_respuestas || 0;
  const tasaConv  = totalResp > 0 ? ((aprobados / totalResp) * 100).toFixed(1) : 0;

  document.getElementById('dash-cards').innerHTML = `
    <div class="card"><div class="label">Total Contactos</div><div class="value">${stats.total_contactos}</div><div class="sub">En lista</div></div>
    <div class="card"><div class="label">Llamadas Realizadas</div><div class="value">${totalResp}</div><div class="sub">Con respuesta</div></div>
    <div class="card green"><div class="label">Aprobados</div><div class="value">${aprobados}</div><div class="sub">Tasa: ${tasaConv}%</div></div>
    <div class="card red"><div class="label">Negados</div><div class="value">${negados}</div><div class="sub">Rechazaron</div></div>
    <div class="card orange"><div class="label">Buzón</div><div class="value">${buzon}</div><div class="sub">No contestó</div></div>
    <div class="card gray"><div class="label">Tel. Incorrecto</div><div class="value">${telInc}</div><div class="sub">Fuera de servicio</div></div>
    <div class="card orange"><div class="label">No Compatible</div><div class="value">${nc}</div><div class="sub">Sin fit</div></div>
    <div class="card purple"><div class="label">Marca Única</div><div class="value">${mu}</div><div class="sub">Competencia</div></div>
  `;

  // Las gráficas van aparte, y su fallo es PARCIAL: los indicadores de arriba
  // ya están en pantalla y siguen siendo válidos. Chart.js viene de un CDN sin
  // SRI (deuda del Plan 5): si ese CDN no responde, `new Chart` revienta y
  // antes se llevaba por delante toda la sección, indicadores incluidos.
  pintarGraficasConAviso(() => pintarGraficasDashboard(stats, res),
                         'dash-charts', 'dash-charts-aviso');
}

function pintarGraficasDashboard(stats, res) {
  // Chart: Resultados donut
  destroyChart('chartResultados');
  const ctxR = document.getElementById('chartResultados').getContext('2d');
  const labelsR = Object.keys(res);
  const dataR   = Object.values(res);
  charts['chartResultados'] = new Chart(ctxR, {
    type: 'doughnut',
    data: {
      labels: labelsR,
      datasets: [{ data: dataR, backgroundColor: ['#00CC47','#e74c3c','#e67e22','#8e44ad','#6c757d','#ffc107'] }]
    },
    options: { maintainAspectRatio: false, plugins: { legend: { position: 'right' } }, cutout: '65%' }
  });

  // Chart: Semanas
  destroyChart('chartSemanas');
  const semanas = stats.por_semana || [];
  const ctxS = document.getElementById('chartSemanas').getContext('2d');
  charts['chartSemanas'] = new Chart(ctxS, {
    type: 'line',
    data: {
      labels: semanas.map(s => s.semana),
      datasets: [{ label: 'Contactos', data: semanas.map(s => s.total), borderColor: '#0047CC', backgroundColor: 'rgba(0,71,204,.1)', fill: true, tension: .4 }]
    },
    options: { maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true } } }
  });

  // Chart: Ciudades
  destroyChart('chartCiudades');
  const ciudades = (stats.top_ciudades || []).slice(0,10);
  const ctxC = document.getElementById('chartCiudades').getContext('2d');
  charts['chartCiudades'] = new Chart(ctxC, {
    type: 'bar',
    data: {
      labels: ciudades.map(c => c[0]),
      datasets: [{ label: 'Contactos', data: ciudades.map(c => c[1]), backgroundColor: '#0047CC' }]
    },
    options: { maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true } } }
  });
}

// ─── FRECUENTES ─────────────────────────────────────────────────────────────
async function loadFrecuentes() {
  const data = await fetchAPI('/api/prospectos/clientes-frecuentes');

  // ── KPIs ──
  const totalClientes = data.length;
  const totalMonto    = data.reduce((s, r) => s + (r['Total Monto'] || 0), 0);
  const totalPedidos  = data.reduce((s, r) => s + (r['Pedidos'] || 0), 0);
  const top           = data[0] || {};

  document.getElementById('frec-cards').innerHTML = `
    <div class="card"><div class="label">Clientes</div><div class="value">${totalClientes}</div><div class="sub">Con al menos 1 pedido</div></div>
    <div class="card green"><div class="label">Facturación Total</div><div class="value">$${fmtMonto(totalMonto)}</div><div class="sub">Suma de todos</div></div>
    <div class="card"><div class="label">Total Pedidos</div><div class="value">${totalPedidos}</div><div class="sub">Facturas emitidas</div></div>
    <div class="card orange"><div class="label">Top Cliente</div><div class="value" style="font-size:1em">${top['Cliente'] || '—'}</div><div class="sub">$${fmtMonto(top['Total Monto'] || 0)}</div></div>
  `;

  // ── Tabla agrupada ──
  const pageSize = 50;
  const page     = state.page['frecuentes'] || 1;
  const slice    = data.slice((page-1)*pageSize, page*pageSize);

  let html = `<table><thead><tr>
    <th>#</th><th>Cliente</th><th>Esquema</th><th>Pedidos</th>
    <th style="text-align:right">Total Facturado</th><th>Último Pedido</th>
  </tr></thead><tbody>`;

  slice.forEach((r, i) => {
    const rank = (page-1)*pageSize + i + 1;
    const medal = rank === 1 ? '🥇' : rank === 2 ? '🥈' : rank === 3 ? '🥉' : `${rank}`;
    html += `<tr>
      <td style="font-weight:700;color:var(--blue)">${medal}</td>
      <td><strong>${r['Cliente']}</strong></td>
      <td><span class="tag default">${r['Esquema'] || '—'}</span></td>
      <td style="text-align:center;font-weight:700">${r['Pedidos']}</td>
      <td style="text-align:right;font-weight:800;color:var(--green)">$${fmtMonto(r['Total Monto'])}</td>
      <td style="color:var(--texto-suave);font-size:.85em">${r['Ultimo Pedido'] || '—'}</td>
    </tr>`;
  });
  html += '</tbody></table>';
  document.getElementById('frec-top-table').innerHTML = html;

  // Paginación
  const totalPages = Math.ceil(data.length / pageSize);
  let pag = `<span class="pag-info">${data.length} clientes</span>`;
  if (totalPages > 1) {
    if (page > 1) pag += `<button onclick="frecPage(${page-1})">‹</button>`;
    for (let p = Math.max(1,page-2); p <= Math.min(totalPages,page+2); p++) {
      pag += `<button class="${p===page?'active':''}" onclick="frecPage(${p})">${p}</button>`;
    }
    if (page < totalPages) pag += `<button onclick="frecPage(${page+1})">›</button>`;
  }
  document.getElementById('frec-pag').innerHTML = pag;

  // Guardar data para paginación
  state.data['frecuentes-raw'] = data;
}

function frecPage(p) {
  state.page['frecuentes'] = p;
  state.data['frecuentes'] = state.data['frecuentes-raw'];
  loadFrecuentes();
}

function fmtMonto(n) {
  return Number(n).toLocaleString('es-MX', {minimumFractionDigits:2, maximumFractionDigits:2});
}

// ─── DASHBOARD VENTAS ────────────────────────────────────────────────────────
function pintarGraficasVentas(labels, montos, pedidos, tickets) {
  // ── Chart: Facturación mensual ──
  destroyChart('chartVentasMonto');
  charts['chartVentasMonto'] = new Chart(
    document.getElementById('chartVentasMonto').getContext('2d'), {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        label: 'Facturación $',
        data: montos,
        backgroundColor: montos.map((v,i) =>
          v === Math.max(...montos) ? '#00CC47' : 'rgba(0,71,204,0.7)'),
        borderRadius: 6,
      }]
    },
    options: { maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        y: { beginAtZero: true, ticks: { callback: v => '$'+fmtMonto(v) } }
      }
    }
  });

  // ── Chart: Pedidos por mes ──
  destroyChart('chartVentasPedidos');
  charts['chartVentasPedidos'] = new Chart(
    document.getElementById('chartVentasPedidos').getContext('2d'), {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        label: 'Pedidos',
        data: pedidos,
        backgroundColor: 'rgba(0,71,204,0.75)',
        borderRadius: 6,
      }]
    },
    options: { maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: { y: { beginAtZero: true, ticks: { stepSize: 1 } } }
    }
  });

  // ── Chart: Ticket promedio ──
  destroyChart('chartVentasTicket');
  charts['chartVentasTicket'] = new Chart(
    document.getElementById('chartVentasTicket').getContext('2d'), {
    type: 'line',
    data: {
      labels,
      datasets: [{
        label: 'Ticket Promedio $',
        data: tickets,
        borderColor: '#e67e22',
        backgroundColor: 'rgba(230,126,34,.1)',
        fill: true, tension: .4, pointRadius: 4,
      }]
    },
    options: { maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        y: { beginAtZero: true, ticks: { callback: v => '$'+fmtMonto(v) } }
      }
    }
  });
}

async function loadVentasDash() {
  const d = await fetchAPI('/api/prospectos/ventas-dashboard');
  const meses = d.por_mes || [];

  // ── KPIs ──
  document.getElementById('vdash-cards').innerHTML = `
    <div class="card green">
      <div class="label">Facturación Total</div>
      <div class="value" style="font-size:1.4em">$${fmtMonto(d.total_general)}</div>
      <div class="sub">Todas las ventas</div>
    </div>
    <div class="card">
      <div class="label">Total Pedidos</div>
      <div class="value">${d.total_pedidos}</div>
      <div class="sub">Facturas emitidas</div>
    </div>
    <div class="card orange">
      <div class="label">Promedio Mensual</div>
      <div class="value" style="font-size:1.3em">$${fmtMonto(d.promedio_mes)}</div>
      <div class="sub">Por mes</div>
    </div>
    <div class="card purple">
      <div class="label">Mejor Mes</div>
      <div class="value" style="font-size:1.1em">${d.mejor_mes}</div>
      <div class="sub">$${fmtMonto(d.mejor_mes_monto)}</div>
    </div>
    <div class="card">
      <div class="label">Meses Activos</div>
      <div class="value">${meses.length}</div>
      <div class="sub">Con ventas</div>
    </div>
  `;

  const labels  = meses.map(m => m.mes);
  const montos  = meses.map(m => m.monto);
  const pedidos = meses.map(m => m.pedidos);
  const tickets = meses.map(m => m.ticket_prom);

  // Mismo trato que el tablero: si la libreria de graficas no cargo, la tabla
  // de desglose de abajo tiene que seguir pintandose. Antes el fallo subia al
  // catch generico de loadSection y se llevaba la seccion entera.
  pintarGraficasConAviso(
    () => pintarGraficasVentas(labels, montos, pedidos, tickets),
    'vdash-charts', 'vdash-charts-aviso');

  // ── Tabla desglose por mes ──
  const maxMonto = Math.max(...montos, 1);
  let html = `<table><thead><tr>
    <th>Mes</th><th style="text-align:right">Facturación</th>
    <th style="text-align:center">Pedidos</th><th style="text-align:center">Clientes</th>
    <th style="text-align:right">Ticket Prom.</th><th>Distribución</th>
  </tr></thead><tbody>`;

  meses.forEach(m => {
    const barW = Math.round((m.monto / maxMonto) * 140);
    const esqs = Object.entries(m.por_esquema)
      .sort((a,b) => b[1]-a[1])
      .map(([k,v]) => `<span class="tag default" style="font-size:.7em">${k}: $${fmtMonto(v)}</span>`)
      .join(' ');
    const isMejor = m.mes === d.mejor_mes;
    html += `<tr ${isMejor ? 'style="background:var(--exito-tinte)"' : ''}>
      <td><strong ${isMejor ? 'style="color:var(--green)"' : ''}>${m.mes} ${isMejor ? '⭐' : ''}</strong></td>
      <td style="text-align:right;font-weight:800;color:var(--green)">$${fmtMonto(m.monto)}</td>
      <td style="text-align:center;font-weight:700">${m.pedidos}</td>
      <td style="text-align:center">${m.clientes}</td>
      <td style="text-align:right;color:var(--texto-suave)">$${fmtMonto(m.ticket_prom)}</td>
      <td>
        <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap">
          <div style="background:var(--green);height:8px;border-radius:4px;width:${barW}px;min-width:2px"></div>
          ${esqs}
        </div>
      </td>
    </tr>`;
  });
  html += '</tbody></table>';
  document.getElementById('vdash-table').innerHTML = html;
}

// ─── VENTAS (orden cronológico de ingreso) ────────────────────────────────────
async function loadVentas() {
  const data = await fetchAPI('/api/prospectos/ventas');
  // Orden de ingreso: primeras entradas primero (como en la hoja)
  state.data['ventas'] = data;
  state.filtered['ventas'] = data;
  state.page['ventas'] = 1;
  const countEl = document.getElementById('ventas-count');
  if (countEl) countEl.textContent = `${data.length} registros`;
  renderTable('ventas', 'ventas-table', 'ventas-pag');
}

// ─── GENERIC TABLE ──────────────────────────────────────────────────────────
async function loadTableSection(key, url, tableId, pagId, filterIds) {
  const data = await fetchAPI(url);
  state.data[key] = data;
  state.filtered[key] = data;
  state.page[key] = 1;
  renderTable(key, tableId, pagId);
}

function filterTable(key) {
  const d = state.data[key] || [];
  let filtered = d;

  const searchId = key === 'respuestas' ? 'resp-search'
    : key === 'frecuentes' ? 'frecuentes-search'
    : key + '-search';
  const searchEl = document.getElementById(searchId);
  const q = searchEl ? searchEl.value.toLowerCase() : '';
  if (q) {
    filtered = filtered.filter(row =>
      Object.values(row).some(v => String(v).toLowerCase().includes(q))
    );
  }

  // Specific filters
  if (key === 'respuestas') {
    const concEl = document.getElementById('resp-conclusion');
    const conc = concEl ? concEl.value : '';
    if (conc) filtered = filtered.filter(r =>
      String(r['Conclusión'] || r['Conclusion'] || '').trim() === conc
    );
  }
  if (key === 'contactos' || key === 'pendientes') {
    const ciudadEl = document.getElementById(`${key}-ciudad`);
    const ciudad = ciudadEl ? ciudadEl.value.toLowerCase() : '';
    if (ciudad) filtered = filtered.filter(r => String(r.Ciudad || r.ciudad || r.CIUDAD || '').toLowerCase() === ciudad);
    if (key === 'contactos') {
      const catEl = document.getElementById('contactos-cat');
      const cat = catEl ? catEl.value.toLowerCase() : '';
      if (cat) filtered = filtered.filter(r => Object.values(r).some(v => String(v).toLowerCase() === cat));
    }
  }

  state.filtered[key] = filtered;
  state.page[key] = 1;
  // frecuentes usa IDs distintos
  const tableId = key === 'frecuentes' ? 'frec-top-table' : key + '-table';
  const pagId   = key === 'frecuentes' ? 'frec-pag'       : key + '-pag';
  renderTable(key, tableId, pagId);
}

function renderTable(key, tableId, pagId) {
  const data = state.filtered[key] || [];
  const page = state.page[key] || 1;
  const ps   = state.pageSize;
  const total = data.length;
  const totalPages = Math.ceil(total / ps);

  if (!total) {
    Estados.vacio(tableId, {
      titulo: 'No hay filas que mostrar',
      detalle: 'La hoja se leyó bien; sencillamente no hay registros con los filtros aplicados.',
    });
    document.getElementById(pagId).innerHTML = '';
    return;
  }

  // Ordenar antes de paginar
  const sc = state.sortCol[key];
  const sd = state.sortDir[key]; // true=asc false=desc
  const sorted = sc ? [...data].sort((a, b) => {
    const va = String(a[sc] ?? '');
    const vb = String(b[sc] ?? '');
    const na = parseFloat(va.replace(/[,$\s]/g, ''));
    const nb = parseFloat(vb.replace(/[,$\s]/g, ''));
    const cmp = !isNaN(na) && !isNaN(nb) ? na - nb : va.localeCompare(vb, 'es-MX');
    return sd ? cmp : -cmp;
  }) : data;
  const slice = sorted.slice((page-1)*ps, page*ps);

  const allCols = Object.keys(slice[0]).filter(k => !k.startsWith('_'));

  // Columnas fijas para ventas/frecuentes (en orden exacto de la hoja)
  const VENTAS_COLS = ['Fecha','Cliente','ESQUEMA','MES','Monto ','Monto','Envio Costo','Num Factura','Cotizacion PDF','PAGO'];
  // Columnas clave para respuestas (Conclusión es el campo principal)
  const RESPUESTAS_COLS = ['Marca temporal','Nombre De la Tienda','Teléfono','Telefono','CIUDAD','Ciudad','Conclusión','Conclusion'];
  // Encabezados exactos del sheet de Mensajes Iniciales
  const MENSAJES_COLS = ['Mensaje inicial','Mensaje Seguimiento','Cotizacion','Cotizacion Seguimiento','Seguimiento Clientes','correo'];
  const isVentas     = key === 'ventas' || key === 'frecuentes';
  const isRespuestas = key === 'respuestas';
  const isSeguimiento = key === 'seguimiento';
  const isMensajes    = key === 'mensajes';

  let sortedCols;
  if (isVentas) {
    sortedCols = VENTAS_COLS.filter(c => allCols.includes(c));
    allCols.filter(c => !VENTAS_COLS.includes(c) && c.trim() !== '').forEach(c => sortedCols.push(c));
  } else if (isRespuestas) {
    sortedCols = RESPUESTAS_COLS.filter(c => allCols.includes(c));
  } else if (isMensajes) {
    // Preferir columnas definidas; si no coinciden (distinto header) usar las del dataset
    sortedCols = MENSAJES_COLS.filter(c => allCols.includes(c));
    if (!sortedCols.length) sortedCols = allCols.filter(c => c.trim() !== '').slice(0, 10);
  } else {
    sortedCols = allCols.filter(c => c.trim() !== '').slice(0, 20);
  }
  const isEditable    = isSeguimiento || isMensajes;
  const openFn        = isMensajes ? 'openEditMen' : 'openEditSeg';
  const arrow = c => c === sc ? (sd ? ' ▲' : ' ▼') : ' ⇅';
  const thStyle = 'cursor:pointer;white-space:nowrap;user-select:none';

  const editTh = isEditable ? '<th style="width:60px"></th>' : '';
  let html = `<table><thead><tr>${editTh}${sortedCols.map(c =>
    `<th style="${thStyle}" data-key="${key}" data-tableid="${tableId}" data-pagid="${pagId}" data-col="${c.replace(/"/g,'&quot;')}" onclick="sortTable(this)">${c}<span style="opacity:.4;font-size:.75em">${arrow(c)}</span></th>`
  ).join('')}</tr></thead><tbody>`;

  slice.forEach(row => {
    if (isSeguimiento && row._row) _segRowMap[row._row] = row;
    const editKey = row._row;
    const editTd = isEditable && editKey
      ? `<td><button class="btn-edit-row" onclick="${openFn}(${editKey})">✏️ Editar</button></td>`
      : '<td></td>';
    const colorCode = (isSeguimiento && row._row) ? (_segColorMap[row._row] || '') : '';
    const colorD    = colorCode ? SEG_COLORS[colorCode] : null;
    const rowStyle  = colorD ? `style="background:${colorD.bg};border-left:5px solid ${colorD.border}"` : '';
    html += `<tr ${rowStyle}>` + editTd + sortedCols.map(c => {
      const v = row[c] !== undefined ? row[c] : '';
      return `<td>${renderCell(c, String(v), row)}</td>`;
    }).join('') + '</tr>';
  });
  html += '</tbody></table>';
  document.getElementById(tableId).innerHTML = html;
  escalonarFilas(tableId);

  // Pagination
  let pag = `<span class="pag-info">${total} registros</span>`;
  if (totalPages > 1) {
    if (page > 1) pag += `<button onclick="goPage('${key}','${tableId}','${pagId}',${page-1})">‹</button>`;
    const start = Math.max(1, page-2), end = Math.min(totalPages, page+2);
    for (let p = start; p <= end; p++) {
      pag += `<button class="${p===page?'active':''}" onclick="goPage('${key}','${tableId}','${pagId}',${p})">${p}</button>`;
    }
    if (page < totalPages) pag += `<button onclick="goPage('${key}','${tableId}','${pagId}',${page+1})">›</button>`;
  }
  document.getElementById(pagId).innerHTML = pag;
}

function goPage(key, tableId, pagId, p) {
  state.page[key] = p;
  renderTable(key, tableId, pagId);
}

function sortTable(th) {
  const key     = th.dataset.key;
  const tableId = th.dataset.tableid;
  const pagId   = th.dataset.pagid;
  const col     = th.dataset.col;
  if (state.sortCol[key] === col) {
    state.sortDir[key] = !state.sortDir[key];
  } else {
    state.sortCol[key] = col;
    state.sortDir[key] = true;
  }
  state.page[key] = 1;
  renderTable(key, tableId, pagId);
}

function renderCell(col, val, row) {
  if (!val || val === 'undefined') {
    // Columna PAGO vacía → mostrar botón de upload
    if (col === 'PAGO' && row) {
      const factura = row['Num Factura'] || '';
      return `<button class="btn-upload-pago" onclick="abrirUpload('${factura}', this)" title="Subir comprobante">📎 Subir</button>`;
    }
    return '<span style="color:var(--texto-suave)">—</span>';
  }
  const colLow = col.toLowerCase();
  const valUp  = val.toUpperCase();

  if (colLow.includes('resultado')) {
    if (valUp === 'APROBADO') return `<span class="tag aprobado">✓ Aprobado</span>`;
    if (valUp === 'NEGADO') return `<span class="tag negado">✗ Negado</span>`;
    if (valUp === 'NO COMPATIBLE') return `<span class="tag no-compatible">No Compatible</span>`;
    if (valUp === 'MARCA UNICA') return `<span class="tag marca-unica">Marca Única</span>`;
  }
  if (colLow.includes('estado') && (valUp.includes('BUZON') || valUp.includes('BUZÓN'))) return `<span class="tag buzon">Buzón</span>`;
  if (colLow.includes('estado') && valUp.includes('INCORRECTO')) return `<span class="tag tel-inc">Tel. Incorrecto</span>`;
  if (colLow.includes('estado') && valUp === 'RESPONDIO') return `<span class="tag aprobado">Respondió</span>`;

  // Columna PAGO
  if (col === 'PAGO') {
    if (val.startsWith('http')) {
      // Ya tiene URL (ImgBB o Drive) → solo ver, NO subir
      const fileId = val.match(/\/d\/([^/]+)\//)?.[1] || '';
      // Thumb: Drive usa thumbnail API, ImgBB devuelve URL directa de imagen
      const thumb = fileId
        ? `https://drive.google.com/thumbnail?id=${fileId}&sz=w120`
        : val;  // ImgBB: la URL ya es la imagen directa
      const full = fileId
        ? `https://drive.google.com/thumbnail?id=${fileId}&sz=w1200`
        : val;
      return `<span style="display:flex;align-items:center;gap:6px">
        <img src="${thumb}" class="pago-thumb" data-full="${full}" data-link="${val}"
             style="height:40px;border-radius:4px;cursor:pointer;border:2px solid #0047CC"
             title="Clic para ampliar"
             onerror="this.style.display='none'">
        <a href="${val}" target="_blank" style="color:var(--blue);font-size:.78em;font-weight:600">🔍 Abrir</a>
      </span>`;
    }
    // Tiene nombre de archivo pero no URL → solo subir
    const factura = row ? (row['Num Factura'] || '') : '';
    return `<span style="display:flex;align-items:center;gap:5px" id="pago-cell-${factura}">
      <span style="font-size:.72em;color:var(--texto-suave);max-width:90px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${val}">🖼 ${val.slice(0,14)}…</span>
      <button class="btn-upload-pago" onclick="abrirUpload('${factura}',this)" title="Subir comprobante a Drive">📤 Subir</button>
    </span>`;
  }

  // Escape HTML para columnas de texto plano (datos de hoja/importador Places): cierra XSS almacenado.
  const _esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c =>
    ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  if (val.startsWith('http')) return `<a href="${_esc(val)}" target="_blank" style="color:var(--blue);font-size:.8em">Ver →</a>`;
  if (val.length > 80) return `<span title="${_esc(val)}">${_esc(val.slice(0,78))}…</span>`;
  return _esc(val);
}

// ─── CONTACTOS ──────────────────────────────────────────────────────────────
async function loadContactos() {
  const data = await fetchAPI('/api/prospectos/contactos');
  state.data['contactos'] = data;
  state.filtered['contactos'] = data;
  state.page['contactos'] = 1;

  // Populate ciudad filter
  const ciudades = [...new Set(data.map(r => String(r.Ciudad || r.ciudad || r.CIUDAD || '').trim()).filter(Boolean))].sort();
  const ciudadSel = document.getElementById('contactos-ciudad');
  ciudades.forEach(c => { const o = document.createElement('option'); o.value = c.toLowerCase(); o.textContent = c; ciudadSel.appendChild(o); });

  // Populate categoria filter
  const catKey = Object.keys(data[0] || {}).find(k => k.toLowerCase().includes('categ')) || null;
  if (catKey) {
    const cats = [...new Set(data.map(r => String(r[catKey] || '').trim()).filter(Boolean))].sort();
    const catSel = document.getElementById('contactos-cat');
    catSel.parentElement.querySelector('option').textContent = `Todas las categorías`;
    cats.forEach(c => { const o = document.createElement('option'); o.value = c.toLowerCase(); o.textContent = c; catSel.appendChild(o); });
  }

  renderTable('contactos', 'contactos-table', 'contactos-pag');
}

// ─── POR LLAMAR ─────────────────────────────────────────────────────────────
async function loadPendientes() {
  const data = await fetchAPI('/api/prospectos/contactos-pendientes');
  state.data['pendientes']     = data;
  state.filtered['pendientes'] = data;
  state.page['pendientes']     = 1;

  // KPIs
  const totalPend = data.length;
  const ciudadesSet = [...new Set(data.map(r =>
    String(r.CIUDAD || r.Ciudad || r.ciudad || '').trim()).filter(Boolean))];

  document.getElementById('pend-cards').innerHTML = `
    <div class="card red">
      <div class="label">Sin Llamar</div>
      <div class="value">${totalPend}</div>
      <div class="sub">Sin respuesta aún</div>
    </div>
    <div class="card">
      <div class="label">Ciudades</div>
      <div class="value">${ciudadesSet.length}</div>
      <div class="sub">Diferentes</div>
    </div>
  `;

  // Populate ciudad filter
  const ciudadSel = document.getElementById('pendientes-ciudad');
  ciudadSel.innerHTML = '<option value="">Todas las ciudades</option>';
  ciudadesSet.sort().forEach(c => {
    const o = document.createElement('option');
    o.value = c.toLowerCase();
    o.textContent = c;
    ciudadSel.appendChild(o);
  });

  renderTable('pendientes', 'pendientes-table', 'pendientes-pag');
}

// ─── CIUDADES ───────────────────────────────────────────────────────────────
// El nombre de ciudad viene de la columna CIUDAD de LISTA DE CONTACTOS, que
// teclea un operador sin ninguna validacion, y esta tabla lo mete en innerHTML.
// Una ciudad llamada <img src=x onerror=...> ejecutaba en el navegador de
// cualquiera que abriera la pestana. El importador ya lo tenia cerrado en sus
// chips; esta tabla usa otra funcion de render y se habia quedado fuera.
function escCiudad(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, c =>
    ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

let ciudadesData = [];
let ciudadesSortCol = 'prioridad';   // antes 'relevancia', 100 % historial propio (Plan 1)
let ciudadesSortAsc = false;

async function loadCiudades() {
  ciudadesData = await fetchAPI('/api/prospectos/ciudades');
  renderCiudades(getSortedCiudades());
}

function filterCiudades() {
  const q = document.getElementById('ciudades-search').value.toLowerCase();
  const filtradas = q ? ciudadesData.filter(c => c.ciudad.toLowerCase().includes(q)) : ciudadesData;
  renderCiudades(getSortedCiudades(filtradas));
}

function getSortedCiudades(data) {
  const d = (data || ciudadesData).slice();
  d.sort((a, b) => {
    // Las ciudades fuera del catalogo traen null en los campos del Plan 1.
    // Con `?? 0` se colaban en mitad de la tabla como si valieran cero, que es
    // una afirmacion; van al final, que es lo que "no hay dato" significa.
    const na = a[ciudadesSortCol] == null, nb = b[ciudadesSortCol] == null;
    if (na !== nb) return na ? 1 : -1;
    const va = a[ciudadesSortCol] ?? 0;
    const vb = b[ciudadesSortCol] ?? 0;
    return ciudadesSortAsc ? (va > vb ? 1 : -1) : (va < vb ? 1 : -1);
  });
  return d;
}

function sortCiudades(col) {
  if (ciudadesSortCol === col) ciudadesSortAsc = !ciudadesSortAsc;
  else { ciudadesSortCol = col; ciudadesSortAsc = false; }
  const q = document.getElementById('ciudades-search').value.toLowerCase();
  const filtradas = q ? ciudadesData.filter(c => c.ciudad.toLowerCase().includes(q)) : null;
  renderCiudades(getSortedCiudades(filtradas));
}

function renderCiudades(data) {
  if (!data || !data.length) {
    Estados.vacio('ciudades-table', {
      titulo: 'Ninguna ciudad coincide',
      detalle: 'Prueba con otro texto en el buscador.',
    });
    return;
  }
  const maxAprob = Math.max(...data.map(c => c.aprobados), 1);

  const cols = [
    { key: 'ciudad',        label: 'Ciudad',        fmt: (v,c) => `<strong>${escCiudad(v)}</strong>` },
    { key: 'prioridad',     label: '★ Prioridad',    fmt: v => v == null
        ? '<span style="opacity:.45" title="No esta en el catalogo nacional">sin catalogo</span>'
        : `<strong style="color:var(--blue)">${v}</strong>` },
    { key: 'potencial_mercado', label: 'Mercado',    fmt: v => v == null ? '—' : v },
    { key: 'desempeno_nioval',  label: 'Ajuste',     fmt: v => v == null ? '—' : `x${v}` },
    { key: 'total',         label: 'En Lista',       fmt: v => v },
    { key: 'llamados',      label: 'Llamados',       fmt: v => v },
    { key: 'respondio',     label: '📞 Respondió',   fmt: v => v || 0 },
    { key: 'buzon',         label: '📬 Buzón',       fmt: v => v || 0 },
    { key: 'tel_incorrecto',label: '✗ Tel. Inc.',    fmt: v => v || 0 },
    { key: 'aprobados',     label: '✓ Aprobados',    fmt: (v,c) => {
      const w = Math.round((v / maxAprob) * 80);
      return `${v} <span class="interes-bar" style="width:${w}px"></span>`;
    }},
    { key: 'interes_pct',   label: '% Interés',      fmt: v => `<strong style="color:var(--green)">${v}%</strong>` },
    { key: 'negados',       label: '✗ Negados',      fmt: v => v || 0 },
    { key: 'no_compatible', label: '⊘ No Compat.',   fmt: v => v || 0 },
    { key: 'marca_unica',   label: '◈ M.Única',      fmt: v => v || 0 },
    { key: 'pedido',        label: '📦 Pedido',      fmt: v => v ? `<strong style="color:var(--green)">${v}</strong>` : 0 },
    { key: 'catalogo',      label: '📖 Catálogo',    fmt: v => v || 0 },
    { key: 'correo',        label: '📧 Correo',      fmt: v => v || 0 },
    { key: 'avance',        label: '📅 Avance',      fmt: v => v || 0 },
    { key: 'continuacion',  label: '⏳ Continuación',fmt: v => v || 0 },
    { key: 'nulo',          label: '✗ Nulo',         fmt: v => v || 0 },
    { key: 'colgo',         label: '📵 Colgó',       fmt: v => v || 0 },
  ];

  const arrow = col => col === ciudadesSortCol ? (ciudadesSortAsc ? ' ▲' : ' ▼') : '';

  let html = `<table><thead><tr>
    <th style="cursor:default">#</th>
    ${cols.map(c =>
      `<th style="cursor:pointer;white-space:nowrap" onclick="sortCiudades('${c.key}')">${c.label}${arrow(c.key)}</th>`
    ).join('')}
  </tr></thead><tbody>`;

  data.forEach((c, i) => {
    html += `<tr>${[`<td>${i+1}</td>`,
      ...cols.map(col => `<td>${col.fmt(c[col.key], c)}</td>`)
    ].join('')}</tr>`;
  });

  html += '</tbody></table>';
  document.getElementById('ciudades-table').innerHTML = html;
}

// ─── SEGUIMIENTO ────────────────────────────────────────────────────────────
const SEG_ICONS = {
  callback:'📞', llamar:'📞', 'volver a llamar':'📞', rellamar:'📞',
  'buzón':'📬', buzon:'📬', voz:'📬',
  respondió:'✅', respondio:'✅', contestó:'✅', contesto:'✅',
  'no contesta':'❌', 'no contest':'❌', 'no respondió':'❌', 'no respondio':'❌',
  incorrecto:'⚠️', equivocado:'⚠️', inexistente:'⚠️',
  pedido:'🛒', interesado:'🌟', aprobado:'✅',
  negado:'🚫', rechazado:'🚫',
};
function segIcon(val) {
  const v = (val || '').toLowerCase();
  for (const [k, icon] of Object.entries(SEG_ICONS)) { if (v.includes(k)) return icon; }
  return '📋';
}

let _segGroups = {};
let _segActiveTab = 'todos';
let _segResultKey = null;

async function loadSeguimiento() {
  const data = await fetchAPI('/api/seguimiento');
  state.data['seguimiento'] = data;
  _segColumnOptions = buildColumnOptions(data);

  // Detectar columna "Resultado Llamada" o similar
  if (data.length) {
    const keys = Object.keys(data[0]);
    _segResultKey = keys.find(k => /resultado/i.test(k))
      || keys.find(k => /estado/i.test(k))
      || keys.find(k => /status/i.test(k))
      || null;
  }

  // Agrupar por valor de resultado
  _segGroups = { todos: data };
  if (_segResultKey) {
    data.forEach(r => {
      const v = String(r[_segResultKey] || '').trim() || 'Sin resultado';
      if (!_segGroups[v]) _segGroups[v] = [];
      _segGroups[v].push(r);
    });
  }

  // KPI cards
  const total = data.length;
  let cardsHtml = `<div class="card"><div class="label">Total</div><div class="value">${total}</div><div class="sub">Registros</div></div>`;
  Object.entries(_segGroups).filter(([k]) => k !== 'todos').forEach(([s, arr]) => {
    const pct = total > 0 ? ((arr.length / total) * 100).toFixed(0) : 0;
    cardsHtml += `<div class="card"><div class="label">${s}</div><div class="value">${arr.length}</div><div class="sub">${pct}%</div></div>`;
  });
  document.getElementById('seg-cards').innerHTML = cardsHtml;

  // Tabs
  const tabKeys = ['todos', ...Object.keys(_segGroups).filter(k => k !== 'todos')];
  document.getElementById('seg-tabs').innerHTML = tabKeys.map(k => {
    const count = (_segGroups[k] || []).length;
    const icon  = k === 'todos' ? '🔄' : segIcon(k);
    const label = k === 'todos' ? 'Todos' : k;
    return `<div class="seg-tab${k==='todos'?' active':''}" data-tab="${k.replace(/"/g,'&quot;')}" onclick="switchSegTab(this)">${icon} ${label} <span class="tab-count">(${count})</span></div>`;
  }).join('');

  _segActiveTab = 'todos';
  renderSegTab();
}

function switchSegTab(el) {
  _segActiveTab = el.dataset.tab;
  document.querySelectorAll('#seg-tabs .seg-tab').forEach(t => t.classList.remove('active'));
  el.classList.add('active');
  document.getElementById('seg-search').value = '';
  renderSegTab();
}

function filterSegTab() { renderSegTab(); }

function renderSegTab() {
  const raw = _segGroups[_segActiveTab] || [];
  const q = (document.getElementById('seg-search')?.value || '').toLowerCase();
  const filtered = q ? raw.filter(r => Object.values(r).some(v => String(v).toLowerCase().includes(q))) : raw;
  const label = _segActiveTab === 'todos' ? 'Todos' : _segActiveTab;
  document.getElementById('seg-tab-title').textContent = `🔄 Seguimiento — ${label} (${filtered.length})`;
  state.filtered['seguimiento'] = filtered;
  state.page['seguimiento'] = 1;
  renderTable('seguimiento', 'seguimiento-table', 'seguimiento-pag');
}

// ─── EDICIÓN GENÉRICA (Seguimiento + Mensajes) ───────────────────────────────
const _segRowMap = {};
const _menColMap = {};
let _segColumnOptions = {};
let _editCtx = { endpoint: '', rowMap: {}, reload: null, label: '' };

// Colores de estado visual — persisten en localStorage
const SEG_COLORS = {
  '':       { hex:'#cbd5e1', bg:'',        border:'',        label:'Sin estado' },
  'yellow': { hex:'#f59e0b', bg:'#fffbeb', border:'#f59e0b', label:'Pendiente envío' },
  'red':    { hex:'#ef4444', bg:'#fef2f2', border:'#ef4444', label:'Urgente' },
  'green':  { hex:'#22c55e', bg:'#f0fdf4', border:'#22c55e', label:'Completado' },
  'blue':   { hex:'#3b82f6', bg:'#eff6ff', border:'#3b82f6', label:'En seguimiento' },
  'orange': { hex:'#f97316', bg:'#fff7ed', border:'#f97316', label:'Esperando resp.' },
  'purple': { hex:'#a855f7', bg:'#faf5ff', border:'#a855f7', label:'Info enviada' },
};
let _segColorMap = {};
try { _segColorMap = JSON.parse(localStorage.getItem('seg_colors') || '{}'); } catch(e) {}
function _saveColorMap() {
  try { localStorage.setItem('seg_colors', JSON.stringify(_segColorMap)); } catch(e) {}
}

function buildColumnOptions(data) {
  const opts = {};
  if (!data.length) return opts;
  const keys = Object.keys(data[0]).filter(k => !k.startsWith('_'));
  keys.forEach(k => {
    const vals = [...new Set(data.map(r => String(r[k] || '').trim()).filter(Boolean))].sort();
    if (vals.length >= 2 && vals.length <= 20) opts[k] = vals;
  });
  return opts;
}

// Conversión de fechas DD/MM/YYYY ↔ YYYY-MM-DD
function toInputDate(val) {
  if (!val) return new Date().toISOString().slice(0, 10);
  const m = val.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})/);
  if (m) return `${m[3]}-${m[2].padStart(2,'0')}-${m[1].padStart(2,'0')}`;
  if (/^\d{4}-\d{2}-\d{2}/.test(val)) return val.slice(0, 10);
  return new Date().toISOString().slice(0, 10);
}
function fromInputDate(val) {
  const m = val.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  return m ? `${m[3]}/${m[2]}/${m[1]}` : val;
}

function _isDateField(k)  { return /fecha|date/i.test(k); }
function _isLongField(k,v){ return /nota|detalle|comentar|observ|descrip|info|mensaje/i.test(k) || String(v).length > 80; }

function openEdit(ctx, rowNum) {
  _editCtx = ctx;
  const row = ctx.rowMap[rowNum];
  if (!row) return;
  const opts = ctx.columnOptions || {};
  const isSeg = ctx.label === 'Seguimiento';
  const fields = Object.entries(row).filter(([k]) => !k.startsWith('_'));

  // ── Color picker ──
  const modal = document.getElementById('edit-seg-modal');
  const colorSection = document.getElementById('edit-color-section');
  if (isSeg) {
    const curColor = _segColorMap[row._row] || '';
    document.getElementById('edit-color-picker').innerHTML = Object.entries(SEG_COLORS).map(([code, c]) =>
      `<div class="color-opt${code===curColor?' selected':''}" data-color="${code}" onclick="selectEditColor(this)"
           title="${c.label}"
           style="background:${code?c.hex:'var(--borde)'};border:3px solid ${code===curColor?'var(--gris-800)':'transparent'}">
         ${code===curColor?'<span style="position:absolute;inset:0;display:flex;align-items:center;justify-content:center;color:var(--texto-inverso);font-size:.75em;font-weight:900">✓</span>':''}
       </div>`).join('');
    document.getElementById('edit-color-label').textContent = SEG_COLORS[curColor]?.label || '';
    colorSection.style.display = 'flex';
    modal._color = curColor;
  } else {
    colorSection.style.display = 'none';
    modal._color = undefined;
  }

  // ── Fields ──
  const html = fields.map(([k, v]) => {
    const safeK  = k.replace(/"/g,'&quot;');
    const safeV  = String(v).replace(/"/g,'&quot;').replace(/</g,'&lt;');
    const fullRow = _isLongField(k, v) ? 'grid-column:1/-1' : '';
    const icon   = _isDateField(k) ? '📅 ' : '';

    if (_isDateField(k)) {
      return `<div class="edit-field-group" style="${fullRow}">
        <label>${icon}${k}</label>
        <input type="date" data-field="${safeK}" data-type="date" value="${toInputDate(String(v))}">
      </div>`;
    }
    if (opts[k]) {
      const opts2 = opts[k].map(o=>
        `<option value="${o.replace(/"/g,'&quot;')}"${o===String(v).trim()?' selected':''}>${o}</option>`).join('');
      return `<div class="edit-field-group" style="${fullRow}">
        <label>${k}</label>
        <select data-field="${safeK}"><option value=""></option>${opts2}</select>
      </div>`;
    }
    if (_isLongField(k, v)) {
      return `<div class="edit-field-group" style="${fullRow}">
        <label>${k}</label>
        <textarea data-field="${safeK}" rows="3">${String(v).replace(/</g,'&lt;')}</textarea>
      </div>`;
    }
    return `<div class="edit-field-group">
      <label>${k}</label>
      <input data-field="${safeK}" value="${safeV}">
    </div>`;
  }).join('');

  // Subtitle = primer valor no vacío
  const subtitle = (fields.find(([,v]) => String(v).trim())?.[1] || '').slice(0, 55);
  document.getElementById('edit-modal-title').textContent = `✏️ Editar — ${ctx.label}`;
  document.getElementById('edit-modal-subtitle').textContent = subtitle;
  document.getElementById('edit-seg-fields').innerHTML = html;
  modal._rowNum = rowNum;
  modal.style.display = 'block';
}

function selectEditColor(el) {
  const code = el.dataset.color;
  document.querySelectorAll('#edit-color-picker .color-opt').forEach(d => {
    d.style.border = '3px solid transparent';
    d.innerHTML = '';
  });
  el.style.border = '3px solid var(--gris-800)';
  el.innerHTML = '<span style="position:absolute;inset:0;display:flex;align-items:center;justify-content:center;color:var(--texto-inverso);font-size:.75em;font-weight:900">✓</span>';
  document.getElementById('edit-seg-modal')._color = code;
  document.getElementById('edit-color-label').textContent = SEG_COLORS[code]?.label || '';
}

function openEditSeg(rowNum) {
  openEdit({ endpoint: '/api/seguimiento/update', rowMap: _segRowMap,
    columnOptions: _segColumnOptions, label: 'Seguimiento',
    reload: async () => { delete state.loaded['seguimiento']; await loadSeguimiento(); }
  }, rowNum);
}

async function loadMensajes() {
  const data = await fetchAPI('/api/prospectos/mensajes');
  // Poblar mapa por columna
  Object.keys(_menColMap).forEach(k => delete _menColMap[k]);
  data.forEach(d => { _menColMap[d._col] = d; });

  const container = document.getElementById('mensajes-table');
  document.getElementById('mensajes-pag').innerHTML = '';
  if (!data.length) {
    Estados.vacio(container, {
      titulo: 'No hay mensajes configurados',
      detalle: 'Se cargan desde la hoja «Mensajes»; en cuanto tenga filas aparecerán aquí.',
    });
    return;
  }
  container.innerHTML = `<div class="men-grid">${data.map(d => `
    <div class="men-card">
      <div class="men-card-header">
        <span class="men-card-tipo">💬 ${d.Tipo}</span>
        <button class="btn-edit-row" onclick="openEditMen(${d._col})">✏️ Editar</button>
      </div>
      ${d.Contenido
        ? `<div class="men-card-content">${d.Contenido.replace(/</g,'&lt;').replace(/\n/g,'<br>')}</div>`
        : `<div class="men-card-empty">(Sin contenido)</div>`
      }
    </div>`).join('')}</div>`;
}

function filterMensajes(q) {
  const lq = q.toLowerCase();
  document.querySelectorAll('.men-card').forEach(card => {
    const text = card.textContent.toLowerCase();
    card.style.display = (!lq || text.includes(lq)) ? '' : 'none';
  });
}

function openEditMen(colKey) {
  const row = _menColMap[colKey];
  if (!row) return;
  _editCtx = {
    endpoint: '/api/mensajes/update',
    rowMap: _menColMap,
    label: 'Mensajes',
    reload: async () => { delete state.loaded['mensajes']; await loadMensajes(); }
  };
  const modal = document.getElementById('edit-seg-modal');
  document.getElementById('edit-color-section').style.display = 'none';
  modal._color = undefined;
  modal._rowNum = colKey;
  document.getElementById('edit-modal-title').textContent = `✏️ ${row.Tipo}`;
  document.getElementById('edit-modal-subtitle').textContent = '';
  document.getElementById('edit-seg-fields').innerHTML = `
    <div class="edit-field-group" style="grid-column:1/-1">
      <label>Contenido</label>
      <textarea data-field="Contenido" rows="10" style="min-height:180px">${(row.Contenido || '').replace(/</g,'&lt;')}</textarea>
    </div>`;
  modal.style.display = 'block';
}

function closeEditSeg() {
  document.getElementById('edit-seg-modal').style.display = 'none';
}

async function saveEdit() {
  const modal = document.getElementById('edit-seg-modal');
  const rowNum = modal._rowNum;
  const row = _editCtx.rowMap[rowNum];
  if (!row) return;
  const inputs = modal.querySelectorAll('[data-field]');
  const payload = {};
  if (row._row !== undefined) payload._row = row._row;
  if (row._col !== undefined) payload._col = row._col;
  inputs.forEach(el => {
    payload[el.dataset.field] = el.dataset.type === 'date' ? fromInputDate(el.value) : el.value;
  });
  // Guardar color en localStorage
  if (_editCtx.label === 'Seguimiento' && row._row !== undefined) {
    const color = modal._color !== undefined ? modal._color : '';
    if (color) _segColorMap[row._row] = color;
    else        delete _segColorMap[row._row];
    _saveColorMap();
  }
  const btn = document.getElementById('edit-seg-save');
  btn.textContent = '⏳ Guardando...'; btn.disabled = true;
  try {
    const res = await fetch(_editCtx.endpoint, {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (data.ok) {
      closeEditSeg();
      if (_editCtx.reload) await _editCtx.reload();
    } else {
      alert('Error: ' + (data.error || 'No se pudo guardar'));
    }
  } catch(e) { alert('Error de conexión'); }
  btn.textContent = '💾 Guardar cambios'; btn.disabled = false;
}

// ─── UTILS ──────────────────────────────────────────────────────────────────
function destroyChart(id) {
  if (charts[id]) { charts[id].destroy(); delete charts[id]; }
}

function updateCacheBadge() {
  document.getElementById('cache-badge').textContent = 'Actualizado ' + new Date().toLocaleTimeString('es-MX', {hour:'2-digit',minute:'2-digit'});
}

async function refreshData() {
  await fetch('/api/refresh', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({key:'all'}) });
  Object.keys(state.loaded).forEach(k => delete state.loaded[k]);
  ['chartResultados','chartSemanas','chartCiudades','chartVentasMes'].forEach(destroyChart);
  loadSection(state.currentSection);
}

// ─── BUSCAR IMAGEN EN DRIVE ──────────────────────────────────────────────────
async function buscarEnDrive(nombreEnc, factura) {
  const cell = document.getElementById(`pago-cell-${factura}`);
  if (cell) cell.innerHTML = '<span style="font-size:.78em;color:var(--texto-suave)">🔍 Buscando...</span>';

  try {
    const res = await fetch(`/api/ventas/buscar-imagen?nombre=${nombreEnc}`);
    const data = await res.json();

    if (data.encontrado) {
      // Actualizar celda visualmente
      if (cell) {
        cell.innerHTML = `<span style="display:flex;align-items:center;gap:6px">
          <img src="${data.thumb}" style="height:40px;border-radius:4px;cursor:pointer;border:1px solid var(--borde)" onclick="verImagen('${data.url}','${data.thumb}')">
          <a href="${data.url}" target="_blank" style="color:var(--blue);font-size:.78em">🔍 Abrir</a>
        </span>`;
      }
      // Actualizar el sheet con la URL encontrada
      const form = new FormData();
      form.append('num_factura', factura);
      form.append('url_existente', data.url);
      await fetch('/api/ventas/update-pago-url', { method: 'POST', body: form });
    } else {
      if (cell) cell.innerHTML = `<span style="display:flex;align-items:center;gap:5px">
        <span style="font-size:.72em;color:var(--texto-suave)">No en Drive</span>
        <button class="btn-upload-pago" onclick="abrirUpload('${factura}',this)">📤 Subir</button>
      </span>`;
    }
  } catch(e) {
    if (cell) cell.innerHTML = `<button class="btn-upload-pago" onclick="abrirUpload('${factura}',this)">📤 Subir</button>`;
  }
}

// ─── UPLOAD PAGO ─────────────────────────────────────────────────────────────
function abrirUpload(numFactura, btn) {
  const modal = document.getElementById('modal-upload');
  document.getElementById('upload-factura').value = numFactura;
  document.getElementById('upload-preview').innerHTML = '';
  document.getElementById('upload-status').textContent = '';
  document.getElementById('upload-file').value = '';
  document.getElementById('upload-factura-display').textContent = numFactura || '(sin factura)';
  modal.style.display = 'flex';
  state._uploadBtn = btn;
}

function cerrarUpload() {
  document.getElementById('modal-upload').style.display = 'none';
}

function previewImagen(input) {
  const file = input.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = e => {
    document.getElementById('upload-preview').innerHTML =
      `<img src="${e.target.result}" style="max-height:160px;border-radius:8px;border:1px solid var(--borde);margin-top:8px">`;
  };
  reader.readAsDataURL(file);
}

async function subirComprobante() {
  const fileInput = document.getElementById('upload-file');
  const numFactura = document.getElementById('upload-factura').value;
  const statusEl = document.getElementById('upload-status');
  const btnSubir = document.getElementById('btn-subir');

  if (!fileInput.files[0]) {
    statusEl.textContent = '⚠️ Selecciona una imagen primero';
    statusEl.style.color = 'orange';
    return;
  }

  btnSubir.disabled = true;
  statusEl.textContent = '⏳ Subiendo...';
  statusEl.style.color = '#0047CC';

  const form = new FormData();
  form.append('imagen', fileInput.files[0]);
  form.append('num_factura', numFactura);

  try {
    const res = await fetch('/api/ventas/upload-pago', { method: 'POST', body: form });
    const data = await res.json();

    if (data.ok) {
      statusEl.textContent = '✅ Comprobante subido correctamente';
      statusEl.style.color = 'green';
      // Actualizar preview con la imagen de Drive
      if (data.thumb) {
        document.getElementById('upload-preview').innerHTML =
          `<img src="${data.thumb}" style="max-height:160px;border-radius:8px;border:1px solid var(--borde);margin-top:8px">
           <div style="margin-top:6px"><a href="${data.url}" target="_blank" style="color:var(--blue);font-size:.82em">Ver en Drive →</a></div>`;
      }
      // Actualizar celda en la tabla sin recargar todo
      if (state._uploadBtn) {
        const td = state._uploadBtn.closest('td');
        if (td && data.url) {
          const fileId = data.url.match(/\/d\/([^/]+)\//)?.[1] || '';
          const thumb = fileId ? `https://drive.google.com/thumbnail?id=${fileId}&sz=w120` : '';
          td.innerHTML = `<span style="display:flex;align-items:center;gap:6px">
            ${thumb ? `<img src="${thumb}" style="height:40px;border-radius:4px;cursor:pointer;border:1px solid var(--borde)" onclick="verImagen('${data.url}','${thumb}')">` : ''}
            <a href="${data.url}" target="_blank" style="color:var(--blue);font-size:.78em">Ver →</a>
          </span>`;
        }
      }
      // Invalidar cache
      fetch('/api/refresh', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({key:'ventas'}) });
      setTimeout(cerrarUpload, 2000);
    } else {
      statusEl.textContent = '❌ Error: ' + (data.error || 'desconocido');
      statusEl.style.color = 'red';
      btnSubir.disabled = false;
    }
  } catch (e) {
    statusEl.textContent = '❌ Error de red: ' + e.message;
    statusEl.style.color = 'red';
    btnSubir.disabled = false;
  }
}

function verImagen(url, full) {
  const m   = document.getElementById('modal-imagen');
  const img = document.getElementById('img-full');
  img.src = '';
  img.style.opacity = '0';
  img.onload = () => { img.style.transition = 'opacity .3s'; img.style.opacity = '1'; };
  img.src = full || url;
  document.getElementById('img-link').href = url;
  m.style.display = 'flex';
}

function cerrarImagen() {
  document.getElementById('modal-imagen').style.display = 'none';
}

// ─── LISTENER GLOBAL THUMBNAILS PAGO ────────────────────────────────────────
document.addEventListener('click', function(e) {
  const img = e.target.closest('.pago-thumb');
  if (!img) return;
  const full = img.getAttribute('data-full');
  const link = img.getAttribute('data-link');
  if (full || link) verImagen(link, full);
});

// ─── ENVÍOS DE CATÁLOGO — números a corregir ─────────────────────────────────
const CAT_ESTADOS_PROBLEMA = ['NUMERO_INVALIDO', 'FALLO'];
let _catSel = null;
function _catEsc(s){ return String(s==null?'':s).replace(/[&<>"']/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }

async function _catFetchProblema(){
  const [inv, fall] = await Promise.all([
    fetch('/api/catalogo/envios?estado=NUMERO_INVALIDO').then(r=>r.json()),
    fetch('/api/catalogo/envios?estado=FALLO').then(r=>r.json()),
  ]);
  return [].concat(inv.envios||[], fall.envios||[]);
}

function _catTag(estado){
  const e = String(estado||'').toUpperCase();
  if (e==='ENVIADO') return '<span class="tag aprobado">Enviado</span>';
  if (e==='NUMERO_INVALIDO') return '<span class="tag negado">Número inválido</span>';
  if (e==='FALLO') return '<span class="tag no-compatible">Falló</span>';
  if (e==='PENDIENTE') return '<span class="tag buzon">Pendiente</span>';
  if (e==='EN_PROCESO') return '<span class="tag default">En proceso</span>';
  return '<span class="tag default">'+_catEsc(estado)+'</span>';
}

async function loadCatalogo(){
  const filtro = document.getElementById('cat-filtro').value;
  const cont = document.getElementById('catalogo-table');
  const quitarEsqueleto = Estados.esqueleto(cont, 'tabla');
  let envios = [];
  try {
    if (filtro === 'problema') envios = await _catFetchProblema();
    else { const d = await fetch('/api/catalogo/envios'+(filtro?('?estado='+filtro):'')).then(r=>r.json()); envios = d.envios||[]; }
  } catch(e){
    quitarEsqueleto();
    Estados.error(cont, {
      titulo: 'No se pudieron cargar los envíos',
      detalle: mensajeDeFallo(e),
      reintentar: loadCatalogo,
    });
    return;
  }
  quitarEsqueleto();
  renderCatalogo(envios);
  actualizarBadgeCatalogo();
}

function renderCatalogo(envios){
  const cont = document.getElementById('catalogo-table');
  if (!envios.length){
    Estados.vacio(cont, {
      titulo: 'Ningún envío en este filtro',
      detalle: 'Puede ser que no haya nada pendiente, o que el worker no haya registrado nada todavía.',
    });
    return;
  }
  const rows = envios.map(e=>{
    const prob = CAT_ESTADOS_PROBLEMA.includes(String(e.estado).toUpperCase());
    const acc = prob
      ? `<button class="btn-refresh" style="padding:4px 10px;font-size:.76em" onclick='catAbrirCorregir(${JSON.stringify(e).replace(/'/g,"&#39;")})'>✏️ Corregir</button> `
        + `<button class="btn-refresh" style="padding:4px 10px;font-size:.76em" onclick="catReintentar(${e._row})">🔁 Reintentar</button>`
      : '—';
    return `<tr><td>${_catEsc(e.tienda)}</td><td>${_catEsc(e.telefono)}</td><td>${_catTag(e.estado)}</td>`
         + `<td style="text-align:center">${_catEsc(e.intentos)}</td><td style="font-size:.8em;color:var(--texto-suave)">${_catEsc(e.timestamp_estado)}</td><td>${acc}</td></tr>`;
  }).join('');
  cont.innerHTML = `<table><thead><tr><th>Tienda</th><th>Teléfono</th><th>Estado</th><th>Intentos</th><th>Actualizado</th><th>Acción</th></tr></thead><tbody>${rows}</tbody></table>`;
  escalonarFilas(cont);
}

async function actualizarBadgeCatalogo(){
  try {
    const envios = await _catFetchProblema();
    const badge = document.getElementById('cat-badge');
    if (!badge) return;
    if (envios.length){ badge.textContent = envios.length; badge.style.display='inline-block'; }
    else badge.style.display='none';
  } catch(e){ /* silencioso */ }
}

function catAbrirCorregir(e){
  _catSel = e;
  document.getElementById('modal-corregir-cat').style.display = 'flex';
  document.getElementById('cat-corr-tienda').textContent = e.tienda || '';
  const inp = document.getElementById('cat-corr-input'); inp.value = ''; inp.focus();
  document.getElementById('cat-corr-error').textContent = '';
  document.getElementById('cat-corr-btn').disabled = true;
}
function catValidarCorregir(){
  const v = document.getElementById('cat-corr-input').value;
  const dig = (v.match(/\d/g)||[]).length; const ok = dig>=10 && dig<=13;
  document.getElementById('cat-corr-btn').disabled = !ok;
  document.getElementById('cat-corr-error').textContent = (v && !ok) ? 'Deben ser 10 a 13 dígitos.' : '';
  return ok;
}
async function catGuardarCorreccion(){
  if (!catValidarCorregir() || !_catSel) return;
  const btn = document.getElementById('cat-corr-btn'); btn.disabled = true;
  try {
    const r = await fetch('/api/catalogo/corregir-numero', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ envio_row: _catSel._row, telefono: document.getElementById('cat-corr-input').value, contacto_row: _catSel.fila_respuesta })
    });
    const d = await r.json();
    if (d.ok) { catCerrarModal(); loadCatalogo(); }
    else { document.getElementById('cat-corr-error').textContent = d.error || 'No se pudo corregir.'; btn.disabled = false; }
  } catch(e){ document.getElementById('cat-corr-error').textContent = 'Error de conexión.'; btn.disabled = false; }
}
async function catReintentar(row){
  try {
    const r = await fetch('/api/catalogo/reintentar', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ envio_row: row }) });
    const d = await r.json();
    if (!d.ok) alert('⚠️ ' + (d.error || 'No se pudo reintentar.'));
    loadCatalogo();
  } catch(e){ alert('⚠️ Error de conexión.'); }
}
function catCerrarModal(){ document.getElementById('modal-corregir-cat').style.display = 'none'; }

// ─── INIT ────────────────────────────────────────────────────────────────────
// Antes de la primera grafica: aplicarla despues dejaria las seis nacidas con
// la animacion puesta.
aplicarPreferenciaDeMovimiento();
loadSection('dashboard');
actualizarBadgeCatalogo();  // badge de "números a corregir" desde el arranque

// ─── PROSPECTOS BRUCE ────────────────────────────────────────────────────────
let _bruceData = [];

function _initBruceForm() {
  const now = new Date();
  const dd = String(now.getDate()).padStart(2,'0');
  const mm = String(now.getMonth()+1).padStart(2,'0');
  const yy = now.getFullYear();
  const hh = String(now.getHours()).padStart(2,'0');
  const mi = String(now.getMinutes()).padStart(2,'0');
  document.getElementById('bf-fecha').value = `${dd}/${mm}/${yy} ${hh}:${mi}`;
}

async function loadBruce() {
  _initBruceForm();
  const data = await fetchAPI('/api/bruce/prospectos');
  _bruceData = data;
  renderBruceTable(data);
}

function filterBruce(q) {
  const lq = q.toLowerCase();
  const filtered = lq ? _bruceData.filter(r =>
    Object.values(r).some(v => String(v).toLowerCase().includes(lq))
  ) : _bruceData;
  renderBruceTable(filtered);
}

function renderBruceTable(data) {
  const container = document.getElementById('bruce-table');
  document.getElementById('bruce-pag').innerHTML = '';
  if (!data.length) {
    Estados.vacio(container, {
      titulo: 'Sin prospectos todavía',
      detalle: 'Los que agregues con el formulario de arriba aparecerán en esta tabla.',
    });
    return;
  }
  let html = `<table><thead><tr>
    <th>Fecha</th><th>Nombre</th><th>Teléfono</th><th>Tipo de Interés</th>
    <th style="text-align:center">Contactado</th><th>NOTA</th><th style="width:60px"></th>
  </tr></thead><tbody>`;
  data.forEach(r => {
    const casilla = (r['Contactado'] || '').trim() === '✓';
    html += `<tr>
      <td style="white-space:nowrap;font-size:.8em">${r['Fecha'] || ''}</td>
      <td style="font-weight:600">${r['Nombre'] || ''}</td>
      <td>${r['Teléfono'] || ''}</td>
      <td>${r['Tipo de Interés'] || ''}</td>
      <td style="text-align:center">
        <span class="bruce-casilla" onclick="toggleContactadoBruce(${r._row}, this)" title="Marcar/desmarcar">
          ${casilla ? '✅' : '⬜'}
        </span>
      </td>
      <td style="font-size:.82em;max-width:220px;word-break:break-word">${(r['NOTA'] || '').replace(/</g,'&lt;').replace(/\n/g,'<br>')}</td>
      <td><button class="btn-edit-row" onclick="editNotaBruce(${r._row})">✏️</button></td>
    </tr>`;
  });
  html += '</tbody></table>';
  container.innerHTML = html;
  escalonarFilas(container);
}

async function agregarBruce() {
  const nombre = document.getElementById('bf-nombre').value.trim();
  if (!nombre) { alert('El Nombre es obligatorio'); return; }
  const payload = {
    'Nombre':         nombre,
    'Teléfono':       document.getElementById('bf-tel').value.trim(),
    'Tipo de Interés':document.getElementById('bf-tipo').value.trim(),
    'NOTA':           document.getElementById('bf-nota').value.trim(),
  };
  const btn = document.querySelector('#bruce-form .btn-blue');
  btn.textContent = '⏳ Guardando...'; btn.disabled = true;
  try {
    const res = await fetch('/api/bruce/agregar', {
      method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)
    });
    const d = await res.json();
    if (d.ok) {
      ['bf-nombre','bf-tel','bf-tipo','bf-nota'].forEach(id => document.getElementById(id).value = '');
      delete state.loaded['bruce'];
      await loadBruce();
    } else { alert('Error: ' + (d.error || 'No se pudo guardar')); }
  } catch(e) { alert('Error de conexión'); }
  btn.textContent = '➕ Agregar Prospecto'; btn.disabled = false;
}

async function toggleContactadoBruce(rowNum, el) {
  const actual = el.textContent.trim() === '✅';
  const nuevo  = actual ? '' : '✓';
  el.textContent = nuevo ? '✅' : '⬜';
  await fetch('/api/bruce/actualizar', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({ _row: rowNum, 'Contactado': nuevo })
  });
  const rec = _bruceData.find(r => r._row === rowNum);
  if (rec) rec['Contactado'] = nuevo;
}

function editNotaBruce(rowNum) {
  const rec = _bruceData.find(r => r._row === rowNum);
  if (!rec) return;
  _editCtx = {
    endpoint: '/api/bruce/actualizar',
    rowMap: Object.fromEntries(_bruceData.map(r => [r._row, r])),
    label: 'Bruce',
    reload: async () => { delete state.loaded['bruce']; await loadBruce(); }
  };
  const modal = document.getElementById('edit-seg-modal');
  document.getElementById('edit-color-section').style.display = 'none';
  modal._color = undefined;
  modal._rowNum = rowNum;
  document.getElementById('edit-modal-title').textContent = `✏️ ${rec['Nombre'] || 'Prospecto'}`;
  document.getElementById('edit-modal-subtitle').textContent = rec['Tipo de Interés'] || '';
  document.getElementById('edit-seg-fields').innerHTML = `
    <div class="edit-field-group" style="grid-column:1/-1">
      <label>NOTA</label>
      <textarea data-field="NOTA" rows="8" style="min-height:160px">${(rec['NOTA'] || '').replace(/</g,'&lt;')}</textarea>
    </div>`;
  modal.style.display = 'block';
}
