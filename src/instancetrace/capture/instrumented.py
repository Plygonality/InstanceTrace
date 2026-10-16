"""Merge a Blender attribute dump with an optional authored program.

Host attribute bytes win. A program supplies the operation chain only for ids
that were actually read back and that match that program. Missing attributes
do not get a reconstructed chain.
"""

from __future__ import annotations

import platform
import sys
from typing import Any

from instancetrace.capture.locators import evaluated_locator
from instancetrace.ids.codec import unpack_int32x4
from instancetrace.instrument.execute import execute
from instancetrace.instrument.grammar import Program
from instancetrace.schema.canonical import decimal_string
from instancetrace.schema.enums import (
    CONFIDENCE_LEVELS,
    FLAG_NOT_OBSERVED,
    FLAG_SEED_UNKNOWN,
    SAMPLE_MODES,
    CaptureMode,
    Confidence,
    EventType,
    LossReason,
)
from instancetrace.schema.models import Event, HostInfo, TraceMeta
from instancetrace.storage.manifest import LoadedTrace
from instancetrace.storage.table import build_index, table_from_rows


def _require_dump(dump: dict) -> None:
    if dump.get("format") != "instancetrace.blender_capture":
        raise ValueError("not an instancetrace blender capture dump")
    if dump.get("capture_mode") != "INSTRUMENTED":
        raise ValueError("instrumented import requires capture_mode INSTRUMENTED")


def _locator(dump: dict, instance: dict) -> str:
    return evaluated_locator(
        scene_id=str(dump.get("scene_id") or "scene:unknown"),
        frame=int(dump.get("frame") or 0),
        parent_name=str(instance.get("parent_name") or ""),
        object_name=str(instance.get("object_name") or ""),
        persistent_id=instance.get("persistent_id") or (0,) * 8,
        evaluated_index=int(instance.get("evaluated_index") or 0),
        random_id=instance.get("random_id"),
    )


def _row_dict(trace: LoadedTrace, row: int) -> dict[str, Any]:
    table = trace.table
    logical = table.logical_id[row].tobytes() if table.has_logical_id(row) else None
    return {
        "logical_id": logical,
        "sample_key": int(table.sample_key[row]),
        "sample_mode": table.sample_modes[int(table.sample_mode[row])],
        "branch_id": table.decode(table.branches, int(table.branch_code[row])),
        "source_id": table.decode(table.sources, int(table.source_code[row])),
        "path": table.decode(table.paths, int(table.path_code[row])) or "",
        "event_code": int(table.event_code[row]),
        "container_event_code": int(table.container_event_code[row]),
        "alive": bool(table.alive[row]),
        "confidence": table.confidences[int(table.confidence[row])],
        "loss_reason": table.decode(table.loss_reasons, int(table.loss_code[row])),
        "seed": int(table.seed[row]),
        "transform": tuple(float(value) for value in table.transform[row].tolist()),
        "flags": int(table.flags[row]),
        "parent_ids": tuple(
            table.parent_ids[index].tobytes()
            for index in range(int(table.parent_indptr[row]), int(table.parent_indptr[row + 1]))
        ),
        "candidate_event_codes": table.candidate_codes(row),
        "locator": table.locator(row),
    }


def _codebook_value(codebook: dict, key: str, index: int | None) -> str | None:
    if index is None:
        return None
    values = codebook.get(key) or []
    if index < 0 or index >= len(values):
        return None
    return str(values[index])


def import_instrumented_dump(dump: dict, program: Program | None = None) -> LoadedTrace:
    _require_dump(dump)
    instances = list(dump.get("instances") or [])
    attributes_present = any(bool(item.get("attributes_read")) and item.get("it_lid") is not None for item in instances)
    if not attributes_present:
        return _unreadable(dump, program_supplied=program is not None)
    if program is None:
        return _attributes_only(dump)
    return _matched(dump, program)


def _host(dump: dict, trace: LoadedTrace) -> None:
    trace.meta.host.application = "Blender"
    trace.meta.host.version = str(dump.get("blender_version") or "unknown")
    trace.meta.capture_mode = CaptureMode.INSTRUMENTED.value
    trace.meta.frame = int(dump.get("frame") or trace.meta.frame)
    if dump.get("scene_id"):
        trace.meta.scene_id = str(dump["scene_id"])
    trace.meta.notes.append(f"attribute_read_path={dump.get('attribute_read_path') or 'unspecified'}")


