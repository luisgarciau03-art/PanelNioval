"""Inspección de solo lectura de la hoja LISTA DE CONTACTOS (Plan 4, T4.1 — gate de datos).

Imprime los encabezados y el estado de la columna T (índice 20) para confirmar que
está libre antes de escribir correos. NO escribe nada.

Uso (en la PC del owner, con credenciales):
    set GOOGLE_CREDENTIALS_JSON=...   (o dejar el .json local del panel)
    python tools/inspeccionar_contactos.py
"""
import os
import sys

# Permite importar `app` (get_gs_client, SHEET_IDS) desde la raíz del proyecto.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app  # noqa: E402

COL_T = 20  # columna T (1-based)


def main():
    client = app.get_gs_client()
    ws = client.open_by_key(app.SHEET_IDS["contactos"]).worksheet("LISTA DE CONTACTOS")
    filas = ws.get_all_values()
    if not filas:
        print("Hoja vacía.")
        return
    headers = filas[0]
    print(f"Total columnas: {len(headers)}")
    print("Encabezados:")
    for i, h in enumerate(headers, start=1):
        marca = "  <-- COLUMNA T" if i == COL_T else ""
        print(f"  {i:>2}. {h!r}{marca}")

    header_t = headers[COL_T - 1] if len(headers) >= COL_T else "(no existe)"
    print(f"\nHeader de la columna T (idx {COL_T}): {header_t!r}")

    # Muestras y % de ocupación de la columna T.
    ocupadas, muestras = 0, []
    for fila in filas[1:]:
        val = fila[COL_T - 1] if len(fila) >= COL_T else ""
        if str(val).strip():
            ocupadas += 1
            if len(muestras) < 5:
                muestras.append(val)
    total = max(1, len(filas) - 1)
    print(f"Filas con columna T ocupada: {ocupadas}/{len(filas) - 1} ({100 * ocupadas // total}%)")
    print("Muestras (máx 5):", muestras)
    print("\nVEREDICTO: si el header es 'CORREO'/'EMAIL' o la columna está vacía → proceder.")
    print("Si contiene otro dato distinto a correo → BLOQUEAR y avisar al owner.")


if __name__ == "__main__":
    main()
