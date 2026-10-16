"""Rules for what a Blender session is allowed to delete or retarget."""

from __future__ import annotations

from instancetrace.errors import SceneSafetyError

DEMO_COLLECTION = "InstanceTrace_Demo"
OVERLAY_COLLECTION = "InstanceTrace_Overlay"
OBJECT_PREFIX = "IT_"


def deletion_allowed(object_name: str, collection_names: set[str]) -> bool:
    """True only for trace-owned objects that sit in a trace collection."""
    if not object_name.startswith(OBJECT_PREFIX):
        return False
    allowed = {DEMO_COLLECTION, OVERLAY_COLLECTION}
    if not collection_names or not collection_names <= allowed:
        return False
    return True


def assert_deletion_allowed(object_name: str, collection_names: set[str]) -> None:
    if not deletion_allowed(object_name, collection_names):
        raise SceneSafetyError(
            f"refusing to delete {object_name!r} from collections {sorted(collection_names)}"
        )


def resolve_instrument_target(
    *,
    original_name: str,
    allow_modify_original: bool,
    confirm: bool,
) -> str:
    """Instrumentation copies onto an ``IT_`` object unless modification is confirmed."""
    if allow_modify_original and confirm:
        return original_name
    if allow_modify_original and not confirm:
        raise SceneSafetyError("modifying the original object requires confirm=True")
    return f"{OBJECT_PREFIX}{original_name}"


def resolve_node_path(trees: dict[str, set[str]], path: str) -> tuple[str, str] | None:
    """Validate ``TreeName/NodeName`` against known trees before any editor change.

    ``trees`` maps a node-tree name to the set of node names in that tree.
    """
    if "/" not in path:
        return None
    tree_name, node_name = path.split("/", 1)
    if not tree_name or not node_name or "/" in node_name:
        return None
    nodes = trees.get(tree_name)
    if not nodes or node_name not in nodes:
        return None
    return tree_name, node_name
