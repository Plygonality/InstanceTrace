"""JSON-serialisable trace metadata. Instance rows live in the NPZ table."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from instancetrace import CONTINUITY_POLICY, GRAMMAR_VERSION, TRACE_SCHEMA_VERSION
from instancetrace.schema.enums import CONFIDENCE_LEVELS, SAMPLE_MODES


def _require_str(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    return value


@dataclass
class HostInfo:
    application: str
    version: str
    python_version: str
    platform: str

    def to_dict(self) -> dict[str, str]:
        return {
            "application": self.application,
            "version": self.version,
            "python_version": self.python_version,
            "platform": self.platform,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HostInfo:
        python_version = data.get("python_version", data.get("python", ""))
        return cls(
            application=_require_str(data.get("application", ""), "host.application"),
            version=_require_str(data.get("version", ""), "host.version"),
            python_version=_require_str(python_version, "host.python_version"),
            platform=_require_str(data.get("platform", ""), "host.platform"),
        )


@dataclass
class Event:
    event_id: str
    event_type: str
    instrumented_path: str
    parent_event_ids: list[str]
    seed: int | None
    notes: str
    confidence: str
    loss_reason: str | None
    candidate_ancestor_ids: list[str]
    config: dict[str, Any]
    display_path: str | None = None
    ordinal: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "instrumented_path": self.instrumented_path,
            "display_path": self.display_path,
            "parent_event_ids": list(self.parent_event_ids),
            "seed": self.seed,
            "notes": self.notes,
            "confidence": self.confidence,
            "loss_reason": self.loss_reason,
            "candidate_ancestor_ids": list(self.candidate_ancestor_ids),
            "config": self.config,
            "ordinal": self.ordinal,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Event:
        return cls(
            event_id=data["event_id"],
            event_type=data["event_type"],
            instrumented_path=data.get("instrumented_path", ""),
            parent_event_ids=list(data.get("parent_event_ids", [])),
            seed=data.get("seed"),
            notes=data.get("notes", ""),
            confidence=data.get("confidence", "UNKNOWN"),
            loss_reason=data.get("loss_reason"),
            candidate_ancestor_ids=list(data.get("candidate_ancestor_ids", [])),
            config=dict(data.get("config", {})),
            display_path=data.get("display_path"),
            ordinal=int(data.get("ordinal", 0)),
        )


@dataclass
class TraceMeta:
    """Header fields. ``unit_scale_to_meters`` is a decimal string."""

    capture_mode: str
    graph_id: str
    source_revision: str
    scene_id: str
    frame: int
    epoch: int | None
    seed: int | None
    units: str
    unit_scale_to_meters: str
    coordinate_system: str
    host: HostInfo
    labels: dict[str, str] = field(default_factory=dict)
    branches: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    paths: list[str] = field(default_factory=list)
    loss_reasons: list[str] = field(default_factory=list)
    collisions: list[dict[str, Any]] = field(default_factory=list)
    duplicates: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    privacy: dict[str, Any] = field(
        default_factory=lambda: {"redacted": False, "policy": "local-only", "telemetry": False}
    )
    instance_count: int = 0
    live_count: int = 0
    trace_schema_version: str = TRACE_SCHEMA_VERSION
    grammar: str = GRAMMAR_VERSION
    continuity_policy: str = CONTINUITY_POLICY
    confidences: list[str] = field(default_factory=lambda: list(CONFIDENCE_LEVELS))
    sample_modes: list[str] = field(default_factory=lambda: list(SAMPLE_MODES))

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_schema_version": self.trace_schema_version,
            "capture_mode": self.capture_mode,
            "graph_id": self.graph_id,
            "source_revision": self.source_revision,
            "scene_id": self.scene_id,
            "frame": self.frame,
            "epoch": self.epoch,
            "seed": self.seed,
            "units": self.units,
            "unit_scale_to_meters": self.unit_scale_to_meters,
            "coordinate_system": self.coordinate_system,
            "grammar": self.grammar,
            "continuity_policy": self.continuity_policy,
            "host": self.host.to_dict(),
            "labels": dict(self.labels),
            "tables": {
                "branches": list(self.branches),
                "sources": list(self.sources),
                "paths": list(self.paths),
                "loss_reasons": list(self.loss_reasons),
                "confidences": list(self.confidences),
                "sample_modes": list(self.sample_modes),
            },
            "collisions": self.collisions,
            "duplicates": self.duplicates,
            "notes": list(self.notes),
            "privacy": dict(self.privacy),
            "instance_count": self.instance_count,
            "live_count": self.live_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TraceMeta:
        tables = data.get("tables", {})
        return cls(
            capture_mode=data["capture_mode"],
            graph_id=data.get("graph_id", ""),
            source_revision=data.get("source_revision", ""),
            scene_id=data.get("scene_id", ""),
            frame=int(data.get("frame", 0)),
            epoch=data.get("epoch"),
            seed=data.get("seed"),
            units=data.get("units", "none"),
            unit_scale_to_meters=str(data.get("unit_scale_to_meters", "1.0")),
            coordinate_system=data.get("coordinate_system", "unknown"),
            host=HostInfo.from_dict(data.get("host", {})),
            labels=dict(data.get("labels", {})),
            branches=list(tables.get("branches", [])),
            sources=list(tables.get("sources", [])),
            paths=list(tables.get("paths", [])),
            loss_reasons=list(tables.get("loss_reasons", [])),
            collisions=list(data.get("collisions", [])),
            duplicates=list(data.get("duplicates", [])),
            notes=list(data.get("notes", [])),
            privacy=dict(data.get("privacy", {})),
            instance_count=int(data.get("instance_count", 0)),
            live_count=int(data.get("live_count", 0)),
            trace_schema_version=data.get("trace_schema_version", TRACE_SCHEMA_VERSION),
            grammar=data.get("grammar", GRAMMAR_VERSION),
            continuity_policy=data.get("continuity_policy", CONTINUITY_POLICY),
            confidences=list(tables.get("confidences", list(CONFIDENCE_LEVELS))),
            sample_modes=list(tables.get("sample_modes", list(SAMPLE_MODES))),
        )
