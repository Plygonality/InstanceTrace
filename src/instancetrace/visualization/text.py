"""Plain-text lineage reports."""

from __future__ import annotations

from typing import Any


def _line(label: str, value: object) -> str:
    if value is None or value == "":
        value = "unknown"
    return f"{label}: {value}"


def format_report(report: dict[str, Any]) -> str:
    lines = [
        f"Instance {report.get('instance_id') or 'unknown'}",
        _line("Origin", report.get("origin_status")),
        _line("Confidence", report.get("confidence")),
        _line("Capture", report.get("capture_mode")),
        _line("Graph", _named(report.get("graph_id"), report.get("graph_label"))),
        _line("Source revision", report.get("source_revision")),
        _line("Revision status", report.get("revision_status")),
        _line(
            "Scene",
            f"{report.get('scene_id')}  frame {report.get('frame')}  epoch {report.get('epoch')}",
        ),
        _line("Manifest seed", report.get("manifest_seed")),
        _line("Units", f"{report.get('units')} (scale {report.get('unit_scale_to_meters')})"),
        _line("Coordinates", report.get("coordinate_system")),
        "",
    ]
    if report.get("generator_known"):
        lines.extend(
            [
                _line("Generator path", report.get("instrumented_path")),
                _line("Branch", report.get("branch_id")),
                _line("Sample key", f"{report.get('sample_key')} ({report.get('sample_key_mode')})"),
                _line("Instance seed", report.get("seed")),
                _line("Source object", _named(report.get("source_id"), report.get("source_label"))),
                _line("Live output", "yes" if report.get("alive") else "no"),
                _line("Exact parent", "yes" if report.get("exact_parent") else "no"),
            ]
        )
    else:
        lines.extend(
            [
                "Generator path: unknown",
                "Branch: unknown",
                "Instance seed: unknown",
                "Source object: unknown",
                _line("Runtime object", report.get("runtime_object")),
                "The capture does not contain an instrumented node path.",
            ]
        )
    parents = report.get("parent_logical_ids") or []
    lines.append("Parent logical ids: " + (", ".join(parents) if parents else "none"))
    if report.get("evaluated_locator"):
        lines.append(f"Evaluated locator: {report['evaluated_locator']}")
    container = report.get("container")
    if container:
        lines.append(
            "Containing operation: "
            f"{container['event_type']} parents={','.join(container['parent_event_ids'])}"
        )
        lines.append(f"  note: {container.get('notes') or ''}")
    lines.append("")
    lines.append("Operation chain:")
    operations = report.get("operations") or []
    if not operations:
        lines.append("  (no instrumented operations)")
    for index, operation in enumerate(operations, start=1):
        loss = f" loss={operation['loss_reason']}" if operation.get("loss_reason") else ""
        lines.append(
            f"  {index}. {operation['event_type']} {operation['instrumented_path']}{loss}"
        )
        if operation.get("notes"):
            lines.append(f"     {operation['notes']}")
        if operation.get("parent_event_ids"):
            lines.append("     parents: " + ", ".join(operation["parent_event_ids"]))
    candidates = report.get("candidate_ancestors") or []
    if candidates:
        lines.append("")
        lines.append("Candidate ancestors (none selected as the sole parent):")
        for candidate in candidates:
            lines.append(f"  {candidate}")
    losses = report.get("loss_points") or []
    lines.append("")
    if losses:
        lines.append("Loss points:")
        for loss in losses:
            lines.append(f"  {loss.get('event_type')} {loss.get('loss_reason')}")
    else:
        lines.append("Loss points: none")
    notes = report.get("notes") or []
    if notes:
        lines.append("")
        lines.append("Notes:")
        for note in notes:
            lines.append(f"  {note}")
    return "\n".join(lines) + "\n"


def _named(identifier: object, label: object) -> str:
    if not identifier and not label:
        return "unknown"
    if identifier and label and label != identifier:
        return f"{label} ({identifier})"
    return str(identifier or label)
