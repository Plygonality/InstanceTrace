"""Import node identifiers from a NodeBridge graph document.

This does not run NodeBridge's compiler and does not treat a translated
graph as the same provenance chain. NodeBridge node ids are often the node
name; those are flagged ``label_independent: false``.
"""

from __future__ import annotations

from typing import Any


def import_node_identifiers(graph: dict[str, Any]) -> list[dict[str, Any]]:
    if graph.get("format") != "nodebridge.graph":
        raise ValueError("expected format nodebridge.graph")
    found = []
    for tree in graph.get("trees") or []:
        tree_name = str(tree.get("name") or "")
        for node in tree.get("nodes") or []:
            node_id = str(node["id"])
            name = str(node.get("name") or "")
            label = str(node.get("label") or "")
            found.append(
                {
                    "source_id": node_id,
                    "tree": tree_name,
                    "node_type": node.get("type"),
                    "name": name,
                    "label": label,
                    "label_independent": bool(name and name != node_id) or bool(label and label != node_id and name != node_id),
                    "role": "nodebridge_node_id",
                }
            )
    return found
