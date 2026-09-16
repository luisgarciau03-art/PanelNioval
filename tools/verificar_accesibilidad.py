"""Auditoria de accesibilidad y responsive de las tres superficies (Plan 4, T4.10).

Uso:
    python tools/verificar_accesibilidad.py            # las tres superficies, 5 anchos
    python tools/verificar_accesibilidad.py --detalle  # lista cada hallazgo

Por que un auditor propio y no `axe`: esta maquina no tiene `axe-core` instalado
y el proyecto no descarga dependencias de red para verificar. Pero eso no es la
razon principal. La T4.9 dejo demostrado que **el fallo mas caro de esta tanda no
lo veia ningun guarda de patrones**: un color de token atenuado con `opacity:.55`
da 2.97:1 y pasa el guarda de CE3, porque el color declarado si es un token. Lo
unico que lo atrapa es medir el color EFECTIVO en el navegador, componiendo la
opacidad heredada y el fondo real. Eso es lo que hace esto.

Que comprueba, por superficie y por ancho (CE8, CE9, CE10):

  1. **Desborde horizontal** (CE10): `scrollWidth <= clientWidth`, y QUE elemento
     lo causa cuando falla.
  2. **Contraste** (CE9): recorre cada elemento con texto visible, compone la
     opacidad acumulada de sus ancestros y busca el primer fondo opaco -incluidos
     los degradados de las cabeceras, midiendo contra sus dos paradas-. Umbral
     4.5:1, o 3:1 si el texto es grande segun la definicion de WCAG.
  3. **Alcanzable con teclado** (CE8): todo lo que se comporta como control
     -`onclick`, `role` interactivo- tiene que poder recibir foco.
  4. **Foco visible**: se tabula de verdad y se comprueba que el elemento
     enfocado tiene indicador (contorno o sombra), no que exista una regla CSS.
  5. **Etiquetas**: cada campo con nombre accesible, y de donde sale.
  6. **Landmarks y encabezados**: `main`, un solo `h1`, sin saltos de nivel.
  7. **Imagenes**: `alt` presente y dimensiones explicitas (CLS).

La app arranca SIN credenciales de Google -comprobado en la direccion util- y
todos los datos son sinteticos. No llama a ninguna API de pago.
"""
import argparse
import json
import os
import sys
import threading
from collections import Counter
from pathlib import Path
from wsgiref.simple_server import make_server

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))

os.environ.setdefault("PANEL_AUTH_DESACTIVADA", "1")
os.environ.pop("GOOGLE_CREDENTIALS_JSON", None)
os.environ["GOOGLE_CREDENTIALS_FILE"] = str(
    Path(__file__).resolve().parent / "_credencial-inexistente-para-capturas.json"
)

import medir_cls  # noqa: E402

PUERTO = 5071
ANCHOS = (320, 375, 768, 1024, 1440)
SUPERFICIES = medir_cls.SUPERFICIES

# El contraste y las etiquetas no cambian con el ancho; el desborde si. Medir
# todo en los cinco anchos multiplicaria por cinco el ruido del informe sin
# anadir un solo hallazgo distinto.
ANCHO_AUDITORIA = 1440

