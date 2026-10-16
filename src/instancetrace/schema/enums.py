"""Closed vocabularies for traces.

Event type names are stable schema tokens. Adding a token requires a schema
migration. ``LINEAGE_AMBIGUOUS`` is explicit: a mixed or destroyed element
keeps every candidate ancestor instead of a chosen parent.
"""

from __future__ import annotations

from enum import StrEnum


class CaptureMode(StrEnum):
    INSTRUMENTED = "INSTRUMENTED"
    PASSIVE_ONLY = "PASSIVE_ONLY"
    SYNTHETIC = "SYNTHETIC"


class Confidence(StrEnum):
    EXACT = "EXACT"
    PARTIAL = "PARTIAL"
    AMBIGUOUS = "AMBIGUOUS"
    UNKNOWN = "UNKNOWN"
    PASSIVE_ONLY = "PASSIVE_ONLY"


class EventType(StrEnum):
    CREATE = "CREATE"
    SOURCE_OBJECT = "SOURCE_OBJECT"
    DISTRIBUTE = "DISTRIBUTE"
    INSTANCE = "INSTANCE"
    TRANSFORM = "TRANSFORM"
    FILTER = "FILTER"
    MERGE = "MERGE"
    JOIN = "JOIN"
    REALIZE = "REALIZE"
    REMOVE = "REMOVE"
    DERIVE_ATTRIBUTE = "DERIVE_ATTRIBUTE"
    UNSUPPORTED_OR_LOST = "UNSUPPORTED_OR_LOST"
    LINEAGE_AMBIGUOUS = "LINEAGE_AMBIGUOUS"


class LossReason(StrEnum):
    NOT_INSTRUMENTED = "NOT_INSTRUMENTED"
    ATTRIBUTE_DROPPED = "ATTRIBUTE_DROPPED"
    ATTRIBUTE_UNREADABLE = "ATTRIBUTE_UNREADABLE"
    ATTRIBUTE_PROGRAM_MISMATCH = "ATTRIBUTE_PROGRAM_MISMATCH"
    CODEBOOK_MISSING = "CODEBOOK_MISSING"
    REALIZE_INSTANCES = "REALIZE_INSTANCES"
    REALIZE_DOMAIN_CHANGE = "REALIZE_DOMAIN_CHANGE"
    JOIN_GEOMETRY = "JOIN_GEOMETRY"
    REMESH = "REMESH"
    BOOLEAN = "BOOLEAN"
    RESAMPLE = "RESAMPLE"
    TOPOLOGY_CHANGE = "TOPOLOGY_CHANGE"
    EXPORT_CONVERSION = "EXPORT_CONVERSION"
    OBJECT_INSTANCING_UNINSTRUMENTED = "OBJECT_INSTANCING_UNINSTRUMENTED"
    INDEX_ONLY_SAMPLING = "INDEX_ONLY_SAMPLING"
    REVISION_MISMATCH = "REVISION_MISMATCH"
    NESTED_GROUP_OPAQUE = "NESTED_GROUP_OPAQUE"
    STRING_ATTR_UNAVAILABLE = "STRING_ATTR_UNAVAILABLE"
    NOT_IN_EVALUATED_SCENE = "NOT_IN_EVALUATED_SCENE"
    NOT_OBSERVED_AT_EVALUATION = "NOT_OBSERVED_AT_EVALUATION"
    LOOP_SUMMARISED = "LOOP_SUMMARISED"
    DEPTH_LIMIT = "DEPTH_LIMIT"
    CYCLE_DETECTED = "CYCLE_DETECTED"
    DUPLICATE_ID = "DUPLICATE_ID"
    HASH_COLLISION = "HASH_COLLISION"
    SOURCE_UNASSIGNED = "SOURCE_UNASSIGNED"
    AMBIGUOUS_PICK = "AMBIGUOUS_PICK"
    PICK_UNSUPPORTED = "PICK_UNSUPPORTED"


class SampleMode(StrEnum):
    AUTHORED = "authored"
    INDEX = "index"
    AUTHORED_TEXT = "authored_text"


# Written into every manifest so numeric columns stay self-describing.
CONFIDENCE_LEVELS: tuple[str, ...] = tuple(level.value for level in Confidence)
SAMPLE_MODES: tuple[str, ...] = tuple(mode.value for mode in SampleMode)
EVENT_TYPES: frozenset[str] = frozenset(item.value for item in EventType)
LOSS_REASONS: frozenset[str] = frozenset(item.value for item in LossReason)

FLAG_INDEX_UNSTABLE = 1
FLAG_REMOVED = 2
FLAG_IDENTITY_DESTROYED = 4
FLAG_NOT_OBSERVED = 8
FLAG_SEED_UNKNOWN = 32

FORBIDDEN_CONFIG_KEYS = frozenset(
    {
        "script",
        "python",
        "python_source",
        "executable",
        "eval",
        "bytecode",
        "source_code",
        "exec",
    }
)
