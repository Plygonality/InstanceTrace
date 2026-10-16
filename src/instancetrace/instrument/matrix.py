"""4x4 row-major matrices in Blender's mathutils layout.

Translation lives in elements 3, 7 and 11. A child world matrix is
``parent @ local`` for column vectors.
"""

from __future__ import annotations


def translation_matrix(
    x: float,
    y: float,
    z: float,
    scale: float = 1.0,
) -> tuple[float, ...]:
    s = float(scale)
    return (
        s, 0.0, 0.0, float(x),
        0.0, s, 0.0, float(y),
        0.0, 0.0, s, float(z),
        0.0, 0.0, 0.0, 1.0,
    )


def matmul(left: tuple[float, ...], right: tuple[float, ...]) -> tuple[float, ...]:
    out = [0.0] * 16
    for row in range(4):
        for col in range(4):
            total = 0.0
            for k in range(4):
                total += left[row * 4 + k] * right[k * 4 + col]
            out[row * 4 + col] = total
    return tuple(out)


def identity() -> tuple[float, ...]:
    return translation_matrix(0.0, 0.0, 0.0, 1.0)
