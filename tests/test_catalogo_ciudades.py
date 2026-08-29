"""Plan 1 - T1.4. Contrato del catalogo canonico datos/ciudades_mx.json.

Estos tests se escribieron ANTES del generador (tools/generar_catalogo_ciudades.py)
y fijan lo que el catalogo tiene que cumplir, no lo que el generador produjo.

El array viejo se compara contra tests/datos/ciudades_mx_legacy.txt, una copia
congelada del CIUDADES_MX de app.py: T1.7 borra el array del codigo, y sin la
copia este test se quedaria sin nada contra que comparar.
"""
import json
import pathlib
import re
import time
import unicodedata

import pytest

RAIZ = pathlib.Path(__file__).resolve().parents[1]
CATALOGO = RAIZ / "datos" / "ciudades_mx.json"
LEGACY = pathlib.Path(__file__).resolve().parent / "datos" / "ciudades_mx_legacy.txt"

# Abreviaturas de estado que el array viejo pegaba al nombre y que viajaban
# literalmente a Google Places: "Ferreterias en Santiago Ixc" no la escribe nadie.
SUFIJOS_PROHIBIDOS = re.compile(
    r"\s(NL|Chih|Chis|Tamps|Zac|BCS|Ixc|Gto|Mich|Son|Sin|Dgo|Coah|Qro|SLP"
    r"|Pue|Mex|Jal|Hgo|Oax|Gro|Tab|Camp|Yuc|QR|Ags|Col|Nay|Tlax|Mor|BC|Ver)$"
)

REGIONES = {
    "Noroeste", "Noreste", "Occidente", "Centro-Norte",
    "Centro-Sur", "Valle de Mexico", "Sureste", "Peninsula",
}


