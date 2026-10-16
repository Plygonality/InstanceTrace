"""Acceptance checks for identity, loss, nesting, and continuity."""

from __future__ import annotations

from instancetrace.demo.habitat import PANEL_A, PANEL_B, habitat_program, highlighted_id
from instancetrace.instrument.execute import execute
from instancetrace.instrument.grammar import (
    Distribute,
    GroupDecl,
    InstanceOn,
    LossyJoinStep,
    Program,
    SourceDecl,
    TransformStep,
    UnsupportedStep,
)
from instancetrace.query.diff import diff_traces
from instancetrace.query.engine import query_logical
from instancetrace.schema.enums import FLAG_INDEX_UNSTABLE


def _ids(trace, *, alive_only=False):
    found = []
    for row in range(len(trace.table)):
        if alive_only and not trace.table.alive[row]:
            continue
        if trace.table.has_logical_id(row):
            found.append(trace.table.logical_hex(row))
    return found


def _row_for(trace, logical_hex: str) -> int:
    rows = trace.index[bytes.fromhex(logical_hex[2:])]
    return rows[0]


def test_determinism_and_source_change():
    first = execute(habitat_program())
    second = execute(habitat_program())
    assert _ids(first) == _ids(second)
    assert first.meta.source_revision == second.meta.source_revision
    changed = execute(habitat_program(panel_a="src:hk.panel_a.v2"))
    original = set(_ids(first))
    mutated = set(_ids(changed))
    assert original != mutated
    # Panel_B windows do not carry the panel_a id, so those logical ids stay.
    stable = []
    moved = []
    for row in range(len(first.table)):
        source = first.table.decode(first.table.sources, int(first.table.source_code[row]))
        parent = first.table.parent_hexes(row)
        logical = first.table.logical_hex(row)
        if source == PANEL_B and not parent:
            stable.append(logical)
        if source == PANEL_A:
            moved.append(logical)
    assert stable
    assert all(item in mutated for item in stable)
    assert all(item not in mutated for item in moved)


def test_sibling_branches_do_not_collide_and_duplicates_are_reported():
    trace = execute(habitat_program())
    left = {}
    right = {}
    for row in range(len(trace.table)):
        branch = trace.table.decode(trace.table.branches, int(trace.table.branch_code[row]))
        key = int(trace.table.sample_key[row])
        logical = trace.table.logical_hex(row)
        if branch == "bay.L":
            left[key] = logical
        elif branch == "bay.R":
            right[key] = logical
    shared = set(left) & set(right)
    assert shared
    assert all(left[key] != right[key] for key in shared)

    program = Program(
        graph_id="src:dup",
        namespace="ns",
        scene_id="scene:dup",
        frame=1,
        seed=1,
        units="none",
        unit_scale_to_meters=1.0,
        coordinate_system="unknown",
        groups=(GroupDecl("src:dup", "Dup", None),),
        sources=(SourceDecl("src:mesh", "Mesh", "m"),),
        steps=(
            Distribute("d1", "main", "src:dup", count=3),
            Distribute("d2", "main", "src:dup", count=3),
            InstanceOn("i", "main", "src:dup", sources=("src:mesh",)),
        ),
    )
    duplicated = execute(program)
    assert duplicated.meta.duplicates
    assert duplicated.table.live_count == 3
    assert any("duplicate" in note for note in duplicated.meta.notes)


def test_order_and_index_warning():
    def program(order: str, mode: str = "authored"):
        left = [
            Distribute("dl", "L", "src:g", count=4, sample_key_mode=mode),
            InstanceOn("il", "L", "src:g", sources=("src:a",)),
        ]
        right = [
            Distribute("dr", "R", "src:g", count=4, sample_key_mode=mode),
            InstanceOn("ir", "R", "src:g", sources=("src:b",)),
        ]
        steps = tuple(left + right if order == "lr" else right + left)
        return Program(
            graph_id="src:g",
            namespace="ns",
            scene_id="scene:g",
            frame=1,
            seed=5,
            units="none",
            unit_scale_to_meters=1.0,
            coordinate_system="unknown",
            groups=(GroupDecl("src:g", "G", None),),
            sources=(SourceDecl("src:a", "A", "f"), SourceDecl("src:b", "B", "f")),
            steps=steps,
        )

    forward = execute(program("lr"))
    backward = execute(program("rl"))
    assert set(_ids(forward)) == set(_ids(backward))
    indexed = execute(program("lr", mode="index"))
    assert any(int(indexed.table.flags[row]) & FLAG_INDEX_UNSTABLE for row in range(len(indexed.table)))
    report = query_logical(indexed, indexed.table.logical_hex(0))
    assert report["confidence"] == "PARTIAL"
    assert any("index" in note.lower() for note in report["notes"])
    assert set(_ids(indexed)).isdisjoint(set(_ids(forward)))


