"""Schema migration policy.

v0.1 reads ``0.1.0`` only. Unknown versions raise. A future migration must be
an explicit function from one version to the next and must refuse to guess
missing provenance fields.
"""

from __future__ import annotations

from typing import Any

from instancetrace import TRACE_SCHEMA_VERSION
from instancetrace.errors import SchemaVersionError

SUPPORTED_VERSIONS = frozenset({TRACE_SCHEMA_VERSION})


def schema_version_of(document: dict[str, Any]) -> str:
    if "trace_schema_version" in document:
        return str(document["trace_schema_version"])
    trace = document.get("trace")
    if isinstance(trace, dict) and "trace_schema_version" in trace:
        return str(trace["trace_schema_version"])
    return ""


def migrate(document: dict[str, Any]) -> dict[str, Any]:
    version = schema_version_of(document)
    if version in SUPPORTED_VERSIONS:
        return document
    if not version:
        raise SchemaVersionError("manifest has no trace_schema_version")
    raise SchemaVersionError(
        f"trace_schema_version {version} cannot be migrated; this build reads {sorted(SUPPORTED_VERSIONS)}"
    )
