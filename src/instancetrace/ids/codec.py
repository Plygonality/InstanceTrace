"""Hex ids and the signed int32 attribute packing used by Blender.

Geometry Nodes integer attributes are signed 32-bit. A 128-bit id is stored
as four little-endian int32 values named ``it_lid_0`` .. ``it_lid_3``.
"""

from __future__ import annotations

_WIDTH = 16


def format_id(raw: bytes) -> str:
    if len(raw) != _WIDTH:
        raise ValueError("id must be 16 bytes")
    return "0x" + raw.hex()


def parse_id(text: str) -> bytes:
    if not isinstance(text, str) or not text.startswith("0x") or len(text) != 34:
        raise ValueError("logical id must look like 0x followed by 32 hexadecimal digits")
    try:
        raw = bytes.fromhex(text[2:])
    except ValueError as exc:
        raise ValueError("logical id is not hexadecimal") from exc
    if len(raw) != _WIDTH:
        raise ValueError("logical id must be 16 bytes")
    return raw


def pack_int32x4(raw: bytes) -> tuple[int, int, int, int]:
    if len(raw) != _WIDTH:
        raise ValueError("id must be 16 bytes")
    values = []
    for index in range(4):
        chunk = int.from_bytes(raw[index * 4 : (index + 1) * 4], "little", signed=False)
        if chunk >= 2**31:
            chunk -= 2**32
        values.append(chunk)
    return (values[0], values[1], values[2], values[3])


def unpack_int32x4(values: tuple[int, int, int, int] | list[int]) -> bytes:
    if len(values) != 4:
        raise ValueError("expected four int32 components")
    parts = []
    for value in values:
        number = int(value)
        if number < -(2**31) or number > 2**31 - 1:
            raise ValueError("int32 component out of range")
        parts.append(int(number).to_bytes(4, "little", signed=True))
    return b"".join(parts)
