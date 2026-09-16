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
UNIVERSO = pathlib.Path(__file__).resolve().parent / "datos" / "universo_ferretero_denue.csv"
HOMONIMOS = pathlib.Path(__file__).resolve().parent / "datos" / "municipios_homonimos.txt"
RELEVANTES = pathlib.Path(__file__).resolve().parent / "datos" / "universo_ferretero_min10.csv"

# Compromiso de servicio, NO umbral derivado del dato. Ver TestCoberturaNacionalPorRegion.
COBERTURA_REGIONAL_MINIMA = 75.0

# Piso del ADR: por debajo de esto la normalizacion logaritmica estaria aplastando
# ciudades contra el cero, que es el empate arbitrario que el Plan 1 vino a quitar.
POTENCIAL_MINIMO_ACEPTABLE = 5

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


@pytest.fixture(scope="module")
def universo_ferretero():
    """Masa ferretera del universo DENUE por macro-region: el DENOMINADOR.

    El catalogo solo sabe de las ciudades que entraron; para saber que PARTE del
    mercado cubre hace falta el total, y eso vive en el ZIP de 60 MB del INEGI que
    un test no puede descargar. El fixture es ese total, congelado y con su
    procedencia escrita en la cabecera del archivo.
    """
    universo = {}
    for linea in UNIVERSO.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or linea.startswith("region,"):
            continue
        region, municipios, ferreterias = linea.split(",")
        universo[region] = {"municipios": int(municipios), "ferreterias": int(ferreterias)}
    return universo


@pytest.fixture(scope="module")
def homonimos():
    """Nombres de municipio que se repiten en Mexico, ya normalizados."""
    return {
        l.strip() for l in HOMONIMOS.read_text(encoding="utf-8").splitlines()
        if l.strip() and not l.startswith("#")
    }


@pytest.fixture(scope="module")
def municipios_relevantes():
    """Los 995 municipios con >=10 ferreterias: el CE1 en forma de dato.

    Devuelve {clave_inegi: (ferreterias, nombre)}. Es la lista que el catalogo
    tiene que contener ENTERA, municipio por municipio.
    """
    relevantes = {}
    for linea in RELEVANTES.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or linea.startswith("clave_inegi,"):
            continue
        clave, ferreterias, municipio = linea.split(",", 2)
        relevantes[clave] = (int(ferreterias), municipio)
    return relevantes


def _masa_por_region(catalogo) -> dict[str, int]:
    """Ferreterias que el catalogo alcanza, sumadas por region. Arranca en 0 para
    las ocho: una region que se quedara sin ninguna ciudad desapareceria del dict
    y su cobertura del 0 % no se veria por ningun lado."""
    masa = {r: 0 for r in REGIONES}
    for c in catalogo:
        masa[c["region"]] += c["indicadores"]["unidades_ferreteras"]
    return masa


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


class TestCoberturaNacionalPorRegion:
    """Plan 1 - T1.3. El catalogo no solo tiene que estar bien formado: tiene que
    cubrir el mercado. El dueno pidio "todas las ciudades de la region", y hasta
    T1.2 nadie habia medido si los 606 municipios eran "todas".

    Se mide contra MASA FERRETERA, no contra numero de municipios. Son dos
    preguntas distintas y las dos son legitimas (ver el documento de T1.2, 4.2),
    pero la que se traduce en ingresos es la masa: en un conteo de municipios uno
    de 3 ferreterias pesa igual que uno de 300, y eso sobredimensiona la
    fragmentacion rural del Sureste.

    EL 75 % ES NORMATIVO, NO DERIVADO DEL DATO. Se eligio DESPUES de ver las
    cifras, sabiendo que deja fuera al umbral >=20 y dentro al >=10: eso es
    ajuste retrospectivo y se declara en vez de disimularse. No se defiende como
    hallazgo estadistico sino como compromiso de servicio -- si la promesa es
    "cobertura nacional", dejar fuera mas de una cuarta parte del mercado de una
    region rompe esa promesa. Cualquiera puede discutir el numero; lo que no
    puede es creer que salio del dato.
    """

    def test_el_universo_de_referencia_cuadra_con_la_medicion_de_t12(self, universo_ferretero):
        """Si el fixture se regenera contra un corte del DENUE distinto al del
        catalogo, la cobertura medida deja de significar nada y el test de abajo
        pasaria o fallaria por la razon equivocada. Estas son las cifras que T1.2
        reprodujo por dos caminos independientes."""
        total = sum(v["ferreterias"] for v in universo_ferretero.values())
        municipios = sum(v["municipios"] for v in universo_ferretero.values())
        assert total == 75_726, f"masa ferretera nacional cambio: {total}"
        assert municipios == 2_227, f"universo de municipios cambio: {municipios}"
        assert set(universo_ferretero) == REGIONES

    def test_ninguna_region_del_catalogo_supera_a_su_propio_universo(
        self, catalogo, universo_ferretero
    ):
        """Cobertura por encima del 100 % no es una region muy bien cubierta: es
        un fixture viejo o un cruce roto. Se detecta antes de leer el porcentaje."""
        imposibles = []
        for region, cubierta in _masa_por_region(catalogo).items():
            universo = universo_ferretero[region]["ferreterias"]
            if cubierta > universo:
                imposibles.append(f"{region}: {cubierta} cubiertas > {universo} del universo")
        assert imposibles == [], f"cobertura imposible (fixture desfasado?): {imposibles}"

    def test_ninguna_region_cubre_menos_del_75_por_ciento_de_su_masa_ferretera(
        self, catalogo, universo_ferretero
    ):
        """EL test de T1.3. Con el umbral >=20 el Sureste se queda en ~65 % y esto
        FALLA, que es lo que tiene que hacer antes del cambio. Con >=10 sube a
        ~80 % y pasa."""
        flojas = []
        for region, cubierta in sorted(_masa_por_region(catalogo).items()):
            universo = universo_ferretero[region]["ferreterias"]
            pct = 100 * cubierta / universo
            if pct < COBERTURA_REGIONAL_MINIMA:
                flojas.append(f"{region}: {pct:.1f} % ({cubierta} de {universo} ferreterias)")
        assert flojas == [], (
            f"regiones por debajo del {COBERTURA_REGIONAL_MINIMA} % de su masa ferretera: {flojas}"
        )

    def test_el_potencial_minimo_deja_margen_sobre_el_piso_de_cinco(self, catalogo):
        """CE3. El test de arriba solo exige > 0, y eso no basta: al bajar el
        umbral entran municipios chicos y la normalizacion logaritmica podria
        aplastarlos contra el cero, devolviendo el empate arbitrario que este
        plan vino a quitar. El piso de 5 es el que fija el criterio de exito."""
        minimo = min(c["potencial_mercado"] for c in catalogo)
        peor = min(catalogo, key=lambda c: c["potencial_mercado"])
        assert minimo > POTENCIAL_MINIMO_ACEPTABLE, (
            f"potencial minimo {minimo} en {peor['nombre']} "
            f"({peor['indicadores']['unidades_ferreteras']} ferreterias)"
        )


