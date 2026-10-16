"""Graphviz DOT for one instance chain. Graphviz itself is not required to write the file."""

from __future__ import annotations

from typing import Any


def _esc(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def format_dot(report: dict[str, Any]) -> str:
    lines = [
        "digraph lineage {",
        "  rankdir=LR;",
        '  graph [fontname="sans-serif", labelloc=t];',
        '  node [shape=box, style=filled, fontname="sans-serif", fillcolor="#f4f1ea"];',
        f'  label="{_esc(_title(report))}";',
    ]
    operations = report.get("operations") or []
    highlight = report.get("instance_id") or "instance"
    lines.append(
        f'  "{_esc(highlight)}" [fillcolor="#e2b340", label="{_esc(_node_label(report))}"];'
    )
    previous = highlight
    seen = {highlight}
    for operation in operations:
        node = operation["event_id"]
        if node not in seen:
            color = "#f0d0c8" if operation.get("loss_reason") or operation["event_type"] in {
                "LINEAGE_AMBIGUOUS",
                "UNSUPPORTED_OR_LOST",
                "REMOVE",
            } else "#f4f1ea"
            label = f"{operation['event_type']}\\n{operation['instrumented_path']}"
            lines.append(f'  "{_esc(node)}" [fillcolor="{color}", label="{_esc(label)}"];')
            seen.add(node)
        lines.append(f'  "{_esc(node)}" -> "{_esc(previous)}";')
        previous = node
    container = report.get("container")
    if container:
        node = container["event_id"]
        if node not in seen:
            lines.append(
                f'  "{_esc(node)}" [fillcolor="#d5e2d2", label="{_esc(container["event_type"])}"];'
            )
            seen.add(node)
        lines.append(f'  "{_esc(node)}" -> "{_esc(highlight)}" [style=dashed, label="contains"];')
        for parent in container.get("parent_event_ids") or []:
            if parent not in seen:
                lines.append(f'  "{_esc(parent)}" [label="{_esc(parent)}"];')
                seen.add(parent)
            lines.append(f'  "{_esc(parent)}" -> "{_esc(node)}";')
    for candidate in report.get("candidate_ancestors") or []:
        if candidate not in seen:
            lines.append(f'  "{_esc(candidate)}" [style=dashed, label="{_esc(candidate)}"];')
            seen.add(candidate)
        lines.append(
            f'  "{_esc(candidate)}" -> "{_esc(highlight)}" [style=dotted, label="candidate"];'
        )
    lines.append("}")
    return "\n".join(lines) + "\n"


def _title(report: dict[str, Any]) -> str:
    return f"InstanceTrace {report.get('instance_id') or ''} {report.get('origin_status') or ''}"


def _node_label(report: dict[str, Any]) -> str:
    source = report.get("source_label") or report.get("source_id") or "unknown source"
    sample = report.get("sample_key")
    return f"{report.get('instance_id')}\\nsource {source}\\nsample {sample}"
