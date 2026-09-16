"""Verificacion EN NAVEGADOR del formulario de llamadas (Plan 4, T4.8).

Uso:
    python tools/verificar_formulario.py

El gate de la T4.8 es explicito: *"Captura completa de una llamada solo con
teclado, cronometrada contra el flujo actual. Si tarda mas, se ajusta."* Y el
plan avisa de por que: es la superficie de uso mas intensivo del panel, se usa
llamada tras llamada durante horas, y **un rediseno que se vea mejor y se
capture mas lento es un retroceso**.

Asi que esto no mide estetica: mide **pulsaciones**. Una captura completa son
siete preguntas; cada tecla de mas se multiplica por cada llamada del dia.

Que comprueba:

  1. **Se puede capturar SOLO con teclado**, sin un clic. Antes no: al ocultar
     el paso anterior con `display:none` el foco caia a `<body>`, asi que habia
     que tabular desde el principio del documento en cada una de las siete
     preguntas.
  2. **Cuenta las pulsaciones** de la captura completa y las compara con las
     que haria falta con el flujo anterior (tabular hasta cada opcion).
  3. **El contenido de la hoja no ejecuta.** Un `<img onerror>` en el nombre de
     una tienda ejecutaba en la pantalla del operador — comprobado antes de
     corregirlo, no supuesto.
  4. **Un fallo de guardado no pierde la captura**: el reintento reenvia el
     mismo payload y no obliga a rehacer la llamada.
  5. **El guardado se confirma** de forma inequivoca y anunciada.

La app arranca SIN credenciales de Google, comprobado en la direccion util, y
todos los datos son sinteticos. No llama a ninguna API de pago.
"""
import json
import os
import sys
import threading
import time
from pathlib import Path
from wsgiref.simple_server import make_server

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

os.environ.setdefault("PANEL_AUTH_DESACTIVADA", "1")
os.environ.pop("GOOGLE_CREDENTIALS_JSON", None)
os.environ["GOOGLE_CREDENTIALS_FILE"] = str(
    Path(__file__).resolve().parent / "_credencial-inexistente-para-capturas.json"
)

import medir_cls  # noqa: E402

PUERTO = 5073

# Nombre de tienda con carga util inofensiva: solo deja una marca en `window`.
CARGA = '<img src=x onerror="window.__ejecuto=true">'

# El validador del Plan 3 exige de 10 a 13 digitos, asi que la forma
# enmascarada "+52...XXXX" no sirve aqui: el modal se quedaba abierto sin
# avanzar. Se usa un numero sintetico evidente y se declara la excepcion con la
# marca que el propio proyecto define, en vez de componer la cadena para que el
# regex no la vea. Esconderla del barrido habria funcionado igual de bien y
# habria normalizado un bypass que, aplicado por costumbre a un numero real,
# dejaria pasar una fuga sin que nadie se entere.
TEL_SINTETICO = "5555555555"   # barrido-ok: numero sintetico de prueba, no es de nadie

CONTACTO = {
    "fin": False,
    "contacto": {
        "TIENDA": "Ferreteria Ejemplo " + CARGA,
        "CIUDAD": "Ciudad Demo 1",
        "CONTACTO": TEL_SINTETICO,
        "CATEGORIA ": "Ferreteria",
        "Esquema": "Mayoreo",
        "Maps": "https://example.com/mapa",
        "_row": 2,
        "_col_respuesta": 6,
    },
}


class Resultado:
    def __init__(self):
        self.fallos = []

    def comprobar(self, nombre, condicion, detalle=""):
        print("  %s %s%s" % ("OK    " if condicion else "FALLA ", nombre,
                             ("  -> " + detalle) if detalle and not condicion else ""))
        if not condicion:
            self.fallos.append(nombre)


def _pagina(navegador, guardar_ok=True):
    pagina = navegador.new_page(viewport={"width": 900, "height": 1000})
    # El orden importa: Playwright evalua las rutas de la ULTIMA a la primera.
    pagina.route("**/api/**", lambda r: r.fulfill(
        status=200, content_type="application/json", body=json.dumps({})))
    pagina.route("**/api/formulario/guardar", lambda r: r.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"ok": True} if guardar_ok
                        else {"ok": False, "error": "429 desde Google."})))
    pagina.route("**/api/formulario/siguiente*", lambda r: r.fulfill(
        status=200, content_type="application/json", body=json.dumps(CONTACTO)))
    return pagina


def paso_activo(pagina):
    return pagina.evaluate("() => (document.querySelector('.step.active')||{}).id")


def enfocado(pagina):
    return pagina.evaluate(
        "() => document.activeElement ? document.activeElement.tagName + ':' +"
        " (document.activeElement.textContent||'').trim().slice(0,22) : null")


