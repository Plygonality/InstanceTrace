# Known issues

These are the limits that should be handled before calling a trace exact, in the order they bite.

1. **Instance attributes are not readable on the depsgraph.** Blender 5.2.2 exposes transforms and `persistent_id` on `DepsgraphObjectInstance`, and it does not expose Geometry Nodes named attributes there. The habitat fixture realizes a separate `IT_Probe` mesh to read `it_lid_*`. That read changes the domain from instance to point and repeats the id once per vertex, so the captured origin is `PARTIAL_TRACE` with `REALIZE_DOMAIN_CHANGE`. An exact evaluated chain needs a read path that does not realize.

2. **Collection pick index is host-specific.** On 5.2.2, Pick Instance followed sorted object name, not collection link order. The fixture writes `it_pick` from that sorted order. Another Blender version needs the same experiment before that index is trusted. A wrong index places the right logical id on the wrong mesh.

3. **Picking a rendered instance is not selection.** `persistent_id` and `random_id` are runtime locators. `random_id` was observed negative, and unused `persistent_id` slots were `2147483647`. Geometry Nodes instances do not appear in `bpy.context.selected_objects`. The N-panel pick raycasts captured boxes and returns `AMBIGUOUS_PICK` or `PICK_UNSUPPORTED`. Query by logical id is the supported inspection path.

4. **Most sibling generators were not available to instrument.** On 2026-10-16, gn-as-code, Probe-kit, Habitat-kit, Blend-ci, Time-slice, Collection-linter, and Unit-canon were not public. NodeBridge ids can be imported and are not executed. Houdini and Unreal adapters raise `UnverifiedHost`. A matching seed or layout across those hosts is not a shared logical id.

5. **Recorded scale is the offline scatter bench on one machine.** The 1,000 / 10,000 / 100,000 runs in `docs/evidence/bench-2026-10-16.json` measure this repository's Python grammar, with tracemalloc peaks rather than resident memory. They do not measure Blender evaluation. Counts that are absent from that file were not run. The v0.1 grammar has no loop step, so `LOOP_SUMMARISED` is unused.
