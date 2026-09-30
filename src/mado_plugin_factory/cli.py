from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .scanner import ScanError, scan_candidate


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mpf", description="MADO Plugin Factory")
    sub = parser.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan", help="Statically inspect a plugin/skill candidate")
    scan.add_argument("path", nargs="?", default=".", help="Candidate directory (default: .)")
    scan.add_argument("--pretty", action="store_true", help="Pretty-print JSON output")
    scan.add_argument(
        "--fail-on-not-ready",
        action="store_true",
        help="Exit with status 2 when architecture is not_ready",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command != "scan":
        return 1

    try:
        result = scan_candidate(Path(args.path))
    except ScanError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1

    indent = 2 if args.pretty else None
    print(json.dumps(result, ensure_ascii=False, indent=indent, sort_keys=True))
    if args.fail_on_not_ready and result["architecture"] == "not_ready":
        return 2
    return 0
