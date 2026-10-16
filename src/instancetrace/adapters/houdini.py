"""Houdini point and primitive lineage is unverified in v0.1."""

from __future__ import annotations

from instancetrace.errors import UnverifiedHost


def trace_points(*_args: object, **_kwargs: object) -> None:
    raise UnverifiedHost(
        "Houdini point/primitive lineage has no verified host experiment in v0.1. "
        "Refusing to invent a trace from a seed or a scene layout."
    )
