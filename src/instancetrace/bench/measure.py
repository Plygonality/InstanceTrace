"""Measure instrumentation cost on this process. Results are not universal."""

from __future__ import annotations

import platform
import time
import tracemalloc
from typing import Any

import numpy as np

from instancetrace import __version__
from instancetrace.demo.habitat import habitat_program
from instancetrace.instrument.execute import execute
from instancetrace.instrument.grammar import (
    Distribute,
    GroupDecl,
    InstanceOn,
    Program,
    SourceDecl,
)
from instancetrace.query.engine import query_logical
from instancetrace.storage.manifest import save_trace


def _program(count: int) -> Program:
    return Program(
        graph_id="src:bench.scatter",
        namespace="plygonality.instancetrace.bench",
        scene_id="scene:bench",
        frame=1,
        seed=218,
        units="none",
        unit_scale_to_meters=1.0,
        coordinate_system="right_handed_z_up",
        groups=(GroupDecl("src:bench.scatter", "Bench", None),),
        sources=(SourceDecl("src:bench.source", "Source", "bench"),),
        steps=(
            Distribute("dist", "main", "src:bench.scatter", count=count, sample_key_mode="authored"),
            InstanceOn("inst", "main", "src:bench.scatter", sources=("src:bench.source",)),
        ),
        display_name="Bench",
    )


def _baseline(count: int) -> np.ndarray:
    return np.zeros((count, 16), dtype=np.float64)


def measure_count(count: int, *, out_dir: str | None = None) -> dict[str, Any]:
    tracemalloc.start()
    started = time.perf_counter()
    _baseline(count)
    baseline_seconds = time.perf_counter() - started
    _, baseline_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    tracemalloc.start()
    started = time.perf_counter()
    trace = execute(_program(count))
    instrument_seconds = time.perf_counter() - started
    _, instrument_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    query_seconds = None
    manifest_bytes = None
    if len(trace.table):
        instance_id = trace.table.logical_hex(0)
        started = time.perf_counter()
        query_logical(trace, instance_id)
        query_seconds = time.perf_counter() - started
    if out_dir is not None:
        from pathlib import Path

        path = save_trace(trace, Path(out_dir) / f"n{count}.json")
        manifest_bytes = path.stat().st_size + path.with_suffix(".npz").stat().st_size
    return {
        "count": count,
        "baseline_seconds": baseline_seconds,
        "instrument_seconds": instrument_seconds,
        "query_seconds": query_seconds,
        "baseline_tracemalloc_peak_bytes": baseline_peak,
        "instrument_tracemalloc_peak_bytes": instrument_peak,
        "manifest_bytes": manifest_bytes,
        "live_count": trace.table.live_count,
    }


def measure(counts: list[int], *, out_dir: str | None = None) -> dict[str, Any]:
    habitat = habitat_program()
    return {
        "instancetrace": __version__,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "processor": platform.processor(),
        "note": (
            "Times are wall time in this process. Peak bytes are tracemalloc peaks, "
            "not resident set size. Baseline allocates transforms only. "
            "Untested counts are omitted."
        ),
        "habitat_step_count": len(habitat.steps),
        "runs": [measure_count(count, out_dir=out_dir) for count in counts],
    }
