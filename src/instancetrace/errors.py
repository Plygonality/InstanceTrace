"""Public errors. Exit codes are documented on the CLI."""

from __future__ import annotations


class InstanceTraceError(Exception):
    """Base error for expected failures."""


class SchemaVersionError(InstanceTraceError):
    """Manifest schema is absent or not migratable."""


class CorruptManifest(InstanceTraceError):
    """Checksum, structure, or array payload failed verification."""


class ManifestValidationError(InstanceTraceError):
    """Manifest loaded but violated the provenance contract."""


class UnknownInstance(InstanceTraceError):
    """The requested logical id is not a record in this manifest."""


class UnverifiedHost(InstanceTraceError):
    """A host adapter has no verified experiment and will not invent a trace."""


class SceneSafetyError(InstanceTraceError):
    """An operation would modify or delete something outside the trace collections."""
