"""Host checks. They run only when a Blender executable is available."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _blender() -> str | None:
    env = os.environ.get("INSTANCETRACE_BLENDER")
    if env and Path(env).is_file():
        return env
    found = shutil.which("blender")
    if found:
        return found
    candidate = Path("/tmp/blender/blender")
    if candidate.is_file():
        return str(candidate)
    return None


def _run(script: str, extra: list[str]) -> subprocess.CompletedProcess[str]:
    blender = _blender()
    if blender is None:
        pytest.skip(
            "Blender executable not found. Set INSTANCETRACE_BLENDER. "
            "This host test is skipped rather than replaced with a mock."
        )
    return subprocess.run(
        [blender, "--background", "--python", str(ROOT / script), "--", *extra],
        check=False,
        capture_output=True,
        text=True,
        timeout=180,
    )


def test_habitat_capture_reads_panel_a(tmp_path: Path):
    out = tmp_path / "habitat"
    proc = _run("examples/blender/build_habitat_and_capture.py", ["--out", str(out)])
    if proc.returncode == 5 and "skipped" in proc.stdout:
        pytest.skip(proc.stdout)
    assert proc.returncode == 0, proc.stdout + "\n" + proc.stderr
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert summary["paired_instance_object"] == "IT_Panel_A"
    assert summary["source_id"] == "src:hk.panel_a"
    assert summary["source_label"] == "Panel_A"
    assert summary["instrumented_path"] == "src:hk.habitat.module/src:hk.bay/src:hk.window_scatter/src:hk.panel_a"
    assert summary["branch_id"] == "bay.L"
    assert summary["sample_key"] == 2
    assert summary["seed"] == 218
    assert summary["origin_status"] == "PARTIAL_TRACE"
    assert summary["confidence"] == "PARTIAL"
    assert summary["saved_blend"] is False
    assert summary["depsgraph_instances"] == 40
    assert summary["attribute_ids"] == 40
    assert "BLENDER_CAPTURE" in proc.stdout


def test_addon_smoke_leaves_startup_scene():
    proc = _run("examples/blender/smoke_addon.py", [])
    assert proc.returncode == 0, proc.stdout + "\n" + proc.stderr
    line = next(item for item in proc.stdout.splitlines() if item.startswith("{"))
    report = json.loads(line)
    assert report["capture_mode"] == "PASSIVE_ONLY"
    assert report["objects_unchanged"] is True
    assert report["filepath_unchanged"] is True
    assert report["pick_status"] == "PICK_UNSUPPORTED"
    assert report["query_origin"] in {"UNKNOWN_ORIGIN", "MALFORMED_ID", "NOT_IN_MANIFEST"}