def _unreadable(dump: dict, *, program_supplied: bool) -> LoadedTrace:
    """Attributes were not read. The authored program is ignored."""
    rows = []
    for instance in dump.get("instances") or []:
        rows.append(
            {
                "logical_id": None,
                "sample_key": 0,
                "sample_mode": "authored",
                "branch_id": None,
                "source_id": None,
                "path": "",
                "event_code": 0,
                "container_event_code": None,
                "alive": True,
                "confidence": Confidence.UNKNOWN.value,
                "loss_reason": LossReason.ATTRIBUTE_UNREADABLE.value,
                "seed": 0,
                "transform": tuple(float(value) for value in (instance.get("matrix_world") or [0.0] * 16)),
                "flags": FLAG_SEED_UNKNOWN,
                "parent_ids": (),
                "candidate_event_codes": [],
                "locator": _locator(dump, instance),
            }
        )
    event = Event(
        event_id="0x" + "00" * 16,
        event_type=EventType.UNSUPPORTED_OR_LOST.value,
        instrumented_path="",
        parent_event_ids=[],
        seed=None,
        notes="named attributes were not readable; no generator path was inferred",
        confidence=Confidence.UNKNOWN.value,
        loss_reason=LossReason.ATTRIBUTE_UNREADABLE.value,
        candidate_ancestor_ids=[],
        config={"program_supplied": program_supplied},
    )
    # A zero id is not a valid 0x id... format requires 32 hex digits. "0x" + 32 zeros is 34 chars. Good.
    # But event id of all zeros might collide with "no logical id". It's an event id, stored in JSON, OK.
    table = table_from_rows(rows, confidences=list(CONFIDENCE_LEVELS), sample_modes=list(SAMPLE_MODES))
    meta = TraceMeta(
        capture_mode=CaptureMode.INSTRUMENTED.value,
        graph_id="",
        source_revision="0x" + "00" * 16,
        scene_id=str(dump.get("scene_id") or "scene:unknown"),
        frame=int(dump.get("frame") or 0),
        epoch=dump.get("epoch"),
        seed=None,
        units=str(dump.get("units") or "blender_units"),
        unit_scale_to_meters=decimal_string(float(dump.get("unit_scale_to_meters") or 1.0)),
        coordinate_system=str(dump.get("coordinate_system") or "right_handed_z_up"),
        host=HostInfo(
            application="Blender",
            version=str(dump.get("blender_version") or "unknown"),
            python_version=".".join(str(part) for part in sys.version_info[:3]),
            platform=platform.platform(),
        ),
        notes=[
            "Attributes were not read from the evaluated geometry.",
            "The authored program was not used to fill logical ids or node paths.",
        ],
    )
    loaded = LoadedTrace(meta=meta, events=[event], table=table)
    loaded.index = build_index(table)
    return loaded


def _attributes_only(dump: dict) -> LoadedTrace:
    codebook = dump.get("codebook") or {}
    event = Event(
        event_id="0x" + "11" * 16,
        event_type=EventType.DERIVE_ATTRIBUTE.value,
        instrumented_path="",
        parent_event_ids=[],
        seed=None,
        notes="ids were read from named attributes; the operation chain was not in the capture",
        confidence=Confidence.PARTIAL.value,
        loss_reason=None,
        candidate_ancestor_ids=[],
        config={},
    )
    rows = []
    for instance in dump["instances"]:
        if not instance.get("attributes_read") or instance.get("it_lid") is None:
            continue
        logical = unpack_int32x4(instance["it_lid"])
        source = _codebook_value(codebook, "sources", instance.get("it_source"))
        branch = _codebook_value(codebook, "branches", instance.get("it_branch"))
        path = _codebook_value(codebook, "paths", instance.get("it_source")) or source or ""
        loss = None if source is not None and branch is not None else LossReason.CODEBOOK_MISSING.value
        rows.append(
            {
                "logical_id": logical,
                "sample_key": int(instance.get("it_sample") or 0),
                "sample_mode": "authored",
                "branch_id": branch,
                "source_id": source,
                "path": path,
                "event_code": 0,
                "container_event_code": None,
                "alive": True,
                "confidence": Confidence.PARTIAL.value,
                "loss_reason": loss,
                "seed": 0,
                "transform": tuple(float(value) for value in instance.get("matrix_world") or [0.0] * 16),
                "flags": FLAG_SEED_UNKNOWN,
                "parent_ids": (),
                "candidate_event_codes": [],
                "locator": _locator(dump, instance),
            }
        )
    table = table_from_rows(rows, confidences=list(CONFIDENCE_LEVELS), sample_modes=list(SAMPLE_MODES))
    meta = TraceMeta(
        capture_mode=CaptureMode.INSTRUMENTED.value,
        graph_id="",
        source_revision="0x" + "11" * 16,
        scene_id=str(dump.get("scene_id") or "scene:unknown"),
        frame=int(dump.get("frame") or 0),
        epoch=dump.get("epoch"),
        seed=None,
        units=str(dump.get("units") or "blender_units"),
        unit_scale_to_meters=decimal_string(float(dump.get("unit_scale_to_meters") or 1.0)),
        coordinate_system=str(dump.get("coordinate_system") or "right_handed_z_up"),
        host=HostInfo(
            application="Blender",
            version=str(dump.get("blender_version") or "unknown"),
            python_version=".".join(str(part) for part in sys.version_info[:3]),
            platform=platform.platform(),
        ),
        notes=["Attribute codes were read. No operation chain was attached because no program was supplied."],
    )
    loaded = LoadedTrace(meta=meta, events=[event], table=table)
    loaded.index = build_index(table)
    return loaded