AUDITOR = r"""
() => {
  const hallazgos = [];
  const anota = (regla, gravedad, criterio, detalle, nodo) => hallazgos.push({
    regla, gravedad, criterio, detalle,
    nodo: nodo ? (nodo.tagName.toLowerCase()
        + (nodo.id ? '#' + nodo.id : '')
        + (nodo.className && typeof nodo.className === 'string' && nodo.className.trim()
           ? '.' + nodo.className.trim().split(/\s+/).slice(0, 3).join('.') : '')) : '',
    texto: nodo ? (nodo.textContent || '').trim().slice(0, 40) : '',
  });

  const NATIVOS = 'a[href],button,input,select,textarea,summary,[contenteditable="true"]';

  // ── util de color ──────────────────────────────────────────────────────
  const aRgb = (c) => {
    const m = String(c).match(/rgba?\(([^)]+)\)/);
    if (!m) return null;
    const p = m[1].split(',').map(x => parseFloat(x));
    return {r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1};
  };
  const sobre = (frente, fondo) => ({          // composicion alfa
    r: frente.r * frente.a + fondo.r * (1 - frente.a),
    g: frente.g * frente.a + fondo.g * (1 - frente.a),
    b: frente.b * frente.a + fondo.b * (1 - frente.a),
    a: 1,
  });
  const lum = (c) => {
    const f = (v) => {
      v /= 255;
      return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
    };
    return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b);
  };
  const ratio = (a, b) => {
    const l1 = lum(a), l2 = lum(b);
    return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
  };

  // Fondos posibles detras de un elemento. Devuelve varios cuando hay
  // degradado: el texto tiene que pasar sobre TODAS sus paradas, no sobre la
  // media. Las cabeceras del panel son degradados azules, asi que sin esto la
  // mitad de la pantalla se quedaria sin medir.
  // OJO: solo se reconocen degradados (`linear/radial-gradient`). Si alguna
  // superficie pusiera texto sobre una imagen rasterizada (`url(...)`), esta
  // funcion cae al blanco por defecto y devolveria un "pasa" falso. Hoy no hay
  // ningun caso asi; si se anade uno, hay que medirlo a mano.
  const fondosDe = (el) => {
    const blanco = {r: 255, g: 255, b: 255, a: 1};
    let nodo = el;
    const acumulados = [];
    while (nodo && nodo.nodeType === 1) {
      const cs = getComputedStyle(nodo);
      const img = cs.backgroundImage;
      if (img && img !== 'none') {
        const paradas = [...img.matchAll(/rgba?\([^)]+\)/g)].map(m => aRgb(m[0])).filter(Boolean);
        if (paradas.length) {
          return paradas.map(p => acumulados.reduce((f, c) => sobre(c, f), p));
        }
      }
      const bg = aRgb(cs.backgroundColor);
      if (bg && bg.a === 1) return [acumulados.reduce((f, c) => sobre(c, f), bg)];
      if (bg && bg.a > 0) acumulados.unshift(bg);
      nodo = nodo.parentElement;
    }
    return [acumulados.reduce((f, c) => sobre(c, f), blanco)];
  };

  const opacidadAcumulada = (el) => {
    let o = 1, nodo = el;
    while (nodo && nodo.nodeType === 1) {
      const v = parseFloat(getComputedStyle(nodo).opacity);
      if (!isNaN(v)) o *= v;
      nodo = nodo.parentElement;
    }
    return o;
  };

  const visible = (el) => {
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') return false;
    if (el.hidden || el.closest('[hidden]')) return false;
    // `.solo-lectores` esta recortado a 1px: existe para el lector, no para el
    // ojo, asi que no tiene requisito de contraste.
    if (el.closest('.solo-lectores')) return false;
    const r = el.getBoundingClientRect();
    return r.width > 1 && r.height > 1;
  };

  // ── 1. Contraste de texto ──────────────────────────────────────────────
  const conTexto = [...document.querySelectorAll('body *')].filter(el => {
    if (!visible(el)) return false;
    return [...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim().length > 1);
  });
  for (const el of conTexto) {
    // WCAG 1.4.3 exime explicitamente a los componentes de interfaz inactivos.
    // Sin esta exencion, cada boton deshabilitado sale como CRITICO y entierra
    // los fallos de verdad.
    if (el.matches(':disabled') || el.closest('[aria-disabled="true"],:disabled')) continue;
    const cs = getComputedStyle(el);
    const color = aRgb(cs.color);
    if (!color) continue;
    const opacidad = opacidadAcumulada(el);
    const px = parseFloat(cs.fontSize);
    const peso = parseInt(cs.fontWeight, 10) || 400;
    // Definicion de WCAG para "texto grande": 24px, o 18.66px en negrita.
    const grande = px >= 24 || (px >= 18.66 && peso >= 700);
    const minimo = grande ? 3.0 : 4.5;
    for (const fondo of fondosDe(el)) {
      const frente = sobre({...color, a: color.a * opacidad}, fondo);
      const r = ratio(frente, fondo);
      if (r + 0.005 < minimo) {
        anota('contraste', r < minimo - 1 ? 'CRITICO' : 'ALTO', 'WCAG 1.4.3',
              `${r.toFixed(2)}:1 (min ${minimo}) · ${cs.color} sobre rgb(${
                Math.round(fondo.r)},${Math.round(fondo.g)},${Math.round(fondo.b)})`
              + (opacidad < 1 ? ` · opacidad acumulada ${opacidad.toFixed(2)}` : ''), el);
        break;
      }
    }
  }

  // ── 2. Alcanzable con teclado ──────────────────────────────────────────
  const ROLES_INTERACTIVOS = ['button', 'option', 'tab', 'link', 'checkbox', 'radio', 'menuitem'];
  // Un `tabindex="-1"` NO es un fallo cuando el elemento pertenece a un widget
  // compuesto que mueve el foco con flechas: es el patron de tabindex movil, y
  // marcarlo convertiria en "critico" justo lo que la T4.9 hizo bien. Lo que si
  // hay que exigir es que el conjunto tenga UNA entrada por tabulacion.
  const COMPUESTOS = '[role="listbox"],[role="tablist"],[role="menu"],[role="radiogroup"],[role="grid"],[role="tree"]';
  const gestionadoPorSuContenedor = (el) => {
    const caja = el.closest(COMPUESTOS);
    if (!caja) return false;
    if (caja.hasAttribute('aria-activedescendant')) return true;
    return !!caja.querySelector('[tabindex="0"]');
  };
  for (const el of document.querySelectorAll('[onclick],[role]')) {
    if (!visible(el)) continue;
    const rol = el.getAttribute('role');
    const interactivo = el.hasAttribute('onclick') || ROLES_INTERACTIVOS.includes(rol);
    if (!interactivo) continue;
    if (el.matches(NATIVOS)) continue;
    if (el.tabIndex >= 0) continue;
    if (gestionadoPorSuContenedor(el)) continue;
    // El fondo de un dialogo que cierra al pinchar es un atajo de raton que
    // duplica un boton que si existe; y un manejador que solo frena la
    // propagacion no es una accion. Ninguno de los dos es un control.
    if (rol === 'dialog' || rol === 'alertdialog') continue;
    const manejador = el.getAttribute('onclick') || '';
    if (/^\s*event\.stopPropagation\(\)\s*;?\s*$/.test(manejador)) continue;
    anota('teclado', 'CRITICO', 'WCAG 2.1.1',
          'se comporta como control pero no puede recibir foco', el);
  }
  // El otro lado del patron: un widget compuesto SIN ninguna entrada por
  // tabulacion es inalcanzable entero, y ahi si es critico.
  for (const caja of document.querySelectorAll(COMPUESTOS)) {
    if (!visible(caja)) continue;
    if (caja.hasAttribute('aria-activedescendant')) continue;
    if (caja.tabIndex >= 0 || caja.querySelector('[tabindex="0"]')) continue;
    anota('teclado', 'CRITICO', 'WCAG 2.1.1',
          'widget compuesto sin ninguna parada de tabulacion', caja);
  }

  // ── 3. Etiquetas de los campos ─────────────────────────────────────────
  for (const el of document.querySelectorAll('input,select,textarea')) {
    if (!visible(el)) continue;
    const tipo = (el.getAttribute('type') || '').toLowerCase();
    if (['hidden', 'submit', 'button', 'reset', 'image'].includes(tipo)) continue;
    const porFor = el.id && document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
    const nombre = el.getAttribute('aria-label')
      || (el.getAttribute('aria-labelledby') && document.getElementById(
            el.getAttribute('aria-labelledby').split(/\s+/)[0]))
      || porFor
      || el.closest('label');
    if (!nombre) {
      anota('etiqueta', el.placeholder ? 'ALTO' : 'CRITICO', 'WCAG 4.1.2 / 3.3.2',
            el.placeholder ? 'solo tiene placeholder, que no es una etiqueta'
                           : 'campo sin nombre accesible', el);
    }
  }

  // ── 4. Landmarks y encabezados ─────────────────────────────────────────
  if (!document.querySelector('main')) {
    anota('landmark', 'ALTO', 'WCAG 1.3.1', 'la pagina no declara <main>', document.body);
  }
  const h1 = document.querySelectorAll('h1');
  if (h1.length !== 1) {
    anota('encabezado', 'MEDIO', 'WCAG 1.3.1',
          `hay ${h1.length} elementos <h1>`, document.body);
  }
  let ultimo = 0;
  for (const h of document.querySelectorAll('h1,h2,h3,h4,h5,h6')) {
    if (!visible(h)) continue;
    const nivel = parseInt(h.tagName[1], 10);
    if (ultimo && nivel > ultimo + 1) {
      anota('encabezado', 'MEDIO', 'WCAG 1.3.1',
            `salta de h${ultimo} a h${nivel}`, h);
    }
    ultimo = nivel;
  }

  // ── 5. Destino de los enlaces de salto ─────────────────────────────────
  // Sin `tabindex="-1"` el navegador desplaza pero NO emite evento de foco: para
  // un lector el salto es un scroll silencioso, o sea nada, y es justo el
  // usuario para el que existe el mecanismo.
  for (const enlace of document.querySelectorAll('a[href^="#"]')) {
    const id = enlace.getAttribute('href').slice(1);
    if (!id) continue;
    const destino = document.getElementById(id);
    if (!destino) {
      anota('salto', 'ALTO', 'WCAG 2.4.1', 'el enlace de salto apunta a un id que no existe', enlace);
      continue;
    }
    const enfocable = destino.matches(NATIVOS) || destino.tabIndex >= 0
      || destino.hasAttribute('tabindex');
    if (!enfocable) {
      anota('salto', 'ALTO', 'WCAG 2.4.1',
            'el destino no puede recibir foco: falta tabindex="-1" en #' + id, enlace);
    }
  }

  // ── 6. Dialogos ────────────────────────────────────────────────────────
  // Un modal que tapa la pagina y no se anuncia como dialogo no existe para un
  // lector. Y uno que atrapa el foco sin salida por teclado es PEOR que el
  // original (SC 2.1.2), asi que las dos cosas se comprueban juntas.
  const SOSPECHOSOS = '[id^="modal"],[id$="-modal"],[role="dialog"],[role="alertdialog"]';
  for (const caja of document.querySelectorAll(SOSPECHOSOS)) {
    const rol = caja.getAttribute('role');
    const cs = getComputedStyle(caja);
    const parecePantalla = cs.position === 'fixed';
    if (!parecePantalla && !rol) continue;
    if (rol !== 'dialog' && rol !== 'alertdialog') {
      anota('dialogo', 'ALTO', 'WCAG 4.1.2',
            'tapa la pagina pero no se anuncia como dialogo', caja);
      continue;
    }
    const nombre = caja.getAttribute('aria-label')
      || (caja.getAttribute('aria-labelledby')
          && document.getElementById(caja.getAttribute('aria-labelledby')));
    if (!nombre) {
      anota('dialogo', 'ALTO', 'WCAG 4.1.2', 'dialogo sin nombre accesible', caja);
    }
    if (caja.getAttribute('aria-modal') === 'true' && !caja.querySelector('[data-cerrar]')) {
      anota('dialogo', 'CRITICO', 'WCAG 2.1.2',
            'dialogo modal sin salida marcada: el foco atrapado no tiene por donde salir', caja);
    }
  }

  // ── 7. Contenido no textual con nombre ─────────────────────────────────
  for (const lienzo of document.querySelectorAll('canvas')) {
    if (!visible(lienzo)) continue;
    const nombre = lienzo.getAttribute('aria-label') || lienzo.textContent.trim();
    if (!nombre) {
      anota('grafica', 'ALTO', 'WCAG 1.1.1',
            'un <canvas> sin nombre se anuncia como "canvas" y nada mas', lienzo);
    }
  }

  // ── 8. Tamano del objetivo ─────────────────────────────────────────────
  // SC 2.5.8 pide 24x24 px CSS, salvo excepciones (elementos en linea dentro de
  // un texto, o con separacion suficiente). Se aplica el minimo estricto y se
  // deja fuera lo que va dentro de un parrafo.
  for (const control of document.querySelectorAll('button,a[href],[role="button"],[role="option"],[role="radio"],[role="tab"]')) {
    if (!visible(control)) continue;
    if (control.closest('p')) continue;
    const r = control.getBoundingClientRect();
    if (r.width < 24 || r.height < 24) {
      anota('objetivo', 'MEDIO', 'WCAG 2.5.8',
            `${Math.round(r.width)}x${Math.round(r.height)} px (minimo 24x24)`, control);
    }
  }

  // ── 9. Imagenes ────────────────────────────────────────────────────────
  for (const img of document.querySelectorAll('img')) {
    // `alt` se exige SIEMPRE: da igual que la imagen este en un modal cerrado,
    // porque cuando se abra hara falta.
    if (!img.hasAttribute('alt')) {
      anota('imagen', 'ALTO', 'WCAG 1.1.1', 'sin atributo alt', img);
    }
    // Las dimensiones, en cambio, son un requisito de CLS, y CLS mide lo que se
    // pinta. Una imagen dentro de un modal cerrado no desplaza nada al cargar,
    // y exigirle un alto fijo a una imagen de src dinamico la deformaria.
    if (!visible(img)) continue;
    // Sin `src` no hay descarga ni reserva que discutir: es un hueco que el JS
    // rellena al abrir el visor.
    if (!img.getAttribute('src')) continue;
    if (!img.hasAttribute('width') || !img.hasAttribute('height')) {
      anota('imagen', 'MEDIO', 'CLS',
            'sin dimensiones explicitas: reserva 0 y la pagina salta al cargar', img);
    }
  }
  return hallazgos;
}
"""

