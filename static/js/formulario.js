const _ventanasAbiertas = [];
function abrirVentana(url) {
  // `noopener` no es opcional: sin el, la pestana que se abre conserva
  // `window.opener` y puede redirigir la del panel a donde quiera. Un sitio
  // que imite el login del panel, con el operador convencido de que su pestana
  // de siempre sigue ahi, es una via de robo de credenciales bastante barata.
  // La URL sale de la hoja, que edita gente y alimenta el importador.
  const w = window.open(url, '_blank',
    'noopener,noreferrer,width=1000,height=700,left=100,top=80');
  if (w) _ventanasAbiertas.push(w);
}
function cerrarVentanasContacto() {
  while (_ventanasAbiertas.length) {
    const w = _ventanasAbiertas.pop();
    try { if (w && !w.closed) w.close(); } catch(e) {}
  }
}

const O = {
  skip: 0,
  procesados: 0,
  contacto: null,
  resultado: '',
  r0:'', r1:'', r2:'', r3:'', r4:'', r5:'', r6:'', r7:'',
  opcionesP1: [],
};

// El nombre de la tienda, la ciudad y la categoria vienen de la hoja. Se
// interpolaban crudos en `innerHTML`: un `<img src=x onerror=...>` en el
// nombre de una tienda ejecutaba en la pantalla del operador. Se reutiliza el
// escapador del sistema de estados, que ya carga esta pagina.
function esc(s) {
  return (window.Estados && Estados.escapar)
    ? Estados.escapar(s)
    : String(s == null ? '' : s)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

const PASOS = ['loading','contacto','p0','p1','p2','p3','p4','p5','p6','p7','guardando','siguiente','fin','error','guardado-error'];
const TOTAL_PREGUNTAS = 7;

function showStep(name) {
  PASOS.forEach(p => {
    const el = document.getElementById('step-' + p);
    if (el) el.classList.toggle('active', p === name);
  });
  prepararPaso(document.getElementById('step-' + name));
}

// Los botones de cada paso, en orden de lectura. Se excluyen los enlaces del
// contacto (Maps, Sitio Web, Llamar): no son respuestas, son herramientas.
function opcionesDelPaso(paso) {
  if (!paso) return [];
  // Se numeran TAMBIEN los deshabilitados. En el paso p1 el boton "Continuar"
  // nace deshabilitado y se habilita al marcar una opcion: si se numerara solo
  // lo habilitado, ese boton se quedaria sin digito, o peor, renumeraria todo
  // a media pregunta y el operador veria cambiar los numeros bajo el dedo.
  // El manejador de teclado ya ignora los deshabilitados.
  return Array.prototype.filter.call(
    paso.querySelectorAll('button'),
    b => !b.classList.contains('link-btn'));
}

// Dos cosas que el formulario no hacia y que cuestan una jornada entera:
//
// 1. **El foco no viajaba.** Al ocultar el paso anterior con `display:none`,
//    el foco caia a <body>, asi que para responder con teclado habia que
//    tabular desde el principio del documento EN CADA UNA de las siete
//    preguntas, llamada tras llamada.
//
// 2. **Los atajos no existian.** Las etiquetas decian "1 — Respondio",
//    "2 — Buzon", "0 — Telefono Incorrecto", pero no habia un solo manejador
//    de teclado en el archivo: los numeros eran decoracion. Ahora cada opcion
//    del paso lleva su digito, se ve en la propia etiqueta y funciona.
function prepararPaso(paso) {
  const opciones = opcionesDelPaso(paso);
  opciones.forEach((btn, i) => {
    if (i < 9) {
      const digito = String(i + 1);
      btn.dataset.atajo = digito;
      if (!btn.querySelector('.tecla')) {
        // El texto del boton se guarda ANTES de meterle la pastilla: despues
        // ya no se puede distinguir el digito del nombre de la opcion.
        btn.dataset.etiqueta = (btn.textContent || '').trim();
        const kbd = document.createElement('kbd');
        kbd.className = 'tecla';
        kbd.setAttribute('aria-hidden', 'true');   // no se lee dos veces
        kbd.textContent = digito;
        btn.prepend(kbd);
      }
      btn.setAttribute('aria-keyshortcuts', digito);
      // Y el digito va TAMBIEN en el nombre accesible. `aria-keyshortcuts` es
      // metadata que la mayoria de lectores no anuncia por defecto, asi que
      // sin esto los tres botones de p0 -que antes llevaban el numero escrito
      // en el texto visible, "1 — Respondio"- se lo habrian quedado quien ve
      // la pantalla y perdido quien la escucha. Sale peor de lo que estaba.
      const etiqueta = btn.dataset.etiqueta || (btn.textContent || '').trim();
      if (etiqueta) btn.setAttribute('aria-label', digito + '. ' + etiqueta);
    }
  });
  // El foco va a la primera opcion USABLE: la numeracion incluye las
  // deshabilitadas, pero enfocar una deshabilitada deja al operador con el
  // foco en la nada.
  const primera = opciones.find(b => !b.disabled);
  // `preventScroll` porque el formulario cabe en pantalla y un salto de scroll
  // aqui solo desorienta.
  if (primera) primera.focus({ preventScroll: true });
}

// Un digito activa su opcion. Se ignora si el foco esta en un campo de texto:
// el modal de correo y el de telefono se escriben con numeros.
document.addEventListener('keydown', (ev) => {
  if (ev.ctrlKey || ev.altKey || ev.metaKey) return;
  const activo = document.activeElement;
  if (activo && /^(INPUT|TEXTAREA|SELECT)$/.test(activo.tagName)) return;
  // Con un modal abierto manda el modal, no el paso de debajo.
  const modalAbierto = Array.prototype.some.call(
    document.querySelectorAll('[id^="modal-"]'),
    m => m.style.display && m.style.display !== 'none');
  if (modalAbierto) return;
  if (!/^[1-9]$/.test(ev.key)) return;
  const paso = document.querySelector('.step.active');
  const btn = paso && paso.querySelector('button[data-atajo="' + ev.key + '"]:not([disabled])');
  if (btn) { ev.preventDefault(); btn.click(); }
});

function setProgress(stepId, actual, total) {
  const el = document.getElementById(stepId);
  if (!el) return;
  el.innerHTML = Array.from({length: total}, (_,i) =>
    `<div class="prog-step ${i < actual ? 'done' : i === actual ? 'active' : ''}"></div>`
  ).join('');
}

// Un fallo de lectura NO es el fin de la lista. Hasta la T4.5 lo era: el
// backend se tragaba la excepción de Google y devolvía `{fin: true}`, así que
// con las hojas caídas el operador veía «🎉 ¡Lista completada!» y dejaba de
// llamar. La celebración queda reservada a estados verificados.
function mostrarErrorDeLectura(e) {
  const m = String((e && e.message) || e || '');
  document.getElementById('header-sub').textContent = 'No se pudo cargar el contacto';
  // El paso se revela ANTES de escribir el texto, y no al revés. Los pasos
  // inactivos son `display:none`, que los saca del árbol de accesibilidad: si
  // el texto se escribe con el bloque todavía oculto, la mutación de la región
  // viva ocurre donde nadie la ve, y revelarla después no cuenta como cambio.
  // Resultado del orden anterior: el error no se anunciaba NUNCA.
  showStep('error');
  document.getElementById('error-detalle').textContent =
    /Failed to fetch|NetworkError/i.test(m)
      ? 'Sin conexión con el panel. Revisa la red y vuelve a intentarlo.'
      : (m || 'El panel no pudo leer la hoja de contactos.');
  // El foco va al reintento: es la única acción disponible y el operador puede
  // estar trabajando solo con teclado. Aquí es seguro moverlo porque el
  // formulario muestra un paso a la vez; en el tablero no se hace, que ahí
  // pueden aparecer dos bloques de error a la vez y se pelearían por el foco.
  const btn = document.getElementById('btn-reintentar-contacto');
  if (btn) btn.focus();
}

async function cargarContacto() {
  cerrarVentanasContacto();
  showStep('loading');
  document.getElementById('header-sub').textContent = 'Cargando contacto...';
  let d;
  try {
    const r = await fetch(`/api/formulario/siguiente?skip=${O.skip}`);
    d = await r.json();
    if (!r.ok || d.error) throw new Error(d.error || ('HTTP ' + r.status));
  } catch (e) {
    mostrarErrorDeLectura(e);
    return;
  }
  if (d.fin) { showStep('fin'); document.getElementById('stat-total').textContent = O.procesados; return; }
  O.contacto = d.contacto;
  O._telConfirmado = null;   // reset del número confirmado por contacto
  renderContacto(d.contacto);
}

function renderContacto(c) {
  const tienda = c.TIENDA || c.Tienda || c.Nombre || '(Sin nombre)';
  const ciudad = c.CIUDAD || c.Ciudad || '';
  const tel    = c.CONTACTO || c.TELÉFONO || c['Teléfono'] || c.TELEFONO || c.Telefono || '';
  const maps   = c.Maps || c.MAPS || '';
  const link   = c.Link || c.LINK || '';
  const cat    = c['CATEGORIA '] || c.CATEGORIA || c.Categoria || '';
  const esq    = c.Esquema || c.ESQUEMA || '';

  document.getElementById('badge-ciudad').textContent = `📍 ${ciudad || 'Sin ciudad'}`;
  document.getElementById('header-sub').textContent = tienda;

  const campos = [
    {l:'Tienda', v: tienda, full: true},
    {l:'Teléfono', v: tel},
    {l:'Ciudad', v: ciudad},
    {l:'Categoría', v: cat},
    {l:'Esquema', v: esq},
    {l:'Contacto', v: c.CONTACTO || c.Contacto || ''},
  ].filter(x => x.v);

  document.getElementById('info-grid').innerHTML = campos.map(f =>
    `<div class="info-item ${f.full?'full':''}"><div class="lbl">${esc(f.l)}</div><div class="val">${esc(f.v)}</div></div>`
  ).join('');

  // La URL viaja por `data-url`, nunca dentro de un atributo de codigo: el
  // `replace` de comillas anterior solo tapaba un caracter y dejaba pasar el
  // resto. Y se exige http(s) explicitamente para cerrar `javascript:`.
  const links = [];
  const seguro = u => /^https?:\/\//i.test(u);
  if (seguro(maps)) links.push(
    `<button type="button" class="link-btn" data-url="${esc(maps)}">🗺️ Google Maps</button>`);
  if (seguro(link)) links.push(
    `<button type="button" class="link-btn" data-url="${esc(link)}">🌐 Sitio Web</button>`);
  if (tel) links.push(
    `<a class="link-btn" href="tel:${encodeURIComponent(tel)}">📞 Llamar</a>`);
  document.getElementById('links-contacto').innerHTML = links.join('');

  showStep('contacto');
}

function decidir(resultado) {
  O.resultado = resultado;
  O.r1=''; O.r2=''; O.r3=''; O.r4=''; O.r5=''; O.r6=''; O.r7='';
  if (resultado === 'APROBADO') {
    O.r0 = '';  // se captura en p0
    setProgress('prog0', 0, TOTAL_PREGUNTAS);
    showStep('p0');
  } else {
    // NEGADO / NO COMPATIBLE / MARCA UNICA → el cliente respondió
    O.r0 = 'Respondio';
    guardar();
  }
}

function resp0(v) {
  O.r0 = v;
  if (v === 'Respondio') {
    renderP1();
    setProgress('prog1', 1, TOTAL_PREGUNTAS);
    showStep('p1');
  } else {
    guardar();
  }
}

function renderP1() {
  const opciones = ['Entregas Rápidas','Líneas de Crédito','Contra Entrega','Envío Gratis','Precio Preferente','Evaluar Calidad'];
  O.opcionesP1 = [];
  // Estas seis opciones son CONSTANTES del codigo, no vienen de la hoja: se
  // escapan igual porque el patron tiene que ser el mismo en todo el archivo,
  // pero que nadie las de por "ya cubiertas" si algun dia pasan a leerse de
  // fuera. Lo que si cambia es que la opcion viaja por `data-opcion` en vez de
  // interpolarse dentro de un `onclick`.
  document.getElementById('sel-p1').innerHTML = opciones.map(op =>
    `<button type="button" class="btn btn-blue btn--opcion" data-opcion="${esc(op)}">${esc(op)}</button>`
  ).join('');
}

document.addEventListener('click', (ev) => {
  const enlace = ev.target.closest('.link-btn[data-url]');
  if (enlace) { abrirVentana(enlace.dataset.url); return; }
  const opcion = ev.target.closest('#sel-p1 .btn--opcion');
  if (opcion) { toggleP1(opcion, opcion.dataset.opcion); return; }
  const corregir = ev.target.closest('.btn--corregir');
  if (corregir) {
    const caja = corregir.closest('.envio-problema');
    try { abrirCorregir(JSON.parse(caja.dataset.envio)); }
    catch (e) { console.error('envio con problema ilegible:', e); }
  }
});

function toggleP1(btn, op) {
  const idx = O.opcionesP1.indexOf(op);
  if (idx > -1) { O.opcionesP1.splice(idx, 1); btn.style.opacity='.7'; }
  else { O.opcionesP1.push(op); btn.style.opacity='1'; btn.style.background='var(--green)'; }
  document.getElementById('btn-p1').disabled = O.opcionesP1.length === 0;
}

function enviarP1() {
  O.r1 = O.opcionesP1.join(', ');
  setProgress('prog2', 2, TOTAL_PREGUNTAS);
  showStep('p2');
}

function resp2(v) { O.r2=v; setProgress('prog3',3,TOTAL_PREGUNTAS); showStep('p3'); }
function resp3(v) { O.r3=v; setProgress('prog4',4,TOTAL_PREGUNTAS); showStep('p4'); }
function resp4(v) { O.r4=v; setProgress('prog5',5,TOTAL_PREGUNTAS); showStep('p5'); }
function resp5(v) { O.r5=v; setProgress('prog6',6,TOTAL_PREGUNTAS); showStep('p6'); }
function resp6(v) { O.r6=v; setProgress('prog7',7,TOTAL_PREGUNTAS); showStep('p7'); }
function resp7(v) {
  O.r7 = v;
  if (v === 'Correo') { abrirModalCorreo(); return; }  // Plan 4: capturar correo antes de guardar
  if (v === 'Pedido' || v === 'Revisara el Catalogo') { abrirValidadorCatalogo(); return; }  // validador pre-envío
  guardar();
}

// ─── Validador PRE-envío de catálogo (confirmar/corregir número antes de encolar) ───
function abrirValidadorCatalogo() {
  const modal = document.getElementById('modal-validar-catalogo');
  modal.style.display = 'flex';
  document.getElementById('val-cat-tienda').textContent =
    O.contacto ? (O.contacto.TIENDA || O.contacto.Tienda || O.contacto.Nombre || '') : '';
  document.getElementById('val-cat-conclusion').textContent = O.r7;
  const inp = document.getElementById('val-cat-tel');
  inp.value = telContacto(O.contacto) || '';
  validarValCat();
  inp.focus();
}
// Enter confirma, Escape cancela — el mismo trato que el modal de correo.
// Sin esto el operador tenia que TABULAR desde el campo hasta el boton en cada
// pedido, que es de las conclusiones mas frecuentes.
function valCatKeydown(e) {
  if (e.key === 'Enter') {
    e.preventDefault();
    if (validarValCat()) confirmarEnviarCatalogo();
  } else if (e.key === 'Escape') {
    cerrarValidadorCatalogo();
  }
}

function validarValCat() {
  const v = document.getElementById('val-cat-tel').value;
  const dig = (v.match(/\d/g) || []).length;
  const ok = dig >= 10 && dig <= 13;
  document.getElementById('val-cat-btn').disabled = !ok;
  // Distinguir "el numero guardado esta incompleto" de "lo tecleaste mal": el
  // campo se precarga desde LISTA DE CONTACTOS y hay 131 contactos con menos de
  // 10 digitos (40 con nueve, 26 con siete, y algunos con uno solo). Sin esta
  // distincion el operador cree que se equivoco al teclear.
  const sinTocar = v === (telContacto(O.contacto) || '');
  let msg = '';
  if (v && !ok) {
    msg = (sinTocar && dig > 0 && dig < 10)
      ? 'El número guardado está incompleto (' + dig + ' dígitos). Escribe el número completo de 10 dígitos.'
      : 'Faltan dígitos: se necesitan 10 (o 12 si incluyes la lada 52).';
  }
  document.getElementById('val-cat-error').textContent = msg;
  return ok;
}
async function confirmarEnviarCatalogo() {
  if (!validarValCat()) return;
  const btn = document.getElementById('val-cat-btn'); btn.disabled = true;
  const nuevoTel = document.getElementById('val-cat-tel').value.trim();
  const origDig = (telContacto(O.contacto) || '').replace(/\D/g, '');
  const nuevoDig = nuevoTel.replace(/\D/g, '');
  try {
    // Si el número cambió, actualízalo en LISTA DE CONTACTOS (para este envío y los próximos).
    if (nuevoDig !== origDig && O.contacto && O.contacto._row) {
      const r = await fetch('/api/formulario/telefono', {
        method: 'POST', headers: {'Content-Type':'application/json'},
        body: JSON.stringify({ row: O.contacto._row, telefono: nuevoTel })
      });
      const d = await r.json();
      if (!d.ok) { document.getElementById('val-cat-error').textContent = d.error || 'No se pudo actualizar el número.'; btn.disabled = false; return; }
    }
    O._telConfirmado = nuevoTel;   // encolarCatalogo usará este número
    cerrarValidadorCatalogo();
    guardar();                     // guarda la respuesta y encola con el número confirmado
  } catch(e) {
    document.getElementById('val-cat-error').textContent = 'Error de conexión.'; btn.disabled = false;
  }
}
function cerrarValidadorCatalogo() { document.getElementById('modal-validar-catalogo').style.display = 'none'; }

// ─── Plan 4: captura de correo (conclusión "Correo") ───
function abrirModalCorreo() {
  _enviandoCorreo = false;
  document.getElementById('modal-correo').style.display = 'flex';
  const inp = document.getElementById('correo-input');
  inp.value = ''; inp.disabled = false; inp.focus();
  document.getElementById('correo-error').textContent = '';
  document.getElementById('correo-btn').disabled = true;
}
function validarCorreo() {
  const v = document.getElementById('correo-input').value.trim();
  const ok = /^[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}$/.test(v) && v.length <= 254;
  document.getElementById('correo-btn').disabled = !ok;
  document.getElementById('correo-error').textContent = (v && !ok) ? 'Correo inválido.' : '';
  return ok;
}
function correoKeydown(e) {
  if (e.key === 'Enter') { e.preventDefault(); guardarCorreo(); }
  else if (e.key === 'Escape') { continuarSinCorreo(); }
}
let _enviandoCorreo = false;
async function guardarCorreo() {
  if (_enviandoCorreo || !validarCorreo()) return;  // guard de reentrancia (doble Enter)
  _enviandoCorreo = true;
  const btn = document.getElementById('correo-btn');
  const inp = document.getElementById('correo-input');
  btn.disabled = true; inp.disabled = true;
  const fallar = (msg) => {
    document.getElementById('correo-error').textContent = msg;
    btn.disabled = false; inp.disabled = false; _enviandoCorreo = false;
  };
  try {
    const r = await fetch('/api/formulario/correo', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ row: O.contacto ? O.contacto._row : null,
                             correo: inp.value.trim() })
    });
    const d = await r.json();
    if (d.ok) { cerrarModalCorreo(); guardar(); }  // guardar() tiene su propio guard
    else fallar(d.error || 'No se pudo guardar el correo.');
  } catch(e) { fallar('Error de conexión.'); }
}
function continuarSinCorreo() { if (_enviandoCorreo) return; cerrarModalCorreo(); guardar(); }  // sin escribir T
function cerrarModalCorreo() { document.getElementById('modal-correo').style.display = 'none'; }

