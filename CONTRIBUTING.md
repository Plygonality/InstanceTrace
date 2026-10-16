# Contributing

The offline package in `src/instancetrace/` must import and test without Blender. Host code lives in `examples/blender/` and `blender_addon/`.

```bash
pip install -e ".[dev]"
ruff check src tests blender_addon examples
pytest
```

A Blender integration test runs when `INSTANCETRACE_BLENDER` points at a real executable. If that variable is unset and `blender` is not on `PATH`, the test skips. Do not replace it with a mock and then treat the skip as host validation.

Manifests can describe a private scene. The default tools write files locally and do not send telemetry. See `docs/privacy.md`.
