from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "0.1"
DEFAULT_OUTPUT_DIR = "evidence/host/captures"

SURFACES = {
    "web",
    "desktop",
    "ios",
    "android",
    "api_playground",
}
MODES = {
    "developer_mode",
    "installed_plugin",
    "api_playground",
}
FORM_METHODS = {
    "openai/elicitation/create",
    "elicitation/create",
}
RELEVANT_METHODS = {
    "ui/initialize",
    "ui/notifications/host-context-changed",
    "ui/update-model-context",
    *FORM_METHODS,
}
DIRECTIONS = {
    "host_to_app",
    "app_to_host",
    "server_to_host",
    "host_to_server",
}


class HostCaptureError(ValueError):
    pass


def normalize_host_capture(
    root: Path,
    input_path: Path,
    *,
    source_format: str = "auto",
    surface: str,
    mode: str,
    executed: bool = False,
    attest_chatgpt_capture: bool = False,
    output_dir: str | None = None,
) -> dict[str, Any]:
    root = root.expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise HostCaptureError(f"candidate path is not a directory: {root}")

    source = input_path.expanduser().resolve()
    if not source.is_file() or source.is_symlink():
        raise HostCaptureError(f"capture input is not a regular file: {source}")

    if source_format not in {"auto", "json", "jsonl", "normalized"}:
        raise HostCaptureError(
            "source format must be auto, json, jsonl, or normalized"
        )
    if surface not in SURFACES:
        raise HostCaptureError(
            "surface must be one of: " + ", ".join(sorted(SURFACES))
        )
    if mode not in MODES:
        raise HostCaptureError(
            "mode must be one of: " + ", ".join(sorted(MODES))
        )
    if attest_chatgpt_capture and not executed:
        raise HostCaptureError(
            "capture attestation requires --executed"
        )

    raw = source.read_bytes()
    source_sha256 = _sha256(raw)
    parsed, adapter = _parse_source(
        raw,
        requested_format=source_format,
        source_name=source.name,
    )

    records = _records_from_parsed(parsed)
    extracted, skipped = _extract_events(records)
    if not extracted:
        raise HostCaptureError(
            "no host-replay-relevant MCP Apps events were found"
        )

    canonical = _canonicalize_call_ids(extracted)
    normalized_events, redactions = _sanitize_events(canonical)
    if not normalized_events:
        raise HostCaptureError(
            "capture contained no usable host-replay events after normalization"
        )

    capture = {
        "product": "chatgpt",
        "surface": surface,
        "mode": mode,
        "executed": bool(executed),
        "attested_chatgpt_capture": bool(attest_chatgpt_capture),
    }
    trace = {
        "schema_version": SCHEMA_VERSION,
        "capture": capture,
        "events": normalized_events,
    }

    capture_id = _capture_id(
        source_sha256,
        capture,
        normalized_events,
    )
    resolved_output = output_dir or (
        f"{DEFAULT_OUTPUT_DIR}/{capture_id}"
    )
    output_path = _safe_relative(
        root,
        resolved_output,
        label="capture output directory",
    )

    report = {
        "schema_version": SCHEMA_VERSION,
        "evidence_state": "inspected",
        "capture_id": capture_id,
        "source": {
            "filename": source.name,
            "sha256": source_sha256,
            "format_requested": source_format,
            "adapter": adapter,
            "raw_input_persisted": False,
        },
        "capture": capture,
        "normalization": {
            "records_seen": len(records),
            "events_extracted": len(extracted),
            "events_written": len(normalized_events),
            "records_skipped": skipped,
            "methods": sorted(
                {event["method"] for event in normalized_events}
            ),
            "directions": sorted(
                {event["direction"] for event in normalized_events}
            ),
            "redactions": redactions,
            "sensitive_payloads_persisted": False,
        },
        "normalization_ready": True,
        "capture_attested": bool(
            executed and attest_chatgpt_capture
        ),
        "output": output_path.relative_to(root).as_posix(),
        "artifacts": {
            "trace": (
                output_path.relative_to(root) / "trace.json"
            ).as_posix(),
            "report": (
                output_path.relative_to(root) / "capture.json"
            ).as_posix(),
        },
        "warnings": _warnings(
            adapter=adapter,
            executed=executed,
            attested=attest_chatgpt_capture,
            skipped=skipped,
        ),
        "_trace": trace,
    }
    return report


