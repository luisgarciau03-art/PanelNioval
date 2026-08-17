"""Smoke test post-deploy contra la URL productiva del panel.

Sin costo de LLM. Verifica códigos 200 y shape JSON de los endpoints clave.

Uso:
    python tools/smoke_panel.py https://panelnioval.duckdns.org --token TOKEN
"""
import argparse
import sys

import requests


def _get(base, path, token):
    headers = {"X-Dashboard-Token": token} if token else {}
    return requests.get(f"{base.rstrip('/')}{path}", headers=headers, timeout=20)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--token", default=None, help="PANEL_DASHBOARD_TOKEN si el panel lo exige")
    args = ap.parse_args()

    fallos = []

    def chequear(nombre, path, esperar_json=None):
        try:
            r = _get(args.url, path, args.token)
        except Exception as e:
            fallos.append(f"{nombre}: excepción {e}")
            return
        if r.status_code != 200:
            fallos.append(f"{nombre}: HTTP {r.status_code}")
            return
        if esperar_json:
            try:
                data = r.json()
            except Exception:
                fallos.append(f"{nombre}: respuesta no es JSON")
                return
            if esperar_json not in data:
                fallos.append(f"{nombre}: falta clave '{esperar_json}' en JSON")
                return
        print(f"  OK  {nombre} ({path})")

    print(f"Smoke test contra {args.url}")
    chequear("home", "/")
    chequear("formulario", "/formulario")
    chequear("siguiente", "/api/formulario/siguiente", esperar_json="fin")
    chequear("envios", "/api/catalogo/envios", esperar_json="envios")
    chequear("worker-estado", "/api/catalogo/worker-estado", esperar_json="vivo")

    if fallos:
        print("\nFALLOS:")
        for f in fallos:
            print("  -", f)
        sys.exit(1)
    print("\nTodo OK ✅")


if __name__ == "__main__":
    main()
