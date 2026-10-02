from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from .capture import (
    HostCaptureError,
    normalize_host_capture,
    public_capture_report,
)
from .host import HostReplayError, evaluate_host_replay
from .marketplace import plugin_package_digest
from .runtime import RuntimeSmokeError, run_extension_runtime_smoke

SCHEMA_VERSION = "0.1"
DEFAULT_OUTPUT_DIR = "evidence/verifications/extensions"


class VerificationOrchestratorError(ValueError):
    pass


def run_extension_verification(
    root: Path,
    *,
    server: str | None = None,
    runtime_mode: str = "auto",
    timeout: float = 5.0,
    capture_input: Path | None = None,
    capture_format: str = "auto",
    surface: str | None = None,
    capture_mode: str | None = None,
    executed: bool = False,
    attest_chatgpt_capture: bool = False,
    output_dir: str | None = None,
) -> dict[str, Any]:
    root = root.expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise VerificationOrchestratorError(
            f"candidate path is not a directory: {root}"
        )
    if capture_input is None and any(
        [
            surface is not None,
            capture_mode is not None,
            executed,
            attest_chatgpt_capture,
        ]
    ):
        raise VerificationOrchestratorError(
            "capture provenance options require --capture"
        )
    if capture_input is not None and (
        not surface or not capture_mode
    ):
        raise VerificationOrchestratorError(
            "--capture requires --surface and --capture-mode"
        )

    package_digest = plugin_package_digest(root)

    runtime: dict[str, Any] | None = None
    capture_report: dict[str, Any] | None = None
    trace: dict[str, Any] | None = None
    host: dict[str, Any] | None = None
    stage_errors: list[dict[str, str]] = []
    warnings: list[str] = []

    try:
        runtime = run_extension_runtime_smoke(
            root,
            server=server,
            mode=runtime_mode,
            timeout=timeout,
            write_evidence=False,
        )
    except RuntimeSmokeError as exc:
        stage_errors.append(
            {
                "stage": "runtime_smoke",
                "error": str(exc),
            }
        )

    if runtime is None:
        state = "runtime_error"
        verified = False
        followup = True
        next_actions = [
            "Fix the MCP runtime/configuration error and rerun verification."
        ]
    elif not runtime.get("runtime_smoke_passed"):
        state = "runtime_failed"
        verified = False
        followup = True
        next_actions = [
            "Fix missing or invalid MCP runtime extension metadata, then rerun verification."
        ]
    else:
        host_required = sorted(
            runtime.get("host_required_extensions") or []
        )
        if not host_required:
            if runtime.get("runtime_verified"):
                state = "verified_mcp_server"
                verified = True
                followup = False
                next_actions = []
            else:
                state = "no_verification_target"
                verified = False
                followup = True
                next_actions = [
                    "Add at least one runtime-verifiable extension surface or host-required extension before expecting a verification verdict."
                ]
        elif capture_input is None:
            state = "awaiting_host_capture"
            verified = False
            followup = True
            next_actions = [
                "Capture the relevant ChatGPT developer-mode, installed-plugin, or API Playground host exchange and rerun with --capture."
            ]
        else:
            try:
                capture_report = normalize_host_capture(
                    root,
                    capture_input,
                    source_format=capture_format,
                    surface=surface or "",
                    mode=capture_mode or "",
                    executed=executed,
                    attest_chatgpt_capture=attest_chatgpt_capture,
                )
                trace = capture_report["_trace"]
            except HostCaptureError as exc:
                stage_errors.append(
                    {
                        "stage": "host_capture",
                        "error": str(exc),
                    }
                )

            if capture_report is None or trace is None:
                state = "capture_failed"
                verified = False
                followup = True
                next_actions = [
                    "Fix or replace the host capture input and rerun verification."
                ]
            else:
                runtime_digest = _json_digest(runtime)
                trace_digest = _json_digest(trace)
                try:
                    host = evaluate_host_replay(
                        trace,
                        runtime,
                        trace_sha256=trace_digest,
                        runtime_sha256=runtime_digest,
                        runtime_label="orchestrator/runtime.json",
                    )
                except HostReplayError as exc:
                    stage_errors.append(
                        {
                            "stage": "host_replay",
                            "error": str(exc),
                        }
                    )

                if host is None:
                    state = "host_replay_error"
                    verified = False
                    followup = True
                    next_actions = [
                        "Fix the normalized host trace/runtime evidence mismatch and rerun verification."
                    ]
                elif host.get("end_to_end_verified"):
                    state = "verified_chatgpt_host"
                    verified = True
                    followup = False
                    next_actions = []
                elif host.get("host_replay_passed"):
                    state = "awaiting_capture_attestation"
                    verified = False
                    followup = True
                    next_actions = [
                        "Repeat or confirm the capture from an executed ChatGPT session and rerun with --executed --attest-chatgpt-capture."
                    ]
                else:
                    state = "host_incomplete"
                    verified = False
                    followup = True
                    missing = ", ".join(
                        host.get("missing_extensions") or []
                    )
                    next_actions = [
                        "Capture the missing ChatGPT host interactions"
                        + (f" for: {missing}." if missing else ".")
                    ]

    runtime_snapshot = (
        _runtime_snapshot(runtime)
        if runtime is not None
        else None
    )
    capture_snapshot = (
        _capture_snapshot(capture_report)
        if capture_report is not None
        else None
    )
    host_snapshot = deepcopy(host) if host is not None else None

    runtime_digest = (
        _json_digest(runtime_snapshot)
        if runtime_snapshot is not None
        else None
    )
    capture_digest = (
        _json_digest(capture_snapshot)
        if capture_snapshot is not None
        else None
    )
    trace_digest = (
        _json_digest(trace)
        if trace is not None
        else None
    )
    host_digest = (
        _json_digest(host_snapshot)
        if host_snapshot is not None
        else None
    )

    verification_id = _verification_id(
        state=state,
        runtime_digest=runtime_digest,
        capture_digest=capture_digest,
        trace_digest=trace_digest,
        host_digest=host_digest,
        stage_errors=stage_errors,
        package_digest=package_digest,
    )
    resolved_output = output_dir or (
        f"{DEFAULT_OUTPUT_DIR}/{verification_id}"
    )
    output_path = _safe_relative(
        root,
        resolved_output,
        label="verification output directory",
    )

    artifacts: dict[str, str] = {
        "dossier": (
            output_path.relative_to(root) / "dossier.json"
        ).as_posix(),
    }
    rendered: dict[str, str] = {}

    if runtime_snapshot is not None:
        path = (
            output_path.relative_to(root) / "runtime.json"
        ).as_posix()
        artifacts["runtime"] = path
        rendered["runtime.json"] = _json_text(runtime_snapshot)

    if capture_snapshot is not None and trace is not None:
        capture_path = (
            output_path.relative_to(root) / "capture.json"
        ).as_posix()
        trace_path = (
            output_path.relative_to(root) / "trace.json"
        ).as_posix()
        artifacts["capture"] = capture_path
        artifacts["trace"] = trace_path
        rendered["capture.json"] = _json_text(
            capture_snapshot
        )
        rendered["trace.json"] = _json_text(trace)

    if host_snapshot is not None:
        path = (
            output_path.relative_to(root) / "host.json"
        ).as_posix()
        artifacts["host"] = path
        rendered["host.json"] = _json_text(host_snapshot)

    if capture_report is not None:
        warnings.extend(
            capture_report.get("warnings") or []
        )
    if runtime is not None:
        warnings.extend(runtime.get("warnings") or [])
    if host is not None:
        warnings.extend(host.get("warnings") or [])
    warnings = list(dict.fromkeys(warnings))

    report = {
        "schema_version": SCHEMA_VERSION,
        "evidence_state": "executed",
        "verification_id": verification_id,
        "verification_state": state,
        "verification_verified": verified,
        "needs_followup": followup,
        "verification_scope": (
            "chatgpt_host"
            if state == "verified_chatgpt_host"
            else "mcp_server"
        ),
        "source": {
            "root": str(root),
            "capture_supplied": capture_input is not None,
            "plugin_package_digest": package_digest,
        },
        "stages": {
            "runtime_smoke": _runtime_stage(
                runtime,
                runtime_digest,
                stage_errors,
            ),
            "host_capture": _capture_stage(
                capture_report,
                capture_digest,
                trace_digest,
                stage_errors,
                required=bool(
                    runtime
                    and runtime.get(
                        "host_required_extensions"
                    )
                ),
            ),
            "host_replay": _host_stage(
                host,
                host_digest,
                stage_errors,
                required=bool(
                    runtime
                    and runtime.get(
                        "host_required_extensions"
                    )
                ),
            ),
        },
        "summary": {
            "runtime_verified_extensions": (
                runtime.get("verified_extensions") or []
                if runtime
                else []
            ),
            "host_required_extensions": (
                runtime.get("host_required_extensions") or []
                if runtime
                else []
            ),
            "runtime_missing_extensions": (
                runtime.get("missing_extensions") or []
                if runtime
                else []
            ),
            "host_accepted_extensions": (
                host.get("accepted_extensions") or []
                if host
                else []
            ),
            "host_missing_extensions": (
                host.get("missing_extensions") or []
                if host
                else []
            ),
        },
        "stage_errors": stage_errors,
        "next_actions": next_actions,
        "warnings": warnings,
        "output": output_path.relative_to(root).as_posix(),
        "artifacts": artifacts,
        "_artifacts": rendered,
    }
    public = public_verification_report(report)
    rendered["dossier.json"] = _json_text(public)
    return report


