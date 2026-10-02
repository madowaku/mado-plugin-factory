from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .bundle import (
    DEFAULT_EVAL_EVIDENCE,
    DEFAULT_INSTALL_EVIDENCE,
    BundleError,
    compile_submission_bundle,
    load_release_metadata,
    write_submission_bundle,
)
from .extensions import (
    DEFAULT_OUTPUT as DEFAULT_EXTENSION_OUTPUT,
    ExtensionError,
    compile_extension_capabilities,
    write_extension_report,
)
from .evals import (
    DEFAULT_OUTPUT,
    EvalError,
    compile_submission_evals,
    load_eval_metadata,
    write_submission_evals,
)
from .manifest import ManifestError, compile_manifest, load_metadata, write_compiled_manifest
from .marketplace import (
    DEFAULT_CACHE_ROOT,
    DEFAULT_EVIDENCE_OUTPUT,
    DEFAULT_MARKETPLACE_DISPLAY_NAME,
    DEFAULT_MARKETPLACE_NAME,
    MarketplaceError,
    compile_marketplace_bridge,
    verify_marketplace_install,
    write_install_evidence,
    write_marketplace_bridge,
)
from .patch import (
    DEFAULT_SCAFFOLD as DEFAULT_PATCH_SCAFFOLD,
    PatchError,
    apply_extension_patch,
    compile_extension_patch,
    public_patch_report,
)
from .scanner import ScanError, scan_candidate
from .scaffold import (
    DEFAULT_OUTPUT as DEFAULT_SCAFFOLD_OUTPUT,
    ScaffoldError,
    compile_extension_scaffold,
    write_extension_scaffold,
    public_scaffold_report,
)


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

    extensions = sub.add_parser("extensions", help="Compile ChatGPT plugin extension capabilities")
    extensions.add_argument("path", nargs="?", default=".", help="Candidate directory (default: .)")
    extensions.add_argument(
        "--output",
        default=DEFAULT_EXTENSION_OUTPUT,
        help=f"Relative evidence output path (default: {DEFAULT_EXTENSION_OUTPUT})",
    )
    extensions.add_argument("--write", action="store_true", help="Write the inspected extension capability report")
    extensions.add_argument("--force", action="store_true", help="Replace a differing extension report")
    extensions.add_argument("--pretty", action="store_true", help="Pretty-print JSON output")

    scaffold = sub.add_parser("scaffold", help="Generate reviewable extension scaffold artifacts")
    scaffold.add_argument("path", nargs="?", default=".", help="Candidate directory (default: .)")
    scaffold.add_argument(
        "--extension",
        action="append",
        dest="extensions",
        help="Extension id to scaffold; repeat to select multiple. Defaults to all actionable capabilities.",
    )
    scaffold.add_argument(
        "--file-extension",
        action="append",
        dest="file_extensions",
        default=[],
        help="File suffix for file_viewer_editor, e.g. .stl; repeat for multiple.",
    )
    scaffold.add_argument(
        "--output",
        default=DEFAULT_SCAFFOLD_OUTPUT,
        help=f"Relative scaffold directory (default: {DEFAULT_SCAFFOLD_OUTPUT})",
    )
    scaffold.add_argument("--write", action="store_true", help="Write the generated scaffold pack")
    scaffold.add_argument("--force", action="store_true", help="Replace differing scaffold files")
    scaffold.add_argument("--pretty", action="store_true", help="Pretty-print JSON output")

    patch = sub.add_parser("patch", help="Plan or apply an extension scaffold pack to active source")
    patch.add_argument("path", nargs="?", default=".", help="Candidate directory (default: .)")
    patch.add_argument(
        "--scaffold",
        default=DEFAULT_PATCH_SCAFFOLD,
        help=f"Relative scaffold directory (default: {DEFAULT_PATCH_SCAFFOLD})",
    )
    patch.add_argument("--apply", action="store_true", help="Apply the inspected patch plan")
    patch.add_argument("--force", action="store_true", help="Replace differing generated source files")
    patch.add_argument(
        "--evidence-output",
        help="Relative executed evidence path; defaults to evidence/patches/extensions/<patch-id>.json",
    )
    patch.add_argument("--pretty", action="store_true", help="Pretty-print JSON output")

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

    marketplace = sub.add_parser("marketplace", help="Bridge and verify local plugin marketplaces")
    marketplace_sub = marketplace.add_subparsers(dest="marketplace_command", required=True)

    bridge = marketplace_sub.add_parser("bridge", help="Compile or write a repo marketplace bridge")
    bridge.add_argument("path", nargs="?", default=".", help="Plugin candidate directory")
    bridge.add_argument(
        "--root",
        type=Path,
        required=True,
        help="Marketplace root containing .agents/plugins/marketplace.json",
    )
    bridge.add_argument(
        "--marketplace-name",
        default=DEFAULT_MARKETPLACE_NAME,
        help=f"Marketplace id (default: {DEFAULT_MARKETPLACE_NAME})",
    )
    bridge.add_argument(
        "--marketplace-display-name",
        default=DEFAULT_MARKETPLACE_DISPLAY_NAME,
        help=f"Marketplace picker label (default: {DEFAULT_MARKETPLACE_DISPLAY_NAME})",
    )
    bridge.add_argument("--category", help="Marketplace category; falls back to plugin metadata")
    bridge.add_argument(
        "--installation",
        default="AVAILABLE",
        choices=["AVAILABLE", "INSTALLED_BY_DEFAULT", "NOT_AVAILABLE"],
    )
    bridge.add_argument(
        "--authentication",
        default="ON_INSTALL",
        choices=["ON_INSTALL", "ON_FIRST_USE", "NONE"],
    )
    bridge.add_argument("--write", action="store_true", help="Stage plugin files and write marketplace.json")
    bridge.add_argument("--force", action="store_true", help="Replace differing staged/catalog files")
    bridge.add_argument("--pretty", action="store_true", help="Pretty-print JSON output")

    verify = marketplace_sub.add_parser("verify", help="Verify the installed ChatGPT/Codex cache copy")
    verify.add_argument("path", nargs="?", default=".", help="Original plugin candidate directory")
    verify.add_argument("--root", type=Path, required=True, help="Marketplace root used by bridge")
    verify.add_argument(
        "--marketplace-name",
        default=DEFAULT_MARKETPLACE_NAME,
        help=f"Marketplace id (default: {DEFAULT_MARKETPLACE_NAME})",
    )
    verify.add_argument(
        "--cache-root",
        type=Path,
        default=Path(DEFAULT_CACHE_ROOT),
        help=f"Installed plugin cache root (default: {DEFAULT_CACHE_ROOT})",
    )
    verify.add_argument("--cache-version", default="local", help="Installed cache version directory")
    verify.add_argument(
        "--evidence-output",
        default=DEFAULT_EVIDENCE_OUTPUT,
        help=f"Relative evidence output path (default: {DEFAULT_EVIDENCE_OUTPUT})",
    )
    verify.add_argument("--write-evidence", action="store_true", help="Write executed verification evidence")
    verify.add_argument("--force", action="store_true", help="Replace differing evidence output")
    verify.add_argument("--pretty", action="store_true", help="Pretty-print JSON output")

    bundle = sub.add_parser("bundle", help="Compile a versioned submission evidence bundle")
    bundle.add_argument("path", nargs="?", default=".", help="Plugin candidate directory")
    bundle.add_argument("--release-metadata", type=Path, help="JSON release/submission attestations")
    bundle.add_argument(
        "--eval-evidence",
        default=DEFAULT_EVAL_EVIDENCE,
        help=f"Relative eval evidence path (default: {DEFAULT_EVAL_EVIDENCE})",
    )
    bundle.add_argument(
        "--install-evidence",
        default=DEFAULT_INSTALL_EVIDENCE,
        help=f"Relative install evidence path (default: {DEFAULT_INSTALL_EVIDENCE})",
    )
    bundle.add_argument(
        "--output",
        help="Relative bundle directory; defaults to evidence/releases/<plugin-version>",
    )
    bundle.add_argument("--write", action="store_true", help="Write bundle files and deterministic plugin ZIP")
    bundle.add_argument("--force", action="store_true", help="Replace differing bundle files")
    bundle.add_argument("--pretty", action="store_true", help="Pretty-print JSON output")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "scan":
        return _run_scan(args)
    if args.command == "extensions":
        return _run_extensions(args)
    if args.command == "scaffold":
        return _run_scaffold(args)
    if args.command == "patch":
        return _run_patch(args)
    if args.command == "manifest":
        return _run_manifest(args)
    if args.command == "evals":
        return _run_evals(args)
    if args.command == "marketplace":
        if args.marketplace_command == "bridge":
            return _run_marketplace_bridge(args)
        if args.marketplace_command == "verify":
            return _run_marketplace_verify(args)
    if args.command == "bundle":
        return _run_bundle(args)
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


