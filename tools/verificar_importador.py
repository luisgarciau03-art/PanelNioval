"""Verificacion EN NAVEGADOR del importador (Plan 4, T4.9).

Uso:
    python tools/verificar_importador.py

El registro del ADR para esta superficie es NARRATIVO: una corrida dura minutos
y gasta dinero, asi que la pantalla tiene que contar donde va, en que fase, y
como acabo. Lo que se mide aqui es justo eso, mas las dos cosas que ninguna
lectura de codigo ve:

  1. **Los 606 chips no se reconstruyen al filtrar.** La version anterior
     rehacia el `innerHTML` entero en cada pulsacion: 713.5 ms en el peor caso
     de siete repeticiones, 18.0 ms de mediana, medidos en navegador con el
     catalogo completo. Aqui se comprueba que el nodo del primer chip SOBREVIVE
     al filtro -o sea que no hubo re-render, que el reloj podria disimular en
     una maquina rapida- y ademas se cronometra la pulsacion EN CALIENTE: el
     primer layout tras cargar la pagina es caro con cualquier implementacion,
     y medirlo como si fuera el caso normal exagera las dos cifras.
  2. **Los chips se pueden usar con teclado.** Antes eran 606 `<span>` con
     manejador de clic: ni uno alcanzable sin raton. Ahora son un `listbox` con
     UNA sola parada de tabulacion y flechas que saltan lo que el filtro oculta.

Y ademas: agrupacion por macro-region con conteo por grupo en vivo, jerarquia
real de los cuatro contadores, la fase visible junto al progreso, el registro
que se ANADE sin robar el scroll, los cuatro finales distinguibles -solo `done`
celebra-, y cero `alert()`/`confirm()`.

Las ciudades salen del catalogo versionado del repo (datos publicos del INEGI);
los contadores de la corrida son sinteticos. La app arranca SIN credenciales de
Google, comprobado en la direccion util. No se llama a ninguna API de pago.
"""
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
# No basta con quitar la variable: app.py cae a un .json de la raiz del
# proyecto. Se cortan las DOS vias y `medir_cls.verificar_sin_credenciales()`
# comprueba que el cliente de verdad falla.
os.environ.pop("GOOGLE_CREDENTIALS_JSON", None)
os.environ["GOOGLE_CREDENTIALS_FILE"] = str(
    Path(__file__).resolve().parent / "_credencial-inexistente-para-capturas.json"
)

import medir_cls  # noqa: E402

PUERTO = 5079

# Nombre de ciudad con carga util inofensiva: solo deja una marca en `window`.
# El catalogo lo alimenta un archivo del repo, pero el nombre acaba viniendo de
# `LISTA DE CONTACTOS`, que teclea un operador sin validacion.
CARGA = '<img src=x onerror="window.__ejecuto=true">'


def _catalogo():
    """606 municipios reales del catalogo versionado + uno con carga util."""
    catalogo = json.loads((RAIZ / "datos" / "ciudades_mx.json").read_text(encoding="utf-8"))
    ciudades = []
    for i, reg in enumerate(catalogo):
        ciudades.append({
            "ciudad": reg["nombre"],
            "estado": reg["estado"],
            "region": reg["region"],
            "potencial_mercado": reg.get("potencial_mercado", 0),
            "desempeno_nioval": 1.0,
            "prioridad": round(1000 - i, 1),
            "unidades_ferreteras": reg["indicadores"]["unidades_ferreteras"],
            "explicacion": "Sintetico: posicion %d" % (i + 1),
            "total": 0, "llamados": 0, "aprobados": 0,
            "interes_pct": (i % 7) * 3,
        })
    ciudades.append({
        "ciudad": "Ciudad Demo " + CARGA,
        "estado": "Demo", "region": ciudades[0]["region"],
        "potencial_mercado": 0, "desempeno_nioval": 1.0, "prioridad": 0,
        "unidades_ferreteras": 1, "explicacion": "Sintetico con carga util",
        "total": 0, "llamados": 0, "aprobados": 0, "interes_pct": 0,
    })
    conteo = Counter(c["region"] for c in ciudades)
    regiones = sorted(({"region": r, "total": n} for r, n in conteo.items()),
                      key=lambda x: -x["total"])
    return {"ciudades": ciudades, "sin_clasificar": [], "regiones": regiones,
            "catalogo_cargado": True}


