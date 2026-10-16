"""Structural validation after checksum verification."""

from __future__ import annotations

from typing import Any

from instancetrace.errors import ManifestValidationError
from instancetrace.graph.dag import cycle_nodes
from instancetrace.schema.canonical import reject_unhashable
from instancetrace.schema.enums import (
    CONFIDENCE_LEVELS,
    EVENT_TYPES,
    SAMPLE_MODES,
    CaptureMode,
    LossReason,
)
from instancetrace.schema.models import Event

_UNITS = frozenset({"meters", "blender_units", "none"})
_COORDS = frozenset({"right_handed_z_up", "right_handed_y_up", "unknown"})
_ID_WIDTH = 34  # "0x" + 32 hex chars


def _fail(message: str) -> None:
    raise ManifestValidationError(message)


def _check_id(value: str, label: str) -> None:
    if not isinstance(value, str) or len(value) != _ID_WIDTH or not value.startswith("0x"):
        _fail(f"{label} must be a 128-bit 0x id")
    try:
        int(value[2:], 16)
    except ValueError:
        _fail(f"{label} is not hexadecimal")


def validate_trace_dict(trace: dict[str, Any], events: list[Event], *, instance_count: int) -> None:
    try:
        reject_unhashable(trace)
    except ValueError as exc:
        _fail(str(exc))
    if trace.get("capture_mode") not in {mode.value for mode in CaptureMode}:
        _fail("capture_mode is not a known mode")
    if trace.get("units") not in _UNITS:
        _fail("units must be meters, blender_units, or none")
    if trace.get("coordinate_system") not in _COORDS:
        _fail("coordinate_system is not a known system")
    if not isinstance(trace.get("frame"), int):
        _fail("frame must be an integer")
    revision = trace.get("source_revision", "")
    if trace.get("capture_mode") != CaptureMode.PASSIVE_ONLY.value and revision:
        _check_id(revision, "source_revision")
    tables = trace.get("tables", {})
    if tables.get("confidences") != list(CONFIDENCE_LEVELS):
        _fail("confidence table does not match the v0.1 vocabulary")
    if tables.get("sample_modes") != list(SAMPLE_MODES):
        _fail("sample mode table does not match the v0.1 vocabulary")
    if int(trace.get("instance_count", -1)) != instance_count:
        _fail("instance_count does not match the array table")
    known_losses = {item.value for item in LossReason}
    for reason in tables.get("loss_reasons", []):
        if reason not in known_losses:
            _fail(f"unknown loss reason {reason}")
    ids = [event.event_id for event in events]
    if len(ids) != len(set(ids)):
        _fail("duplicate event id")
    known = set(ids)
    for event in events:
        _check_id(event.event_id, "event_id")
        if event.event_type not in EVENT_TYPES:
            _fail(f"unknown event type {event.event_type}")
        if event.confidence not in CONFIDENCE_LEVELS:
            _fail(f"unknown confidence {event.confidence}")
        if event.loss_reason is not None and event.loss_reason not in known_losses:
            _fail(f"unknown loss reason {event.loss_reason}")
        for parent in event.parent_event_ids:
            if parent not in known:
                _fail(f"event {event.event_id} references missing parent {parent}")
        for ancestor in event.candidate_ancestor_ids:
            if ancestor not in known:
                _fail(f"event {event.event_id} references missing candidate {ancestor}")
        try:
            reject_unhashable(event.config)
        except ValueError as exc:
            _fail(str(exc))
    cyclic = cycle_nodes(events)
    if cyclic:
        _fail("event graph contains a cycle: " + ",".join(cyclic))
