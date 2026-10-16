"""Build the instrumented habitat scatter in Blender and write a trace.

Verified against Blender 5.2.2 LTS:

* Depsgraph instances expose transforms, ``persistent_id`` and ``random_id``.
  They do not expose Geometry Nodes named attributes.
* ``persistent_id`` in this scene was an 8-int motion-blur key, with unused
  slots set to 2147483647. It is stored as an evaluated locator only.
* Storing ``it_lid_*`` on the instance domain and then realizing instances
  copies those ints onto the point domain, repeated once per realized vertex.
* String attribute values on a mesh expect bytes, so ids stay numeric.
* A mesh datablock rejects the INSTANCE attribute domain.

The script adds ``IT_`` objects and does not delete or save the factory scene
unless ``--save`` is passed.

Run::

    blender --background --python examples/blender/build_habitat_and_capture.py -- \\
        --out build/blender-demo
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from instancetrace.capture.instrumented import import_instrumented_dump  # noqa: E402
from instancetrace.capture.passive import import_passive_dump  # noqa: E402
from instancetrace.demo.habitat import habitat_program, highlighted_id  # noqa: E402
from instancetrace.ids.codec import pack_int32x4  # noqa: E402
from instancetrace.instrument.execute import execute  # noqa: E402
from instancetrace.query.engine import query_logical  # noqa: E402
from instancetrace.storage.manifest import save_trace  # noqa: E402
from instancetrace.visualization.text import format_report  # noqa: E402

SOURCE_OBJECTS = {
    "src:hk.panel_a": "IT_Panel_A",
    "src:hk.panel_b": "IT_Panel_B",
    "src:hk.mullion": "IT_Mullion",
}


def _args() -> dict:
    out = ROOT / "build" / "blender-demo"
    save = False
    if "--" in sys.argv:
        raw = sys.argv[sys.argv.index("--") + 1 :]
        if "--out" in raw:
            out = Path(raw[raw.index("--out") + 1])
        save = "--save" in raw
    return {"out": out, "save": save}


def _quad(name: str, z: float) -> bpy.types.Object:
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(
        [(-0.25, -0.04, -0.25), (0.25, -0.04, -0.25), (0.25, 0.04, 0.25 + z), (-0.25, 0.04, 0.25 + z)],
        [],
        [(0, 1, 2, 3)],
    )
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def _set_int(mesh, name: str, values: list[int]) -> None:
    attribute = mesh.attributes.new(name, "INT", "POINT")
    for index, value in enumerate(values):
        attribute.data[index].value = int(value)


def _points(name: str, rows: list[dict]) -> bpy.types.Object:
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([(row["x"], row["y"], row["z"]) for row in rows], [], [])
    _set_int(mesh, "it_lid_0", [row["lid"][0] for row in rows])
    _set_int(mesh, "it_lid_1", [row["lid"][1] for row in rows])
    _set_int(mesh, "it_lid_2", [row["lid"][2] for row in rows])
    _set_int(mesh, "it_lid_3", [row["lid"][3] for row in rows])
    _set_int(mesh, "it_sample", [row["sample"] for row in rows])
    _set_int(mesh, "it_branch", [row["branch"] for row in rows])
    _set_int(mesh, "it_source", [row["source"] for row in rows])
    _set_int(mesh, "it_pick", [row["pick"] for row in rows])
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def _socket(tree, name: str, in_out: str, socket_type: str):
    return tree.interface.new_socket(name=name, in_out=in_out, socket_type=socket_type)


def _object_info(tree, obj, space: str):
    node = tree.nodes.new("GeometryNodeObjectInfo")
    node.inputs["Object"].default_value = obj
    node.transform_space = space
    return node


def _store_ints(tree, geometry_socket, names: list[str]):
    current = geometry_socket
    for name in names:
        store = tree.nodes.new("GeometryNodeStoreNamedAttribute")
        store.data_type = "INT"
        store.domain = "INSTANCE"
        store.inputs["Name"].default_value = name
        named = tree.nodes.new("GeometryNodeInputNamedAttribute")
        named.data_type = "INT"
        named.inputs["Name"].default_value = name
        tree.links.new(current, store.inputs["Geometry"])
        tree.links.new(named.outputs["Attribute"], store.inputs["Value"])
        current = store.outputs["Geometry"]
    return current


def _source_collection() -> bpy.types.Collection:
    collection = bpy.data.collections.new("IT_Sources")
    bpy.context.scene.collection.children.link(collection)
    for name in ("IT_Panel_A", "IT_Panel_B", "IT_Mullion"):
        collection.objects.link(bpy.data.objects[name])
    return collection


def _instance_sources(name: str, points_obj, collection: bpy.types.Collection) -> bpy.types.NodeTree:
    """Pick collection children by ``it_pick``, which is the live collection index.

    ``it_source`` stays the codebook index. Those two numbers differed in
    Blender 5.2.2 because collection instance order was not link order.
    """
    tree = bpy.data.node_groups.new(name, "GeometryNodeTree")
    _socket(tree, "Geometry", "INPUT", "NodeSocketGeometry")
    _socket(tree, "Geometry", "OUTPUT", "NodeSocketGeometry")
    points = _object_info(tree, points_obj, "RELATIVE")
    instancer = tree.nodes.new("GeometryNodeInstanceOnPoints")
    instancer.inputs["Pick Instance"].default_value = True
    tree.links.new(points.outputs["Geometry"], instancer.inputs["Points"])
    info = tree.nodes.new("GeometryNodeCollectionInfo")
    info.inputs["Collection"].default_value = collection
    info.transform_space = "ORIGINAL"
    if "Separate Children" in info.inputs:
        info.inputs["Separate Children"].default_value = True
    if "Reset Children" in info.inputs:
        info.inputs["Reset Children"].default_value = True
    tree.links.new(info.outputs["Instances"], instancer.inputs["Instance"])
    named = tree.nodes.new("GeometryNodeInputNamedAttribute")
    named.data_type = "INT"
    named.inputs["Name"].default_value = "it_pick"
    tree.links.new(named.outputs["Attribute"], instancer.inputs["Instance Index"])
    stored = _store_ints(
        tree,
        instancer.outputs["Instances"],
        ["it_lid_0", "it_lid_1", "it_lid_2", "it_lid_3", "it_sample", "it_branch", "it_source"],
    )
    tree.links.new(stored, tree.nodes.new("NodeGroupOutput").inputs["Geometry"])
    return tree


def _wrapper(name: str, inner: bpy.types.NodeTree, realize: bool) -> bpy.types.NodeTree:
    tree = bpy.data.node_groups.new(name, "GeometryNodeTree")
    _socket(tree, "Geometry", "INPUT", "NodeSocketGeometry")
    _socket(tree, "Geometry", "OUTPUT", "NodeSocketGeometry")
    group = tree.nodes.new("GeometryNodeGroup")
    group.node_tree = inner
    output = tree.nodes.new("NodeGroupOutput")
    geometry = group.outputs[0]
    if realize:
        node = tree.nodes.new("GeometryNodeRealizeInstances")
        tree.links.new(geometry, node.inputs["Geometry"])
        geometry = node.outputs["Geometry"]
    tree.links.new(geometry, output.inputs["Geometry"])
    return tree


def _join_groups(name: str, members: list[bpy.types.NodeTree]) -> bpy.types.NodeTree:
    tree = bpy.data.node_groups.new(name, "GeometryNodeTree")
    _socket(tree, "Geometry", "INPUT", "NodeSocketGeometry")
    _socket(tree, "Geometry", "OUTPUT", "NodeSocketGeometry")
    join = tree.nodes.new("GeometryNodeJoinGeometry")
    for member in members:
        group = tree.nodes.new("GeometryNodeGroup")
        group.node_tree = member
        tree.links.new(group.outputs[0], join.inputs[0])
    output = tree.nodes.new("NodeGroupOutput")
    tree.links.new(join.outputs["Geometry"], output.inputs["Geometry"])
    return tree


def _live_rows(trace, prefixes: tuple[str, ...]) -> list[dict]:
    table = trace.table
    rows = []
    for index in range(len(table)):
        if not table.alive[index]:
            continue
        branch = table.decode(table.branches, int(table.branch_code[index])) or ""
        if not branch.startswith(prefixes):
            continue
        matrix = table.transform[index]
        rows.append(
            {
                "x": float(matrix[3]),
                "y": float(matrix[7]),
                "z": float(matrix[11]),
                "lid": pack_int32x4(table.logical_id[index].tobytes()),
                "sample": int(table.sample_key[index]),
                "branch": int(table.branch_code[index]),
                "source": int(table.source_code[index]),
                "logical_id": table.logical_hex(index),
                "pick": int(table.source_code[index]),
            }
        )
    return rows


def _read_ints(mesh, name: str) -> list[int]:
    attribute = mesh.attributes.get(name)
    if attribute is None:
        return []
    return [int(item.value) for item in attribute.data]


def _unique_instances(mesh) -> list[dict]:
    lids = list(
        zip(
            _read_ints(mesh, "it_lid_0"),
            _read_ints(mesh, "it_lid_1"),
            _read_ints(mesh, "it_lid_2"),
            _read_ints(mesh, "it_lid_3"),
            strict=False,
        )
    )
    samples = _read_ints(mesh, "it_sample")
    branches = _read_ints(mesh, "it_branch")
    sources = _read_ints(mesh, "it_source")
    found: dict[tuple, dict] = {}
    for index, lid in enumerate(lids):
        if lid in found:
            found[lid]["repeats"] += 1
            continue
        found[lid] = {
            "it_lid": list(lid),
            "it_sample": samples[index] if index < len(samples) else None,
            "it_branch": branches[index] if index < len(branches) else None,
            "it_source": sources[index] if index < len(sources) else None,
            "repeats": 1,
        }
    return list(found.values())


def _depsgraph_instances(host_name: str) -> list[dict]:
    depsgraph = bpy.context.evaluated_depsgraph_get()
    found = []
    for index, item in enumerate(depsgraph.object_instances):
        parent = item.parent.original if item.parent is not None else None
        if parent is None or parent.name != host_name or not item.is_instance:
            continue
        instance_object = item.instance_object.name if item.instance_object is not None else None
        found.append(
            {
                "evaluated_index": index,
                "object_name": item.object.name if item.object is not None else "",
                "instance_object_name": instance_object,
                "parent_name": parent.name,
                "is_instance": True,
                "persistent_id": [int(value) for value in item.persistent_id],
                "random_id": int(item.random_id),
                "matrix_world": [float(item.matrix_world[row][col]) for row in range(4) for col in range(4)],
            }
        )
    return found


def main() -> None:
    options = _args()
    out = Path(options["out"])
    out.mkdir(parents=True, exist_ok=True)
    program = habitat_program()
    predicted = execute(program)
    target = highlighted_id(predicted)

    _quad("IT_Panel_A", 0.0)
    _quad("IT_Panel_B", 0.02)
    _quad("IT_Mullion", 0.0)
    windows = _live_rows(predicted, ("bay.",))
    mullions = _live_rows(predicted, ("mullion.",))
    window_points = _points("IT_WindowPoints", windows)
    mullion_points = _points("IT_MullionPoints", mullions)

    collection = _source_collection()
    # Blender 5.2.2 pick-instance index followed sorted object name, not link order.
    order = sorted(obj.name for obj in collection.objects)
    source_names = list(predicted.table.sources)
    for row in windows + mullions:
        object_name = SOURCE_OBJECTS[source_names[row["source"]]]
        row["pick"] = order.index(object_name)
    # Attributes were written before the collection order was known. Rewrite it_pick.
    for obj, rows in ((window_points, windows), (mullion_points, mullions)):
        attribute = obj.data.attributes["it_pick"]
        for index, row in enumerate(rows):
            attribute.data[index].value = int(row["pick"])
    window_tree = _instance_sources("IT_WindowScatter", window_points, collection)
    mullion_tree = _instance_sources("IT_MullionScatter", mullion_points, collection)
    bay = _join_groups("IT_BayModule", [window_tree, mullion_tree])
    habitat = _wrapper("IT_HabitatModule", bay, realize=False)
    probe_tree = _wrapper("IT_HabitatProbe", habitat, realize=True)

    scatter = bpy.data.objects.new("IT_Scatter", bpy.data.meshes.new("IT_ScatterMesh"))
    probe = bpy.data.objects.new("IT_Probe", bpy.data.meshes.new("IT_ProbeMesh"))
    for obj, tree in ((scatter, habitat), (probe, probe_tree)):
        bpy.context.scene.collection.objects.link(obj)
        modifier = obj.modifiers.new("InstanceTrace", "NODES")
        modifier.node_group = tree

    bpy.context.view_layer.update()
    instances = _depsgraph_instances("IT_Scatter")
    probe_eval = probe.evaluated_get(bpy.context.evaluated_depsgraph_get())
    unique = _unique_instances(probe_eval.data)
    by_lid = {tuple(item["it_lid"]): item for item in unique}

    # Pair runtime instances with realized ids by translation, and keep attribute
    # rows even when a translation is shared. Attributes are the identity source.
    dump_instances = []
    for item in unique:
        dump_instances.append(
            {
                "evaluated_index": len(dump_instances),
                "object_name": "IT_Probe",
                "instance_object_name": None,
                "parent_name": "IT_Probe",
                "is_instance": False,
                "persistent_id": [0, 0, 0, 0, 0, 0, 0, 0],
                "random_id": 0,
                "matrix_world": [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1],
                "attributes_read": True,
                "it_lid": item["it_lid"],
                "it_sample": item["it_sample"],
                "it_branch": item["it_branch"],
                "it_source": item["it_source"],
                "vertex_repeats": item["repeats"],
            }
        )
    # Attach one depsgraph transform when the translation matches a point we authored.
    authored = {(round(row["x"], 5), round(row["y"], 5), round(row["z"], 5)): row for row in windows + mullions}
    source_names = list(predicted.table.sources)
    for inst in instances:
        translation = (
            round(inst["matrix_world"][3], 5),
            round(inst["matrix_world"][7], 5),
            round(inst["matrix_world"][11], 5),
        )
        authored_row = authored.get(translation)
        if authored_row is None:
            continue
        expected = SOURCE_OBJECTS.get(source_names[authored_row["source"]])
        if inst["instance_object_name"] != expected:
            continue
        for record in dump_instances:
            if tuple(record["it_lid"]) != tuple(authored_row["lid"]) or record.get("paired"):
                continue
            record["matrix_world"] = inst["matrix_world"]
            record["persistent_id"] = inst["persistent_id"]
            record["random_id"] = inst["random_id"]
            record["object_name"] = inst["instance_object_name"] or inst["object_name"]
            record["instance_object_name"] = inst["instance_object_name"]
            record["parent_name"] = inst["parent_name"]
            record["is_instance"] = True
            record["evaluated_index"] = inst["evaluated_index"]
            record["paired"] = True
            break

    dump = {
        "format": "instancetrace.blender_capture",
        "format_version": 1,
        "capture_mode": "INSTRUMENTED",
        "blender_version": bpy.app.version_string,
        "scene_id": program.scene_id,
        "frame": bpy.context.scene.frame_current,
        "units": "blender_units",
        "unit_scale_to_meters": float(bpy.context.scene.unit_settings.scale_length),
        "coordinate_system": "right_handed_z_up",
        "attribute_read_path": "realized_probe_point_domain",
        "confidence_ceiling": "PARTIAL",
        "ceiling_reason": "REALIZE_DOMAIN_CHANGE",
        "codebook": {
            "branches": list(predicted.table.branches),
            "sources": list(predicted.table.sources),
            "paths": list(predicted.table.paths),
        },
        "depsgraph_instance_count": len(instances),
        "unique_attribute_ids": len(unique),
        "instances": dump_instances,
        "notes": [
            "Named attributes were read from IT_Probe after Realize Instances.",
            "IT_Scatter keeps instances. DepsgraphObjectInstance did not expose it_lid_*.",
            "persistent_id and random_id are copied from the depsgraph when a translation matched.",
        ],
    }
    (out / "capture.json").write_text(json.dumps(dump, indent=2) + "\n", encoding="utf-8")
    traced = import_instrumented_dump(dump, program)
    save_trace(traced, out / "trace.json")
    report = query_logical(traced, target)
    (out / "lineage.txt").write_text(format_report(report), encoding="utf-8")

    passive_instances = []
    for inst in instances:
        passive_instances.append(
            {
                "evaluated_index": inst["evaluated_index"],
                "object_name": inst["instance_object_name"] or inst["object_name"],
                "parent_name": inst["parent_name"],
                "is_instance": True,
                "persistent_id": inst["persistent_id"],
                "random_id": inst["random_id"],
                "matrix_world": inst["matrix_world"],
            }
        )
    passive = {
        "format": "instancetrace.blender_capture",
        "format_version": 1,
        "capture_mode": "PASSIVE_ONLY",
        "blender_version": bpy.app.version_string,
        "scene_id": program.scene_id,
        "frame": bpy.context.scene.frame_current,
        "instances": passive_instances,
    }
    passive_trace = import_passive_dump(passive)
    save_trace(passive_trace, out / "passive" / "trace.json")

    summary = {
        "blender_version": bpy.app.version_string,
        "instance_id": target,
        "origin_status": report["origin_status"],
        "confidence": report["confidence"],
        "source_id": report.get("source_id"),
        "source_label": report.get("source_label"),
        "instrumented_path": report.get("instrumented_path"),
        "branch_id": report.get("branch_id"),
        "sample_key": report.get("sample_key"),
        "seed": report.get("seed"),
        "depsgraph_instances": len(instances),
        "attribute_ids": len(unique),
        "first_instance_object": instances[0]["instance_object_name"] if instances else None,
        "first_persistent_id": instances[0]["persistent_id"] if instances else None,
        "collection_order": order,
        "saved_blend": False,
    }
    if options["save"]:
        blend = out / "habitat.blend"
        bpy.ops.wm.save_as_mainfile(filepath=str(blend))
        summary["saved_blend"] = True
    highlight_lid = tuple(pack_int32x4(bytes.fromhex(target[2:])))
    paired = [record for record in dump_instances if tuple(record["it_lid"]) == highlight_lid]
    paired_name = paired[0].get("instance_object_name") if paired else None
    summary["paired_instance_object"] = paired_name
    summary["attribute_read_back"] = highlight_lid in by_lid
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print("BLENDER_CAPTURE")
    print(json.dumps(summary, indent=2))
    print(format_report(report))
    if report.get("source_id") != "src:hk.panel_a":
        raise SystemExit("captured source did not match Panel_A")
    if "src:hk.window_scatter" not in (report.get("instrumented_path") or ""):
        raise SystemExit("captured path lost WindowScatter")
    if not instances:
        raise SystemExit("depsgraph returned no instances")
    if target not in {row["logical_id"] for row in windows}:
        raise SystemExit("highlight id was not authored onto the point cloud")
    if highlight_lid not in {tuple(item["it_lid"]) for item in unique}:
        raise SystemExit("highlight id was not read back from realized attributes")
    if paired_name != "IT_Panel_A":
        raise SystemExit(f"highlight depsgraph object was {paired_name}")


if __name__ == "__main__":
    main()
