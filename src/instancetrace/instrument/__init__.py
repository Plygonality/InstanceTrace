"""Authored-graph instrumentation. Host application is separate."""

from instancetrace.instrument.execute import execute
from instancetrace.instrument.grammar import Program

__all__ = ["Program", "execute"]
