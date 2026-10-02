from __future__ import annotations

import hashlib
import io
import json
import re
import zipfile
from copy import deepcopy
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .evals import validate_submission_evals
from .manifest import validate_manifest
from .marketplace import plugin_package_digest, plugin_package_files
from .scanner import scan_candidate

DEFAULT_EVAL_EVIDENCE = "evidence/evals/test-cases.json"
DEFAULT_INSTALL_EVIDENCE = "evidence/marketplace/install-verification.json"
DEFAULT_RELEASES_ROOT = "evidence/releases"

PORTAL_BOOL_FIELDS = (
    "apps_management_write_access",
    "developer_identity_verified",
    "policy_attestations_complete",
    "skill_safety_scan_passed",
)
MCP_BOOL_FIELDS = (
    "domain_verified",
    "tool_scan_current",
    "tool_annotations_reviewed",
    "reviewer_credentials_ready",
)
REVIEW_BOOL_FIELDS = (
    "eval_cases_reviewed",
    "skills_final_tree_tested",
    "listing_reviewed",
)
URL_FIELDS = (
    "website_url",
    "support_url",
    "privacy_policy_url",
    "terms_url",
)
SECRET_KEY_RE = re.compile(
    r"(password|secret|token|api[_-]?key|credential|authorization|bearer)",
    re.I,
)


class BundleError(ValueError):
    pass


