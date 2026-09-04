/* ==========================================================================
   NIOVAL — Estados de carga  ·  Plan 4, T4.5
   ==========================================================================
   Un solo modulo para las tres superficies. Expone `window.Estados` con los
   cuatro estados que antes no existian por separado:

     Estados.esqueleto(el, forma, opciones)  la forma del contenido que viene
     Estados.vacio(el, {...})                no hay filas, y eso esta bien
     Estados.error(el, {..., reintentar})    la lectura fallo, con salida
     Estados.parcial(el, {...})              lo demas cargo; esto no

   Tres reglas que el modulo impone y no deja negociar:

   1. **El esqueleto no parpadea.** Por debajo de UMBRAL_ESQUELETO no se pinta
      nada: una respuesta de 80 ms con esqueleto se ve peor que sin el. El
      temporizador se cancela si los datos llegan antes.

   2. **Un error siempre trae salida.** `Estados.error` exige `reintentar`; sin
      el, el operador solo puede recargar la pagina entera.

   3. **Nada celebra sin verificar.** Aqui no hay confeti, ni marcas de
      verificacion, ni verde de exito. Un estado que solo puede afirmar "no
      recibi datos" no se viste de exito (ADR de direccion visual, voto del
      Critico).

   Sin dependencias. Se carga antes que el script de cada superficie.
   ========================================================================== */
