"""CLI paths, scene guard, and the import boundary."""

from __future__ import annotations

import importlib
import json
import pkgutil
import sys

import instancetrace
from instancetrace.capture.scene_guard import (
    assert_deletion_allowed,
    deletion_allowed,
    resolve_instrument_target,
    resolve_node_path,
)
from instancetrace.cli.main import main
from instancetrace.demo.habitat import build_demo
from instancetrace.errors import SceneSafetyError
from instancetrace.graph.dag import cycle_nodes
from instancetrace.schema.models import Event


def test_core_does_not_import_bpy():
    sys.modules.pop("bpy", None)
    package = importlib.import_module("instancetrace")
    for module in pkgutil.walk_packages(package.__path__, prefix="instancetrace."):
        importlib.import_module(module.name)
    assert "bpy" not in sys.modules


def test_demo_and_cli(tmp_path, capsys):
    out = tmp_path / "demo"
    instance_id = build_demo(out)
    assert (out / "trace.json").exists()
    assert (out / "trace.npz").exists()
    assert (out / "lineage.dot").read_text(encoding="utf-8").startswith("digraph")
    assert "LINEAGE" in (out / "loss" / "lineage.txt").read_text(encoding="utf-8").upper() or "AMBIGUOUS" in (
        out / "loss" / "lineage.txt"
    ).read_text(encoding="utf-8")
    continuity = json.loads((out / "continuity.json").read_text(encoding="utf-8"))
    assert continuity["counts"]["persisted"] > 0
    assert continuity["counts"]["changed_same_slot"] > 0

    assert main(["demo", "--out", str(tmp_path / "cli-demo")]) == 0
    printed = capsys.readouterr().out
    assert "instance 0x" in printed
    assert "0x0000000000001234" not in printed
    cli_id = [line.split()[-1] for line in printed.splitlines() if line.startswith("instance ")][0]
    assert main(["inspect", str(tmp_path / "cli-demo" / "trace.json")]) == 0
    assert main(["query", str(out / "trace.json"), "--instance-id", instance_id, "--format", "text"]) == 0
    text = capsys.readouterr().out
    assert "Panel_A" in text
    assert "src:hk.window_scatter" in text
    assert "218" in text
    assert main(["query", str(out / "trace.json"), "--instance-id", instance_id, "--format", "json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["source_id"] == "src:hk.panel_a"
    dot = tmp_path / "lineage.dot"
    assert main(["graph", str(out / "trace.json"), "--instance-id", instance_id, "--out", str(dot)]) == 0
    assert "digraph" in dot.read_text(encoding="utf-8")
    diff_path = tmp_path / "continuity.json"
    assert (
        main(
            [
                "diff",
                str(out / "runA" / "trace.json"),
                str(out / "runB" / "trace.json"),
                "--out",
                str(diff_path),
            ]
        )
        == 0
    )
    assert json.loads(diff_path.read_text(encoding="utf-8"))["counts"]["persisted"] > 0
    assert main(["validate", str(out / "trace.json")]) == 0
    assert main(["doctor"]) == 0
    assert main(["query", str(out / "trace.json"), "--instance-id", "0x0000000000001234"]) == 2
    assert cli_id.startswith("0x")
    _ = instancetrace.__version__


def test_scene_guard():
    assert deletion_allowed("IT_Overlay", {"InstanceTrace_Overlay"})
    assert not deletion_allowed("Cube", {"InstanceTrace_Overlay"})
    assert not deletion_allowed("IT_Overlay", {"Collection"})
    try:
        assert_deletion_allowed("Camera", set())
        raised = False
    except SceneSafetyError:
        raised = True
    assert raised
    assert resolve_instrument_target(original_name="Facade", allow_modify_original=False, confirm=False) == "IT_Facade"
    try:
        resolve_instrument_target(original_name="Facade", allow_modify_original=True, confirm=False)
        raised = False
    except SceneSafetyError:
        raised = True
    assert raised
    assert resolve_instrument_target(original_name="Facade", allow_modify_original=True, confirm=True) == "Facade"
    trees = {"WindowScatter": {"Instance on Points", "Store Named Attribute"}}
    assert resolve_node_path(trees, "WindowScatter/Instance on Points") == ("WindowScatter", "Instance on Points")
    assert resolve_node_path(trees, "Missing/Node") is None
    assert resolve_node_path(trees, "WindowScatter") is None


def test_cycle_detection():
    first = Event(
        event_id="0x" + "11" * 16,
        event_type="CREATE",
        instrumented_path="a",
        parent_event_ids=["0x" + "22" * 16],
        seed=None,
        notes="",
        confidence="EXACT",
        loss_reason=None,
        candidate_ancestor_ids=[],
        config={},
    )
    second = Event(
        event_id="0x" + "22" * 16,
        event_type="CREATE",
        instrumented_path="b",
        parent_event_ids=["0x" + "11" * 16],
        seed=None,
        notes="",
        confidence="EXACT",
        loss_reason=None,
        candidate_ancestor_ids=[],
        config={},
    )
    assert cycle_nodes([first, second])
