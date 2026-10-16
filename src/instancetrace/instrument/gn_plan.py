"""Documented Geometry Nodes operations for a supported program.

The plan is data. It does not import ``bpy`` and it is not a node interpreter.
Integer attributes carry ids because string attributes are a poor fit for
large instance domains; the codebook lives beside the arrays.
"""

from __future__ import annotations

from typing import Any

from instancetrace.instrument.grammar import Program

ATTRIBUTE_SPEC = {
    "logical_id": ["it_lid_0", "it_lid_1", "it_lid_2", "it_lid_3"],
    "sample_key": "it_sample",
    "branch_code": "it_branch",
    "source_code": "it_source",
    "data_type": "INT",
    "domains": ["POINT", "INSTANCE"],
    "string_policy": "Strings are not stored on geometry. Codes use the capture codebook.",
}


def plan_geometry_nodes(program: Program) -> dict[str, Any]:
    nodes = [
        {
            "op": "store_named_attribute",
            "domain": "POINT",
            "data_type": "INT",
            "names": list(ATTRIBUTE_SPEC["logical_id"]) + ["it_sample", "it_branch", "it_source"],
            "when": "authoring, before Instance on Points",
        },
        {
            "op": "instance_on_points",
            "notes": "Instance references are the declared source objects.",
        },
        {
            "op": "store_named_attribute",
            "domain": "INSTANCE",
            "data_type": "INT",
            "names": list(ATTRIBUTE_SPEC["logical_id"]),
            "when": "after Instance on Points, if the host keeps the instance domain",
        },
    ]
    return {
        "plan_version": "0.1.0",
        "graph_id": program.graph_id,
        "attributes": ATTRIBUTE_SPEC,
        "lineage_policy": {
            "realize_instances": "LINEAGE_AMBIGUOUS unless a capture reads surviving ids, and then PARTIAL",
            "join_geometry": "LINEAGE_AMBIGUOUS when ids do not survive on one domain",
            "remesh_boolean_resample_export": "UNSUPPORTED_OR_LOST",
            "index_sampling": "PARTIAL with INDEX_ONLY_SAMPLING",
        },
        "nodes": nodes,
        "groups": [group.group_id for group in program.groups],
        "sources": [source.source_id for source in program.sources],
    }
