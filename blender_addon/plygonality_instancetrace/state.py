"""In-memory session for the Blender panel. Not a scene file."""

from __future__ import annotations

from typing import Any


class Session:
    def __init__(self) -> None:
        self.trace: Any = None
        self.report: dict[str, Any] | None = None
        self.boxes: list[dict[str, Any]] = []
        self.pick_bounds_available: bool = False

    def clear(self) -> None:
        self.trace = None
        self.report = None
        self.boxes = []
        self.pick_bounds_available = False


SESSION = Session()