function colgo() { O.r7='Colgo'; guardar(); }
function encNoDisp() { O.resultado='Enc No Disponible'; O.r0='Respondio'; O.r7='Enc No Disponible'; guardar(); }

function saltarContacto() { O.skip++; cargarContacto(); }

let _guardando = false;

// `guardar()` ARMA el payload; `enviarGuardado()` lo MANDA. Separarlos es lo
// que hace posible reintentar con exactamente lo mismo que fallo, en vez de
// obligar al operador a rehacer la llamada de memoria.
function guardar() {
  if (_guardando) return;  // guard de reentrancia: evita filas duplicadas por doble envío
  const tienda = O.contacto ? (O.contacto.TIENDA || O.contacto.Tienda || O.contacto.Nombre || '') : '';
  return enviarGuardado({
    row: O.contacto ? O.contacto._row : null,
    col_respuesta: O.contacto ? (O.contacto._col_respuesta || 6) : 6,
    tienda, resultado: O.resultado,
    r0: O.r0, r1: O.r1, r2: O.r2, r3: O.r3,
    r4: O.r4, r5: O.r5, r6: O.r6, r7: O.r7,
  });
}

async function enviarGuardado(payload) {
  if (_guardando) return;
  _guardando = true;
  showStep('guardando');
  try {
    const r = await fetch('/api/formulario/guardar', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify(payload)
    });
    const d = await r.json();
    if (!d.ok) {
      fallarGuardado(d.error || 'La hoja no aceptó la respuesta.', payload);
      return;
    }
    O.procesados++;
    document.getElementById('stat-procesados').textContent = O.procesados;
    // La confirmacion tiene que ser inequivoca: en una llamada no hay tiempo
    // de dudar si se guardo. Dice QUE se guardo y CON QUE conclusion.
    document.getElementById('resumen-guardado').textContent =
      `${payload.tienda} → ${payload.resultado}` +
      (payload.r0 && payload.r0 !== 'Respondio' ? ' (' + payload.r0 + ')' : '');
    document.getElementById('catalogo-nota').textContent = '';
    showStep('siguiente');
    // Plan 3: si la conclusión dispara catálogo (Pedido / Revisará el Catálogo), encolar el envío.
    encolarCatalogo(payload.tienda);
    _guardando = false;
  } catch(e) {
    fallarGuardado('Sin conexión con el panel. Revisa la red.', payload);
  }
}

