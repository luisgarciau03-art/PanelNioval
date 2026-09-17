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
    PANEL_DASHBOARD_TOKEN=<valor> python tools/huella_despliegue.py https://panelnioval.duckdns.org

El token no se imprime nunca, ni entero ni en fragmentos.

**Codigos de salida, que son tres y no dos:**

    0  al dia      1  rancio (falta algo del arreglo)
    2  no se pudo interpretar la respuesta      3  no se pudo medir

Confundir "no pude comprobarlo" con "esta al dia" convertiria esta herramienta en lo
que vino a evitar.

La decision vive en `veredicto()`, que es pura y no toca la red: asi puede probarse
(`tests/test_huella_despliegue.py`) en las dos direcciones, que es lo unico que hace
creible un barrido.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from urllib.parse import urlsplit

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

# Tercer y cuarto resultado, distintos de 0 (al dia) y de 1 (rancio).
NO_INTERPRETABLE = 2
NO_MEDIDO = 3


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


def _sirve(datos: dict[str, object], clave: str) -> bool:
    """¿El panel publica este marcador con un valor utilizable?

    Comprobar solo `clave in datos` no basta: un campo presente con valor `None` es
    un marcador que NO sirve, y darlo por bueno es exactamente el "fallo de medicion
    que se lee como exito" que esta herramienta existe para evitar. Hoy el endpoint
    nunca devuelve `None` en estos campos, pero un cambio de una linea en `app.py`
    lo haria sin que nada se enterara.

    `0`, `''` y `{}` SI valen: son valores legitimos de un importador en reposo.
    """
    return datos.get(clave) is not None


def veredicto(datos: dict[str, object]) -> Veredicto:
    """Decide sobre el cuerpo de `/api/importador/estado`. No toca la red."""
    del_arreglo = [c for c, desde, _ in MARCADORES if desde == ARREGLO]
    return Veredicto(
        rancio=bool([c for c in del_arreglo if not _sirve(datos, c)]),
        faltantes=[c for c in del_arreglo if not _sirve(datos, c)],
        presentes=[c for c, _, _ in MARCADORES if _sirve(datos, c)],
        # Un marcador que nacio DESPUES del arreglo prueba que lo servido es
        # estrictamente posterior, no solo "igual o posterior".
        posterior_al_arreglo=any(
            _sirve(datos, c) for c, desde, _ in MARCADORES
            if desde not in (ARREGLO, "pre-" + ARREGLO)
        ),
    )


def _pista(respuesta: requests.Response, con_cuerpo: bool) -> str:
    """Que decir de una respuesta que no se pudo interpretar.

    Por defecto, su forma -- no su contenido: el cuerpo puede venir de un proxy o un
    WAF intermedio y no hay razon para volcarlo a la terminal por rutina.
    """
    forma = (f"Content-Type={respuesta.headers.get('Content-Type', '?')!r}, "
             f"{len(respuesta.content)} bytes")
    if not con_cuerpo:
        return forma + ". Con --cuerpo se vuelcan los primeros 200 caracteres."
    return forma + f". Cuerpo (200 primeros): {respuesta.text[:200]!r}"


def consultar(base: str, ruta: str, token: str | None) -> requests.Response:
    """Una peticion, sin seguir redirecciones.

    `X-Dashboard-Token` es una cabecera NUESTRA, y `requests` solo limpia
    `Authorization` y `Cookie` al cambiar de host en un 30x: una cabecera propia se
    reenvia intacta a donde diga el `Location`. Con DNS dinamico eso no es teorico
    -- quien controle el nombre devuelve un 302 y se queda con el token --, y este
    endpoint no tiene ninguna razon legitima para redirigir.
    """
    cab = {"X-Dashboard-Token": token} if token else {}
    return requests.get(f"{base.rstrip('/')}{ruta}", headers=cab, timeout=25,
                        allow_redirects=False)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--token", default=None,
                    help="Por defecto se toma de PANEL_DASHBOARD_TOKEN. Pasarlo aqui lo "
                         "deja visible en `ps` y en el historial del shell.")
    ap.add_argument("--cuerpo", action="store_true",
                    help="Volcar el cuerpo de la respuesta cuando no se pueda interpretar. "
                         "Apagado por defecto: puede venir de un proxy o WAF intermedio.")
    args = ap.parse_args()

    token = args.token or os.environ.get("PANEL_DASHBOARD_TOKEN")

    print(f"Panel: {args.url}")
    print(f"Token: {'presente' if token else 'AUSENTE'}\n")

    try:
        r = consultar(args.url, "/api/importador/estado", token)
    except requests.exceptions.RequestException as e:
        print(f"NO SE PUDO MEDIR: {type(e).__name__}.")
        print("  Ni al dia ni rancio: sin medicion. Revisa red, DNS o el nombre del host.")
        return NO_MEDIDO

    print(f"GET /api/importador/estado -> HTTP {r.status_code}")

    if 300 <= r.status_code < 400:
        destino = urlsplit(r.headers.get("Location", "")).netloc or "(sin Location)"
        print(f"  REDIRECCION a {destino}, y NO se sigue: la cabecera del token viajaria")
        print("  con ella. Este endpoint no deberia redirigir; averigua por que lo hace.")
        return NO_INTERPRETABLE
    if r.status_code in (401, 403):
        print("  El panel exige token y el que se paso no sirve. Sin token no hay huella.")
        return NO_INTERPRETABLE
    if r.status_code != 200:
        print(f"  Respuesta inesperada. {_pista(r, args.cuerpo)}")
        return NO_INTERPRETABLE

    try:
        datos = r.json()
    except json.JSONDecodeError:
        print(f"  No es JSON. {_pista(r, args.cuerpo)}")
        return NO_INTERPRETABLE

    # JSON valido pero que no es un objeto (`null`, un numero, `true`) no revienta en
    # `.json()`: revienta dos lineas mas abajo, con traceback en vez de mensaje.
    if not isinstance(datos, dict):
        print(f"  JSON valido pero no es un objeto ({type(datos).__name__}). "
              f"{_pista(r, args.cuerpo)}")
        return NO_INTERPRETABLE

    print(f"  Claves devueltas: {len(datos)}\n")
    for clave, desde, que_es in MARCADORES:
        print(f"  {'SI' if _sirve(datos, clave) else 'NO':2}  {clave:16} "
              f"(desde {desde})  {que_es}")

    v = veredicto(datos)
    print()

    if v.rancio:
        print(f"VEREDICTO: H1 CONFIRMADA -- el VPS sirve codigo ANTERIOR a {ARREGLO}.")
        print(f"  Faltan del fix de agosto: {', '.join(v.faltantes)}")
        print("  El problema es de DESPLIEGUE, no de codigo. Ver docs/RUNBOOK.md,")
        print("  seccion 'Como saber que version sirve el VPS'.")
        return 1

    print(f"VEREDICTO: H1 DESCARTADA -- {len(v.presentes)} marcadores confirmados, "
          f"y los 5 del arreglo estan entre ellos.")
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