def test_nesting_parent_chain():
    trace = execute(habitat_program())
    instance_id = highlighted_id(trace)
    report = query_logical(trace, instance_id)
    assert report["origin_status"] == "EXACT"
    assert report["source_id"] == PANEL_A
    assert report["source_label"] == "Panel_A"
    assert "src:hk.window_scatter" in report["instrumented_path"]
    assert "src:hk.habitat.module" in report["instrumented_path"]
    assert "src:hk.bay" in report["instrumented_path"]
    types = [item["event_type"] for item in report["operations"]]
    assert types[0] == "CREATE"
    assert "INSTANCE" in types
    assert "TRANSFORM" in types
    assert "FILTER" in types
    assert "SOURCE_OBJECT" in types
    assert any(
        item["event_type"] == "SOURCE_OBJECT" and item["instrumented_path"] == PANEL_A
        for item in report["operations"]
    )
    assert any(
        item["event_type"] == "INSTANCE" and str(item["instrumented_path"]).endswith(PANEL_A)
        for item in report["operations"]
    )
    assert report["seed"] == 218
    assert report["sample_key"] == 2
    assert report["branch_id"] == "bay.L"
    assert report["container"]["event_type"] == "MERGE"
    assert len(report["container"]["parent_event_ids"]) >= 2
    # Mullions keep the window id as their logical parent.
    window = instance_id
    children = []
    for row in range(len(trace.table)):
        if window in trace.table.parent_hexes(row):
            children.append(row)
    assert children
    child = query_logical(trace, trace.table.logical_hex(children[0]))
    assert child["parent_logical_ids"] == [window]
    assert "src:hk.mullion_scatter" in child["instrumented_path"]


def test_filter_removes_live_output():
    trace = execute(habitat_program())
    removed = []
    for row in range(len(trace.table)):
        branch = trace.table.decode(trace.table.branches, int(trace.table.branch_code[row]))
        if branch == "bay.L" and int(trace.table.sample_key[row]) % 11 == 0:
            removed.append(row)
            assert not trace.table.alive[row]
    assert removed
    report = query_logical(trace, trace.table.logical_hex(removed[0]))
    assert report["alive"] is False
    assert any(item["event_type"] == "REMOVE" for item in report["operations"])


def test_merge_keeps_multiple_ancestors_and_lossy_join_refuses_exact():
    trace = execute(habitat_program())
    report = query_logical(trace, highlighted_id(trace))
    assert report["exact_parent"] is True
    assert len(report["container"]["parent_event_ids"]) >= 2
    # The identity chain's instance event has the source and the distribute, not the other bay.
    instance = next(item for item in report["operations"] if item["event_type"] == "INSTANCE")
    assert len(instance["parent_event_ids"]) == 2
    program = Program(
        graph_id="src:join",
        namespace="ns",
        scene_id="scene:join",
        frame=1,
        seed=3,
        units="none",
        unit_scale_to_meters=1.0,
        coordinate_system="unknown",
        groups=(GroupDecl("src:join", "Join", None),),
        sources=(SourceDecl("src:a", "A", "f"), SourceDecl("src:b", "B", "f")),
        steps=(
            Distribute("dl", "L", "src:join", count=2),
            InstanceOn("il", "L", "src:join", sources=("src:a",)),
            Distribute("dr", "R", "src:join", count=2),
            InstanceOn("ir", "R", "src:join", sources=("src:b",)),
            LossyJoinStep("join", ("L", "R"), "out"),
        ),
    )
    joined = execute(program)
    report = query_logical(joined, joined.table.logical_hex(0))
    assert report["origin_status"] == "LINEAGE_AMBIGUOUS"
    assert report["exact_parent"] is False
    assert report["confidence"] != "EXACT"
    assert len(report["candidate_ancestors"]) >= 2


