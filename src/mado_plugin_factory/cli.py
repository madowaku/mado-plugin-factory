from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .evals import (
    DEFAULT_OUTPUT,
    EvalError,
    compile_submission_evals,
    load_eval_metadata,
    write_submission_evals,
)
from .manifest import ManifestError, compile_manifest, load_metadata, write_compiled_manifest
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

    manifest = sub.add_parser("manifest", help="Compile a portable plugin.json manifest")
    manifest.add_argument("path", nargs="?", default=".", help="Candidate directory (default: .)")
    manifest.add_argument("--metadata", type=Path, help="JSON metadata overrides")
    manifest.add_argument("--name", help="Stable kebab-case plugin name")
    manifest.add_argument("--version", help="Semantic version, e.g. 0.1.0")
    manifest.add_argument("--description", help="Portable plugin description")
    manifest.add_argument("--display-name", help="OpenAI install-surface display name")
    manifest.add_argument("--short-description", help="OpenAI install-surface short description")
    manifest.add_argument("--long-description", help="OpenAI install-surface long description")
    manifest.add_argument("--developer-name", help="Publisher/developer display name")
    manifest.add_argument(
        "--compat",
        action="store_true",
        help="Also compile a .codex-plugin/plugin.json compatibility mirror",
    )
    manifest.add_argument("--write", action="store_true", help="Write compiled manifest files to the candidate")
    manifest.add_argument("--force", action="store_true", help="Allow --write to replace differing manifest files")
    manifest.add_argument("--pretty", action="store_true", help="Pretty-print JSON output")

    evals = sub.add_parser("evals", help="Compile submission positive/negative test cases")
    evals.add_argument("path", nargs="?", default=".", help="Candidate directory (default: .)")
    evals.add_argument("--metadata", type=Path, help="JSON eval metadata and reviewer fixtures")
    evals.add_argument(
        "--output",
        default=DEFAULT_OUTPUT,
        help=f"Relative evidence output path (default: {DEFAULT_OUTPUT})",
    )
    evals.add_argument("--write", action="store_true", help="Write the generated eval report")
    evals.add_argument("--force", action="store_true", help="Allow --write to replace a differing eval report")
    evals.add_argument("--pretty", action="store_true", help="Pretty-print JSON output")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "scan":
        return _run_scan(args)
    if args.command == "manifest":
        return _run_manifest(args)
    if args.command == "evals":
        return _run_evals(args)
    return 1


def _run_scan(args: argparse.Namespace) -> int:
    try:
        result = scan_candidate(Path(args.path))
    except ScanError as exc:
        _print_error(str(exc))
        return 1

    _print_json(result, pretty=args.pretty)
    if args.fail_on_not_ready and result["architecture"] == "not_ready":
        return 2
    return 0


def _run_manifest(args: argparse.Namespace) -> int:
    try:
        metadata = load_metadata(args.metadata) if args.metadata else {}
        metadata = _apply_manifest_overrides(metadata, args)
        report = compile_manifest(
            Path(args.path),
            metadata=metadata,
            compatibility=args.compat,
        )
        if args.write:
            report["written"] = write_compiled_manifest(
                Path(args.path),
                report,
                compatibility=args.compat,
                force=args.force,
            )
    except (ManifestError, ScanError) as exc:
        _print_error(str(exc))
        return 1

    _print_json(report, pretty=args.pretty)
    return 0 if report["validation"]["valid"] else 2


def _run_evals(args: argparse.Namespace) -> int:
    try:
        metadata = load_eval_metadata(args.metadata) if args.metadata else {}
        report = compile_submission_evals(Path(args.path), metadata=metadata)
        if args.write:
            report["written"] = write_submission_evals(
                Path(args.path),
                report,
                output=args.output,
                force=args.force,
            )
    except (EvalError, ScanError) as exc:
        _print_error(str(exc))
        return 1

    _print_json(report, pretty=args.pretty)
    return 0 if report["validation"]["valid"] else 2


def _apply_manifest_overrides(metadata: dict, args: argparse.Namespace) -> dict:
    result = dict(metadata)
    direct = {
        "name": args.name,
        "version": args.version,
        "description": args.description,
    }
    for key, value in direct.items():
        if value is not None:
            result[key] = value

    interface = dict(result.get("interface") or {})
    interface_overrides = {
        "displayName": args.display_name,
        "shortDescription": args.short_description,
        "longDescription": args.long_description,
        "developerName": args.developer_name,
    }
    for key, value in interface_overrides.items():
        if value is not None:
            interface[key] = value
    if interface:
        result["interface"] = interface
    return result


def _print_json(value: dict, *, pretty: bool) -> None:
    indent = 2 if pretty else None
    print(json.dumps(value, ensure_ascii=False, indent=indent, sort_keys=True))


def _print_error(message: str) -> None:
    print(json.dumps({"error": message}, ensure_ascii=False), file=sys.stderr)
