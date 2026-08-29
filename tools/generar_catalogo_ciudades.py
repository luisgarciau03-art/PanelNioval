"""Genera datos/ciudades_mx.json desde fuentes publicas del INEGI.

Uso:
    python tools/generar_catalogo_ciudades.py [--cache DIR] [--salida ARCHIVO]
                                              [--min-ferreterias N] [--verificar]

Fuentes (documentadas en docs/investigacion/2026-08-28-relevancia-ferretera-mexico.md):
  DENUE 05_2026 ramas 46591-46911 -> ferreterias y tlapalerias (SCIAN 467111)
  DENUE 05_2026 sector 43         -> mayoreo de materiales de construccion
  DENUE 05_2026 sector 23         -> empresas de construccion
  Censo 2020 ITER nacional        -> poblacion municipal

Modelo de puntuacion: docs/adr/2026-08-28-modelo-relevancia-ciudades.md

El script NO llama a ninguna API de pago. Las cuatro descargas son archivos
estaticos del INEGI, sin token. Se cachean en disco: la segunda corrida no
vuelve a bajar 118 MB.
"""
import argparse
import collections
import csv
import io
import json
import math
import pathlib
import re
import socket
import sys
import unicodedata
import urllib.request
import zipfile

# Sin timeout, una descarga que se cuelga a mitad deja el script esperando para
# siempre y sin un solo mensaje. Son archivos de 15-60 MB desde un servidor
# publico: 120 s de inactividad es se colgo, no es que vaya lento.
socket.setdefaulttimeout(120)

RAIZ = pathlib.Path(__file__).resolve().parents[1]
SALIDA_POR_DEFECTO = RAIZ / "datos" / "ciudades_mx.json"

BASE_DENUE = "https://www.inegi.org.mx/contenidos/masiva/denue/"
FUENTES = {
    "ferreterias": (BASE_DENUE + "denue_00_46591-46911_csv.zip", 50_000_000),
    "mayoreo": (BASE_DENUE + "denue_00_43_csv.zip", 15_000_000),
    "construccion": (BASE_DENUE + "denue_00_23_csv.zip", 2_000_000),
    "poblacion": (
        "https://www.inegi.org.mx/contenidos/programas/ccpv/2020/datosabiertos/"
        "iter/iter_00_cpv2020_csv.zip",
        30_000_000,
    ),
}

# SCIAN 467111. Se excluye a proposito 467115 (articulos de limpieza): son 46,582
# establecimientos que NO son prospectos de una distribuidora de ferreteria y
# plomeria, e inflarian el indicador principal un 61 %.
SCIAN_FERRETERIAS = {"467111"}
SCIAN_MAYOREO = {"434211", "434219", "434221", "434224", "434225", "434226"}

# El estrato de personal ocupado del DENUE es un rango de texto. El punto medio
# es una aproximacion declarada, no un dato: solo se usa para derivar el TAMANO
# MEDIO, que es lo unico que aporta informacion propia (r=0.152 contra el conteo;
# el personal ocupado en crudo es colineal, r=0.971 -- ver el ADR).
PUNTO_MEDIO_OCUPADOS = {
    "0 a 5 personas": 3, "6 a 10 personas": 8, "11 a 30 personas": 20,
    "31 a 50 personas": 40, "51 a 100 personas": 75, "101 a 250 personas": 175,
    "251 y m\xe1s personas": 300,
}

PESOS = {
    "ferreterias": 0.50,
    "tamano": 0.10,
    "mayoreo": 0.15,
    "construccion": 0.10,
    "poblacion": 0.15,
}

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

