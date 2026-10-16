# Blender fixtures

These scripts run inside Blender:

```bash
blender --background --python examples/blender/probe_host.py -- --out /tmp/it-probe.json
blender --background --python examples/blender/build_habitat_and_capture.py -- --out build/blender-habitat
blender --background --python examples/blender/smoke_addon.py
```

`probe_host.py` records depsgraph fields and attribute behaviour for the installed Blender. `build_habitat_and_capture.py` builds the nested HK habitat scatter, evaluates it, and writes `trace.json`. It saves a `.blend` only with `--save`. `smoke_addon.py` registers the N-panel, captures the startup scene as `PASSIVE_ONLY`, and checks that existing objects are still there.

The offline package never imports these modules.
