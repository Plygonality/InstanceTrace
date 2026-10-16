"""Backward queries over a loaded trace."""

from __future__ import annotations

from typing import Any

from instancetrace.graph.dag import causal_order
from instancetrace.ids.codec import parse_id
from instancetrace.schema.enums import (
    FLAG_INDEX_UNSTABLE,
    FLAG_SEED_UNKNOWN,
    CaptureMode,
    Confidence,
    EventType,
)
from instancetrace.schema.models import Event
from instancetrace.storage.manifest import LoadedTrace


def _origin(trace: LoadedTrace, row: int | None, *, found: bool) -> str:
    if trace.meta.capture_mode == CaptureMode.PASSIVE_ONLY.value:
        return "PASSIVE_ONLY" if found else "UNKNOWN_ORIGIN"
    if not found or row is None:
        return "NOT_IN_MANIFEST"
    table = trace.table
    confidence = table.confidences[int(table.confidence[row])]
    event = _event(trace, int(table.event_code[row]))
    event_type = event.event_type if event else ""
    if confidence == Confidence.AMBIGUOUS.value and event_type == EventType.LINEAGE_AMBIGUOUS.value:
        return "LINEAGE_AMBIGUOUS"
    if confidence == Confidence.AMBIGUOUS.value and event_type == EventType.UNSUPPORTED_OR_LOST.value:
        return "UNSUPPORTED_OR_LOST"
    if confidence == Confidence.AMBIGUOUS.value:
        return "LINEAGE_AMBIGUOUS"
    if confidence == Confidence.PARTIAL.value:
        return "PARTIAL_TRACE"
    if confidence == Confidence.UNKNOWN.value:
        return "UNKNOWN_ORIGIN"
    if confidence == Confidence.PASSIVE_ONLY.value:
        return "PASSIVE_ONLY"
    return "EXACT"


def _event(trace: LoadedTrace, code: int) -> Event | None:
    if code < 0 or code >= len(trace.events):
        return None
    return trace.events[code]


def _revision_status(trace: LoadedTrace, scene_revision: str | None) -> str:
    if scene_revision is None:
        return "NOT_CHECKED"
    if scene_revision == trace.meta.source_revision:
        return "MATCH"
    return "INCOMPATIBLE"


def _operation(event: Event) -> dict[str, Any]:
    return {
        "event_id": event.event_id,
        "event_type": event.event_type,
        "instrumented_path": event.instrumented_path,
        "display_path": event.display_path,
        "notes": event.notes,
        "seed": event.seed,
        "confidence": event.confidence,
        "loss_reason": event.loss_reason,
        "parent_event_ids": list(event.parent_event_ids),
        "candidate_ancestor_ids": list(event.candidate_ancestor_ids),
    }


def _base(trace: LoadedTrace, *, scene_revision: str | None) -> dict[str, Any]:
    meta = trace.meta
    return {
        "capture_mode": meta.capture_mode,
        "graph_id": meta.graph_id,
        "graph_label": meta.labels.get(meta.graph_id),
        "scene_id": meta.scene_id,
        "frame": meta.frame,
        "epoch": meta.epoch,
        "manifest_seed": meta.seed,
        "source_revision": meta.source_revision,
        "revision_status": _revision_status(trace, scene_revision),
        "units": meta.units,
        "unit_scale_to_meters": meta.unit_scale_to_meters,
        "coordinate_system": meta.coordinate_system,
        "continuity_policy": meta.continuity_policy,
        "generator_known": meta.capture_mode != CaptureMode.PASSIVE_ONLY.value,
    }