# Nombre comercial -> (fragmento del nombre INEGI, estado). El generador RESUELVE
# la clave por nombre contra el dato real en vez de llevarla escrita: escribirlas
# a mano ya metio cinco claves equivocadas al preparar esta tabla, y el propio
# plan traia 25006 para Los Mochis cuando 25006 es Culiacan.
NOMBRE_COMERCIAL = {
    "Acapulco": ("acapulco", "Guerrero"),
    "Autlán": ("autlan", "Jalisco"),
    "Cabo San Lucas": ("los cabos", "Baja California Sur"),
    "Cadereyta": ("cadereyta jimenez", "Nuevo Leon"),
    "Cancún": ("benito juarez", "Quintana Roo"),
    "Chetumal": ("othon p blanco", "Quintana Roo"),
    "Chilpancingo": ("chilpancingo", "Guerrero"),
    "Cholula": ("san pedro cholula", "Puebla"),
    "Ciudad Guzmán": ("zapotlan el grande", "Jalisco"),
    "Ciudad López Mateos": ("atizapan de zaragoza", "Mexico"),
    "Ciudad Obregón": ("cajeme", "Sonora"),
    "Ciudad del Carmen": ("carmen", "Campeche"),
    "Coacalco": ("coacalco", "Mexico"),
    "Comitán": ("comitan de dominguez", "Chiapas"),
    "Cosamaloapan": ("cosamaloapan", "Veracruz de Ignacio de la Llave"),
    "Cruz Grande": ("florencio villarreal", "Guerrero"),
    "Dolores Hidalgo": ("dolores hidalgo", "Guanajuato"),
    "Guamúchil": ("salvador alvarado", "Sinaloa"),
    "Huatulco": ("santa maria huatulco", "Oaxaca"),
    "Iguala": ("iguala de la independencia", "Guerrero"),
    "Los Mochis": ("ahome", "Sinaloa"),
    "Mante": ("el mante", "Tamaulipas"),
    "Parral": ("hidalgo del parral", "Chihuahua"),
    "Playa del Carmen": ("solidaridad", "Quintana Roo"),
    "Puerto Escondido": ("san pedro mixtepec", "Oaxaca"),
    "Rosarito": ("playas de rosarito", "Baja California"),
    "Tehuantepec": ("santo domingo tehuantepec", "Oaxaca"),
    "Tlapa": ("tlapa de comonfort", "Guerrero"),
    "Tuxtepec": ("san juan bautista tuxtepec", "Oaxaca"),
    "Villahermosa": ("centro", "Tabasco"),
    "Zihuatanejo": ("zihuatanejo", "Guerrero"),
}

# Alias extra que no cambian el nombre canonico pero deben reconciliar: entradas
# del array viejo y formas que el operador teclea en la hoja.
ALIAS_EXTRA = {
    "Los Mochis": ["Mochis"],
    "Cabo San Lucas": ["San Jose del Cabo"],
    "Cuauhtemoc, Ciudad de Mexico": ["Ciudad de Mexico", "CDMX", "Mexico DF"],
    "Cuauhtemoc, Chihuahua": ["Cuauhtemoc Chih"],
    "Guadalupe, Nuevo Leon": ["Guadalupe NL"],
    "Guadalupe, Zacatecas": ["Guadalupe Zacatecas"],
    "Juarez, Nuevo Leon": ["Juarez NL"],
    "Juarez, Chihuahua": ["Ciudad Juarez"],
    "La Paz, Baja California Sur": ["La Paz BCS"],
    "Loreto, Zacatecas": ["Loreto Zac"],
    "Allende, Nuevo Leon": ["Allende NL"],
    "Tonala, Chiapas": ["Tonala Chis"],
    "Durango": ["Victoria de Durango"],
    "Ecatepec de Morelos": ["Ecatepec"],
    "General Escobedo": ["Escobedo"],
    "Naucalpan de Juarez": ["Naucalpan"],
    "Oaxaca de Juarez": ["Oaxaca"],
    "Pachuca de Soto": ["Pachuca"],
    "Poza Rica de Hidalgo": ["Poza Rica"],
    "San Pedro Tlaquepaque": ["Tlaquepaque"],
    "Silao de la Victoria": ["Silao"],
    "Taxco de Alarcon": ["Taxco"],
    "Tepatitlan de Morelos": ["Tepatitlan"],
    "Tianguistenco": ["Santiago Tianguistenco"],
    "Tlajomulco de Zuniga": ["Tlajomulco"],
    "Tulancingo de Bravo": ["Tulancingo"],
    "Valle de Chalco Solidaridad": ["Valle de Chalco"],
}

