"""Viewport pick classification and locator parsing."""

from __future__ import annotations

from instancetrace.capture.locators import evaluated_locator, locator_object_name
from instancetrace.capture.pick import boxes_from_trace, pick_ray
from instancetrace.demo.habitat import habitat_program
from instancetrace.instrument.execute import execute


def test_pick_exact_ambiguous_and_miss():
    boxes = [
        {"instance_id": "near", "min": (0, 0, 0), "max": (1, 1, 1)},
        {"instance_id": "far", "min": (4, 0, 0), "max": (5, 1, 1)},
        {"instance_id": "overlap", "min": (0.2, 0, 0), "max": (1.2, 1, 1)},
    ]
    exact = pick_ray((0.5, 0.5, -2), (0, 0, 1), [boxes[0], boxes[1]])
    assert exact["status"] == "EXACT"
    assert exact["instance_ids"] == ["near"]
    ambiguous = pick_ray((0.5, 0.5, -2), (0, 0, 1), boxes)
    assert ambiguous["status"] == "AMBIGUOUS_PICK"
    assert ambiguous["loss_reason"] == "AMBIGUOUS_PICK"
    assert set(ambiguous["instance_ids"]) == {"near", "overlap"}
    miss = pick_ray((9, 9, 9), (0, 0, 1), boxes)
    assert miss["status"] == "MISS"


def test_locator_object_name_keeps_scene_colons():
    locator = evaluated_locator(
        scene_id="scene:hk.habitat.demo",
        frame=1,
        parent_name="IT_Scatter",
        object_name="IT_Panel_A",
        persistent_id=(21, 2147483647),
        evaluated_index=30,
        random_id=7,
    )
    assert locator_object_name(locator) == "IT_Panel_A"


def test_boxes_follow_matrix_translation():
    trace = execute(habitat_program(count=2))
    boxes = boxes_from_trace(trace, half_extent=0.1)
    assert boxes
    assert all(item["instance_id"].startswith("0x") for item in boxes)
    width = boxes[0]["max"][0] - boxes[0]["min"][0]
    assert abs(width - 0.2) < 1e-9
