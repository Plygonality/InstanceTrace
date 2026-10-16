"""Local environment report. No network calls."""

from __future__ import annotations

import importlib.util
import os
import platform
import shutil
import tempfile
from pathlib import Path
from typing import Any

from instancetrace import TRACE_SCHEMA_VERSION, __version__


def doctor() -> dict[str, Any]:
    checks: list[dict[str, str]] = []

    def add(name: str, status: str, detail: str) -> None:
        checks.append({"name": name, "status": status, "detail": detail})

    add("python", "ok", platform.python_version())
    add("schema", "ok", TRACE_SCHEMA_VERSION)
    add("package", "ok", __version__)
    if importlib.util.find_spec("numpy") is None:
        add("numpy", "fail", "numpy is not importable")
    else:
        import numpy

        add("numpy", "ok", numpy.__version__)
    if importlib.util.find_spec("bpy") is None:
        add("bpy", "ok", "not imported in this interpreter; Blender capture is a separate executable")
    else:
        add("bpy", "warn", "bpy is visible to this interpreter; the offline core must still not import it")
    blender = os.environ.get("INSTANCETRACE_BLENDER") or shutil.which("blender")
    if blender and Path(blender).exists():
        add("blender", "ok", blender)
    else:
        add("blender", "warn", "no Blender executable on PATH; offline commands still run")
    try:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "write-test"
            path.write_text("ok", encoding="utf-8")
        add("write", "ok", "temporary directory is writable")
    except OSError as exc:
        add("write", "fail", str(exc))
    add("telemetry", "ok", "disabled")
    failed = any(item["status"] == "fail" for item in checks)
    return {
        "ok": not failed,
        "version": __version__,
        "schema": TRACE_SCHEMA_VERSION,
        "checks": checks,
    }
