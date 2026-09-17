#!/usr/bin/env python
"""Fecha el codigo que sirve el VPS por su comportamiento, no por su version.

**Por que existe.** El bug de conteo del importador se arreglo el 2026-08-27 y el
operador lo siguio sufriendo tres semanas: el arreglo estaba en `main` y produccion
seguia sirviendo `51520f3`. No hay auto-deploy, y nadie tenia forma de notarlo.

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

La decision vive en `veredicto()`, que es pura y no toca la red: asi puede probarse
(`tests/test_huella_despliegue.py`) en las dos direcciones, que es lo unico que hace
creible un barrido.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field

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

ARREGLO = "ae0e1c9"


@dataclass
class Veredicto:
    """Que se pudo concluir del estado que devolvio el panel.

    `rancio` responde a la pregunta que importa: ¿le falta algo del arreglo?
    `faltantes` dice QUE le falta, porque un "esta rancio" sin detalle obliga a
    rediagnosticar desde cero.
    """

    rancio: bool
    faltantes: list[str] = field(default_factory=list)
    presentes: list[str] = field(default_factory=list)
    posterior_al_arreglo: bool = False


def veredicto(datos: dict) -> Veredicto:
    """Decide sobre el cuerpo de `/api/importador/estado`. No toca la red."""
    del_arreglo = [c for c, desde, _ in MARCADORES if desde == ARREGLO]
    faltantes = [c for c in del_arreglo if c not in datos]
    return Veredicto(
        rancio=bool(faltantes),
        faltantes=faltantes,
        presentes=[c for c, _, _ in MARCADORES if c in datos],
        # Un marcador que nacio DESPUES del arreglo prueba que lo servido es
        # estrictamente posterior, no solo "igual o posterior".
        posterior_al_arreglo=any(
            c in datos for c, desde, _ in MARCADORES
            if desde not in (ARREGLO, "pre-" + ARREGLO)
        ),
    )


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

    if r.status_code in (401, 403):
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
    for clave, desde, que_es in MARCADORES:
        print(f"  {'SI' if clave in datos else 'NO':2}  {clave:16} (desde {desde})  {que_es}")

    v = veredicto(datos)
    print()

    if v.rancio:
        print(f"VEREDICTO: H1 CONFIRMADA -- el VPS sirve codigo ANTERIOR a {ARREGLO}.")
        print(f"  Faltan del fix de agosto: {', '.join(v.faltantes)}")
        print("  El problema es de DESPLIEGUE, no de codigo. Ver docs/RUNBOOK.md,")
        print("  seccion 'Como saber que version sirve el VPS'.")
        return 1

    print("VEREDICTO: H1 DESCARTADA -- los 5 marcadores del fix de agosto estan presentes.")
    if v.posterior_al_arreglo:
        print("  Y ademas hay un marcador POSTERIOR al fix: el codigo servido es mas")
        print("  reciente que el arreglo, no solo igual.")
    print("  El VPS tiene el fix. Si el sintoma sigue vivo, es regresion o caso residual.")

    interesantes = ("status", "ciudad", "encontrados", "nuevos_en_sheet",
                    "duplicados", "descartados")
    print("\nEstado actual del importador en produccion:")
    for k in interesantes:
        if k in datos:
            print(f"  {k:16} = {datos[k]!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
