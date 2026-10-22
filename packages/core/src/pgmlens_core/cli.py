"""``pgmlens`` command line interface."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from . import __version__
from .analysis import analyze
from .demo import generate_demo
from .models import Dataset
from .render import render_text
from .risk import SEVERITY_RANK, Severity, load_rules


def _load_dataset(path: str) -> Dataset:
    source = sys.stdin.read() if path == "-" else Path(path).read_text("utf-8")
    return Dataset.model_validate_json(source)


def _cmd_analyze(args: argparse.Namespace) -> int:
    ds = _load_dataset(args.path)
    rules = load_rules(args.rules)
    result = analyze(ds, rules, seed=args.seed)
    if args.format == "json":
        print(result.model_dump_json(indent=2))
    else:
        print(render_text(result, ds))
    if args.fail_on:
        threshold = SEVERITY_RANK[Severity(args.fail_on)]
        if any(SEVERITY_RANK[f.severity] >= threshold for f in result.findings):
            return 1
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    ds = _load_dataset(args.path)
    print(
        f"OK: {len(ds.issues)} issues, {len(ds.dependencies)} dependencies, {len(ds.milestones)} milestones"
    )
    return 0


def _cmd_demo(args: argparse.Namespace) -> int:
    as_of = (
        datetime.now(UTC)
        if args.now
        else (datetime.fromisoformat(args.as_of) if args.as_of else None)
    )
    payload = generate_demo(as_of=as_of, seed=args.seed).model_dump_json(indent=2)
    if args.out:
        Path(args.out).write_text(payload + "\n", encoding="utf-8")
        print(f"Wrote {args.out}")
    else:
        print(payload)
    return 0


def _cmd_schema(_: argparse.Namespace) -> int:
    print(json.dumps(Dataset.model_json_schema(), indent=2))
    return 0


def _cmd_brief(args: argparse.Namespace) -> int:
    try:
        from pgmlens_reporting import build_briefing, render_markdown
    except ImportError:
        print("Install pgmlens-reporting to generate briefings.", file=sys.stderr)
        return 2
    ds = _load_dataset(args.path)
    result = analyze(ds, load_rules(args.rules))
    briefing = build_briefing(result, ds, model=args.llm)
    print(render_markdown(briefing))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pgmlens", description="Program intelligence from your delivery data."
    )
    parser.add_argument("--version", action="version", version=f"pgmlens {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("analyze", help="analyze a dataset and print health, forecasts and risks")
    p.add_argument("path", help="dataset JSON file, or - for stdin")
    p.add_argument("--format", choices=["text", "json"], default="text")
    p.add_argument("--rules", help="custom rules YAML (may use `extends: default`)")
    p.add_argument("--seed", type=int, default=7, help="Monte Carlo seed (default 7)")
    p.add_argument(
        "--fail-on",
        choices=[s.value for s in Severity],
        help="exit 1 if any finding is at least this severe",
    )
    p.set_defaults(func=_cmd_analyze)

    p = sub.add_parser("validate", help="validate a dataset against the schema")
    p.add_argument("path")
    p.set_defaults(func=_cmd_validate)

    p = sub.add_parser("demo", help="generate the synthetic demo dataset")
    p.add_argument("--out", help="write to a file instead of stdout")
    p.add_argument("--now", action="store_true", help="anchor the demo to the current time")
    p.add_argument("--as-of", help="anchor the demo to an ISO timestamp")
    p.add_argument("--seed", type=int, default=42)
    p.set_defaults(func=_cmd_demo)

    p = sub.add_parser("schema", help="print the dataset JSON Schema")
    p.set_defaults(func=_cmd_schema)

    p = sub.add_parser("brief", help="generate an executive briefing (needs pgmlens-reporting)")
    p.add_argument("path")
    p.add_argument("--rules")
    p.add_argument(
        "--llm", metavar="MODEL", help="LiteLLM model name; omit for the deterministic briefing"
    )
    p.set_defaults(func=_cmd_brief)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except ValidationError as exc:
        print(f"Invalid dataset:\n{exc}", file=sys.stderr)
        return 2
    except (OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
