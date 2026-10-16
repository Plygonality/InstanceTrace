"""Evaluated locators. These are capture coordinates, not logical ids."""

from __future__ import annotations


def evaluated_locator(
    *,
    scene_id: str,
    frame: int,
    parent_name: str,
    object_name: str,
    persistent_id: list[int] | tuple[int, ...],
    evaluated_index: int,
    random_id: int | None = None,
) -> str:
    persistent = ",".join(str(int(value)) for value in persistent_id)
    locator = (
        f"eval:{scene_id}:f{int(frame)}:{parent_name}:{object_name}:pid{persistent}:i{int(evaluated_index)}"
    )
    if random_id is not None:
        locator += f":rnd{int(random_id)}"
    return locator


def locator_object_name(locator: str) -> str | None:
    """Return the evaluated object name stored in a locator.

    Scene ids may contain colons. The object name is the field immediately
    before ``:pid``.
    """
    if ":pid" not in locator:
        return None
    head, _rest = locator.split(":pid", 1)
    name = head.rsplit(":", 1)[-1]
    return name or None