// `alert()` era la peor forma posible de contar esto. Bloquea la pagina, roba
// el foco, no se puede leer con calma y -lo importante- al aceptarlo devolvia
// al paso de contacto SIN las respuestas: el operador tenia que rehacer la
// llamada entera de memoria. Perder una respuesta capturada es perder una
// llamada.
//
// Ahora las respuestas se conservan y el reintento reenvia EXACTAMENTE el
// mismo payload.
let _ultimoPayload = null;

function fallarGuardado(motivo, payload) {
  _guardando = false;
  _ultimoPayload = payload;
  document.getElementById('guardado-error-detalle').textContent =
    motivo + ' Tus respuestas siguen aquí: al reintentar se envían tal cual.';
  showStep('guardado-error');
}

async function reintentarGuardado() {
  if (!_ultimoPayload) { showStep('contacto'); return; }
  const payload = _ultimoPayload;
  _ultimoPayload = null;
  _guardando = false;   // `fallarGuardado` ya lo libero; se reafirma por si acaso
  await enviarGuardado(payload);
}

// Conclusiones elegibles (mismo criterio que nucleo_catalogo.CONCLUSIONES_ELEGIBLES).
const CONCLUSIONES_CATALOGO = ['pedido', 'revisara el catalogo'];

function telContacto(c) {
  return c ? (c.CONTACTO || c['TELÉFONO'] || c['Teléfono'] || c.TELEFONO || c.Telefono || '') : '';
}

