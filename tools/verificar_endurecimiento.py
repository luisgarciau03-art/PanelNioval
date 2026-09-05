"""Comprueba que los guardas del Plan 5 detectan el defecto que dicen detectar.

Plan 5 · T5.6. Un test que pasa con y sin el arreglo no vale nada, asi que este
arnes REINTRODUCE cada defecto a proposito y exige que la suite se ponga en
rojo. Si un guarda sigue en verde con su defecto puesto, es que no mide nada.

Es el mismo principio que las ocho herramientas de verificacion del Plan 4:
comprobado en las dos direcciones, no solo en la util.

SEGURIDAD DEL ARNES. Cada archivo se copia antes de tocarlo y se restaura en un
`finally`, comprobando el SHA-256. NO se usa `git checkout` para restaurar: eso
revierte a HEAD y se lleva por delante lo que no este commiteado.

Uso:  python tools/verificar_endurecimiento.py [--detalle]
"""
import hashlib
import pathlib
import shutil
import subprocess
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

RAIZ = pathlib.Path(__file__).resolve().parents[1]
DETALLE = "--detalle" in sys.argv

# (nombre, archivo, viejo, nuevo, tests que DEBEN ponerse en rojo)
DEFECTOS = [
    ("M2 · el reloj vuelve a ser UTC",
     "nucleo_catalogo.py",
     "    return datetime.now(TZ_MEXICO)",
     "    return datetime.now()",
     "tests/test_endurecimiento_zona_horaria.py"),

    ("M2 · app.py deja de usar el helper",
     "app.py",
     "    fecha  = nc.ahora_mexico().strftime('%d/%m/%Y')",
     "    fecha  = datetime.now().strftime('%d/%m/%Y')",
     "tests/test_endurecimiento_zona_horaria.py"),

    ("M14 · el escape se evade con un espacio delante",
     "app.py",
     "    sin_blancos = valor.lstrip().lstrip(_INVISIBLES)",
     "    sin_blancos = valor",
     "tests/test_endurecimiento_escape_formulas.py"),

    ("M14 · seguimiento deja de escapar",
     "app.py",
     "            updates.append({'range': a1, 'values': [[_valor_para_celda(value)]]})",
     "            updates.append({'range': a1, 'values': [[str(value)]]})",
     "tests/test_endurecimiento_escape_formulas.py"),

    ("M5 · el importador pierde su limite propio",
     "app.py",
     "@limiter.limit(LIMITE_IMPORTADOR)\n",
     "",
     "tests/test_endurecimiento_limites.py"),

    ("M5 · el limitador vuelve a correr antes de la auth",
     "app.py",
     "limiter.init_app(app)",
     "app.before_request(limiter._check_request_limit)",
     "tests/test_endurecimiento_limites.py"),

    ("M5 · se retira ProxyFix (todos comparten cubo)",
     "app.py",
     "app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)",
     "pass  # sin ProxyFix",
     "tests/test_endurecimiento_limites.py"),

    ("M5 · la fila 1 (encabezados) vuelve a ser escribible",
     "app.py",
     "    if fila < 2:",
     "    if fila < -999999:",
     "tests/test_endurecimiento_limites.py"),

    ("M3 · el manejador deja de encadenar al de gunicorn",
     "app.py",
     "            if callable(anterior):\n                anterior(sig, frame)\n                return",
     "            if False:\n                anterior(sig, frame)\n                return",
     "tests/test_endurecimiento_parada.py"),

    ("M3 · la senal deja de llegar al bucle",
     "app.py",
     "            _import_job['cancelado'] = True",
     "            pass",
     "tests/test_endurecimiento_parada.py"),

    ("M9 · /salud empieza a filtrar estado interno",
     "app.py",
     "    return jsonify({'ok': True})\n",
     "    return jsonify({'ok': True, 'status': _import_job.get('status')})\n",
     "tests/test_endurecimiento_salud.py"),

    ("M9 · el healthcheck pasa a usar curl (que la imagen no trae)",
     "Dockerfile",
     'CMD ["python", "-c"',
     'CMD ["curl", "-f", "http://127.0.0.1:8000/salud"]  # ["python", "-c"',
     "tests/test_endurecimiento_salud.py"),
]


def sha(ruta: pathlib.Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def en_rojo(tests: str) -> bool:
    r = subprocess.run([sys.executable, "-m", "pytest", tests, "-x", "--no-header", "-q"],
                       cwd=RAIZ, capture_output=True, text=True)
    return r.returncode != 0


def main() -> int:
    respaldo = pathlib.Path(tempfile.mkdtemp(prefix="endurecimiento_"))
    fallos, revisados = [], 0

    print(f"Arnes de verificacion del Plan 5 — {len(DEFECTOS)} defectos")
    print(f"Respaldos en {respaldo}\n")

    for nombre, archivo, viejo, nuevo, tests in DEFECTOS:
        ruta = RAIZ / archivo
        copia = respaldo / archivo.replace("/", "_")
        shutil.copy2(ruta, copia)
        antes = sha(ruta)
        revisados += 1
        try:
            texto = ruta.read_text(encoding="utf-8")
            if viejo not in texto:
                # Un patron que no casa NO es un exito: significa que el arnes
                # esta midiendo un codigo que ya no existe.
                print(f"  ??  {nombre}\n      el patron no casa: el arnes esta desactualizado")
                fallos.append((nombre, "patron no encontrado"))
                continue
            ruta.write_text(texto.replace(viejo, nuevo, 1), encoding="utf-8")
            rojo = en_rojo(tests)
            print(f"  {'OK ' if rojo else 'MAL'} {nombre}")
            if DETALLE:
                print(f"      {archivo} · {tests}")
            if not rojo:
                fallos.append((nombre, f"{tests} sigue en VERDE con el defecto puesto"))
        finally:
            shutil.copy2(copia, ruta)
            if sha(ruta) != antes:
                print(f"  !!! {archivo} NO se restauro bien — revisar {copia}")
                fallos.append((nombre, "restauracion fallida"))

    print(f"\n{revisados - len(fallos)} de {revisados} guardas detectan su defecto.")
    if fallos:
        print("\nGUARDAS QUE NO MIDEN LO QUE DICEN:")
        for nombre, motivo in fallos:
            print(f"  - {nombre}: {motivo}")
        return 1
    print("Todos los guardas se pusieron en rojo al reintroducir su defecto.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
