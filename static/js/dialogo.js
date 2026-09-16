/* ============================================================================
   NIOVAL - Dialogos  ·  Plan 4, T4.10
   ============================================================================
   Los siete modales del panel -cuatro en el tablero, tres en el formulario- se
   abrian poniendo `style.display`. Visualmente tapaban la pagina; para un lector
   de pantalla no eran nada: sin `role="dialog"`, sin nombre, sin foco dentro y
   sin trampa, asi que el Tab se escapaba al contenido de fondo, que seguia
   siendo interactivo. Lo encontraron los dos gates de accesibilidad de la T4.10,
   cada uno por su lado.

   Este modulo NO cambia como se abren. Observa el atributo `style` de cada
   dialogo declarado en el marcado (`role="dialog"`) y reacciona cuando pasa a
   visible o a oculto. Esa fue la decision de diseno: envolver siete funciones de
   apertura repartidas en dos archivos habria tocado mucho mas codigo y roto mas
   cosas que observar el efecto que ya producen.

   Lo que hace al abrirse:
     - recuerda quien tenia el foco,
     - lo mueve al primer elemento enfocable de dentro,
     - retiene el Tab dentro del dialogo mientras este abierto,
     - cierra con Escape usando el propio boton de cerrar del dialogo, para que
       se ejecute la MISMA logica que un clic (que a veces guarda o limpia),
     - y devuelve el foco a donde estaba al cerrarse.

   Sin dependencias. Se carga antes del script de cada superficie.
   ========================================================================== */
(function (global) {
  'use strict';

  var ENFOCABLES = 'a[href],button:not([disabled]),input:not([disabled]),' +
    'select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])';

  var focoPrevio = null;
  var abierto = null;

  function visible(el) {
    // `offsetParent` es null tambien para `position:fixed`, que es justo lo que
    // son estos dialogos: hay que mirar el estilo calculado.
    var cs = getComputedStyle(el);
    return cs.display !== 'none' && cs.visibility !== 'hidden';
  }

  function enfocables(dialogo) {
    var todos = dialogo.querySelectorAll(ENFOCABLES);
    var salida = [];
    for (var i = 0; i < todos.length; i++) {
      if (visible(todos[i])) salida.push(todos[i]);
    }
    return salida;
  }

  function alAbrir(dialogo) {
    if (abierto === dialogo) return;
    abierto = dialogo;
    focoPrevio = document.activeElement;
    var lista = enfocables(dialogo);
    // Si el dialogo no tiene NADA enfocable dentro, se enfoca el propio
    // contenedor: dejar el foco fuera seria peor que cualquier alternativa.
    if (lista.length) {
      lista[0].focus();
    } else {
      if (!dialogo.hasAttribute('tabindex')) dialogo.setAttribute('tabindex', '-1');
      dialogo.focus();
    }
  }

  function alCerrar() {
    abierto = null;
    if (focoPrevio && document.contains(focoPrevio) && visible(focoPrevio)) {
      focoPrevio.focus();
    }
    focoPrevio = null;
  }

  function atrapar(ev) {
    if (!abierto || ev.key !== 'Tab') return;
    var lista = enfocables(abierto);
    if (!lista.length) { ev.preventDefault(); return; }
    var primero = lista[0];
    var ultimo = lista[lista.length - 1];
    // Si el foco se escapo fuera del dialogo -por un clic previo, por ejemplo-,
    // se devuelve dentro en vez de dejarlo vagar por el fondo.
    if (!abierto.contains(document.activeElement)) {
      ev.preventDefault();
      primero.focus();
      return;
    }
    if (ev.shiftKey && document.activeElement === primero) {
      ev.preventDefault();
      ultimo.focus();
    } else if (!ev.shiftKey && document.activeElement === ultimo) {
      ev.preventDefault();
      primero.focus();
    }
  }

  function escapar(ev) {
    if (!abierto || ev.key !== 'Escape') return;
    // Se pulsa el boton de cerrar del propio dialogo en vez de ocultarlo a
    // mano: esas funciones limpian estado -el color elegido, el archivo
    // subido- y saltarselas dejaria el dialogo cerrado y el estado a medias.
    var cerrar = abierto.querySelector('[data-cerrar]');
    if (cerrar) {
      ev.preventDefault();
      cerrar.click();
    }
  }

  function vigilar(dialogo) {
    var observador = new MutationObserver(function () {
      if (visible(dialogo)) alAbrir(dialogo);
      else if (abierto === dialogo) alCerrar();
    });
    observador.observe(dialogo, {attributes: true, attributeFilter: ['style', 'class', 'hidden']});
  }

  function iniciar() {
    var dialogos = document.querySelectorAll('[role="dialog"]');
    for (var i = 0; i < dialogos.length; i++) {
      vigilar(dialogos[i]);
      if (visible(dialogos[i])) alAbrir(dialogos[i]);
    }
    document.addEventListener('keydown', atrapar, true);
    document.addEventListener('keydown', escapar, true);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', iniciar);
  } else {
    iniciar();
  }

  global.Dialogo = {
    get abierto() { return abierto; },
    enfocables: enfocables,
    iniciar: iniciar,
  };
})(window);