def write_host_capture(
    root: Path,
    report: dict[str, Any],
    *,
    force: bool = False,
) -> dict[str, str]:
    root = root.expanduser().resolve()
    output = report.get("output")
    trace = report.get("_trace")
    if not isinstance(output, str) or not output:
        raise HostCaptureError("capture report is missing output")
    if not isinstance(trace, dict):
        raise HostCaptureError("capture report is missing normalized trace")

    output_dir = _safe_relative(
        root,
        output,
        label="capture output directory",
    )
    _reject_symlink_target(root, output_dir)

    public = public_capture_report(report)
    artifacts = {
        output_dir / "trace.json": _json_text(trace),
        output_dir / "capture.json": _json_text(public),
    }

    for target, content in artifacts.items():
        _reject_symlink_target(root, target)
        if target.exists():
            if not target.is_file():
                raise HostCaptureError(
                    f"capture target is not a regular file: {target}"
                )
            current = target.read_text(encoding="utf-8")
            if current != content and not force:
                raise HostCaptureError(
                    f"capture artifact differs at {target}; use --force to replace it"
                )

    written: dict[str, str] = {}
    for target, content in artifacts.items():
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


def public_capture_report(
    report: dict[str, Any],
) -> dict[str, Any]:
    return {
        key: deepcopy(value)
        for key, value in report.items()
        if key != "_trace"
    }


def _parse_source(
    raw: bytes,
    *,
    requested_format: str,
    source_name: str,
) -> tuple[Any, str]:
    text = raw.decode("utf-8")
    if requested_format == "normalized":
        value = _parse_json(text, "normalized capture")
        if not isinstance(value, dict) or not isinstance(
            value.get("events"),
            list,
        ):
            raise HostCaptureError(
                "normalized capture must contain an events array"
            )
        return value, "normalized"

    if requested_format == "json":
        return _parse_json(text, "capture JSON"), "json"

    if requested_format == "jsonl":
        return _parse_jsonl(text), "jsonl"

    if source_name.lower().endswith((".jsonl", ".ndjson")):
        return _parse_jsonl(text), "jsonl"

    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return _parse_jsonl(text), "jsonl"

    if isinstance(value, dict) and isinstance(
        value.get("events"),
        list,
    ):
        return value, "normalized"
    return value, "json"