(function (global) {
  'use strict';

  // Por debajo de esto, el esqueleto aparece y desaparece antes de que el ojo
  // lo lea: se ve como un parpadeo, no como una espera.
  var UMBRAL_ESQUELETO = 200;

  // Filas que pinta un esqueleto de tabla. Fijo a proposito: es lo que reserva
  // la altura, y si cada seccion elige la suya el espacio reservado cambia.
  var FILAS_ESQUELETO = 8;

  // Tarjetas de indicador por defecto (el tablero pinta 4 y 5 segun seccion).
  var TARJETAS_ESQUELETO = 4;

  function escapar(s) {
    return String(s === null || s === undefined ? '' : s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function elemento(destino) {
    return typeof destino === 'string' ? document.getElementById(destino) : destino;
  }

  function repetir(n, html) {
    var salida = '';
    for (var i = 0; i < n; i++) salida += html;
    return salida;
  }

  /* ── Formas de esqueleto ────────────────────────────────────────────────
     Cada una replica la caja del contenido real. El `aria-hidden` no es
     opcional: un esqueleto es decoracion y anunciarlo llena el lector de
     ruido sin decir nada util. Lo que si se anuncia es el texto de espera,
     una sola vez, en la region viva. */
  var FORMAS = {
    tabla: function (opciones) {
      var filas = (opciones && opciones.filas) || FILAS_ESQUELETO;
      return '<div class="esqueleto-tabla" aria-hidden="true">' +
        '<div class="esqueleto-tabla__cabecera esqueleto"></div>' +
        repetir(filas,
          '<div class="esqueleto-tabla__fila esqueleto"></div>') +
        '</div>';
    },
    tarjetas: function (opciones) {
      var n = (opciones && opciones.tarjetas) || TARJETAS_ESQUELETO;
      return '<div class="esqueleto-rejilla" aria-hidden="true">' +
        repetir(n,
          '<div class="esqueleto-tarjeta">' +
            '<div class="esqueleto esqueleto--texto esqueleto--corto"></div>' +
            '<div class="esqueleto esqueleto--num"></div>' +
          '</div>') +
        '</div>';
    },
    chips: function (opciones) {
      var n = (opciones && opciones.chips) || 12;
      return '<div class="esqueleto-chips" aria-hidden="true">' +
        repetir(n, '<div class="esqueleto esqueleto-chip"></div>') +
        '</div>';
    },
    ficha: function () {
      // La ficha de contacto del formulario: rejilla de dos columnas mas los
      // botones de resultado. Reserva su alto para que el contacto real no
      // desplace la botonera bajo el dedo del operador.
      return '<div class="esqueleto-ficha" aria-hidden="true">' +
        '<div class="esqueleto esqueleto--texto esqueleto--corto"></div>' +
        '<div class="esqueleto-rejilla">' +
          repetir(4,
            '<div class="esqueleto-tarjeta">' +
              '<div class="esqueleto esqueleto--texto esqueleto--corto"></div>' +
              '<div class="esqueleto esqueleto--texto esqueleto--medio"></div>' +
            '</div>') +
        '</div>' +
        '</div>';
    }
  };

  /* ── Estado de carga ────────────────────────────────────────────────────
     Devuelve una funcion `terminar()`. Si se llama antes del umbral, el
     esqueleto no llega a pintarse; si se llama despues, lo retira. Sin ese
     `clearTimeout` el esqueleto aparece DESPUES de los datos y los borra. */
  function esqueleto(destino, forma, opciones) {
    var el = elemento(destino);
    if (!el) return function () {};

    var construir = FORMAS[forma] || FORMAS.tabla;
    var nodo = null;
    var temporizador = setTimeout(function () {
      nodo = document.createElement('div');
      nodo.innerHTML =
        '<div class="solo-lectores" role="status">Cargando…</div>' +
        construir(opciones);
      el.innerHTML = '';
      el.appendChild(nodo);
    }, UMBRAL_ESQUELETO);

    return function terminar() {
      clearTimeout(temporizador);
      // Se retira EL NODO que este esqueleto insertó, y solo si sigue puesto.
      // Vaciar el contenedor entero borraba los datos recién pintados: quien
      // llama suele cerrar el esqueleto en un `finally`, que corre DESPUÉS de
      // que la sección haya escrito su contenido real. Con el botón
      // "Actualizar" del tablero y una respuesta de Google de más de 200 ms,
      // eso dejaba la pantalla en blanco.
      var estaba = !!(nodo && nodo.parentNode === el);
      if (estaba) el.removeChild(nodo);
      nodo = null;
      return estaba;
    };
  }

  /* ── Estados finales ────────────────────────────────────────────────────
     `role="status"` porque el cambio ocurre despues de cargar la pagina: sin
     region viva, quien usa lector se queda esperando un contenido que ya
     decidio no llegar. */
  function bloque(clase, titulo, detalle, accion) {
    // `alert` solo para el error. Un fallo de lectura BLOQUEA la tarea —no hay
    // tabla que leer ni contacto al que llamar— y `status` (aria-live polite)
    // se anuncia cuando el lector está ocioso, así que puede perderse. Vacío y
    // parcial no bloquean nada: ahí interrumpir sería ruido.
    var rol = clase === 'estado--error' ? 'alert' : 'status';
    return '<div class="estado ' + clase + '" role="' + rol + '">' +
      '<div class="estado__titulo">' + escapar(titulo) + '</div>' +
      (detalle ? '<div class="estado__detalle">' + escapar(detalle) + '</div>' : '') +
      (accion || '') +
      '</div>';
  }

  function vacio(destino, opciones) {
    var el = elemento(destino);
    if (!el) return;
    opciones = opciones || {};
    el.innerHTML = bloque(
      'estado--vacio',
      opciones.titulo || 'No hay nada que mostrar',
      opciones.detalle || ''
    );
  }

  function error(destino, opciones) {
    var el = elemento(destino);
    if (!el) return;
    opciones = opciones || {};
    var idBoton = 'reintentar-' + Math.random().toString(36).slice(2, 9);
    var hayReintento = typeof opciones.reintentar === 'function';
    var accion = hayReintento
      ? '<div class="estado__accion">' +
          '<button type="button" class="btn btn--secundario" id="' + idBoton + '">' +
          'Reintentar</button></div>'
      : '';

    el.innerHTML = bloque(
      'estado--error',
      opciones.titulo || 'No se pudieron cargar los datos',
      opciones.detalle || '',
      accion
    );

    if (hayReintento) {
      // Listener, no `onclick` inline: el atributo obliga a interpolar el
      // nombre de una funcion global en el HTML, y ahi es donde entran las
      // comillas de un mensaje de error sin escapar.
      var boton = document.getElementById(idBoton);
      if (boton) boton.addEventListener('click', opciones.reintentar);
    }
  }

  function parcial(destino, opciones) {
    var el = elemento(destino);
    if (!el) return;
    opciones = opciones || {};
    el.innerHTML = bloque(
      'estado--parcial',
      opciones.titulo || 'Faltan datos de esta sección',
      opciones.detalle || ''
    );
  }

  /* ── Aviso al margen ────────────────────────────────────────────────────
     El estado parcial de verdad: el tablero cargo, pero una pieza fallo. No
     puede tapar lo que si llego, asi que se inserta al principio del bloque
     sin borrar nada. */
  function avisoParcial(destino, opciones) {
    var el = elemento(destino);
    if (!el) return;
    opciones = opciones || {};
    var aviso = document.createElement('div');
    aviso.className = 'estado estado--parcial';
    aviso.setAttribute('role', 'status');
    aviso.innerHTML =
      '<div class="estado__titulo">' + escapar(opciones.titulo || 'Datos incompletos') + '</div>' +
      (opciones.detalle ? '<div class="estado__detalle">' + escapar(opciones.detalle) + '</div>' : '');
    el.insertBefore(aviso, el.firstChild);
  }

  /* ── Avisos de la primera carga ─────────────────────────────────────────
     Los esqueletos de la carga inicial vienen en la plantilla, no de aquí: es
     lo único que evita el salto de layout del primer render. Pero un
     `role="status"` que YA estaba en el HTML cuando el lector construyó el
     árbol no se anuncia — los lectores anuncian MUTACIONES de una región viva,
     no contenido preexistente. Por eso la plantilla deja el nodo vacío con
     `data-aviso-carga` y el texto se escribe aquí, después del primer render:
     así sí es una mutación. */
  function activarAvisos() {
    var nodos = document.querySelectorAll('[data-aviso-carga]');
    for (var i = 0; i < nodos.length; i++) {
      nodos[i].textContent = nodos[i].getAttribute('data-aviso-carga') || 'Cargando…';
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', activarAvisos);
  } else {
    activarAvisos();
  }

  global.Estados = {
    UMBRAL_ESQUELETO: UMBRAL_ESQUELETO,
    FILAS_ESQUELETO: FILAS_ESQUELETO,
    esqueleto: esqueleto,
    vacio: vacio,
    error: error,
    parcial: parcial,
    avisoParcial: avisoParcial,
    escapar: escapar,
    activarAvisos: activarAvisos
  };
})(window);
