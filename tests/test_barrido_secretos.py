"""El barrido de secretos del CI: que encuentre lo que debe y calle lo que no.

Este archivo existe por dos incidentes reales de este entorno, y cada uno deja
su test:

1. Un token de Telegram quedo INVISIBLE en un barrido de 356 commits porque
   `grep` sin `-a` trata como binario cualquier volcado con bytes raros y
   suprime las coincidencias sin avisar de forma evidente. De ahi que aqui se
   barra en Python sobre texto ya decodificado, y que haya un test que exige
   encontrar un positivo conocido: un barrido cuyo cero no esta probado no vale
   nada.

2. Un barrido previo dio 2,179 hallazgos de los que 2,156 eran base64 de
   imagenes PNG: el patron de Meta (`EAA` + 40) casa con fragmentos de PNG. Un
   numero plausible y equivocado por exceso engana igual que uno por defecto.

**Los dos sentidos se prueban.** Cada patron tiene su test de que marca el
positivo y su test de que no marca el negativo parecido. Un test que solo
comprueba una direccion pasaria con un barrido que devuelve siempre `[]` o con
uno que marca todo.

Ninguna cadena de este archivo es una credencial real: todas son sinteticas y
con forma valida a proposito, que es justo lo que el barrido debe reconocer.
"""
import io

import pytest

from tools.barrer_secretos import (
    barrer_diff,
    barrer_texto,
    contar_lineas_anadidas,
    enmascarar,
    formatear,
    main,
)

# --- Cadenas sinteticas con la FORMA de cada secreto -------------------------
# Numero de bot + 35 caracteres, que es la forma que publica BotFather.
# La marca `barrido-ok` silencia la linea en el propio barrido: sin ella este
# archivo se denunciaria a si mismo en cada PR. Va en linea y no como exclusion
# de `tests/` para que cada uso quede visible en el diff.
TOKEN_TELEGRAM_FALSO = "8404009072:AAFalsoFalsoFalsoFalsoFalsoFalsoFal"  # barrido-ok: fixture con forma de token
# 'AIza' + 35 caracteres, la forma de una clave de API de Google.
CLAVE_GOOGLE_FALSA = "AIzaSyFALSAfalsaFALSAfalsaFALSAfalsaFAL"  # barrido-ok: fixture con forma de clave
# 'EAA' + 40, la forma de un token de Meta. Es la que colisiona con PNG.
TOKEN_META_FALSO = "EAA" + "FalsoFalsoFalsoFalsoFalsoFalsoFalsoFalso"

# Base64 real de un PNG de 1x1 px transparente. Empieza por la firma
# `iVBORw0KGgo`, que es `\x89PNG\r\n\x1a\n` codificado.
PNG_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk"
    "YPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)

# Un SHA-1 de commit de este mismo repositorio. Es publico y no es un secreto.
HASH_DE_COMMIT = "393c511f036ee0bae2dbfbd01d56f16d2f3bf906"

# Telefono sintetico de 10 digitos (lada 55 + secuencia). No es de nadie.
TELEFONO_SIN_ENMASCARAR = "5512345678"  # barrido-ok: telefono sintetico de prueba
# La forma que exige la regla del proyecto para logs y commits.
TELEFONO_ENMASCARADO = "+52...5678"


def _tipos(hallazgos):
    return sorted(h.tipo for h in hallazgos)


class TestPositivosConocidos:
    """Lo que el barrido TIENE que encontrar.

    Sin estos, el cero del barrido no significa nada: podria estar devolviendo
    lista vacia siempre.
    """

    def test_marca_un_token_con_forma_de_telegram(self):
        hallazgos = barrer_texto(f'TOKEN = "{TOKEN_TELEGRAM_FALSO}"')

        assert _tipos(hallazgos) == ["telegram"]

    def test_marca_una_clave_con_forma_de_google_api(self):
        hallazgos = barrer_texto(f"clave={CLAVE_GOOGLE_FALSA}")

        assert _tipos(hallazgos) == ["google_api_key"]

    def test_marca_un_telefono_de_diez_digitos_sin_enmascarar(self):
        hallazgos = barrer_texto(f"logger.info('cliente {TELEFONO_SIN_ENMASCARAR}')")

        assert _tipos(hallazgos) == ["telefono_mx"]