def _parse_json(text: str, label: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise HostCaptureError(
            f"unable to parse {label}: {exc}"
        ) from exc


def _parse_jsonl(text: str) -> list[Any]:
    result = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            result.append(json.loads(stripped))
        except json.JSONDecodeError as exc:
            raise HostCaptureError(
                f"invalid JSONL at line {line_no}: {exc}"
            ) from exc
    if not result:
        raise HostCaptureError("JSONL capture is empty")
    return result


def _records_from_parsed(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if not isinstance(value, dict):
        raise HostCaptureError(
            "capture root must be a JSON object or array"
        )

    for key in ("events", "records", "logs", "messages", "items"):
        candidate = value.get(key)
        if isinstance(candidate, list):
            return candidate
    return [value]


def _extract_events(
    records: list[Any],
) -> tuple[list[dict[str, Any]], int]:
    events: list[dict[str, Any]] = []
    skipped = 0
    pending: dict[str, tuple[str, str]] = {}

    for record in records:
        if not isinstance(record, dict):
            skipped += 1
            continue

        direct = _direct_event(record)
        if direct is not None:
            events.append(direct)
            continue

        pair = _request_response_pair(record)
        if pair:
            events.extend(pair)
            continue

        message = record.get("message")
        if isinstance(message, (dict, str)):
            parsed = _coerce_message(message)
            direction = record.get("direction")
            event = _event_from_rpc(
                parsed,
                direction=direction,
                pending=pending,
            )
            if event is not None:
                events.append(event)
                continue

        event = _event_from_rpc(
            record,
            direction=record.get("direction"),
            pending=pending,
        )
        if event is not None:
            events.append(event)
            continue

        skipped += 1

    return events, skipped


def _direct_event(
    record: dict[str, Any],
) -> dict[str, Any] | None:
    method = record.get("method")
    direction = record.get("direction")
    if (
        isinstance(method, str)
        and method in RELEVANT_METHODS
        and direction in DIRECTIONS
    ):
        params = record.get("params")
        result = record.get("result")
        return {
            "direction": direction,
            "method": method,
            "call_id": record.get(
                "call_id",
                record.get("id"),
            ),
            "params": params if isinstance(params, dict) else {},
            "result": result if isinstance(result, dict) else {},
        }
    return None


def _request_response_pair(
    record: dict[str, Any],
) -> list[dict[str, Any]]:
    request = record.get("request")
    response = record.get("response")
    if request is None or response is None:
        return []

    request_obj = _coerce_message(request)
    response_obj = _coerce_message(response)
    method = request_obj.get("method")
    if not isinstance(method, str) or method not in RELEVANT_METHODS:
        return []

    request_direction = record.get("request_direction")
    if request_direction not in DIRECTIONS:
        request_direction = _request_direction(method)

    response_direction = record.get("response_direction")
    if response_direction not in DIRECTIONS:
        response_direction = _reverse_direction(request_direction)

    call_id = request_obj.get("id")
    if call_id is None:
        call_id = response_obj.get("id")
    params = request_obj.get("params")
    result = response_obj.get("result")

    events = [
        {
            "direction": request_direction,
            "method": method,
            "call_id": call_id,
            "params": params if isinstance(params, dict) else {},
            "result": {},
        }
    ]
    if isinstance(result, dict):
        events.append(
            {
                "direction": response_direction,
                "method": method,
                "call_id": call_id,
                "params": {},
                "result": result,
            }
        )
    return events


def _event_from_rpc(
    message: dict[str, Any],
    *,
    direction: Any,
    pending: dict[str, tuple[str, str]],
) -> dict[str, Any] | None:
    method = message.get("method")
    call_id = message.get("id")

    if isinstance(method, str):
        if method not in RELEVANT_METHODS:
            return None
        resolved_direction = (
            direction
            if direction in DIRECTIONS
            else _request_direction(method)
        )
        if call_id is not None:
            pending[str(call_id)] = (
                method,
                resolved_direction,
            )
        params = message.get("params")
        return {
            "direction": resolved_direction,
            "method": method,
            "call_id": call_id,
            "params": params if isinstance(params, dict) else {},
            "result": {},
        }

    if call_id is None:
        return None
    pending_item = pending.get(str(call_id))
    if pending_item is None:
        return None
    method, request_direction = pending_item
    result = message.get("result")
    if not isinstance(result, dict):
        return None
    resolved_direction = (
        direction
        if direction in DIRECTIONS
        else _reverse_direction(request_direction)
    )
    return {
        "direction": resolved_direction,
        "method": method,
        "call_id": call_id,
        "params": {},
        "result": result,
    }


def _coerce_message(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise HostCaptureError(
                "request/response message string must contain JSON"
            ) from exc
        if isinstance(parsed, dict):
            return parsed
    raise HostCaptureError(
        "request/response message must be a JSON object"
    )


def _request_direction(method: str) -> str:
    if method in FORM_METHODS:
        return "server_to_host"
    if method == "ui/notifications/host-context-changed":
        return "host_to_app"
    return "app_to_host"


def _reverse_direction(direction: str) -> str:
    reverse = {
        "app_to_host": "host_to_app",
        "host_to_app": "app_to_host",
        "server_to_host": "host_to_server",
        "host_to_server": "server_to_host",
    }
    return reverse[direction]


def _canonicalize_call_ids(
    events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    mapping: dict[str, str] = {}
    next_id = 1
    result = []
    for event in events:
        item = deepcopy(event)
        call_id = item.get("call_id")
        if call_id is not None:
            key = str(call_id)
            if key not in mapping:
                mapping[key] = f"call-{next_id}"
                next_id += 1
            item["call_id"] = mapping[key]
        result.append(item)
    return result


def _sanitize_events(
    events: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    counts = {
        "deep_link_urls": 0,
        "model_context_payloads": 0,
        "model_context_update_ids": 0,
        "form_messages": 0,
        "form_schemas": 0,
        "form_content": 0,
    }
    result = []
    for event in events:
        method = event["method"]
        item = {
            "direction": event["direction"],
            "method": method,
            "call_id": event.get("call_id"),
            "params": deepcopy(event.get("params") or {}),
            "result": deepcopy(event.get("result") or {}),
        }

        if method == "ui/initialize":
            context = item["result"].get("hostContext")
            if isinstance(context, dict):
                deep = context.get("openai/deepLink")
                if isinstance(deep, dict):
                    url = deep.get("url")
                    if isinstance(url, str):
                        deep["url"] = _redacted_path(url)
                        counts["deep_link_urls"] += 1

        elif method == "ui/notifications/host-context-changed":
            deep = item["params"].get("openai/deepLink")
            if isinstance(deep, dict):
                url = deep.get("url")
                if isinstance(url, str):
                    deep["url"] = _redacted_path(url)
                    counts["deep_link_urls"] += 1

        elif method == "ui/update-model-context":
            if item["direction"] == "app_to_host":
                params = item["params"]
                content = params.get("content")
                if isinstance(content, list) and content:
                    params["content"] = [
                        {
                            "type": "text",
                            "text": "[redacted]",
                        }
                    ]
                    counts["model_context_payloads"] += 1
                structured = params.get("structuredContent")
                if isinstance(structured, dict):
                    params["structuredContent"] = {
                        "redacted": True
                    }
                    counts["model_context_payloads"] += 1
            elif item["direction"] == "host_to_app":
                meta = item["result"].get("_meta")
                model = (
                    meta.get("openai/modelContext")
                    if isinstance(meta, dict)
                    else None
                )
                if isinstance(model, dict):
                    update_id = model.get("updateId")
                    if isinstance(update_id, str):
                        model["updateId"] = (
                            "sha256:" + _sha256(
                                update_id.encode("utf-8")
                            )
                        )
                        counts[
                            "model_context_update_ids"
                        ] += 1

        elif method in FORM_METHODS:
            if item["direction"] == "server_to_host":
                params = item["params"]
                message = params.get("message")
                if isinstance(message, str):
                    params["message"] = "[redacted]"
                    counts["form_messages"] += 1
                schema = params.get("requestedSchema")
                if isinstance(schema, dict):
                    params["requestedSchema"] = {
                        "type": "object",
                        "properties": {},
                    }
                    counts["form_schemas"] += 1
            elif item["direction"] == "host_to_server":
                if "content" in item["result"]:
                    item["result"]["content"] = {}
                    counts["form_content"] += 1

        result.append(item)
    return result, counts


def _redacted_path(value: str) -> str:
    return (
        "/__mpf_redacted__?sha256="
        + _sha256(value.encode("utf-8"))
    )


def _capture_id(
    source_sha256: str,
    capture: dict[str, Any],
    events: list[dict[str, Any]],
) -> str:
    payload = {
        "source_sha256": source_sha256,
        "capture": capture,
        "events": events,
    }
    return _sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )[:20]


def _warnings(
    *,
    adapter: str,
    executed: bool,
    attested: bool,
    skipped: int,
) -> list[str]:
    warnings = [
        "M1.1 normalizes supplied logs; it does not independently observe the ChatGPT UI."
    ]
    if not executed:
        warnings.append(
            "Capture is marked executed=false; M1.0 will not grant end-to-end verification."
        )
    elif not attested:
        warnings.append(
            "Capture is executed but unattested; M1.0 will withhold end-to-end verification."
        )
    if skipped:
        warnings.append(
            f"{skipped} input record(s) did not map to host-replay-relevant events."
        )
    if adapter != "normalized":
        warnings.append(
            "Raw log schemas are adapter-normalized heuristically; review capture.json before replay."
        )
    return warnings


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
        raise HostCaptureError(
            f"{label} must be a non-empty relative path"
        )
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise HostCaptureError(
            f"{label} must stay inside the plugin root"
        )
    target = (root / candidate).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise HostCaptureError(
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
            raise HostCaptureError(
                f"refusing symlinked capture target: {current}"
            )


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