DESBORDE = r"""
() => {
  const doc = document.documentElement;
  const culpables = [];
  if (doc.scrollWidth > doc.clientWidth) {
    for (const el of document.querySelectorAll('body *')) {
      const cs = getComputedStyle(el);
      if (cs.display === 'none' || cs.visibility === 'hidden') continue;
      const r = el.getBoundingClientRect();
      if (r.width <= 0) continue;
      if (r.right > doc.clientWidth + 1) {
        // Solo el que desborda POR SI MISMO: si su padre ya desbordaba, el hijo
        // es consecuencia y no causa, y listarlos todos entierra al culpable.
        const p = el.parentElement;
        const pr = p ? p.getBoundingClientRect() : null;
        if (pr && pr.right > doc.clientWidth + 1) continue;
        culpables.push({
          sel: el.tagName.toLowerCase() + (el.id ? '#' + el.id : '')
               + (el.className && typeof el.className === 'string' && el.className.trim()
                  ? '.' + el.className.trim().split(/\s+/).slice(0, 2).join('.') : ''),
          derecha: Math.round(r.right), ancho: Math.round(r.width),
        });
      }
    }
  }
  return {scroll: doc.scrollWidth, cliente: doc.clientWidth, culpables: culpables.slice(0, 8)};
}
"""


