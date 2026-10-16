# Host capabilities

Audit date: 2026-10-16. Sibling repositories were read when public and were not modified.

## Ecosystem

Public Plygonality repositories visible that day included InstanceTrace, NodeBridge, and Plygon-mcp, among others. These URLs returned 404:

- `Plygonality/gn-as-code`
- `Plygonality/Probe-kit`
- `Plygonality/Habitat-kit`
- `Plygonality/Blend-ci`
- `Plygonality/Time-slice`
- `Plygonality/Collection-linter`
- `Plygonality/Unit-canon`

`gn_as_code` is not an installed dependency. `instrument/gn_as_code.py` returns `available: false` unless that package is already installed, and a `gn_as_code.graph` document yields identifiers with `executed: false`.

NodeBridge documents with `format: nodebridge.graph` can be scanned for node ids. The scanner does not run NodeBridge's compiler. In the public scatter example, node `id` is often the node name, so `label_independent` is false. A NodeBridge id is a source identifier, not a proof that the translated graph has the same provenance as the original tree.

Plygon-mcp can query a live scene in other tools. InstanceTrace does not require it, and this package does not call it.

Collection and unit rules from the missing linter repositories stay out of provenance. Scale is a manifest field (`units`, `unit_scale_to_meters`, `coordinate_system`).

## Blender 5.2.2 LTS

Verified with Blender 5.2.2 LTS, hash `d13f752e3b9c`, built 2026-09-15, using `examples/blender/probe_host.py` and `examples/blender/build_habitat_and_capture.py`. Blender's embedded Python was 3.13. The offline suite uses a separate interpreter and does not import `bpy`.

`bpy.types.Depsgraph.object_instances` yields `DepsgraphObjectInstance` with `object`, `instance_object`, `parent`, `matrix_world`, `persistent_id` (8 ints), `random_id`, and `is_instance`. Named Geometry Nodes attributes were not present on that iterator. They were also absent from the evaluated mesh while instances remained unrealized.

`persistent_id` behaved as a motion-blur matcher. In a simple point scatter the second component followed `0 .. n-1` and the unused slots were `2147483647`. That pattern is not a durable logical id across collection instancing or topology changes. One captured `random_id` was `-1185792493`.

`Store Named Attribute` of type `INT` on the `INSTANCE` domain, fed from point attributes and then `Realize Instances`, landed on the `POINT` domain. A quad source repeated the value once per vertex (`100, 100, 100, 100, 101, ...`). Moving a source vertex did not renumber those stored integers. The read path therefore sets `confidence_ceiling` to `PARTIAL` and loss reason `REALIZE_DOMAIN_CHANGE` even when the integer matches the authored id.

A mesh datablock rejected domain `INSTANCE` with `Attribute domain not supported by this geometry type`. Assigning a Python `str` to a `STRING` attribute failed: `StringAttributeValue.value expected a bytes type, not str`. v0.1 stores four signed int32 limbs (`it_lid_0` .. `it_lid_3`) plus `it_sample`, `it_branch`, `it_source`, and a sidecar codebook. Strings are not written onto geometry.

Attribute data types observed on this build included `FLOAT`, `INT`, `BOOLEAN`, `FLOAT_VECTOR`, `FLOAT_COLOR`, `QUATERNION`, `FLOAT4X4`, `STRING`, `INT8`, `INT16_2D`, `INT32_2D`, `FLOAT2`, `FLOAT4`, and `BYTE_COLOR`. Domains included `POINT`, `EDGE`, `FACE`, `CORNER`, `CURVE`, `INSTANCE`, and `LAYER`.

Node construction that succeeded on this build:

- `node_groups.new(name, "GeometryNodeTree")` and geometry interface sockets
- `GeometryNodeGroup`, `GeometryNodeObjectInfo` (`RELATIVE` / `ORIGINAL`)
- `GeometryNodeInstanceOnPoints`
- `GeometryNodeStoreNamedAttribute` (`INT`, domain `INSTANCE`)
- `GeometryNodeInputNamedAttribute`
- `GeometryNodeRealizeInstances`
- `GeometryNodeJoinGeometry`, with both inputs linked to `inputs[0]` so the multi-input socket accumulates
- `GeometryNodeCollectionInfo` with Separate Children, Reset Children, Pick Instance, and Instance Index

`Collection Info` pick index followed sorted object name, not `collection.objects` link order. Link order was `IT_Panel_A`, `IT_Panel_B`, `IT_Mullion`. Alphabetical index was `IT_Mullion` 0, `IT_Panel_A` 1, `IT_Panel_B` 2. The fixture writes `it_pick` from the sorted names. This index rule is a 5.2.2 observation, not a promise about other versions.

When Pick Instance is false and a single Object Info mesh is instanced, `instance_object` was the scatter host `IT_Scatter`, so the depsgraph did not name the source mesh. With Pick Instance and the sorted index, `instance_object` was `IT_Panel_A`, `IT_Panel_B`, or `IT_Mullion`.

The habitat capture on this build read 40 depsgraph instances and 40 unique attribute ids. The highlighted logical id `0xd587c79a52f095ed9d49adfc66978cf5` resolved to source `src:hk.panel_a` (`Panel_A`), path `src:hk.habitat.module/src:hk.bay/src:hk.window_scatter/src:hk.panel_a`, branch `bay.L`, sample key 2, seed 218, and evaluated object `IT_Panel_A`. Origin status was `PARTIAL_TRACE` because the attribute read used a realize probe.

The N-panel is `blender_addon/plygonality_instancetrace`. Capture reads attributes that are already on evaluated meshes and does not insert Realize Instances into the user's modifier. Without those attributes the panel writes `PASSIVE_ONLY`. Geometry Nodes instances are not added to `bpy.context.selected_objects`. Highlight selects a scene object only when the locator's object name is in the view layer, and it places an `IT_Highlight` empty in `InstanceTrace_Overlay`. A node path is selected only after `resolve_node_path` matches a current node tree.

Viewport picking raycasts captured bounding boxes. Overlap along the ray is `AMBIGUOUS_PICK`. A background context, a missing region, or a capture with no depsgraph instance bounds is `PICK_UNSUPPORTED`.

## Houdini and Unreal

`adapters/houdini.py` and `adapters/unreal.py` raise `UnverifiedHost`. No Houdini or Unreal session was run for v0.1.

Unreal PCG already has a debug tree, node inspection, and point attributes. A future adapter would attach source and lineage metadata those inspectors do not store. It would not duplicate the point spreadsheet. Matching a seed or a scene layout across DCCs does not establish a shared logical id.

Houdini point and primitive attributes are the likely future carrier, after a host experiment confirms which attributes survive the SOP cooks this project cares about.
