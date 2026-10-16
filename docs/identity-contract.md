# Identity contract

Four identities stay separate. A trace may store more than one of them on the same row, and none of them is silently substituted for another.

## Source identity

A source id is assigned by the author or by a graph serializer. `src:hk.panel_a` stays the same when the display label changes from `Panel_A` to something else. Display labels live in the manifest label map. They are not part of the source-revision fingerprint.

## Generation-event identity

An event id is an immutable BLAKE2b-128 digest over domain `instancetrace.event.v1`. The preimage includes the graph id, source revision, event type, instrumented path, seed, ordinal, ordered parent event ids, and a config fingerprint. The config fingerprint rejects executable keys (`script`, `python`, `python_source`, `executable`, `eval`, `bytecode`, `source_code`, `exec`).

The same operation at a new ordinal or a new parent is a new event.

## Logical instance identity

A logical id is a BLAKE2b-128 digest over domain `instancetrace.logical.v1`. Python's built-in `hash()` is not used. The digest is displayed as `0x` plus 32 lowercase hex digits.

Preimage, in order:

1. `u32le` byte length, then UTF-8 namespace
2. `u32le` byte length, then UTF-8 source path
3. `u32le` parent count
4. each parent logical id as 16 raw bytes, in the order declared by the caller
5. `u32le` byte length, then UTF-8 branch id
6. `u8` sample mode: `0` authored integer, `1` index, `2` authored text
7. mode `0` or `1`: `i64le` sample key. Mode `2`: `u32le` byte length, then UTF-8 sample key
8. `i64le` seed

Frame, epoch, and source revision are coordinates. They are stored on the manifest and are absent from this preimage. Re-rendering the same inputs at another frame keeps the logical id. A changed namespace, source path, parent, branch, sample key, sample mode, or seed produces a different id.

Sibling branches do not collide when they share a local sample index, because the branch id is inside the preimage. A duplicate of a full logical id is recorded and the extra row is not treated as a second live identity. A hash collision between different preimages is reported as `HASH_COLLISION` rather than merged.

Index mode sets confidence `PARTIAL` and loss reason `INDEX_ONLY_SAMPLING`. Reordering rows does not change an authored sample key. An index-only key follows the authored index, so a topology change that renumbers indexes breaks continuity.

## Evaluated object identity

`DepsgraphObjectInstance.persistent_id`, `random_id`, the evaluated index, and the object pointer are locators for one evaluation. The locator format is:

```text
eval:{scene_id}:f{frame}:{parent}:{object}:pid{ints}:i{index}:rnd{random_id}
```

On Blender 5.2.2, unused `persistent_id` slots were `2147483647`, and `random_id` was observed negative. Neither value is a logical id. See `docs/host-capabilities.md`.

## Source revision and continuity

The source revision is BLAKE2b-128 over domain `instancetrace.revision.v1`. The fingerprint includes group ids and parents, source ids and families, step fingerprints, units, seed, namespace, graph id, and coordinate system. It excludes display labels.

Continuity policy `logical-id-v1`:

- The same declaration, namespace, seed, and ordered source ids reproduce logical ids and ancestry.
- A changed stable source id changes the descendants whose path includes that source.
- A different source revision on the scene marks a query `INCOMPATIBLE`. An otherwise exact row is reported as `PARTIAL_TRACE`.
- A seed or sample-domain change is labelled by `instancetrace diff`. Logical ids that still match are `PERSISTED_UNDER_REVISION_CHANGE` only when the revision itself changed and the id bytes match. Matching bytes are not a claim that the graphs are the same generation.

## Schema

`trace_schema_version` is `0.1.0`. A manifest carries the graph id, source revision, scene id, frame, epoch, seed, units, unit scale, coordinate system, events, and instance rows. Migration accepts only `0.1.0`. A future version needs an explicit migrator.

Event types: `CREATE`, `SOURCE_OBJECT`, `DISTRIBUTE`, `INSTANCE`, `TRANSFORM`, `FILTER`, `MERGE`, `JOIN`, `REALIZE`, `REMOVE`, `DERIVE_ATTRIBUTE`, `UNSUPPORTED_OR_LOST`, `LINEAGE_AMBIGUOUS`.

The event graph is a DAG. `causal_order` emits parents before children, stops at a depth bound, and records `CYCLE_DETECTED` or `DEPTH_LIMIT`. Loops are not a v0.1 grammar step. `LOOP_SUMMARISED` is reserved and unused.
