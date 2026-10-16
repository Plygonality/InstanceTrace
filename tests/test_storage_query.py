"""Round-trip, corruption, privacy, sqlite, and passive capture."""

from __future__ import annotations

import json

import pytest

from instancetrace.capture.instrumented import import_instrumented_dump
from instancetrace.capture.passive import import_passive_dump
from instancetrace.demo.habitat import habitat_program, highlighted_id
from instancetrace.errors import CorruptManifest, SchemaVersionError, UnverifiedHost
from instancetrace.ids.codec import pack_int32x4, parse_id, unpack_int32x4
from instancetrace.ids.registry import IdRegistry
from instancetrace.instrument.execute import execute
from instancetrace.instrument.gn_as_code import import_identifiers, probe_installed_package
from instancetrace.instrument.gn_plan import plan_geometry_nodes
from instancetrace.instrument.nodebridge_import import import_node_identifiers
from instancetrace.privacy.filter import redact
from instancetrace.query.engine import query_locator, query_logical
from instancetrace.schema.migrate import migrate
from instancetrace.storage.manifest import load_trace, save_trace
from instancetrace.storage.sqlite_index import build_sqlite, lookup_sqlite


def test_round_trip(tmp_path):
    trace = execute(habitat_program())
    path = save_trace(trace, tmp_path / "trace.json")
    loaded = load_trace(path)
    assert loaded.meta.source_revision == trace.meta.source_revision
    assert loaded.meta.units == "meters"
    assert loaded.meta.unit_scale_to_meters == trace.meta.unit_scale_to_meters
    assert [event.event_id for event in loaded.events] == [event.event_id for event in trace.events]
    assert [event.parent_event_ids for event in loaded.events] == [event.parent_event_ids for event in trace.events]
    assert list(loaded.index) == list(trace.index)
    row = 0
    assert loaded.table.logical_hex(row) == trace.table.logical_hex(row)
    assert loaded.table.transform[row].tolist() == pytest.approx(trace.table.transform[row].tolist())


def test_corruption_is_detected(tmp_path):
    trace = execute(habitat_program())
    path = save_trace(trace, tmp_path / "trace.json")
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace("meters", "meterz"), encoding="utf-8")
    with pytest.raises(CorruptManifest):
        load_trace(path)
    path.write_text(text, encoding="utf-8")
    npz = path.with_suffix(".npz")
    data = bytearray(npz.read_bytes())
    data[80] ^= 0xFF
    npz.write_bytes(data)
    with pytest.raises(CorruptManifest):
        load_trace(path)


def test_unknown_schema_is_rejected():
    with pytest.raises(SchemaVersionError):
        migrate({"trace_schema_version": "9.9.9"})


def test_privacy_strips_labels(tmp_path):
    trace = execute(habitat_program())
    hidden = redact(trace)
    assert hidden.meta.labels == {}
    assert all(event.display_path is None for event in hidden.events)
    assert hidden.meta.privacy["telemetry"] is False
    strict = redact(execute(habitat_program()), strict=True)
    assert "Panel_A" not in json.dumps(strict.meta.to_dict())
    assert "src:hk.panel_a" not in json.dumps(strict.meta.to_dict())
    save_trace(strict, tmp_path / "trace.json")
    load_trace(tmp_path / "trace.json")


def test_pack_int32_round_trip():
    raw = bytes(range(16))
    assert unpack_int32x4(pack_int32x4(raw)) == raw
    high = bytes([255, 255, 255, 255]) + bytes(12)
    assert unpack_int32x4(pack_int32x4(high)) == high


def test_collision_registry():
    registry = IdRegistry()
    assert registry.register(b"a" * 16, b"one") == "ok"
    assert registry.register(b"a" * 16, b"one") == "duplicate"
    assert registry.register(b"a" * 16, b"two") == "collision"
    assert registry.collisions


def test_passive_has_no_generator(tmp_path):
    dump = {
        "format": "instancetrace.blender_capture",
        "format_version": 1,
        "capture_mode": "PASSIVE_ONLY",
        "blender_version": "5.2.2",
        "scene_id": "scene:passive",
        "frame": 3,
        "instances": [
            {
                "evaluated_index": 0,
                "object_name": "Panel_A",
                "parent_name": "Scatter",
                "is_instance": True,
                "persistent_id": [1, 0, 0, 0, 0, 0, 0, 0],
                "random_id": 99,
                "matrix_world": [1, 0, 0, 2, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1],
            }
        ],
    }
    trace = import_passive_dump(dump)
    assert trace.meta.capture_mode == "PASSIVE_ONLY"
    assert trace.meta.seed is None
    path = save_trace(trace, tmp_path / "trace.json")
    loaded = load_trace(path)
    logical = query_logical(loaded, "0x" + "ab" * 16)
    assert logical["origin_status"] == "UNKNOWN_ORIGIN"
    assert logical["generator_known"] is False
    text = json.dumps(logical)
    assert "src:hk.window_scatter" not in text
    assert "WindowScatter" not in text
    locator = loaded.table.locator(0)
    found = query_locator(loaded, locator)
    assert found["origin_status"] == "PASSIVE_ONLY"
    assert found["runtime_object"] == "Panel_A"
    assert found["seed"] is None
    assert found["branch_id"] is None
    assert "persistent_id" in " ".join(found["notes"])