def ev(pagina, guion, argumento=None):
    """Evalua en la pagina y devuelve None si algo falla, en vez de reventar."""
    try:
        return (pagina.evaluate(guion, argumento) if argumento is not None
                else pagina.evaluate(guion))
    except Exception as e:                      # noqa: BLE001 - se reporta, no se traga
        print("      (un estado no respondio: %s)" % str(e).splitlines()[0][:80])
        return None


def _rutas_sinteticas(pagina):
    """Sirve datos inventados a /api/*. Ninguna fila real de la hoja."""
    def responder(ruta):
        cuerpo = medir_cls._cuerpo(ruta.request.url)
        ruta.fulfill(status=200, content_type="application/json",
                     body=json.dumps(cuerpo, ensure_ascii=False))
    pagina.route("**/api/**", responder)


def _auditar_todos_los_estados(pagina):
    """Audita el estado inicial Y el resto de estados de la superficie.

    Es la correccion del limite estructural que encontro `a11y-architect`: la
    version anterior cargaba la URL una vez y auditaba ese DOM. El tablero tiene
    14 secciones intercambiadas con `display:none`, el formulario 15 pasos y tres
    modales, y **cualquier defecto confinado a un estado que no sea el inicial
    era invisible por diseno**. Asi se colaron dos CRITICAL de teclado: las
    pestanas de Seguimiento y el selector de color, los dos `div` con `onclick`
    en secciones que nunca se activaban durante la auditoria.

    Los hallazgos se deduplican por regla + nodo + detalle: la misma cabecera
    aparece en las catorce secciones y listarla catorce veces entierra el resto.
    """
    vistos = set()
    hallazgos = []

    def acumular(lote):
        for h in lote or []:
            clave = (h["regla"], h["nodo"], h["detalle"])
            if clave in vistos:
                continue
            vistos.add(clave)
            hallazgos.append(h)

    acumular(ev(pagina, AUDITOR))

    # 1. Cada seccion del tablero, activada como la activa el operador.
    secciones = ev(pagina, """() => [...document.querySelectorAll('[data-seccion]')]
        .map(b => b.dataset.seccion)""") or []
    for seccion in secciones:
        try:
            pagina.click('[data-seccion="%s"]' % seccion, timeout=4000)
            pagina.wait_for_timeout(700)
        except Exception:                       # noqa: BLE001
            continue
        acumular(ev(pagina, AUDITOR))

    # 2. Cada dialogo, revelado. No se pulsa el boton que lo abre -son siete
    #    funciones distintas repartidas en dos archivos- sino que se muestra y
    #    se vuelve a ocultar: basta para auditar su semantica y su contenido.
    dialogos = ev(pagina, """() => [...document.querySelectorAll('[role="dialog"],[id^="modal"]')]
        .map(d => d.id).filter(Boolean)""") or []
    for ident in dialogos:
        ev(pagina, """(id) => {
            const d = document.getElementById(id);
            if (!d) return;
            d.dataset.displayPrevio = d.style.display || '';
            d.style.display = 'flex';
        }""", ident)
        pagina.wait_for_timeout(250)
        acumular(ev(pagina, AUDITOR))
        ev(pagina, """(id) => {
            const d = document.getElementById(id);
            if (!d) return;
            d.style.display = d.dataset.displayPrevio || 'none';
        }""", ident)
    return hallazgos


