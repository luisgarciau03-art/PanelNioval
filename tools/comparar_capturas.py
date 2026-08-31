"""Compara dos juegos de capturas pixel a pixel.

La T4.3 es un refactor preservador de comportamiento: las tres superficies
tienen que verse **identicas** despues de moverlas a templates/ y static/.
"Se ven igual" no es una opinion; se mide.

Uso:
    python tools/comparar_capturas.py docs/diseno/antes docs/diseno/despues
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageChops


def comparar(a: Path, b: Path) -> tuple[bool, float, tuple[int, int], tuple[int, int]]:
    ia, ib = Image.open(a).convert("RGB"), Image.open(b).convert("RGB")
    if ia.size != ib.size:
        return False, 100.0, ia.size, ib.size
    diff = ImageChops.difference(ia, ib)
    caja = diff.getbbox()
    if caja is None:
        return True, 0.0, ia.size, ib.size
    # porcentaje de pixeles distintos
    distintos = sum(1 for p in diff.getdata() if p != (0, 0, 0))
    pct = 100.0 * distintos / (ia.size[0] * ia.size[1])
    return False, pct, ia.size, ib.size


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    dir_a, dir_b = Path(sys.argv[1]), Path(sys.argv[2])
    archivos = sorted(p.name for p in dir_a.glob("*.png"))
    if not archivos:
        print(f"no hay capturas en {dir_a}")
        return 2

    fallos = 0
    print(f"{'captura':24} {'veredicto':12} {'% distinto':>11}")
    print("-" * 50)
    for nombre in archivos:
        pa, pb = dir_a / nombre, dir_b / nombre
        if not pb.exists():
            print(f"{nombre:24} {'FALTA':12}")
            fallos += 1
            continue
        igual, pct, ta, tb = comparar(pa, pb)
        if igual:
            print(f"{nombre:24} {'identica':12} {pct:10.4f}%")
        else:
            extra = "" if ta == tb else f"  tamano {ta} vs {tb}"
            print(f"{nombre:24} {'DISTINTA':12} {pct:10.4f}%{extra}")
            fallos += 1

    print()
    if fallos:
        print(f"{fallos} de {len(archivos)} capturas difieren")
        return 1
    print(f"las {len(archivos)} capturas son identicas pixel a pixel")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
