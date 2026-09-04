"""Mide cuantas filas historicas pudieron guardarse con la fecha desplazada (M2).

Plan 5 · T5.3, punto 4. El contenedor corria en UTC y Mexico es UTC-6, asi que
lo capturado entre las 18:00 y las 23:59 hora local se guardaba con la fecha del
DIA SIGUIENTE y con una hora entre 00:00 y 05:59.

Este script SOLO CUENTA. No reescribe nada: corregir historico de clientes sin
que el owner lo pida es una operacion destructiva encubierta (SUPUESTO de §2.1
del plan, riesgo R7).

Lee el RESPALDO en disco, no las hojas de produccion: no hace ni una llamada de
red y no puede alterar nada por accidente.

Uso:  python tools/medir_desfase_horario.py docs/auditoria/respaldos/2026-09-04
"""
import collections
import glob
import pathlib
import re
import sys

import openpyxl

# La consola de Windows es cp1252 y revienta al imprimir lo que no existe ahi,
# llevandose por delante lo que viniera despues.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Ventana sospechosa en hora local: lo escrito entre las 18:00 y medianoche de
# Mexico aparece guardado entre las 00:00 y las 06:00.
HORA_DESDE, HORA_HASTA = 0, 6

# Hojas que reciben un timestamp escrito por el panel, con la columna que lo
# lleva. Se identifican por encabezado, no por indice: reordenar la hoja
# rompe los proyectos externos sincronizados con ella, asi que el indice no es
# estable pero el nombre si.
OBJETIVOS = {
    "Respuestas de formulario 1": ["marca temporal", "fecha", "timestamp"],
    "ENVIOS_CATALOGO": ["fecha_solicitud", "timestamp_estado"],
    "PROSPECTOS BRUCE": ["fecha"],
}

# dd/mm/aaaa hh:mm[:ss]  — el formato que escriben app.py y nucleo_catalogo.
PATRON = re.compile(r"^\s*(\d{1,2})/(\d{1,2})/(\d{4})[ ,]+(\d{1,2}):(\d{2})")


def hora_de(valor):
    """Devuelve (hora 0-23, escrita_por_el_panel) o (None, _) si no lleva hora.

    El segundo dato importa mas que el primero. La columna A de 'Respuestas de
    formulario 1' la escriben DOS fuentes: Google Forms, cuya marca temporal
    llega como celda de fecha real y NO la toca este bug, y el panel, que
    escribe una CADENA con `value_input_option='RAW'`. Contar las dos juntas
    diluye el porcentaje y da un numero tranquilizador que no responde a la
    pregunta: solo las filas del panel pudieron guardarse desplazadas.
    """
    if valor is None:
        return None, False
    if hasattr(valor, "hour") and hasattr(valor, "year"):
        return valor.hour, False           # celda de fecha: la puso Google Forms
    m = PATRON.match(str(valor))
    if not m:
        return None, False
    return int(m.group(4)), True           # texto: lo escribio el panel


def medir(directorio: pathlib.Path) -> int:
    total_general = collections.Counter()
    hubo_columna = False

    for ruta in sorted(glob.glob(str(directorio / "*.xlsx"))):
        wb = openpyxl.load_workbook(ruta, read_only=True, data_only=True)
        for hoja, columnas in OBJETIVOS.items():
            if hoja not in wb.sheetnames:
                continue
            ws = wb[hoja]
            filas = ws.iter_rows(values_only=True)
            try:
                encabezados = [str(c or "").strip().lower() for c in next(filas)]
            except StopIteration:
                continue

            indices = {
                col: encabezados.index(col)
                for col in columnas
                if col in encabezados
            }
            if not indices:
                continue
            hubo_columna = True

            conteo = collections.Counter()
            for fila in filas:
                for col, i in indices.items():
                    if i >= len(fila):
                        continue
                    h, del_panel = hora_de(fila[i])
                    if h is None:
                        continue
                    conteo[(col, "con_hora")] += 1
                    if del_panel:
                        conteo[(col, "del_panel")] += 1
                    if HORA_DESDE <= h < HORA_HASTA:
                        conteo[(col, "sospechosa")] += 1
                        if del_panel:
                            conteo[(col, "sospechosa_panel")] += 1

            for col in indices:
                con_hora = conteo[(col, "con_hora")]
                if not con_hora:
                    continue
                panel = conteo[(col, "del_panel")]
                sosp_panel = conteo[(col, "sospechosa_panel")]
                otras = con_hora - panel
                pct = (100.0 * sosp_panel / panel) if panel else 0.0
                print(f"  {hoja} :: {col}")
                print(f"      filas con hora            : {con_hora}")
                print(f"      escritas por el panel     : {panel}"
                      f"   (otras fuentes: {otras})")
                print(f"      del panel, 00:00-05:59    : {sosp_panel}  ({pct:.1f} %)")
                total_general["con_hora"] += con_hora
                total_general["del_panel"] += panel
                total_general["sospechosa"] += sosp_panel
        wb.close()

    if not hubo_columna:
        print("ERROR: no se encontro ninguna columna de timestamp conocida.")
        print("El barrido no puede devolver 0 valido si no alcanza el dato.")
        return 2

    con_hora = total_general["con_hora"]
    panel = total_general["del_panel"]
    sosp = total_general["sospechosa"]
    pct = (100.0 * sosp / panel) if panel else 0.0
    print()
    print(f"TOTAL filas con hora        : {con_hora}")
    print(f"TOTAL escritas por el panel : {panel}   <- el universo en riesgo")
    print(f"TOTAL sospechosas           : {sosp}  ({pct:.1f} % de las del panel)")
    print()
    print("Sospechosa = escrita por el panel entre 00:00 y 05:59, la ventana")
    print("donde caen las capturas de 18:00-23:59 hora de Mexico. NO es prueba")
    print("de desfase fila a fila: una captura real de madrugada cae igual ahi.")
    print()
    print("Y es una COTA SUPERIOR flojo por arriba en otro sentido: solo las")
    print("filas escritas desde el contenedor (UTC) pudieron desplazarse. Las")
    print("escritas desde la PC del owner ya estaban en hora de Mexico, y el")
    print("respaldo no distingue que proceso escribio cada fila.")
    print()
    print("NO se corrige nada. La decision sobre el historico es del owner.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    destino = pathlib.Path(sys.argv[1])
    if not destino.is_dir():
        print(f"ERROR: no existe el directorio {destino}")
        sys.exit(1)
    sys.exit(medir(destino))
