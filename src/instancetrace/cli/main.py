"""Command line interface.

``instancetrace demo`` prints a real logical id from the habitat trace.
The placeholder ``0x0000000000001234`` is not an id this tool accepts.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from instancetrace import __version__
from instancetrace.doctor import doctor
from instancetrace.errors import CorruptManifest, InstanceTraceError, SchemaVersionError
from instancetrace.ids.codec import parse_id
from instancetrace.query.diff import diff_traces
from instancetrace.query.engine import query_logical
from instancetrace.storage.manifest import load_trace
from instancetrace.visualization.dot import format_dot
from instancetrace.visualization.html import format_html
from instancetrace.visualization.text import format_report


def _load(path: str):
    try:
        return load_trace(path)
    except (CorruptManifest, SchemaVersionError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(3) from exc


def _cmd_demo(args: argparse.Namespace) -> int:
    from instancetrace.demo.habitat import build_demo

    instance_id = build_demo(args.out)
    out = Path(args.out)
    print(f"wrote {out / 'trace.json'}")
    print(f"instance {instance_id}")
    print(f"instancetrace query {out / 'trace.json'} --instance-id {instance_id} --format text")
    print(f"instancetrace query {out / 'trace.json'} --instance-id {instance_id} --format json")
    print(f"instancetrace graph {out / 'trace.json'} --instance-id {instance_id} --out {out / 'lineage.dot'}")
    print(f"instancetrace diff {out / 'runA' / 'trace.json'} {out / 'runB' / 'trace.json'} --out {out / 'continuity.json'}")
    return 0


def _cmd_inspect(args: argparse.Namespace) -> int:
    trace = _load(args.path)
    meta = trace.meta
    print(f"schema {meta.trace_schema_version}")
    print(f"capture {meta.capture_mode}")
    print(f"graph {meta.graph_id}")
    print(f"revision {meta.source_revision}")
    print(f"scene {meta.scene_id} frame {meta.frame} epoch {meta.epoch} seed {meta.seed}")
    print(f"units {meta.units} scale {meta.unit_scale_to_meters} coordinates {meta.coordinate_system}")
    print(f"events {len(trace.events)} instances {len(trace.table)} live {trace.table.live_count}")
    print(f"host {meta.host.application} {meta.host.version}")
    print("checksum ok")
    shown = 0
    for row in range(len(trace.table)):
        if not trace.table.alive[row] or not trace.table.has_logical_id(row):
            continue
        print(f"live {trace.table.logical_hex(row)}")
        shown += 1
        if shown >= 5:
            break
    return 0


def _cmd_query(args: argparse.Namespace) -> int:
    try:
        parse_id(args.instance_id)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        print("Run `instancetrace demo --out build/demo` and use the printed instance id.", file=sys.stderr)
        return 2
    trace = _load(args.path)
    report = query_logical(trace, args.instance_id, scene_revision=args.scene_revision)
    if args.format == "json":
        print(json.dumps(report, indent=2))
    else:
        print(format_report(report), end="")
    return 0


def _cmd_graph(args: argparse.Namespace) -> int:
    try:
        parse_id(args.instance_id)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    trace = _load(args.path)
    report = query_logical(trace, args.instance_id)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.suffix == ".html":
        out.write_text(format_html(report), encoding="utf-8")
    else:
        out.write_text(format_dot(report), encoding="utf-8")
    print(f"wrote {out}")
    return 0


def _cmd_diff(args: argparse.Namespace) -> int:
    left = _load(args.left)
    right = _load(args.right)
    report = diff_traces(left, right)
    text = json.dumps(report, indent=2) + "\n"
    if args.out:
        path = Path(args.out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        print(f"wrote {path}")
    else:
        print(text, end="")
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    trace = _load(args.path)
    print(f"valid {trace.meta.trace_schema_version} instances {len(trace.table)} events {len(trace.events)}")
    return 0


def _cmd_doctor(_args: argparse.Namespace) -> int:
    report = doctor()
    for check in report["checks"]:
        print(f"{check['status']:4} {check['name']:10} {check['detail']}")
    return 0 if report["ok"] else 1


def _cmd_capture(args: argparse.Namespace) -> int:
    from instancetrace.capture.instrumented import import_instrumented_dump
    from instancetrace.capture.passive import import_passive_dump

    dump = json.loads(Path(args.import_path).read_text(encoding="utf-8"))
    if args.passive or dump.get("capture_mode") == "PASSIVE_ONLY":
        trace = import_passive_dump(dump)
    else:
        program = None
        if args.program:
            print("error: --program expects a Python builder; pass the dump's embedded program via the Blender script", file=sys.stderr)
            return 2
        trace = import_instrumented_dump(dump, program)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    from instancetrace.storage.manifest import save_trace

    save_trace(trace, out / "trace.json")
    print(f"wrote {out / 'trace.json'}")
    print(f"capture {trace.meta.capture_mode}")
    return 0


def _cmd_bench(args: argparse.Namespace) -> int:
    from instancetrace.bench.measure import measure

    counts = [int(part) for part in args.counts.split(",") if part]
    report = measure(counts, out_dir=args.out)
    text = json.dumps(report, indent=2) + "\n"
    if args.out:
        path = Path(args.out) / "bench.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        print(f"wrote {path}")
    print(text, end="")
    return 0


def _cmd_redact(args: argparse.Namespace) -> int:
    from instancetrace.privacy.filter import redact
    from instancetrace.storage.manifest import save_trace

    trace = redact(_load(args.path), strict=args.strict)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    save_trace(trace, out / "trace.json")
    print(f"wrote {out / 'trace.json'}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="instancetrace", description="Provenance tracer for procedural instances.")
    parser.add_argument("--version", action="version", version=f"instancetrace {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    demo = commands.add_parser("demo", help="write the habitat facade trace")
    demo.add_argument("--out", required=True, help="output directory")
    demo.set_defaults(func=_cmd_demo)

    inspect = commands.add_parser("inspect", help="summarise a manifest")
    inspect.add_argument("path")
    inspect.set_defaults(func=_cmd_inspect)

    query = commands.add_parser("query", help="trace one logical instance id")
    query.add_argument("path")
    query.add_argument("--instance-id", required=True)
    query.add_argument("--format", choices=("text", "json"), default="text")
    query.add_argument("--scene-revision", default=None, help="flag INCOMPATIBLE when this revision differs")
    query.set_defaults(func=_cmd_query)

    graph = commands.add_parser("graph", help="write a DOT or HTML lineage graph")
    graph.add_argument("path")
    graph.add_argument("--instance-id", required=True)
    graph.add_argument("--out", required=True)
    graph.set_defaults(func=_cmd_graph)

    diff = commands.add_parser("diff", help="compare two manifests")
    diff.add_argument("left")
    diff.add_argument("right")
    diff.add_argument("--out", default=None)
    diff.set_defaults(func=_cmd_diff)

    validate = commands.add_parser("validate", help="check checksums, references, and acyclicity")
    validate.add_argument("path")
    validate.set_defaults(func=_cmd_validate)

    doctor_cmd = commands.add_parser("doctor", help="local environment check")
    doctor_cmd.set_defaults(func=_cmd_doctor)

    capture = commands.add_parser("capture", help="import a Blender capture dump")
    capture.add_argument("--import", dest="import_path", required=True, help="capture JSON from Blender")
    capture.add_argument("--out", required=True)
    capture.add_argument("--passive", action="store_true")
    capture.add_argument("--program", default=None)
    capture.set_defaults(func=_cmd_capture)

    bench = commands.add_parser("bench", help="measure instrumentation on this machine")
    bench.add_argument("--counts", default="1000,10000,100000")
    bench.add_argument("--out", default=None)
    bench.set_defaults(func=_cmd_bench)

    redact = commands.add_parser("redact", help="write a redacted copy of a manifest")
    redact.add_argument("path")
    redact.add_argument("--out", required=True)
    redact.add_argument("--strict", action="store_true")
    redact.set_defaults(func=_cmd_redact)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except InstanceTraceError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
