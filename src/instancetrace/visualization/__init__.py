"""Text, DOT, and HTML reports."""

from instancetrace.visualization.dot import format_dot
from instancetrace.visualization.html import format_html
from instancetrace.visualization.text import format_report

__all__ = ["format_dot", "format_html", "format_report"]