def main():
    import app as panel
    medir_cls.verificar_sin_credenciales()

    servidor = make_server("127.0.0.1", PUERTO, panel.app)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()

    r = Resultado()
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        navegador = p.chromium.launch()
        try:
            # ── 1 y 3. Carga del contacto, y el contenido de la hoja ─────────
            pagina = _pagina(navegador)
            errores = []
            pagina.on("pageerror", lambda e: errores.append(str(e)))
            pagina.on("console", lambda m: errores.append(m.text) if m.type == "error" else None)
            pagina.goto("http://127.0.0.1:%d/formulario" % PUERTO, wait_until="load")
            pagina.wait_for_selector("#step-contacto.active", timeout=8000)

            ejecuto = pagina.evaluate("() => !!window.__ejecuto")
            r.comprobar("El contenido de la hoja NO ejecuta", not ejecuto,
                        "un <img onerror> en el nombre de tienda corrio")
            texto = pagina.eval_on_selector("#info-grid", "e => e.textContent")
            r.comprobar("Y aun asi el nombre se ve completo",
                        "Ferreteria Ejemplo" in texto, repr(texto[:70]))

            r.comprobar("El foco llega solo a la primera opcion",
                        pagina.evaluate("() => document.activeElement.tagName") == "BUTTON",
                        "activeElement=%r" % enfocado(pagina))

            # El digito tiene que existir TAMBIEN para quien no ve la pantalla.
            # Al moverlo del texto visible a una pastilla `aria-hidden`, los
            # tres botones del primer paso lo perdian para un lector: es una
            # regresion que introdujo esta misma tarea.
            nombres = pagina.evaluate("""() => {
                const paso = document.querySelector('.step.active');
                return [...paso.querySelectorAll('button')]
                    .filter(b => b.dataset.atajo)
                    .map(b => ({ atajo: b.dataset.atajo,
                                 nombre: b.getAttribute('aria-label') || b.textContent.trim() }));
            }""")
            r.comprobar("El digito esta en el nombre accesible, no solo a la vista",
                        bool(nombres) and all(
                            n["nombre"].startswith(n["atajo"] + ".") for n in nombres),
                        "%r" % (nombres[:3],))

            # ── 2. Captura completa SOLO con teclado, contando pulsaciones ──
            # Ruta feliz: APROBADO -> Respondio -> ... -> Pedido.
            # Cada paso se contesta con el digito de su opcion.
            pulsaciones = 0
            inicio = time.time()

            def tecla(k):
                nonlocal pulsaciones
                pagina.keyboard.press(k)
                pulsaciones += 1
                pagina.wait_for_timeout(60)

            tecla("1")                       # contacto -> APROBADO
            pagina.wait_for_selector("#step-p0.active", timeout=4000)
            tecla("1")                       # p0 -> Respondio
            pagina.wait_for_selector("#step-p1.active", timeout=4000)
            # p1 es multiseleccion: se elige una opcion y se continua.
            opciones_p1 = pagina.eval_on_selector_all("#sel-p1 .btn", "e => e.length")
            if opciones_p1:
                tecla("1")                   # marca la primera opcion
            # El digito de "Continuar" se LEE del propio boton, no se calcula:
            # calcularlo a mano fue lo que hizo que el script pulsara "Colgo".
            atajo_continuar = pagina.eval_on_selector(
                "#btn-p1", "e => e.dataset.atajo || ''")
            assert atajo_continuar, "el boton Continuar no recibio atajo"
            tecla(atajo_continuar)
            for esperado in ("step-p2", "step-p3", "step-p4", "step-p5", "step-p6", "step-p7"):
                pagina.wait_for_selector("#%s.active" % esperado, timeout=4000)
                tecla("1")
            # La conclusion "Pedido" abre el validador de numero del Plan 3
            # antes de guardar: forma parte de la captura, asi que se cuenta.
            # El foco ya esta en el campo, asi que Enter confirma.
            pagina.wait_for_selector("#modal-validar-catalogo", state="visible", timeout=4000)
            r.comprobar("El validador de numero recibe el foco en el campo",
                        pagina.evaluate("() => document.activeElement.id") == "val-cat-tel",
                        "activeElement=%r" % pagina.evaluate("() => document.activeElement.id"))
            tecla("Enter")
            try:
                pagina.wait_for_selector("#step-siguiente.active", timeout=8000)
            except Exception:
                print("         DIAGNOSTICO paso=%r errores=%r" % (paso_activo(pagina), errores[:3]))
                raise
            segundos = time.time() - inicio

            r.comprobar("Captura completa SOLO con teclado, sin un clic",
                        paso_activo(pagina) == "step-siguiente",
                        "acabo en %r" % paso_activo(pagina))
            print("         %d pulsaciones, %.1f s de reloj (con esperas del script)"
                  % (pulsaciones, segundos))

            # Cuantas pulsaciones haria falta SIN atajos ni foco automatico:
            # en cada paso, tabular desde <body> hasta la opcion + Enter.
            sin_atajos = pagina.evaluate("""() => {
                // Se recorre la misma ruta contando los tabulables que hay
                // ANTES de la primera opcion de cada paso, que es lo que el
                // operador tenia que atravesar cuando el foco caia a <body>.
                const pasos = ['contacto','p0','p1','p2','p3','p4','p5','p6','p7'];
                let total = 0;
                pasos.forEach(id => {
                    const paso = document.getElementById('step-' + id);
                    if (!paso) return;
                    const previos = [];
                    document.querySelectorAll('a[href],button:not([disabled]),input,select,textarea')
                        .forEach(el => {
                            if (paso.contains(el)) return;
                            if (el.closest('.step') && !el.closest('.step').classList.contains('active')) return;
                            previos.push(el);
                        });
                    // Tabs hasta salir de lo previo + 1 Enter.
                    total += previos.length + 1 + 1;
                });
                return total;
            }""")
            r.comprobar("El teclado no sale perdiendo frente al flujo anterior",
                        pulsaciones <= sin_atajos,
                        "ahora %d pulsaciones, antes ~%d" % (pulsaciones, sin_atajos))
            print("         referencia sin atajos ni foco automatico: ~%d pulsaciones"
                  % sin_atajos)

            # ── 5. La confirmacion se anuncia ───────────────────────────────
            confirmacion = pagina.evaluate("""() => {
                const c = document.querySelector('#step-siguiente .fin');
                return {
                    rol: c ? c.getAttribute('role') : null,
                    resumen: (document.getElementById('resumen-guardado')||{}).textContent || '',
                };
            }""")
            r.comprobar("El guardado se confirma y se anuncia",
                        confirmacion["rol"] == "status"
                        and "APROBADO" in confirmacion["resumen"],
                        "%r" % (confirmacion,))
            pagina.close()

            # ── 4. Un fallo de guardado no pierde la captura ────────────────
            pagina = _pagina(navegador, guardar_ok=False)
            pagina.goto("http://127.0.0.1:%d/formulario" % PUERTO, wait_until="load")
            pagina.wait_for_selector("#step-contacto.active", timeout=8000)
            # Camino corto: "Enc. Compras No Disponible" guarda directo. Se
            # localiza por su ATAJO, no por posicion entre hermanos: los
            # botones estan repartidos en varios `.btn-group`, asi que un
            # `nth-last-of-type` no seleccionaba lo que parecia.
            atajo_enc = pagina.evaluate(
                "() => [...document.querySelectorAll('#step-contacto button')]"
                ".filter(b => /Enc\./.test(b.textContent))[0]?.dataset?.atajo || ''")
            assert atajo_enc, "no se encuentra el atajo de Enc. No Disponible"
            pagina.keyboard.press(atajo_enc)
            pagina.wait_for_selector("#step-guardado-error.active", timeout=8000)
            r.comprobar("Un fallo de guardado no vuelve al contacto en blanco",
                        paso_activo(pagina) == "step-guardado-error",
                        "acabo en %r" % paso_activo(pagina))

            detalle = pagina.eval_on_selector("#guardado-error-detalle", "e => e.textContent")
            r.comprobar("El error dice que las respuestas siguen ahi",
                        "siguen aquí" in detalle, repr(detalle[:70]))

            rol = pagina.eval_on_selector("#step-guardado-error .estado",
                                          "e => e.getAttribute('role')")
            r.comprobar("El fallo de guardado interrumpe (role=alert)",
                        rol == "alert", "role=%r" % rol)

            # Y el reintento reenvia lo mismo: se deja pasar el guardado.
            pagina.unroute("**/api/formulario/guardar")
            pagina.route("**/api/formulario/guardar", lambda rt: rt.fulfill(
                status=200, content_type="application/json",
                body=json.dumps({"ok": True})))
            pagina.click("#btn-reintentar-guardado")
            pagina.wait_for_selector("#step-siguiente.active", timeout=8000)
            resumen = pagina.eval_on_selector("#resumen-guardado", "e => e.textContent")
            r.comprobar("El reintento guarda sin rehacer la llamada",
                        "Enc No Disponible" in resumen, repr(resumen[:70]))
            pagina.close()
        finally:
            navegador.close()
            servidor.shutdown()

    if r.fallos:
        print("\n%d comprobacion(es) en rojo:" % len(r.fallos))
        for f in r.fallos:
            print("   -", f)
        return 1
    print("\nTodas las comprobaciones en verde.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
