"""Execute a supported program into an event DAG and instance rows.

This records authored provenance. It does not evaluate Geometry Nodes and it
does not invent a chain for geometry that was never described by the program.
"""

from __future__ import annotations

import platform
import sys
from dataclasses import dataclass, field

from instancetrace import __version__
from instancetrace.ids.codec import format_id, parse_id
from instancetrace.ids.logical import (
    event_id_bytes,
    logical_id_bytes,
    logical_preimage,
    revision_bytes,
)
from instancetrace.ids.registry import IdRegistry
from instancetrace.instrument.grammar import (
    Distribute,
    FilterStep,
    GroupDecl,
    InstanceOn,
    LossyJoinStep,
    MergeStep,
    Program,
    RealizeStep,
    TransformStep,
    UnsupportedStep,
)
from instancetrace.instrument.matrix import identity, matmul, translation_matrix
from instancetrace.instrument.predicates import discards
from instancetrace.schema.canonical import decimal_string
from instancetrace.schema.enums import (
    CONFIDENCE_LEVELS,
    FLAG_IDENTITY_DESTROYED,
    FLAG_INDEX_UNSTABLE,
    FLAG_REMOVED,
    SAMPLE_MODES,
    CaptureMode,
    Confidence,
    EventType,
    LossReason,
)
from instancetrace.schema.models import Event, HostInfo, TraceMeta
from instancetrace.storage.manifest import LoadedTrace
from instancetrace.storage.table import build_index, table_from_rows


@dataclass
class _Row:
    sample_key: int
    sample_mode: str
    branch_id: str
    group_id: str
    source_id: str | None = None
    path: str = ""
    logical_id: bytes | None = None
    parent_ids: tuple[bytes, ...] = ()
    parent_key: tuple[str, int] | None = None
    seed: int = 0
    local: tuple[float, ...] = field(default_factory=identity)
    world: tuple[float, ...] = field(default_factory=identity)
    alive: bool = True
    confidence: str = Confidence.EXACT.value
    loss_reason: str | None = None
    primary_event_id: str | None = None
    container_event_id: str | None = None
    flags: int = 0
    candidate_event_ids: tuple[str, ...] = ()
    locator: str = ""


class _Events:
    def __init__(self, graph_id: str, revision: str) -> None:
        self.graph_id = graph_id
        self.revision = revision
        self.events: list[Event] = []
        self._ids: dict[str, int] = {}

    def add(
        self,
        event_type: str,
        path: str,
        parents: list[str],
        *,
        seed: int | None,
        config: dict,
        confidence: str = Confidence.EXACT.value,
        loss_reason: str | None = None,
        notes: str = "",
        display_path: str | None = None,
        candidates: list[str] | None = None,
        ordinal: int = 0,
    ) -> str:
        raw_parents = tuple(parse_id(parent) for parent in parents)
        digest = event_id_bytes(
            graph_id=self.graph_id,
            source_revision=self.revision,
            event_type=event_type,
            instrumented_path=path,
            seed=seed,
            parent_event_ids=raw_parents,
            config=config,
            ordinal=ordinal,
        )
        event_id = format_id(digest)
        if event_id in self._ids:
            return event_id
        self._ids[event_id] = len(self.events)
        self.events.append(
            Event(
                event_id=event_id,
                event_type=event_type,
                instrumented_path=path,
                parent_event_ids=list(parents),
                seed=seed,
                notes=notes,
                confidence=confidence,
                loss_reason=loss_reason,
                candidate_ancestor_ids=list(candidates or []),
                config=config,
                display_path=display_path,
                ordinal=ordinal,
            )
        )
        return event_id

    def code(self, event_id: str | None) -> int | None:
        if event_id is None:
            return None
        return self._ids[event_id]


def _group_path(groups: dict[str, GroupDecl], group_id: str) -> str:
    chain: list[str] = []
    seen: set[str] = set()
    current: str | None = group_id
    while current:
        if current in seen:
            raise ValueError(f"group cycle at {current}")
        seen.add(current)
        if current not in groups:
            raise ValueError(f"unknown group {current}")
        chain.append(current)
        current = groups[current].parent_group_id
    chain.reverse()
    return "/".join(chain)


def _host() -> HostInfo:
    return HostInfo(
        application="instancetrace",
        version=__version__,
        python_version=".".join(str(part) for part in sys.version_info[:3]),
        platform=platform.platform(),
    )