def _run_extensions(args: argparse.Namespace) -> int:
    try:
        report = compile_extension_capabilities(Path(args.path))
        if args.write:
            report["written"] = write_extension_report(
                Path(args.path),
                report,
                output=args.output,
                force=args.force,
            )
    except (ExtensionError, ScanError) as exc:
        _print_error(str(exc))
        return 1

    _print_json(report, pretty=args.pretty)
    return 0 if report["summary"]["actionable_count"] > 0 else 2


def _run_scaffold(args: argparse.Namespace) -> int:
    try:
        report = compile_extension_scaffold(
            Path(args.path),
            extensions=args.extensions,
            file_extensions=args.file_extensions,
            output=args.output,
        )
        if args.write:
            report["written"] = write_extension_scaffold(
                Path(args.path),
                report,
                force=args.force,
            )
    except (ScaffoldError, ExtensionError, ScanError) as exc:
        _print_error(str(exc))
        return 1

    _print_json(public_scaffold_report(report), pretty=args.pretty)
    return 0 if report["summary"]["generated_count"] > 0 else 2


def _run_patch(args: argparse.Namespace) -> int:
    try:
        report = compile_extension_patch(
            Path(args.path),
            scaffold=args.scaffold,
        )
        if args.apply:
            report = apply_extension_patch(
                Path(args.path),
                report,
                force=args.force,
                evidence_output=args.evidence_output,
            )
    except (PatchError, ScaffoldError, ExtensionError, ScanError) as exc:
        _print_error(str(exc))
        return 1

    _print_json(public_patch_report(report), pretty=args.pretty)
    if args.apply:
        return 0 if report.get("applied") and report.get("post_apply", {}).get("verified") else 2
    return 0 if report["apply_ready"] else 2


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