def _matched(dump: dict, program: Program) -> LoadedTrace:
    predicted = execute(program, capture_mode=CaptureMode.INSTRUMENTED.value)
    observed: dict[bytes, dict] = {}
    for instance in dump.get("instances") or []:
        if not instance.get("attributes_read") or instance.get("it_lid") is None:
            continue
        observed[unpack_int32x4(instance["it_lid"])] = instance
    codebook = dump.get("codebook") or {}
    rows = []
    seen: set[bytes] = set()
    for index in range(len(predicted.table)):
        packed = _row_dict(predicted, index)
        logical = packed["logical_id"]
        if logical is None:
            rows.append(packed)
            continue
        instance = observed.get(logical)
        if instance is None:
            if packed["alive"]:
                packed["alive"] = False
                packed["confidence"] = Confidence.PARTIAL.value
                packed["loss_reason"] = LossReason.NOT_OBSERVED_AT_EVALUATION.value
                packed["flags"] = int(packed["flags"]) | FLAG_NOT_OBSERVED
            else:
                packed["confidence"] = Confidence.PARTIAL.value
                packed["loss_reason"] = packed["loss_reason"] or LossReason.NOT_IN_EVALUATED_SCENE.value
                packed["flags"] = int(packed["flags"]) | FLAG_NOT_OBSERVED
            rows.append(packed)
            continue
        seen.add(logical)
        host_source = _codebook_value(codebook, "sources", instance.get("it_source"))
        if host_source is not None and packed["source_id"] is not None and host_source != packed["source_id"]:
            packed["confidence"] = Confidence.PARTIAL.value
            packed["loss_reason"] = LossReason.ATTRIBUTE_PROGRAM_MISMATCH.value
            packed["source_id"] = host_source
            packed["event_code"] = None
        if instance.get("matrix_world"):
            packed["transform"] = tuple(float(value) for value in instance["matrix_world"])
        packed["locator"] = _locator(dump, instance)
        if dump.get("confidence_ceiling") == "PARTIAL" and packed["confidence"] == Confidence.EXACT.value:
            packed["confidence"] = Confidence.PARTIAL.value
            packed["loss_reason"] = str(dump.get("ceiling_reason") or LossReason.REALIZE_DOMAIN_CHANGE.value)
        rows.append(packed)
    mismatch_code = None
    extras = []
    for logical, instance in observed.items():
        if logical in seen or logical in predicted.index:
            continue
        if mismatch_code is None:
            mismatch_code = len(predicted.events)
            predicted.events.append(
                Event(
                    event_id="0x" + "ab" * 16,
                    event_type=EventType.UNSUPPORTED_OR_LOST.value,
                    instrumented_path="",
                    parent_event_ids=[],
                    seed=None,
                    notes="host attribute id is not in the authored program",
                    confidence=Confidence.PARTIAL.value,
                    loss_reason=LossReason.ATTRIBUTE_PROGRAM_MISMATCH.value,
                    candidate_ancestor_ids=[],
                    config={},
                )
            )
        extras.append(
            {
                "logical_id": logical,
                "sample_key": int(instance.get("it_sample") or 0),
                "sample_mode": "authored",
                "branch_id": _codebook_value(codebook, "branches", instance.get("it_branch")),
                "source_id": _codebook_value(codebook, "sources", instance.get("it_source")),
                "path": "",
                "event_code": mismatch_code,
                "container_event_code": None,
                "alive": True,
                "confidence": Confidence.PARTIAL.value,
                "loss_reason": LossReason.ATTRIBUTE_PROGRAM_MISMATCH.value,
                "seed": 0,
                "transform": tuple(float(value) for value in instance.get("matrix_world") or [0.0] * 16),
                "flags": FLAG_SEED_UNKNOWN,
                "parent_ids": (),
                "candidate_event_codes": [],
                "locator": _locator(dump, instance),
            }
        )
    table = table_from_rows(rows + extras, confidences=list(CONFIDENCE_LEVELS), sample_modes=list(SAMPLE_MODES))
    predicted.table = table
    predicted.index = build_index(table)
    predicted.meta.instance_count = len(table)
    predicted.meta.live_count = table.live_count
    _host(dump, predicted)
    predicted.meta.notes.append("Logical ids were taken from evaluated attributes and matched to the authored program.")
    return predicted
