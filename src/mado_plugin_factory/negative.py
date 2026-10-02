from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from .runtime import (
    RuntimeSmokeError,
    UnsafeCanaryToolError,
    execute_mcp_negative_canary,
)

SCHEMA_VERSION = "0.1"
DEFAULT_EVIDENCE_DIR = "evidence/negative/extensions"
VALID_CATEGORIES = {
    "invalid_input",
    "unauthorized",
    "not_found",
    "recoverable_error",
}
VALID_OUTCOMES = {
    "tool_error",
    "protocol_error",
    "http_error",
}
VALID_STRUCTURED = {
    "required",
    "optional",
    "forbidden",
}
VALID_CHALLENGE = {
    "required",
    "optional",
    "forbidden",
}


class NegativeContractError(ValueError):
    pass


def run_negative_contract(
    root: Path,
    *,
    contract: str,
    baseline_evidence: str | None = None,
    verification_evidence: str | None = None,
    server: str | None = None,
    mode: str = "auto",
    timeout: float = 5.0,
    write_evidence: bool = False,
    evidence_output: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    root = root.expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise NegativeContractError(
            f"candidate path is not a directory: {root}"
        )

    contract_path = _safe_existing_file(
        root,
        contract,
        label="negative contract",
    )
    contract_bytes = contract_path.read_bytes()
    contract_sha256 = hashlib.sha256(
        contract_bytes
    ).hexdigest()
    payload = _load_json_object(
        contract_path,
        "negative contract",
    )
    cases = _validate_contract(payload)

    contract_server = payload.get("server")
    selected_server = server or (
        contract_server
        if isinstance(contract_server, str)
        and contract_server
        else None
    )

    verification_binding = (
        _verification_binding(
            root,
            verification_evidence,
        )
        if verification_evidence
        else None
    )

    baseline: dict[str, Any] | None = None
    if baseline_evidence:
        baseline_path = _safe_existing_file(
            root,
            baseline_evidence,
            label="negative baseline evidence",
        )
        baseline = _load_json_object(
            baseline_path,
            "negative baseline evidence",
        )
        if baseline.get("evidence_state") != "executed":
            raise NegativeContractError(
                "negative baseline must have evidence_state=executed"
            )
        baseline_contract = baseline.get("contract")
        baseline_contract_sha = (
            baseline_contract.get("sha256")
            if isinstance(baseline_contract, dict)
            else None
        )
        if baseline_contract_sha != contract_sha256:
            raise NegativeContractError(
                "negative contract changed since baseline"
            )
        if verification_binding is not None:
            baseline_verification = baseline.get(
                "verification"
            )
            baseline_dossier_sha = (
                baseline_verification.get(
                    "dossier_sha256"
                )
                if isinstance(
                    baseline_verification,
                    dict,
                )
                else None
            )
            if (
                baseline_dossier_sha
                != verification_binding[
                    "dossier_sha256"
                ]
            ):
                raise NegativeContractError(
                    "negative baseline is not bound to the selected verification dossier"
                )

    baseline_cases = {
        item.get("id"): item
        for item in (
            baseline.get("cases", [])
            if isinstance(baseline, dict)
            else []
        )
        if isinstance(item, dict)
        and isinstance(item.get("id"), str)
    }

    observations: list[dict[str, Any]] = []
    blockers: list[str] = []
    for case in cases:
        case_id = case["id"]
        try:
            execution = execute_mcp_negative_canary(
                root,
                tool_name=case["tool"],
                arguments=case["arguments"],
                request_context=case[
                    "request_context"
                ],
                server=selected_server,
                mode=mode,
                timeout=timeout,
            )
        except UnsafeCanaryToolError:
            item = _failed_case(
                case,
                "tool_not_explicitly_read_only",
            )
            observations.append(item)
            blockers.append(
                f"{case_id}:tool_not_explicitly_read_only"
            )
            continue
        except RuntimeSmokeError as exc:
            item = _failed_case(
                case,
                "negative_execution_error",
                execution_error=exc,
            )
            observations.append(item)
            blockers.append(
                f"{case_id}:negative_execution_error"
            )
            continue

        observation = _observe_negative(
            execution.get(
                "transport_observation"
            )
        )
        expectation_reasons = _check_expectation(
            observation,
            case,
        )
        behavior_sha = _json_sha256(
            observation
        )
        case_report = {
            "id": case_id,
            "category": case["category"],
            "tool": case["tool"],
            "request_context": case[
                "request_context"
            ],
            "arguments_sha256": _json_sha256(
                case["arguments"]
            ),
            "safe_to_execute": True,
            "protocol": {
                "era": execution.get("era"),
                "version": execution.get(
                    "protocol_version"
                ),
                "transport": execution.get(
                    "transport"
                ),
            },
            "observation": observation,
            "behavior_sha256": behavior_sha,
            "expectation_passed": (
                not expectation_reasons
            ),
            "baseline_matches": None,
            "blocking_reasons": list(
                expectation_reasons
            ),
        }

        if baseline is not None:
            base = baseline_cases.get(
                case_id
            )
            if not isinstance(base, dict):
                case_report[
                    "baseline_matches"
                ] = False
                case_report[
                    "blocking_reasons"
                ].append(
                    "baseline_case_missing"
                )
            elif (
                base.get("category")
                != case["category"]
                or base.get("tool")
                != case["tool"]
                or base.get("request_context")
                != case["request_context"]
                or base.get("arguments_sha256")
                != case_report[
                    "arguments_sha256"
                ]
            ):
                case_report[
                    "baseline_matches"
                ] = False
                case_report[
                    "blocking_reasons"
                ].append(
                    "baseline_case_contract_mismatch"
                )
            else:
                matches = (
                    base.get("behavior_sha256")
                    == behavior_sha
                )
                case_report[
                    "baseline_matches"
                ] = matches
                if not matches:
                    case_report[
                        "blocking_reasons"
                    ].append(
                        "negative_contract_drift"
                    )

        case_report[
            "blocking_reasons"
        ] = list(
            dict.fromkeys(
                case_report[
                    "blocking_reasons"
                ]
            )
        )
        if case_report[
            "blocking_reasons"
        ]:
            blockers.extend(
                f"{case_id}:{reason}"
                for reason in case_report[
                    "blocking_reasons"
                ]
            )
        observations.append(case_report)

    mode_name = (
        "replay"
        if baseline is not None
        else "record"
    )
    negative_passed = bool(
        observations
        and not blockers
        and all(
            item.get("safe_to_execute")
            and item.get(
                "expectation_passed"
            )
            for item in observations
        )
    )
    if baseline is not None:
        negative_verified = bool(
            negative_passed
            and all(
                item.get(
                    "baseline_matches"
                )
                is True
                for item in observations
            )
        )
    else:
        negative_verified = False

    negative_id = _negative_id(
        contract_sha256=contract_sha256,
        mode=mode_name,
        cases=observations,
        baseline_id=(
            baseline.get("negative_id")
            if isinstance(baseline, dict)
            else None
        ),
    )
    report = {
        "schema_version": SCHEMA_VERSION,
        "evidence_state": "executed",
        "negative_id": negative_id,
        "mode": mode_name,
        "contract": {
            "path": contract,
            "sha256": contract_sha256,
            "case_count": len(cases),
            "raw_arguments_persisted": False,
        },
        "baseline": {
            "path": baseline_evidence,
            "negative_id": (
                baseline.get("negative_id")
                if isinstance(
                    baseline,
                    dict,
                )
                else None
            ),
        },
        "verification": deepcopy(
            verification_binding
        ),
        "server": {
            "name": selected_server,
        },
        "cases": observations,
        "negative_passed": negative_passed,
        "negative_verified": (
            negative_verified
        ),
        "blocking_reasons": list(
            dict.fromkeys(blockers)
        ),
        "scope": (
            "read_only_negative_and_authorization_contract"
        ),
        "warnings": [
            (
                "M1.6 executes only tools that advertise "
                "annotations.readOnlyHint=true."
            ),
            (
                "Anonymous authorization replay is supported only "
                "for streamable-http MCP servers and removes the "
                "Authorization header for the canary tool call."
            ),
            (
                "Evidence stores failure class/status/code, "
                "content types, structured shape, and a hash of "
                "WWW-Authenticate when present. Raw arguments, "
                "tool-result values, HTTP bodies, tokens, and "
                "challenge text are not persisted."
            ),
            (
                "M1.6 does not exercise destructive tools or "
                "prove every scope/role combination."
            ),
        ],
    }

    if write_evidence:
        output = evidence_output or (
            f"{DEFAULT_EVIDENCE_DIR}/"
            f"{negative_id}.json"
        )
        report[
            "evidence_output"
        ] = _write_evidence(
            root,
            report,
            output=output,
            force=force,
        )
    return report


def _validate_contract(
    payload: dict[str, Any],
) -> list[dict[str, Any]]:
    raw_cases = payload.get("cases")
    if (
        not isinstance(raw_cases, list)
        or not raw_cases
    ):
        raise NegativeContractError(
            "negative contract cases must be a non-empty list"
        )

    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for index, raw in enumerate(
        raw_cases
    ):
        if not isinstance(raw, dict):
            raise NegativeContractError(
                f"negative case {index} must be an object"
            )
        case_id = raw.get("id")
        category = raw.get("category")
        tool = raw.get("tool")
        arguments = raw.get(
            "arguments",
            {},
        )
        expect = raw.get(
            "expect",
            {},
        )

        if (
            not isinstance(case_id, str)
            or not case_id.strip()
        ):
            raise NegativeContractError(
                f"negative case {index} id is required"
            )
        if case_id in seen:
            raise NegativeContractError(
                f"duplicate negative case id: {case_id}"
            )
        seen.add(case_id)
        if category not in VALID_CATEGORIES:
            raise NegativeContractError(
                f"negative case {case_id} has invalid category"
            )
        if (
            not isinstance(tool, str)
            or not tool.strip()
        ):
            raise NegativeContractError(
                f"negative case {case_id} tool is required"
            )
        if not isinstance(arguments, dict):
            raise NegativeContractError(
                f"negative case {case_id} arguments must be an object"
            )
        if not isinstance(expect, dict):
            raise NegativeContractError(
                f"negative case {case_id} expect must be an object"
            )

        request_context = raw.get(
            "request_context",
            (
                "anonymous"
                if category == "unauthorized"
                else "configured"
            ),
        )
        if request_context not in {
            "configured",
            "anonymous",
        }:
            raise NegativeContractError(
                f"negative case {case_id} has invalid request_context"
            )
        if (
            category == "unauthorized"
            and request_context
            != "anonymous"
        ):
            raise NegativeContractError(
                f"negative case {case_id} unauthorized category requires request_context=anonymous"
            )
        if (
            category != "unauthorized"
            and request_context
            == "anonymous"
        ):
            raise NegativeContractError(
                f"negative case {case_id} anonymous context is reserved for unauthorized contracts"
            )

        outcome = expect.get("outcome")
        if outcome not in VALID_OUTCOMES:
            raise NegativeContractError(
                f"negative case {case_id} expect.outcome must be tool_error, protocol_error, or http_error"
            )
        if category == "unauthorized":
            if outcome != "http_error":
                raise NegativeContractError(
                    f"negative case {case_id} unauthorized contracts require expect.outcome=http_error"
                )
            status = expect.get(
                "http_status",
                401,
            )
            if status not in {401, 403}:
                raise NegativeContractError(
                    f"negative case {case_id} unauthorized http_status must be 401 or 403"
                )
        else:
            status = expect.get(
                "http_status"
            )

        structured = expect.get(
            "structured_content",
            "optional",
        )
        if (
            structured
            not in VALID_STRUCTURED
        ):
            raise NegativeContractError(
                f"negative case {case_id} has invalid expect.structured_content"
            )
        content_types = expect.get(
            "content_types",
            [],
        )
        if (
            not isinstance(
                content_types,
                list,
            )
            or not all(
                isinstance(item, str)
                for item in content_types
            )
        ):
            raise NegativeContractError(
                f"negative case {case_id} expect.content_types must be a string list"
            )

        auth_challenge = expect.get(
            "auth_challenge",
            (
                "required"
                if (
                    category
                    == "unauthorized"
                    and status == 401
                )
                else "optional"
            ),
        )
        if (
            auth_challenge
            not in VALID_CHALLENGE
        ):
            raise NegativeContractError(
                f"negative case {case_id} has invalid expect.auth_challenge"
            )

        result.append(
            {
                "id": case_id,
                "category": category,
                "tool": tool,
                "arguments": arguments,
                "request_context": (
                    request_context
                ),
                "expect": {
                    "outcome": outcome,
                    "protocol_error_code": (
                        expect.get(
                            "protocol_error_code"
                        )
                    ),
                    "http_status": status,
                    "auth_challenge": (
                        auth_challenge
                    ),
                    "structured_content": (
                        structured
                    ),
                    "content_types": sorted(
                        set(
                            content_types
                        )
                    ),
                },
            }
        )
    return result


def _observe_negative(
    transport: Any,
) -> dict[str, Any]:
    if not isinstance(
        transport,
        dict,
    ):
        return {
            "outcome": "transport_invalid",
            "http_status": None,
            "www_authenticate_present": False,
            "www_authenticate_sha256": None,
            "protocol_error_code": None,
            "content_types": [],
            "structured_content": {
                "present": False,
                "shape": None,
            },
        }

    kind = transport.get("kind")
    if kind == "http_error":
        return {
            "outcome": "http_error",
            "http_status": transport.get(
                "status"
            ),
            "www_authenticate_present": bool(
                transport.get(
                    "www_authenticate_present"
                )
            ),
            "www_authenticate_sha256": (
                transport.get(
                    "www_authenticate_sha256"
                )
            ),
            "protocol_error_code": None,
            "content_types": [],
            "structured_content": {
                "present": False,
                "shape": None,
            },
        }

    message = transport.get(
        "message"
    )
    if not isinstance(message, dict):
        message = {}
    error = message.get("error")
    if isinstance(error, dict):
        return {
            "outcome": "protocol_error",
            "http_status": None,
            "www_authenticate_present": False,
            "www_authenticate_sha256": None,
            "protocol_error_code": error.get(
                "code"
            ),
            "content_types": [],
            "structured_content": {
                "present": False,
                "shape": None,
            },
        }

    result = message.get("result")
    if not isinstance(result, dict):
        result = {}
    outcome = (
        "tool_error"
        if result.get("isError") is True
        else "success"
    )
    content = result.get("content")
    content_types = sorted(
        {
            str(item.get("type"))
            for item in content
            if isinstance(item, dict)
            and item.get("type")
        }
    ) if isinstance(content, list) else []

    structured = result.get(
        "structuredContent"
    )
    present = isinstance(
        structured,
        (dict, list),
    )
    return {
        "outcome": outcome,
        "http_status": None,
        "www_authenticate_present": False,
        "www_authenticate_sha256": None,
        "protocol_error_code": None,
        "content_types": content_types,
        "structured_content": {
            "present": present,
            "shape": (
                _shape(structured)
                if present
                else None
            ),
        },
    }


def _check_expectation(
    observation: dict[str, Any],
    case: dict[str, Any],
) -> list[str]:
    expect = case["expect"]
    blockers: list[str] = []
    actual_outcome = observation.get(
        "outcome"
    )
    if actual_outcome == "success":
        blockers.append(
            "negative_case_unexpectedly_succeeded"
        )
    if actual_outcome != expect.get(
        "outcome"
    ):
        blockers.append(
            "unexpected_negative_outcome"
        )

    expected_code = expect.get(
        "protocol_error_code"
    )
    if (
        expected_code is not None
        and observation.get(
            "protocol_error_code"
        )
        != expected_code
    ):
        blockers.append(
            "unexpected_protocol_error_code"
        )

    expected_status = expect.get(
        "http_status"
    )
    if (
        expected_status is not None
        and observation.get(
            "http_status"
        )
        != expected_status
    ):
        blockers.append(
            "unexpected_http_status"
        )

    challenge_rule = expect.get(
        "auth_challenge"
    )
    challenge_present = bool(
        observation.get(
            "www_authenticate_present"
        )
    )
    if (
        challenge_rule == "required"
        and not challenge_present
    ):
        blockers.append(
            "www_authenticate_required"
        )
    if (
        challenge_rule == "forbidden"
        and challenge_present
    ):
        blockers.append(
            "www_authenticate_forbidden"
        )

    structured = observation.get(
        "structured_content"
    )
    present = bool(
        isinstance(structured, dict)
        and structured.get("present")
    )
    structured_rule = expect.get(
        "structured_content"
    )
    if (
        structured_rule == "required"
        and not present
    ):
        blockers.append(
            "structured_content_required"
        )
    if (
        structured_rule == "forbidden"
        and present
    ):
        blockers.append(
            "structured_content_forbidden"
        )

    expected_types = expect.get(
        "content_types"
    ) or []
    actual_types = observation.get(
        "content_types"
    ) or []
    if sorted(expected_types) != sorted(
        actual_types
    ):
        blockers.append(
            "unexpected_content_types"
        )
    return blockers


def _failed_case(
    case: dict[str, Any],
    reason: str,
    *,
    execution_error: Exception | None = None,
) -> dict[str, Any]:
    result = {
        "id": case["id"],
        "category": case["category"],
        "tool": case["tool"],
        "request_context": case[
            "request_context"
        ],
        "arguments_sha256": _json_sha256(
            case["arguments"]
        ),
        "safe_to_execute": False,
        "expectation_passed": False,
        "baseline_matches": None,
        "behavior_sha256": None,
        "blocking_reasons": [reason],
    }
    if execution_error is not None:
        result[
            "execution_error_sha256"
        ] = hashlib.sha256(
            str(execution_error).encode(
                "utf-8"
            )
        ).hexdigest()
    return result


def _verification_binding(
    root: Path,
    verification_evidence: str,
) -> dict[str, Any]:
    path = _safe_existing_file(
        root,
        verification_evidence,
        label="verification dossier",
    )
    dossier = _load_json_object(
        path,
        "verification dossier",
    )
    if (
        dossier.get("evidence_state")
        != "executed"
    ):
        raise NegativeContractError(
            "verification dossier must have evidence_state=executed"
        )
    if (
        dossier.get(
            "verification_verified"
        )
        is not True
    ):
        raise NegativeContractError(
            "verification dossier must be verified before recording/replaying negative contracts"
        )
    verification_id = dossier.get(
        "verification_id"
    )
    if (
        not isinstance(
            verification_id,
            str,
        )
        or not verification_id
    ):
        raise NegativeContractError(
            "verification dossier is missing verification_id"
        )
    return {
        "path": verification_evidence,
        "verification_id": (
            verification_id
        ),
        "dossier_sha256": hashlib.sha256(
            path.read_bytes()
        ).hexdigest(),
    }


def _shape(
    value: Any,
    *,
    depth: int = 0,
) -> Any:
    if depth >= 8:
        return {"type": "truncated"}
    if value is None:
        return {"type": "null"}
    if isinstance(value, bool):
        return {"type": "boolean"}
    if (
        isinstance(value, int)
        and not isinstance(value, bool)
    ):
        return {"type": "integer"}
    if isinstance(value, float):
        return {"type": "number"}
    if isinstance(value, str):
        return {"type": "string"}
    if isinstance(value, dict):
        return {
            "type": "object",
            "keys": {
                str(key): _shape(
                    item,
                    depth=depth + 1,
                )
                for key, item in sorted(
                    value.items(),
                    key=lambda pair: str(
                        pair[0]
                    ),
                )
            },
        }
    if isinstance(value, list):
        unique: dict[str, Any] = {}
        for item in value[:50]:
            shaped = _shape(
                item,
                depth=depth + 1,
            )
            unique[
                _json_sha256(shaped)
            ] = shaped
        return {
            "type": "array",
            "item_shapes": [
                unique[key]
                for key in sorted(
                    unique
                )
            ],
        }
    return {
        "type": type(value).__name__,
    }


def _negative_id(
    *,
    contract_sha256: str,
    mode: str,
    cases: list[dict[str, Any]],
    baseline_id: Any,
) -> str:
    payload = {
        "contract_sha256": (
            contract_sha256
        ),
        "mode": mode,
        "baseline_id": baseline_id,
        "cases": [
            {
                "id": item.get("id"),
                "category": item.get(
                    "category"
                ),
                "tool": item.get("tool"),
                "request_context": (
                    item.get(
                        "request_context"
                    )
                ),
                "arguments_sha256": (
                    item.get(
                        "arguments_sha256"
                    )
                ),
                "behavior_sha256": (
                    item.get(
                        "behavior_sha256"
                    )
                ),
                "blocking_reasons": (
                    item.get(
                        "blocking_reasons"
                    )
                ),
            }
            for item in cases
        ],
    }
    return _json_sha256(
        payload
    )[:20]


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
        label="negative evidence output",
    )
    _reject_symlink_target(
        root,
        target,
    )
    rendered = _json_text(
        report
    )
    if target.exists():
        if not target.is_file():
            raise NegativeContractError(
                f"negative evidence target is not a file: {target}"
            )
        current = target.read_text(
            encoding="utf-8"
        )
        if (
            current != rendered
            and not force
        ):
            raise NegativeContractError(
                f"negative evidence differs at {target}; use --force to replace it"
            )
    target.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    if (
        not target.exists()
        or target.read_text(
            encoding="utf-8"
        )
        != rendered
    ):
        target.write_text(
            rendered,
            encoding="utf-8",
        )
    return target.relative_to(
        root
    ).as_posix()


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
    if (
        not target.is_file()
        or target.is_symlink()
    ):
        raise NegativeContractError(
            f"{label} does not exist: {target}"
        )
    return target


def _safe_relative(
    root: Path,
    value: str,
    *,
    label: str,
) -> Path:
    if (
        not isinstance(value, str)
        or not value.strip()
    ):
        raise NegativeContractError(
            f"{label} must be a non-empty relative path"
        )
    candidate = Path(value)
    if (
        candidate.is_absolute()
        or ".." in candidate.parts
    ):
        raise NegativeContractError(
            f"{label} must stay inside the plugin root"
        )
    target = (
        root / candidate
    ).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise NegativeContractError(
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
        current = (
            current / part
        )
        if (
            current.exists()
            and current.is_symlink()
        ):
            raise NegativeContractError(
                f"refusing symlinked negative evidence target: {current}"
            )


def _load_json_object(
    path: Path,
    label: str,
) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as exc:
        raise NegativeContractError(
            f"unable to read {label} at {path}: {exc}"
        ) from exc
    if not isinstance(
        value,
        dict,
    ):
        raise NegativeContractError(
            f"{label} at {path} must be a JSON object"
        )
    return value


def _json_sha256(
    value: Any,
) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _json_text(
    value: Any,
) -> str:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