def _cap(current: str, ceiling: str) -> str:
    order = {
        Confidence.EXACT.value: 0,
        Confidence.PARTIAL.value: 1,
        Confidence.AMBIGUOUS.value: 2,
        Confidence.UNKNOWN.value: 3,
        Confidence.PASSIVE_ONLY.value: 4,
    }
    return current if order[current] >= order[ceiling] else ceiling


class _Engine:
    def __init__(self, program: Program) -> None:
        self.program = program
        self.revision = format_id(revision_bytes(program.declaration()))
        self.events = _Events(program.graph_id, self.revision)
        self.groups = {group.group_id: group for group in program.groups}
        self.sources = {source.source_id: source for source in program.sources}
        self.rows: dict[str, list[_Row]] = {}
        self.registry = IdRegistry()
        self.notes: list[str] = []
        self._create_ids: dict[str, str] = {}
        self._source_ids: dict[str, str] = {}
        self._branch_event: dict[str, str] = {}
        self._seen_payload: dict[bytes, bytes] = {}

    def run(self) -> None:
        self._emit_structure()
        for step in self.program.steps:
            if isinstance(step, Distribute):
                self._distribute(step)
            elif isinstance(step, InstanceOn):
                self._instance(step)
            elif isinstance(step, TransformStep):
                self._transform(step)
            elif isinstance(step, FilterStep):
                self._filter(step)
            elif isinstance(step, MergeStep):
                self._merge(step)
            elif isinstance(step, RealizeStep):
                self._realize(step)
            elif isinstance(step, LossyJoinStep):
                self._lossy_join(step)
            elif isinstance(step, UnsupportedStep):
                self._unsupported(step)
            else:
                raise TypeError(f"unsupported step {type(step).__name__}")
        self._resolve_world()

    def _emit_structure(self) -> None:
        pending = list(self.program.groups)
        guard = 0
        while pending:
            guard += 1
            if guard > len(self.program.groups) + 2:
                raise ValueError("group parent is missing or cyclic")
            group = pending.pop(0)
            if group.parent_group_id and group.parent_group_id not in self._create_ids:
                pending.append(group)
                continue
            parents = [self._create_ids[group.parent_group_id]] if group.parent_group_id else []
            path = _group_path(self.groups, group.group_id)
            self._create_ids[group.group_id] = self.events.add(
                EventType.CREATE.value,
                path,
                parents,
                seed=self.program.seed,
                config={"group_id": group.group_id},
                display_path=group.display_name,
                notes="group scope",
            )
        for source in self.program.sources:
            self._source_ids[source.source_id] = self.events.add(
                EventType.SOURCE_OBJECT.value,
                source.source_id,
                [],
                seed=None,
                config={"source_id": source.source_id, "family": source.family},
                display_path=source.display_name,
                notes="authored source object",
            )

    def _distribute(self, step: Distribute) -> None:
        if step.branch_id in self.rows:
            self.notes.append(f"duplicate distribute on branch {step.branch_id}")
        path = _group_path(self.groups, step.group_id)
        seed = self.program.seed if step.seed is None else step.seed
        parent_event = self._create_ids[step.group_id]
        event = self.events.add(
            EventType.DISTRIBUTE.value,
            path,
            [parent_event],
            seed=seed,
            config={
                "branch_id": step.branch_id,
                "mode": step.sample_key_mode,
                "count": step.count,
                "align_to_branch": step.align_to_branch,
            },
            confidence=Confidence.PARTIAL.value
            if step.sample_key_mode == "index"
            else Confidence.EXACT.value,
            loss_reason=LossReason.INDEX_ONLY_SAMPLING.value if step.sample_key_mode == "index" else None,
            notes="index keys follow evaluation order and are not stable across topology edits"
            if step.sample_key_mode == "index"
            else "authored sample keys",
        )
        self._branch_event[step.branch_id] = event
        made: list[_Row] = []
        if step.align_to_branch:
            parents = [row for row in self.rows.get(step.align_to_branch, []) if row.alive and row.logical_id]
            pairs = [(row.sample_key, row) for row in parents]
        else:
            if step.count is None:
                raise ValueError(f"distribute {step.step_id} needs a count")
            pairs = [(key, None) for key in range(step.count)]
        for sample_key, parent in pairs:
            flags = FLAG_INDEX_UNSTABLE if step.sample_key_mode == "index" else 0
            row = _Row(
                sample_key=int(sample_key),
                sample_mode=step.sample_key_mode,
                branch_id=step.branch_id,
                group_id=step.group_id,
                path=path,
                seed=seed,
                primary_event_id=event,
                flags=flags,
                confidence=Confidence.PARTIAL.value if flags else Confidence.EXACT.value,
                loss_reason=LossReason.INDEX_ONLY_SAMPLING.value if flags else None,
                parent_key=(parent.branch_id, parent.sample_key) if parent is not None else None,
                parent_ids=(parent.logical_id,) if parent is not None and parent.logical_id else (),
            )
            made.append(row)
        self.rows.setdefault(step.branch_id, []).extend(made)

    def _assign_identity(self, row: _Row) -> str:
        path = row.path if not row.source_id else f"{row.path}/{row.source_id}"
        row.path = path
        payload = logical_preimage(
            namespace=self.program.namespace,
            source_path=path,
            parent_ids=row.parent_ids,
            branch_id=row.branch_id,
            sample_key=row.sample_key,
            sample_key_mode=row.sample_mode,
            seed=row.seed,
        )
        digest = logical_id_bytes(
            namespace=self.program.namespace,
            source_path=path,
            parent_ids=row.parent_ids,
            branch_id=row.branch_id,
            sample_key=row.sample_key,
            sample_key_mode=row.sample_mode,
            seed=row.seed,
        )
        status = self.registry.register(digest, payload)
        row.logical_id = digest
        if status == "duplicate":
            row.alive = False
            row.flags |= FLAG_REMOVED
            row.loss_reason = LossReason.DUPLICATE_ID.value
            row.confidence = Confidence.AMBIGUOUS.value
            self.notes.append(f"duplicate logical id {format_id(digest)} on branch {row.branch_id}")
        elif status == "collision":
            row.confidence = Confidence.AMBIGUOUS.value
            row.loss_reason = LossReason.HASH_COLLISION.value
            self.notes.append(f"hash collision at {format_id(digest)}")
        return status

    def _instance(self, step: InstanceOn) -> None:
        if not step.sources:
            raise ValueError(f"instance {step.step_id} has no sources")
        for source_id in step.sources:
            if source_id not in self.sources:
                raise ValueError(f"unknown source {source_id}")
        path = _group_path(self.groups, step.group_id)
        distribute_event = self._branch_event.get(step.branch_id)
        if distribute_event is None:
            raise ValueError(f"instance branch {step.branch_id} was not distributed")
        for row in self.rows.get(step.branch_id, []):
            if row.logical_id is not None:
                payload = logical_preimage(
                    namespace=self.program.namespace,
                    source_path=row.path,
                    parent_ids=row.parent_ids,
                    branch_id=row.branch_id,
                    sample_key=row.sample_key,
                    sample_key_mode=row.sample_mode,
                    seed=row.seed,
                )
                status = self.registry.register(row.logical_id, payload)
                if status == "duplicate":
                    self.notes.append(f"duplicate instance registration {format_id(row.logical_id)}")
                continue
            source_id = step.sources[row.sample_key % len(step.sources)]
            row.source_id = source_id
            row.group_id = step.group_id
            source_event = self._source_ids[source_id]
            event = self.events.add(
                EventType.INSTANCE.value,
                f"{path}/{source_id}",
                [distribute_event, source_event],
                seed=row.seed,
                config={"branch_id": step.branch_id, "source_id": source_id},
                display_path=self.sources[source_id].display_name,
            )
            row.primary_event_id = event
            self._branch_event[step.branch_id] = event
            self._assign_identity(row)

    def _groups(self, branch_id: str, *, alive_only: bool) -> dict[str, list[_Row]]:
        groups: dict[str, list[_Row]] = {}
        for row in self.rows.get(branch_id, []):
            if alive_only and not row.alive:
                continue
            if row.primary_event_id is None:
                continue
            groups.setdefault(row.primary_event_id, []).append(row)
        return groups

    def _heads(self, branch_id: str) -> list[str]:
        return list(self._groups(branch_id, alive_only=True))

    def _transform(self, step: TransformStep) -> None:
        base = step.translation
        offset = step.per_sample_offset
        config = {
            "translation": [decimal_string(v) for v in step.translation],
            "per_sample_offset": [decimal_string(v) for v in step.per_sample_offset],
            "scale": decimal_string(step.scale),
            "compose_parent": step.compose_parent,
        }
        last = None
        for parent, members in self._groups(step.branch_id, alive_only=True).items():
            event = self.events.add(
                EventType.TRANSFORM.value,
                step.branch_id,
                [parent],
                seed=None,
                config=config,
                notes="local transform; world matrix is resolved after the program",
            )
            last = event
            for row in members:
                local = translation_matrix(
                    base[0] + offset[0] * row.sample_key,
                    base[1] + offset[1] * row.sample_key,
                    base[2] + offset[2] * row.sample_key,
                    step.scale,
                )
                row.local = matmul(row.local, local) if row.local != identity() else local
                row.primary_event_id = event
        if last is not None:
            self._branch_event[step.branch_id] = last

    def _filter(self, step: FilterStep) -> None:
        last = None
        for parent, members in self._groups(step.branch_id, alive_only=True).items():
            filter_event = self.events.add(
                EventType.FILTER.value,
                step.branch_id,
                [parent],
                seed=None,
                config={"predicate": step.predicate, "branch_id": step.branch_id, "parent": parent},
                notes="survivors stay live; matches become REMOVE rows",
            )
            remove_event = self.events.add(
                EventType.REMOVE.value,
                step.branch_id,
                [filter_event],
                seed=None,
                config={"predicate": step.predicate, "parent": parent},
                notes="filtered before the live output",
            )
            last = filter_event
            for row in members:
                if discards(step.predicate, row.sample_key):
                    row.alive = False
                    row.flags |= FLAG_REMOVED
                    row.primary_event_id = remove_event
                    if row.sample_mode != "index":
                        row.confidence = Confidence.EXACT.value
                else:
                    row.primary_event_id = filter_event
        if last is not None:
            self._branch_event[step.branch_id] = last

    def _merge(self, step: MergeStep) -> None:
        parents: list[str] = []
        for branch in step.branch_ids:
            for head in self._heads(branch):
                if head not in parents:
                    parents.append(head)
        event = self.events.add(
            EventType.MERGE.value,
            step.output_branch,
            parents,
            seed=self.program.seed,
            config={
                "branches": list(step.branch_ids),
                "output_branch": step.output_branch,
                "preserves_identity": step.preserves_identity,
            },
            notes="identity-preserving merge; each element keeps its own parent",
        )
        for branch in step.branch_ids:
            for row in self.rows.get(branch, []):
                if row.alive:
                    row.container_event_id = event

    def _realize(self, step: RealizeStep) -> None:
        last = None
        for previous, members in self._groups(step.branch_id, alive_only=True).items():
            realize = self.events.add(
                EventType.REALIZE.value,
                step.branch_id,
                [previous],
                seed=None,
                config={"ids_survive": step.ids_survive, "parent": previous},
                confidence=Confidence.PARTIAL.value,
                loss_reason=LossReason.REALIZE_DOMAIN_CHANGE.value
                if step.ids_survive
                else LossReason.REALIZE_INSTANCES.value,
                notes="realization destroys the instance domain",
            )
            if step.ids_survive:
                for row in members:
                    row.primary_event_id = realize
                    row.confidence = _cap(row.confidence, Confidence.PARTIAL.value)
                    row.loss_reason = LossReason.REALIZE_DOMAIN_CHANGE.value
                last = realize
                continue
            ambiguous = self.events.add(
                EventType.LINEAGE_AMBIGUOUS.value,
                step.branch_id,
                [realize, previous],
                seed=None,
                config={"operation": "realize", "parent": previous},
                confidence=Confidence.AMBIGUOUS.value,
                loss_reason=LossReason.REALIZE_INSTANCES.value,
                candidates=[previous],
                notes="no surviving instance identity; pre-realize event is a candidate, not a proof",
            )
            for row in members:
                row.primary_event_id = ambiguous
                row.confidence = Confidence.AMBIGUOUS.value
                row.loss_reason = LossReason.REALIZE_INSTANCES.value
                row.flags |= FLAG_IDENTITY_DESTROYED
                row.candidate_event_ids = (previous, realize)
            last = ambiguous
        if last is not None:
            self._branch_event[step.branch_id] = last

    def _lossy_join(self, step: LossyJoinStep) -> None:
        parents: list[str] = []
        for branch in step.branch_ids:
            for head in self._heads(branch):
                if head not in parents:
                    parents.append(head)
        join = self.events.add(
            EventType.JOIN.value,
            step.output_branch,
            parents,
            seed=None,
            config={"branches": list(step.branch_ids)},
            confidence=Confidence.AMBIGUOUS.value,
            loss_reason=step.loss_reason,
            notes="join without a surviving per-element id",
        )
        ambiguous = self.events.add(
            EventType.LINEAGE_AMBIGUOUS.value,
            step.output_branch,
            parents,
            seed=None,
            config={"operation": "join"},
            confidence=Confidence.AMBIGUOUS.value,
            loss_reason=step.loss_reason,
            candidates=parents,
            notes="candidate ancestors are the joined branches; none is the sole parent",
        )
        for branch in step.branch_ids:
            for row in self.rows.get(branch, []):
                if not row.alive:
                    continue
                row.primary_event_id = ambiguous
                row.container_event_id = join
                row.confidence = Confidence.AMBIGUOUS.value
                row.loss_reason = step.loss_reason
                row.flags |= FLAG_IDENTITY_DESTROYED
                row.candidate_event_ids = tuple(parents)

    def _unsupported(self, step: UnsupportedStep) -> None:
        last = None
        for previous, members in self._groups(step.branch_id, alive_only=True).items():
            event = self.events.add(
                EventType.UNSUPPORTED_OR_LOST.value,
                step.branch_id,
                [previous],
                seed=None,
                config={"operation": step.operation, "parent": previous},
                confidence=Confidence.AMBIGUOUS.value,
                loss_reason=step.loss_reason,
                candidates=[previous],
                notes="operation is outside the instrumented grammar",
            )
            for row in members:
                row.primary_event_id = event
                row.confidence = Confidence.AMBIGUOUS.value
                row.loss_reason = step.loss_reason
                row.flags |= FLAG_IDENTITY_DESTROYED
                row.candidate_event_ids = (previous,)
            last = event
        if last is not None:
            self._branch_event[step.branch_id] = last

    def _resolve_world(self) -> None:
        by_key = {(row.branch_id, row.sample_key): row for rows in self.rows.values() for row in rows}

        def world_of(row: _Row, stack: set[tuple[str, int]]) -> tuple[float, ...]:
            key = (row.branch_id, row.sample_key)
            if key in stack:
                raise ValueError(f"transform cycle at {key}")
            if row.parent_key is None:
                row.world = row.local
                return row.world
            stack.add(key)
            parent = by_key.get(row.parent_key)
            if parent is None:
                row.world = row.local
            else:
                row.world = matmul(world_of(parent, stack), row.local)
            stack.remove(key)
            return row.world

        for rows in self.rows.values():
            for row in rows:
                world_of(row, set())

    def finish(self, *, capture_mode: str) -> LoadedTrace:
        flat: list[_Row] = []
        for branch_rows in self.rows.values():
            flat.extend(branch_rows)
        code = self.events.code
        packed = []
        for row in flat:
            packed.append(
                {
                    "logical_id": row.logical_id,
                    "sample_key": row.sample_key,
                    "sample_mode": row.sample_mode,
                    "branch_id": row.branch_id,
                    "source_id": row.source_id,
                    "path": row.path,
                    "event_code": code(row.primary_event_id),
                    "container_event_code": code(row.container_event_id),
                    "alive": row.alive,
                    "confidence": row.confidence,
                    "loss_reason": row.loss_reason,
                    "seed": row.seed,
                    "transform": row.world,
                    "flags": row.flags,
                    "parent_ids": row.parent_ids,
                    "candidate_event_codes": [code(item) for item in row.candidate_event_ids if code(item) is not None],
                    "locator": row.locator,
                }
            )
        table = table_from_rows(packed, confidences=list(CONFIDENCE_LEVELS), sample_modes=list(SAMPLE_MODES))
        collisions = [
            {
                "logical_id": format_id(digest),
                "payloads": [left.hex(), right.hex()],
            }
            for digest, left, right in self.registry.collisions
        ]
        duplicates = [{"logical_id": format_id(digest)} for digest in self.registry.duplicates]
        meta = TraceMeta(
            capture_mode=capture_mode,
            graph_id=self.program.graph_id,
            source_revision=self.revision,
            scene_id=self.program.scene_id,
            frame=self.program.frame,
            epoch=self.program.epoch,
            seed=self.program.seed,
            units=self.program.units,
            unit_scale_to_meters=decimal_string(self.program.unit_scale_to_meters),
            coordinate_system=self.program.coordinate_system,
            host=_host(),
            labels=self.program.labels(),
            collisions=collisions,
            duplicates=duplicates,
            notes=self.notes,
        )
        loaded = LoadedTrace(meta=meta, events=self.events.events, table=table)
        loaded.index = build_index(table)
        loaded.meta.instance_count = len(table)
        loaded.meta.live_count = table.live_count
        return loaded


def execute(program: Program, *, capture_mode: str = CaptureMode.SYNTHETIC.value) -> LoadedTrace:
    engine = _Engine(program)
    engine.run()
    return engine.finish(capture_mode=capture_mode)
