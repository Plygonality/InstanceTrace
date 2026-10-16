"""Atomic JSON + NPZ manifests.

Write order: NPZ temp file, BLAKE2b-256 of those bytes, JSON temp file that
records both checksums, ``fsync``, then ``os.replace`` the NPZ and the JSON.
A reader rejects the manifest when either checksum disagrees. The JSON
checksum covers the canonical ``trace`` object and the event list inside it.
The NPZ checksum covers the array file the JSON names.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from instancetrace import TRACE_SCHEMA_VERSION
from instancetrace.errors import CorruptManifest
from instancetrace.schema.canonical import canonical_bytes
from instancetrace.schema.migrate import migrate
from instancetrace.schema.models import Event, TraceMeta
from instancetrace.schema.validate import validate_trace_dict
from instancetrace.storage.table import InstanceTable, build_index, empty_table

_ARRAY_KEYS = (
    "logical_id",
    "sample_key",
    "sample_mode",
    "branch_code",
    "source_code",
    "path_code",
    "event_code",
    "container_event_code",
    "alive",
    "confidence",
    "loss_code",
    "seed",
    "transform",
    "flags",
    "parent_indptr",
    "parent_ids",
    "candidate_indptr",
    "candidate_event_codes",
    "locator_offsets",
    "locator_utf8",
)


@dataclass
class LoadedTrace:
    meta: TraceMeta
    events: list[Event]
    table: InstanceTable
    index: dict[bytes, list[int]] = field(default_factory=dict)
    path: str | None = None

    def event_by_id(self) -> dict[str, Event]:
        return {event.event_id: event for event in self.events}

    def event_codes(self) -> dict[str, int]:
        return {event.event_id: index for index, event in enumerate(self.events)}


def _hash_bytes(payload: bytes) -> str:
    return hashlib.blake2b(payload, digest_size=32).hexdigest()


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def save_trace(trace: LoadedTrace, json_path: str | Path) -> Path:
    json_path = Path(json_path)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    npz_path = json_path.with_suffix(".npz")
    trace.meta.instance_count = len(trace.table)
    trace.meta.live_count = trace.table.live_count
    trace.meta.branches = list(trace.table.branches)
    trace.meta.sources = list(trace.table.sources)
    trace.meta.paths = list(trace.table.paths)
    trace.meta.loss_reasons = list(trace.table.loss_reasons)
    body = trace.meta.to_dict()
    body["events"] = [event.to_dict() for event in trace.events]
    payload = canonical_bytes(body)
    npz_tmp = npz_path.with_name(npz_path.name + ".tmp")
    json_tmp = json_path.with_name(json_path.name + ".tmp")
    trace.table.write_npz(str(npz_tmp))
    array_bytes = npz_tmp.read_bytes()
    envelope = {
        "manifest_kind": "instancetrace.trace",
        "trace_schema_version": TRACE_SCHEMA_VERSION,
        "arrays_file": npz_path.name,
        "checksum": {
            "algorithm": "blake2b-256",
            "canonical_trace": _hash_bytes(payload),
            "arrays": _hash_bytes(array_bytes),
        },
        "trace": body,
    }
    json_tmp.write_text(json.dumps(envelope, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with json_tmp.open("rb") as handle:
        os.fsync(handle.fileno())
    with npz_tmp.open("rb") as handle:
        os.fsync(handle.fileno())
    os.replace(npz_tmp, npz_path)
    os.replace(json_tmp, json_path)
    _fsync_directory(json_path.parent)
    return json_path


def load_trace(json_path: str | Path) -> LoadedTrace:
    json_path = Path(json_path)
    try:
        envelope = json.loads(json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CorruptManifest(f"cannot read manifest JSON: {exc}") from exc
    if not isinstance(envelope, dict) or envelope.get("manifest_kind") != "instancetrace.trace":
        raise CorruptManifest("not an instancetrace manifest")
    envelope = migrate(envelope)
    trace = envelope.get("trace")
    checksum = envelope.get("checksum") or {}
    if not isinstance(trace, dict) or checksum.get("algorithm") != "blake2b-256":
        raise CorruptManifest("manifest envelope is missing its checksum")
    payload = canonical_bytes(trace)
    if _hash_bytes(payload) != checksum.get("canonical_trace"):
        raise CorruptManifest("canonical trace checksum mismatch")
    arrays_name = envelope.get("arrays_file")
    if not isinstance(arrays_name, str) or Path(arrays_name).name != arrays_name:
        raise CorruptManifest("arrays_file must be a file name in the manifest directory")
    npz_path = json_path.parent / arrays_name
    try:
        array_bytes = npz_path.read_bytes()
    except OSError as exc:
        raise CorruptManifest(f"cannot read arrays: {exc}") from exc
    if _hash_bytes(array_bytes) != checksum.get("arrays"):
        raise CorruptManifest("array checksum mismatch")
    try:
        with np.load(npz_path) as archive:
            arrays = {key: archive[key] for key in _ARRAY_KEYS}
    except (OSError, KeyError, ValueError) as exc:
        raise CorruptManifest(f"array payload is unreadable: {exc}") from exc
    events = [Event.from_dict(item) for item in trace.get("events", [])]
    meta = TraceMeta.from_dict(trace)
    table = InstanceTable.from_arrays(
        arrays,
        {
            "branches": meta.branches,
            "sources": meta.sources,
            "paths": meta.paths,
            "loss_reasons": meta.loss_reasons,
            "confidences": meta.confidences,
            "sample_modes": meta.sample_modes,
        },
    )
    if len(table) != meta.instance_count:
        raise CorruptManifest("instance_count does not match arrays")
    validate_trace_dict(trace, events, instance_count=len(table))
    _validate_row_ranges(table, event_count=len(events))
    loaded = LoadedTrace(meta=meta, events=events, table=table, path=str(json_path))
    loaded.index = build_index(table)
    return loaded


def _validate_row_ranges(table: InstanceTable, *, event_count: int) -> None:
    count = len(table)
    if table.parent_indptr.shape != (count + 1,) or table.locator_offsets.shape != (count + 1,):
        raise CorruptManifest("ragged index arrays have the wrong length")
    if count and int(table.parent_indptr[-1]) != len(table.parent_ids):
        raise CorruptManifest("parent index does not cover parent ids")
    if int(table.candidate_indptr[-1]) != len(table.candidate_event_codes):
        raise CorruptManifest("candidate index does not cover candidate codes")
    if count and int(table.event_code.max()) >= event_count:
        raise CorruptManifest("instance references a missing event")
    if count and int(table.container_event_code.max()) >= event_count:
        raise CorruptManifest("instance references a missing container event")


def blank_trace(meta: TraceMeta) -> LoadedTrace:
    tables = {
        "branches": meta.branches,
        "sources": meta.sources,
        "paths": meta.paths,
        "loss_reasons": meta.loss_reasons,
        "confidences": meta.confidences,
        "sample_modes": meta.sample_modes,
    }
    return LoadedTrace(meta=meta, events=[], table=empty_table(tables), index={})
