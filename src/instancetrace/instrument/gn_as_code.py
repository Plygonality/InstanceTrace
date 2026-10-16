"""Optional adapter for a graph-as-code document.

``gn-as-code`` was not a public repository at the time of v0.1, so this
module does not depend on it. A document already in ``instancetrace.graph``
form can be executed by the caller. A ``gn_as_code.graph`` document yields
identifiers only.
"""

from __future__ import annotations

import importlib
from typing import Any


def probe_installed_package() -> dict[str, Any]:
    try:
        module = importlib.import_module("gn_as_code")
    except ImportError:
        return {"available": False, "reason": "gn_as_code is not installed"}
    return {"available": True, "version": getattr(module, "__version__", "unknown")}


def import_identifiers(graph: dict[str, Any]) -> list[dict[str, Any]]:
    fmt = graph.get("format")
    if fmt not in {"gn_as_code.graph", "instancetrace.graph"}:
        raise ValueError("unsupported graph format")
    nodes = graph.get("nodes") or []
    found = []
    for node in nodes:
        node_id = str(node.get("id") or "")
        if not node_id:
            continue
        label = str(node.get("label") or node.get("name") or "")
        found.append(
            {
                "source_id": node_id,
                "label": label,
                "node_type": node.get("type"),
                "label_independent": bool(label) and label != node_id,
                "executed": False,
                "role": "identifier_only",
            }
        )
    return found
