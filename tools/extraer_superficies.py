"""T4.3 - Saca las tres superficies de app.py a templates/ y static/.

Refactor PRESERVADOR DE COMPORTAMIENTO: copia, no mejora. No cambia ni un
pixel; solo cambia donde vive el codigo.

Lo unico que se reescribe son las dos etiquetas que antes incrustaban CSS y JS
y ahora los enlazan con ``url_for``. El contenido de esos bloques se copia
byte a byte y el script lo COMPRUEBA antes de escribir nada.

`app.py` es 100% CRLF: se lee y escribe con ``newline=''`` para no convertir
saltos de linea por accidente.

Uso:
    python tools/extraer_superficies.py            # aplica
    python tools/extraer_superficies.py --simular  # solo informa
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

# constante en app.py -> nombre base de plantilla / css / js
SUPERFICIES = [
    ("HTML", "dashboard"),
    ("FORMULARIO_HTML", "formulario"),
    ("IMPORTADOR_HTML", "importador"),
]


def leer(ruta: Path) -> str:
    with open(ruta, "r", encoding="utf-8", newline="") as f:
        return f.read()


def escribir(ruta: Path, texto: str) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with open(ruta, "w", encoding="utf-8", newline="") as f:
        f.write(texto)


def cortar_literal(fuente: str, constante: str) -> tuple[str, str]:
    """Devuelve (bloque completo incluido el `X = r\"\"\"...\"\"\"`, cuerpo HTML)."""
    apertura = f'{constante} = r"""'
    i = fuente.index(apertura)
    ini_cuerpo = i + len(apertura)
    fin_cuerpo = fuente.index('"""', ini_cuerpo)
    return fuente[i : fin_cuerpo + 3], fuente[ini_cuerpo:fin_cuerpo]


def main() -> int:
    simular = "--simular" in sys.argv
    ruta_app = RAIZ / "app.py"
    fuente = leer(ruta_app)
    original = fuente

    for constante, nombre in SUPERFICIES:
        bloque, cuerpo = cortar_literal(fuente, constante)

        # --- CSS: el unico <style> de la superficie ---
        m_css = re.search(r"[ \t]*<style>(.*?)</style>", cuerpo, re.S)
        if not m_css:
            raise SystemExit(f"{nombre}: no se encontro <style>")
        css = m_css.group(1)

        # --- JS: el <script> SIN src (el de Chart.js por CDN se queda) ---
        m_js = re.search(r"[ \t]*<script>(.*?)</script>", cuerpo, re.S)
        if not m_js:
            raise SystemExit(f"{nombre}: no se encontro <script> inline")
        js = m_js.group(1)

        # Jinja parsea la plantilla al renderizar. Si el marcado trae {{ {% o {#
        # revienta en tiempo de peticion, no al importar. Se comprueba aqui.
        resto = cuerpo.replace(m_css.group(0), "").replace(m_js.group(0), "")
        for delim in ("{{", "{%", "{#"):
            if delim in resto:
                raise SystemExit(
                    f"{nombre}: el marcado contiene '{delim}', que Jinja interpretaria. "
                    "Hay que envolverlo en {% raw %} antes de extraer."
                )

        enlace_css = (
            f"<link rel=\"stylesheet\" href=\"{{{{ url_for('static', "
            f"filename='css/{nombre}.css') }}}}\">"
        )
        enlace_js = (
            f"<script src=\"{{{{ url_for('static', "
            f"filename='js/{nombre}.js') }}}}\"></script>"
        )

        html = cuerpo.replace(m_css.group(0), enlace_css, 1)
        html = html.replace(m_js.group(0), enlace_js, 1)

        # Verificacion antes de escribir: el cuerpo, quitados los dos enlaces
        # nuevos y devueltos los bloques originales, tiene que ser identico al
        # de partida. Una sustitucion que no casa devuelve el texto igual y no
        # se queja: esto lo detecta.
        reconstruido = html.replace(enlace_css, m_css.group(0), 1).replace(
            enlace_js, m_js.group(0), 1
        )
        if reconstruido != cuerpo:
            raise SystemExit(f"{nombre}: la sustitucion no es reversible; abortado")

        print(f"{nombre}:")
        print(f"   html {len(html.splitlines()):5} lineas -> templates/{nombre}.html")
        print(f"   css  {len(css.splitlines()):5} lineas -> static/css/{nombre}.css")
        print(f"   js   {len(js.splitlines()):5} lineas -> static/js/{nombre}.js")

        if not simular:
            escribir(RAIZ / "templates" / f"{nombre}.html", html.lstrip("\r\n"))
            escribir(RAIZ / "static" / "css" / f"{nombre}.css", css.strip("\r\n") + "\r\n")
            escribir(RAIZ / "static" / "js" / f"{nombre}.js", js.strip("\r\n") + "\r\n")

        # --- quitar la constante de app.py ---
        fuente = fuente.replace(bloque + "\r\n", "", 1)
        # --- cambiar la llamada de render ---
        antes = f"render_template_string({constante})"
        despues = f"render_template('{nombre}.html')"
        if antes not in fuente:
            raise SystemExit(f"{nombre}: no se encontro {antes}")
        fuente = fuente.replace(antes, despues, 1)

    # --- el import ---
    imp_antes = "from flask import Flask, jsonify, render_template_string, request, session"
    imp_despues = "from flask import Flask, jsonify, render_template, request, session"
    if imp_antes not in fuente:
        raise SystemExit("no se encontro la linea de import esperada")
    fuente = fuente.replace(imp_antes, imp_despues, 1)

    if fuente == original:
        raise SystemExit("app.py no cambio: ninguna sustitucion caso")

    if "render_template_string" in fuente:
        raise SystemExit("queda alguna referencia a render_template_string")

    print(f"\napp.py: {len(original.splitlines())} -> {len(fuente.splitlines())} lineas")
    if not simular:
        escribir(ruta_app, fuente)
        print("escrito")
    else:
        print("(simulacion: no se escribio nada)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