CIUDADES = _catalogo()

# Estado de una corrida a medias, servido por /api/importador/estado.
def _estado(**cambios):
    base = {
        "status": "running", "ciudad": "Ciudad Demo 1", "categoria": "Ferreterías",
        "progreso": 1, "total": 2, "fraccion": 42, "fase": "Ferreterías: página 2 de 3",
        "medidor": {"text_search": 6, "place_details": 30, "cache_hits": 4,
                    "duplicados_evitados": 2, "costo": None},
        "encontrados": 20, "nuevos_en_sheet": 7, "duplicados": 13, "descartados": 5,
        "log": ["Buscando Ferreterías en Ciudad Demo 1...", "12 resultados"],
        "error": "",
    }
    base.update(cambios)
    return base


class _SinDato:
    """Valor ausente que se deja comparar, formatear y recorrer sin reventar.

    Con `None` no basta: `None > 0` lanza `TypeError`, y entonces el arnes
    muere igual que antes, solo que una linea mas abajo. Este objeto es SIEMPRE
    falso, asi que cualquier comprobacion que lo toque sale en rojo -que es lo
    correcto cuando la pantalla no tiene la pieza- en vez de tumbar la corrida.
    """
    def __bool__(self): return False
    def __eq__(self, otro): return isinstance(otro, _SinDato)
    def __ne__(self, otro): return not isinstance(otro, _SinDato)
    def __lt__(self, otro): return False
    def __le__(self, otro): return False
    def __gt__(self, otro): return False
    def __ge__(self, otro): return False
    def __mul__(self, otro): return self
    __rmul__ = __mul__
    def __contains__(self, otro): return False
    def __iter__(self): return iter(())
    def __len__(self): return 0
    def __getitem__(self, clave): return self
    def __getattr__(self, nombre): return lambda *a, **kw: self
    def __float__(self): return 0.0
    def __int__(self): return 0
    def __hash__(self): return 0
    def __repr__(self): return "<sin dato>"
    def __str__(self): return "<sin dato>"


SIN_DATO = _SinDato()


class Caja(dict):
    """Dict que devuelve `SIN_DATO` en vez de reventar por una clave que falta.

    Es lo que permite que el arnes siga informando cuando la pantalla NO tiene
    la pieza que se le pregunta: sin esto, la primera regresion tira un
    `TypeError` de Playwright y las veinte comprobaciones siguientes no llegan
    a correr. Un arnes que muere en el primer fallo informa de uno; este
    informa de todos.
    """
    def __missing__(self, clave):
        return SIN_DATO


def ev(pagina, guion, argumento=None):
    """Evalua en la pagina y convierte cualquier fallo en un resultado vacio."""
    try:
        salida = (pagina.evaluate(guion, argumento) if argumento is not None
                  else pagina.evaluate(guion))
    except Exception as e:                      # noqa: BLE001 - se reporta, no se traga
        print("         (la pagina no respondio: %s)" % str(e).splitlines()[0][:90])
        return Caja()
    return Caja(salida) if isinstance(salida, dict) else salida


class Resultado:
    def __init__(self):
        self.fallos = []

    def comprobar(self, nombre, condicion, detalle=""):
        print("  %s %s%s" % ("OK    " if condicion else "FALLA ", nombre,
                             ("  -> " + detalle) if detalle and not condicion else ""))
        if not condicion:
            self.fallos.append(nombre)


