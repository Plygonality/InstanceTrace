"""Unreal PCG lineage metadata is unverified in v0.1.

A future plugin would add source and lineage fields that the built-in Debug
Tree and point spreadsheet do not record. It would not duplicate those tools.
"""

from __future__ import annotations

from instancetrace.errors import UnverifiedHost


def trace_pcg(*_args: object, **_kwargs: object) -> None:
    raise UnverifiedHost(
        "Unreal PCG lineage has no verified host experiment in v0.1. "
        "Refusing to invent a trace from PCG debug data."
    )
