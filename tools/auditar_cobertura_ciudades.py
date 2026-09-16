"""T1.2 — Auditoria de cobertura del catalogo de ciudades por macro-region.

Calcula el universo DENUE (municipios con >=1 ferreteria 467111), lo cruza contra
los 606 del catalogo y evalua los tres umbrales (>=20 vigente, >=10, >=5).

No inventa cifras: todo sale del ZIP del INEGI descargado en esta sesion.
"""
import csv, io, json, pathlib, sys, zipfile, collections, unicodedata

ZIP = pathlib.Path(sys.argv[1])
CATALOGO = pathlib.Path(sys.argv[2])
SALIDA = pathlib.Path(sys.argv[3])

# Identico al generador (tools/generar_catalogo_ciudades.py:77-88)
REGION_POR_ENTIDAD = {
    "02": "Noroeste", "03": "Noroeste", "18": "Noroeste", "25": "Noroeste", "26": "Noroeste",
    "05": "Noreste", "08": "Noreste", "10": "Noreste", "19": "Noreste", "28": "Noreste",
    "06": "Occidente", "14": "Occidente", "16": "Occidente",
    "01": "Centro-Norte", "11": "Centro-Norte", "22": "Centro-Norte",
    "24": "Centro-Norte", "32": "Centro-Norte",
    "12": "Centro-Sur", "13": "Centro-Sur", "17": "Centro-Sur",
    "21": "Centro-Sur", "29": "Centro-Sur",
    "09": "Valle de Mexico", "15": "Valle de Mexico",
    "07": "Sureste", "20": "Sureste", "27": "Sureste", "30": "Sureste",
    "04": "Peninsula", "23": "Peninsula", "31": "Peninsula",
}
SCIAN_FERRETERIA = "467111"


def agregar_universo(ruta_zip):
    """Cuenta establecimientos 467111 por municipio. DENUE va en latin-1."""
    z = zipfile.ZipFile(ruta_zip)
    interno = next(n for n in z.namelist()
                   if "conjunto_de_datos/" in n and n.endswith(".csv"))
    conteo = collections.Counter()
    nombres = {}
    total_filas = 0
    with z.open(interno) as f:
        for fila in csv.DictReader(io.TextIOWrapper(f, encoding="latin-1", newline="")):
            total_filas += 1
            if (fila.get("codigo_act") or "").strip() != SCIAN_FERRETERIA:
                continue
            ent = (fila.get("cve_ent") or "").strip().zfill(2)
            mun = (fila.get("cve_mun") or "").strip().zfill(3)
            if not ent or not mun or ent not in REGION_POR_ENTIDAD:
                continue
            clave = ent + mun
            conteo[clave] += 1
            nombres.setdefault(clave, (fila.get("municipio") or "").strip())
    return conteo, nombres, total_filas


