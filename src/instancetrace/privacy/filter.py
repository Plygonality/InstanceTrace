"""Local-only redaction. Nothing in this package sends a manifest anywhere."""

from __future__ import annotations

import hashlib

from instancetrace.schema.models import Event
from instancetrace.storage.manifest import LoadedTrace
from instancetrace.storage.table import InstanceTable


def _token(value: str, salt: str) -> str:
    digest = hashlib.blake2b(f"{salt}:{value}".encode(), digest_size=8).hexdigest()
    return f"redacted:{digest}"


def redact(trace: LoadedTrace, *, strict: bool = False) -> LoadedTrace:
    """Drop display labels, locators, and host platform detail.

    Strict mode also replaces source, group, branch, and path strings with
    stable tokens so a shared manifest does not expose scene structure.
    Logical id bytes stay, because they are already digests.
    """
    labels: dict[str, str] = {}
    mapping: dict[str, str] = {}

    def hide(value: str) -> str:
        if not strict or not value:
            return value
        if value not in mapping:
            mapping[value] = _token(value, "instancetrace.privacy.v1")
        return mapping[value]

    events = []
    for event in trace.events:
        events.append(
            Event(
                event_id=event.event_id,
                event_type=event.event_type,
                instrumented_path=hide(event.instrumented_path),
                parent_event_ids=list(event.parent_event_ids),
                seed=event.seed,
                notes="" if strict else event.notes,
                confidence=event.confidence,
                loss_reason=event.loss_reason,
                candidate_ancestor_ids=list(event.candidate_ancestor_ids),
                config={} if strict else dict(event.config),
                display_path=None,
                ordinal=event.ordinal,
            )
        )
    table = trace.table
    meta = trace.meta
    meta.labels = labels
    meta.privacy = {"redacted": True, "policy": "strict" if strict else "labels", "telemetry": False}
    meta.host.platform = "redacted"
    if strict:
        meta.graph_id = hide(meta.graph_id)
        meta.scene_id = hide(meta.scene_id)
        meta.branches = [hide(item) for item in table.branches]
        meta.sources = [hide(item) for item in table.sources]
        meta.paths = [hide(item) for item in table.paths]
        table.branches = list(meta.branches)
        table.sources = list(meta.sources)
        table.paths = list(meta.paths)
    cleared = InstanceTable(
        logical_id=table.logical_id,
        sample_key=table.sample_key,
        sample_mode=table.sample_mode,
        branch_code=table.branch_code,
        source_code=table.source_code,
        path_code=table.path_code,
        event_code=table.event_code,
        container_event_code=table.container_event_code,
        alive=table.alive,
        confidence=table.confidence,
        loss_code=table.loss_code,
        seed=table.seed,
        transform=table.transform,
        flags=table.flags,
        parent_indptr=table.parent_indptr,
        parent_ids=table.parent_ids,
        candidate_indptr=table.candidate_indptr,
        candidate_event_codes=table.candidate_event_codes,
        locator_offsets=table.locator_offsets * 0,
        locator_utf8=table.locator_utf8[:0],
        branches=list(table.branches),
        sources=list(table.sources),
        paths=list(table.paths),
        loss_reasons=list(table.loss_reasons),
        confidences=list(table.confidences),
        sample_modes=list(table.sample_modes),
    )
    # Zeroing offsets without resizing the indptr still has to be a valid empty blob.
    cleared.locator_offsets = table.locator_offsets.copy()
    cleared.locator_offsets[:] = 0
    redacted = LoadedTrace(meta=meta, events=events, table=cleared, index=dict(trace.index))
    return redacted
