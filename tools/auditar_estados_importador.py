"""Auditoria de los estados del importador: ¿cual MIENTE? (Plan 3, T3.5)

No audita como se ven -- eso fue el Plan 4, y esta cerrado. Audita si lo que la
pantalla AFIRMA coincide con lo que de verdad paso.

El metodo, y por que es asi:

  1. Cada estado se PROVOCA de verdad, corriendo `_worker_importador` con dobles en
     las dos fronteras externas (Places y Sheets). No se fabrica un diccionario a
     mano: un estado inventado prueba que la pantalla sabe pintar ese diccionario,
     no que el backend lo produzca nunca.
  2. El aviso de Telegram se captura interceptando el `post`, no reimplementando el
     mensaje. Telegram es un SEPTIMO canal de estado que el plan no contaba entre
     los seis de la UI, y en agosto mintio dos veces.
  3. La pantalla se renderiza en navegador con ese estado exacto y se lee lo que el
     operador ve.
  4. Veredicto por estado: COINCIDE o MIENTE, con la afirmacion concreta.

Ni red, ni hoja de produccion, ni un centavo de Places. Los negocios son inventados.

Uso:
    python tools/auditar_estados_importador.py [directorio-de-capturas]

    # Y el mismo recorrido contra el front-end DESPLEGADO, sin provocar corridas:
    PANEL_DASHBOARD_TOKEN=<valor> python tools/auditar_estados_importador.py         docs/investigacion/estados-produccion --contra https://panelnioval.duckdns.org

En el modo `--contra` los estados NO se provocan: se reutilizan los que ya produjo el
backend en la corrida local (`estados.json`) y se le dan a la pantalla que sirve el
VPS. Provocarlos contra produccion costaria dinero de Places y escribiria filas en
`LISTA DE CONTACTOS`; eso es la corrida real, que es gate del owner.

Lo que este modo SI demuestra: que el front-end desplegado saca los mismos veredictos
sobre los mismos datos.
"""
import json
import os
import sys
import threading
from pathlib import Path
from wsgiref.simple_server import make_server

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))

os.environ.setdefault("PANEL_AUTH_DESACTIVADA", "1")
os.environ.pop("GOOGLE_CREDENTIALS_JSON", None)
# El notificador se calla sin estas dos. Se ponen valores de juguete para que el
# mensaje REAL se construya y se pueda leer; el `post` se intercepta mas abajo.
os.environ["TELEGRAM_TOKEN"] = "token-de-juguete-para-la-auditoria"
os.environ["TELEGRAM_CHAT_ID"] = "0"

import reproducir_bugs_importador as repro  # noqa: E402

PUERTO = 5077


# ───────────────────────────── escenarios ─────────────────────────────

def _negocios(prefijo, n, desde=1):
    return [repro._negocio(f"{prefijo} {i}", f"pid-{prefijo[0]}{i}", f"Calle {i}")
            for i in range(desde, desde + n)]


def _correr(app, ciudad, *, ws=None, gmaps=None, cancelar_en=None,
            por_senal=False, tope=None):
    """Provoca UNA corrida real y devuelve (estado_final, aviso_de_telegram)."""
    gmaps = gmaps or repro.GmapsFalso(repro._catalogo(_negocios("Ferreteria", 6),
                                                      _negocios("Distribuidora", 3)))
    ws = ws if ws is not None else repro.WorksheetFalsa()
    previo = _guardar_globales(app)
    repro._preparar(app, gmaps, ws)

    # `_preparar` silencia Telegram; aqui SI lo queremos, con su `post` capturado.
    avisos = []
    app._enviar_telegram_importador = _telegram_real(app, avisos)

    tope_previo = app.PLACES_MAX_LLAMADAS_CORRIDA
    if tope is not None:
        app.PLACES_MAX_LLAMADAS_CORRIDA = tope

    app._import_job = repro._job_limpio(ciudad)
    if cancelar_en is not None:
        _cancelar_a_la_enesima(app, gmaps, cancelar_en, por_senal)

    try:
        app._worker_importador(ciudad, "clave-de-juguete")
    finally:
        # TODO lo global vuelve a su sitio, no solo el tope. `app.googlemaps` y
        # `app.time` son los modulos REALES del proceso, no copias de `app`:
        # dejarlos parcheados convierte `time.sleep` en un no-op permanente para
        # cualquier otro codigo que corra despues en este interprete.
        app.PLACES_MAX_LLAMADAS_CORRIDA = tope_previo
        _restaurar(app, previo)

    return dict(app._import_job), (avisos[0] if avisos else None)


