"""Barrido de secretos y datos personales sobre el diff de un pull request.

Uso:
    git diff origin/main...HEAD | python tools/barrer_secretos.py
    python tools/barrer_secretos.py --estricto < cambios.diff

Sale con 0 y solo AVISA por defecto. Con `--estricto` sale con 1 si hay
hallazgos. La primera version del gate avisa a proposito: bloquear el dia uno
con patrones sin calibrar convierte el gate en algo que la gente aprende a
saltarse.

POR QUE SOBRE EL DIFF Y NO SOBRE EL REPOSITORIO
-----------------------------------------------
El historial de git de este proyecto YA contiene el TELEGRAM_TOKEN (~14 copias)
y su rotacion es un gate del owner. Un barrido sobre el historial marcaria todos
los PR desde el primer dia hasta que se rote, que es la forma mas rapida de que
nadie vuelva a leer el check.

POR QUE NO SE FILTRA RUIDO POR ENTROPIA
---------------------------------------
La tentacion es descartar los falsos positivos contando caracteres distintos.
Se midio antes de decidir, y **no funciona en este caso**:

    PNG de 1x1 en base64 (96 chars) ...... 36 caracteres distintos
    token de Telegram real (46 chars) .... ~33 distintos esperados
      (64 * (1 - (63/64)**46), alfabeto base64)

Las dos poblaciones se solapan: cualquier umbral que oculte el blob de imagen
oculta tambien un token de verdad, y un barrido que no encuentra el secreto que
sabes que esta ahi no vale nada. Por eso el ruido se filtra por **firma del
formato** (deterministica), nunca por estadistica ni por largo.

Nota historica: la regla del entorno sobre usar conteo ABSOLUTO de caracteres
distintos en vez de un ratio sigue siendo correcta —un ratio penaliza justo a
los secretos mas largos por pura aritmetica—. Lo que esta medicion muestra es
que aqui ni el ratio ni el conteo absoluto separan las dos poblaciones, asi que
no se usa ninguno de los dos.

HUECOS CONOCIDOS, DECLARADOS A PROPOSITO
----------------------------------------
Un barrido que no dice donde no mira invita a leer su cero como "esta limpio".
Estos son los sitios donde este no mira:

1. **Secretos partidos en varias lineas.** El barrido es linea a linea; una
   clave cortada en dos concatenaciones no casa con ningun patron.
2. **Hexadecimales de exactamente 40 o 64 caracteres.** Son SHA-1 y SHA-256 de
   git y se citan constantemente en este repositorio. Ver `_es_objeto_git`.
3. **Proveedores sin patron propio**: AWS (`AKIA...`), Stripe (`sk_live_...`),
   JWT (`eyJ...`), cadenas de conexion con contrasena embebida. Ninguno esta en
   el stack de hoy; el dia que entre uno, aqui hay que anadir su patron.
4. **Valores aleatorios sin nombre reconocible.** Los secretos propios del panel
   se detectan por NOMBRE de variable (ver el patron `secreto_del_panel`)
   justamente porque por forma son indistinguibles de cualquier cadena. Uno
   guardado en una variable con otro nombre pasaria sin marcarse.
"""
import argparse
import re
import sys
from typing import NamedTuple


class Hallazgo(NamedTuple):
    """Un posible secreto. `muestra` va SIEMPRE enmascarada.

    El log de GitHub Actions queda archivado y es visible para cualquiera con
    acceso al repositorio: un barrido que imprime la credencial que encontro la
    propaga en vez de contenerla.
    """

    archivo: str
    linea: int
    tipo: str
    muestra: str


