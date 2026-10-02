from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from .runtime import (
    RuntimeSmokeError,
    UnsafeCanaryToolError,
    execute_mcp_tool_canary,
)

SCHEMA_VERSION = "0.1"
DEFAULT_EVIDENCE_DIR = "evidence/canary/extensions"
VALID_OUTCOMES = {"success", "tool_error", "protocol_error"}
VALID_STRUCTURED = {"required", "optional", "forbidden"}


class CanaryError(ValueError):
    pass


def run_behavior_canary(
    root: Path,
    *,
    contract: str,
    baseline_evidence: str | None = None,
    server: str | None = None,
    mode: str = "auto",
    timeout: float = 5.0,
    write_evidence: bool = False,
    evidence_output: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    root = root.expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise CanaryError(
            f"candidate path is not a directory: {root}"
        )

    contract_path = _safe_existing_file(
        root,
        contract,
        label="canary contract",
    )
    contract_bytes = contract_path.read_bytes()
    contract_sha256 = hashlib.sha256(
        contract_bytes
    ).hexdigest()
    payload = _load_json_object(
        contract_path,
        "canary contract",
    )
    cases = _validate_contract(payload)

    contract_server = payload.get("server")
    selected_server = server or (
        contract_server
        if isinstance(contract_server, str)
        and contract_server
        else None
    )

    baseline: dict[str, Any] | None = None
    if baseline_evidence:
        baseline_path = _safe_existing_file(
            root,
            baseline_evidence,
            label="canary baseline evidence",
        )
        baseline = _load_json_object(
            baseline_path,
            "canary baseline evidence",
        )
        if baseline.get("evidence_state") != "executed":
            raise CanaryError(
                "canary baseline must have evidence_state=executed"
            )
        baseline_contract = baseline.get("contract")
        baseline_contract_sha = (
            baseline_contract.get("sha256")
            if isinstance(baseline_contract, dict)
            else None
        )
        if baseline_contract_sha != contract_sha256:
            raise CanaryError(
                "canary contract changed since baseline"
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
        tool = case["tool"]
        arguments = case["arguments"]
        expectation = case["expect"]

        try:
            execution = execute_mcp_tool_canary(
                root,
                tool_name=tool,
                arguments=arguments,
                server=selected_server,
                mode=mode,
                timeout=timeout,
            )
        except UnsafeCanaryToolError:
            observations.append(
                {
                    "id": case_id,
                    "tool": tool,
                    "arguments_sha256": _json_sha256(
                        arguments
                    ),
                    "safe_to_execute": False,
                    "expectation_passed": False,
                    "behavior_sha256": None,
                    "blocking_reasons": [
                        "tool_not_explicitly_read_only"
                    ],
                }
            )
            blockers.append(
                f"{case_id}:tool_not_explicitly_read_only"
            )
            continue
        except RuntimeSmokeError as exc:
            observations.append(
                {
                    "id": case_id,
                    "tool": tool,
                    "arguments_sha256": _json_sha256(
                        arguments
                    ),
                    "safe_to_execute": False,
                    "expectation_passed": False,
                    "behavior_sha256": None,
                    "execution_error_sha256": hashlib.sha256(
                        str(exc).encode("utf-8")
                    ).hexdigest(),
                    "blocking_reasons": [
                        "canary_execution_error"
                    ],
                }
            )
            blockers.append(
                f"{case_id}:canary_execution_error"
            )
            continue

        message = execution["message"]
        observation = _observe_behavior(
            message,
            stable_paths=case["stable_paths"],
        )
        expectation_reasons = _check_expectation(
            observation,
            expectation,
        )
        behavior_sha = _json_sha256(observation)

        case_report = {
            "id": case_id,
            "tool": tool,
            "arguments_sha256": _json_sha256(
                arguments
            ),
            "safe_to_execute": True,
            "protocol": {
                "era": execution.get("era"),
                "version": execution.get(
                    "protocol_version"
                ),
            },
            "observation": observation,
            "behavior_sha256": behavior_sha,
            "expectation_passed": not expectation_reasons,
            "baseline_matches": None,
            "blocking_reasons": list(
                expectation_reasons
            ),
        }

        if baseline is not None:
            base = baseline_cases.get(case_id)
            if not isinstance(base, dict):
                case_report["baseline_matches"] = False
                case_report["blocking_reasons"].append(
                    "baseline_case_missing"
                )
            elif (
                base.get("tool") != tool
                or base.get("arguments_sha256")
                != case_report["arguments_sha256"]
            ):
                case_report["baseline_matches"] = False
                case_report["blocking_reasons"].append(
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
                        "behavior_contract_drift"
                    )

        case_report["blocking_reasons"] = list(
            dict.fromkeys(
                case_report["blocking_reasons"]
            )
        )
        if case_report["blocking_reasons"]:
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
    canary_passed = bool(
        observations
        and not blockers
        and all(
            item.get("safe_to_execute")
            and item.get("expectation_passed")
            for item in observations
        )
    )
    if baseline is not None:
        canary_verified = bool(
            canary_passed
            and all(
                item.get("baseline_matches") is True
                for item in observations
            )
        )
    else:
        canary_verified = False

    canary_id = _canary_id(
        contract_sha256=contract_sha256,
        mode=mode_name,
        cases=observations,
        baseline_id=(
            baseline.get("canary_id")
            if isinstance(baseline, dict)
            else None
        ),
    )
    report = {
        "schema_version": SCHEMA_VERSION,
        "evidence_state": "executed",
        "canary_id": canary_id,
        "mode": mode_name,
        "contract": {
            "path": contract,
            "sha256": contract_sha256,
            "case_count": len(cases),
            "raw_arguments_persisted": False,
        },
        "baseline": {
            "path": baseline_evidence,
            "canary_id": (
                baseline.get("canary_id")
                if isinstance(baseline, dict)
                else None
            ),
        },
        "server": {
            "name": selected_server,
        },
        "cases": observations,
        "canary_passed": canary_passed,
        "canary_verified": canary_verified,
        "blocking_reasons": list(
            dict.fromkeys(blockers)
        ),
        "scope": "read_only_behavior_contract",
        "warnings": [
            (
                "M1.5 executes only tools that advertise "
                "annotations.readOnlyHint=true."
            ),
            (
                "Evidence stores result shape, error class/code, "
                "content types, and declared stable-path hashes, "
                "not raw tool results."
            ),
            (
                "Behavior replay does not prove write-tool behavior, "
                "authorization enforcement, or all business semantics."
            ),
        ],
    }

    if write_evidence:
        output = evidence_output or (
            f"{DEFAULT_EVIDENCE_DIR}/{canary_id}.json"
        )
        report["evidence_output"] = _write_evidence(
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
    if not isinstance(raw_cases, list) or not raw_cases:
        raise CanaryError(
            "canary contract cases must be a non-empty list"
        )

    seen: set[str] = set()
    cases: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_cases):
        if not isinstance(raw, dict):
            raise CanaryError(
                f"canary case {index} must be an object"
            )
        case_id = raw.get("id")
        tool = raw.get("tool")
        arguments = raw.get("arguments", {})
        expect = raw.get("expect", {})
        stable_paths = raw.get("stable_paths", [])

        if (
            not isinstance(case_id, str)
            or not case_id.strip()
        ):
            raise CanaryError(
                f"canary case {index} id is required"
            )
        if case_id in seen:
            raise CanaryError(
                f"duplicate canary case id: {case_id}"
            )
        seen.add(case_id)
        if not isinstance(tool, str) or not tool.strip():
            raise CanaryError(
                f"canary case {case_id} tool is required"
            )
        if not isinstance(arguments, dict):
            raise CanaryError(
                f"canary case {case_id} arguments must be an object"
            )
        if not isinstance(expect, dict):
            raise CanaryError(
                f"canary case {case_id} expect must be an object"
            )

        outcome = expect.get("outcome", "success")
        structured = expect.get(
            "structured_content",
            "optional",
        )
        content_types = expect.get("content_types", [])
        if outcome not in VALID_OUTCOMES:
            raise CanaryError(
                f"canary case {case_id} has invalid expect.outcome"
            )
        if structured not in VALID_STRUCTURED:
            raise CanaryError(
                f"canary case {case_id} has invalid expect.structured_content"
            )
        if not isinstance(content_types, list) or not all(
            isinstance(item, str)
            for item in content_types
        ):
            raise CanaryError(
                f"canary case {case_id} expect.content_types must be a string list"
            )
        if not isinstance(stable_paths, list) or not all(
            isinstance(item, str)
            and item.startswith("$.")
            for item in stable_paths
        ):
            raise CanaryError(
                f"canary case {case_id} stable_paths must contain $. paths"
            )

        cases.append(
            {
                "id": case_id,
                "tool": tool,
                "arguments": arguments,
                "expect": {
                    "outcome": outcome,
                    "structured_content": structured,
                    "content_types": sorted(
                        set(content_types)
                    ),
                    "protocol_error_code": expect.get(
                        "protocol_error_code"
                    ),
                },
                "stable_paths": sorted(
                    set(stable_paths)
                ),
            }
        )
    return cases


def _observe_behavior(
    message: dict[str, Any],
    *,
    stable_paths: list[str],
) -> dict[str, Any]:
    error = message.get("error")
    if isinstance(error, dict):
        return {
            "outcome": "protocol_error",
            "protocol_error_code": error.get("code"),
            "content_types": [],
            "structured_content": {
                "present": False,
                "shape": None,
            },
            "stable_paths": {},
        }

    result = message.get("result")
    if not isinstance(result, dict):
        result = {}
    is_error = result.get("isError") is True
    outcome = (
        "tool_error"
        if is_error
        else "success"
    )
    content = result.get("content")
    content_types = []
    if isinstance(content, list):
        content_types = sorted(
            {
                str(item.get("type"))
                for item in content
                if isinstance(item, dict)
                and item.get("type")
            }
        )

    structured = result.get("structuredContent")
    structured_present = isinstance(
        structured,
        (dict, list),
    )
    stable_hashes: dict[str, str | None] = {}
    for path in stable_paths:
        found, value = _resolve_path(
            structured,
            path,
        )
        stable_hashes[path] = (
            _json_sha256(value)
            if found
            else None
        )

    return {
        "outcome": outcome,
        "protocol_error_code": None,
        "content_types": content_types,
        "structured_content": {
            "present": structured_present,
            "shape": (
                _shape(structured)
                if structured_present
                else None
            ),
        },
        "stable_paths": stable_hashes,
    }


def _check_expectation(
    observation: dict[str, Any],
    expectation: dict[str, Any],
) -> list[str]:
    blockers = []
    if observation.get("outcome") != expectation.get(
        "outcome"
    ):
        blockers.append("unexpected_outcome")

    expected_code = expectation.get(
        "protocol_error_code"
    )
    if (
        expected_code is not None
        and observation.get("protocol_error_code")
        != expected_code
    ):
        blockers.append(
            "unexpected_protocol_error_code"
        )

    structured_rule = expectation.get(
        "structured_content"
    )
    structured = observation.get(
        "structured_content"
    )
    present = bool(
        isinstance(structured, dict)
        and structured.get("present")
    )
    if structured_rule == "required" and not present:
        blockers.append(
            "structured_content_required"
        )
    if structured_rule == "forbidden" and present:
        blockers.append(
            "structured_content_forbidden"
        )

    expected_types = expectation.get(
        "content_types"
    ) or []
    actual_types = observation.get(
        "content_types"
    ) or []
    if sorted(expected_types) != sorted(actual_types):
        blockers.append(
            "unexpected_content_types"
        )
    return blockers


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
    if isinstance(value, int) and not isinstance(
        value,
        bool,
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
                    key=lambda pair: str(pair[0]),
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
            digest = _json_sha256(shaped)
            unique[digest] = shaped
        return {
            "type": "array",
            "item_shapes": [
                unique[key]
                for key in sorted(unique)
            ],
        }
    return {
        "type": type(value).__name__,
    }


def _resolve_path(
    value: Any,
    path: str,
) -> tuple[bool, Any]:
    if not path.startswith("$."):
        return False, None
    current = value
    for part in path[2:].split("."):
        if not isinstance(current, dict):
            return False, None
        if part not in current:
            return False, None
        current = current[part]
    return True, current


def _canary_id(
    *,
    contract_sha256: str,
    mode: str,
    cases: list[dict[str, Any]],
    baseline_id: Any,
) -> str:
    payload = {
        "contract_sha256": contract_sha256,
        "mode": mode,
        "baseline_id": baseline_id,
        "cases": [
            {
                "id": item.get("id"),
                "tool": item.get("tool"),
                "arguments_sha256": item.get(
                    "arguments_sha256"
                ),
                "behavior_sha256": item.get(
                    "behavior_sha256"
                ),
                "blocking_reasons": item.get(
                    "blocking_reasons"
                ),
            }
            for item in cases
        ],
    }
    return _json_sha256(payload)[:20]


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
        label="canary evidence output",
    )
    _reject_symlink_target(root, target)
    rendered = _json_text(report)
    if target.exists():
        if not target.is_file():
            raise CanaryError(
                f"canary evidence target is not a file: {target}"
            )
        current = target.read_text(
            encoding="utf-8"
        )
        if current != rendered and not force:
            raise CanaryError(
                f"canary evidence differs at {target}; use --force to replace it"
            )
    target.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    if (
        not target.exists()
        or target.read_text(
            encoding="utf-8"
        ) != rendered
    ):
        target.write_text(
            rendered,
            encoding="utf-8",
        )
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
        raise CanaryError(
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
        raise CanaryError(
            f"{label} must be a non-empty relative path"
        )
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise CanaryError(
            f"{label} must stay inside the plugin root"
        )
    target = (root / candidate).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise CanaryError(
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
            raise CanaryError(
                f"refusing symlinked canary evidence target: {current}"
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
        raise CanaryError(
            f"unable to read {label} at {path}: {exc}"
        ) from exc
    if not isinstance(value, dict):
        raise CanaryError(
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
