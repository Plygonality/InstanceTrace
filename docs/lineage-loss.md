# Lineage loss

A supported program is a declared vocabulary, not an arbitrary node tree.

v0.1 can represent:

- one source object, or a small set of source objects, with stable source ids
- deterministic sampled points and instancing with authored sample keys
- parent and local transforms, composed as `parent @ local` in row-major order
- a filter written as `sample_key % M == R` or `never`
- a nested group path known to the program
- an identity-preserving merge that keeps every live head as a parent
- a realize, lossy join, or unsupported step with an explicit loss reason

Predicates are matched as that grammar. They are not passed to `eval`.

## What each operation does to identity

| Operation | Live row | Report |
| --- | --- | --- |
| Filter match | Removed. The row stays in the log. | `REMOVE`. It is not a live output. |
| Identity-preserving merge | Keeps its own parent chain. | Container `MERGE` lists every parent event. |
| Merge that does not preserve identity | Ambiguous. | `LINEAGE_AMBIGUOUS` and the candidate ancestors. |
| Realize with `ids_survive` false | The logical id remains queryable. | `LINEAGE_AMBIGUOUS`. The chain is not marked exact. |
| Realize probe that reads `it_lid_*` after domain change | The host integers are kept when they match the program. | `PARTIAL` and `REALIZE_DOMAIN_CHANGE`. |
| Lossy join | Candidates are listed. | `LINEAGE_AMBIGUOUS` or the declared join reason. |
| Remesh, boolean, resample, topology change, export | No exact parent is chosen. | `UNSUPPORTED_OR_LOST` with that loss reason. |
| Index-only sampling | Id follows the index. | `PARTIAL` and `INDEX_ONLY_SAMPLING`. |
| Attribute missing at evaluation | Program chain is not attached. | `ATTRIBUTE_UNREADABLE` or `NOT_OBSERVED_AT_EVALUATION`. |
| Attribute id disagrees with the program | Host bytes win. | `PARTIAL` and `ATTRIBUTE_PROGRAM_MISMATCH`. |
| Passive depsgraph dump | Object, parent, matrix, `persistent_id`, `random_id`. | `PASSIVE_ONLY` and `NOT_INSTRUMENTED`. |

`Join Geometry`, remeshing, booleans, resampling, and export conversions do not automatically preserve a named attribute or its domain. A point attribute may survive one of those nodes and disappear in another. The trace records the policy of the step that was declared. It does not discover an undeclared node after the fact.

A deleted element can exist only in the event log. A merged output can have several parents. When an operation mixes identities, the event is `LINEAGE_AMBIGUOUS` and lists candidate ancestors.

## Passive capture

`PASSIVE_ONLY` stores runtime locators and transforms. Querying it with a logical id returns `UNKNOWN_ORIGIN`. The generating node, seed, and branch stay empty. `query_locator` can return the evaluated object and matrix for a locator that was actually captured.

## Scene safety

Instrumentation copies onto an `IT_` object unless `allow_modify_original` and `confirm` are both set. Deletion is allowed only for an `IT_` object whose collections are a subset of `InstanceTrace_Demo` and `InstanceTrace_Overlay`. The habitat script does not delete Cube, Light, or Camera, and it saves a `.blend` only when `--save` is passed.
