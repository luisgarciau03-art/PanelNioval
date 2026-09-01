const _ventanasAbiertas = [];
function abrirVentana(url) {
  const w = window.open(url, '_blank', 'width=1000,height=700,left=100,top=80');
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

const PASOS = ['loading','contacto','p0','p1','p2','p3','p4','p5','p6','p7','guardando','siguiente','fin','error'];
const TOTAL_PREGUNTAS = 7;

function showStep(name) {
  PASOS.forEach(p => {
    const el = document.getElementById('step-' + p);
    if (el) el.classList.toggle('active', p === name);
  });
}

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
    `<div class="info-item ${f.full?'full':''}"><div class="lbl">${f.l}</div><div class="val">${f.v}</div></div>`
  ).join('');

  const links = [];
  if (maps && maps.startsWith('http')) links.push(`<button class="link-btn" onclick="abrirVentana('${maps.replace(/'/g,"\\'")}')">🗺️ Google Maps</button>`);
  if (link && link.startsWith('http')) links.push(`<button class="link-btn" onclick="abrirVentana('${link.replace(/'/g,"\\'")}')">🌐 Sitio Web</button>`);
  if (tel) links.push(`<a class="link-btn" href="tel:${tel}">📞 Llamar</a>`);
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
  document.getElementById('sel-p1').innerHTML = opciones.map(op =>
    `<button class="btn btn-blue" style="opacity:.7;font-size:.82em" onclick="toggleP1(this,'${op}')">${op}</button>`
  ).join('');
}

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
async function guardar() {
  if (_guardando) return;  // guard de reentrancia: evita filas duplicadas por doble envío
  _guardando = true;
  showStep('guardando');
  const tienda = O.contacto ? (O.contacto.TIENDA || O.contacto.Tienda || O.contacto.Nombre || '') : '';
  const payload = {
    row: O.contacto ? O.contacto._row : null,
    col_respuesta: O.contacto ? (O.contacto._col_respuesta || 6) : 6,
    tienda, resultado: O.resultado,
    r0: O.r0, r1: O.r1, r2: O.r2, r3: O.r3,
    r4: O.r4, r5: O.r5, r6: O.r6, r7: O.r7,
  };
  try {
    const r = await fetch('/api/formulario/guardar', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify(payload)
    });
    const d = await r.json();
    if (!d.ok) {
      _guardando = false;
      showStep('contacto');
      alert('⚠️ Error al guardar: ' + (d.error || 'No se pudo guardar en la hoja. Intenta de nuevo.'));
      return;
    }
    O.procesados++;
    document.getElementById('stat-procesados').textContent = O.procesados;
    document.getElementById('resumen-guardado').textContent =
      `${tienda} → ${O.resultado}${O.r0 && O.r0 !== 'Respondio' ? ' ('+O.r0+')' : ''}`;
    document.getElementById('catalogo-nota').textContent = '';
    showStep('siguiente');
    // Plan 3: si la conclusión dispara catálogo (Pedido / Revisará el Catálogo), encolar el envío.
    encolarCatalogo(tienda);
    _guardando = false;
  } catch(e) {
    _guardando = false;
    showStep('contacto');
    alert('⚠️ Error de conexión al guardar. Verifica tu internet e intenta de nuevo.');
  }
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
    if (!envios.length) { cont.innerHTML = '<p style="color:var(--gray)">Sin envíos con problema. 🎉</p>'; return; }
    cont.innerHTML = envios.map(e =>
      `<div style="border:1px solid var(--borde);border-radius:8px;padding:8px;margin-bottom:6px">
        <b>${escHtml(e.tienda)}</b> — <span style="color:var(--red)">${escHtml(e.estado)}</span><br>
        <span style="color:var(--gray);font-size:.85em">${escHtml(e.telefono)} · intentos: ${escHtml(e.intentos)}</span><br>
        <button class="btn btn-blue" style="margin-top:4px;font-size:.82em;padding:6px 10px"
          onclick='abrirCorregir(${JSON.stringify(e).replace(/'/g,"&#39;")})'>✏️ Corregir número</button>
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

// Iniciar
cargarContacto();