def test_unreadable_instrumentation_does_not_invent_a_chain():
    program = habitat_program()
    predicted = execute(program)
    instance_id = highlighted_id(predicted)
    dump = {
        "format": "instancetrace.blender_capture",
        "format_version": 1,
        "capture_mode": "INSTRUMENTED",
        "blender_version": "5.2.2",
        "scene_id": program.scene_id,
        "frame": 1,
        "attribute_read_path": "unavailable",
        "instances": [
            {
                "evaluated_index": 0,
                "object_name": "IT_Panel_A",
                "parent_name": "IT_Scatter",
                "persistent_id": [0, 0, 0, 0, 0, 0, 0, 0],
                "random_id": 1,
                "matrix_world": [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1],
                "attributes_read": False,
            }
        ],
    }
    trace = import_instrumented_dump(dump, program)
    report = query_logical(trace, instance_id)
    assert report["found"] is False
    assert report["origin_status"] == "NOT_IN_MANIFEST"
    locator = trace.table.locator(0)
    located = query_locator(trace, locator)
    assert located["generator_known"] is False
    assert located["source_id"] in {None, ""}
    assert "src:hk.window_scatter" not in json.dumps(located["operations"])


def test_attribute_match_uses_host_bytes():
    program = habitat_program(count=4, predicate="never")
    predicted = execute(program)
    row = 0
    raw = predicted.table.logical_id[row].tobytes()
    codebook = {
        "branches": predicted.table.branches,
        "sources": predicted.table.sources,
        "paths": predicted.table.paths,
    }
    dump = {
        "format": "instancetrace.blender_capture",
        "format_version": 1,
        "capture_mode": "INSTRUMENTED",
        "blender_version": "5.2.2",
        "scene_id": program.scene_id,
        "frame": 1,
        "attribute_read_path": "point_attributes",
        "codebook": codebook,
        "instances": [
            {
                "evaluated_index": 0,
                "object_name": "IT_Panel_A",
                "parent_name": "IT_Scatter",
                "persistent_id": [4, 0, 0, 0, 0, 0, 0, 0],
                "random_id": 3,
                "matrix_world": [1, 0, 0, 0.25, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1],
                "attributes_read": True,
                "it_lid": list(pack_int32x4(raw)),
                "it_sample": int(predicted.table.sample_key[row]),
                "it_branch": int(predicted.table.branch_code[row]),
                "it_source": int(predicted.table.source_code[row]),
            }
        ],
    }
    trace = import_instrumented_dump(dump, program)
    report = query_logical(trace, format_id_from(raw))
    assert report["found"] is True
    assert report["origin_status"] == "EXACT"
    assert report["source_id"]
    assert "src:hk.window_scatter" in report["instrumented_path"]
    assert report["transform"][3] == pytest.approx(0.25)
    # A host id that was never authored is not replaced with a program id.
    foreign = bytes([9]) * 16
    dump["instances"].append(
        {
            "evaluated_index": 1,
            "object_name": "IT_Other",
            "parent_name": "IT_Scatter",
            "persistent_id": [0, 0, 0, 0, 0, 0, 0, 0],
            "random_id": 1,
            "matrix_world": [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1],
            "attributes_read": True,
            "it_lid": list(pack_int32x4(foreign)),
            "it_sample": 0,
            "it_branch": 0,
            "it_source": 0,
        }
    )
    mixed = import_instrumented_dump(dump, program)
    foreign_report = query_logical(mixed, format_id_from(foreign))
    assert foreign_report["confidence"] == "PARTIAL"
    assert foreign_report["origin_status"] != "EXACT"
    assert "src:hk.window_scatter" not in (foreign_report.get("instrumented_path") or "")


def format_id_from(raw: bytes) -> str:
    return "0x" + raw.hex()


def test_sqlite_lookup(tmp_path):
    trace = execute(habitat_program())
    path = build_sqlite(trace, tmp_path / "index.sqlite")
    logical = parse_id(highlighted_id(trace))
    assert lookup_sqlite(path, logical) == trace.index[logical][0]


def test_nodebridge_identifiers_are_not_a_trace():
    graph = {
        "format": "nodebridge.graph",
        "format_version": 1,
        "trees": [
            {
                "name": "Scatter",
                "nodes": [
                    {"id": "Group Input", "type": "NodeGroupInput", "name": "Group Input"},
                    {"id": "src:scatter.points", "type": "FunctionNode", "name": "Points", "label": "Points"},
                ],
            }
        ],
    }
    refs = import_node_identifiers(graph)
    assert refs[0]["label_independent"] is False
    assert refs[1]["label_independent"] is True
    assert probe_installed_package()["available"] is False
    ident = import_identifiers({"format": "gn_as_code.graph", "nodes": [{"id": "src:a", "label": "A", "type": "instance"}]})
    assert ident[0]["executed"] is False


def test_plan_names_integer_attributes():
    plan = plan_geometry_nodes(habitat_program())
    names = plan["nodes"][0]["names"]
    assert "it_lid_0" in names
    assert plan["attributes"]["data_type"] == "INT"


def test_unverified_hosts_refuse():
    from instancetrace.adapters.houdini import trace_points
    from instancetrace.adapters.unreal import trace_pcg

    with pytest.raises(UnverifiedHost):
        trace_points()
    with pytest.raises(UnverifiedHost):
        trace_pcg()
