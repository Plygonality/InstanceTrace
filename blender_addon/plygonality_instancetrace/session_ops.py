"""Scene capture and panel actions.

These functions run inside Blender. They read evaluated data and may add an
``IT_Highlight`` empty in ``InstanceTrace_Overlay``. They do not replace mesh
datablocks, realise the user's modifiers, delete unrelated objects, or save
the file.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import Any

import bpy

from .state import SESSION

_HIGHLIGHT = "IT_Highlight"
_REPORT_TEXT = "InstanceTrace Report"


def _library_root() -> None:
    root = Path(__file__).resolve().parents[2] / "src"
    if root.is_dir() and str(root) not in sys.path:
        sys.path.insert(0, str(root))


def _imports():
    _library_root()
    from instancetrace.capture.instrumented import import_instrumented_dump
    from instancetrace.capture.locators import locator_object_name
    from instancetrace.capture.passive import import_passive_dump
    from instancetrace.capture.pick import boxes_from_trace, pick_ray
    from instancetrace.capture.scene_guard import (
        OVERLAY_COLLECTION,
        assert_deletion_allowed,
        resolve_node_path,
    )
    from instancetrace.errors import SceneSafetyError
    from instancetrace.query.engine import query_logical
    from instancetrace.storage.manifest import load_trace, save_trace
    from instancetrace.visualization.html import format_html
    from instancetrace.visualization.text import format_report

    return {
        "import_instrumented_dump": import_instrumented_dump,
        "import_passive_dump": import_passive_dump,
        "locator_object_name": locator_object_name,
        "boxes_from_trace": boxes_from_trace,
        "pick_ray": pick_ray,
        "OVERLAY_COLLECTION": OVERLAY_COLLECTION,
        "assert_deletion_allowed": assert_deletion_allowed,
        "resolve_node_path": resolve_node_path,
        "SceneSafetyError": SceneSafetyError,
        "query_logical": query_logical,
        "load_trace": load_trace,
        "save_trace": save_trace,
        "format_html": format_html,
        "format_report": format_report,
    }


def _scene_id(scene: bpy.types.Scene) -> str:
    return f"scene:{scene.name}"


def _read_ints(mesh: bpy.types.Mesh, name: str) -> list[int] | None:
    attribute = mesh.attributes.get(name)
    if attribute is None or attribute.data_type != "INT":
        return None
    return [int(item.value) for item in attribute.data]


def _attribute_instances(context: bpy.types.Context) -> list[dict[str, Any]]:
    """Read ``it_lid_*`` from meshes that already store them.

    This does not add a Realize Instances node. Unrealized instance attributes
    stay unread.
    """
    depsgraph = context.evaluated_depsgraph_get()
    found: dict[tuple[int, int, int, int], dict[str, Any]] = {}
    for obj in context.scene.objects:
        if obj.type != "MESH":
            continue
        evaluated = obj.evaluated_get(depsgraph)
        mesh = evaluated.data
        if mesh is None or not hasattr(mesh, "attributes"):
            continue
        lids = [_read_ints(mesh, f"it_lid_{slot}") for slot in range(4)]
        if any(column is None for column in lids):
            continue
        sample = _read_ints(mesh, "it_sample")
        branch = _read_ints(mesh, "it_branch")
        source = _read_ints(mesh, "it_source")
        count = len(lids[0] or [])
        for index in range(count):
            key = tuple(int(column[index]) for column in lids if column is not None)
            if key in found:
                found[key]["repeats"] += 1
                continue
            found[key] = {
                "evaluated_index": index,
                "object_name": obj.name,
                "parent_name": obj.name,
                "is_instance": False,
                "persistent_id": [0, 0, 0, 0, 0, 0, 0, 0],
                "random_id": 0,
                "matrix_world": [float(value) for row in obj.matrix_world for value in row],
                "attributes_read": True,
                "it_lid": list(key),
                "it_sample": int(sample[index]) if sample and index < len(sample) else 0,
                "it_branch": int(branch[index]) if branch and index < len(branch) else 0,
                "it_source": int(source[index]) if source and index < len(source) else 0,
                "repeats": 1,
            }
    return list(found.values())


def _passive_instances(context: bpy.types.Context) -> list[dict[str, Any]]:
    depsgraph = context.evaluated_depsgraph_get()
    rows = []
    for index, item in enumerate(depsgraph.object_instances):
        if not item.is_instance:
            continue
        parent = item.parent.original if item.parent is not None else None
        instance_object = item.instance_object.name if item.instance_object is not None else ""
        rows.append(
            {
                "evaluated_index": index,
                "object_name": instance_object or (item.object.name if item.object else ""),
                "parent_name": parent.name if parent is not None else "",
                "is_instance": True,
                "persistent_id": [int(value) for value in item.persistent_id],
                "random_id": int(item.random_id),
                "matrix_world": [float(item.matrix_world[row][col]) for row in range(4) for col in range(4)],
            }
        )
    return rows


def capture_scene(context: bpy.types.Context) -> dict[str, Any]:
    """Capture the current scene without writing the blend file."""
    api = _imports()
    scene = context.scene
    settings = scene.instancetrace
    attribute_rows = _attribute_instances(context)
    passive_rows = _passive_instances(context)
    if attribute_rows:
        dump = {
            "format": "instancetrace.blender_capture",
            "format_version": 1,
            "capture_mode": "INSTRUMENTED",
            "blender_version": bpy.app.version_string,
            "scene_id": _scene_id(scene),
            "frame": scene.frame_current,
            "units": "blender_units",
            "unit_scale_to_meters": float(scene.unit_settings.scale_length),
            "coordinate_system": "right_handed_z_up",
            "attribute_read_path": "existing_evaluated_mesh",
            "confidence_ceiling": "PARTIAL",
            "ceiling_reason": "REALIZE_DOMAIN_CHANGE",
            "instances": attribute_rows,
            "notes": [
                "Attributes were already on evaluated meshes. No Realize node was added.",
            ],
        }
        trace = api["import_instrumented_dump"](dump, None)
        mode = "INSTRUMENTED"
    else:
        dump = {
            "format": "instancetrace.blender_capture",
            "format_version": 1,
            "capture_mode": "PASSIVE_ONLY",
            "blender_version": bpy.app.version_string,
            "scene_id": _scene_id(scene),
            "frame": scene.frame_current,
            "units": "blender_units",
            "unit_scale_to_meters": float(scene.unit_settings.scale_length),
            "coordinate_system": "right_handed_z_up",
            "instances": passive_rows,
        }
        trace = api["import_passive_dump"](dump)
        mode = "PASSIVE_ONLY"
    directory = Path(tempfile.mkdtemp(prefix="instancetrace-"))
    path = api["save_trace"](trace, directory / "trace.json")
    SESSION.trace = trace
    SESSION.report = None
    SESSION.boxes = api["boxes_from_trace"](trace) if passive_rows or attribute_rows else []
    SESSION.pick_bounds_available = bool(passive_rows)
    settings.manifest_path = str(path)
    settings.capture_mode = mode
    settings.source_revision = trace.meta.source_revision or ""
    settings.origin_status = ""
    settings.status = (
        f"{mode}: {len(trace.table)} rows, {len(passive_rows)} depsgraph instances. "
        "File was not saved."
    )
    return {
        "capture_mode": mode,
        "rows": len(trace.table),
        "depsgraph_instances": len(passive_rows),
        "manifest": str(path),
        "saved_blend": False,
    }


def _active_trace(context: bpy.types.Context):
    api = _imports()
    settings = context.scene.instancetrace
    path = settings.manifest_path.strip()
    if path and Path(path).is_file():
        trace = api["load_trace"](path)
        SESSION.trace = trace
        if not SESSION.boxes:
            SESSION.boxes = api["boxes_from_trace"](trace)
        return trace
    if SESSION.trace is not None:
        return SESSION.trace
    return None


def query_instance(context: bpy.types.Context) -> dict[str, Any]:
    api = _imports()
    settings = context.scene.instancetrace
    instance_id = settings.instance_id.strip()
    trace = _active_trace(context)
    if trace is None:
        settings.status = "No manifest is loaded. Capture the scene or set a manifest path."
        return {"origin_status": "NOT_IN_MANIFEST"}
    revision = settings.scene_revision.strip() or None
    report = api["query_logical"](trace, instance_id, scene_revision=revision)
    SESSION.report = report
    SESSION.trace = trace
    settings.origin_status = str(report.get("origin_status") or "")
    settings.source_revision = trace.meta.source_revision or ""
    settings.status = api["format_report"](report)
    _write_report(settings.status)
    return report


def _write_report(text: str) -> None:
    block = bpy.data.texts.get(_REPORT_TEXT)
    if block is None:
        block = bpy.data.texts.new(_REPORT_TEXT)
    block.clear()
    block.write(text)


def _overlay_collection(scene: bpy.types.Scene, name: str) -> bpy.types.Collection:
    collection = bpy.data.collections.get(name)
    if collection is None:
        collection = bpy.data.collections.new(name)
        scene.collection.children.link(collection)
    return collection


def _replace_highlight(context: bpy.types.Context, translation: tuple[float, float, float] | None) -> str:
    api = _imports()
    existing = bpy.data.objects.get(_HIGHLIGHT)
    if existing is not None:
        collections = {item.name for item in existing.users_collection}
        try:
            api["assert_deletion_allowed"](existing.name, collections)
        except api["SceneSafetyError"] as exc:
            return f"highlight left in place: {exc}"
        bpy.data.objects.remove(existing, do_unlink=True)
    if translation is None:
        return "no evaluated translation on this report"
    empty = bpy.data.objects.new(_HIGHLIGHT, None)
    empty.empty_display_type = "CUBE"
    empty.empty_display_size = 0.2
    empty.location = translation
    empty.show_name = True
    collection = _overlay_collection(context.scene, api["OVERLAY_COLLECTION"])
    collection.objects.link(empty)
    return "overlay empty placed"


def highlight_source(context: bpy.types.Context) -> dict[str, str]:
    """Select a source object and node only when the names exist."""
    api = _imports()
    report = SESSION.report
    if report is None:
        context.scene.instancetrace.status = "Query an instance id before highlighting."
        return {"object": "not_queried", "node": "not_queried", "overlay": "not_queried"}
    locator = str(report.get("evaluated_locator") or "")
    object_name = api["locator_object_name"](locator) if locator else None
    selected = "not_in_scene"
    if object_name and object_name in context.view_layer.objects:
        source = context.view_layer.objects[object_name]
        source.select_set(True)
        context.view_layer.objects.active = source
        selected = object_name
    path = str(report.get("instrumented_path") or "")
    trees = {group.name: {node.name for node in group.nodes} for group in bpy.data.node_groups}
    resolved = api["resolve_node_path"](trees, path)
    node_status = "path_not_in_file"
    if resolved is not None:
        tree_name, node_name = resolved
        group = bpy.data.node_groups[tree_name]
        for node in group.nodes:
            node.select = False
        node = group.nodes[node_name]
        node.select = True
        group.nodes.active = node
        if context.screen is not None:
            for area in context.screen.areas:
                if area.type != "NODE_EDITOR":
                    continue
                space = area.spaces.active
                if getattr(space, "tree_type", "") == "GeometryNodeTree":
                    space.node_tree = group
        node_status = f"{tree_name}/{node_name}"
    transform = report.get("transform")
    translation = None
    if isinstance(transform, list) and len(transform) == 16:
        translation = (float(transform[3]), float(transform[7]), float(transform[11]))
    overlay = _replace_highlight(context, translation if report.get("found") else None)
    context.scene.instancetrace.status = (
        f"source object {selected}; node {node_status}; overlay {overlay}"
    )
    return {"object": selected, "node": node_status, "overlay": overlay}


def open_event_graph(context: bpy.types.Context) -> str:
    api = _imports()
    report = SESSION.report
    if report is None:
        context.scene.instancetrace.status = "Query an instance id before opening the event graph."
        return ""
    directory = context.scene.instancetrace.output_dir.strip()
    folder = Path(directory) if directory else Path(tempfile.mkdtemp(prefix="instancetrace-graph-"))
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "lineage.html"
    path.write_text(api["format_html"](report), encoding="utf-8")
    context.scene.instancetrace.status = f"wrote {path}"
    return str(path)


def show_lost_lineage(context: bpy.types.Context) -> str:
    report = SESSION.report
    if report is None:
        text = "Query an instance id before listing lost lineage."
    else:
        points = report.get("loss_points") or []
        if not points:
            text = f"Origin {report.get('origin_status')}. No loss points on this report."
        else:
            lines = [f"Origin {report.get('origin_status')}"]
            for point in points:
                lines.append(
                    f"{point.get('event_type') or 'LOSS'} {point.get('loss_reason') or ''}".rstrip()
                )
            text = "\n".join(lines)
    context.scene.instancetrace.status = text
    _write_report(text)
    return text


def pick_instance(context: bpy.types.Context, origin: tuple[float, float, float] | None, direction: tuple[float, float, float] | None) -> dict[str, Any]:
    api = _imports()
    if origin is None or direction is None or context.region is None or context.area is None:
        result = {"status": "PICK_UNSUPPORTED", "instance_ids": [], "loss_reason": "PICK_UNSUPPORTED"}
    elif not SESSION.pick_bounds_available or not SESSION.boxes:
        result = {"status": "PICK_UNSUPPORTED", "instance_ids": [], "loss_reason": "PICK_UNSUPPORTED"}
    else:
        result = api["pick_ray"](origin, direction, SESSION.boxes)
    context.scene.instancetrace.status = (
        f"{result['status']} {', '.join(result.get('instance_ids') or [])}".rstrip()
    )
    if result["status"] == "EXACT" and result["instance_ids"]:
        chosen = result["instance_ids"][0]
        if chosen.startswith("0x"):
            context.scene.instancetrace.instance_id = chosen
    return result
