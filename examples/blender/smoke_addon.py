"""Register the panel and capture the startup scene.

Run with Blender's Python:

    blender --background --python examples/blender/smoke_addon.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "blender_addon"))

import plygonality_instancetrace as addon  # noqa: E402
from plygonality_instancetrace import session_ops  # noqa: E402


def main() -> None:
    before = {obj.name: obj.data.name if obj.data is not None else None for obj in bpy.data.objects}
    filepath = bpy.data.filepath
    addon.register()
    assert hasattr(bpy.types.Scene, "instancetrace")
    capture = session_ops.capture_scene(bpy.context)
    query = session_ops.query_instance(bpy.context)
    pick = session_ops.pick_instance(bpy.context, None, None)
    after = {obj.name: obj.data.name if obj.data is not None else None for obj in bpy.data.objects}
    report = {
        "capture_mode": capture["capture_mode"],
        "saved_blend": capture["saved_blend"],
        "filepath_unchanged": bpy.data.filepath == filepath,
        "objects_unchanged": before == after,
        "query_origin": query.get("origin_status"),
        "pick_status": pick["status"],
        "panel": "INSTANCETRACE_PT_panel" in dir(bpy.types),
    }
    addon.unregister()
    print("ADDON_SMOKE")
    print(json.dumps(report))
    if capture["capture_mode"] != "PASSIVE_ONLY":
        raise SystemExit("startup scene was treated as instrumented")
    if not report["objects_unchanged"] or not report["filepath_unchanged"]:
        raise SystemExit("capture changed the startup scene")
    if pick["status"] != "PICK_UNSUPPORTED":
        raise SystemExit("pick without a view returned a selection")
    if query.get("origin_status") not in {"UNKNOWN_ORIGIN", "MALFORMED_ID", "NOT_IN_MANIFEST"}:
        raise SystemExit("empty query invented an origin")


if __name__ == "__main__":
    main()