def query_logical(
    trace: LoadedTrace,
    instance_id: str,
    *,
    scene_revision: str | None = None,
    max_depth: int = 64,
) -> dict[str, Any]:
    """Trace one logical id.

    A passive manifest has no logical ids. The result is ``UNKNOWN_ORIGIN``
    with the runtime fields omitted rather than a reconstructed node path.
    """
    report = _base(trace, scene_revision=scene_revision)
    report.update(
        {
            "query": "logical_id",
            "instance_id": instance_id,
            "found": False,
            "origin_status": "UNKNOWN_ORIGIN",
            "confidence": Confidence.UNKNOWN.value,
            "exact_parent": False,
            "notes": [],
            "operations": [],
            "loss_points": [],
            "parent_logical_ids": [],
            "candidate_ancestors": [],
            "generator_known": False,
        }
    )
    try:
        raw = parse_id(instance_id)
    except ValueError as exc:
        report["origin_status"] = "MALFORMED_ID"
        report["notes"] = [str(exc)]
        return report
    if trace.meta.capture_mode == CaptureMode.PASSIVE_ONLY.value:
        report["origin_status"] = "UNKNOWN_ORIGIN"
        report["confidence"] = Confidence.PASSIVE_ONLY.value
        report["notes"] = [
            "This manifest is PASSIVE_ONLY. Evaluated object names and transforms were captured. "
            "The generating node, seed, and branch were not instrumented, so they are unknown."
        ]
        report["loss_points"] = [{"loss_reason": "NOT_INSTRUMENTED", "event_type": "UNSUPPORTED_OR_LOST"}]
        return report
    rows = trace.index.get(raw, [])
    if not rows:
        report["origin_status"] = "NOT_IN_MANIFEST"
        report["notes"] = ["No row in this manifest carries that logical id."]
        return report
    if len(rows) > 1:
        report["notes"].append(
            f"This logical id is stored on {len(rows)} rows. The rows are listed and none is selected as the sole element."
        )
        report["duplicate_rows"] = rows
    return _fill_row(trace, rows[0], report, max_depth=max_depth, extra_rows=rows[1:])


def query_locator(
    trace: LoadedTrace,
    locator: str,
    *,
    scene_revision: str | None = None,
    max_depth: int = 64,
) -> dict[str, Any]:
    report = _base(trace, scene_revision=scene_revision)
    matches = [row for row in range(len(trace.table)) if trace.table.locator(row) == locator]
    report.update(
        {
            "query": "evaluated_locator",
            "instance_id": None,
            "evaluated_locator": locator,
            "found": bool(matches),
            "origin_status": "UNKNOWN_ORIGIN",
            "confidence": Confidence.UNKNOWN.value,
            "exact_parent": False,
            "notes": [],
            "operations": [],
            "loss_points": [],
            "parent_logical_ids": [],
            "candidate_ancestors": [],
        }
    )
    if not matches:
        report["origin_status"] = "NOT_IN_MANIFEST"
        report["notes"] = ["No evaluated locator matches."]
        return report
    if len(matches) > 1:
        report["origin_status"] = "AMBIGUOUS_PICK"
        report["confidence"] = Confidence.AMBIGUOUS.value
        report["notes"] = [f"{len(matches)} rows share this locator."]
        report["candidate_rows"] = matches
        return report
    filled = _fill_row(trace, matches[0], report, max_depth=max_depth, extra_rows=[])
    if trace.meta.capture_mode == CaptureMode.PASSIVE_ONLY.value:
        filled["origin_status"] = "PASSIVE_ONLY"
        filled["confidence"] = Confidence.PASSIVE_ONLY.value
        filled["generator_known"] = False
        filled["instrumented_path"] = None
        filled["source_id"] = None
        filled["source_label"] = None
        filled["branch_id"] = None
        filled["seed"] = None
        filled["operations"] = []
        filled["exact_parent"] = False
        filled["notes"].append(
            "Passive capture reports the evaluated object, parent, and matrix only. "
            "persistent_id is a motion-blur matcher. random_id is a shading id. Neither is a logical instance id."
        )
    return filled


