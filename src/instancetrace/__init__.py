"""InstanceTrace: provenance for procedurally generated instances.

The offline package never imports ``bpy``. Host capture runs inside Blender
and returns data this package can validate.
"""

from __future__ import annotations

__version__ = "0.1.0"

TRACE_SCHEMA_VERSION = "0.1.0"
GRAMMAR_VERSION = "instancetrace.grammar.v0.1"
CONTINUITY_POLICY = "logical-id-v1"
