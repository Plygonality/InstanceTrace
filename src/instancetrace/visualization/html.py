"""Self-contained HTML lineage page. No remote assets."""

from __future__ import annotations

import html
from typing import Any


def format_html(report: dict[str, Any], *, diff: dict[str, Any] | None = None) -> str:
    title = html.escape(str(report.get("instance_id") or "trace"))
    operations = report.get("operations") or []
    items = []
    for operation in operations:
        kind = html.escape(str(operation["event_type"]))
        path = html.escape(str(operation["instrumented_path"]))
        notes = html.escape(str(operation.get("notes") or ""))
        loss = operation.get("loss_reason")
        klass = "loss" if loss or kind in {"LINEAGE_AMBIGUOUS", "UNSUPPORTED_OR_LOST", "REMOVE"} else "step"
        loss_html = f"<em>{html.escape(str(loss))}</em>" if loss else ""
        items.append(
            f'<li class="{klass}"><strong>{kind}</strong> {path} {loss_html}<br><span>{notes}</span></li>'
        )
    chain = "\n".join(items) or "<li>No instrumented operations.</li>"
    candidates = report.get("candidate_ancestors") or []
    candidate_html = ""
    if candidates:
        lis = "".join(f"<li>{html.escape(item)}</li>" for item in candidates)
        candidate_html = f"<h2>Candidate ancestors</h2><ul>{lis}</ul>"
    diff_html = ""
    if diff:
        counts = diff.get("counts", {})
        labels = ", ".join(html.escape(str(item)) for item in diff.get("labels", []))
        diff_html = (
            "<h2>Regeneration comparison</h2>"
            f"<p>{labels}</p>"
            "<ul>"
            f"<li>Persisted {counts.get('persisted', 0)}</li>"
            f"<li>Added {counts.get('added', 0)}</li>"
            f"<li>Removed {counts.get('removed', 0)}</li>"
            f"<li>Same slot, new id {counts.get('changed_same_slot', 0)}</li>"
            "</ul>"
        )
    origin = html.escape(str(report.get("origin_status")))
    source = html.escape(str(report.get("source_label") or report.get("source_id") or "unknown"))
    path = html.escape(str(report.get("instrumented_path") or "unknown"))
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>InstanceTrace {title}</title>
<style>
  body {{ margin: 0; background: #f6f3ec; color: #1c1915; font: 16px/1.45 Georgia, serif; }}
  main {{ max-width: 760px; margin: 0 auto; padding: 48px 24px 80px; }}
  h1 {{ font-weight: 500; letter-spacing: -0.03em; font-size: 28px; }}
  .meta {{ color: #5c564c; }}
  ol {{ list-style: none; padding: 0; }}
  li {{ border-left: 3px solid #1c1915; margin: 0; padding: 10px 14px; }}
  li.loss {{ border-left-color: #9c3b2e; background: #f8ebe7; }}
  code {{ font-family: ui-monospace, monospace; font-size: 13px; }}
</style>
</head>
<body>
<main>
  <p class="meta">InstanceTrace lineage</p>
  <h1><code>{title}</code></h1>
  <p>Origin <strong>{origin}</strong>. Source object <strong>{source}</strong>.</p>
  <p>Path <code>{path}</code></p>
  <p>Branch {html.escape(str(report.get("branch_id") or "unknown"))},
     sample {html.escape(str(report.get("sample_key")))}
     ({html.escape(str(report.get("sample_key_mode") or ""))}),
     seed {html.escape(str(report.get("seed")))}.</p>
  <h2>Operations</h2>
  <ol>
  {chain}
  </ol>
  {candidate_html}
  {diff_html}
</main>
</body>
</html>
"""
