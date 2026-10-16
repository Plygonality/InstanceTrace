"""Compare two manifests. Frame and epoch are coordinates, not identity."""

from __future__ import annotations

from typing import Any

from instancetrace.ids.codec import format_id
from instancetrace.storage.manifest import LoadedTrace


def _ids(trace: LoadedTrace) -> dict[bytes, int]:
    found: dict[bytes, int] = {}
    for key, rows in trace.index.items():
        found[key] = rows[0]
    return found


def _sample_signature(trace: LoadedTrace, row: int) -> tuple[Any, ...]:
    table = trace.table
    branch = table.decode(table.branches, int(table.branch_code[row]))
    path = table.decode(table.paths, int(table.path_code[row]))
    return (branch, path, int(table.sample_key[row]), table.sample_modes[int(table.sample_mode[row])])


def diff_traces(left: LoadedTrace, right: LoadedTrace, *, list_limit: int = 10000) -> dict[str, Any]:
    left_ids = _ids(left)
    right_ids = _ids(right)
    persisted = sorted(set(left_ids) & set(right_ids), key=lambda item: item.hex())
    removed = sorted(set(left_ids) - set(right_ids), key=lambda item: item.hex())
    added = sorted(set(right_ids) - set(left_ids), key=lambda item: item.hex())
    labels: list[str] = []
    if left.meta.source_revision != right.meta.source_revision:
        labels.append("REVISION_DIVERGED")
    if left.meta.seed != right.meta.seed:
        labels.append("SEED_CHANGED")
    if left.meta.frame != right.meta.frame:
        labels.append("FRAME_COORDINATE_CHANGED")
    if left.meta.epoch != right.meta.epoch:
        labels.append("EPOCH_COORDINATE_CHANGED")
    left_samples = {_sample_signature(left, row) for row in left_ids.values()}
    right_samples = {_sample_signature(right, row) for row in right_ids.values()}
    if left_samples != right_samples:
        labels.append("SAMPLE_DOMAIN_CHANGED")
    changed_same_slot: list[dict[str, str]] = []
    right_by_sig = {_sample_signature(right, row): key for key, row in right_ids.items()}
    slot_seed_changed = False
    for key, row in left_ids.items():
        signature = _sample_signature(left, row)
        other = right_by_sig.get(signature)
        if other is not None and other != key:
            changed_same_slot.append(
                {"slot_branch": signature[0] or "", "before": format_id(key), "after": format_id(other)}
            )
            if int(left.table.seed[row]) != int(right.table.seed[right_ids[other]]):
                slot_seed_changed = True
    if slot_seed_changed and "SEED_CHANGED" not in labels:
        labels.append("SEED_CHANGED")
    if changed_same_slot and "SEED_CHANGED" not in labels:
        labels.append("IDENTITY_INPUT_CHANGED")
    if persisted and "REVISION_DIVERGED" in labels:
        labels.append("PERSISTED_UNDER_REVISION_CHANGE")
    if persisted and "REVISION_DIVERGED" not in labels and not removed and not added:
        labels.append("ALL_PERSISTED")
    elif persisted:
        labels.append("PARTIAL_PERSISTENCE")

    def take(values: list[bytes]) -> tuple[list[str], bool]:
        shown = values[:list_limit]
        return [format_id(item) for item in shown], len(values) > list_limit

    persisted_ids, persisted_truncated = take(persisted)
    removed_ids, removed_truncated = take(removed)
    added_ids, added_truncated = take(added)
    return {
        "trace_schema_version": left.meta.trace_schema_version,
        "left_revision": left.meta.source_revision,
        "right_revision": right.meta.source_revision,
        "left_seed": left.meta.seed,
        "right_seed": right.meta.seed,
        "left_frame": left.meta.frame,
        "right_frame": right.meta.frame,
        "left_epoch": left.meta.epoch,
        "right_epoch": right.meta.epoch,
        "labels": labels,
        "counts": {
            "persisted": len(persisted),
            "removed": len(removed),
            "added": len(added),
            "changed_same_slot": len(changed_same_slot),
        },
        "persisted_ids": persisted_ids,
        "removed_ids": removed_ids,
        "added_ids": added_ids,
        "changed_same_slot": changed_same_slot[:list_limit],
        "truncated": persisted_truncated or removed_truncated or added_truncated,
        "continuity_policy": left.meta.continuity_policy,
    }