def write_verification_dossier(
    root: Path,
    report: dict[str, Any],
    *,
    force: bool = False,
) -> dict[str, str]:
    root = root.expanduser().resolve()
    output = report.get("output")
    rendered = report.get("_artifacts")
    if not isinstance(output, str) or not output:
        raise VerificationOrchestratorError(
            "verification report is missing output"
        )
    if not isinstance(rendered, dict) or not rendered:
        raise VerificationOrchestratorError(
            "verification report has no artifacts"
        )

    output_dir = _safe_relative(
        root,
        output,
        label="verification output directory",
    )
    _reject_symlink_target(root, output_dir)

    targets: list[tuple[Path, str]] = []
    for relative, content in sorted(rendered.items()):
        if not isinstance(relative, str) or not isinstance(
            content,
            str,
        ):
            raise VerificationOrchestratorError(
                "verification artifacts must map relative paths to text"
            )
        target = _safe_child(output_dir, relative)
        _reject_symlink_target(root, target)
        if target.exists():
            if not target.is_file():
                raise VerificationOrchestratorError(
                    f"verification target is not a regular file: {target}"
                )
            current = target.read_text(encoding="utf-8")
            if current != content and not force:
                raise VerificationOrchestratorError(
                    f"verification artifact differs at {target}; use --force to replace it"
                )
        targets.append((target, content))

    written: dict[str, str] = {}
    for target, content in targets:
        target.parent.mkdir(parents=True, exist_ok=True)
        status = "unchanged"
        if (
            not target.exists()
            or target.read_text(encoding="utf-8") != content
        ):
            target.write_text(content, encoding="utf-8")
            status = "written"
        written[target.relative_to(root).as_posix()] = status
    return written