class TestElNombreQueViajaAPlaces:
    """Plan 1 - T1.3, condicion 1 del consejo de T1.2.

    El catalogo no le habla a una base de datos con claves: le habla a Google
    Places, y le manda el NOMBRE tal cual. "Ferreterias en Juarez" no es una
    consulta: son tres municipios en tres estados. Traer los resultados del
    equivocado no falla ruidosamente -- devuelve 20 ferreterias reales que no
    sirven, y cobra las llamadas igual.

    TestIntegridadDelCatalogo ya cubre los choques DENTRO del catalogo. Lo que
    falta es el homonimo del que solo entro un gemelo: su nombre es unico aqui
    dentro y sigue siendo ambiguo alla afuera. Por eso el contraste va contra el
    universo del DENUE y no contra el propio catalogo.
    """

    def test_ningun_nombre_ni_alias_lleva_espacios_sobrantes(self, catalogo):
        """El DENUE trae el campo `municipio` rellenado con espacios en algunas
        filas, y ese relleno llega intacto al catalogo: "Dzitbalche" viaja con 70
        espacios detras. La consulta que se le manda a Places es literalmente
        "Ferreterias en Dzitbalche                    ".

        No revienta -- y por eso nadie lo ve. normalizar() colapsa los espacios,
        asi que los tests de duplicados tampoco lo detectan: para ellos el nombre
        sucio y el limpio son el mismo. Se mira el nombre CRUDO a proposito.
        """
        sucios = [
            (c["clave_inegi"], repr(x)) for c in catalogo
            for x in [c["nombre"], *c["alias"]]
            if x != x.strip() or "  " in x
        ]
        assert sucios == [], f"nombres o alias con espacios sobrantes: {sucios[:10]}"

    def test_ningun_nombre_es_un_homonimo_sin_su_estado(self, catalogo, homonimos):
        ambiguos = [
            f"{c['nombre']} ({c['estado']}, {c['clave_inegi']})"
            for c in catalogo
            if normalizar(c["nombre"]) in homonimos and "," not in c["nombre"]
        ]
        assert ambiguos == [], (
            f"nombres que Places no puede resolver sin el estado: {ambiguos}"
        )

    def test_la_lista_de_homonimos_no_se_quedo_vacia(self, homonimos):
        """Una lista vacia haria pasar el test de arriba sin mirar nada. Un
        chequeo que no puede encontrar un positivo no vale su cero."""
        assert len(homonimos) >= 50
        assert {"juarez", "hidalgo", "zaragoza", "benito juarez"} <= homonimos


class TestNingunaPlazaRelevanteSeQuedaFuera:
    """Plan 1 - T1.3. CE1, y hasta ahora solo lo verificaba un script de una corrida.

    TestCoberturaNacionalPorRegion mide MASA AGREGADA por region, y esa es una
    pregunta distinta: una region puede cumplir el 75 % y tener dentro un
    municipio grande excluido, porque el agregado lo tapa. Sin este test, subir
    el corte del generador dejaria la suite en verde mientras CE1 regresa en
    silencio -- que es exactamente como se cuelan las regresiones que nadie ve.

    Hallazgo del gate de code-reviewer en T1.3.
    """

    def test_todos_los_municipios_con_diez_o_mas_ferreterias_estan_en_el_catalogo(
        self, catalogo, municipios_relevantes
    ):
        en_catalogo = {c["clave_inegi"] for c in catalogo}
        fuera = sorted(set(municipios_relevantes) - en_catalogo)
        detalle = [
            f"{k} {municipios_relevantes[k][1]} ({municipios_relevantes[k][0]} ferreterias)"
            for k in fuera[:15]
        ]
        assert fuera == [], (
            f"{len(fuera)} municipios con presencia ferretera relevante fuera "
            f"del catalogo: {detalle}"
        )

    def test_la_lista_de_relevantes_es_la_que_midio_t12(self, municipios_relevantes):
        """Sin esto, un fixture truncado dejaria pasar el test de arriba sin
        mirar casi nada. 995 es la cifra que T1.2 reprodujo por dos caminos."""
        assert len(municipios_relevantes) == 995
        assert min(f for f, _ in municipios_relevantes.values()) >= 10
