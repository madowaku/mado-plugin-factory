from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from .runtime import RuntimeSmokeError, run_extension_runtime_smoke

SCHEMA_VERSION = "0.1"
DEFAULT_EVIDENCE_DIR = "evidence/freshness/extensions"


class FreshnessError(ValueError):
    pass


def run_verification_freshness(
    root: Path,
    *,
    verification_evidence: str,
    server: str | None = None,
    mode: str = "auto",
    timeout: float = 5.0,
    write_evidence: bool = False,
    evidence_output: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    root = root.expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise FreshnessError(f"candidate path is not a directory: {root}")

    dossier_path = _safe_existing_file(
        root,
        verification_evidence,
        label="verification dossier",
    )
    dossier = _load_json_object(
        dossier_path,
        "verification dossier",
    )
    runtime_path = _runtime_artifact_path(root, dossier)
    baseline_runtime = _load_json_object(
        runtime_path,
        "verification runtime artifact",
    )
    _validate_runtime_artifact_binding(
        dossier,
        baseline_runtime,
    )

    baseline_fingerprint = baseline_runtime.get(
        "runtime_fingerprint"
    )
    baseline_fp_sha = (
        baseline_fingerprint.get("sha256")
        if isinstance(baseline_fingerprint, dict)
        else None
    )
    baseline_components = (
        baseline_fingerprint.get("components")
        if isinstance(baseline_fingerprint, dict)
        else None
    )
    if not isinstance(baseline_components, dict):
        baseline_components = {}

    baseline_source = baseline_runtime.get("source")
    if not isinstance(baseline_source, dict):
        baseline_source = {}
    baseline_server = baseline_source.get("server")
    if not isinstance(baseline_server, str) or not baseline_server:
        raise FreshnessError(
            "verification runtime artifact is missing source.server"
        )
    selected_server = server or baseline_server
    if selected_server != baseline_server:
        raise FreshnessError(
            "freshness must probe the same MCP server recorded by verification"
        )

    probe_error: str | None = None
    current_runtime: dict[str, Any] | None = None
    try:
        current_runtime = run_extension_runtime_smoke(
            root,
            server=selected_server,
            mode=mode,
            timeout=timeout,
            write_evidence=False,
        )
    except RuntimeSmokeError as exc:
        probe_error = str(exc)

    current_fingerprint = (
        current_runtime.get("runtime_fingerprint")
        if isinstance(current_runtime, dict)
        else None
    )
    current_fp_sha = (
        current_fingerprint.get("sha256")
        if isinstance(current_fingerprint, dict)
        else None
    )
    current_components = (
        current_fingerprint.get("components")
        if isinstance(current_fingerprint, dict)
        else None
    )
    if not isinstance(current_components, dict):
        current_components = {}

    blockers: list[str] = []
    if not isinstance(baseline_fp_sha, str) or not baseline_fp_sha:
        blockers.append("baseline_runtime_fingerprint_missing")
    if probe_error:
        blockers.append("freshness_probe_error")
    elif not current_runtime.get("runtime_smoke_passed"):
        blockers.append("current_runtime_smoke_failed")
    if (
        isinstance(baseline_fp_sha, str)
        and baseline_fp_sha
        and isinstance(current_fp_sha, str)
        and current_fp_sha
        and baseline_fp_sha != current_fp_sha
    ):
        blockers.append("remote_mcp_surface_drift")
    if current_runtime is not None and not isinstance(
        current_fp_sha,
        str,
    ):
        blockers.append("current_runtime_fingerprint_missing")

    changed_components = sorted(
        key.removesuffix("_sha256")
        for key in {
            *baseline_components.keys(),
            *current_components.keys(),
        }
        if baseline_components.get(key)
        != current_components.get(key)
    )

    baseline_observations = baseline_runtime.get("observations")
    current_observations = (
        current_runtime.get("observations")
        if isinstance(current_runtime, dict)
        else None
    )
    if not isinstance(baseline_observations, dict):
        baseline_observations = {}
    if not isinstance(current_observations, dict):
        current_observations = {}

    baseline_tools = set(
        item
        for item in baseline_observations.get(
            "tool_names",
            [],
        )
        if isinstance(item, str)
    )
    current_tools = set(
        item
        for item in current_observations.get(
            "tool_names",
            [],
        )
        if isinstance(item, str)
    )
    baseline_resources = set(
        item
        for item in baseline_observations.get(
            "resource_uris",
            [],
        )
        if isinstance(item, str)
    )
    current_resources = set(
        item
        for item in current_observations.get(
            "resource_uris",
            [],
        )
        if isinstance(item, str)
    )

    fingerprint_matches = bool(
        isinstance(baseline_fp_sha, str)
        and baseline_fp_sha
        and isinstance(current_fp_sha, str)
        and current_fp_sha
        and baseline_fp_sha == current_fp_sha
    )
    freshness_verified = bool(
        fingerprint_matches
        and current_runtime is not None
        and current_runtime.get("runtime_smoke_passed")
        and not probe_error
    )

    dossier_sha256 = hashlib.sha256(
        dossier_path.read_bytes()
    ).hexdigest()
    freshness_id = _freshness_id(
        dossier_sha256=dossier_sha256,
        baseline_fingerprint=baseline_fp_sha,
        current_fingerprint=current_fp_sha,
        blockers=blockers,
    )

    report = {
        "schema_version": SCHEMA_VERSION,
        "evidence_state": "executed",
        "freshness_id": freshness_id,
        "freshness_verified": freshness_verified,
        "verification": {
            "path": verification_evidence,
            "dossier_sha256": dossier_sha256,
            "verification_id": dossier.get(
                "verification_id"
            ),
            "verification_state": dossier.get(
                "verification_state"
            ),
            "verification_verified": dossier.get(
                "verification_verified"
            ) is True,
        },
        "server": {
            "name": baseline_server,
            "transport": baseline_source.get(
                "transport"
            ),
        },
        "baseline": {
            "smoke_id": baseline_runtime.get(
                "smoke_id"
            ),
            "runtime_fingerprint": deepcopy(
                baseline_fingerprint
            )
            if isinstance(baseline_fingerprint, dict)
            else None,
        },
        "current": {
            "probe_error": probe_error,
            "smoke_id": (
                current_runtime.get("smoke_id")
                if current_runtime
                else None
            ),
            "runtime_smoke_passed": bool(
                current_runtime
                and current_runtime.get(
                    "runtime_smoke_passed"
                )
            ),
            "runtime_fingerprint": deepcopy(
                current_fingerprint
            )
            if isinstance(current_fingerprint, dict)
            else None,
        },
        "drift": {
            "fingerprint_matches": fingerprint_matches,
            "changed_components": changed_components,
            "tools_added": sorted(
                current_tools - baseline_tools
            ),
            "tools_removed": sorted(
                baseline_tools - current_tools
            ),
            "resources_added": sorted(
                current_resources - baseline_resources
            ),
            "resources_removed": sorted(
                baseline_resources - current_resources
            ),
        },
        "blocking_reasons": list(
            dict.fromkeys(blockers)
        ),
        "scope": "advertised_mcp_surface",
        "warnings": [
            (
                "Freshness compares advertised MCP protocol/capabilities, "
                "tool descriptors, and referenced resource content digests. "
                "It does not prove unchanged tool behavior or authorization enforcement."
            ),
            (
                "serverInfo is observational metadata and is intentionally "
                "excluded from the freshness fingerprint."
            ),
        ],
    }

    if write_evidence:
        output = evidence_output or (
            f"{DEFAULT_EVIDENCE_DIR}/{freshness_id}.json"
        )
        report["evidence_output"] = _write_evidence(
            root,
            report,
            output=output,
            force=force,
        )
    return report


def _runtime_artifact_path(
    root: Path,
    dossier: dict[str, Any],
) -> Path:
    artifacts = dossier.get("artifacts")
    if not isinstance(artifacts, dict):
        raise FreshnessError(
            "verification dossier is missing artifacts"
        )
    runtime = artifacts.get("runtime")
    if not isinstance(runtime, str) or not runtime:
        raise FreshnessError(
            "verification dossier is missing runtime artifact"
        )
    return _safe_existing_file(
        root,
        runtime,
        label="verification runtime artifact",
    )


def _validate_runtime_artifact_binding(
    dossier: dict[str, Any],
    runtime: dict[str, Any],
) -> None:
    stages = dossier.get("stages")
    if not isinstance(stages, dict):
        raise FreshnessError(
            "verification dossier is missing stages"
        )
    stage = stages.get("runtime_smoke")
    if not isinstance(stage, dict):
        raise FreshnessError(
            "verification dossier is missing runtime_smoke stage"
        )
    expected = stage.get("sha256")
    if not isinstance(expected, str) or not expected:
        raise FreshnessError(
            "verification dossier runtime stage has no SHA-256 binding"
        )
    actual = _json_digest(runtime)
    if actual != expected:
        raise FreshnessError(
            "verification runtime artifact digest does not match dossier"
        )


def _freshness_id(
    *,
    dossier_sha256: str,
    baseline_fingerprint: Any,
    current_fingerprint: Any,
    blockers: list[str],
) -> str:
    payload = {
        "dossier_sha256": dossier_sha256,
        "baseline_fingerprint": baseline_fingerprint,
        "current_fingerprint": current_fingerprint,
        "blockers": blockers,
    }
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()[:20]


def _write_evidence(
    root: Path,
    report: dict[str, Any],
    *,
    output: str,
    force: bool,
) -> str:
    target = _safe_relative(
        root,
        output,
        label="freshness evidence output",
    )
    _reject_symlink_target(root, target)
    rendered = _json_text(report)
    if target.exists():
        if not target.is_file():
            raise FreshnessError(
                f"freshness evidence target is not a file: {target}"
            )
        current = target.read_text(encoding="utf-8")
        if current != rendered and not force:
            raise FreshnessError(
                f"freshness evidence differs at {target}; use --force to replace it"
            )
    target.parent.mkdir(parents=True, exist_ok=True)
    if (
        not target.exists()
        or target.read_text(encoding="utf-8")
        != rendered
    ):
        target.write_text(rendered, encoding="utf-8")
    return target.relative_to(root).as_posix()


def _safe_existing_file(
    root: Path,
    value: str,
    *,
    label: str,
) -> Path:
    target = _safe_relative(
        root,
        value,
        label=label,
    )
    if not target.is_file() or target.is_symlink():
        raise FreshnessError(
            f"{label} does not exist: {target}"
        )
    return target


def _safe_relative(
    root: Path,
    value: str,
    *,
    label: str,
) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise FreshnessError(
            f"{label} must be a non-empty relative path"
        )
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise FreshnessError(
            f"{label} must stay inside the plugin root"
        )
    target = (root / candidate).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise FreshnessError(
            f"{label} must stay inside the plugin root"
        ) from exc
    return target


def _reject_symlink_target(
    root: Path,
    target: Path,
) -> None:
    rel = target.relative_to(root)
    current = root
    for part in rel.parts:
        current = current / part
        if current.exists() and current.is_symlink():
            raise FreshnessError(
                f"refusing symlinked freshness evidence target: {current}"
            )


def _load_json_object(
    path: Path,
    label: str,
) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8")
        )
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as exc:
        raise FreshnessError(
            f"unable to read {label} at {path}: {exc}"
        ) from exc
    if not isinstance(value, dict):
        raise FreshnessError(
            f"{label} at {path} must be a JSON object"
        )
    return value


def _json_digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _json_text(value: Any) -> str:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