def _run_marketplace_bridge(args: argparse.Namespace) -> int:
    try:
        report = compile_marketplace_bridge(
            Path(args.path),
            args.root,
            marketplace_name=args.marketplace_name,
            marketplace_display_name=args.marketplace_display_name,
            category=args.category,
            installation=args.installation,
            authentication=args.authentication,
        )
        if args.write:
            report["written"] = write_marketplace_bridge(
                Path(args.path),
                args.root,
                report,
                force=args.force,
            )
    except MarketplaceError as exc:
        _print_error(str(exc))
        return 1

    _print_json(report, pretty=args.pretty)
    return 0 if report["validation"]["valid"] else 2


def _run_marketplace_verify(args: argparse.Namespace) -> int:
    try:
        report = verify_marketplace_install(
            Path(args.path),
            args.root,
            marketplace_name=args.marketplace_name,
            cache_root=args.cache_root,
            cache_version=args.cache_version,
        )
        if args.write_evidence:
            report["written"] = write_install_evidence(
                Path(args.path),
                report,
                output=args.evidence_output,
                force=args.force,
            )
    except MarketplaceError as exc:
        _print_error(str(exc))
        return 1

    _print_json(report, pretty=args.pretty)
    return 0 if report["install_verified"] else 2


def _run_bundle(args: argparse.Namespace) -> int:
    try:
        metadata = load_release_metadata(args.release_metadata) if args.release_metadata else {}
        report = compile_submission_bundle(
            Path(args.path),
            release_metadata=metadata,
            eval_evidence=args.eval_evidence,
            install_evidence=args.install_evidence,
        )
        if args.write:
            report["written"] = write_submission_bundle(
                Path(args.path),
                report,
                output=args.output,
                force=args.force,
            )
    except (BundleError, ScanError) as exc:
        _print_error(str(exc))
        return 1

    _print_json(report, pretty=args.pretty)
    if report["submission_ready"]:
        return 0
    if report["upload_ready"]:
        return 3
    return 2


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