def load_release_metadata(path: Path) -> dict[str, Any]:
    path = path.expanduser().resolve()
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BundleError(f"unable to read release metadata from {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise BundleError("release metadata must be a JSON object")
    _reject_secret_keys(value)
    return value


def compile_submission_bundle(
    root: Path,
    *,
    release_metadata: dict[str, Any] | None = None,
    eval_evidence: str = DEFAULT_EVAL_EVIDENCE,
    install_evidence: str = DEFAULT_INSTALL_EVIDENCE,
) -> dict[str, Any]:
    root = root.expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise BundleError(f"candidate path is not a directory: {root}")

    metadata = _normalize_release_metadata(deepcopy(release_metadata or {}))
    scan = scan_candidate(root)
    if scan["architecture"] == "not_ready":
        raise BundleError("candidate has no discoverable Skill or configured MCP server")

    manifest_path = root / "plugin.json"
    manifest = _load_json_object(manifest_path, "plugin manifest")
    manifest_validation = validate_manifest(manifest, root=root)
    interface = _openai_interface(manifest)
    submission_type = (
        "skills_only" if scan["architecture"] == "skills_only" else "with_mcp"
    )

    eval_path = _safe_existing_path(root, eval_evidence, "eval evidence")
    eval_report = _load_optional_json_object(eval_path)
    eval_validation = _validate_eval_report(eval_report)

    install_path = _safe_existing_path(root, install_evidence, "install evidence")
    install_report = _load_optional_json_object(install_path)
    install_validation = _validate_install_report(install_report)

    package_files = plugin_package_files(root)
    package_digest = plugin_package_digest(root)
    version = manifest.get("version")
    name = manifest.get("name")
    if not isinstance(name, str) or not name:
        raise BundleError("plugin manifest must have a non-empty name")
    if not isinstance(version, str) or not version:
        raise BundleError("plugin manifest must have a non-empty version")

    local_blockers: list[str] = []
    submission_blockers: list[str] = []
    warnings: list[dict[str, str]] = []

    if not manifest_validation["valid"]:
        local_blockers.append("manifest_invalid")
    if scan["missing"]:
        hard_missing = [
            item["code"]
            for item in scan["missing"]
            if item.get("code")
            not in {
                "portable_manifest_missing",
                "portable_manifest_schema_missing",
            }
        ]
        if hard_missing:
            local_blockers.append("scanner_requirements_missing")

    if eval_report is None:
        local_blockers.append("eval_evidence_missing")
    elif not eval_validation["valid"]:
        local_blockers.append("eval_evidence_invalid")

    if not metadata["review"]["eval_cases_reviewed"]:
        local_blockers.append("eval_cases_not_reviewed")
    if not metadata["review"]["skills_final_tree_tested"]:
        local_blockers.append("skills_final_tree_not_tested")
    if not metadata["review"]["listing_reviewed"]:
        local_blockers.append("listing_not_reviewed")

    if install_report is None:
        local_blockers.append("install_evidence_missing")
    elif not install_validation["valid"]:
        local_blockers.append("install_evidence_invalid")
    elif not install_validation["install_verified"]:
        local_blockers.append("local_install_not_verified")

    if not metadata["availability"]:
        local_blockers.append("availability_missing")
    if not metadata["release_notes"]:
        local_blockers.append("release_notes_missing")

    starter_prompts = _starter_prompts(interface, metadata)
    if not starter_prompts:
        submission_blockers.append("starter_prompts_missing")

    if not _listing_copy_complete(manifest, interface):
        submission_blockers.append("listing_copy_incomplete")
    if not metadata["listing"]["logo_ready"] and not interface.get("logo"):
        submission_blockers.append("logo_not_ready")

    missing_urls = [
        key for key in URL_FIELDS if not metadata["listing"].get(key)
    ]
    if missing_urls:
        submission_blockers.append("publication_urls_missing")
        warnings.append(
            {
                "code": "publication_urls_missing",
                "message": "Missing publication URLs: " + ", ".join(missing_urls),
            }
        )

    for key in PORTAL_BOOL_FIELDS:
        if not metadata["portal"][key]:
            submission_blockers.append(f"portal_{key}_pending")

    if submission_type == "with_mcp":
        if not metadata["mcp"]["production_url"]:
            submission_blockers.append("mcp_production_url_missing")
        if not metadata["mcp"]["demo_recording_url"]:
            submission_blockers.append("mcp_demo_recording_url_missing")
        for key in MCP_BOOL_FIELDS:
            if not metadata["mcp"][key]:
                submission_blockers.append(f"mcp_{key}_pending")

    if not metadata["policy_attestation_note"]:
        warnings.append(
            {
                "code": "policy_attestation_note_missing",
                "message": (
                    "Add a short policy-attestation note describing what was reviewed "
                    "before final portal submission."
                ),
            }
        )

    local_blockers = _unique(local_blockers)
    submission_blockers = _unique(local_blockers + submission_blockers)
    upload_ready = not local_blockers
    submission_ready = not submission_blockers

    checks = {
        "scanner": {
            "evidence_state": "inspected",
            "architecture": scan["architecture"],
            "risk_flags": scan["risk_flags"],
            "missing": scan["missing"],
            "passed": "scanner_requirements_missing" not in local_blockers,
        },
        "manifest": {
            "evidence_state": "inspected",
            "validation": manifest_validation,
            "passed": manifest_validation["valid"],
        },
        "evals": {
            "evidence_state": (
                "inspected"
                if metadata["review"]["eval_cases_reviewed"] and eval_validation["valid"]
                else "generated"
            ),
            "path": eval_evidence,
            "validation": eval_validation,
            "human_review_attested": metadata["review"]["eval_cases_reviewed"],
            "passed": (
                eval_report is not None
                and eval_validation["valid"]
                and metadata["review"]["eval_cases_reviewed"]
            ),
        },
        "local_install": {
            "evidence_state": (
                "executed"
                if install_report is not None
                and install_report.get("evidence_state") == "executed"
                else "generated"
            ),
            "path": install_evidence,
            "validation": install_validation,
            "passed": install_validation.get("install_verified", False),
        },
        "release": {
            "evidence_state": "inspected",
            "availability_ready": bool(metadata["availability"]),
            "release_notes_ready": bool(metadata["release_notes"]),
            "listing_reviewed": metadata["review"]["listing_reviewed"],
            "skills_final_tree_tested": metadata["review"]["skills_final_tree_tested"],
        },
        "portal": {
            "evidence_state": "inspected",
            "requirements": deepcopy(metadata["portal"]),
            "passed": all(metadata["portal"][key] for key in PORTAL_BOOL_FIELDS),
        },
    }
    if submission_type == "with_mcp":
        checks["mcp"] = {
            "evidence_state": "inspected",
            "production_url": metadata["mcp"]["production_url"],
            "demo_recording_url": metadata["mcp"]["demo_recording_url"],
            "requirements": {
                key: metadata["mcp"][key] for key in MCP_BOOL_FIELDS
            },
            "passed": (
                bool(metadata["mcp"]["production_url"])
                and bool(metadata["mcp"]["demo_recording_url"])
                and all(metadata["mcp"][key] for key in MCP_BOOL_FIELDS)
            ),
        }

    return {
        "schema_version": "0.5",
        "bundle_id": f"{name}@{version}",
        "release_id": version,
        "submission_type": submission_type,
        "plugin": {
            "name": name,
            "version": version,
            "package_files": package_files,
            "package_digest": package_digest,
        },
        "source": {
            "root": str(root),
            "eval_evidence": eval_evidence,
            "install_evidence": install_evidence,
        },
        "release_metadata": metadata,
        "starter_prompts": starter_prompts,
        "checks": checks,
        "upload_ready": upload_ready,
        "submission_ready": submission_ready,
        "blocking_reasons": {
            "upload": local_blockers,
            "submission": submission_blockers,
        },
        "warnings": warnings,
        "artifacts": {
            "default_directory": f"{DEFAULT_RELEASES_ROOT}/{version}",
            "plugin_zip": "plugin.zip",
            "bundle_report": "bundle.json",
            "scanner_report": "scanner.json",
            "manifest_report": "manifest-validation.json",
            "eval_report": "evals.json",
            "install_report": "install-verification.json",
            "release_metadata": "release-metadata.json",
            "package_sha256": "plugin.zip.sha256",
        },
    }


def write_submission_bundle(
    root: Path,
    report: dict[str, Any],
    *,
    output: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    root = root.expanduser().resolve()
    release_id = report.get("release_id")
    if not isinstance(release_id, str) or not release_id:
        raise BundleError("bundle report is missing release_id")

    relative_output = output or f"{DEFAULT_RELEASES_ROOT}/{release_id}"
    bundle_root = _safe_output_path(root, relative_output)
    desired = _bundle_files(root, report)

    if bundle_root.exists() and bundle_root.is_symlink():
        raise BundleError("refusing to write bundle into a symlink directory")

    conflicts: list[str] = []
    for rel, payload in desired.items():
        target = bundle_root / rel
        if target.exists() and target.is_file():
            current = target.read_bytes()
            if current != payload:
                conflicts.append(rel)
        elif target.exists():
            conflicts.append(rel)

    if conflicts and not force:
        raise BundleError(
            "refusing to overwrite differing bundle files without --force: "
            + ", ".join(conflicts)
        )

    bundle_root.mkdir(parents=True, exist_ok=True)
    if force:
        for rel in conflicts:
            target = bundle_root / rel
            if target.is_dir():
                raise BundleError(f"refusing to replace directory with file: {target}")

    written: list[str] = []
    unchanged: list[str] = []
    for rel, payload in desired.items():
        target = bundle_root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and target.read_bytes() == payload:
            unchanged.append(rel)
            continue
        target.write_bytes(payload)
        written.append(rel)

    return {
        "evidence_state": "executed",
        "bundle_root": str(bundle_root),
        "release_id": release_id,
        "written": written,
        "unchanged": unchanged,
        "file_count": len(desired),
        "plugin_zip_sha256": hashlib.sha256(desired["plugin.zip"]).hexdigest(),
    }


def _bundle_files(root: Path, report: dict[str, Any]) -> dict[str, bytes]:
    scan = scan_candidate(root)
    manifest = _load_json_object(root / "plugin.json", "plugin manifest")
    manifest_validation = validate_manifest(manifest, root=root)

    eval_path = _safe_existing_path(
        root,
        report["source"]["eval_evidence"],
        "eval evidence",
    )
    install_path = _safe_existing_path(
        root,
        report["source"]["install_evidence"],
        "install evidence",
    )
    eval_report = _load_optional_json_object(eval_path)
    install_report = _load_optional_json_object(install_path)

    plugin_zip = _deterministic_plugin_zip(root)
    zip_digest = hashlib.sha256(plugin_zip).hexdigest()

    files: dict[str, bytes] = {
        "bundle.json": _json_bytes(report),
        "scanner.json": _json_bytes(scan),
        "manifest-validation.json": _json_bytes(
            {
                "manifest": manifest,
                "validation": manifest_validation,
                "evidence_state": "inspected",
            }
        ),
        "release-metadata.json": _json_bytes(report["release_metadata"]),
        "plugin.zip": plugin_zip,
        "plugin.zip.sha256": (zip_digest + "  plugin.zip\n").encode("utf-8"),
    }
    if eval_report is not None:
        files["evals.json"] = _json_bytes(eval_report)
    if install_report is not None:
        files["install-verification.json"] = _json_bytes(install_report)
    return files


def _deterministic_plugin_zip(root: Path) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(
        buffer,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        for rel in plugin_package_files(root):
            path = root / rel
            if path.is_symlink():
                raise BundleError(f"refusing symlinked plugin content in ZIP: {rel}")
            info = zipfile.ZipInfo(rel)
            info.date_time = (1980, 1, 1, 0, 0, 0)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())
    return buffer.getvalue()


def _normalize_release_metadata(value: dict[str, Any]) -> dict[str, Any]:
    _reject_secret_keys(value)

    availability = value.get("availability", [])
    if availability is None:
        availability = []
    if not isinstance(availability, list) or not all(
        isinstance(item, str) and item.strip() for item in availability
    ):
        raise BundleError("release_metadata.availability must be a list of non-empty strings")

    release_notes = value.get("release_notes", "")
    if release_notes is None:
        release_notes = ""
    if not isinstance(release_notes, str):
        raise BundleError("release_metadata.release_notes must be a string")

    listing_raw = value.get("listing", {})
    review_raw = value.get("review", {})
    portal_raw = value.get("portal", {})
    mcp_raw = value.get("mcp", {})
    for label, raw in (
        ("listing", listing_raw),
        ("review", review_raw),
        ("portal", portal_raw),
        ("mcp", mcp_raw),
    ):
        if raw is None:
            raw = {}
        if not isinstance(raw, dict):
            raise BundleError(f"release_metadata.{label} must be an object")

    listing_raw = listing_raw or {}
    review_raw = review_raw or {}
    portal_raw = portal_raw or {}
    mcp_raw = mcp_raw or {}

    listing = {key: _optional_url(listing_raw.get(key), f"listing.{key}") for key in URL_FIELDS}
    listing["logo_ready"] = _bool(listing_raw.get("logo_ready"), "listing.logo_ready")

    review = {
        key: _bool(review_raw.get(key), f"review.{key}")
        for key in REVIEW_BOOL_FIELDS
    }
    portal = {
        key: _bool(portal_raw.get(key), f"portal.{key}")
        for key in PORTAL_BOOL_FIELDS
    }
    mcp = {
        "production_url": _optional_url(
            mcp_raw.get("production_url"),
            "mcp.production_url",
        ),
        "demo_recording_url": _optional_url(
            mcp_raw.get("demo_recording_url"),
            "mcp.demo_recording_url",
        ),
        **{
            key: _bool(mcp_raw.get(key), f"mcp.{key}")
            for key in MCP_BOOL_FIELDS
        },
    }

    starter_prompts = value.get("starter_prompts", [])
    if starter_prompts is None:
        starter_prompts = []
    if not isinstance(starter_prompts, list) or not all(
        isinstance(item, str) and item.strip() for item in starter_prompts
    ):
        raise BundleError("release_metadata.starter_prompts must be a list of non-empty strings")

    note = value.get("policy_attestation_note", "")
    if note is None:
        note = ""
    if not isinstance(note, str):
        raise BundleError("release_metadata.policy_attestation_note must be a string")

    return {
        "availability": [item.strip() for item in availability],
        "release_notes": release_notes.strip(),
        "starter_prompts": [item.strip() for item in starter_prompts],
        "listing": listing,
        "review": review,
        "portal": portal,
        "mcp": mcp,
        "policy_attestation_note": note.strip(),
    }


def _validate_eval_report(report: dict[str, Any] | None) -> dict[str, Any]:
    if report is None:
        return {
            "valid": False,
            "errors": [{"code": "missing", "message": "eval evidence file is missing"}],
        }
    positive = report.get("positive")
    negative = report.get("negative")
    if not isinstance(positive, list) or not isinstance(negative, list):
        return {
            "valid": False,
            "errors": [
                {
                    "code": "shape_invalid",
                    "message": "eval evidence must contain positive and negative lists",
                }
            ],
        }
    return validate_submission_evals(positive=positive, negative=negative)


def _validate_install_report(report: dict[str, Any] | None) -> dict[str, Any]:
    if report is None:
        return {
            "valid": False,
            "install_verified": False,
            "errors": [{"code": "missing", "message": "install evidence file is missing"}],
        }
    executed = report.get("evidence_state") == "executed"
    verified = report.get("install_verified") is True
    errors: list[dict[str, str]] = []
    if not executed:
        errors.append(
            {
                "code": "not_executed",
                "message": "install evidence must have evidence_state=executed",
            }
        )
    if not isinstance(report.get("blocking_reasons", []), list):
        errors.append(
            {
                "code": "blocking_reasons_invalid",
                "message": "install evidence blocking_reasons must be a list",
            }
        )
    return {
        "valid": executed and not errors,
        "install_verified": executed and verified and not errors,
        "errors": errors,
        "blocking_reasons": report.get("blocking_reasons", []),
    }


def _starter_prompts(interface: dict[str, Any], metadata: dict[str, Any]) -> list[str]:
    manifest_prompts = interface.get("defaultPrompt")
    result: list[str] = []
    if isinstance(manifest_prompts, list):
        result.extend(
            item.strip()
            for item in manifest_prompts
            if isinstance(item, str) and item.strip()
        )
    result.extend(metadata["starter_prompts"])
    return _unique(result)


def _listing_copy_complete(manifest: dict[str, Any], interface: dict[str, Any]) -> bool:
    return all(
        isinstance(value, str) and value.strip()
        for value in (
            manifest.get("name"),
            interface.get("displayName"),
            interface.get("shortDescription"),
            interface.get("longDescription"),
            interface.get("category"),
        )
    )


def _openai_interface(manifest: dict[str, Any]) -> dict[str, Any]:
    extensions = manifest.get("extensions")
    if not isinstance(extensions, dict):
        return {}
    openai_extension = extensions.get("com.openai")
    if not isinstance(openai_extension, dict):
        return {}
    interface = openai_extension.get("interface")
    return interface if isinstance(interface, dict) else {}


def _safe_existing_path(root: Path, relative: str, label: str) -> Path:
    if not isinstance(relative, str) or not relative.strip():
        raise BundleError(f"{label} path must be a non-empty relative path")
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise BundleError(f"{label} path must stay inside the plugin root")
    target = (root / candidate).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise BundleError(f"{label} path must stay inside the plugin root") from exc
    return target


def _safe_output_path(root: Path, relative: str) -> Path:
    return _safe_existing_path(root, relative, "bundle output")


def _load_optional_json_object(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    return _load_json_object(path, "evidence file")


def _load_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BundleError(f"unable to read {label} at {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise BundleError(f"{label} at {path} must be a JSON object")
    return value


def _optional_url(value: Any, label: str) -> str:
    if value in (None, ""):
        return ""
    if not isinstance(value, str):
        raise BundleError(f"{label} must be an HTTPS URL when provided")
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise BundleError(f"{label} must be a public HTTPS URL when provided")
    if len(value) > 1024:
        raise BundleError(f"{label} must be 1024 characters or fewer")
    return value


def _bool(value: Any, label: str) -> bool:
    if value is None:
        return False
    if not isinstance(value, bool):
        raise BundleError(f"{label} must be true or false")
    return value


def _reject_secret_keys(value: Any, *, path: str = "release_metadata") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if SECRET_KEY_RE.search(str(key)):
                raise BundleError(
                    f"{path}.{key} looks secret-bearing; do not store credentials in release metadata"
                )
            _reject_secret_keys(child, path=f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_secret_keys(child, path=f"{path}[{index}]")


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=False) + "\n"
    ).encode("utf-8")


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result