# Entradas del array viejo que llevan la abreviatura del estado justamente para
# desambiguar. Hay que LEERLA, no tirarla: "Cuauhtemoc Chih" es Chihuahua, no la
# alcaldia de la CDMX que tiene 887 ferreterias y ganaria el desempate por conteo.
ABREVIATURA_ESTADO = {
    "NL": "Nuevo Leon", "Chih": "Chihuahua", "Chis": "Chiapas", "Tamps": "Tamaulipas",
    "Zac": "Zacatecas", "BCS": "Baja California Sur", "BC": "Baja California",
    "Gto": "Guanajuato", "Mich": "Michoacan de Ocampo", "Son": "Sonora",
    "Sin": "Sinaloa", "Dgo": "Durango", "Coah": "Coahuila de Zaragoza",
    "Qro": "Queretaro", "SLP": "San Luis Potosi", "Pue": "Puebla",
    "Jal": "Jalisco", "Hgo": "Hidalgo", "Oax": "Oaxaca", "Gro": "Guerrero",
    "Tab": "Tabasco", "Camp": "Campeche", "Yuc": "Yucatan", "QR": "Quintana Roo",
    "Ags": "Aguascalientes", "Col": "Colima", "Nay": "Nayarit", "Tlax": "Tlaxcala",
    "Mor": "Morelos", "Ver": "Veracruz de Ignacio de la Llave",
}
RE_ABREVIATURA = re.compile(r"^(.*?)\s+(" + "|".join(ABREVIATURA_ESTADO) + r")$")

# "Santiago Ixc" no esta en la tabla de arriba porque Ixc no es abreviatura de
# ningun estado: es Ixcuintla, o sea Santiago Ixcuintla, Nayarit.
ABREVIATURA_MUNICIPIO = {"Santiago Ixc": ("santiago ixcuintla", "Nayarit")}


