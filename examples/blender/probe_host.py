"""Probe Blender 5.2 depsgraph and named-attribute behaviour.

Run:
  blender --background --python examples/blender/probe_host.py -- --out /tmp/it-probe.json

This script only adds IT_ objects. It does not delete the default scene.
"""

from __future__ import annotations

import json
import sys
import traceback

import bpy

OUT = "/tmp/it-probe.json"
if "--" in sys.argv:
    args = sys.argv[sys.argv.index("--") + 1 :]
    if "--out" in args:
        OUT = args[args.index("--out") + 1]


def note(bucket, message):
    bucket.append(message)
    print(message)


def main():
    report = {
        "blender_version": bpy.app.version_string,
        "notes": [],
        "attribute_data_types": [],
        "attribute_domains": [],
        "instances_before_realize": [],
        "evaluated_attributes_before_realize": [],
        "instances_after_realize": [],
        "evaluated_attributes_after_realize": [],
        "string_attribute": None,
        "instance_domain_on_mesh": None,
        "nested_group": None,
        "errors": [],
    }
    try:
        report["attribute_data_types"] = [
            item.identifier for item in bpy.types.Attribute.bl_rna.properties["data_type"].enum_items
        ]
    except Exception as exc:  # noqa: BLE001
        report["errors"].append(f"data_type enum: {exc}")
    try:
        report["attribute_domains"] = [
            item.identifier for item in bpy.types.Attribute.bl_rna.properties["domain"].enum_items
        ]
    except Exception as exc:  # noqa: BLE001
        report["errors"].append(f"domain enum: {exc}")

    panel = bpy.data.meshes.new("IT_Panel_A")
    panel.from_pydata([(-0.2, -0.05, -0.2), (0.2, -0.05, -0.2), (0.2, 0.05, 0.2), (-0.2, 0.05, 0.2)], [], [(0, 1, 2, 3)])
    panel_obj = bpy.data.objects.new("IT_Panel_A", panel)
    bpy.context.scene.collection.objects.link(panel_obj)

    points = bpy.data.meshes.new("IT_Points")
    points.from_pydata([(i * 0.8, 0.0, 1.5) for i in range(4)], [], [])
    attr = points.attributes.new("it_lid_0", "INT", "POINT")
    for index in range(4):
        attr.data[index].value = 100 + index
    try:
        string_attr = points.attributes.new("it_name", "STRING", "POINT")
        string_attr.data[0].value = "Panel_A"
        report["string_attribute"] = "created_on_point"
    except Exception as exc:  # noqa: BLE001
        report["string_attribute"] = f"failed: {exc}"
    try:
        points.attributes.new("it_inst", "INT", "INSTANCE")
        report["instance_domain_on_mesh"] = "created"
    except Exception as exc:  # noqa: BLE001
        report["instance_domain_on_mesh"] = f"failed: {exc}"
    points_obj = bpy.data.objects.new("IT_Points", points)
    bpy.context.scene.collection.objects.link(points_obj)

    tree = bpy.data.node_groups.new("IT_WindowScatter", "GeometryNodeTree")
    tree.interface.new_socket(name="Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    tree.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    nodes = tree.nodes
    links = tree.links
    group_in = nodes.new("NodeGroupInput")
    group_out = nodes.new("NodeGroupOutput")
    info = nodes.new("GeometryNodeObjectInfo")
    info.inputs["Object"].default_value = points_obj
    info.transform_space = "RELATIVE"
    instance = nodes.new("GeometryNodeInstanceOnPoints")
    source = nodes.new("GeometryNodeObjectInfo")
    source.inputs["Object"].default_value = panel_obj
    source.transform_space = "ORIGINAL"
    store = nodes.new("GeometryNodeStoreNamedAttribute")
    store.data_type = "INT"
    store.domain = "INSTANCE"
    store.inputs["Name"].default_value = "it_lid_0"
    # Copy the point index-based value by reading the point attribute through a named attribute node if present.
    named = nodes.new("GeometryNodeInputNamedAttribute")
    named.data_type = "INT"
    named.inputs["Name"].default_value = "it_lid_0"
    links.new(info.outputs["Geometry"], instance.inputs["Points"])
    links.new(source.outputs["Geometry"], instance.inputs["Instance"])
    links.new(instance.outputs["Instances"], store.inputs["Geometry"])
    links.new(named.outputs["Attribute"], store.inputs["Value"])
    links.new(store.outputs["Geometry"], group_out.inputs["Geometry"])
    # Keep the group input linked so the modifier's geometry socket is used as a no-op companion.
    _ = group_in

    outer = bpy.data.node_groups.new("IT_Habitat", "GeometryNodeTree")
    outer.interface.new_socket(name="Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    outer.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    outer_in = outer.nodes.new("NodeGroupInput")
    outer_out = outer.nodes.new("NodeGroupOutput")
    group = outer.nodes.new("GeometryNodeGroup")
    group.node_tree = tree
    outer.links.new(group.outputs[0], outer_out.inputs[0])
    _ = outer_in
    report["nested_group"] = {"outer": outer.name, "inner": tree.name, "group_node": group.bl_idname}

    host = bpy.data.objects.new("IT_Scatter", bpy.data.meshes.new("IT_ScatterMesh"))
    bpy.context.scene.collection.objects.link(host)
    modifier = host.modifiers.new("InstanceTrace", "NODES")
    modifier.node_group = outer

    def capture(label):
        depsgraph = bpy.context.evaluated_depsgraph_get()
        host_eval = host.evaluated_get(depsgraph)
        attributes = []
        data = host_eval.data
        if hasattr(data, "attributes"):
            for attribute in data.attributes:
                values = []
                try:
                    for item in attribute.data:
                        if hasattr(item, "value"):
                            values.append(item.value)
                        elif hasattr(item, "vector"):
                            values.append(list(item.vector))
                except Exception as exc:  # noqa: BLE001
                    values = [f"unreadable: {exc}"]
                attributes.append(
                    {
                        "name": attribute.name,
                        "domain": str(attribute.domain),
                        "data_type": str(attribute.data_type),
                        "values_head": [int(v) if isinstance(v, int) else str(v) for v in values[:16]],
                        "count": len(values) if isinstance(values, list) else None,
                    }
                )
                if attribute.name == "it_lid_0":
                    note(report["notes"], f"{label} it_lid_0 domain={attribute.domain} count={len(values)} head={values[:16]}")
        report[f"evaluated_attributes_{label}"] = attributes
        report.setdefault("mesh_counts", {})[label] = {
            "verts": len(data.vertices) if hasattr(data, "vertices") else None,
            "polygons": len(data.polygons) if hasattr(data, "polygons") else None,
        }
        instances = []
        for index, item in enumerate(depsgraph.object_instances):
            parent = item.parent.original.name if item.parent is not None else None
            if parent != host.name and (item.object is None or not item.object.name.startswith("IT_")):
                continue
            if not item.is_instance and parent != host.name:
                continue
            instances.append(
                {
                    "index": index,
                    "is_instance": bool(item.is_instance),
                    "object": item.object.name if item.object else None,
                    "parent": parent,
                    "persistent_id": [int(v) for v in item.persistent_id],
                    "random_id": int(item.random_id),
                    "translation": [float(item.matrix_world[r][3]) for r in range(3)],
                }
            )
        report[f"instances_{label}"] = instances
        note(report["notes"], f"{label}: instances={len(instances)} attributes={[a['name'] for a in attributes]}")

    capture("before_realize")
    realize = nodes.new("GeometryNodeRealizeInstances")
    # Rewire store -> realize -> group out
    for link in list(tree.links):
        if link.to_node == group_out:
            tree.links.remove(link)
    tree.links.new(store.outputs["Geometry"], realize.inputs["Geometry"])
    tree.links.new(realize.outputs["Geometry"], group_out.inputs["Geometry"])
    capture("after_realize")

    # Density change: move a point and see whether persistent_id stays put.
    points.vertices[0].co.x = -5.0
    capture("after_edit")
    report["notes"].append(
        "persistent_id values above are motion-blur matchers captured in this session; they are not logical ids."
    )
    with open(OUT, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
    print("WROTE", OUT)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