def _guardar_globales(app):
    """Todo lo que `_preparar` va a pisar, antes de que lo pise."""
    return {
        "GMAPS_OK": app.GMAPS_OK,
        "Client": app.googlemaps.Client,
        "sleep": app.time.sleep,
        "get_worksheet": app.get_worksheet,
        "telegram": app._enviar_telegram_importador,
    }


def _restaurar(app, previo):
    app.GMAPS_OK = previo["GMAPS_OK"]
    app.googlemaps.Client = previo["Client"]
    app.time.sleep = previo["sleep"]
    app.get_worksheet = previo["get_worksheet"]
    app._enviar_telegram_importador = previo["telegram"]


def _telegram_real(app, avisos):
    """El notificador de produccion, con el `post` interceptado.

    Reimplementar el mensaje aqui probaria mi copia, no la suya.
    """
    original = _original_telegram(app)

    class PostFalso:
        @staticmethod
        def post(url, data=None, timeout=None, **kw):
            avisos.append((data or {}).get("text", ""))

            class R:
                status_code = 200
            return R()

    def envolver(*a, **kw):
        req_previo = app.req_lib
        app.req_lib = PostFalso
        try:
            return original(*a, **kw)
        finally:
            app.req_lib = req_previo

    return envolver


_ORIGINAL = {}


def _original_telegram(app):
    if "fn" not in _ORIGINAL:
        raise RuntimeError("guardar el notificador original antes de sustituirlo")
    return _ORIGINAL["fn"]


def _cancelar_a_la_enesima(app, gmaps, enesima, por_senal):
    """Pide la cancelacion a mitad de corrida, como la pediria el operador."""
    llamadas = {"n": 0}
    places_original = gmaps.places

    def places(*a, **kw):
        llamadas["n"] += 1
        if llamadas["n"] >= enesima:
            with app._import_lock:
                app._import_job["cancelado"] = True
                if por_senal:
                    app._import_job["parada_por_senal"] = True
        return places_original(*a, **kw)

    gmaps.places = places


def escenarios(app):
    """Los SIETE estados. El plan cuenta seis: `interrumpido` no estaba."""
    out = {}

    # 1. Reposo: nunca se lanzo nada.
    app._import_job = app._nuevo_import_job("", status="idle")
    out["idle"] = (dict(app._import_job), None)

    # 2. Corriendo: instantanea tomada DESDE DENTRO de la corrida, no al final.
    out["running"] = _corrida_a_medias(app)

    # 3. Completada entera, y con SOLAPE a proposito.
    #
    # Si en todos los escenarios `nuevos_en_sheet == encontrados`, comparar los dos
    # numeros no prueba nada: la comprobacion pasaria igual con la pantalla pintando
    # el contador equivocado. Una ciudad ya trabajada los separa -- 14 aprobados,
    # 10 filas nuevas -- que es justo el "20 vs 10" del owner en pequeño.
    ferreterias = _negocios("Ferreteria", 12)
    distribuidoras = _negocios("Ferreteria", 6) + _negocios("Distribuidora", 2)
    gmaps = repro.GmapsFalso(repro._catalogo(ferreterias, distribuidoras))
    ws = repro.WorksheetFalsa(preexistentes=[("Ferreteria %d" % i, "Calle %d" % i)
                                             for i in range(1, 5)])
    out["done"] = _correr(app, "Ciudad Ya Trabajada", gmaps=gmaps, ws=ws)

    # 4. Detenida por el operador a mitad.
    out["cancelado"] = _correr(app, "Ciudad Detenida", cancelar_en=2)

    # 5. Interrumpida por SIGTERM (redespliegue), que NO es lo mismo.
    out["interrumpido"] = _correr(app, "Ciudad Interrumpida", cancelar_en=2,
                                  por_senal=True)

    # 6. Fallo de escritura en Sheets.
    out["error"] = _correr(app, "Ciudad Con Error",
                           ws=RuntimeError("cuota de Sheets agotada (simulado)"))

    # 7. Tope de gasto: un limite respetado, no un fallo.
    out["presupuesto_agotado"] = _correr(app, "Ciudad Al Tope", tope=3)

    # 8. Ciudad sin un solo resultado: `done` legitimo con cero filas.
    vacio = repro.GmapsFalso(repro._catalogo([], []))
    out["done_vacia"] = _correr(app, "Ciudad Vacia", gmaps=vacio)

    # 9. Recargar tras un reinicio: memoria e historia en disco se separan.
    out["recarga_tras_reinicio"] = _tras_reinicio(app, out["running"][0])

    return out