def test_realize_and_remesh_are_not_exact():
    plain = execute(habitat_program())
    instance_id = highlighted_id(plain)
    lost = execute(habitat_program(realize=True))
    report = query_logical(lost, instance_id)
    assert report["found"] is True
    assert report["origin_status"] == "LINEAGE_AMBIGUOUS"
    assert report["confidence"] != "EXACT"
    assert report["exact_parent"] is False
    assert any(item["event_type"] == "LINEAGE_AMBIGUOUS" for item in report["operations"])
    program = habitat_program()
    steps = program.steps + (UnsupportedStep("remesh", "bay.L", "REMESH", "REMESH"),)
    remeshed = execute(
        Program(
            graph_id=program.graph_id,
            namespace=program.namespace,
            scene_id=program.scene_id,
            frame=program.frame,
            seed=program.seed,
            units=program.units,
            unit_scale_to_meters=program.unit_scale_to_meters,
            coordinate_system=program.coordinate_system,
            groups=program.groups,
            sources=program.sources,
            steps=steps,
            display_name=program.display_name,
        )
    )
    report = query_logical(remeshed, instance_id)
    assert report["origin_status"] == "UNSUPPORTED_OR_LOST"
    assert report["confidence"] != "EXACT"


def test_temporal_and_revision():
    frame_a = execute(habitat_program(frame=1))
    frame_b = execute(habitat_program(frame=8))
    assert _ids(frame_a) == _ids(frame_b)
    assert frame_a.meta.source_revision == frame_b.meta.source_revision
    diff = diff_traces(frame_a, frame_b)
    assert "FRAME_COORDINATE_CHANGED" in diff["labels"]
    assert "ALL_PERSISTED" in diff["labels"]
    assert diff["counts"]["persisted"] == len(frame_a.index)

    labelled = habitat_program()
    renamed = Program(
        graph_id=labelled.graph_id,
        namespace=labelled.namespace,
        scene_id=labelled.scene_id,
        frame=labelled.frame,
        seed=labelled.seed,
        units=labelled.units,
        unit_scale_to_meters=labelled.unit_scale_to_meters,
        coordinate_system=labelled.coordinate_system,
        groups=tuple(
            GroupDecl(group.group_id, group.display_name + " renamed", group.parent_group_id)
            for group in labelled.groups
        ),
        sources=labelled.sources,
        steps=labelled.steps,
        display_name="Renamed label",
    )
    assert execute(renamed).meta.source_revision == frame_a.meta.source_revision

    shifted = execute(habitat_program(right_seed=219))
    diff = diff_traces(frame_a, shifted)
    assert "SEED_CHANGED" in diff["labels"]
    assert "REVISION_DIVERGED" in diff["labels"]
    assert "PERSISTED_UNDER_REVISION_CHANGE" in diff["labels"]
    assert diff["counts"]["persisted"] > 0
    assert diff["counts"]["changed_same_slot"] > 0
    report = query_logical(frame_a, highlighted_id(frame_a), scene_revision=shifted.meta.source_revision)
    assert report["revision_status"] == "INCOMPATIBLE"
    assert report["origin_status"] == "PARTIAL_TRACE"


def test_depth_limit():
    steps = [Distribute("d", "main", "src:g", count=1), InstanceOn("i", "main", "src:g", sources=("src:a",))]
    steps.extend(TransformStep(f"t{index}", "main", translation=(index, 0.0, 0.0)) for index in range(10))
    program = Program(
        graph_id="src:g",
        namespace="ns",
        scene_id="scene:g",
        frame=1,
        seed=1,
        units="none",
        unit_scale_to_meters=1.0,
        coordinate_system="unknown",
        groups=(GroupDecl("src:g", "G", None),),
        sources=(SourceDecl("src:a", "A", "f"),),
        steps=tuple(steps),
    )
    trace = execute(program)
    report = query_logical(trace, trace.table.logical_hex(0), max_depth=2)
    assert any(item.get("loss_reason") == "DEPTH_LIMIT" for item in report["loss_points"])
    assert report["origin_status"] != "EXACT"