def normalizar(s: str) -> str:
    s = unicodedata.normalize("NFD", str(s).lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    # Los espacios se colapsan: "Othon P. Blanco" pasa a tener dos seguidos al
    # sustituir el punto, y entonces ningun fragmento escrito a mano casa.
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", s)).strip()


def descargar(url: str, destino: pathlib.Path, minimo: int) -> pathlib.Path:
    """Baja el archivo si falta y comprueba que sirve.

    El INEGI publica denue_00_46_csv.zip con HTTP 200, content-type de zip y CERO
    bytes. Fiarse del codigo de estado se traga el archivo vacio sin enterarse,
    asi que aqui se verifica tamano y que el zip abra de verdad.
    """
    if destino.exists() and destino.stat().st_size >= minimo:
        return destino
    print(f"  bajando {url.rsplit('/', 1)[-1]} ...", flush=True)
    destino.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(url, destino)
    tam = destino.stat().st_size
    if tam < minimo:
        raise SystemExit(
            f"ERROR: {destino.name} son {tam:,} bytes y se esperaban >= {minimo:,}. "
            "El INEGI sirve archivos vacios con HTTP 200; no se sigue con este dato."
        )
    if not zipfile.is_zipfile(destino):
        raise SystemExit(f"ERROR: {destino.name} no es un zip valido (llego HTML?).")
    return destino


def _filas_denue(ruta: pathlib.Path):
    """DENUE va en latin-1. Leerlo como utf-8 rompe los acentos de municipio."""
    with zipfile.ZipFile(ruta) as z:
        interno = next(n for n in z.namelist() if n.startswith("conjunto_de_datos/"))
        with z.open(interno) as f:
            yield from csv.DictReader(io.TextIOWrapper(f, encoding="latin-1", newline=""))


def agregar_por_municipio(cache: pathlib.Path) -> dict:
    avisos = collections.Counter()
    mun = collections.defaultdict(
        lambda: {"ferreterias": 0, "ocupados": 0, "mayoreo": 0,
                 "construccion": 0, "poblacion": 0, "nombre": "", "estado": ""}
    )

    print("Agregando DENUE por municipio...")
    for clave, campo, pertenece in (
        ("ferreterias", "ferreterias", lambda c: c in SCIAN_FERRETERIAS),
        ("mayoreo", "mayoreo", lambda c: c in SCIAN_MAYOREO),
        ("construccion", "construccion", lambda c: c.startswith("23")),
    ):
        url, minimo = FUENTES[clave]
        ruta = descargar(url, cache / url.rsplit("/", 1)[-1], minimo)
        for fila in _filas_denue(ruta):
            if not pertenece(fila["codigo_act"]):
                continue
            d = mun[fila["cve_ent"] + fila["cve_mun"]]
            d[campo] += 1
            d["nombre"] = fila["municipio"]
            d["estado"] = fila["entidad"]
            if campo == "ferreterias":
                estrato = fila["per_ocu"]
                if estrato not in PUNTO_MEDIO_OCUPADOS:
                    # Si el DENUE cambia el texto del estrato, todos caerian al
                    # minimo en silencio y el tamano medio quedaria sesgado sin
                    # que nadie lo notara hasta comparar contra una corrida vieja.
                    avisos[f"estrato desconocido: {estrato!r}"] += 1
                d["ocupados"] += PUNTO_MEDIO_OCUPADOS.get(estrato, 3)

    print("Leyendo poblacion del Censo 2020...")
    url, minimo = FUENTES["poblacion"]
    ruta = descargar(url, cache / url.rsplit("/", 1)[-1], minimo)
    zp = zipfile.ZipFile(ruta)
    interno = next(n for n in zp.namelist() if "conjunto_de_datos/" in n and n.endswith(".csv"))
    with zp, zp.open(interno) as f:
        # El ITER va en utf-8 CON BOM. Sin utf-8-sig la primera columna se llama
        # "﻿ENTIDAD" y el KeyError llega en tiempo de ejecucion.
        for fila in csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig", newline="")):
            if fila.get("LOC") != "0000" or fila.get("MUN") in (None, "000"):
                continue
            clave = fila["ENTIDAD"].zfill(2) + fila["MUN"].zfill(3)
            if clave in mun:
                try:
                    mun[clave]["poblacion"] = int(fila["POBTOT"])
                except (ValueError, TypeError):
                    avisos["POBTOT no parseable"] += 1

    for motivo, n in avisos.most_common():
        print(f"  AVISO: {n:,} registros con {motivo}")
    return {k: v for k, v in mun.items() if v["nombre"]}


def calcular_potencial(municipios: dict) -> dict:
    """potencial_mercado, 0-100 exogeno. Ver el ADR para el porque de cada peso.

    Escala logaritmica en los conteos: la distribucion es de cola pesada -- el
    primer municipio vale 185 veces la mediana -- y normalizar linealmente deja
    dos de cada tres ciudades apretadas en una banda de 4 puntos, que es el
    empate arbitrario que este catalogo viene a eliminar.
    """
    bruto = {
        k: {
            "ferreterias": math.log1p(v["ferreterias"]),
            # Tamano MEDIO, no personal ocupado total: el total es colineal con
            # el conteo (r=0.971) y no aporta; el medio no lo es (r=0.152).
            "tamano": v["ocupados"] / max(v["ferreterias"], 1),
            "mayoreo": math.log1p(v["mayoreo"]),
            "construccion": math.log1p(v["construccion"]),
            "poblacion": math.log1p(v["poblacion"]),
        }
        for k, v in municipios.items()
    }
    maximos = {f: max((b[f] for b in bruto.values()), default=1) or 1 for f in PESOS}
    return {
        k: round(sum(PESOS[f] * bruto[k][f] / maximos[f] * 100 for f in PESOS), 1)
        for k in municipios
    }


def _resolver(municipios, fragmento, estado):
    """Busca UNA clave por nombre y estado. Si hay 0 o >1, es un error ruidoso."""
    hits = [
        k for k, v in municipios.items()
        if normalizar(v["estado"]) == normalizar(estado)
        and normalizar(v["nombre"]).startswith(fragmento)
    ]
    return hits[0] if len(hits) == 1 else None


def limpiar_nombre_inegi(nombre: str, estado: str) -> str:
    """Quita la abreviatura del estado que el propio INEGI pega a algun nombre.

    "Villa de Pozos SLP" viene asi del DENUE. Si se copia tal cual al catalogo, se
    le pide a Google Places "Ferreterias en Villa de Pozos SLP", que es justo la
    degradacion silenciosa que este plan elimina. Solo se recorta cuando la
    abreviatura coincide con el estado del municipio: en cualquier otro caso
    formaria parte del nombre de verdad.
    """
    m = RE_ABREVIATURA.match(nombre)
    if m and normalizar(ABREVIATURA_ESTADO[m.group(2)]) == normalizar(estado):
        return m.group(1).strip()
    return nombre


def leer_array_viejo() -> list:
    legacy = RAIZ / "tests" / "datos" / "ciudades_mx_legacy.txt"
    if not legacy.exists():
        return []
    return [
        l.strip() for l in legacy.read_text(encoding="utf-8").splitlines()
        if l.strip() and not l.startswith("#")
    ]


def resolver_array_viejo(municipios: dict, comercial_por_clave: dict) -> tuple:
    """Cada entrada del array viejo a su municipio. Devuelve (destinos, huerfanas).

    Se resuelve ANTES de recortar el catalogo: una ciudad que el operador ya podia
    elegir no puede desaparecer porque no llegue al corte de ferreterias. Quitarle
    una opcion es irreversible para el; dejarla abajo en el ranking, no.

    Orden de resolucion, de mas especifico a menos. La abreviatura de estado va
    ANTES que la coincidencia por nombre a proposito: "Cuauhtemoc Chih" tiene que
    caer en Chihuahua (120 ferreterias) y no en la alcaldia de la CDMX (887), que
    ganaria cualquier desempate por conteo.
    """
    por_nombre = collections.defaultdict(list)
    for clave, v in municipios.items():
        por_nombre[normalizar(v["nombre"])].append(clave)
    por_nombre_estado = {
        (normalizar(v["nombre"]), normalizar(v["estado"])): k for k, v in municipios.items()
    }
    comercial_normalizado = {normalizar(n): k for k, n in comercial_por_clave.items()}

    def por_prefijo(nombre, entidad_estado=None):
        n = normalizar(nombre)
        hits = [
            k for k, v in municipios.items()
            if normalizar(v["nombre"]).startswith(n)
            and (entidad_estado is None or normalizar(v["estado"]) == entidad_estado)
        ]
        # Empate: gana el de mas ferreterias. Es una ELECCION, no un hecho, y por
        # eso la entrada vieja queda registrada como alias de ese municipio.
        return max(hits, key=lambda k: municipios[k]["ferreterias"]) if hits else None

    destinos, huerfanas = collections.defaultdict(set), []
    for entrada in dict.fromkeys(leer_array_viejo()):
        n = normalizar(entrada)
        clave = comercial_normalizado.get(n)
        if clave is None and entrada in ABREVIATURA_MUNICIPIO:
            frag, estado = ABREVIATURA_MUNICIPIO[entrada]
            clave = por_prefijo(frag, normalizar(estado))
        if clave is None:
            m = RE_ABREVIATURA.match(entrada)
            if m:
                clave = por_prefijo(m.group(1), normalizar(ABREVIATURA_ESTADO[m.group(2)]))
        if clave is None and len(por_nombre.get(n, [])) == 1:
            clave = por_nombre[n][0]
        if clave is None:
            clave = por_nombre_estado.get((n, n))
        if clave is None:
            clave = por_prefijo(entrada)
        if clave is None:
            huerfanas.append(entrada)
        else:
            destinos[clave].add(entrada)
    return destinos, huerfanas


def construir_catalogo(municipios: dict, potencial: dict, minimo_ferreterias: int) -> tuple:
    seleccion = {
        k: v for k, v in municipios.items() if v["ferreterias"] >= minimo_ferreterias
    }

    comercial_por_clave = {}
    for comercial, (frag, estado) in NOMBRE_COMERCIAL.items():
        clave = _resolver(municipios, normalizar(frag), estado)
        if clave is None:
            raise SystemExit(
                f"ERROR: el alias comercial '{comercial}' no resuelve a un municipio unico."
            )
        comercial_por_clave[clave] = comercial

    destinos_viejos, huerfanas = resolver_array_viejo(municipios, comercial_por_clave)

    # Cobertura nacional: si un estado se queda sin ninguna ciudad por el corte,
    # entra su municipio con mas ferreterias. Un estado ausente del catalogo es
    # una plaza que el operador NO puede elegir nunca.
    for ent in {f"{i:02d}" for i in range(1, 33)}:
        if any(k.startswith(ent) for k in seleccion):
            continue
        del_estado = {k: v for k, v in municipios.items() if k.startswith(ent)}
        if del_estado:
            mejor = max(del_estado, key=lambda k: del_estado[k]["ferreterias"])
            seleccion[mejor] = del_estado[mejor]
            print(f"  entidad {ent} rescatada con {del_estado[mejor]['nombre']}")

    for clave in list(comercial_por_clave) + list(destinos_viejos):
        seleccion.setdefault(clave, municipios[clave])

    # Un nombre repetido entre municipios se desambigua con el estado COMPLETO, no
    # con una abreviatura. "Juarez, Chihuahua" es lo que escribiria una persona en
    # Google; "Juarez Chih" no lo escribe nadie, y hoy se le manda tal cual.
    repetidos = collections.Counter(normalizar(v["nombre"]) for v in municipios.values())
    alias_extra = {normalizar(k): v for k, v in ALIAS_EXTRA.items()}

    catalogo = []
    for clave, v in seleccion.items():
        comercial = comercial_por_clave.get(clave)
        limpio = limpiar_nombre_inegi(v["nombre"], v["estado"])
        if comercial:
            nombre, alias = comercial, {v["nombre"], limpio}
        elif repetidos[normalizar(v["nombre"])] > 1:
            nombre, alias = f"{limpio}, {v['estado']}", {v["nombre"], limpio}
        else:
            nombre, alias = limpio, {v["nombre"]}
        alias.update(alias_extra.get(normalizar(nombre), []))
        alias.update(destinos_viejos.get(clave, set()))
        alias = {a for a in alias if normalizar(a) != normalizar(nombre)}
        catalogo.append({
            "nombre": nombre,
            "estado": v["estado"],
            "clave_inegi": clave,
            "region": REGION_POR_ENTIDAD[clave[:2]],
            "alias": sorted(alias),
            "potencial_mercado": potencial[clave],
            "indicadores": {
                "unidades_ferreteras": v["ferreterias"],
                "tamano_medio": round(v["ocupados"] / max(v["ferreterias"], 1), 1),
                "mayoreo_construccion": v["mayoreo"],
                "empresas_construccion": v["construccion"],
                "poblacion": v["poblacion"],
            },
        })

    # Un alias no puede apuntar a dos ciudades: la reconciliacion de la hoja
    # dejaria de ser determinista y el destino dependeria del orden de recorrido.
    dueno = {}
    for c in catalogo:
        for a in list(c["alias"]):
            n = normalizar(a)
            if n in dueno and dueno[n]["clave_inegi"] != c["clave_inegi"]:
                # Gana quien tenga mas ferreterias; el otro lo suelta. El empate
                # se rompe por clave INEGI y no por orden de recorrido: si no,
                # dos corridas sobre el mismo dato podrian repartir los alias
                # distinto y el catalogo dejaria de ser reproducible.
                perdedor = min(
                    dueno[n], c,
                    key=lambda x: (x["indicadores"]["unidades_ferreteras"], x["clave_inegi"]),
                )
                perdedor["alias"] = [x for x in perdedor["alias"] if normalizar(x) != n]
                ganador = dueno[n] if perdedor is c else c
                dueno[n] = ganador
                print(f"  alias '{a}' era ambiguo: se queda con {ganador['nombre']}")
            else:
                dueno[n] = c
    nombres = {normalizar(c["nombre"]): c["clave_inegi"] for c in catalogo}
    for c in catalogo:
        # La pasada de arriba si avisaba y esta no: un alias que pisa el NOMBRE de
        # otra ciudad se caia sin dejar rastro. Solo se detecta despues si venia
        # del array viejo; uno de ALIAS_EXTRA desaparecia sin senal ninguna.
        quitados = [a for a in c["alias"]
                    if nombres.get(normalizar(a), c["clave_inegi"]) != c["clave_inegi"]]
        for a in quitados:
            print(f"  alias '{a}' de {c['nombre']} pisa el nombre de otra ciudad: se quita")
        c["alias"] = sorted(a for a in c["alias"] if a not in quitados)

    # Desempate del ADR: potencial, luego ferreterias, luego clave INEGI. Es
    # determinista: la misma entrada da el mismo orden en cualquier maquina.
    catalogo.sort(
        key=lambda c: (-c["potencial_mercado"],
                       -c["indicadores"]["unidades_ferreteras"],
                       c["clave_inegi"])
    )

    # Las huerfanas se recuentan AQUI, contra los alias definitivos. Calcularlas
    # antes daba ocho falsos positivos: "Ciudad de Mexico" no es el nombre de
    # ningun municipio y no resuelve sola, pero si esta cubierta como alias.
    # Un informe de cobertura que se toma antes de aplicar la cobertura miente.
    cubiertos = {normalizar(c["nombre"]) for c in catalogo}
    cubiertos |= {normalizar(a) for c in catalogo for a in c["alias"]}
    huerfanas = [v for v in dict.fromkeys(leer_array_viejo()) if normalizar(v) not in cubiertos]
    return catalogo, huerfanas


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--cache", default=str(pathlib.Path.home() / ".cache" / "inegi"),
                   help="Donde guardar los zips del INEGI entre corridas")
    p.add_argument("--salida", default=str(SALIDA_POR_DEFECTO))
    p.add_argument("--min-ferreterias", type=int, default=20,
                   help="Corte del catalogo. 20 -> ~589 municipios (ver el ADR)")
    p.add_argument("--verificar", action="store_true",
                   help="No escribe: solo compara contra el catalogo ya versionado")
    args = p.parse_args(argv)

    municipios = agregar_por_municipio(pathlib.Path(args.cache))
    print(f"  {len(municipios):,} municipios con datos, "
          f"{len({k[:2] for k in municipios})} entidades")

    potencial = calcular_potencial(municipios)
    catalogo, huerfanas = construir_catalogo(municipios, potencial, args.min_ferreterias)
    if huerfanas:
        print(f"\nAVISO: {len(huerfanas)} entradas del array viejo SIN destino:")
        for h in huerfanas:
            print("   ", h)

    salida = pathlib.Path(args.salida)
    texto = json.dumps(catalogo, ensure_ascii=False, indent=1) + "\n"
    if args.verificar:
        actual = salida.read_text(encoding="utf-8") if salida.exists() else ""
        if actual != texto:
            print("\nEl catalogo en disco NO coincide con el que generan las fuentes de hoy.")
            return 1
        print("\nEl catalogo en disco coincide con las fuentes.")
        return 0

    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text(texto, encoding="utf-8")
    print(f"\n{len(catalogo):,} ciudades escritas en {salida}")
    print(f"  entidades cubiertas: {len({c['clave_inegi'][:2] for c in catalogo})}/32")
    print(f"  potencial minimo: {min(c['potencial_mercado'] for c in catalogo)}")
    print("\n  Top 10:")
    for i, c in enumerate(catalogo[:10], 1):
        print(f"   {i:>2}. {c['nombre'][:34]:<34} {c['region']:<16} "
              f"{c['potencial_mercado']:>5}  ferre={c['indicadores']['unidades_ferreteras']}")
    return 1 if huerfanas else 0


if __name__ == "__main__":
    sys.exit(main())