def _foco_visible(pagina, saltos=60):
    """Tabula de verdad y comprueba que se ve donde esta el foco.

    Comprobar que existe una regla `:focus-visible` en el CSS no prueba nada: la
    regla puede no aplicar al elemento, o el elemento puede estar tapado. Aqui se
    pulsa Tab y se mira el estilo computado del que quedo enfocado.
    """
    sin_indicador = []
    vistos = set()
    for _ in range(saltos):
        pagina.keyboard.press("Tab")
        dato = pagina.evaluate(r"""() => {
            const el = document.activeElement;
            if (!el || el === document.body) return null;
            const cs = getComputedStyle(el);
            const contorno = parseFloat(cs.outlineWidth) || 0;
            const sombra = cs.boxShadow && cs.boxShadow !== 'none';
            // La clave incluye clase y texto: sin eso, los treinta botones sin
            // id del tablero colapsaban en una sola entrada y el recuento de
            // paradas daba 2 donde hay decenas.
            return {
                sel: el.tagName.toLowerCase() + (el.id ? '#' + el.id : '')
                     + (el.className && typeof el.className === 'string' && el.className.trim()
                        ? '.' + el.className.trim().split(/\s+/)[0] : '')
                     + '|' + (el.textContent || '').trim().slice(0, 18),
                indicador: (contorno > 0 && cs.outlineStyle !== 'none') || sombra,
            };
        }""")
        if not dato:
            continue
        if dato["sel"] in vistos:
            continue
        vistos.add(dato["sel"])
        if not dato["indicador"]:
            sin_indicador.append(dato["sel"])
    return sin_indicador, len(vistos)