def _fill_row(
    trace: LoadedTrace,
    row: int,
    report: dict[str, Any],
    *,
    max_depth: int,
    extra_rows: list[int],
) -> dict[str, Any]:
    table = trace.table
    event = _event(trace, int(table.event_code[row]))
    container = _event(trace, int(table.container_event_code[row]))
    source_id = table.decode(table.sources, int(table.source_code[row]))
    branch_id = table.decode(table.branches, int(table.branch_code[row]))
    path = table.decode(table.paths, int(table.path_code[row]))
    loss = table.decode(table.loss_reasons, int(table.loss_code[row]))
    confidence = table.confidences[int(table.confidence[row])]
    mode = table.sample_modes[int(table.sample_mode[row])]
    logical = table.logical_hex(row) if table.has_logical_id(row) else None
    chain: list[Event] = []
    walk_losses: list[str] = []
    if event is not None and trace.meta.capture_mode != CaptureMode.PASSIVE_ONLY.value:
        chain, walk_losses = causal_order(trace.events, event.event_id, max_depth=max_depth)
    elif trace.meta.capture_mode == CaptureMode.PASSIVE_ONLY.value:
        report["generator_known"] = False
    operations = [_operation(item) for item in chain]
    loss_points = [op for op in operations if op["loss_reason"] or op["event_type"] in {
        EventType.LINEAGE_AMBIGUOUS.value,
        EventType.UNSUPPORTED_OR_LOST.value,
        EventType.REMOVE.value,
    }]
    for token in walk_losses:
        loss_points.append({"loss_reason": token, "event_type": "UNSUPPORTED_OR_LOST", "notes": token})
    candidates = []
    if event is not None:
        candidates.extend(event.candidate_ancestor_ids)
    for code in table.candidate_codes(row):
        candidate = _event(trace, code)
        if candidate is not None and candidate.event_id not in candidates:
            candidates.append(candidate.event_id)
    notes = list(report.get("notes") or [])
    if int(table.flags[row]) & FLAG_INDEX_UNSTABLE:
        notes.append(
            "Sample key mode is index. The id follows the authored index, and a topology change that renumbers indexes breaks continuity."
        )
    if loss:
        notes.append(f"Row loss reason: {loss}.")
        loss_points.append({"event_type": "ROW", "loss_reason": loss, "notes": loss})
    if extra_rows:
        notes.append("Duplicate rows: " + ", ".join(str(item) for item in extra_rows))
    exact_parent = confidence == Confidence.EXACT.value and event is not None and event.event_type != EventType.LINEAGE_AMBIGUOUS.value
    origin = _origin(trace, row, found=True)
    if extra_rows:
        origin = "DUPLICATE"
        exact_parent = False
    if "DEPTH_LIMIT" in walk_losses or "CYCLE_DETECTED" in walk_losses:
        if origin == "EXACT":
            origin = "PARTIAL_TRACE"
        exact_parent = False
    report.update(
        {
            "found": True,
            "instance_id": logical,
            "origin_status": origin,
            "confidence": confidence,
            "exact_parent": exact_parent,
            "source_id": source_id,
            "source_label": trace.meta.labels.get(source_id or "", None),
            "instrumented_path": path if trace.meta.capture_mode != CaptureMode.PASSIVE_ONLY.value else None,
            "runtime_object": path if trace.meta.capture_mode == CaptureMode.PASSIVE_ONLY.value else None,
            "branch_id": branch_id if trace.meta.capture_mode != CaptureMode.PASSIVE_ONLY.value else None,
            "sample_key": int(table.sample_key[row]) if trace.meta.capture_mode != CaptureMode.PASSIVE_ONLY.value else None,
            "sample_key_mode": mode if trace.meta.capture_mode != CaptureMode.PASSIVE_ONLY.value else None,
            "seed": None
            if trace.meta.capture_mode == CaptureMode.PASSIVE_ONLY.value or int(table.flags[row]) & FLAG_SEED_UNKNOWN
            else int(table.seed[row]),
            "transform": [float(value) for value in table.transform[row].tolist()],
            "alive": bool(table.alive[row]),
            "operations": operations if trace.meta.capture_mode != CaptureMode.PASSIVE_ONLY.value else [],
            "loss_points": loss_points,
            "parent_logical_ids": table.parent_hexes(row),
            "candidate_ancestors": candidates,
            "container": _operation(container) if container is not None else None,
            "evaluated_locator": table.locator(row) or None,
            "row": row,
            "notes": notes,
            "generator_known": trace.meta.capture_mode != CaptureMode.PASSIVE_ONLY.value and bool(path),
        }
    )
    if report["revision_status"] == "INCOMPATIBLE":
        report["notes"].append(
            "This manifest's source revision does not match the current scene revision. "
            "Matching logical ids are not treated as proof that the graphs are the same generation."
        )
        if report["origin_status"] == "EXACT":
            report["origin_status"] = "PARTIAL_TRACE"
            report["exact_parent"] = False
    return report