def normalizar(nombre: str) -> str:
    """Minusculas, sin acentos y sin puntuacion. Es como se comparan los nombres."""
    s = unicodedata.normalize("NFD", str(nombre).lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    # Los espacios se colapsan: "Guadalupe, Zacatecas" deja dos seguidos al
    # sustituir la coma, y entonces no casa con "Guadalupe Zacatecas" del array
    # viejo aunque sean la misma ciudad.
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", s)).strip()


@pytest.fixture(scope="module")
def catalogo():
    with CATALOGO.open(encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def legacy():
    lineas = LEGACY.read_text(encoding="utf-8").splitlines()
    return [l.strip() for l in lineas if l.strip() and not l.startswith("#")]


class TestIntegridadDelCatalogo:
    def test_sin_duplicados_por_clave_inegi(self, catalogo):
        claves = [c["clave_inegi"] for c in catalogo]
        assert len(claves) == len(set(claves))

    def test_sin_duplicados_por_nombre_normalizado(self, catalogo):
        """Sin acentos y en minusculas. Tehuacan y Tehuacan son la misma ciudad,
        y hoy generan dos consultas facturables a Places."""
        nombres = [normalizar(c["nombre"]) for c in catalogo]
        repetidos = sorted({n for n in nombres if nombres.count(n) > 1})
        assert repetidos == [], f"nombres repetidos tras normalizar: {repetidos}"

    def test_ningun_nombre_lleva_sufijo_desambiguador(self, catalogo):
        malos = [c["nombre"] for c in catalogo if SUFIJOS_PROHIBIDOS.search(c["nombre"])]
        assert malos == [], f"nombres con abreviatura de estado pegada: {malos}"

    def test_toda_ciudad_tiene_estado_y_region(self, catalogo):
        sin_estado = [c["nombre"] for c in catalogo if not c.get("estado", "").strip()]
        sin_region = [c["nombre"] for c in catalogo if not c.get("region", "").strip()]
        assert sin_estado == [] and sin_region == []

    def test_las_regiones_son_las_ocho_declaradas(self, catalogo):
        usadas = {c["region"] for c in catalogo}
        assert usadas <= REGIONES, f"regiones fuera del catalogo: {usadas - REGIONES}"

    def test_las_32_entidades_estan_representadas(self, catalogo):
        entidades = {c["clave_inegi"][:2] for c in catalogo}
        faltan = {f"{i:02d}" for i in range(1, 33)} - entidades
        assert faltan == set(), f"entidades sin ninguna ciudad: {sorted(faltan)}"

    def test_todo_potencial_es_mayor_que_cero(self, catalogo):
        """Restriccion no negociable del ADR: un cero reintroduce el empate
        arbitrario que este plan corrige."""
        ceros = [c["nombre"] for c in catalogo if not c["potencial_mercado"] > 0]
        assert ceros == [], f"ciudades con potencial 0: {ceros}"

    def test_toda_ciudad_del_array_viejo_mapea_a_una_canonica(self, catalogo, legacy):
        """Toda entrada del array actual debe tener destino. Si alguna no mapea se
        reporta; no se descarta en silencio."""
        conocidos = set()
        for c in catalogo:
            conocidos.add(normalizar(c["nombre"]))
            for a in c.get("alias", []):
                conocidos.add(normalizar(a))
        huerfanas = sorted({v for v in legacy if normalizar(v) not in conocidos})
        assert huerfanas == [], f"entradas del array viejo sin destino: {huerfanas}"

    def test_el_catalogo_carga_en_menos_de_50_ms(self):
        inicio = time.perf_counter()
        with CATALOGO.open(encoding="utf-8") as f:
            json.load(f)
        transcurrido = (time.perf_counter() - inicio) * 1000
        assert transcurrido < 50, f"cargar el catalogo tardo {transcurrido:.1f} ms"


class TestFormaDeCadaRegistro:
    def test_cada_registro_trae_los_campos_del_contrato(self, catalogo):
        obligatorios = {
            "nombre", "estado", "clave_inegi", "region",
            "alias", "potencial_mercado", "indicadores",
        }
        for c in catalogo:
            faltan = obligatorios - set(c)
            assert faltan == set(), f"{c.get('nombre')} sin campos {sorted(faltan)}"

    def test_la_clave_inegi_son_cinco_digitos(self, catalogo):
        malas = [c["clave_inegi"] for c in catalogo if not re.fullmatch(r"\d{5}", c["clave_inegi"])]
        assert malas == [], f"claves INEGI mal formadas: {malas}"

    def test_los_indicadores_traen_las_unidades_ferreteras(self, catalogo):
        """Es el conteo que la UI muestra junto al chip para que el ranking sea
        auditable sin creerse el puntaje comprimido (ADR 4.3)."""
        malos = [
            c["nombre"] for c in catalogo
            if not isinstance(c["indicadores"].get("unidades_ferreteras"), int)
            or c["indicadores"]["unidades_ferreteras"] <= 0
        ]
        assert malos == [], f"sin unidades_ferreteras utilizables: {malos}"

    def test_los_alias_no_chocan_entre_ciudades_distintas(self, catalogo):
        """Un alias que apunte a dos ciudades haria la reconciliacion de T1.5
        no determinista: la hoja diria 'Guadalupe' y el destino dependeria del
        orden de recorrido."""
        duenos = {}
        choques = []
        for c in catalogo:
            for a in c.get("alias", []):
                n = normalizar(a)
                if n in duenos and duenos[n] != c["clave_inegi"]:
                    choques.append((a, duenos[n], c["clave_inegi"]))
                duenos[n] = c["clave_inegi"]
        assert choques == [], f"alias ambiguos: {choques}"

    def test_ningun_alias_choca_con_el_nombre_de_otra_ciudad(self, catalogo):
        nombres = {normalizar(c["nombre"]): c["clave_inegi"] for c in catalogo}
        choques = [
            (a, c["nombre"]) for c in catalogo for a in c.get("alias", [])
            if normalizar(a) in nombres and nombres[normalizar(a)] != c["clave_inegi"]
        ]
        assert choques == [], f"alias que pisan el nombre de otra ciudad: {choques}"


class TestElCatalogoLlegaAlDespliegue:
    """El .gitignore del proyecto cubre *.json para atrapar credenciales, y eso
    dejaba fuera al catalogo SIN avisar. Un archivo que no se versiona no llega
    al VPS, y el panel arrancaria sin catalogo en produccion mientras en local
    funciona perfecto."""

    def test_git_no_ignora_el_catalogo(self):
        import subprocess
        r = subprocess.run(
            ["git", "check-ignore", "-q", "datos/ciudades_mx.json"],
            cwd=RAIZ, capture_output=True,
        )
        assert r.returncode != 0, "git esta ignorando datos/ciudades_mx.json"

    def test_docker_no_ignora_el_catalogo(self):
        dockerignore = RAIZ / ".dockerignore"
        if not dockerignore.exists():
            pytest.skip("no hay .dockerignore")
        patrones = [
            l.strip() for l in dockerignore.read_text(encoding="utf-8").splitlines()
            if l.strip() and not l.startswith("#")
        ]
        assert "datos/" not in patrones and "datos" not in patrones
