"""Acyclic event graphs with a hard depth bound."""

from __future__ import annotations

from collections import defaultdict
from typing import TypeVar

T = TypeVar("T")


def _parents_of(event: object) -> list[str]:
    return list(event.parent_event_ids)  # type: ignore[attr-defined]


def _id_of(event: object) -> str:
    return str(event.event_id)  # type: ignore[attr-defined]


def cycle_nodes(events: list[object]) -> list[str]:
    """Return one cyclic node id list, or an empty list when the graph is a DAG."""
    by_id = {_id_of(event): event for event in events}
    color: dict[str, int] = {}
    stack: list[str] = []

    def visit(node: str) -> list[str] | None:
        color[node] = 1
        stack.append(node)
        for parent in _parents_of(by_id[node]):
            if parent not in by_id:
                continue
            state = color.get(parent, 0)
            if state == 1:
                start = stack.index(parent)
                return stack[start:] + [parent]
            if state == 0:
                found = visit(parent)
                if found:
                    return found
        stack.pop()
        color[node] = 2
        return None

    for node in by_id:
        if color.get(node, 0) == 0:
            found = visit(node)
            if found:
                return found
    return []


def ancestors(events: list[object], start: str, *, max_depth: int = 64) -> tuple[list[object], list[str]]:
    """Walk parent links root-ward.

    Returns the visited events in child-to-parent order and a list of loss
    tokens (``DEPTH_LIMIT`` or ``CYCLE_DETECTED``).
    """
    by_id = {_id_of(event): event for event in events}
    if start not in by_id:
        return [], []
    visited: list[object] = []
    visiting: set[str] = set()
    done: set[str] = set()
    losses: list[str] = []

    def walk(node: str, depth: int) -> None:
        if node in visiting:
            losses.append("CYCLE_DETECTED")
            return
        if node in done:
            return
        if depth > max_depth:
            losses.append("DEPTH_LIMIT")
            return
        event = by_id.get(node)
        if event is None:
            return
        visiting.add(node)
        visited.append(event)
        for parent in _parents_of(event):
            walk(parent, depth + 1)
        visiting.remove(node)
        done.add(node)

    walk(start, 0)
    return visited, losses


def causal_order(events: list[object], start: str, *, max_depth: int = 64) -> tuple[list[object], list[str]]:
    """Parents before children for the ancestor cone of ``start``."""
    by_id = {_id_of(event): event for event in events}
    if start not in by_id:
        return [], []
    order: list[object] = []
    visiting: set[str] = set()
    done: set[str] = set()
    losses: list[str] = []

    def visit(node: str, depth: int) -> None:
        if node in done:
            return
        if node in visiting:
            losses.append("CYCLE_DETECTED")
            return
        if depth > max_depth:
            losses.append("DEPTH_LIMIT")
            return
        event = by_id.get(node)
        if event is None:
            return
        visiting.add(node)
        for parent in _parents_of(event):
            visit(parent, depth + 1)
        visiting.remove(node)
        done.add(node)
        order.append(event)

    visit(start, 0)
    return order, losses


def children_index(events: list[object]) -> dict[str, list[str]]:
    index: dict[str, list[str]] = defaultdict(list)
    for event in events:
        for parent in _parents_of(event):
            index[parent].append(_id_of(event))
    return index