def public_verification_report(
    report: dict[str, Any],
) -> dict[str, Any]:
    return {
        key: deepcopy(value)
        for key, value in report.items()
        if key != "_artifacts"
    }


def _runtime_snapshot(
    runtime: dict[str, Any],
) -> dict[str, Any]:
    return deepcopy(runtime)


def _capture_snapshot(
    report: dict[str, Any],
) -> dict[str, Any]:
    public = public_capture_report(report)
    public.pop("output", None)
    public.pop("artifacts", None)
    return public


def _runtime_stage(
    runtime: dict[str, Any] | None,
    digest: str | None,
    errors: list[dict[str, str]],
) -> dict[str, Any]:
    error = _stage_error(errors, "runtime_smoke")
    if error:
        return {
            "state": "error",
            "error": error,
            "sha256": None,
        }
    if runtime is None:
        return {
            "state": "not_run",
            "sha256": None,
        }
    return {
        "state": (
            "passed"
            if runtime.get("runtime_smoke_passed")
            else "failed"
        ),
        "smoke_id": runtime.get("smoke_id"),
        "runtime_verified": runtime.get("runtime_verified"),
        "sha256": digest,
    }


def _capture_stage(
    capture: dict[str, Any] | None,
    capture_digest: str | None,
    trace_digest: str | None,
    errors: list[dict[str, str]],
    *,
    required: bool,
) -> dict[str, Any]:
    error = _stage_error(errors, "host_capture")
    if error:
        return {
            "state": "error",
            "required": required,
            "error": error,
            "sha256": None,
            "trace_sha256": None,
        }
    if capture is None:
        return {
            "state": "awaiting" if required else "not_required",
            "required": required,
            "sha256": None,
            "trace_sha256": None,
        }
    return {
        "state": "normalized",
        "required": required,
        "capture_id": capture.get("capture_id"),
        "capture_attested": capture.get(
            "capture_attested"
        ),
        "sha256": capture_digest,
        "trace_sha256": trace_digest,
    }