def main():
    # La consola de Windows es cp1252 y el informe lleva caracteres que no
    # existen ahi. Sin esto, imprimir el detalle revienta a mitad y se lleva por
    # delante la escritura del JSON, que va despues: el informe completo se
    # perdia y quedaba el del run anterior, que parece valido y no lo es.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                       # noqa: BLE001
        pass

    ap = argparse.ArgumentParser()
    ap.add_argument("--detalle", action="store_true", help="lista cada hallazgo")
    ap.add_argument("--json", help="vuelca los hallazgos a un archivo")
    args = ap.parse_args()

    import app as panel
    medir_cls.verificar_sin_credenciales()
    servidor = make_server("127.0.0.1", PUERTO, panel.app)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()

    informe = {}
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        navegador = p.chromium.launch()
        try:
            for nombre, ruta in SUPERFICIES:
                url = "http://127.0.0.1:%d%s" % (PUERTO, ruta)
                datos = {"hallazgos": [], "desborde": {}, "foco": {}}

                # Auditoria de contenido: en un solo ancho, que es donde vive.
                pagina = navegador.new_page(viewport={"width": ANCHO_AUDITORIA, "height": 1000})
                _rutas_sinteticas(pagina)
                pagina.goto(url, wait_until="domcontentloaded")
                pagina.wait_for_timeout(1800)
                datos["hallazgos"] = _auditar_todos_los_estados(pagina)
                sin_foco, tabulables = _foco_visible(pagina)
                datos["foco"] = {"sin_indicador": sin_foco, "tabulables": tabulables}
                pagina.close()

                # Desborde: en los cinco anchos de CE10.
                for ancho in ANCHOS:
                    pagina = navegador.new_page(viewport={"width": ancho, "height": 900})
                    _rutas_sinteticas(pagina)
                    pagina.goto(url, wait_until="domcontentloaded")
                    pagina.wait_for_timeout(1500)
                    datos["desborde"][ancho] = pagina.evaluate(DESBORDE)
                    pagina.close()
                informe[nombre] = datos
        finally:
            navegador.close()
            servidor.shutdown()

    # ── Informe ────────────────────────────────────────────────────────────
    total = 0
    for nombre, datos in informe.items():
        print("\n=== %s ===" % nombre.upper())
        conteo = Counter((h["regla"], h["gravedad"]) for h in datos["hallazgos"])
        if conteo:
            for (regla, gravedad), n in sorted(conteo.items(), key=lambda x: -x[1]):
                print("  %-10s %-8s %3d" % (regla, gravedad, n))
        else:
            print("  sin hallazgos de contenido")
        total += len(datos["hallazgos"])

        print("  desborde horizontal:")
        for ancho, d in datos["desborde"].items():
            exceso = d["scroll"] - d["cliente"]
            estado = "OK" if exceso <= 0 else "DESBORDA %d px" % exceso
            print("    %5d px -> %s" % (ancho, estado))
            if exceso > 0:
                for c in d["culpables"]:
                    print("             %s (derecha %d, ancho %d)"
                          % (c["sel"], c["derecha"], c["ancho"]))
                total += 1

        foco = datos["foco"]
        print("  foco visible: %d paradas de tabulacion, %d sin indicador"
              % (foco["tabulables"], len(foco["sin_indicador"])))
        if foco["sin_indicador"]:
            print("             %s" % ", ".join(foco["sin_indicador"][:6]))
            total += len(foco["sin_indicador"])

        if args.detalle:
            for h in datos["hallazgos"]:
                print("    [%s] %s %s -> %s | %s" % (h["gravedad"], h["criterio"],
                                                     h["nodo"], h["detalle"], h["texto"]))

    if args.json:
        Path(args.json).write_text(json.dumps(informe, ensure_ascii=False, indent=1),
                                   encoding="utf-8")
        print("\nInforme completo en %s" % args.json)

    print("\nTOTAL: %d hallazgos" % total)
    return 1 if total else 0


if __name__ == "__main__":
    raise SystemExit(main())
