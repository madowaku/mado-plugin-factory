from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "0.1"
DEFAULT_RUNTIME_DIR = "evidence/runtime/extensions"
DEFAULT_EVIDENCE_DIR = "evidence/host/extensions"

HOST_EXTENSION_IDS = {
    "deep_links",
    "model_app_context",
    "rich_forms",
}

CAPTURE_PRODUCTS = {"chatgpt"}
CAPTURE_SURFACES = {
    "web",
    "desktop",
    "ios",
    "android",
    "api_playground",
}
CAPTURE_MODES = {
    "developer_mode",
    "installed_plugin",
    "api_playground",
}
DIRECTIONS = {
    "host_to_app",
    "app_to_host",
    "server_to_host",
    "host_to_server",
}


class HostReplayError(ValueError):
    pass


def run_host_replay(
    root: Path,
    trace_path: Path,
    *,
    runtime_evidence: str | None = None,
    write_evidence: bool = False,
    evidence_output: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    root = root.expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise HostReplayError(f"candidate path is not a directory: {root}")

    trace_path = trace_path.expanduser().resolve()
    trace = _load_json_object(trace_path, "host trace")
    capture = _validate_capture(trace)
    events = _validate_events(trace)

    runtime_path = _resolve_runtime_evidence(
        root,
        runtime_evidence,
    )
    runtime = _load_json_object(
        runtime_path,
        "runtime evidence",
    )
    _validate_runtime_evidence(runtime)

    expected = sorted(
        set(runtime.get("host_required_extensions") or [])
        & HOST_EXTENSION_IDS
    )

    checks = [
        _check_extension(extension_id, events)
        for extension_id in expected
    ]
    accepted = sorted(
        item["id"] for item in checks if item["state"] == "accepted"
    )
    missing = sorted(
        item["id"] for item in checks if item["state"] != "accepted"
    )

    capture_attested = bool(
        capture["product"] == "chatgpt"
        and capture["executed"]
        and capture["attested_chatgpt_capture"]
    )
    replay_passed = not missing
    end_to_end_verified = bool(
        runtime["runtime_smoke_passed"]
        and expected
        and replay_passed
        and capture_attested
    )

    trace_sha256 = _sha256(trace_path.read_bytes())
    runtime_sha256 = _sha256(runtime_path.read_bytes())
    acceptance_id = _acceptance_id(
        trace_sha256,
        runtime_sha256,
        expected,
        accepted,
    )

    result = {
        "schema_version": SCHEMA_VERSION,
        "evidence_state": "executed",
        "acceptance_id": acceptance_id,
        "source": {
            "trace_sha256": trace_sha256,
            "runtime_evidence": runtime_path.relative_to(root).as_posix(),
            "runtime_evidence_sha256": runtime_sha256,
        },
        "capture": {
            "product": capture["product"],
            "surface": capture["surface"],
            "mode": capture["mode"],
            "executed": capture["executed"],
            "attested_chatgpt_capture": capture[
                "attested_chatgpt_capture"
            ],
        },
        "trace": {
            "event_count": len(events),
            "raw_trace_persisted": False,
            "sensitive_payloads_persisted": False,
        },
        "runtime_prerequisite": {
            "smoke_id": runtime.get("smoke_id"),
            "runtime_smoke_passed": runtime["runtime_smoke_passed"],
            "runtime_scope": runtime.get("runtime_scope"),
            "host_required_extensions": expected,
        },
        "extension_checks": checks,
        "accepted_extensions": accepted,
        "missing_extensions": missing,
        "capture_attested": capture_attested,
        "host_replay_passed": replay_passed,
        "end_to_end_verified": end_to_end_verified,
        "verification_scope": (
            "chatgpt_host_replay"
            if capture_attested
            else "unattested_host_trace_replay"
        ),
        "warnings": _warnings(
            capture_attested=capture_attested,
            expected=expected,
            missing=missing,
        ),
    }

    if write_evidence:
        output = evidence_output or (
            f"{DEFAULT_EVIDENCE_DIR}/{acceptance_id}.json"
        )
        result["evidence_output"] = _write_evidence(
            root,
            result,
            output=output,
            force=force,
        )
    return result


def _validate_capture(trace: dict[str, Any]) -> dict[str, Any]:
    capture = trace.get("capture")
    if not isinstance(capture, dict):
        raise HostReplayError("host trace capture must be an object")

    product = capture.get("product")
    surface = capture.get("surface")
    mode = capture.get("mode")
    executed = capture.get("executed")
    attested = capture.get("attested_chatgpt_capture")

    if product not in CAPTURE_PRODUCTS:
        raise HostReplayError("host trace capture.product must be chatgpt")
    if surface not in CAPTURE_SURFACES:
        raise HostReplayError(
            "host trace capture.surface must be one of: "
            + ", ".join(sorted(CAPTURE_SURFACES))
        )
    if mode not in CAPTURE_MODES:
        raise HostReplayError(
            "host trace capture.mode must be one of: "
            + ", ".join(sorted(CAPTURE_MODES))
        )
    if not isinstance(executed, bool):
        raise HostReplayError(
            "host trace capture.executed must be boolean"
        )
    if not isinstance(attested, bool):
        raise HostReplayError(
            "host trace capture.attested_chatgpt_capture must be boolean"
        )
    return {
        "product": product,
        "surface": surface,
        "mode": mode,
        "executed": executed,
        "attested_chatgpt_capture": attested,
    }


def _validate_events(
    trace: dict[str, Any],
) -> list[dict[str, Any]]:
    raw = trace.get("events")
    if not isinstance(raw, list) or not raw:
        raise HostReplayError("host trace events must be a non-empty list")

    events = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise HostReplayError(
                f"host trace event {index} must be an object"
            )
        direction = item.get("direction")
        method = item.get("method")
        if direction not in DIRECTIONS:
            raise HostReplayError(
                f"host trace event {index} has invalid direction"
            )
        if not isinstance(method, str) or not method.strip():
            raise HostReplayError(
                f"host trace event {index} method must be non-empty"
            )
        call_id = item.get("call_id")
        if call_id is not None and not isinstance(
            call_id,
            (str, int),
        ):
            raise HostReplayError(
                f"host trace event {index} call_id must be string, integer, or null"
            )
        params = item.get("params")
        result = item.get("result")
        if params is not None and not isinstance(params, dict):
            raise HostReplayError(
                f"host trace event {index} params must be an object"
            )
        if result is not None and not isinstance(result, dict):
            raise HostReplayError(
                f"host trace event {index} result must be an object"
            )
        events.append(
            {
                "direction": direction,
                "method": method,
                "call_id": call_id,
                "params": params or {},
                "result": result or {},
            }
        )
    return events


def _resolve_runtime_evidence(
    root: Path,
    requested: str | None,
) -> Path:
    if requested:
        target = _safe_relative(
            root,
            requested,
            label="runtime evidence",
        )
        if not target.is_file() or target.is_symlink():
            raise HostReplayError(
                f"runtime evidence does not exist: {target}"
            )
        return target

    directory = root / DEFAULT_RUNTIME_DIR
    if not directory.is_dir():
        raise HostReplayError(
            "runtime evidence is required; run mpf runtime-smoke --write-evidence or pass --runtime-evidence"
        )
    candidates = sorted(
        path
        for path in directory.glob("*.json")
        if path.is_file() and not path.is_symlink()
    )
    if len(candidates) != 1:
        raise HostReplayError(
            "select runtime evidence with --runtime-evidence when zero or multiple evidence files exist"
        )
    return candidates[0]


def _validate_runtime_evidence(
    runtime: dict[str, Any],
) -> None:
    if runtime.get("evidence_state") != "executed":
        raise HostReplayError(
            "runtime evidence must have evidence_state=executed"
        )
    if runtime.get("runtime_scope") != "mcp_server":
        raise HostReplayError(
            "runtime evidence must have runtime_scope=mcp_server"
        )
    if runtime.get("runtime_smoke_passed") is not True:
        raise HostReplayError(
            "runtime evidence must have runtime_smoke_passed=true"
        )
    host_required = runtime.get("host_required_extensions")
    if not isinstance(host_required, list):
        raise HostReplayError(
            "runtime evidence host_required_extensions must be a list"
        )


def _check_extension(
    extension_id: str,
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    if extension_id == "deep_links":
        return _check_deep_links(events)
    if extension_id == "model_app_context":
        return _check_model_context(events)
    if extension_id == "rich_forms":
        return _check_rich_forms(events)
    return {
        "id": extension_id,
        "state": "unsupported",
        "evidence": [],
    }


def _check_deep_links(
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    evidence = []
    for event in events:
        state = None
        if (
            event["direction"] == "host_to_app"
            and event["method"] == "ui/initialize"
        ):
            host_context = event["result"].get("hostContext")
            if isinstance(host_context, dict):
                state = host_context.get("openai/deepLink")
                source = "ui/initialize.hostContext"
            else:
                source = "ui/initialize.hostContext"
        elif (
            event["direction"] == "host_to_app"
            and event["method"]
            == "ui/notifications/host-context-changed"
        ):
            state = event["params"].get("openai/deepLink")
            source = "ui/notifications/host-context-changed"
        else:
            continue

        if not isinstance(state, dict):
            continue
        url = state.get("url")
        if (
            isinstance(url, str)
            and url.startswith("/")
            and "#" not in url
        ):
            evidence.append(
                {
                    "source": source,
                    "url_shape": "absolute_app_relative_path",
                    "url_sha256": _sha256(
                        url.encode("utf-8")
                    ),
                }
            )

    return {
        "id": "deep_links",
        "state": "accepted" if evidence else "missing",
        "evidence": evidence,
    }


def _check_model_context(
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    requests = {}
    responses = {}
    for event in events:
        if event["method"] != "ui/update-model-context":
            continue
        call_id = event["call_id"]
        if call_id is None:
            continue
        if event["direction"] == "app_to_host":
            params = event["params"]
            content = params.get("content")
            structured = params.get("structuredContent")
            has_payload = (
                isinstance(content, list) and bool(content)
            ) or isinstance(structured, dict)
            if has_payload:
                requests[str(call_id)] = True
        elif event["direction"] == "host_to_app":
            meta = event["result"].get("_meta")
            model = (
                meta.get("openai/modelContext")
                if isinstance(meta, dict)
                else None
            )
            update_id = (
                model.get("updateId")
                if isinstance(model, dict)
                else None
            )
            if isinstance(update_id, str) and update_id:
                responses[str(call_id)] = _sha256(
                    update_id.encode("utf-8")
                )

    matched = sorted(set(requests) & set(responses))
    evidence = [
        {
            "call_id": call_id,
            "update_id_sha256": responses[call_id],
        }
        for call_id in matched
    ]
    return {
        "id": "model_app_context",
        "state": "accepted" if evidence else "missing",
        "evidence": evidence,
    }


def _check_rich_forms(
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    valid_methods = {
        "openai/elicitation/create",
        "elicitation/create",
    }
    requests: dict[str, str] = {}
    responses: dict[str, str] = {}
    for event in events:
        method = event["method"]
        if method not in valid_methods:
            continue
        call_id = event["call_id"]
        if call_id is None:
            continue
        key = f"{method}:{call_id}"
        if event["direction"] == "server_to_host":
            params = event["params"]
            if (
                params.get("mode") == "form"
                and isinstance(
                    params.get("requestedSchema"),
                    dict,
                )
            ):
                requests[key] = method
        elif event["direction"] == "host_to_server":
            action = event["result"].get("action")
            if action in {"accept", "decline", "cancel"}:
                responses[key] = action

    matched = sorted(set(requests) & set(responses))
    evidence = [
        {
            "call_id": key.split(":", 1)[1],
            "method": requests[key],
            "action": responses[key],
        }
        for key in matched
    ]
    return {
        "id": "rich_forms",
        "state": "accepted" if evidence else "missing",
        "evidence": evidence,
    }


def _acceptance_id(
    trace_sha256: str,
    runtime_sha256: str,
    expected: list[str],
    accepted: list[str],
) -> str:
    payload = {
        "trace_sha256": trace_sha256,
        "runtime_sha256": runtime_sha256,
        "expected": expected,
        "accepted": accepted,
    }
    return _sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )[:20]


def _warnings(
    *,
    capture_attested: bool,
    expected: list[str],
    missing: list[str],
) -> list[str]:
    warnings = [
        "M1.0 replays a captured ChatGPT host trace; it does not drive the ChatGPT UI itself."
    ]
    if not capture_attested:
        warnings.append(
            "The trace is not attested as an executed ChatGPT capture, so end-to-end verification is withheld."
        )
    if not expected:
        warnings.append(
            "The runtime evidence contains no host-required extensions to accept."
        )
    if missing:
        warnings.append(
            "Host acceptance evidence is missing for: "
            + ", ".join(missing)
        )
    return warnings


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
        label="host acceptance evidence output",
    )
    _reject_symlink_target(root, target)
    rendered = (
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    if target.exists():
        current = target.read_text(encoding="utf-8")
        if current != rendered and not force:
            raise HostReplayError(
                f"host acceptance evidence differs at {target}; use --force to replace it"
            )
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists() or target.read_text(encoding="utf-8") != rendered:
        target.write_text(rendered, encoding="utf-8")
    return target.relative_to(root).as_posix()


def _load_json_object(
    path: Path,
    label: str,
) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HostReplayError(
            f"unable to read {label} at {path}: {exc}"
        ) from exc
    if not isinstance(value, dict):
        raise HostReplayError(
            f"{label} at {path} must be a JSON object"
        )
    return value


def _safe_relative(
    root: Path,
    value: str,
    *,
    label: str,
) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise HostReplayError(
            f"{label} must be a non-empty relative path"
        )
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise HostReplayError(
            f"{label} must stay inside the plugin root"
        )
    target = (root / candidate).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise HostReplayError(
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
            raise HostReplayError(
                f"refusing symlinked host evidence target: {current}"
            )


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