def _host_stage(
    host: dict[str, Any] | None,
    digest: str | None,
    errors: list[dict[str, str]],
    *,
    required: bool,
) -> dict[str, Any]:
    error = _stage_error(errors, "host_replay")
    if error:
        return {
            "state": "error",
            "required": required,
            "error": error,
            "sha256": None,
        }
    if host is None:
        return {
            "state": "awaiting" if required else "not_required",
            "required": required,
            "sha256": None,
        }
    return {
        "state": (
            "verified"
            if host.get("end_to_end_verified")
            else (
                "replayed_unattested"
                if host.get("host_replay_passed")
                else "incomplete"
            )
        ),
        "required": required,
        "acceptance_id": host.get("acceptance_id"),
        "sha256": digest,
    }


def _stage_error(
    errors: list[dict[str, str]],
    stage: str,
) -> str | None:
    for item in errors:
        if item.get("stage") == stage:
            return item.get("error")
    return None


def _verification_id(
    *,
    state: str,
    runtime_digest: str | None,
    capture_digest: str | None,
    trace_digest: str | None,
    host_digest: str | None,
    stage_errors: list[dict[str, str]],
    package_digest: str,
) -> str:
    payload = {
        "state": state,
        "runtime": runtime_digest,
        "capture": capture_digest,
        "trace": trace_digest,
        "host": host_digest,
        "errors": stage_errors,
        "plugin_package_digest": package_digest,
    }
    return _sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )[:20]


def _json_digest(value: Any) -> str:
    return _sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )


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


def _safe_relative(
    root: Path,
    value: str,
    *,
    label: str,
) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise VerificationOrchestratorError(
            f"{label} must be a non-empty relative path"
        )
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise VerificationOrchestratorError(
            f"{label} must stay inside the plugin root"
        )
    target = (root / candidate).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise VerificationOrchestratorError(
            f"{label} must stay inside the plugin root"
        ) from exc
    return target


def _safe_child(
    parent: Path,
    relative: str,
) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise VerificationOrchestratorError(
            "verification artifact path must stay inside output"
        )
    target = (parent / candidate).resolve()
    try:
        target.relative_to(parent)
    except ValueError as exc:
        raise VerificationOrchestratorError(
            "verification artifact path must stay inside output"
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
            raise VerificationOrchestratorError(
                f"refusing symlinked verification target: {current}"
            )


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
