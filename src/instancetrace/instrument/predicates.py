"""Tiny predicate language. There is no ``eval``."""

from __future__ import annotations

import re

_MOD = re.compile(r"^sample_key % (?P<mod>[1-9]\d*) == (?P<rem>0|[1-9]\d*)$")


def discards(predicate: str, sample_key: int) -> bool:
    if predicate == "never":
        return False
    match = _MOD.fullmatch(predicate)
    if match is None:
        raise ValueError(f"unsupported filter predicate {predicate!r}")
    modulus = int(match.group("mod"))
    remainder = int(match.group("rem"))
    return int(sample_key) % modulus == remainder
