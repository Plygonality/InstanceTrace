"""Turn a depsgraph dump into a PASSIVE_ONLY trace.

Object names and matrices are kept. No logical id, seed, branch, or node path
is created from them.
"""

from __future__ import annotations

import platform
import sys

from instancetrace import __version__
from instancetrace.capture.locators import evaluated_locator
from instancetrace.schema.canonical import decimal_string
from instancetrace.schema.enums import CONFIDENCE_LEVELS, SAMPLE_MODES, CaptureMode, Confidence
from instancetrace.schema.models import HostInfo, TraceMeta
from instancetrace.storage.manifest import LoadedTrace
from instancetrace.storage.table import build_index, table_from_rows

_IDENTITY = (1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0)


def import_passive_dump(dump: dict) -> LoadedTrace:
    if dump.get("format") != "instancetrace.blender_capture":
        raise ValueError("not an instancetrace blender capture dump")
    if dump.get("capture_mode") not in {None, "PASSIVE_ONLY"}:
        raise ValueError("passive import refuses an instrumented dump; use import_instrumented_dump")
    scene_id = str(dump.get("scene_id") or "scene:unknown")
    frame = int(dump.get("frame") or 0)
    rows = []
    for instance in dump.get("instances", []):
        locator = evaluated_locator(
            scene_id=scene_id,
            frame=frame,
            parent_name=str(instance.get("parent_name") or ""),
            object_name=str(instance.get("object_name") or ""),
            persistent_id=instance.get("persistent_id") or (0,) * 8,
            evaluated_index=int(instance.get("evaluated_index") or 0),
            random_id=instance.get("random_id"),
        )
        matrix = instance.get("matrix_world") or _IDENTITY
        rows.append(
            {
                "logical_id": None,
                "sample_key": 0,
                "sample_mode": "authored",
                "branch_id": None,
                "source_id": None,
                "path": str(instance.get("object_name") or ""),
                "event_code": None,
                "container_event_code": None,
                "alive": True,
                "confidence": Confidence.PASSIVE_ONLY.value,
                "loss_reason": "NOT_INSTRUMENTED",
                "seed": 0,
                "transform": tuple(float(value) for value in matrix),
                "flags": 0,
                "parent_ids": (),
                "candidate_event_codes": [],
                "locator": locator,
            }
        )
    table = table_from_rows(rows, confidences=list(CONFIDENCE_LEVELS), sample_modes=list(SAMPLE_MODES))
    meta = TraceMeta(
        capture_mode=CaptureMode.PASSIVE_ONLY.value,
        graph_id="",
        source_revision="",
        scene_id=scene_id,
        frame=frame,
        epoch=dump.get("epoch"),
        seed=None,
        units=str(dump.get("units") or "blender_units"),
        unit_scale_to_meters=decimal_string(float(dump.get("unit_scale_to_meters") or 1.0)),
        coordinate_system=str(dump.get("coordinate_system") or "right_handed_z_up"),
        host=HostInfo(
            application="Blender",
            version=str(dump.get("blender_version") or "unknown"),
            python_version=".".join(str(part) for part in sys.version_info[:3]),
            platform=platform.platform(),
        ),
        notes=[
            "PASSIVE_ONLY capture. persistent_id and random_id are host runtime fields, not logical ids.",
            f"importer={__version__}",
        ],
    )
    loaded = LoadedTrace(meta=meta, events=[], table=table)
    loaded.index = build_index(table)
    loaded.meta.instance_count = len(table)
    loaded.meta.live_count = table.live_count
    return loaded
