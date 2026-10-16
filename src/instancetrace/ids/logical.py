"""Byte layout for logical ids, event ids, and source revisions.

Logical id preimage, domain ``instancetrace.logical.v1``::

    u32le strlen + utf-8 namespace
    u32le strlen + utf-8 source_path
    u32le parent_count
    parent_count × 16 raw bytes, declared order
    u32le strlen + utf-8 branch_id
    u8 sample mode (0 authored int, 1 index, 2 authored text)
    when mode is 0 or 1: i64le sample key
    when mode is 2: u32le strlen + utf-8 sample key
    i64le seed

The digest is BLAKE2b-128. Python's built-in ``hash()`` is not used.
Frame and epoch are coordinates and are absent from this preimage.
"""

from __future__ import annotations

import hashlib
from typing import Any

from instancetrace.schema.canonical import canonical_bytes

DOMAIN_LOGICAL = b"instancetrace.logical.v1"
DOMAIN_EVENT = b"instancetrace.event.v1"
DOMAIN_REVISION = b"instancetrace.revision.v1"
DOMAIN_CONFIG = b"instancetrace.config.v1"

_MODE = {"authored": 0, "index": 1, "authored_text": 2}


def _u32(value: int) -> bytes:
    if value < 0 or value > 0xFFFFFFFF:
        raise ValueError("u32 out of range")
    return value.to_bytes(4, "little", signed=False)


def _i64(value: int) -> bytes:
    return int(value).to_bytes(8, "little", signed=True)


def _lp(text: str) -> bytes:
    raw = text.encode("utf-8")
    return _u32(len(raw)) + raw


def _digest(prefix: bytes, payload: bytes) -> bytes:
    return hashlib.blake2b(prefix + payload, digest_size=16).digest()


def logical_preimage(
    *,
    namespace: str,
    source_path: str,
    parent_ids: tuple[bytes, ...],
    branch_id: str,
    sample_key: int | str,
    sample_key_mode: str,
    seed: int,
) -> bytes:
    mode = _MODE.get(sample_key_mode)
    if mode is None:
        raise ValueError(f"unknown sample key mode {sample_key_mode}")
    parts = [
        _lp(namespace),
        _lp(source_path),
        _u32(len(parent_ids)),
    ]
    for parent in parent_ids:
        if len(parent) != 16:
            raise ValueError("parent logical id must be 16 bytes")
        parts.append(parent)
    parts.append(_lp(branch_id))
    parts.append(bytes([mode]))
    if mode == 2:
        if not isinstance(sample_key, str):
            raise ValueError("authored_text sample keys are strings")
        parts.append(_lp(sample_key))
    else:
        if isinstance(sample_key, str):
            raise ValueError("numeric sample key required")
        parts.append(_i64(int(sample_key)))
    parts.append(_i64(int(seed)))
    return b"".join(parts)


def logical_id_bytes(**kwargs: Any) -> bytes:
    return _digest(DOMAIN_LOGICAL, logical_preimage(**kwargs))


def config_fingerprint(config: dict[str, Any]) -> bytes:
    return _digest(DOMAIN_CONFIG, canonical_bytes(config))


def event_id_bytes(
    *,
    graph_id: str,
    source_revision: str,
    event_type: str,
    instrumented_path: str,
    seed: int | None,
    parent_event_ids: tuple[bytes, ...],
    config: dict[str, Any],
    ordinal: int,
) -> bytes:
    parts = [
        _lp(graph_id),
        _lp(source_revision),
        _lp(event_type),
        _lp(instrumented_path),
        bytes([0 if seed is None else 1]),
        _i64(0 if seed is None else int(seed)),
        _u32(int(ordinal)),
        _u32(len(parent_event_ids)),
    ]
    for parent in parent_event_ids:
        if len(parent) != 16:
            raise ValueError("parent event id must be 16 bytes")
        parts.append(parent)
    parts.append(config_fingerprint(config))
    return _digest(DOMAIN_EVENT, b"".join(parts))


def revision_bytes(declaration: dict[str, Any]) -> bytes:
    return _digest(DOMAIN_REVISION, canonical_bytes(declaration))
