# InstanceTrace

InstanceTrace answers a narrow question for a supported procedural instance: which generator, branch, source asset, seed, and operations produced it.

An instrumented habitat window reports its source object, nested group path, authored sample key, and seed. A realize probe that had to change attribute domain stays `PARTIAL_TRACE`. An uninstrumented object stays `PASSIVE_ONLY` or `UNKNOWN_ORIGIN`. A realize, join, or remesh that drops identity becomes `LINEAGE_AMBIGUOUS` or `UNSUPPORTED_OR_LOST`. The tracer does not invent a node chain for those cases.

The offline package is Python 3.11+ and does not import `bpy`. Blender 5.2.2 is the host that was actually evaluated. Houdini and Unreal adapters refuse to answer until a host experiment exists.

## Demo

```bash
pip install -e ".[dev]"
instancetrace demo --out build/demo
```

The command prints a logical id from the HK Habitat Module facade (namespace `plygonality.instancetrace.hk.habitat`, seed 218). On the current declaration that highlighted bay-L `Panel_A` window is:

```text
0xd587c79a52f095ed9d49adfc66978cf5
```

```bash
instancetrace query build/demo/trace.json \
  --instance-id 0xd587c79a52f095ed9d49adfc66978cf5 --format text
```

The offline report names `Panel_A`, group path `src:hk.habitat.module/src:hk.bay/src:hk.window_scatter`, branch `bay.L`, sample key 2, and seed 218. `build/demo/runB` regenerates the right bay at seed 219. `build/demo/continuity.json` lists ids that persisted and ids that changed. `build/demo/loss` runs the same id through a realize step that does not keep an exact parent.

The same id was read back from a real Blender 5.2.2 LTS session (hash `d13f752e3b9c`). The depsgraph object was `IT_Panel_A`. Because the integers were read after Realize Instances, that host report is `PARTIAL_TRACE` with `REALIZE_DOMAIN_CHANGE`. Details are in `docs/host-capabilities.md`.

```bash
blender --background --python examples/blender/build_habitat_and_capture.py -- --out build/blender-habitat
```

## Layout

```text
src/instancetrace/     schema, ids, event DAG, storage, query, CLI
blender_addon/         N-panel extension plygonality_instancetrace
examples/blender/      probe, habitat capture, addon smoke
examples/habitat/      committed offline demo
tests/                 acceptance, storage, and optional Blender host tests
docs/                  identity contract, host notes, loss policy, privacy
```

## Panel

Install the extension in `blender_addon/plygonality_instancetrace`, with this repository's `src` on Blender's Python path (an editable install into Blender's Python does that). The sidebar tab is **InstanceTrace**. It can capture the current scene, query an id, highlight a source object when that object exists, write an HTML event graph, and list loss points. Pick Instance is a bounds prototype. The panel does not save the blend file, replace meshes, or delete objects outside `IT_` overlay collections.

## Tests

```bash
ruff check src tests blender_addon examples
pytest
```

Host tests skip when no Blender executable is configured. Set `INSTANCETRACE_BLENDER` to run them. A skip is not a host result.

Further reading: `docs/cli.md`, `docs/identity-contract.md`, `docs/lineage-loss.md`, `docs/privacy.md`, `docs/known-issues.md`.
