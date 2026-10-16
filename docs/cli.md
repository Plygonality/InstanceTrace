# Command line

Install the package, then run the commands below. The demo prints a real logical id. `0x0000000000001234` is not an id this tool accepts.

```bash
pip install -e ".[dev]"
instancetrace demo --out build/demo
instancetrace inspect build/demo/trace.json
instancetrace query build/demo/trace.json --instance-id <printed-id> --format text
instancetrace query build/demo/trace.json --instance-id <printed-id> --format json
instancetrace graph build/demo/trace.json --instance-id <printed-id> --out reports/lineage.dot
instancetrace diff build/demo/runA/trace.json build/demo/runB/trace.json --out reports/continuity.json
instancetrace validate build/demo/trace.json
instancetrace doctor
```

`graph --out` writes Graphviz DOT, or HTML when the path ends in `.html`.

Exit codes: `0` when a report was produced, including an unknown origin; `2` for a malformed id or a refused capture flag; `3` for a corrupt manifest or an unsupported schema; `1` for another `InstanceTraceError`. `doctor` stays successful when Blender is absent. A missing Blender executable is a warning.

Other commands:

```bash
instancetrace capture --import capture.json --out build/imported
instancetrace capture --import passive.json --passive --out build/passive
instancetrace bench --counts 1000,10000,100000 --out build/bench
instancetrace redact build/demo/trace.json --out build/redacted
instancetrace redact build/demo/trace.json --out build/redacted-strict --strict
```

`capture` imports a JSON dump written by Blender. It does not launch Blender by itself. The authored program is applied by `examples/blender/build_habitat_and_capture.py`, because a system Python process cannot import `bpy`.

```bash
blender --background --python examples/blender/build_habitat_and_capture.py -- --out build/blender-habitat
blender --background --python examples/blender/smoke_addon.py
```

Set `INSTANCETRACE_BLENDER` when `blender` is not on `PATH`. Adding `--save` to the habitat script writes `habitat.blend` in the output directory. Without `--save` the blend file is left untouched.

`bench` prints wall time, a tracemalloc peak, manifest size, and query time for this process. The numbers are measurements of that run. See `docs/known-issues.md`.