class TestNegativosConocidos:
    """Lo que el barrido NO debe marcar, aunque se le parezca.

    Cada uno de estos casos ya genero ruido real. Un gate que grita en todos los
    PR deja de leerse, y entonces da igual lo bien que detecte.
    """

    def test_no_marca_base64_de_imagen_png(self):
        """El caso de los 2,156 falsos positivos.

        Se comprueba en las DOS direcciones dentro del mismo test: la misma
        cadena con forma de token de Meta SE marca cuando esta suelta, y NO se
        marca cuando viaja dentro del blob de una imagen. Si el filtro de ruido
        desapareciera, la primera asercion seguiria pasando y la segunda no: por
        eso hacen falta las dos.
        """
        assert _tipos(barrer_texto(TOKEN_META_FALSO)) == ["meta"]

        assert barrer_texto(f'ICONO = "{PNG_BASE64}"') == []

    def test_un_secreto_que_comparte_linea_con_una_imagen_si_se_marca(self):
        """El filtro de ruido no puede tragarse la linea entera.

        La primera version preguntaba si la linea contenia `data:image/` en
        cualquier posicion, y con eso un secreto real que compartiera linea con
        el icono en base64 de un HTML desaparecia del informe. El barrido tenia
        su propio modo de invisibilidad, que es justo lo que existe para evitar.
        """
        linea = (
            f'<img src="data:image/png;base64,{PNG_BASE64}"> '
            f'CLAVE = "{CLAVE_GOOGLE_FALSA}"'
        )

        assert _tipos(barrer_texto(linea)) == ["google_api_key"]

    def test_no_marca_un_hash_de_commit(self):
        hallazgos = barrer_texto(f"Revisar el commit {HASH_DE_COMMIT} antes de mergear")

        assert hallazgos == []

    def test_no_marca_un_telefono_ya_enmascarado(self):
        hallazgos = barrer_texto(f"logger.info('cliente {TELEFONO_ENMASCARADO}')")

        assert hallazgos == []


class TestNoFiltraElValor:
    """Un barrido que imprime la credencial que encontro la propaga al log.

    La regla del entorno es explicita: las credenciales se identifican por
    nombre de variable y archivo:linea, o por prefijo+sufijo enmascarado, nunca
    por su valor. El log de GitHub Actions es publico para quien tenga acceso al
    repo y queda archivado.
    """

    def test_el_hallazgo_no_lleva_el_secreto_completo(self):
        hallazgo = barrer_texto(f'TOKEN = "{TOKEN_TELEGRAM_FALSO}"')[0]

        assert TOKEN_TELEGRAM_FALSO not in hallazgo.muestra
        assert hallazgo.muestra.startswith(TOKEN_TELEGRAM_FALSO[:4])
        assert hallazgo.muestra.endswith(TOKEN_TELEGRAM_FALSO[-4:])

    def test_enmascarar_no_reconstruye_cadenas_cortas(self):
        """Con una cadena corta, prefijo+sufijo la reconstruiria entera."""
        assert enmascarar("corta") == "(oculto)"


class TestBarridoSobreElDiff:
    """El barrido corre sobre el diff del PR, no sobre el repositorio entero.

    El historial de git de este proyecto YA tiene el TELEGRAM_TOKEN dentro (~14
    copias, su rotacion es gate del owner). Un barrido sobre el historial
    marcaria todos los PR desde el primer dia.
    """

    def test_solo_mira_las_lineas_anadidas(self):
        diff = "\n".join([
            "diff --git a/ejemplo.py b/ejemplo.py",
            "--- a/ejemplo.py",
            "+++ b/ejemplo.py",
            "@@ -1,2 +1,2 @@",
            f'-TOKEN = "{TOKEN_TELEGRAM_FALSO}"',
            ' sin_cambios = "%s"' % CLAVE_GOOGLE_FALSA,
        ])

        assert barrer_diff(diff) == []

    def test_atribuye_el_hallazgo_a_su_archivo_y_a_su_linea(self):
        diff = "\n".join([
            "diff --git a/config.py b/config.py",
            "--- a/config.py",
            "+++ b/config.py",
            "@@ -0,0 +1,2 @@",
            "+# configuracion",
            f'+TOKEN = "{TOKEN_TELEGRAM_FALSO}"',
        ])

        hallazgo = barrer_diff(diff)[0]

        assert hallazgo.archivo == "config.py"
        assert hallazgo.tipo == "telegram"
        assert hallazgo.linea == 2

    def test_el_marcador_de_archivo_no_se_confunde_con_una_linea_anadida(self):
        """`+++ b/...` empieza por '+' y no es contenido: no debe barrerse."""
        diff = "\n".join([
            f"diff --git a/{TOKEN_TELEGRAM_FALSO}.py b/{TOKEN_TELEGRAM_FALSO}.py",
            f"--- a/{TOKEN_TELEGRAM_FALSO}.py",
            f"+++ b/{TOKEN_TELEGRAM_FALSO}.py",
            "@@ -0,0 +1 @@",
            "+x = 1",
        ])

        assert barrer_diff(diff) == []