def _corrida_a_medias(app):
    """El estado tal como esta A MITAD de corrida, no reconstruido al terminar."""
    instantanea = {}
    gmaps = repro.GmapsFalso(repro._catalogo(_negocios("Ferreteria", 6),
                                             _negocios("Distribuidora", 3)))
    places_original = gmaps.places
    visto = {"n": 0}

    def places(*a, **kw):
        visto["n"] += 1
        r = places_original(*a, **kw)
        if visto["n"] == 4 and not instantanea:
            with app._import_lock:
                instantanea.update(app._import_job)
        return r

    gmaps.places = places
    _correr(app, "Ciudad En Marcha", gmaps=gmaps)
    return (instantanea, None)


def _tras_reinicio(app, estado_vivo):
    """Lo que el panel responde cuando el contenedor se reinicio a media corrida.

    El hilo es `daemon=True`: el trabajo muere. La memoria vuelve a `idle` y lo
    unico que sabe que hubo una corrida es el registro en disco. Aqui es donde las
    dos fuentes se pueden separar, y por eso el plan lo pide aparte.
    """
    persistido = dict(estado_vivo)
    persistido["status"] = "interrumpido"
    app._guardar_estado_importador(persistido)
    app._import_job = app._nuevo_import_job("", status="idle")

    cliente = app.app.test_client()
    return (cliente.get("/api/importador/estado").get_json(), None)


# ───────────────────────── lectura de la pantalla ─────────────────────────

LEER_PANTALLA = """(d) => {
  rematar(d);
  const t = (id) => (document.getElementById(id) || {}).textContent || '';
  const caja = document.getElementById('result-box');
  return {
    titular_nuevos: t('s-nuevos'),
    aprobados:      t('s-encontrados'),
    duplicados:     t('s-duplicados'),
    descartados:    t('s-descartados'),
    medidor_llamadas: t('m-llamadas'),
    medidor_ahorro:   t('m-ahorro'),
    titulo:         t('result-titulo'),
    detalle:        t('result-detalle'),
    icono:          t('result-icono'),
    clase:          caja ? caja.className : '',
    rol:            caja ? caja.getAttribute('role') : '',
  };
}"""


LEER_EN_MARCHA = """(d) => {
  pintarEstado(d);
  const t = (id) => (document.getElementById(id) || {}).textContent || '';
  const caja = document.getElementById('result-box');
  return {
    titular_nuevos: t('s-nuevos'), aprobados: t('s-encontrados'),
    duplicados: t('s-duplicados'), descartados: t('s-descartados'),
    medidor_llamadas: t('m-llamadas'), medidor_ahorro: t('m-ahorro'),
    medidor_llamadas: t('m-llamadas'), medidor_ahorro: t('m-ahorro'),
    titulo: t('prog-label'), detalle: t('prog-fase'), icono: '',
    clase: caja ? caja.className : '', rol: caja ? caja.getAttribute('role') : '',
  };
}"""


# Que titulo debe llevar el aviso de Telegram segun como acabo la corrida. Los
# estados que NO estan aqui (idle, running) no notifican: no hay nada que avisar.
TITULO_ESPERADO = {
    "done": "Completado",
    "cancelado": "DETENIDO",
    "interrumpido": "DETENIDO",
    "error": "FALLÓ",
    "presupuesto_agotado": "TOPE DE GASTO",
}


# Escenarios en los que NO hay corrida que termine, asi que no hay nada que avisar:
# el reposo, la instantanea de media corrida, y la recarga tras un reinicio -- que
# lee un registro de disco, no ejecuta al worker. Exigirles aviso seria inventar un
# fallo; NO exigirselo a los demas seria tragarse una regresion del notificador.
SIN_AVISO = {"idle", "running", "recarga_tras_reinicio"}