async function encolarCatalogo(tienda) {
  if (!O.r7 || CONCLUSIONES_CATALOGO.indexOf(O.r7.trim().toLowerCase()) === -1) return;
  const nota = document.getElementById('catalogo-nota');
  try {
    const r = await fetch('/api/catalogo/encolar', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({
        tienda,
        telefono: O._telConfirmado || telContacto(O.contacto),
        referencia: O.contacto ? O.contacto._row : null,
        conclusion: O.r7,
      })
    });
    const d = await r.json();
    if (d && d.ok && d.estado === 'ya_encolado') {
      const est = (d.estado_actual || '').toUpperCase();
      const cuando = d.desde ? (' el ' + d.desde) : '';
      if (est === 'ENVIADO')          nota.textContent = '✅ Ya se envió' + cuando + '. No se encola de nuevo.';
      else if (est === 'FALLO')       nota.textContent = '⚠️ Hubo un fallo' + cuando + '. Usa Reintentar para volver a encolarlo.';
      else if (est === 'NUMERO_INVALIDO') nota.textContent = '⚠️ Número inválido' + cuando + '. Corrige el número y reintenta.';
      else                            nota.textContent = '📖 Ya está en la cola (' + (est || 'PENDIENTE') + cuando + ').';
    } else if (d && d.ok) {
      nota.textContent = '📖 Catálogo encolado para envío (' + (d.estado || 'PENDIENTE') + ').';
    }
    else nota.textContent = '⚠️ No se pudo encolar el catálogo.';
  } catch(e) { nota.textContent = '⚠️ No se pudo encolar el catálogo (sin conexión).'; }
}

