from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from .behavior import CanaryError, run_behavior_canary
from .bundle import (
    DEFAULT_EVAL_EVIDENCE,
    DEFAULT_INSTALL_EVIDENCE,
    BundleError,
    compile_submission_bundle,
    write_submission_bundle,
)
from .credentials import CredentialMatrixError, run_credential_matrix
from .freshness import FreshnessError, run_verification_freshness
from .marketplace import plugin_package_digest
from .negative import NegativeContractError, run_negative_contract
from .security import SecuritySchemeGateError, run_security_scheme_gate

SCHEMA_VERSION = "0.1"
DEFAULT_VERIFICATIONS_ROOT = "evidence/verifications/extensions"
VALID_REQUIREMENTS = {"auto", "mcp_server", "chatgpt_host"}


class PromotionError(ValueError):
    pass


def run_verification_promotion(
    root: Path,
    *,
    release_metadata: dict[str, Any] | None = None,
    verification_evidence: str,
    requirement: str = "auto",
    eval_evidence: str = DEFAULT_EVAL_EVIDENCE,
    install_evidence: str = DEFAULT_INSTALL_EVIDENCE,
    server: str | None = None,
    runtime_mode: str = "auto",
    timeout: float = 5.0,
    canary_contract: str | None = None,
    canary_baseline: str | None = None,
    negative_contract: str | None = None,
    negative_baseline: str | None = None,
    credential_matrix: str | None = None,
    credential_baseline: str | None = None,
    security_contract: str | None = None,
) -> dict[str, Any]:
    if bool(canary_contract) != bool(canary_baseline):
        raise PromotionError(
            "behavior canary promotion requires both canary_contract and canary_baseline"
        )
    if bool(negative_contract) != bool(negative_baseline):
        raise PromotionError(
            "negative contract promotion requires both negative_contract and negative_baseline"
        )
    if bool(credential_matrix) != bool(credential_baseline):
        raise PromotionError(
            "credential matrix promotion requires both credential_matrix and credential_baseline"
        )
    if security_contract and not (credential_matrix and credential_baseline):
        raise PromotionError(
            "security scheme promotion requires credential_matrix and credential_baseline"
        )

    try:
        freshness = run_verification_freshness(
            root,
            verification_evidence=verification_evidence,
            server=server,
            mode=runtime_mode,
            timeout=timeout,
            write_evidence=False,
        )
    except FreshnessError as exc:
        raise PromotionError(str(exc)) from exc

    behavior = None
    baseline_payload = None
    if canary_contract and canary_baseline:
        try:
            behavior = run_behavior_canary(
                root,
                contract=canary_contract,
                baseline_evidence=canary_baseline,
                verification_evidence=verification_evidence,
                server=server,
                mode=runtime_mode,
                timeout=timeout,
                write_evidence=False,
            )
            baseline_path = _safe_existing_file(
                root,
                canary_baseline,
                label="canary baseline evidence",
            )
            baseline_payload = _load_json_object(
                baseline_path,
                "canary baseline evidence",
            )
        except CanaryError as exc:
            raise PromotionError(str(exc)) from exc

    negative = None
    negative_baseline_payload = None
    if negative_contract and negative_baseline:
        try:
            negative = run_negative_contract(
                root,
                contract=negative_contract,
                baseline_evidence=negative_baseline,
                verification_evidence=verification_evidence,
                server=server,
                mode=runtime_mode,
                timeout=timeout,
                write_evidence=False,
            )
            negative_baseline_path = _safe_existing_file(
                root,
                negative_baseline,
                label="negative baseline evidence",
            )
            negative_baseline_payload = _load_json_object(
                negative_baseline_path,
                "negative baseline evidence",
            )
        except NegativeContractError as exc:
            raise PromotionError(str(exc)) from exc

    credential_report = None
    credential_baseline_payload = None
    if credential_matrix and credential_baseline:
        try:
            credential_report = run_credential_matrix(
                root,
                contract=credential_matrix,
                baseline_evidence=credential_baseline,
                verification_evidence=verification_evidence,
                server=server,
                mode=runtime_mode,
                timeout=timeout,
                write_evidence=False,
            )
            credential_baseline_path = _safe_existing_file(
                root,
                credential_baseline,
                label="credential matrix baseline",
            )
            credential_baseline_payload = _load_json_object(
                credential_baseline_path,
                "credential matrix baseline",
            )
        except CredentialMatrixError as exc:
            raise PromotionError(str(exc)) from exc

    security_report = None
    if security_contract:
        try:
            security_report = run_security_scheme_gate(
                root,
                contract=security_contract,
                matrix_report=credential_report,
                server=server,
                mode=runtime_mode,
                timeout=timeout,
                write_evidence=False,
            )
        except SecuritySchemeGateError as exc:
            raise PromotionError(str(exc)) from exc

    return compile_verification_promotion(
        root,
        release_metadata=release_metadata,
        verification_evidence=verification_evidence,
        requirement=requirement,
        eval_evidence=eval_evidence,
        install_evidence=install_evidence,
        freshness_report=freshness,
        enforce_freshness=True,
        behavior_report=behavior,
        enforce_behavior=bool(behavior),
        canary_baseline_payload=baseline_payload,
        negative_report=negative,
        enforce_negative=bool(negative),
        negative_baseline_payload=negative_baseline_payload,
        credential_report=credential_report,
        enforce_credentials=bool(credential_report),
        credential_baseline_payload=credential_baseline_payload,
        security_report=security_report,
        enforce_security=bool(security_report),
    )