class TestExcepcionEnLinea:
    """El barrido necesita fixtures con forma de credencial para probarse.

    Sin un escape hatch, este mismo archivo dispararia el gate en cada PR. Se
    eligio una marca en linea y no excluir `tests/` entera: una carpeta excluida
    esconde para siempre lo que caiga dentro, mientras que cada uso de la marca
    aparece en el diff y un revisor lo ve.
    """

    def test_la_marca_silencia_la_linea(self):
        linea = f'TOKEN = "{TOKEN_TELEGRAM_FALSO}"  # barrido-ok: fixture'

        assert barrer_texto(linea) == []

    def test_sin_la_marca_la_misma_linea_se_marca(self):
        """La otra direccion: si esto pasara, la marca no estaria probando nada."""
        linea = f'TOKEN = "{TOKEN_TELEGRAM_FALSO}"  # fixture'

        assert _tipos(barrer_texto(linea)) == ["telegram"]

    def test_la_marca_sin_motivo_no_silencia(self):
        """Saltarse el barrido cuesta escribir en el diff por que se hizo.

        Sin motivo obligatorio, `barrido-ok` a secas seria un bypass anonimo el
        dia que el job pase a `--estricto`.
        """
        linea = f'TOKEN = "{TOKEN_TELEGRAM_FALSO}"  # barrido-ok'

        assert _tipos(barrer_texto(linea)) == ["telegram"]


class TestNoSeTragaSusErrores:
    """Un barrido que atrapa su excepcion devuelve cero hallazgos y PARECE exito.

    Es exactamente el modo de fallo que hace inutil un gate de seguridad: el
    check sale verde porque el script se rompio, no porque el diff este limpio.
    """

    def test_un_diff_que_no_es_texto_revienta_en_vez_de_devolver_vacio(self):
        with pytest.raises((TypeError, AttributeError)):
            barrer_diff(b"\x89PNG\r\n\x1a\n")

    def test_un_texto_que_no_es_str_tambien_revienta(self):
        """El guardia gemelo de `barrer_texto`, que se importa desde los tests."""
        with pytest.raises((TypeError, AttributeError)):
            barrer_texto(b"TOKEN")

    def test_un_diff_vacio_no_se_informa_como_diff_limpio(self):
        """Cero hallazgos con cero material NO es lo mismo que cero con material.

        Un SHA base mal calculado produce un diff vacio sin error: `git diff`
        sale con 0 y el resumen diria "barrido limpio" habiendo mirado nada.
        """
        vacio = formatear([], contar_lineas_anadidas(""))
        limpio = formatear([], contar_lineas_anadidas("+x = 1"))

        assert vacio != limpio
        assert "sin material" in vacio
        assert "1 lineas anadidas" in limpio


class TestFalsosNegativosCorregidos:
    """Cuatro huecos que el barrido tenia y por los que se colaba un secreto.

    Cada uno se detecto en revision, no en produccion. Van juntos porque
    comparten la misma moraleja: en un barrido, el fallo caro no es marcar de
    mas, es callar. Marcar de mas se lee y se descarta; callar no se nota.
    """

    def test_marca_un_telefono_con_lada_pegada(self):
        """`525512345678`: lada 52 + 10 digitos, el formato de WhatsApp.

        El patron de 10 digitos exige no-digitos a los lados, y dentro de una
        tirada de 12 ninguna ventana de 10 los tiene: el numero pasaba entero.
        """
        hallazgos = barrer_texto("wa.me/525512345678")  # barrido-ok: telefono de prueba

        assert _tipos(hallazgos) == ["telefono_mx"]

    def test_marca_un_hexadecimal_en_mayusculas(self):
        """Con la clase en minusculas, una sola mayuscula lo volvia invisible.

        No casaba entero (por la mayuscula) ni por su tramo en minuscula (que
        quedaba pegado a un caracter excluido por el lookaround).
        """
        clave = "ABCDEF0123456789abcdef0123456789ABC"  # 35, ni 40 ni 64

        assert _tipos(barrer_texto(f"hmac = {clave}")) == ["hex_largo"]

    def test_marca_un_token_de_meta_mas_largo_que_doscientos(self):
        """Habia un corte por largo que daba por volcado todo lo que pasara de 200.

        Los tokens de larga duracion de Meta pasan de 200 con normalidad, asi
        que el corte convertia justo al token mas real en un falso negativo.
        """
        largo = "EAA" + ("Falso123" * 30)  # 243 caracteres

        assert _tipos(barrer_texto(largo)) == ["meta"]

    def test_el_marcador_de_sin_salto_final_no_desplaza_la_numeracion(self):
        """`\\ No newline at end of file` es metadato, no contenido.

        Cuando un cambio toca el final del archivo, el marcador cae ENTRE la
        linea quitada y la anadida, y si contaba como linea desplazaba en uno el
        numero que se le atribuye al hallazgo.
        """
        diff = "\n".join([
            "diff --git a/x.py b/x.py",
            "--- a/x.py",
            "+++ b/x.py",
            "@@ -1 +1 @@",
            "-viejo = 1",
            "\\ No newline at end of file",
            f'+TOKEN = "{TOKEN_TELEGRAM_FALSO}"',
            "\\ No newline at end of file",
        ])

        assert barrer_diff(diff)[0].linea == 1