def _veredicto(estado, pantalla, aviso, escenario=""):
    """¿La pantalla (y Telegram) afirman algo que el backend no dice?"""
    fallos = []
    st = estado["status"]

    if st == "idle":
        # En reposo tambien se puede mentir, y de la peor manera: enseñando los
        # numeros de la corrida ANTERIOR como si fueran de esta. Si aqui no se
        # comprueba nada, el veredicto verde de `idle` no significa nada.
        if pantalla["clase"] != "oculta":
            fallos.append("en reposo la fila de contadores esta VISIBLE")
        rancios = {k: pantalla[k] for k in
                   ("titular_nuevos", "aprobados", "duplicados", "descartados")
                   if pantalla[k] not in ("0", "")}
        if rancios:
            fallos.append(f"en reposo arrastra cifras de otra corrida: {rancios}")
    else:
        for campo, clave, etiqueta in (
                ("titular_nuevos", "nuevos_en_sheet", "el titular"),
                ("aprobados",      "encontrados",     "«Aprobados»"),
                ("duplicados",     "duplicados",      "«Ya estaban»"),
                ("descartados",    "descartados",     "«Descartados»")):
            if pantalla[campo] != str(estado[clave]):
                fallos.append(
                    f"{etiqueta} dice {pantalla[campo]!r} y el backend tiene "
                    f"{clave}={estado[clave]}")

    # T2.5 — el medidor de gasto vivo tras la extraccion del PR #43. Se lee del
    # backend, asi que si el JS extraido dejo de leer los campos del `medidor`, el
    # operador ve "0 busquedas" mientras Google factura.
    med = (estado.get("medidor") or {})
    if st != "idle" and med:
        esperado_ts = str(med.get("text_search", 0))
        esperado_pd = str(med.get("place_details", 0))
        texto = pantalla.get("medidor_llamadas", "")
        if esperado_ts not in texto or esperado_pd not in texto:
            fallos.append(
                f"el medidor dice {texto!r} y el backend cobro "
                f"{esperado_ts} busquedas + {esperado_pd} detalles")

    celebra = "✅" in pantalla["icono"] or "exito" in pantalla["clase"]
    if celebra and st != "done":
        fallos.append(f"celebra con {pantalla['icono']!r} una corrida en estado {st!r}")
    if st == "error" and pantalla["rol"] != "alert":
        fallos.append("un fallo no interrumpe al lector (role != alert)")
    if st in ("cancelado", "interrumpido", "presupuesto_agotado") \
            and "error" in pantalla["clase"]:
        fallos.append(f"presenta {st!r} como si fuera un error")

    esperado = "" if escenario in SIN_AVISO else TITULO_ESPERADO.get(st, "")
    if esperado and aviso is None:
        # El notificador se traga sus excepciones (app.py) y solo las imprime. Sin
        # esta rama, una regresion ahi se leeria igual que "este estado no avisa".
        fallos.append(f"Telegram NO llego a construirse para un estado {st!r}")
    elif aviso is not None:
        titulo = aviso.splitlines()[0] if aviso else ""
        if esperado and esperado not in titulo:
            fallos.append(f"Telegram titula {titulo!r} para un estado {st!r}")
        if f"<b>Nuevos en la hoja:</b> {estado['nuevos_en_sheet']}" not in aviso:
            fallos.append("Telegram no publica el mismo `nuevos_en_sheet` que el panel")

    return fallos