# --- Patrones, en orden de prioridad ----------------------------------------
# El orden importa: un token de Telegram empieza por el id numerico del bot, que
# son 10 digitos y por tanto tambien casa con el patron de telefono. El primero
# que reclama un tramo se lo queda (ver `_reclamados`), asi que el especifico va
# antes que el generico.
PATRONES = [
    ("telegram", re.compile(r"\d{8,10}:[A-Za-z0-9_-]{35}")),
    ("google_api_key", re.compile(r"AIza[0-9A-Za-z_-]{35}")),
    ("openai", re.compile(r"sk-[A-Za-z0-9]{20,}")),
    ("meta", re.compile(r"EAA[A-Za-z0-9]{40,}")),
    ("clave_privada", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    # Los secretos DEL PROPIO PANEL. Se detectan por nombre de variable y no por
    # forma del valor porque no la tienen: son salidas de `secrets.token_urlsafe`
    # y compania, indistinguibles de una cadena cualquiera. Sin esta regla, el
    # secreto mas probable de este repositorio es justo el que no se marcaria.
    # Solo se enmascara el grupo `valor`, nunca el nombre: el nombre es
    # precisamente lo que hay que poder leer en el informe.
    (
        "secreto_del_panel",
        re.compile(
            r"(?:PANEL_DASHBOARD_TOKEN|SECRET_KEY|WORKER_TOKEN|TELEGRAM_TOKEN"
            r"|GOOGLE_CREDENTIALS_JSON|GOOGLE_MAPS_API_KEY)"
            # El valor no lleva espacios ni empieza por `/`. Sin eso, un
            # `grep "^PANEL_DASHBOARD_TOKEN=" /srv/panel/.env` de un runbook se
            # marcaba como si fuera una asignacion: el patron leia la ruta que
            # venia detras como si fuera el secreto.
            r"\s*[:=]\s*[\"'](?P<valor>[^\"'\s/][^\"'\s]{7,})[\"']"
        ),
    ),
    # Secretos en hexadecimal (claves HMAC, API secrets). Ver `_es_objeto_git`
    # para el recorte deliberado que evita marcar cada SHA de commit citado.
    #
    # La clase acepta MAYUSCULAS. Con `[0-9a-f]` y lookarounds que excluian
    # `[0-9a-fA-F]`, un secreto con una sola letra en mayuscula no casaba ni
    # entero ni por su tramo en minuscula, porque ese tramo quedaba pegado a un
    # caracter excluido: era invisible del todo.
    ("hex_largo", re.compile(r"(?<![0-9a-fA-F])[0-9a-fA-F]{32,64}(?![0-9a-fA-F])")),
    # Forma pegada con lada de pais: 52 + 10 digitos, sin separadores. Es el
    # formato que usa WhatsApp y el que este mismo proyecto maneja al construir
    # los enlaces. Va ANTES que el de 10 digitos porque dentro de una tirada de
    # 12 ninguna ventana de 10 esta rodeada de no-digitos, asi que el patron
    # corto no la ve: un telefono en este formato pasaba entero desapercibido.
    ("telefono_mx", re.compile(r"(?<![\d.])52[2-9]\d{9}(?![\d.])")),
    # Telefono mexicano de 10 digitos sin enmascarar. Arranca en [2-9] porque
    # ningun numero nacional empieza por 0 ni por 1, y eso descarta de paso los
    # timestamps epoch en segundos, que son 10 digitos empezando por 1.
    ("telefono_mx", re.compile(r"(?<![\d.])[2-9]\d{9}(?![\d.])")),
    # Forma internacional. Se captura tambien la ya enmascarada para poder
    # descartarla explicitamente en `_esta_enmascarado`.
    ("telefono_mx", re.compile(r"\+52[\s.\-]*[\dXx*.…]{4,14}")),
]

# Firmas en base64 de formatos binarios. Un tramo que empieza por una de estas
# es un archivo incrustado, y nada de lo que haya dentro es una credencial.
# Cada una es la cabecera magica del formato codificada en base64.
FIRMAS_BINARIAS = (
    "iVBORw0KGgo",   # PNG   -> \x89PNG\r\n\x1a\n
    "/9j/",          # JPEG  -> \xff\xd8\xff
    "R0lGOD",        # GIF   -> GIF8
    "UklGR",         # WEBP  -> RIFF
    "JVBERi0",       # PDF   -> %PDF-
    "UEsDB",         # ZIP / xlsx / docx -> PK\x03\x04
    "AAABAA",        # ICO
)

# RETIRADO: habia aqui un `LARGO_IMPLAUSIBLE = 200` que descartaba cualquier
# tramo mas largo, por considerarlo un volcado binario. Era un falso negativo:
# los tokens de larga duracion de Meta pasan de 200 caracteres con normalidad, y
# el patron `meta` no tiene tope superior a proposito. Un token real y largo se
# clasificaba como "volcado" y desaparecia del informe sin dejar rastro.
#
# El trabajo de separar imagenes de secretos lo hace `FIRMAS_BINARIAS`, que es
# deterministico. Quitar el corte por largo cambia un falso NEGATIVO por, como
# mucho, algo de ruido en un blob sin firma reconocible. En un barrido de
# seguridad ese cambio va en la direccion correcta: el ruido se lee y se
# descarta; lo que no aparece, no se descarta, se ignora sin saberlo.

# Debajo de esto, prefijo + sufijo reconstruirian la cadena entera.
LARGO_MINIMO_PARA_ENMASCARAR = 12

# Marcas de que un dato ya viene enmascarado, segun la regla del proyecto
# (`+52...XXXX`).
MARCAS_DE_MASCARA = ("...", "…", "X", "x", "*")

# Escape hatch por linea. Existe porque este mismo barrido necesita fixtures con
# forma de credencial para poder probarse, y sin esto marcaria sus propios tests
# en cada PR: un gate que grita siempre deja de leerse, y entonces da igual lo
# bien que detecte.
#
# Es a proposito una marca EN LINEA y no una exclusion de `tests/` entera: una
# carpeta excluida esconde para siempre lo que caiga dentro, mientras que cada
# uso de esta marca aparece en el diff y un revisor lo ve y lo puede discutir.
#
# **Exige un motivo escrito.** Un `barrido-ok` a secas silenciaria una linea sin
# que nadie tenga que justificar por que, y el dia que el job pase a `--estricto`
# eso seria un bypass de un gate que bloquea. Con el motivo obligatorio, saltarse
# el barrido cuesta escribir en el diff la razon por la que se hizo.
#
# Alcance: silencia la LINEA ENTERA. Un secreto real que compartiera linea con
# una fixture marcada quedaria oculto tambien.
MARCA_DE_EXCEPCION = re.compile(r"barrido-ok:\s*\S+")

# Caracteres que pueden formar parte de un volcado en base64.
_TRAMO_BASE64 = re.compile(r"[A-Za-z0-9+/=_-]+")

# Un data-URI completo, con su carga util. Se necesita el tramo EXACTO y no solo
# saber que la linea lo menciona: ver `_es_ruido_binario`.
_URI_DE_DATOS = re.compile(r"data:[\w.+-]+/[\w.+-]+;base64,[A-Za-z0-9+/=]*")


def enmascarar(valor: str) -> str:
    """Prefijo + sufijo, nunca el valor.

    Las cadenas cortas se ocultan enteras: con 8 caracteres, mostrar los 4
    primeros y los 4 ultimos es mostrarla.
    """
    if len(valor) < LARGO_MINIMO_PARA_ENMASCARAR:
        return "(oculto)"
    return f"{valor[:4]}...{valor[-4:]}"


def _tramos_base64(linea: str) -> list[tuple[int, int, str]]:
    """Los volcados base64 de la linea, calculados UNA vez.

    Antes se recorria la linea entera por cada coincidencia, y eso es
    cuadratico en lineas largas con muchas coincidencias: un archivo minificado
    dentro de un diff basta para notarlo.
    """
    return [(t.start(), t.end(), t.group()) for t in _TRAMO_BASE64.finditer(linea)]


def _tramo_alrededor(
    linea: str, inicio: int, fin: int, tramos: list[tuple[int, int, str]]
) -> str:
    """El volcado base64 completo que contiene la coincidencia.

    Sin esto se juzgaria solo el fragmento que caso, que en una imagen tiene
    exactamente la misma pinta que un token suelto.
    """
    for principio, final, texto in tramos:
        if principio <= inicio and final >= fin:
            return texto
    return linea[inicio:fin]


def _es_ruido_binario(
    linea: str, inicio: int, fin: int, tramos: list[tuple[int, int, str]]
) -> bool:
    """True si la coincidencia vive DENTRO de un archivo incrustado.

    La comprobacion es posicional a proposito. La primera version preguntaba si
    la linea contenia `data:image/` en cualquier sitio, y eso convertia el
    filtro de ruido en un agujero: un secreto de verdad que compartiera linea
    con el icono en base64 de un HTML se descartaba entero y el informe decia
    "barrido limpio". Un barrido con su propio modo de invisibilidad es justo lo
    que este script existe para no repetir.
    """
    for uri in _URI_DE_DATOS.finditer(linea):
        if uri.start() <= inicio and uri.end() >= fin:
            return True
    return _tramo_alrededor(linea, inicio, fin, tramos).startswith(FIRMAS_BINARIAS)


def _es_objeto_git(texto: str) -> bool:
    """True si el hexadecimal tiene el largo exacto de un identificador de git.

    40 = SHA-1, 64 = SHA-256. Los hashes de commit se citan constantemente en
    commits, planes y RUNBOOK de este repositorio.

    **Recorte deliberado y su coste:** un secreto hexadecimal que midiera
    exactamente 40 o 64 caracteres pasaria sin marcarse. Se acepta porque por
    forma es indistinguible de un SHA, y marcarlos convertiria el gate en ruido
    permanente. Los demas largos (32-39, 41-63) si se marcan.
    """
    return len(texto) in (40, 64)


def _esta_enmascarado(texto: str) -> bool:
    """True si el dato ya viene ocultado como exige la regla del proyecto."""
    return any(marca in texto for marca in MARCAS_DE_MASCARA)


def _descartar(
    tipo: str,
    texto: str,
    linea: str,
    inicio: int,
    fin: int,
    tramos: list[tuple[int, int, str]],
) -> bool:
    """Reglas de ruido, todas deterministicas. Ver el docstring del modulo."""
    if _es_ruido_binario(linea, inicio, fin, tramos):
        return True
    if tipo == "hex_largo" and _es_objeto_git(texto):
        return True
    if tipo == "telefono_mx" and _esta_enmascarado(texto):
        return True
    return False


def barrer_linea(linea: str, archivo: str, numero: int) -> list[Hallazgo]:
    """Barre UNA linea ya decodificada.

    Se trabaja sobre texto en Python y no con `grep` a proposito: `grep` sin
    `-a` da por binario cualquier archivo con bytes raros y **suprime las
    coincidencias sin avisar de forma evidente**. Asi se perdio un token de
    Telegram en un barrido de 356 commits.
    """
    if MARCA_DE_EXCEPCION.search(linea):
        return []

    hallazgos: list[Hallazgo] = []
    reclamados: list[range] = []
    tramos = _tramos_base64(linea)

    for tipo, patron in PATRONES:
        for casa in patron.finditer(linea):
            inicio, fin = casa.start(), casa.end()
            if any(inicio < tramo.stop and tramo.start < fin for tramo in reclamados):
                continue
            texto = casa.group()
            # Si el patron aisla el secreto en un grupo `valor`, se enmascara
            # solo eso. Enmascarar la coincidencia entera gastaria el prefijo
            # visible en el nombre de la variable y dejaria asomar el final del
            # valor, que es exactamente lo contrario de lo que se busca.
            secreto = casa.groupdict().get("valor") or texto
            if _descartar(tipo, texto, linea, inicio, fin, tramos):
                # Reclamado igualmente: un tramo ya juzgado como ruido no debe
                # volver a evaluarse con un patron mas generico.
                reclamados.append(range(inicio, fin))
                continue
            reclamados.append(range(inicio, fin))
            hallazgos.append(Hallazgo(archivo, numero, tipo, enmascarar(secreto)))

    return hallazgos


def barrer_texto(texto: str, archivo: str = "") -> list[Hallazgo]:
    """Barre un texto completo, numerando las lineas desde 1."""
    if not isinstance(texto, str):
        raise TypeError(f"barrer_texto espera str, recibio {type(texto).__name__}")
    hallazgos: list[Hallazgo] = []
    for numero, linea in enumerate(texto.splitlines(), start=1):
        hallazgos.extend(barrer_linea(linea, archivo, numero))
    return hallazgos


_CABECERA_ARCHIVO = re.compile(r"^\+\+\+ b/(.+)$")
_CABECERA_TROZO = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def barrer_diff(diff: str) -> list[Hallazgo]:
    """Barre SOLO las lineas anadidas de un diff unificado.

    No se envuelve en try/except a proposito: un barrido que atrapa su propia
    excepcion devuelve cero hallazgos y **parece un exito**, que es justo como
    un gate de seguridad deja de servir sin que nadie se entere.
    """
    if not isinstance(diff, str):
        raise TypeError(f"barrer_diff espera str, recibio {type(diff).__name__}")

    hallazgos: list[Hallazgo] = []
    archivo = ""
    numero = 0
    # `+++ b/x` solo es cabecera si viene detras de `--- a/x`. Sin esta memoria,
    # una linea ANADIDA cuyo contenido sea `++ b/algo` se convierte, con el `+`
    # que le pone el propio diff, en algo indistinguible de una cabecera: se
    # dejaria de barrer y desplazaria la numeracion del resto del trozo.
    anterior_es_cabecera_vieja = False

    for linea in diff.splitlines():
        # Marcador de "sin salto de linea al final". Es metadato, no contenido:
        # si contara como linea, desplazaria en uno el numero de la ultima linea
        # anadida cada vez que un cambio toca el final del archivo.
        if linea.startswith("\\"):
            continue

        if anterior_es_cabecera_vieja:
            cabecera = _CABECERA_ARCHIVO.match(linea)
            if cabecera:
                archivo = cabecera.group(1)
                anterior_es_cabecera_vieja = False
                continue

        trozo = _CABECERA_TROZO.match(linea)
        if trozo:
            numero = int(trozo.group(1)) - 1
            anterior_es_cabecera_vieja = False
            continue

        if linea.startswith("--- ") or linea.startswith("diff --git"):
            anterior_es_cabecera_vieja = True
            continue
        anterior_es_cabecera_vieja = False

        if linea.startswith("+"):
            numero += 1
            hallazgos.extend(barrer_linea(linea[1:], archivo, numero))
        elif not linea.startswith("-"):
            numero += 1

    return hallazgos


def contar_lineas_anadidas(diff: str) -> int:
    """Cuantas lineas anadidas se llegaron a examinar.

    Existe para que el informe pueda distinguir "mire mucho y estaba limpio" de
    "no mire nada". Las dos cosas dan cero hallazgos, y sin este numero se leen
    exactamente igual: un `SHA_BASE` mal calculado produce un diff vacio sin
    error, `git diff` sale con 0, y el resumen diria "barrido limpio" habiendo
    revisado nada.
    """
    return sum(
        1
        for linea in diff.splitlines()
        if linea.startswith("+") and not linea.startswith("+++")
    )


def formatear(hallazgos: list[Hallazgo], lineas_examinadas: int | None = None) -> str:
    """Informe legible. Nunca incluye un valor sin enmascarar."""
    if not hallazgos:
        if lineas_examinadas == 0:
            return (
                "Barrido sin material: 0 lineas anadidas que examinar.\n"
                "Esto NO es lo mismo que un diff limpio. Si el PR si trae "
                "cambios, el SHA base del workflow esta mal calculado."
            )
        if lineas_examinadas:
            return f"Barrido limpio: 0 hallazgos en {lineas_examinadas} lineas anadidas."
        return "Barrido limpio: 0 hallazgos en las lineas anadidas."
    filas: list[str] = [f"{len(hallazgos)} hallazgo(s) en las lineas anadidas:", ""]
    for h in hallazgos:
        ubicacion = f"{h.archivo}:{h.linea}" if h.archivo else f"linea {h.linea}"
        filas.append(f"  [{h.tipo}] {ubicacion} -> {h.muestra}")
    filas.append("")
    filas.append("Si alguno es real: rotalo en el proveedor. Quitarlo del codigo")
    filas.append("no lo rota, y sigue vivo en el historial de git.")
    return "\n".join(filas)


def main(argv: list[str] | None = None) -> int:
    analizador = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    analizador.add_argument(
        "--estricto",
        action="store_true",
        help="salir con codigo 1 si hay hallazgos (por defecto solo avisa)",
    )
    args = analizador.parse_args(argv)

    diff = sys.stdin.read()
    hallazgos = barrer_diff(diff)
    print(formatear(hallazgos, contar_lineas_anadidas(diff)))
    return 1 if (hallazgos and args.estricto) else 0


if __name__ == "__main__":
    sys.exit(main())