class TestSecretosDelPropioPanel:
    """Los secretos del panel no tienen forma reconocible: se buscan por nombre.

    `PANEL_DASHBOARD_TOKEN`, `SECRET_KEY` y `WORKER_TOKEN` son salidas de un
    generador aleatorio, indistinguibles de cualquier cadena. Sin una regla por
    nombre de variable, el secreto mas probable de este repositorio seria justo
    el unico que el barrido no marcaria.
    """

    def test_marca_un_token_del_panel_asignado_en_codigo(self):
        hallazgos = barrer_texto('PANEL_DASHBOARD_TOKEN = "valorLargoDePrueba123"')

        assert _tipos(hallazgos) == ["secreto_del_panel"]

    def test_enmascara_el_valor_pero_deja_leer_el_nombre(self):
        """El nombre es lo que hay que poder leer; el valor, lo que hay que tapar."""
        hallazgo = barrer_texto('SECRET_KEY = "valorLargoDePrueba123"')[0]

        assert "valorLargoDePrueba123" not in hallazgo.muestra
        assert hallazgo.muestra.startswith("valo")

    def test_no_marca_una_lectura_del_entorno(self):
        """`os.environ.get("SECRET_KEY", "")` es lo correcto, no un hallazgo."""
        hallazgos = barrer_texto('clave = os.environ.get("SECRET_KEY", "")')

        assert hallazgos == []

    def test_no_marca_la_plantilla_de_entorno_sin_valor(self):
        """`.env.example` lista nombres sin valores: no hay nada que filtrar."""
        assert barrer_texto("PANEL_DASHBOARD_TOKEN=") == []

    def test_no_marca_un_grep_de_la_variable_en_un_script(self):
        """Falso positivo real, encontrado barriendo el propio repositorio.

        El RUNBOOK trae un `grep "^PANEL_DASHBOARD_TOKEN=" /srv/panel/.env`, y
        el patron leia la ruta que venia detras como si fuera el valor asignado.
        Por eso el valor no puede llevar espacios ni empezar por `/`.
        """
        linea = 'TOK=$(grep "^PANEL_DASHBOARD_TOKEN=" /srv/panel/.env | cut -d= -f2)'

        assert barrer_texto(linea) == []


class TestCodigoDeSalida:
    """`main` es quien decidira verde o rojo cuando el gate pase a bloquear.

    Hoy el job avisa y no bloquea, asi que esta logica no se ejerce en CI. Por
    eso mismo necesita test: un `or` donde va un `and` pasaria desapercibido
    hasta el dia que se anada `--estricto`, que es justo el dia en que importa.
    """

    DIFF_SUCIO = "\n".join([
        "+++ b/x.py",
        "@@ -0,0 +1 @@",
        f'+TOKEN = "{TOKEN_TELEGRAM_FALSO}"',
    ])
    DIFF_LIMPIO = "\n".join(["+++ b/x.py", "@@ -0,0 +1 @@", "+x = 1"])

    @pytest.mark.parametrize("diff, estricto, esperado", [
        (DIFF_LIMPIO, False, 0),
        (DIFF_LIMPIO, True, 0),
        (DIFF_SUCIO, False, 0),   # avisa pero no bloquea
        (DIFF_SUCIO, True, 1),    # la unica combinacion que sale en rojo
    ])
    def test_las_cuatro_combinaciones(self, diff, estricto, esperado, monkeypatch):
        monkeypatch.setattr("sys.stdin", io.StringIO(diff))
        argumentos = ["--estricto"] if estricto else []

        assert main(argumentos) == esperado