def _pagina(navegador, ancho=1000, estado=None):
    pagina = navegador.new_page(viewport={"width": ancho, "height": 1000})
    # Playwright evalua las rutas de la ULTIMA a la primera: la generica va
    # ANTES y las especificas DESPUES. Al reves, la generica se come a las otras
    # y el PoC de XSS da negativo en falso porque no llega a renderizarse nada.
    pagina.route("**/api/**", lambda r: r.fulfill(
        status=200, content_type="application/json", body=json.dumps({})))
    pagina.route("**/api/importador/estado", lambda r: r.fulfill(
        status=200, content_type="application/json",
        body=json.dumps(estado if estado is not None else {"status": "idle"})))
    pagina.route("**/api/importador/ciudades", lambda r: r.fulfill(
        status=200, content_type="application/json",
        body=json.dumps(CIUDADES, ensure_ascii=False)))
    # Ni un dialogo del navegador puede quedar vivo: si alguno aparece, se
    # registra y se cierra para que la corrida no se cuelgue.
    pagina.__dialogos = []
    pagina.on("dialog", lambda d: (pagina.__dialogos.append(d.message), d.dismiss()))
    return pagina


def main():
    import app as panel
    medir_cls.verificar_sin_credenciales()

    servidor = make_server("127.0.0.1", PUERTO, panel.app)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()

    r = Resultado()
    from playwright.sync_api import sync_playwright
    url = "http://127.0.0.1:%d/importador" % PUERTO

    with sync_playwright() as p:
        navegador = p.chromium.launch()
        try:
            pagina = _pagina(navegador)
            errores = []
            pagina.on("pageerror", lambda e: errores.append(str(e)))
            pagina.on("console", lambda m: errores.append(m.text) if m.type == "error" else None)
            pagina.goto(url, wait_until="load")
            pagina.wait_for_selector(".chip-ciudad", timeout=15000)

            # ── 1. El contenido de la hoja no ejecuta ──────────────────────
            r.comprobar("El nombre de ciudad de la hoja NO ejecuta",
                        not ev(pagina, "() => !!window.__ejecuto"),
                        "un <img onerror> en el nombre de una ciudad corrio")
            r.comprobar("Y aun asi el nombre se ve completo",
                        ev(pagina, 
                            "() => [...document.querySelectorAll('.chip-ciudad')]"
                            ".some(c => c.textContent.includes('Ciudad Demo'))"))

            # ── 2. Agrupacion por macro-region con conteo por grupo ────────
            grupos = ev(pagina, """() => {
                const gs = [...document.querySelectorAll('#chips-lista .grupo')];
                return gs.map(g => ({
                    region: g.dataset.region,
                    rol: g.getAttribute('role'),
                    conteo: (g.querySelector('[data-conteo]')||{}).textContent,
                    chips: g.querySelectorAll('.chip-ciudad').length,
                }));
            }""")
            r.comprobar("Los chips van agrupados por macro-region",
                        len(grupos) >= 8, "%d grupos" % len(grupos))
            r.comprobar("Cada grupo declara su conteo en la cabecera",
                        all(g["conteo"] and str(g["chips"]) in g["conteo"] for g in grupos),
                        "%r" % (grupos[:2],))
            total_chips = sum(g["chips"] for g in grupos)
            r.comprobar("Estan las 607 ciudades servidas",
                        total_chips == len(CIUDADES["ciudades"]),
                        "%d chips para %d ciudades" % (total_chips, len(CIUDADES["ciudades"])))

            # ── 3. Filtrar NO reconstruye la lista ─────────────────────────
            ev(pagina, "() => { window.__primerChip = document.querySelector('.chip-ciudad'); }")
            medidas = ev(pagina, """(veces) => {
                const inp = document.getElementById('ciudad-filter');
                const caja = document.getElementById('ciudades-chips');
                const consultas = ['a', 'an', 'ana', ''];
                // Calentamiento. El PRIMER layout tras cargar la pagina es
                // siempre el caro -y lo es igual con cualquier implementacion-,
                // asi que medirlo como si fuera el caso normal exagera la cifra
                // y no dice nada de lo que siente el operador tecleando.
                for (const q of consultas) { inp.value = q; filtrarCiudades(); void caja.offsetHeight; }
                const salida = [];
                for (const q of consultas) {
                    let peor = 0;
                    for (let n = 0; n < veces; n++) {
                        inp.value = '';
                        filtrarCiudades();
                        void caja.offsetHeight;
                        inp.value = q;
                        const t0 = performance.now();
                        filtrarCiudades();
                        void caja.offsetHeight;
                        peor = Math.max(peor, performance.now() - t0);
                    }
                    salida.push({q: q || '(vacio)', ms: +peor.toFixed(1),
                                 visibles: [...document.querySelectorAll('.chip-ciudad')]
                                     .filter(c => !c.hidden).length});
                }
                return salida;
            }""", 5)
            for m in medidas:
                print("         filtro %-8s -> %4d visibles, peor de 5: %5.1f ms"
                      % (m["q"], m["visibles"], m["ms"]))
            r.comprobar("Filtrar no reconstruye los chips (el nodo sobrevive)",
                        ev(pagina, 
                            "() => window.__primerChip === document.querySelector('.chip-ciudad')"),
                        "el primer chip fue reemplazado: hubo re-render")
            peor = max(m["ms"] for m in medidas)
            r.comprobar("Una pulsacion del buscador cuesta menos de 16 ms",
                        peor < 16, "la peor costo %.1f ms" % peor)

            # ── 4. El conteo por grupo se actualiza en vivo ────────────────
            vivo = ev(pagina, """() => {
                const inp = document.getElementById('ciudad-filter');
                inp.value = 'guada';
                filtrarCiudades();
                const gs = [...document.querySelectorAll('#chips-lista .grupo')];
                const visibles = gs.filter(g => !g.hidden);
                return {
                    ocultos: gs.length - visibles.length,
                    conteos: visibles.map(g => (g.querySelector('[data-conteo]')||{}).textContent),
                    chipsVisibles: [...document.querySelectorAll('.chip-ciudad')].filter(c => !c.hidden).length,
                    resumen: document.getElementById('chips-resumen').textContent,
                };
            }""")
            r.comprobar("Un grupo sin coincidencias se retira entero",
                        vivo["ocultos"] > 0, "ningun grupo se oculto")
            r.comprobar("El conteo del grupo pasa a 'N de M' al filtrar",
                        any(" de " in c for c in vivo["conteos"]), "%r" % (vivo["conteos"],))
            r.comprobar("El resumen dice cuantas quedan de cuantas",
                        "de" in vivo["resumen"] and str(vivo["chipsVisibles"]) in vivo["resumen"],
                        "resumen=%r" % vivo["resumen"])

            # ── 5. Region y texto se combinan ──────────────────────────────
            combinado = ev(pagina, """() => {
                const region = [...document.querySelectorAll('#region-filter option')]
                    .map(o => o.value).filter(Boolean)[0];
                document.getElementById('region-filter').value = region;
                document.getElementById('ciudad-filter').value = 'a';
                filtrarCiudades();
                const visibles = [...document.querySelectorAll('.chip-ciudad')].filter(c => !c.hidden);
                return {
                    region,
                    fueraDeRegion: visibles.filter(c => c.closest('.grupo').dataset.region !== region).length,
                    sinLaLetra: visibles.filter(c => !c.dataset.ciudad.toLowerCase().includes('a')).length,
                };
            }""")
            r.comprobar("El filtro de region y el de texto se combinan",
                        combinado["fueraDeRegion"] == 0 and combinado["sinLaLetra"] == 0,
                        "%r" % (combinado,))

            # ── 6. Sin coincidencias: estado vacio, y sin celebrar ─────────
            vacio = ev(pagina, """() => {
                document.getElementById('region-filter').value = '';
                document.getElementById('ciudad-filter').value = 'zzzzzz';
                filtrarCiudades();
                const caja = document.getElementById('chips-sin-resultados');
                return {visible: !caja.hidden, texto: caja.textContent,
                        rol: (caja.querySelector('[role]')||{}).getAttribute
                             ? caja.querySelector('[role]').getAttribute('role') : null};
            }""")
            r.comprobar("Sin coincidencias se explica y se ofrece salida",
                        vacio["visible"] and "Ninguna ciudad coincide" in vacio["texto"],
                        "%r" % (vacio,))
            r.comprobar("El vacio no celebra",
                        not any(c in vacio["texto"] for c in ("🎉", "✅")), vacio["texto"][:60])

            # ── 7. Teclado: una sola parada de tabulacion ──────────────────
            teclado = ev(pagina, """() => {
                document.getElementById('ciudad-filter').value = '';
                filtrarCiudades();
                const chips = [...document.querySelectorAll('.chip-ciudad')];
                return {
                    paradas: chips.filter(c => c.tabIndex === 0).length,
                    rolLista: (document.getElementById('chips-lista')||{}).getAttribute('role'),
                    rolOpcion: chips[0].getAttribute('role'),
                };
            }""")
            r.comprobar("La lista de ciudades es UNA sola parada de tabulacion",
                        teclado["paradas"] == 1, "%d chips con tabindex=0" % teclado["paradas"])
            r.comprobar("La lista se anuncia como listbox y los chips como option",
                        teclado["rolLista"] == "listbox" and teclado["rolOpcion"] == "option",
                        "%r" % (teclado,))

            # Las flechas mueven el foco y SALTAN lo que el filtro oculta.
            ev(pagina, """() => {
                document.getElementById('ciudad-filter').value = 'guadal';
                filtrarCiudades();
                document.querySelectorAll('.chip-ciudad')[0]; }""")
            primero = ev(pagina, """() => {
                const vis = [...document.querySelectorAll('.chip-ciudad')].filter(c => !c.hidden);
                vis[0].focus();
                return document.activeElement.dataset.ciudad;
            }""")
            pagina.keyboard.press("ArrowRight")
            tras_flecha = ev(pagina, 
                "() => ({ciudad: document.activeElement.dataset.ciudad,"
                " oculto: document.activeElement.hidden})")
            r.comprobar("Las flechas recorren solo los chips visibles",
                        tras_flecha["ciudad"] != primero and not tras_flecha["oculto"],
                        "de %r a %r" % (primero, tras_flecha))

            pagina.keyboard.press("Enter")
            elegido = ev(pagina, """() => ({
                input: document.getElementById('input-ciudad').value,
                seleccionados: document.querySelectorAll('.chip-ciudad[aria-selected="true"]').length,
                marcado: document.activeElement.getAttribute('aria-selected'),
                paradas: [...document.querySelectorAll('.chip-ciudad')]
                    .filter(c => c.tabIndex === 0).length,
            })""")
            r.comprobar("Enter elige la ciudad y la escribe en el campo",
                        elegido["input"] == tras_flecha["ciudad"] and elegido["marcado"] == "true",
                        "%r" % (elegido,))
            r.comprobar("Solo hay una ciudad marcada a la vez",
                        elegido["seleccionados"] == 1,
                        "%d marcadas" % elegido["seleccionados"])
            # Elegir no puede dejar DOS paradas de tabulacion: la del chip que
            # ya la tenia y la del recien elegido.
            r.comprobar("Elegir una ciudad deja UNA sola parada de tabulacion",
                        elegido["paradas"] == 1,
                        "%s chips con tabindex=0" % elegido["paradas"])

            # Y la marca sigue al campo: si el operador teclea otra ciudad a
            # mano, el chip de antes deja de decir la verdad.
            a_mano = ev(pagina, """() => {
                const campo = document.getElementById('input-ciudad');
                campo.value = 'Una ciudad escrita a mano';
                campo.dispatchEvent(new Event('input', {bubbles: true}));
                return {marcadas: document.querySelectorAll('.chip-ciudad[aria-selected="true"]').length,
                        paradas: [...document.querySelectorAll('.chip-ciudad')]
                            .filter(c => c.tabIndex === 0).length};
            }""")
            r.comprobar("Escribir otra ciudad a mano apaga la marca del chip",
                        a_mano["marcadas"] == 0 and a_mano["paradas"] == 1,
                        "%r" % (a_mano,))

            # ── 8. Jerarquia de los cuatro contadores ──────────────────────
            ev(pagina, "() => { mostrarPaneles(); pintarEstado(%s); }"
                            % json.dumps(_estado()))
            tam = ev(pagina, """() => {
                const px = id => parseFloat(getComputedStyle(document.getElementById(id)).fontSize);
                return {nuevos: px('s-nuevos'), encontrados: px('s-encontrados'),
                        duplicados: px('s-duplicados'), descartados: px('s-descartados')};
            }""")
            secundario = max(tam["encontrados"], tam["duplicados"], tam["descartados"])
            r.comprobar("`nuevos_en_sheet` es el numero grande de la pantalla",
                        tam["nuevos"] >= secundario * 1.6,
                        "%.1f px contra %.1f px" % (tam["nuevos"], secundario))
            print("         contadores: nuevos %.0f px, secundarios %.0f px"
                  % (tam["nuevos"], secundario))

            # Los cuatro numeros son los que sirve el backend, sin aritmetica
            # propia: es la mitad de cliente de CE1 del Plan 3.
            numeros = ev(pagina, """() => ({
                nuevos: document.getElementById('s-nuevos').textContent,
                encontrados: document.getElementById('s-encontrados').textContent,
                duplicados: document.getElementById('s-duplicados').textContent,
                descartados: document.getElementById('s-descartados').textContent,
                progreso: document.getElementById('s-progreso').textContent,
            })""")
            r.comprobar("Los cuatro contadores muestran lo que sirve el backend",
                        numeros == {"nuevos": "7", "encontrados": "20", "duplicados": "13",
                                    "descartados": "5", "progreso": "1/2"},
                        "%r" % (numeros,))

            # ── 9. La fase, visible junto al progreso ──────────────────────
            fase = ev(pagina, """() => ({
                texto: document.getElementById('prog-fase').textContent,
                visible: !!document.getElementById('prog-fase').offsetParent,
                pct: document.getElementById('prog-pct').textContent,
                aria: document.getElementById('prog-track').getAttribute('aria-valuenow'),
                detalle: document.getElementById('prog-label').textContent,
            })""")
            r.comprobar("La fase del backend se ve junto a la barra",
                        fase["visible"] and "página 2 de 3" in fase["texto"],
                        "%r" % (fase,))
            r.comprobar("El porcentaje y el valor ARIA coinciden con la fraccion",
                        fase["pct"] == "42%" and fase["aria"] == "42", "%r" % (fase,))

            # ── 10. El registro se anade, no se reconstruye ────────────────
            ev(pagina, "() => { window.__primeraLinea = document.querySelector('#log-box .entry'); }")
            log = ev(pagina, """(d) => {
                pintarEstado(d);
                const caja = document.getElementById('log-box');
                return {lineas: caja.childElementCount,
                        sobrevive: window.__primeraLinea === caja.querySelector('.entry'),
                        texto: caja.textContent};
            }""", _estado(log=["Buscando Ferreterías en Ciudad Demo 1...", "12 resultados",
                               "Guardando 7 filas nuevas"]))
            r.comprobar("El registro anade lineas en vez de reconstruirse",
                        log["sobrevive"] and log["lineas"] == 3,
                        "%d lineas, primera sobrevive=%s" % (log["lineas"], log["sobrevive"]))
            r.comprobar("La linea nueva aparece en el registro",
                        "Guardando 7 filas nuevas" in log["texto"])

            # Y no arrastra el scroll de quien esta leyendo mas arriba.
            scroll = ev(pagina, """(d) => {
                const caja = document.getElementById('log-box');
                for (let i = 0; i < 40; i++) {
                    const l = document.createElement('div');
                    l.className = 'entry'; l.textContent = 'relleno ' + i;
                    caja.appendChild(l);
                }
                caja.scrollTop = 0;
                pintarEstado(d);
                return caja.scrollTop;
            }""", _estado(log=["otra linea del worker"]))
            r.comprobar("El registro no roba el scroll al que esta leyendo",
                        scroll == 0, "el scroll salto a %s" % scroll)

            # ── 11. La consola, dentro del sistema ─────────────────────────
            consola = ev(pagina, """() => {
                const el = document.getElementById('log-box');
                return {fuente: getComputedStyle(el).fontFamily,
                        tab: el.tabIndex,
                        rol: el.getAttribute('role'),
                        etiquetada: !!el.getAttribute('aria-labelledby')};
            }""")
            r.comprobar("El registro se anuncia como registro (role=log)",
                        consola["rol"] == "log",
                        "role=%r; con role=region las lineas nuevas no llegan al lector"
                        % consola["rol"])
            r.comprobar("La consola declara su pila monoespaciada",
                        consola["fuente"].strip() != "monospace" and "mono" in consola["fuente"],
                        "font-family=%r" % consola["fuente"])
            r.comprobar("La consola con scroll se puede recorrer con teclado",
                        consola["tab"] == 0 and consola["etiquetada"], "%r" % (consola,))

            # ── 12. Los cuatro finales se distinguen ───────────────────────
            finales = {}
            for st in ("done", "cancelado", "presupuesto_agotado", "error"):
                finales[st] = ev(pagina, """(d) => {
                    rematar(d);
                    const caja = document.getElementById('result-box');
                    return {clase: caja.className, rol: caja.getAttribute('role'),
                            icono: document.getElementById('result-icono').textContent,
                            fondo: getComputedStyle(caja).backgroundColor,
                            fase: document.getElementById('prog-fase').textContent};
                }""", _estado(status=st, error="Tope de gasto alcanzado."))
            clases = {st: v["clase"] for st, v in finales.items()}
            r.comprobar("Los cuatro finales tienen presentacion distinta",
                        len(set(clases.values())) == 4, "%r" % (clases,))
            r.comprobar("Solo `done` se viste de exito",
                        "exito" in clases["done"]
                        and not any("exito" in c for st, c in clases.items() if st != "done"),
                        "%r" % (clases,))
            r.comprobar("Detenido a mano NO se presenta como error",
                        finales["cancelado"]["clase"] != finales["error"]["clase"]
                        and "error" not in finales["cancelado"]["clase"],
                        "%r" % (finales["cancelado"],))
            r.comprobar("Tope de gasto NO se presenta como error",
                        "error" not in finales["presupuesto_agotado"]["clase"],
                        "%r" % (finales["presupuesto_agotado"],))
            r.comprobar("Solo el fallo interrumpe al lector (role=alert)",
                        finales["error"]["rol"] == "alert"
                        and all(v["rol"] == "status" for st, v in finales.items() if st != "error"),
                        "%r" % ({st: v["rol"] for st, v in finales.items()},))
            r.comprobar("Ningun final que no completo lleva marca de exito",
                        all("✅" not in v["icono"] for st, v in finales.items() if st != "done"),
                        "%r" % ({st: v["icono"] for st, v in finales.items()},))

            # ── 13. Ni un dialogo del navegador ────────────────────────────
            ev(pagina, """() => {
                ponerEnMarcha(false);
                document.getElementById('input-ciudad').value = '';
                iniciar();
            }""")
            pagina.wait_for_timeout(200)
            validacion = ev(pagina, """() => ({
                invalido: document.getElementById('input-ciudad').getAttribute('aria-invalid'),
                enfocado: document.activeElement.id,
                rol: (document.querySelector('#aviso-inicio [role]')||{}).getAttribute
                     ? document.querySelector('#aviso-inicio [role]').getAttribute('role') : null,
                texto: document.getElementById('aviso-inicio').textContent,
            })""")
            r.comprobar("Sin ciudad, el error va junto al campo y se anuncia",
                        validacion["invalido"] == "true" and validacion["rol"] == "alert",
                        "%r" % (validacion,))
            r.comprobar("Y el foco vuelve a donde hay que escribir",
                        validacion["enfocado"] == "input-ciudad",
                        "foco en %r" % validacion["enfocado"])

            # Detener pide confirmacion EN LA PAGINA, no con confirm().
            pedido = ev(pagina, """() => {
                mostrarPaneles();
                ponerEnMarcha(true);
                pedirDetener();
                return {hayBotones: !!document.getElementById('btn-detener-si'),
                        enfocado: document.activeElement.id,
                        rol: (document.querySelector('#aviso-inicio [role]')||{}).getAttribute
                             ? document.querySelector('#aviso-inicio [role]').getAttribute('role') : null};
            }""")
            r.comprobar("Detener se confirma en la pagina, con el foco puesto",
                        pedido["hayBotones"] and pedido["enfocado"] == "btn-detener-no",
                        "%r" % (pedido,))
            # Un `alertdialog` promete modalidad: `aria-modal`, trampa de foco y
            # el resto de la pagina inerte. Aqui no hay ninguna de las tres a
            # proposito, asi que anunciarlo como dialogo modal seria mentir.
            r.comprobar("La confirmacion no se anuncia como dialogo modal",
                        pedido["rol"] == "group",
                        "role=%r" % pedido["rol"])
            seguir = ev(pagina, """() => {
                document.getElementById('btn-detener-no').click();
                return document.getElementById('aviso-inicio').textContent.trim();
            }""")
            r.comprobar("'Seguir buscando' cierra la confirmacion sin cancelar",
                        seguir == "", "quedo %r" % seguir[:60])
            r.comprobar("Ningun dialogo del navegador se abrio en toda la corrida",
                        not pagina.__dialogos, "%r" % (pagina.__dialogos,))

            r.comprobar("La pagina no lanzo errores de JavaScript",
                        not errores, "%r" % (errores[:3],))
            pagina.close()

            # ── 14. 320 px: nada se sale ni por fuera ni por dentro ────────
            pagina = _pagina(navegador, ancho=320)
            pagina.goto(url, wait_until="load")
            pagina.wait_for_selector(".chip-ciudad", timeout=15000)
            ev(pagina, "() => { mostrarPaneles(); pintarEstado(%s); }"
                            % json.dumps(_estado()))
            pagina.wait_for_timeout(200)
            estrecho = ev(pagina, """() => {
                const doc = document.documentElement;
                const caja = document.getElementById('ciudades-chips');
                const limite = caja.getBoundingClientRect().right + 1;
                const salidos = [...document.querySelectorAll('.chip-ciudad')]
                    .filter(c => !c.hidden && c.getBoundingClientRect().right > limite).length;
                return {scroll: doc.scrollWidth, cliente: doc.clientWidth, salidos,
                        chips: [...document.querySelectorAll('.chip-ciudad')].filter(c => !c.hidden).length};
            }""")
            r.comprobar("A 320 px el documento no desborda en horizontal",
                        estrecho["scroll"] <= estrecho["cliente"],
                        "scrollWidth=%d clientWidth=%d" % (estrecho["scroll"], estrecho["cliente"]))
            r.comprobar("A 320 px ningun chip se sale de su caja",
                        estrecho["salidos"] == 0,
                        "%d de %d chips desbordan" % (estrecho["salidos"], estrecho["chips"]))
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
