"""Columnar instance rows.

Operation templates stay in JSON. Repeated instances stay in compressed arrays.
Locator strings are length-prefixed UTF-8, never a pickled object array.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from instancetrace.ids.codec import format_id


def _codes(values: list[str]) -> dict[str, int]:
    table: dict[str, int] = {}
    for value in values:
        if value not in table:
            table[value] = len(table)
    return table


@dataclass
class InstanceTable:
    logical_id: np.ndarray
    sample_key: np.ndarray
    sample_mode: np.ndarray
    branch_code: np.ndarray
    source_code: np.ndarray
    path_code: np.ndarray
    event_code: np.ndarray
    container_event_code: np.ndarray
    alive: np.ndarray
    confidence: np.ndarray
    loss_code: np.ndarray
    seed: np.ndarray
    transform: np.ndarray
    flags: np.ndarray
    parent_indptr: np.ndarray
    parent_ids: np.ndarray
    candidate_indptr: np.ndarray
    candidate_event_codes: np.ndarray
    locator_offsets: np.ndarray
    locator_utf8: np.ndarray
    branches: list[str]
    sources: list[str]
    paths: list[str]
    loss_reasons: list[str]
    confidences: list[str]
    sample_modes: list[str]

    def __len__(self) -> int:
        return int(self.logical_id.shape[0])

    @property
    def live_count(self) -> int:
        if len(self) == 0:
            return 0
        return int(np.count_nonzero(self.alive))

    def logical_hex(self, row: int) -> str:
        return format_id(self.logical_id[row].tobytes())

    def has_logical_id(self, row: int) -> bool:
        return bool(self.logical_id[row].any())

    def locator(self, row: int) -> str:
        start = int(self.locator_offsets[row])
        end = int(self.locator_offsets[row + 1])
        if start == end:
            return ""
        return bytes(self.locator_utf8[start:end]).decode("utf-8")

    def parent_hexes(self, row: int) -> list[str]:
        start = int(self.parent_indptr[row])
        end = int(self.parent_indptr[row + 1])
        return [format_id(self.parent_ids[index].tobytes()) for index in range(start, end)]

    def candidate_codes(self, row: int) -> list[int]:
        start = int(self.candidate_indptr[row])
        end = int(self.candidate_indptr[row + 1])
        return [int(self.candidate_event_codes[index]) for index in range(start, end)]

    def decode(self, table: list[str], code: int) -> str | None:
        if code < 0 or code >= len(table):
            return None
        return table[code]

    def write_npz(self, path: str) -> None:
        with open(path, "wb") as handle:
            np.savez_compressed(
                handle,
            logical_id=self.logical_id,
            sample_key=self.sample_key,
            sample_mode=self.sample_mode,
            branch_code=self.branch_code,
            source_code=self.source_code,
            path_code=self.path_code,
            event_code=self.event_code,
            container_event_code=self.container_event_code,
            alive=self.alive,
            confidence=self.confidence,
            loss_code=self.loss_code,
            seed=self.seed,
            transform=self.transform,
            flags=self.flags,
            parent_indptr=self.parent_indptr,
            parent_ids=self.parent_ids,
            candidate_indptr=self.candidate_indptr,
            candidate_event_codes=self.candidate_event_codes,
            locator_offsets=self.locator_offsets,
            locator_utf8=self.locator_utf8,
            )

    @classmethod
    def from_arrays(cls, arrays: dict[str, np.ndarray], meta_tables: dict[str, list[str]]) -> InstanceTable:
        count = int(arrays["logical_id"].shape[0])
        return cls(
            logical_id=np.asarray(arrays["logical_id"], dtype=np.uint8).reshape(count, 16),
            sample_key=np.asarray(arrays["sample_key"], dtype=np.int64),
            sample_mode=np.asarray(arrays["sample_mode"], dtype=np.uint8),
            branch_code=np.asarray(arrays["branch_code"], dtype=np.int32),
            source_code=np.asarray(arrays["source_code"], dtype=np.int32),
            path_code=np.asarray(arrays["path_code"], dtype=np.int32),
            event_code=np.asarray(arrays["event_code"], dtype=np.int32),
            container_event_code=np.asarray(arrays["container_event_code"], dtype=np.int32),
            alive=np.asarray(arrays["alive"], dtype=np.uint8),
            confidence=np.asarray(arrays["confidence"], dtype=np.uint8),
            loss_code=np.asarray(arrays["loss_code"], dtype=np.int32),
            seed=np.asarray(arrays["seed"], dtype=np.int64),
            transform=np.asarray(arrays["transform"], dtype=np.float64).reshape(count, 16),
            flags=np.asarray(arrays["flags"], dtype=np.uint32),
            parent_indptr=np.asarray(arrays["parent_indptr"], dtype=np.int64),
            parent_ids=np.asarray(arrays["parent_ids"], dtype=np.uint8).reshape(-1, 16),
            candidate_indptr=np.asarray(arrays["candidate_indptr"], dtype=np.int64),
            candidate_event_codes=np.asarray(arrays["candidate_event_codes"], dtype=np.int32),
            locator_offsets=np.asarray(arrays["locator_offsets"], dtype=np.int64),
            locator_utf8=np.asarray(arrays["locator_utf8"], dtype=np.uint8),
            branches=list(meta_tables["branches"]),
            sources=list(meta_tables["sources"]),
            paths=list(meta_tables["paths"]),
            loss_reasons=list(meta_tables["loss_reasons"]),
            confidences=list(meta_tables["confidences"]),
            sample_modes=list(meta_tables["sample_modes"]),
        )


def build_index(table: InstanceTable) -> dict[bytes, list[int]]:
    index: dict[bytes, list[int]] = {}
    for row in range(len(table)):
        if not table.has_logical_id(row):
            continue
        key = table.logical_id[row].tobytes()
        index.setdefault(key, []).append(row)
    return index


def empty_table(meta_tables: dict[str, list[str]]) -> InstanceTable:
    return InstanceTable(
        logical_id=np.zeros((0, 16), dtype=np.uint8),
        sample_key=np.zeros((0,), dtype=np.int64),
        sample_mode=np.zeros((0,), dtype=np.uint8),
        branch_code=np.zeros((0,), dtype=np.int32),
        source_code=np.zeros((0,), dtype=np.int32),
        path_code=np.zeros((0,), dtype=np.int32),
        event_code=np.zeros((0,), dtype=np.int32),
        container_event_code=np.zeros((0,), dtype=np.int32),
        alive=np.zeros((0,), dtype=np.uint8),
        confidence=np.zeros((0,), dtype=np.uint8),
        loss_code=np.zeros((0,), dtype=np.int32),
        seed=np.zeros((0,), dtype=np.int64),
        transform=np.zeros((0, 16), dtype=np.float64),
        flags=np.zeros((0,), dtype=np.uint32),
        parent_indptr=np.zeros((1,), dtype=np.int64),
        parent_ids=np.zeros((0, 16), dtype=np.uint8),
        candidate_indptr=np.zeros((1,), dtype=np.int64),
        candidate_event_codes=np.zeros((0,), dtype=np.int32),
        locator_offsets=np.zeros((1,), dtype=np.int64),
        locator_utf8=np.zeros((0,), dtype=np.uint8),
        branches=list(meta_tables.get("branches", [])),
        sources=list(meta_tables.get("sources", [])),
        paths=list(meta_tables.get("paths", [])),
        loss_reasons=list(meta_tables.get("loss_reasons", [])),
        confidences=list(meta_tables.get("confidences", [])),
        sample_modes=list(meta_tables.get("sample_modes", [])),
    )


def table_from_rows(rows: list[dict], *, confidences: list[str], sample_modes: list[str]) -> InstanceTable:
    """Pack row dicts. This path is for authored graphs, not the 100k bench."""
    branches = _codes([row["branch_id"] for row in rows if row.get("branch_id")])
    sources = _codes([row["source_id"] for row in rows if row.get("source_id")])
    paths = _codes([row["path"] for row in rows if row.get("path")])
    losses = _codes([row["loss_reason"] for row in rows if row.get("loss_reason")])
    branch_list = [""] * len(branches)
    for name, code in branches.items():
        branch_list[code] = name
    source_list = [""] * len(sources)
    for name, code in sources.items():
        source_list[code] = name
    path_list = [""] * len(paths)
    for name, code in paths.items():
        path_list[code] = name
    loss_list = [""] * len(losses)
    for name, code in losses.items():
        loss_list[code] = name
    mode_index = {name: index for index, name in enumerate(sample_modes)}
    confidence_index = {name: index for index, name in enumerate(confidences)}

    count = len(rows)
    logical = np.zeros((count, 16), dtype=np.uint8)
    sample_key = np.zeros((count,), dtype=np.int64)
    sample_mode = np.zeros((count,), dtype=np.uint8)
    branch_code = np.full((count,), -1, dtype=np.int32)
    source_code = np.full((count,), -1, dtype=np.int32)
    path_code = np.full((count,), -1, dtype=np.int32)
    event_code = np.full((count,), -1, dtype=np.int32)
    container = np.full((count,), -1, dtype=np.int32)
    alive = np.zeros((count,), dtype=np.uint8)
    confidence = np.zeros((count,), dtype=np.uint8)
    loss_code = np.full((count,), -1, dtype=np.int32)
    seed = np.zeros((count,), dtype=np.int64)
    transform = np.zeros((count, 16), dtype=np.float64)
    flags = np.zeros((count,), dtype=np.uint32)
    parent_indptr = np.zeros((count + 1,), dtype=np.int64)
    parent_blob: list[bytes] = []
    candidate_indptr = np.zeros((count + 1,), dtype=np.int64)
    candidate_blob: list[int] = []
    locator_offsets = np.zeros((count + 1,), dtype=np.int64)
    locator_blob = bytearray()

    for index, row in enumerate(rows):
        raw = row.get("logical_id")
        if raw:
            logical[index] = np.frombuffer(raw, dtype=np.uint8)
        sample_key[index] = int(row.get("sample_key") or 0)
        sample_mode[index] = mode_index[row.get("sample_mode", "authored")]
        if row.get("branch_id"):
            branch_code[index] = branches[row["branch_id"]]
        if row.get("source_id"):
            source_code[index] = sources[row["source_id"]]
        if row.get("path"):
            path_code[index] = paths[row["path"]]
        if row.get("event_code") is not None:
            event_code[index] = int(row["event_code"])
        if row.get("container_event_code") is not None:
            container[index] = int(row["container_event_code"])
        alive[index] = 1 if row.get("alive") else 0
        confidence[index] = confidence_index[row.get("confidence", "UNKNOWN")]
        if row.get("loss_reason"):
            loss_code[index] = losses[row["loss_reason"]]
        seed[index] = int(row.get("seed") or 0)
        transform[index] = np.asarray(row.get("transform") or (0.0,) * 16, dtype=np.float64)
        flags[index] = int(row.get("flags") or 0)
        for parent in row.get("parent_ids") or ():
            parent_blob.append(parent)
        parent_indptr[index + 1] = len(parent_blob)
        for code in row.get("candidate_event_codes") or ():
            candidate_blob.append(int(code))
        candidate_indptr[index + 1] = len(candidate_blob)
        locator = (row.get("locator") or "").encode("utf-8")
        locator_blob.extend(locator)
        locator_offsets[index + 1] = len(locator_blob)

    parent_ids = (
        np.frombuffer(b"".join(parent_blob), dtype=np.uint8).reshape(-1, 16).copy()
        if parent_blob
        else np.zeros((0, 16), dtype=np.uint8)
    )
    return InstanceTable(
        logical_id=logical,
        sample_key=sample_key,
        sample_mode=sample_mode,
        branch_code=branch_code,
        source_code=source_code,
        path_code=path_code,
        event_code=event_code,
        container_event_code=container,
        alive=alive,
        confidence=confidence,
        loss_code=loss_code,
        seed=seed,
        transform=transform,
        flags=flags,
        parent_indptr=parent_indptr,
        parent_ids=parent_ids,
        candidate_indptr=candidate_indptr,
        candidate_event_codes=np.asarray(candidate_blob, dtype=np.int32),
        locator_offsets=locator_offsets,
        locator_utf8=np.frombuffer(bytes(locator_blob), dtype=np.uint8).copy(),
        branches=branch_list,
        sources=source_list,
        paths=path_list,
        loss_reasons=loss_list,
        confidences=list(confidences),
        sample_modes=list(sample_modes),
    )
