"""Optional SQLite lookup. The JSON/NPZ pair remains the source of truth."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from instancetrace.storage.manifest import LoadedTrace


def build_sqlite(trace: LoadedTrace, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            """
            create table instances (
                logical_id blob primary key,
                row_index integer not null,
                alive integer not null,
                source_id text,
                branch_id text,
                sample_key integer
            )
            """
        )
        table = trace.table
        rows = []
        for index in range(len(table)):
            if not table.has_logical_id(index):
                continue
            rows.append(
                (
                    table.logical_id[index].tobytes(),
                    index,
                    int(table.alive[index]),
                    table.decode(table.sources, int(table.source_code[index])),
                    table.decode(table.branches, int(table.branch_code[index])),
                    int(table.sample_key[index]),
                )
            )
        connection.executemany("insert into instances values (?, ?, ?, ?, ?, ?)", rows)
        connection.commit()
    finally:
        connection.close()
    return path


def lookup_sqlite(path: str | Path, logical_id: bytes) -> int | None:
    connection = sqlite3.connect(path)
    try:
        found = connection.execute(
            "select row_index from instances where logical_id = ?",
            (logical_id,),
        ).fetchone()
    finally:
        connection.close()
    if found is None:
        return None
    return int(found[0])
