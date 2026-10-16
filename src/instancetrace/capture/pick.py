"""Axis-aligned bounds test for the viewport pick prototype.

A ray that enters more than one box before leaving the nearest box is
``AMBIGUOUS_PICK``. A miss is ``MISS``. ``PICK_UNSUPPORTED`` is reserved for
a host that cannot supply a ray or instance bounds; this module does not
invent a selected instance in that case.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any


def _interval(
    origin: Sequence[float],
    direction: Sequence[float],
    bmin: Sequence[float],
    bmax: Sequence[float],
) -> tuple[float, float] | None:
    enter = 0.0
    leave = float("inf")
    for axis in range(3):
        start = float(origin[axis])
        delta = float(direction[axis])
        low = float(bmin[axis])
        high = float(bmax[axis])
        if abs(delta) < 1e-12:
            if start < low or start > high:
                return None
            continue
        inv = 1.0 / delta
        t1 = (low - start) * inv
        t2 = (high - start) * inv
        if t1 > t2:
            t1, t2 = t2, t1
        enter = max(enter, t1)
        leave = min(leave, t2)
        if enter > leave:
            return None
    if leave < 0.0:
        return None
    return enter, leave


def pick_ray(
    origin: Sequence[float],
    direction: Sequence[float],
    boxes: Sequence[dict[str, Any]],
    *,
    tie_epsilon: float = 1e-5,
) -> dict[str, Any]:
    """Classify a ray against instance bounds.

    Each box has ``instance_id``, ``min``, and ``max``.
    """
    hits: list[tuple[float, float, str]] = []
    for box in boxes:
        interval = _interval(origin, direction, box["min"], box["max"])
        if interval is None:
            continue
        hits.append((interval[0], interval[1], str(box["instance_id"])))
    if not hits:
        return {"status": "MISS", "instance_ids": [], "loss_reason": None}
    hits.sort(key=lambda item: item[0])
    _nearest_enter, nearest_leave, nearest_id = hits[0]
    overlapping = [nearest_id]
    for enter, _leave, instance_id in hits[1:]:
        if enter <= nearest_leave + tie_epsilon and instance_id not in overlapping:
            overlapping.append(instance_id)
    if len(overlapping) > 1:
        return {
            "status": "AMBIGUOUS_PICK",
            "instance_ids": overlapping,
            "loss_reason": "AMBIGUOUS_PICK",
        }
    return {"status": "EXACT", "instance_ids": overlapping, "loss_reason": None}


def boxes_from_trace(trace: Any, *, half_extent: float = 0.25) -> list[dict[str, Any]]:
    """Build pick bounds from captured row matrices.

    Translation is read from the row-major matrix at elements 3, 7, and 11.
    Rows without a logical id use the evaluated locator as the pick token.
    """
    table = trace.table
    boxes = []
    for row in range(len(table)):
        if not table.alive[row]:
            continue
        if table.has_logical_id(row):
            instance_id = table.logical_hex(row)
        else:
            instance_id = table.locator(row)
        if not instance_id:
            continue
        matrix = table.transform[row]
        center = (float(matrix[3]), float(matrix[7]), float(matrix[11]))
        boxes.append(
            {
                "instance_id": instance_id,
                "min": tuple(value - half_extent for value in center),
                "max": tuple(value + half_extent for value in center),
            }
        )
    return boxes
