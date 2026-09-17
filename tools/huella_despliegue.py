#!/usr/bin/env python
"""Fecha el codigo que sirve el VPS por su comportamiento, no por su version.

`/salud` es deliberadamente mudo -- no dice version, ni commit, ni hostname. Es una
decision de seguridad del Plan 5 y no se revierte. Asi que la unica forma de saber si
un fix esta desplegado es preguntarle al panel por un **rasgo que solo existe despues
de ese fix**.

Cada marcador de abajo se agrego en un commit conocido. El mas moderno que el panel
responda da una **cota inferior** de lo que corre. No prueba que corra `main` exacto:
prueba que corre algo **igual o posterior** al commit de ese marcador.

Uso:
    python tools/huella_despliegue.py https://panelnioval.duckdns.org --token <valor>

El token no se imprime nunca, ni entero ni en fragmentos.
"""
from __future__ import annotations

import argparse
import json
import sys

import requests

# Marcadores ordenados de mas viejo a mas nuevo. `clave` es un campo que el endpoint
# `/api/importador/estado` empezo a devolver en `desde`.
MARCADORES = [
    ("encontrados",     "pre-ae0e1c9", "El contador unico que ya existia antes del fix"),
    ("nuevos_en_sheet", "ae0e1c9",     "B1: filas REALMENTE escritas, separado de los aprobados"),
    ("duplicados",      "ae0e1c9",     "B2/B3: los que ya estaban en la hoja"),
    ("descartados",     "ae0e1c9",     "B15: rechazados por filtros, sin inflar"),
    ("fraccion",        "ae0e1c9",     "B6: progreso continuo, no 0/50/100"),
    ("fase",            "ae0e1c9",     "B6: que esta haciendo ahora mismo"),
    ("medidor",         "PR #38",      "Tope de gasto de Places (posterior al fix)"),
]


def consultar(base: str, ruta: str, token: str | None):
    cab = {"X-Dashboard-Token": token} if token else {}
    return requests.get(f"{base.rstrip('/')}{ruta}", headers=cab, timeout=25)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--token", default=None)
    args = ap.parse_args()

    print(f"Panel: {args.url}")
    print(f"Token: {'presente' if args.token else 'AUSENTE'}\n")

    r = consultar(args.url, "/api/importador/estado", args.token)
    print(f"GET /api/importador/estado -> HTTP {r.status_code}")

    if r.status_code == 401 or r.status_code == 403:
        print("  El panel exige token y el que se paso no sirve. Sin token no hay huella.")
        return 2
    if r.status_code != 200:
        print(f"  Respuesta inesperada. Cuerpo (200 primeros): {r.text[:200]!r}")
        return 2

    try:
        datos = r.json()
    except json.JSONDecodeError:
        print(f"  No es JSON. Cuerpo (200 primeros): {r.text[:200]!r}")
        return 2

    print(f"  Claves devueltas: {len(datos)}\n")

    presentes, ausentes = [], []
    for clave, desde, que_es in MARCADORES:
        hay = clave in datos
        (presentes if hay else ausentes).append((clave, desde, que_es))
        print(f"  {'SI' if hay else 'NO':2}  {clave:16} (desde {desde})  {que_es}")

    print()
    del_fix = [c for c, d, _ in MARCADORES if d == "ae0e1c9"]
    faltan_del_fix = [c for c in del_fix if c not in datos]

    if faltan_del_fix:
        print("VEREDICTO: H1 CONFIRMADA -- el VPS sirve codigo ANTERIOR a ae0e1c9.")
        print(f"  Faltan del fix de agosto: {', '.join(faltan_del_fix)}")
        print("  El problema es de DESPLIEGUE, no de codigo.")
        return 1

    tiene_posterior = any(c in datos for c, d, _ in MARCADORES if d == "PR #38")
    print("VEREDICTO: H1 DESCARTADA -- los 5 marcadores del fix de agosto estan presentes.")
    if tiene_posterior:
        print("  Y ademas hay un marcador POSTERIOR al fix: el codigo servido es mas")
        print("  reciente que ae0e1c9, no solo igual.")
    print("  El VPS tiene el fix. Si el sintoma sigue vivo, es H2 (regresion) o H3")
    print("  (caso residual). Sigue T3.2.")

    # El estado en si mismo es informacion util para T3.1: si hay una corrida viva,
    # los numeros de abajo son los que el operador esta viendo ahora.
    interesantes = ("status", "ciudad", "encontrados", "nuevos_en_sheet",
                    "duplicados", "descartados")
    print("\nEstado actual del importador en produccion:")
    for k in interesantes:
        if k in datos:
            print(f"  {k:16} = {datos[k]!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
