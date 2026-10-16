"""Self-contained habitat facade program and the offline demo writer.

Meshes are described as source ids. The offline demo does not embed geometry
files. The Blender fixture builds the same ids onto primitive meshes.
"""

from __future__ import annotations

import json
from pathlib import Path

from instancetrace.instrument.execute import execute
from instancetrace.instrument.grammar import (
    Distribute,
    FilterStep,
    GroupDecl,
    InstanceOn,
    MergeStep,
    Program,
    RealizeStep,
    SourceDecl,
    TransformStep,
)
from instancetrace.query.diff import diff_traces
from instancetrace.query.engine import query_logical
from instancetrace.storage.manifest import LoadedTrace, save_trace
from instancetrace.visualization.dot import format_dot
from instancetrace.visualization.html import format_html
from instancetrace.visualization.text import format_report

NAMESPACE = "plygonality.instancetrace.hk.habitat"
GRAPH_ID = "src:hk.habitat.module"
SCENE_ID = "scene:hk.habitat.demo"
PANEL_A = "src:hk.panel_a"
PANEL_B = "src:hk.panel_b"
MULLION = "src:hk.mullion"


def habitat_program(
    *,
    frame: int = 1,
    seed: int = 218,
    right_seed: int | None = None,
    panel_a: str = PANEL_A,
    predicate: str = "sample_key % 11 == 0",
    count: int = 12,
    realize: bool = False,
) -> Program:
    """Two bays, a nested window scatter, and mullions parented to surviving windows."""
    groups = (
        GroupDecl(GRAPH_ID, "HK Habitat Module", None),
        GroupDecl("src:hk.bay", "BayModule", GRAPH_ID),
        GroupDecl("src:hk.window_scatter", "WindowScatter", "src:hk.bay"),
        GroupDecl("src:hk.mullion_scatter", "MullionScatter", "src:hk.bay"),
    )
    sources = (
        SourceDecl(panel_a, "Panel_A", "panels"),
        SourceDecl(PANEL_B, "Panel_B", "panels"),
        SourceDecl(MULLION, "Mullion", "mullions"),
    )
    steps: list = []
    for branch, base_x, branch_seed in (
        ("bay.L", -4.0, seed),
        ("bay.R", 4.0, seed if right_seed is None else right_seed),
    ):
        steps.extend(
            [
                Distribute(
                    step_id=f"dist-{branch}",
                    branch_id=branch,
                    group_id="src:hk.window_scatter",
                    sample_key_mode="authored",
                    count=count,
                    seed=branch_seed,
                ),
                InstanceOn(
                    step_id=f"inst-{branch}",
                    branch_id=branch,
                    group_id="src:hk.window_scatter",
                    sources=(panel_a, PANEL_B),
                ),
                TransformStep(
                    step_id=f"xf-{branch}",
                    branch_id=branch,
                    translation=(base_x, 0.0, 1.5),
                    per_sample_offset=(0.8, 0.0, 0.0),
                ),
                FilterStep(step_id=f"filter-{branch}", branch_id=branch, predicate=predicate),
                Distribute(
                    step_id=f"dist-mullion-{branch}",
                    branch_id=f"mullion.{branch}",
                    group_id="src:hk.mullion_scatter",
                    align_to_branch=branch,
                    seed=branch_seed,
                ),
                InstanceOn(
                    step_id=f"inst-mullion-{branch}",
                    branch_id=f"mullion.{branch}",
                    group_id="src:hk.mullion_scatter",
                    sources=(MULLION,),
                ),
                TransformStep(
                    step_id=f"xf-mullion-{branch}",
                    branch_id=f"mullion.{branch}",
                    translation=(0.0, 0.05, -0.2),
                    compose_parent=True,
                ),
            ]
        )
    steps.append(
        MergeStep(
            step_id="merge-windows",
            branch_ids=("bay.L", "bay.R"),
            output_branch="facade.windows",
            preserves_identity=True,
        )
    )
    steps.append(
        MergeStep(
            step_id="merge-mullions",
            branch_ids=("mullion.bay.L", "mullion.bay.R"),
            output_branch="facade.mullions",
            preserves_identity=True,
        )
    )
    if realize:
        for branch in ("bay.L", "bay.R", "mullion.bay.L", "mullion.bay.R"):
            steps.append(RealizeStep(step_id=f"realize-{branch}", branch_id=branch, ids_survive=False))
    return Program(
        graph_id=GRAPH_ID,
        namespace=NAMESPACE,
        scene_id=SCENE_ID,
        frame=frame,
        seed=seed,
        units="meters",
        unit_scale_to_meters=1.0,
        coordinate_system="right_handed_z_up",
        groups=groups,
        sources=sources,
        steps=tuple(steps),
        epoch=0,
        display_name="HK Habitat Module",
    )


def highlighted_row(trace: LoadedTrace) -> int:
    """First live bay.L Panel_A window, the lowest authored sample key."""
    table = trace.table
    chosen = None
    for row in range(len(table)):
        if not table.alive[row]:
            continue
        branch = table.decode(table.branches, int(table.branch_code[row]))
        source = table.decode(table.sources, int(table.source_code[row]))
        if branch == "bay.L" and source == PANEL_A:
            if chosen is None or int(table.sample_key[row]) < int(table.sample_key[chosen]):
                chosen = row
    if chosen is None:
        raise RuntimeError("habitat program produced no live Panel_A instance")
    return chosen


def highlighted_id(trace: LoadedTrace) -> str:
    return trace.table.logical_hex(highlighted_row(trace))


def build_demo(out: str | Path) -> str:
    """Write the reference demo and return the highlighted logical id."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    program = habitat_program()
    trace = execute(program)
    save_trace(trace, out / "trace.json")
    instance_id = highlighted_id(trace)
    report = query_logical(trace, instance_id)
    (out / "lineage.txt").write_text(format_report(report), encoding="utf-8")
    (out / "lineage.dot").write_text(format_dot(report), encoding="utf-8")

    run_a = out / "runA"
    run_b = out / "runB"
    run_a.mkdir(exist_ok=True)
    run_b.mkdir(exist_ok=True)
    save_trace(trace, run_a / "trace.json")
    other = execute(habitat_program(right_seed=219))
    save_trace(other, run_b / "trace.json")
    diff = diff_traces(trace, other)
    (out / "continuity.json").write_text(json.dumps(diff, indent=2) + "\n", encoding="utf-8")
    (out / "lineage.html").write_text(format_html(report, diff=diff), encoding="utf-8")

    loss_dir = out / "loss"
    loss_dir.mkdir(exist_ok=True)
    loss = execute(habitat_program(realize=True))
    save_trace(loss, loss_dir / "trace.json")
    loss_report = query_logical(loss, instance_id)
    (loss_dir / "lineage.txt").write_text(format_report(loss_report), encoding="utf-8")

    (out / "INSTANCE_ID.txt").write_text(instance_id + "\n", encoding="utf-8")
    (out / "program.json").write_text(
        json.dumps(program.declaration(), indent=2) + "\n",
        encoding="utf-8",
    )
    return instance_id
