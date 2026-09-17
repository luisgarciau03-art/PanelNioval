"""Fase 0 del ADR `2026-09-15-ruta-de-telefono-places`: medir antes de migrar.

**No migra nada. No escribe nada. No toca la hoja.** Hace las mismas busquedas por
los dos caminos —Places API legacy, que es lo que corre hoy, y Places API (New)— y
compara las respuestas. Coste aproximado: **$0.46 por ciudad**.

Contesta las dos preguntas que el ADR puso como condicion:

  1. **¿La clave de deduplicacion sale igual por los dos caminos?**
     `_clave_contacto` (`app.py`) es `f"{nombre}|{direccion}"`, y se calcula en tres
     sitios que deben coincidir **caracter a caracter**: el prefiltro, la exportacion
     y la reconstruccion desde la hoja. Si la API New formatea el nombre o la
     direccion distinto, la clave nueva no casa con ninguna de las que la hoja ya
     tiene, y el importador **duplica todo lo ya importado sin lanzar una sola
     excepcion**. No existe ninguna guarda que lo detecte.

     Se compara contra la respuesta **legacy**, no contra la hoja, porque las claves
     de la hoja se escribieron desde respuestas legacy. Asi no hacen falta
     credenciales de Sheets, y se mide exactamente lo que importa.

     ⚠️ **Por debajo del 99 % de coincidencia, el ADR cancela la migracion.**

  2. **¿Que porcentaje de negocios trae `nationalPhoneNumber`?** Eso cierra **CE1**,
     el gate que T2.1 dejo en rojo por no poder medirlo sin llamar a Google.

La comparacion es pura y esta aparte del transporte, para que se pueda probar en las
dos direcciones sin red (`tests/test_comparar_places_new.py`).

Uso:
    GMAPS_API_KEY=<valor> python tools/comparar_places_new.py "Puebla"

Elegir una ciudad **ya trabajada**: son las que tienen claves en la hoja contra las
que la migracion tendria que casar.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import requests

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

os.environ.setdefault("PANEL_AUTH_DESACTIVADA", "1")

# El endpoint y el field mask de la API New. Los campos salen de la documentacion
# oficial consultada en T2.2 (`docs/investigacion/2026-09-15-places-new-field-mask.md`):
# `nationalPhoneNumber`, `rating` y `userRatingCount` caen en el mismo SKU
# (Text Search Enterprise), asi que pedir el telefono no sube la tarifa.
URL_NEW = "https://places.googleapis.com/v1/places:searchText"
FIELD_MASK = ",".join([
    "places.id",
    "places.displayName",
    "places.formattedAddress",
    "places.rating",
    "places.userRatingCount",
    "places.nationalPhoneNumber",
    "nextPageToken",
])


def exigir_clave() -> str:
    """Sin clave no se mide. **Nunca** se abre con un valor por defecto."""
    clave = os.environ.get("GMAPS_API_KEY")
    if not clave:
        raise SystemExit(
            "Falta GMAPS_API_KEY. Esta herramienta llama a Google y cuesta dinero: "
            "sin clave no corre, y no hay valor por defecto.")
    return clave


def clave_desde_legacy(lugar: dict) -> str:
    """La clave tal como la construye hoy el importador desde una respuesta legacy."""
    import app
    return app._clave_contacto(lugar.get("name", ""), lugar.get("formatted_address", ""))


def clave_desde_new(lugar: dict) -> str:
    """La misma clave, construida desde una respuesta de la API New.

    `displayName` es un objeto con `text`; `formattedAddress` es plano. Si alguno
    llega vacio, la clave sale igualmente y la comparacion la marca como
    discrepancia -- que es lo correcto: un campo ausente ES el defecto que se busca.
    """
    import app
    nombre = (lugar.get("displayName") or {}).get("text", "")
    return app._clave_contacto(nombre, lugar.get("formattedAddress", ""))


def comparar(lugares_legacy: list[dict], lugares_new: list[dict]) -> dict:
    """Empareja por Place ID y compara la clave de deduplicacion.

    Solo cuentan los emparejados: un negocio que devuelve una API y la otra no, no
    dice nada sobre el formateo de la clave. Se reportan aparte porque una
    diferencia grande de cobertura seria un hallazgo por si misma.
    """
    por_id_legacy = {l.get("place_id"): l for l in lugares_legacy if l.get("place_id")}
    por_id_new = {n.get("id"): n for n in lugares_new if n.get("id")}
    comunes = [pid for pid in por_id_legacy if pid in por_id_new]

    iguales, discrepancias = 0, []
    for pid in comunes:
        cl = clave_desde_legacy(por_id_legacy[pid])
        cn = clave_desde_new(por_id_new[pid])
        if cl == cn:
            iguales += 1
        else:
            discrepancias.append({"place_id": pid, "legacy": cl, "new": cn})

    return {
        "emparejados": len(comunes),
        "claves_iguales": iguales,
        # None, no 0: "no pude medirlo" y "todas mal" son resultados distintos, y
        # confundirlos cancelaria la migracion por una muestra vacia.
        "tasa_coincidencia": (iguales / len(comunes)) if comunes else None,
        "discrepancias": discrepancias,
        "solo_en_legacy": sorted(p for p in por_id_legacy if p not in por_id_new),
        "solo_en_new": sorted(p for p in por_id_new if p not in por_id_legacy),
    }


def tasa_con_telefono(lugares_new: list[dict]) -> dict:
    """CE1: cuantos negocios trae Google con telefono, de verdad y no por proxy."""
    total = len(lugares_new)
    con = sum(1 for l in lugares_new if (l.get("nationalPhoneNumber") or "").strip())
    return {
        "total": total,
        "con_telefono": con,
        "sin_telefono": total - con,
        "tasa_sin_telefono": ((total - con) / total) if total else None,
    }


# ─────────────────────────── transporte (esto SI llama) ───────────────────────────

def buscar_new(consulta: str, clave: str, paginas: int = 3) -> list[dict]:
    lugares, token = [], None
    for _ in range(paginas):
        cuerpo = {"textQuery": consulta, "languageCode": "es"}
        if token:
            cuerpo["pageToken"] = token
        r = requests.post(URL_NEW, json=cuerpo, timeout=25, allow_redirects=False,
                          headers={"X-Goog-Api-Key": clave,
                                   "X-Goog-FieldMask": FIELD_MASK})
        r.raise_for_status()
        datos = r.json()
        lugares.extend(datos.get("places", []))
        token = datos.get("nextPageToken")
        if not token:
            break
    return lugares


def buscar_legacy(consulta: str, clave: str, paginas: int = 3) -> list[dict]:
    import googlemaps
    cliente = googlemaps.Client(key=clave)
    lugares, resp = [], None
    for _ in range(paginas):
        resp = (cliente.places(query=consulta, language="es", type="establishment")
                if resp is None else
                cliente.places(query=consulta, language="es",
                               page_token=resp["next_page_token"]))
        lugares.extend(resp.get("results", []))
        if "next_page_token" not in resp:
            break
    return lugares


def main() -> int:
    if len(sys.argv) < 2:
        raise SystemExit('Uso: python tools/comparar_places_new.py "Nombre de la ciudad"')
    ciudad = sys.argv[1]
    clave = exigir_clave()

    print(f"Ciudad: {ciudad}")
    print("NO se escribe nada: ni en la hoja, ni en la cache, ni en el estado.\n")

    todos_legacy, todos_new = [], []
    for categoria in ("Ferreterías", "Distribuidoras Ferreterías"):
        consulta = f"{categoria} en {ciudad}"
        print(f"  consultando: {consulta!r}")
        todos_legacy.extend(buscar_legacy(consulta, clave))
        todos_new.extend(buscar_new(consulta, clave))

    cmp_ = comparar(todos_legacy, todos_new)
    tel = tasa_con_telefono(todos_new)

    print(f"\n  legacy: {len(todos_legacy)} lugares · new: {len(todos_new)} lugares")
    print(f"  emparejados por Place ID: {cmp_['emparejados']}")

    tasa = cmp_["tasa_coincidencia"]
    if tasa is None:
        print("\n  NO SE PUDO MEDIR: ningun Place ID en comun. Sin veredicto.")
        return 3
    print(f"  claves identicas: {cmp_['claves_iguales']} ({tasa*100:.1f} %)")

    for d in cmp_["discrepancias"][:10]:
        print(f"    legacy: {d['legacy']!r}")
        print(f"       new: {d['new']!r}")
    if len(cmp_["discrepancias"]) > 10:
        print(f"    … y {len(cmp_['discrepancias']) - 10} mas")

    print(f"\n  CE1 — sin telefono en Google: {tel['sin_telefono']} de {tel['total']}"
          + (f" ({tel['tasa_sin_telefono']*100:.1f} %)" if tel["total"] else ""))

    salida = RAIZ / "docs" / "investigacion" / f"fase0-{ciudad.lower().replace(' ', '-')}.json"
    salida.write_text(json.dumps({"comparacion": cmp_, "telefono": tel},
                                 ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n  Datos en {salida}")

    if tasa < 0.99:
        print("\n  VEREDICTO: por debajo del 99 %. El ADR CANCELA la migracion:")
        print("  la clave de deduplicacion no casa y la hoja se llenaria de duplicados.")
        return 1
    print("\n  VEREDICTO: la clave casa. Se cumple la condicion (a) del ADR.")
    print("  Falta la (b): tasa de sin-telefono >= 30 % para migrar ahora.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
