"""Import host dumps. This package does not import ``bpy``."""

from instancetrace.capture.instrumented import import_instrumented_dump
from instancetrace.capture.passive import import_passive_dump

__all__ = ["import_instrumented_dump", "import_passive_dump"]
