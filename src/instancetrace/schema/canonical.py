"""Canonical JSON used for checksums and fingerprints.

Floats are rejected. Callers format decimals as strings before hashing so
``1`` and ``1.0`` cannot fork a revision silently.
"""

from __future__ import annotations

import json
from typing import Any

from instancetrace.schema.enums import FORBIDDEN_CONFIG_KEYS


def reject_unhashable(value: Any, depth: int = 0) -> None:
    if depth > 32:
        raise ValueError("nested value exceeds depth 32")
    if value is None or isinstance(value, (str, bool)):
        return
    if isinstance(value, int):
        return
    if isinstance(value, list):
        for item in value:
            reject_unhashable(item, depth + 1)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("object keys must be strings")
            if key.lower() in FORBIDDEN_CONFIG_KEYS:
                raise ValueError(f"forbidden manifest key {key!r}")
            reject_unhashable(item, depth + 1)
        return
    raise ValueError(f"value type {type(value).__name__} is not allowed in a trace document")


def canonical_bytes(value: Any) -> bytes:
    reject_unhashable(value)
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def decimal_string(value: float) -> str:
    return format(float(value), ".9f")