def compile_verification_promotion(
    root: Path,
    *,
    release_metadata: dict[str, Any] | None = None,
    verification_evidence: str,
    requirement: str = "auto",
    eval_evidence: str = DEFAULT_EVAL_EVIDENCE,
    install_evidence: str = DEFAULT_INSTALL_EVIDENCE,
    freshness_report: dict[str, Any] | None = None,
    enforce_freshness: bool = False,
    behavior_report: dict[str, Any] | None = None,
    enforce_behavior: bool = False,
    canary_baseline_payload: dict[str, Any] | None = None,
    negative_report: dict[str, Any] | None = None,
    enforce_negative: bool = False,
    negative_baseline_payload: dict[str, Any] | None = None,
    credential_report: dict[str, Any] | None = None,
    enforce_credentials: bool = False,
    credential_baseline_payload: dict[str, Any] | None = None,
    security_report: dict[str, Any] | None = None,
    enforce_security: bool = False,
) -> dict[str, Any]:
    root = root.expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise PromotionError(f"candidate path is not a directory: {root}")
    if requirement not in VALID_REQUIREMENTS:
        raise PromotionError(
            "verification requirement must be auto, mcp_server, or chatgpt_host"
        )

    verification_path = _safe_existing_file(
        root,
        verification_evidence,
        label="verification dossier",
    )
    dossier = _load_json_object(
        verification_path,
        "verification dossier",
    )
    validation = _validate_verification_dossier(
        root,
        verification_path,
        dossier,
    )

    current_package_digest = plugin_package_digest(root)
    verified_package_digest = (
        dossier.get("source", {}).get("plugin_package_digest")
        if isinstance(dossier.get("source"), dict)
        else None
    )
    package_bound = bool(
        isinstance(verified_package_digest, str)
        and verified_package_digest
        and verified_package_digest == current_package_digest
    )

    resolved_requirement = _resolve_requirement(
        dossier,
        requirement,
    )
    state = dossier.get("verification_state")
    verification_verified = dossier.get(
        "verification_verified"
    ) is True

    state_satisfies = _state_satisfies(
        state,
        resolved_requirement,
    )

    dossier_sha256 = hashlib.sha256(
        verification_path.read_bytes()
    ).hexdigest()
    freshness_valid = True
    freshness_summary: dict[str, Any] | None = None
    if enforce_freshness:
        freshness_valid = False
        if isinstance(freshness_report, dict):
            fresh_verification = freshness_report.get("verification")
            fresh_dossier_sha = (
                fresh_verification.get("dossier_sha256")
                if isinstance(fresh_verification, dict)
                else None
            )
            freshness_valid = bool(
                freshness_report.get("freshness_verified")
                and fresh_dossier_sha == dossier_sha256
            )
            freshness_summary = {
                "freshness_id": freshness_report.get("freshness_id"),
                "freshness_verified": freshness_report.get("freshness_verified") is True,
                "dossier_sha256_matches": fresh_dossier_sha == dossier_sha256,
                "blocking_reasons": freshness_report.get("blocking_reasons") or [],
                "drift": deepcopy(freshness_report.get("drift") or {}),
                "scope": freshness_report.get("scope"),
            }

    behavior_valid = True
    behavior_summary: dict[str, Any] | None = None
    if enforce_behavior:
        behavior_valid = bool(
            isinstance(behavior_report, dict)
            and behavior_report.get("mode") == "replay"
            and behavior_report.get("canary_verified") is True
        )
        if isinstance(behavior_report, dict):
            behavior_summary = {
                "canary_id": behavior_report.get("canary_id"),
                "canary_verified": behavior_report.get("canary_verified") is True,
                "canary_passed": behavior_report.get("canary_passed") is True,
                "blocking_reasons": behavior_report.get("blocking_reasons") or [],
                "scope": behavior_report.get("scope"),
                "contract": deepcopy(behavior_report.get("contract") or {}),
                "baseline": deepcopy(behavior_report.get("baseline") or {}),
            }

    negative_valid = True
    negative_summary: dict[str, Any] | None = None
    if enforce_negative:
        negative_valid = bool(
            isinstance(negative_report, dict)
            and negative_report.get("mode") == "replay"
            and negative_report.get("negative_verified") is True
        )
        if isinstance(negative_report, dict):
            negative_summary = {
                "negative_id": negative_report.get("negative_id"),
                "negative_verified": negative_report.get("negative_verified") is True,
                "negative_passed": negative_report.get("negative_passed") is True,
                "blocking_reasons": negative_report.get("blocking_reasons") or [],
                "scope": negative_report.get("scope"),
                "contract": deepcopy(negative_report.get("contract") or {}),
                "baseline": deepcopy(negative_report.get("baseline") or {}),
            }

    credential_valid = True
    credential_summary: dict[str, Any] | None = None
    if enforce_credentials:
        credential_valid = bool(
            isinstance(credential_report, dict)
            and credential_report.get("mode") == "replay"
            and credential_report.get("matrix_verified") is True
        )
        if isinstance(credential_report, dict):
            credential_summary = {
                "matrix_id": credential_report.get("matrix_id"),
                "matrix_verified": credential_report.get("matrix_verified") is True,
                "matrix_passed": credential_report.get("matrix_passed") is True,
                "blocking_reasons": credential_report.get("blocking_reasons") or [],
                "scope": credential_report.get("scope"),
                "contract": deepcopy(credential_report.get("contract") or {}),
                "baseline": deepcopy(credential_report.get("baseline") or {}),
            }

    security_valid = True
    security_summary: dict[str, Any] | None = None
    if enforce_security:
        security_valid = bool(
            isinstance(security_report, dict)
            and security_report.get("gate_passed") is True
        )
        if isinstance(security_report, dict):
            security_summary = {
                "gate_id": security_report.get("gate_id"),
                "gate_passed": security_report.get("gate_passed") is True,
                "blocking_reasons": security_report.get("blocking_reasons") or [],
                "scope": security_report.get("scope"),
                "contract": deepcopy(security_report.get("contract") or {}),
                "matrix": deepcopy(security_report.get("matrix") or {}),
            }

    gate_passed = bool(
        validation["valid"]
        and package_bound
        and verification_verified
        and state_satisfies
        and freshness_valid
        and behavior_valid
        and negative_valid
        and credential_valid
        and security_valid
    )

    verification_blockers: list[str] = []
    if not validation["valid"]:
        verification_blockers.extend(
            validation["blocking_reasons"]
        )
    if not isinstance(verified_package_digest, str) or not verified_package_digest:
        verification_blockers.append(
            "verification_package_digest_missing"
        )
    elif not package_bound:
        verification_blockers.append(
            "verification_package_digest_mismatch"
        )
    if not verification_verified:
        verification_blockers.append(
            "verification_not_verified"
        )
    if not state_satisfies:
        verification_blockers.append(
            f"verification_requirement_{resolved_requirement}_not_satisfied"
        )
    if enforce_freshness:
        if not isinstance(freshness_report, dict):
            verification_blockers.append(
                "verification_freshness_missing"
            )
        elif not freshness_report.get("freshness_verified"):
            verification_blockers.append(
                "verification_freshness_stale"
            )
        else:
            fresh_verification = freshness_report.get("verification")
            fresh_dossier_sha = (
                fresh_verification.get("dossier_sha256")
                if isinstance(fresh_verification, dict)
                else None
            )
            if fresh_dossier_sha != dossier_sha256:
                verification_blockers.append(
                    "verification_freshness_dossier_mismatch"
                )
    if enforce_behavior:
        if not isinstance(behavior_report, dict):
            verification_blockers.append(
                "verification_behavior_canary_missing"
            )
        elif not behavior_report.get("canary_verified"):
            verification_blockers.append(
                "verification_behavior_canary_stale"
            )
    if enforce_negative:
        if not isinstance(negative_report, dict):
            verification_blockers.append(
                "verification_negative_contract_missing"
            )
        elif not negative_report.get("negative_verified"):
            verification_blockers.append(
                "verification_negative_contract_stale"
            )
    if enforce_credentials:
        if not isinstance(credential_report, dict):
            verification_blockers.append(
                "verification_credential_matrix_missing"
            )
        elif not credential_report.get("matrix_verified"):
            verification_blockers.append(
                "verification_credential_matrix_stale"
            )
    if enforce_security:
        if not isinstance(security_report, dict):
            verification_blockers.append(
                "verification_security_scheme_missing"
            )
        elif not security_report.get("gate_passed"):
            verification_blockers.append(
                "verification_security_scheme_contract_failed"
            )
    verification_blockers = _unique(verification_blockers)

    try:
        bundle = compile_submission_bundle(
            root,
            release_metadata=release_metadata,
            eval_evidence=eval_evidence,
            install_evidence=install_evidence,
        )
    except BundleError as exc:
        raise PromotionError(str(exc)) from exc

    if bundle["submission_type"] != "with_mcp":
        raise PromotionError(
            "extension verification promotion requires a plugin with MCP"
        )

    promotion_id = _promotion_id(
        bundle_id=bundle["bundle_id"],
        package_digest=current_package_digest,
        dossier_sha256=dossier_sha256,
        requirement=resolved_requirement,
        freshness_id=(
            freshness_report.get("freshness_id")
            if isinstance(freshness_report, dict)
            else None
        ),
        canary_id=(
            behavior_report.get("canary_id")
            if isinstance(behavior_report, dict)
            else None
        ),
        negative_id=(
            negative_report.get("negative_id")
            if isinstance(negative_report, dict)
            else None
        ),
        matrix_id=(
            credential_report.get("matrix_id")
            if isinstance(credential_report, dict)
            else None
        ),
        security_gate_id=(
            security_report.get("gate_id")
            if isinstance(security_report, dict)
            else None
        ),
    )

    promotion_ready = bool(
        bundle["submission_ready"]
        and gate_passed
    )
    promotion_blockers = _unique(
        list(bundle["blocking_reasons"]["submission"])
        + verification_blockers
    )

    verification_check = {
        "evidence_state": "inspected",
        "path": verification_evidence,
        "dossier_sha256": dossier_sha256,
        "verification_id": dossier.get(
            "verification_id"
        ),
        "verification_state": state,
        "verification_verified": verification_verified,
        "requirement_requested": requirement,
        "requirement_resolved": resolved_requirement,
        "state_satisfies_requirement": state_satisfies,
        "package_digest_verified": verified_package_digest,
        "package_digest_current": current_package_digest,
        "package_digest_matches": package_bound,
        "artifact_integrity": validation,
        "freshness_required": enforce_freshness,
        "freshness": freshness_summary,
        "behavior_canary_required": enforce_behavior,
        "behavior_canary": behavior_summary,
        "negative_contract_required": enforce_negative,
        "negative_contract": negative_summary,
        "credential_matrix_required": enforce_credentials,
        "credential_matrix": credential_summary,
        "security_scheme_required": enforce_security,
        "security_scheme": security_summary,
        "passed": gate_passed,
    }

    promoted_bundle = deepcopy(bundle)
    promoted_bundle["source"][
        "verification_evidence"
    ] = verification_evidence
    promoted_bundle["checks"][
        "extension_verification"
    ] = verification_check
    promoted_bundle["promotion"] = {
        "promotion_id": promotion_id,
        "promotion_ready": promotion_ready,
        "requirement": resolved_requirement,
        "verification_gate_passed": gate_passed,
        "base_submission_ready": bundle[
            "submission_ready"
        ],
        "blocking_reasons": promotion_blockers,
    }
    promoted_bundle["artifacts"][
        "promotion_report"
    ] = "promotion.json"
    promoted_bundle["artifacts"][
        "verification_directory"
    ] = "verification"
    if enforce_freshness:
        promoted_bundle["artifacts"][
            "freshness_report"
        ] = "verification/freshness.json"
    if enforce_behavior:
        promoted_bundle["artifacts"][
            "canary_replay"
        ] = "verification/canary-replay.json"
        promoted_bundle["artifacts"][
            "canary_baseline"
        ] = "verification/canary-baseline.json"
    if enforce_negative:
        promoted_bundle["artifacts"][
            "negative_replay"
        ] = "verification/negative-replay.json"
        promoted_bundle["artifacts"][
            "negative_baseline"
        ] = "verification/negative-baseline.json"
    if enforce_credentials:
        promoted_bundle["artifacts"][
            "credential_matrix_replay"
        ] = "verification/credential-matrix-replay.json"
        promoted_bundle["artifacts"][
            "credential_matrix_baseline"
        ] = "verification/credential-matrix-baseline.json"
    if enforce_security:
        promoted_bundle["artifacts"][
            "security_scheme_gate"
        ] = "verification/security-scheme-gate.json"

    return {
        "schema_version": SCHEMA_VERSION,
        "evidence_state": "inspected",
        "promotion_id": promotion_id,
        "promotion_ready": promotion_ready,
        "requirement": {
            "requested": requirement,
            "resolved": resolved_requirement,
        },
        "plugin": {
            "bundle_id": bundle["bundle_id"],
            "release_id": bundle["release_id"],
            "package_digest": current_package_digest,
        },
        "verification": verification_check,
        "release": {
            "upload_ready": bundle["upload_ready"],
            "submission_ready": bundle[
                "submission_ready"
            ],
        },
        "blocking_reasons": promotion_blockers,
        "bundle": promoted_bundle,
        "source": {
            "verification_evidence": verification_evidence,
        },
        "_verification_dossier": dossier,
        "_verification_artifacts": validation[
            "artifact_payloads"
        ],
        "_freshness_report": deepcopy(freshness_report)
        if isinstance(freshness_report, dict)
        else None,
        "_behavior_report": deepcopy(behavior_report)
        if isinstance(behavior_report, dict)
        else None,
        "_canary_baseline": deepcopy(canary_baseline_payload)
        if isinstance(canary_baseline_payload, dict)
        else None,
        "_negative_report": deepcopy(negative_report)
        if isinstance(negative_report, dict)
        else None,
        "_negative_baseline": deepcopy(negative_baseline_payload)
        if isinstance(negative_baseline_payload, dict)
        else None,
        "_credential_report": deepcopy(credential_report)
        if isinstance(credential_report, dict)
        else None,
        "_credential_baseline": deepcopy(credential_baseline_payload)
        if isinstance(credential_baseline_payload, dict)
        else None,
        "_security_report": deepcopy(security_report)
        if isinstance(security_report, dict)
        else None,
    }