function escHtml(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, c =>
    ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

let _envioSel = null;

async function abrirEnviosProblema() {
  document.getElementById('modal-catalogo').style.display = 'flex';
  document.getElementById('corregir-box').style.display = 'none';
  const cont = document.getElementById('envios-lista');
  cont.textContent = 'Cargando...';
  try {
    const [inv, fall] = await Promise.all([
      fetch('/api/catalogo/envios?estado=NUMERO_INVALIDO').then(r=>r.json()),
      fetch('/api/catalogo/envios?estado=FALLO').then(r=>r.json()),
    ]);
    const envios = [].concat(inv.envios||[], fall.envios||[]);
    // Sin confeti: "no hay envios con problema" puede significar que todo
    // salio bien o que el worker lleva horas caido, y esta pantalla no sabe
    // cual de las dos (regla de celebracion del ADR).
    if (!envios.length) {
      cont.innerHTML = '<p style="color:var(--gray)">Ningún envío con problema en este momento.</p>';
      return;
    }
    // El envio viaja por el `dataset` del contenedor, no interpolado dentro de
    // un atributo `onclick`. No era explotable —el `replace` de comillas
    // aguantaba— pero es el patron que este mismo commit retiro de la ficha de
    // contacto y de las opciones, y dejarlo aqui es dejar una excepcion que el
    // siguiente copiara.
    cont.innerHTML = envios.map(e =>
      `<div class="envio-problema" data-envio="${escHtml(JSON.stringify(e))}"
            style="border:1px solid var(--borde);border-radius:8px;padding:8px;margin-bottom:6px">
        <b>${escHtml(e.tienda)}</b> — <span style="color:var(--red)">${escHtml(e.estado)}</span><br>
        <span style="color:var(--gray);font-size:.85em">${escHtml(e.telefono)} · intentos: ${escHtml(e.intentos)}</span><br>
        <button type="button" class="btn btn-blue btn--corregir" style="margin-top:4px;font-size:.82em;padding:6px 10px">✏️ Corregir número</button>
      </div>`
    ).join('');
  } catch(e) { cont.textContent = 'Error cargando envíos.'; }
}

function abrirCorregir(envio) {
  _envioSel = envio;
  document.getElementById('corregir-box').style.display = 'block';
  document.getElementById('corregir-tienda').textContent = envio.tienda || '';
  const inp = document.getElementById('corregir-input');
  inp.value = ''; inp.focus();
  document.getElementById('corregir-error').textContent = '';
  document.getElementById('corregir-btn').disabled = true;
}

function validarCorregir() {
  const v = document.getElementById('corregir-input').value;
  const dig = (v.match(/\d/g) || []).length;
  const ok = dig >= 10 && dig <= 13;
  document.getElementById('corregir-btn').disabled = !ok;
  document.getElementById('corregir-error').textContent = (v && !ok) ? 'Deben ser 10 a 13 dígitos.' : '';
  return ok;
}

async function guardarCorreccion() {
  if (!validarCorregir() || !_envioSel) return;
  const btn = document.getElementById('corregir-btn');
  btn.disabled = true;
  try {
    const r = await fetch('/api/catalogo/corregir-numero', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({
        envio_row: _envioSel._row,
        telefono: document.getElementById('corregir-input').value,
        contacto_row: _envioSel.fila_respuesta,
      })
    });
    const d = await r.json();
    if (d.ok) { abrirEnviosProblema(); }
    else { document.getElementById('corregir-error').textContent = d.error || 'No se pudo corregir.'; btn.disabled = false; }
  } catch(e) { document.getElementById('corregir-error').textContent = 'Error de conexión.'; btn.disabled = false; }
}

function cerrarModalCatalogo() { document.getElementById('modal-catalogo').style.display = 'none'; }

function cargarSiguiente() {
  O.skip = 0;  // Resetear skip — el contacto anterior ya fue marcado
  cargarContacto();
}

// El reintento cuelga de un listener, no de un `onclick` en el marcado: el
// paso de error se pinta con texto que viene del servidor y ahí es donde se
// cuelan las comillas.
document.getElementById('btn-reintentar-contacto')
  .addEventListener('click', cargarContacto);
document.getElementById('btn-reintentar-guardado')
  .addEventListener('click', reintentarGuardado);

// Iniciar
cargarContacto();