def main():
    universo, nombres, filas = agregar_universo(ZIP)
    catalogo = json.loads(CATALOGO.read_text(encoding="utf-8"))
    en_catalogo = {c["clave_inegi"] for c in catalogo}

    regiones = sorted(set(REGION_POR_ENTIDAD.values()))
    out = {
        "filas_leidas_del_zip": filas,
        "establecimientos_467111": sum(universo.values()),
        "universo_municipios_con_>=1": len(universo),
        "catalogo_total": len(catalogo),
        "por_region": {},
        "umbrales": {},
        "excluidos_top": {},
        "catalogo_fuera_del_universo": [],
    }

    # Un municipio del catalogo que no aparezca en el universo seria un fallo de
    # cruce (clave mal formada). Se comprueba en las dos direcciones.
    for c in catalogo:
        if c["clave_inegi"] not in universo:
            out["catalogo_fuera_del_universo"].append(
                {"clave": c["clave_inegi"], "nombre": c["nombre"],
                 "ferreterias_catalogo": c["indicadores"]["unidades_ferreteras"]})

    reg_de = lambda k: REGION_POR_ENTIDAD[k[:2]]

    for r in regiones:
        u = {k: v for k, v in universo.items() if reg_de(k) == r}
        cat = {c["clave_inegi"] for c in catalogo if c["region"] == r}
        cubiertos = len(cat & set(u))
        out["por_region"][r] = {
            "universo_>=1": len(u),
            "catalogo": len(cat),
            "cubiertos_del_universo": cubiertos,
            "cobertura_pct": round(100 * cubiertos / len(u), 1) if u else 0.0,
            "ferreterias_universo": sum(u.values()),
            "ferreterias_cubiertas": sum(v for k, v in u.items() if k in cat),
        }
        out["por_region"][r]["cobertura_ferreterias_pct"] = (
            round(100 * out["por_region"][r]["ferreterias_cubiertas"]
                  / max(out["por_region"][r]["ferreterias_universo"], 1), 1))
        # Excluidos con mas ferreterias
        fuera = sorted(((v, k) for k, v in u.items() if k not in cat), reverse=True)[:5]
        out["excluidos_top"][r] = [
            {"clave": k, "nombre": nombres.get(k, "?"), "ferreterias": v} for v, k in fuera]

    # Umbrales
    for umbral in (20, 10, 5, 1):
        sel = {k: v for k, v in universo.items() if v >= umbral}
        por_reg = {}
        for r in regiones:
            u = {k: v for k, v in universo.items() if reg_de(k) == r}
            s = {k for k in sel if reg_de(k) == r}
            por_reg[r] = {
                "ciudades": len(s),
                "universo": len(u),
                "cobertura_pct": round(100 * len(s) / len(u), 1) if u else 0.0,
                "cobertura_ferreterias_pct": round(
                    100 * sum(universo[k] for k in s) / max(sum(u.values()), 1), 1),
            }
        mas_chica = min(sel.items(), key=lambda kv: (kv[1], kv[0])) if sel else None
        out["umbrales"][f">={umbral}"] = {
            "total_ciudades": len(sel),
            "cobertura_nacional_ferreterias_pct": round(
                100 * sum(sel.values()) / max(sum(universo.values()), 1), 1),
            "ciudad_mas_pequena": (
                {"clave": mas_chica[0], "nombre": nombres.get(mas_chica[0], "?"),
                 "ferreterias": mas_chica[1]} if mas_chica else None),
            "por_region": por_reg,
            "min_cobertura_regional_pct": min(v["cobertura_pct"] for v in por_reg.values()),
            "max_cobertura_regional_pct": max(v["cobertura_pct"] for v in por_reg.values()),
        }

    SALIDA.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"filas leidas: {filas:,}")
    print(f"establecimientos 467111: {sum(universo.values()):,}")
    print(f"universo (municipios con >=1): {len(universo):,}")
    print(f"catalogo: {len(catalogo)}  |  fuera del universo: {len(out['catalogo_fuera_del_universo'])}")
    print()
    print(f"{'region':18} {'univ>=1':>8} {'catal':>6} {'cubr':>5} {'cob%':>6} {'cobFerr%':>9}")
    for r in regiones:
        d = out["por_region"][r]
        print(f"{r:18} {d['universo_>=1']:>8} {d['catalogo']:>6} {d['cubiertos_del_universo']:>5} "
              f"{d['cobertura_pct']:>6} {d['cobertura_ferreterias_pct']:>9}")
    print()
    for u, d in out["umbrales"].items():
        print(f"umbral {u:>4}: {d['total_ciudades']:>5} ciudades | ferreterias cubiertas "
              f"{d['cobertura_nacional_ferreterias_pct']:>5}% | cobertura regional "
              f"{d['min_cobertura_regional_pct']}%-{d['max_cobertura_regional_pct']}% | "
              f"mas chica: {d['ciudad_mas_pequena']['nombre']} ({d['ciudad_mas_pequena']['ferreterias']})")


if __name__ == "__main__":
    main()