def main():
    argv = sys.argv[1:]
    contra = None
    if "--contra" in argv:
        i = argv.index("--contra")
        if i + 1 >= len(argv):
            raise SystemExit("--contra necesita una URL detras. Ej: --contra https://…")
        contra = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    # Un flag mal escrito NO se descarta en silencio: sin esto, `--contras https://x`
    # dejaba `contra` a None y la URL acababa de nombre de directorio.
    desconocidos = [a for a in argv if a.startswith("--")]
    if desconocidos:
        raise SystemExit(f"Opcion desconocida: {', '.join(desconocidos)}")
    sueltos = argv
    destino = Path(sueltos[0]) if sueltos else \
        RAIZ / "docs" / "investigacion" / "estados-2026-09-17"
    destino.mkdir(parents=True, exist_ok=True)

    servidor = None
    if contra:
        casos = _casos_guardados()
        base = contra.rstrip("/")
        print(f"Recorriendo los estados contra el front-end DESPLEGADO: {base}")
        print("Los estados NO se provocan aqui: son los que produjo el backend local.\n")
    else:
        import app as panel
        import medir_cls
        medir_cls.verificar_sin_credenciales()
        _ORIGINAL["fn"] = panel._enviar_telegram_importador

        print("Provocando los siete estados contra el backend real…\n")
        casos = escenarios(panel)

        servidor = make_server("127.0.0.1", PUERTO, panel.app)
        hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
        hilo.start()
        base = f"http://127.0.0.1:{PUERTO}"

    import verificar_importador as arnes
    from playwright.sync_api import sync_playwright

    # El token se comprueba ANTES de lanzar Chromium: un `return` temprano entre el
    # `launch()` y el `try/finally` dejaba el navegador sin cerrar.
    tok = os.environ.get("PANEL_DASHBOARD_TOKEN") if contra else None
    if contra and not tok:
        print("FALTA PANEL_DASHBOARD_TOKEN: sin token el panel no abre. Sin medicion.")
        return NO_MEDIDO

    filas, total_fallos = [], 0
    with sync_playwright() as p:
        navegador = p.chromium.launch()
        try:
            for nombre, (estado, aviso) in casos.items():
                pagina = arnes._pagina(navegador, estado=estado)
                if tok:
                    # El panel desplegado es fail-closed: sin la cabecera no sirve
                    # ni el HTML. El token no se imprime en ningun momento.
                    pagina.set_extra_http_headers({"X-Dashboard-Token": tok})
                pagina.goto(f"{base}/importador", wait_until="load")
                pagina.wait_for_selector(".chip-ciudad", timeout=15000)
                if estado["status"] == "idle":
                    pantalla = _pantalla_en_reposo(arnes, pagina)
                elif estado["status"] == "running":
                    pantalla = arnes.ev(pagina, LEER_EN_MARCHA, estado)
                else:
                    pantalla = arnes.ev(pagina, LEER_PANTALLA, estado)
                pagina.screenshot(path=str(destino / f"{nombre}.png"), full_page=True)

                fallos = _veredicto(estado, pantalla, aviso, escenario=nombre)
                total_fallos += len(fallos)
                filas.append((nombre, estado, pantalla, aviso, fallos))

                pagina.close()

                marca = "MIENTE " if fallos else "COINCIDE"
                print(f"  {marca}  {nombre:22} "
                      f"nuevos={estado['nuevos_en_sheet']!s:>3} "
                      f"aprobados={estado['encontrados']!s:>3} "
                      f"pantalla={pantalla['titular_nuevos']!s:>3}")
                for f in fallos:
                    print(f"            └─ {f}")
        finally:
            navegador.close()
            if servidor is not None:
                servidor.shutdown()

    (destino / "estados.json").write_text(json.dumps(
        [{"estado": n, "backend": e, "pantalla": p, "telegram": a, "fallos": f}
         for n, e, p, a, f in filas], ensure_ascii=False, indent=2, default=str),
        encoding="utf-8")

    print(f"\n{len(filas)} estados recorridos · {total_fallos} afirmaciones falsas")
    print(f"Capturas y datos en {destino}")
    return 1 if total_fallos else 0


NO_MEDIDO = 3


def _casos_guardados():
    """Los estados que ya produjo el backend local, para dárselos a otra pantalla."""
    ruta = RAIZ / "docs" / "investigacion" / "estados-2026-09-17" / "estados.json"
    if not ruta.exists():
        raise SystemExit("Falta estados.json: corre primero la auditoria local.")
    guardado = json.loads(ruta.read_text(encoding="utf-8"))
    return {e["estado"]: (e["backend"], e["telegram"]) for e in guardado}


def _pantalla_en_reposo(arnes, pagina):
    return arnes.ev(pagina, """() => {
      const t = (id) => (document.getElementById(id) || {}).textContent || '';
      const fila = document.getElementById('stats-row');
      return {titular_nuevos: t('s-nuevos'), aprobados: t('s-encontrados'),
              duplicados: t('s-duplicados'), descartados: t('s-descartados'),
              medidor_llamadas: t('m-llamadas'), medidor_ahorro: t('m-ahorro'),
              titulo: '', detalle: '', icono: '', rol: '',
              clase: fila && fila.hasAttribute('hidden') ? 'oculta' : 'VISIBLE'};
    }""")


if __name__ == "__main__":
    sys.exit(main())