def write_promoted_release(
    root: Path,
    report: dict[str, Any],
    *,
    output: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    root = root.expanduser().resolve()
    bundle = report.get("bundle")
    if not isinstance(bundle, dict):
        raise PromotionError(
            "promotion report is missing bundle report"
        )

    try:
        base_result = write_submission_bundle(
            root,
            bundle,
            output=output,
            force=force,
        )
    except BundleError as exc:
        raise PromotionError(str(exc)) from exc

    bundle_root = Path(base_result["bundle_root"]).resolve()
    try:
        bundle_root.relative_to(root)
    except ValueError as exc:
        raise PromotionError(
            "promoted release root escapes plugin root"
        ) from exc

    dossier = report.get("_verification_dossier")
    stage_payloads = report.get(
        "_verification_artifacts"
    )
    freshness_report = report.get("_freshness_report")
    behavior_report = report.get("_behavior_report")
    canary_baseline = report.get("_canary_baseline")
    negative_report = report.get("_negative_report")
    negative_baseline = report.get("_negative_baseline")
    credential_report = report.get("_credential_report")
    credential_baseline = report.get("_credential_baseline")
    security_report = report.get("_security_report")
    if not isinstance(dossier, dict):
        raise PromotionError(
            "promotion report is missing verification dossier"
        )
    if not isinstance(stage_payloads, dict):
        raise PromotionError(
            "promotion report is missing verification artifacts"
        )

    public = public_promotion_report(report)
    extra: dict[str, bytes] = {
        "promotion.json": _json_bytes(public),
        "verification/dossier.json": _json_bytes(
            dossier
        ),
    }
    for name, payload in sorted(
        stage_payloads.items()
    ):
        extra[f"verification/{name}"] = _json_bytes(
            payload
        )
    if isinstance(freshness_report, dict):
        extra["verification/freshness.json"] = _json_bytes(
            freshness_report
        )
    if isinstance(behavior_report, dict):
        extra["verification/canary-replay.json"] = _json_bytes(
            behavior_report
        )
    if isinstance(canary_baseline, dict):
        extra["verification/canary-baseline.json"] = _json_bytes(
            canary_baseline
        )
    if isinstance(negative_report, dict):
        extra["verification/negative-replay.json"] = _json_bytes(
            negative_report
        )
    if isinstance(negative_baseline, dict):
        extra["verification/negative-baseline.json"] = _json_bytes(
            negative_baseline
        )
    if isinstance(credential_report, dict):
        extra["verification/credential-matrix-replay.json"] = _json_bytes(
            credential_report
        )
    if isinstance(credential_baseline, dict):
        extra["verification/credential-matrix-baseline.json"] = _json_bytes(
            credential_baseline
        )
    if isinstance(security_report, dict):
        extra["verification/security-scheme-gate.json"] = _json_bytes(
            security_report
        )

    written: list[str] = []
    unchanged: list[str] = []
    for rel, payload in extra.items():
        target = _safe_child(bundle_root, rel)
        _reject_symlink_target(root, target)
        if target.exists():
            if not target.is_file():
                raise PromotionError(
                    f"promoted release target is not a regular file: {target}"
                )
            current = target.read_bytes()
            if current != payload and not force:
                raise PromotionError(
                    f"promoted release artifact differs at {target}; use --force to replace it"
                )
            if current == payload:
                unchanged.append(rel)
                continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        written.append(rel)

    return {
        **base_result,
        "promotion_id": report["promotion_id"],
        "promotion_ready": report[
            "promotion_ready"
        ],
        "promotion_written": written,
        "promotion_unchanged": unchanged,
        "promotion_file_count": len(extra),
    }


def public_promotion_report(
    report: dict[str, Any],
) -> dict[str, Any]:
    return {
        key: deepcopy(value)
        for key, value in report.items()
        if key
        not in {
            "_verification_dossier",
            "_verification_artifacts",
            "_freshness_report",
            "_behavior_report",
            "_canary_baseline",
            "_negative_report",
            "_negative_baseline",
            "_credential_report",
            "_credential_baseline",
            "_security_report",
        }
    }


def _resolve_requirement(
    dossier: dict[str, Any],
    requested: str,
) -> str:
    if requested != "auto":
        return requested
    summary = dossier.get("summary")
    host_required = (
        summary.get("host_required_extensions")
        if isinstance(summary, dict)
        else None
    )
    if isinstance(host_required, list) and host_required:
        return "chatgpt_host"
    return "mcp_server"


def _state_satisfies(
    state: Any,
    requirement: str,
) -> bool:
    if requirement == "chatgpt_host":
        return state == "verified_chatgpt_host"
    return state in {
        "verified_mcp_server",
        "verified_chatgpt_host",
    }


def _validate_verification_dossier(
    root: Path,
    dossier_path: Path,
    dossier: dict[str, Any],
) -> dict[str, Any]:
    blockers: list[str] = []
    artifact_payloads: dict[str, dict[str, Any]] = {}
    checks: list[dict[str, Any]] = []

    if dossier.get("evidence_state") != "executed":
        blockers.append(
            "verification_evidence_not_executed"
        )
    if not isinstance(
        dossier.get("verification_id"),
        str,
    ):
        blockers.append(
            "verification_id_missing"
        )

    stages = dossier.get("stages")
    artifacts = dossier.get("artifacts")
    if not isinstance(stages, dict):
        blockers.append(
            "verification_stages_missing"
        )
        stages = {}
    if not isinstance(artifacts, dict):
        blockers.append(
            "verification_artifacts_missing"
        )
        artifacts = {}

    stage_map = [
        (
            "runtime_smoke",
            "runtime",
            "sha256",
            "runtime.json",
        ),
        (
            "host_capture",
            "capture",
            "sha256",
            "capture.json",
        ),
        (
            "host_capture",
            "trace",
            "trace_sha256",
            "trace.json",
        ),
        (
            "host_replay",
            "host",
            "sha256",
            "host.json",
        ),
    ]

    for stage_name, artifact_key, digest_key, canonical_name in stage_map:
        stage = stages.get(stage_name)
        if not isinstance(stage, dict):
            continue
        expected = stage.get(digest_key)
        if expected is None:
            continue
        if not isinstance(expected, str) or not expected:
            blockers.append(
                f"verification_{artifact_key}_digest_invalid"
            )
            continue
        rel = artifacts.get(artifact_key)
        if not isinstance(rel, str) or not rel:
            blockers.append(
                f"verification_{artifact_key}_artifact_missing"
            )
            continue
        try:
            path = _safe_existing_file(
                root,
                rel,
                label=f"verification {artifact_key} artifact",
            )
            payload = _load_json_object(
                path,
                f"verification {artifact_key} artifact",
            )
            actual = _json_digest(payload)
            matches = actual == expected
            if not matches:
                blockers.append(
                    f"verification_{artifact_key}_digest_mismatch"
                )
            else:
                artifact_payloads[
                    canonical_name
                ] = payload
            checks.append(
                {
                    "artifact": artifact_key,
                    "path": rel,
                    "expected_sha256": expected,
                    "actual_sha256": actual,
                    "matches": matches,
                }
            )
        except PromotionError as exc:
            blockers.append(
                f"verification_{artifact_key}_artifact_invalid"
            )
            checks.append(
                {
                    "artifact": artifact_key,
                    "path": rel,
                    "matches": False,
                    "error": str(exc),
                }
            )

    return {
        "valid": not blockers,
        "blocking_reasons": _unique(blockers),
        "checks": checks,
        "artifact_payloads": artifact_payloads,
        "dossier_path": dossier_path.relative_to(
            root
        ).as_posix(),
    }


def _promotion_id(
    *,
    bundle_id: str,
    package_digest: str,
    dossier_sha256: str,
    requirement: str,
    freshness_id: str | None,
    canary_id: str | None,
    negative_id: str | None,
    matrix_id: str | None,
    security_gate_id: str | None,
) -> str:
    payload = {
        "bundle_id": bundle_id,
        "package_digest": package_digest,
        "dossier_sha256": dossier_sha256,
        "requirement": requirement,
        "freshness_id": freshness_id,
        "canary_id": canary_id,
        "negative_id": negative_id,
        "matrix_id": matrix_id,
        "security_gate_id": security_gate_id,
    }
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()[:20]


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
        raise PromotionError(
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
        raise PromotionError(
            f"{label} must be a non-empty relative path"
        )
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise PromotionError(
            f"{label} must stay inside the plugin root"
        )
    target = (root / candidate).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise PromotionError(
            f"{label} must stay inside the plugin root"
        ) from exc
    return target


def _safe_child(
    parent: Path,
    relative: str,
) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise PromotionError(
            "promoted release artifact path escapes release directory"
        )
    target = (parent / candidate).resolve()
    try:
        target.relative_to(parent)
    except ValueError as exc:
        raise PromotionError(
            "promoted release artifact path escapes release directory"
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
            raise PromotionError(
                f"refusing symlinked promoted release target: {current}"
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
        raise PromotionError(
            f"unable to read {label} at {path}: {exc}"
        ) from exc
    if not isinstance(value, dict):
        raise PromotionError(
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


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))
