"""Supported subgraph vocabulary for v0.1.

This is a declarative program, not a Geometry Nodes interpreter. Display names
are labels. Identity uses ``group_id`` and ``source_id`` only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from instancetrace.schema.canonical import decimal_string


@dataclass(frozen=True)
class GroupDecl:
    group_id: str
    display_name: str
    parent_group_id: str | None = None

    def fingerprint(self) -> dict[str, Any]:
        return {"id": self.group_id, "parent": self.parent_group_id}


@dataclass(frozen=True)
class SourceDecl:
    source_id: str
    display_name: str
    family: str

    def fingerprint(self) -> dict[str, str]:
        return {"id": self.source_id, "family": self.family}


@dataclass(frozen=True)
class Distribute:
    step_id: str
    branch_id: str
    group_id: str
    sample_key_mode: str = "authored"
    count: int | None = None
    align_to_branch: str | None = None
    seed: int | None = None

    def fingerprint(self) -> dict[str, Any]:
        return {
            "op": "distribute",
            "id": self.step_id,
            "branch": self.branch_id,
            "group": self.group_id,
            "mode": self.sample_key_mode,
            "count": self.count,
            "align": self.align_to_branch,
            "seed": self.seed,
        }


@dataclass(frozen=True)
class InstanceOn:
    step_id: str
    branch_id: str
    group_id: str
    sources: tuple[str, ...]

    def fingerprint(self) -> dict[str, Any]:
        return {
            "op": "instance",
            "id": self.step_id,
            "branch": self.branch_id,
            "group": self.group_id,
            "sources": list(self.sources),
        }


@dataclass(frozen=True)
class TransformStep:
    step_id: str
    branch_id: str
    translation: tuple[float, float, float] = (0.0, 0.0, 0.0)
    per_sample_offset: tuple[float, float, float] = (0.0, 0.0, 0.0)
    scale: float = 1.0
    compose_parent: bool = False

    def fingerprint(self) -> dict[str, Any]:
        return {
            "op": "transform",
            "id": self.step_id,
            "branch": self.branch_id,
            "translation": [decimal_string(v) for v in self.translation],
            "per_sample_offset": [decimal_string(v) for v in self.per_sample_offset],
            "scale": decimal_string(self.scale),
            "compose_parent": self.compose_parent,
        }


@dataclass(frozen=True)
class FilterStep:
    step_id: str
    branch_id: str
    predicate: str

    def fingerprint(self) -> dict[str, Any]:
        return {
            "op": "filter",
            "id": self.step_id,
            "branch": self.branch_id,
            "predicate": self.predicate,
        }


@dataclass(frozen=True)
class MergeStep:
    step_id: str
    branch_ids: tuple[str, ...]
    output_branch: str
    preserves_identity: bool = True

    def fingerprint(self) -> dict[str, Any]:
        return {
            "op": "merge",
            "id": self.step_id,
            "branches": list(self.branch_ids),
            "output": self.output_branch,
            "preserves_identity": self.preserves_identity,
        }


@dataclass(frozen=True)
class RealizeStep:
    step_id: str
    branch_id: str
    ids_survive: bool = False

    def fingerprint(self) -> dict[str, Any]:
        return {
            "op": "realize",
            "id": self.step_id,
            "branch": self.branch_id,
            "ids_survive": self.ids_survive,
        }


@dataclass(frozen=True)
class LossyJoinStep:
    step_id: str
    branch_ids: tuple[str, ...]
    output_branch: str
    loss_reason: str = "JOIN_GEOMETRY"

    def fingerprint(self) -> dict[str, Any]:
        return {
            "op": "lossy_join",
            "id": self.step_id,
            "branches": list(self.branch_ids),
            "output": self.output_branch,
            "loss_reason": self.loss_reason,
        }


@dataclass(frozen=True)
class UnsupportedStep:
    step_id: str
    branch_id: str
    operation: str
    loss_reason: str

    def fingerprint(self) -> dict[str, Any]:
        return {
            "op": "unsupported",
            "id": self.step_id,
            "branch": self.branch_id,
            "operation": self.operation,
            "loss_reason": self.loss_reason,
        }


Step = (
    Distribute
    | InstanceOn
    | TransformStep
    | FilterStep
    | MergeStep
    | RealizeStep
    | LossyJoinStep
    | UnsupportedStep
)


@dataclass(frozen=True)
class Program:
    graph_id: str
    namespace: str
    scene_id: str
    frame: int
    seed: int
    units: str
    unit_scale_to_meters: float
    coordinate_system: str
    groups: tuple[GroupDecl, ...]
    sources: tuple[SourceDecl, ...]
    steps: tuple[Step, ...]
    epoch: int | None = 0
    display_name: str = ""

    def declaration(self) -> dict[str, Any]:
        """Revision payload. Display labels are excluded on purpose."""
        return {
            "graph_id": self.graph_id,
            "namespace": self.namespace,
            "seed": self.seed,
            "units": self.units,
            "unit_scale_to_meters": decimal_string(self.unit_scale_to_meters),
            "coordinate_system": self.coordinate_system,
            "groups": [group.fingerprint() for group in self.groups],
            "sources": [source.fingerprint() for source in self.sources],
            "steps": [step.fingerprint() for step in self.steps],
        }

    def labels(self) -> dict[str, str]:
        found = {}
        if self.display_name:
            found[self.graph_id] = self.display_name
        for group in self.groups:
            found[group.group_id] = group.display_name
        for source in self.sources:
            found[source.source_id] = source.display_name
        return found
