"""Respalda a XLSX los spreadsheets del panel antes de una prueba de escritura.

Uso:  python tools/respaldar_hojas.py docs/auditoria/respaldos/2026-08-18

Guarda un .xlsx por spreadsheet mas huellas.json con el SHA-256 de los
encabezados de cada hoja. Las huellas permiten demostrar despues de la prueba
que el orden de columnas no se altero: las hojas estan sincronizadas con
proyectos externos y reordenarlas los romperia.
"""
import hashlib
import json
import os
import pathlib
import sys
import time

import gspread
from gspread.exceptions import APIError
from google.auth.transport.requests import AuthorizedSession
from google.oauth2.service_account import Credentials

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

# app.py revienta al importarse si falta PANEL_DASHBOARD_TOKEN (guarda fail-closed,
# app.py:34-44). Esta herramienta es un CLI de solo lectura: no abre puerto ni sirve
# ninguna ruta, asi que usa el escape hatch documentado para poder leer SHEET_IDS.
# Es el mismo mecanismo que usa tests/conftest.py.
os.environ.setdefault("PANEL_AUTH_DESACTIVADA", "1")

from app import SHEET_IDS  # noqa: E402  (fuente de verdad de los IDs)

RAIZ = pathlib.Path(__file__).resolve().parents[1]

# La ruta de credenciales se lee del entorno, igual que en app.py. Hardcodear el
# nombre del archivo fue justo el fallo que habria reventado Sheets en el VPS.
CREDENCIALES = os.environ.get(
    "GOOGLE_CREDENTIALS_FILE",
    str(RAIZ / "bubbly-subject-412101-c969f4a975c5.json"),
)

ALCANCES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]


def _con_reintentos(operacion, intentos=5):
    """Reintenta ante el 429 de cuota de Sheets, que es transitorio por definicion:
    el limite es por minuto, asi que esperar lo resuelve."""
    for intento in range(intentos):
        try:
            return operacion()
        except APIError as e:
            if "429" not in str(e) or intento == intentos - 1:
                raise
            espera = 15 * (intento + 1)
            print(f"  ... cuota agotada, esperando {espera}s")
            time.sleep(espera)


def main():
    if len(sys.argv) < 2:
        sys.exit("Uso: python tools/respaldar_hojas.py <directorio-destino>")

    if not pathlib.Path(CREDENCIALES).is_file():
        sys.exit(f"No existe el archivo de credenciales: {CREDENCIALES}")

    destino = pathlib.Path(sys.argv[1])
    destino.mkdir(parents=True, exist_ok=True)

    creds = Credentials.from_service_account_file(CREDENCIALES, scopes=ALCANCES)
    sesion = AuthorizedSession(creds)
    cliente = gspread.authorize(creds)

    # 7 claves de SHEET_IDS apuntan a 5 spreadsheets: `contactos`/`frecuentes` comparten
    # uno y `seguimiento`/`bruce` otro. Se agrupa por ID para no descargar ni huellear dos
    # veces la misma hoja, que es lo que hacia tardar el respaldo el doble de lo necesario.
    por_id = {}
    for clave, sid in SHEET_IDS.items():
        por_id.setdefault(sid, []).append(clave)

    huellas = {}
    for sid, claves in sorted(por_id.items()):
        claves = sorted(claves)
        nombre = "-".join(claves)
        r = sesion.get(
            f"https://docs.google.com/spreadsheets/d/{sid}/export?format=xlsx"
        )
        r.raise_for_status()
        destino_xlsx = destino / f"{nombre}-{sid}.xlsx"
        destino_xlsx.write_bytes(r.content)

        # Un respaldo que no se comprueba no es un respaldo: una pagina de error de
        # Google se descarga con HTTP 200 y pesa un par de KB.
        tam = destino_xlsx.stat().st_size
        if tam < 5000:
            sys.exit(
                f"Respaldo sospechoso: {destino_xlsx.name} pesa {tam} bytes. "
                "Probablemente sea una pagina de error, no una hoja."
            )

        # Los encabezados se piden en UNA sola llamada por spreadsheet, no una por
        # hoja: la cuota de Sheets es de 60 lecturas por minuto y por usuario, y el
        # bucle hoja-por-hoja la agotaba a mitad del respaldo con un 429.
        libro = cliente.open_by_key(sid)
        hojas = libro.worksheets()
        rangos = [f"'{h.title}'!1:1" for h in hojas]
        respuesta = _con_reintentos(lambda: libro.values_batch_get(rangos))
        rangos_valores = respuesta.get("valueRanges", [])

        for hoja, rango in zip(hojas, rangos_valores):
            filas = rango.get("values") or [[]]
            encabezados = filas[0]
            huellas[f"{nombre}/{hoja.title}"] = {
                "spreadsheet_id": sid,
                "claves": claves,
                "sha256_encabezados": hashlib.sha256(
                    "".join(encabezados).encode("utf-8")).hexdigest(),
                "columnas": len(encabezados),
                "filas": hoja.row_count,
            }
        print(f"  OK  {nombre} ({tam:,} bytes, {len(hojas)} hojas)")

    (destino / "huellas.json").write_text(
        json.dumps(huellas, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\n{len(huellas)} hojas con huella. Respaldo en {destino}")


if __name__ == "__main__":
    main()
