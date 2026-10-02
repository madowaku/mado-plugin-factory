from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from .runtime import (
    RuntimeSmokeError,
    UnsafeCanaryToolError,
    execute_mcp_credential_canary,
)

SCHEMA_VERSION = "0.1"
DEFAULT_EVIDENCE_DIR = "evidence/credentials/extensions"
VALID_KINDS = {"configured", "anonymous", "bearer_env"}
VALID_OUTCOMES = {
    "success",
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


class CredentialMatrixError(ValueError):
    pass


def run_credential_matrix(
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
        raise CredentialMatrixError(
            f"candidate path is not a directory: {root}"
        )

    contract_path = _safe_existing_file(
        root,
        contract,
        label="credential matrix contract",
    )
    contract_bytes = contract_path.read_bytes()
    contract_sha256 = hashlib.sha256(
        contract_bytes
    ).hexdigest()
    payload = _load_json_object(
        contract_path,
        "credential matrix contract",
    )
    credentials, cases = _validate_contract(
        payload
    )
    credentials_sha256 = _json_sha256(
        credentials
    )

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
            label="credential matrix baseline",
        )
        baseline = _load_json_object(
            baseline_path,
            "credential matrix baseline",
        )
        if baseline.get("evidence_state") != "executed":
            raise CredentialMatrixError(
                "credential matrix baseline must have evidence_state=executed"
            )
        baseline_contract = baseline.get(
            "contract"
        )
        baseline_contract_sha = (
            baseline_contract.get("sha256")
            if isinstance(
                baseline_contract,
                dict,
            )
            else None
        )
        if (
            baseline_contract_sha
            != contract_sha256
        ):
            raise CredentialMatrixError(
                "credential matrix contract changed since baseline"
            )
        baseline_credentials_sha = (
            baseline_contract.get(
                "credentials_sha256"
            )
            if isinstance(
                baseline_contract,
                dict,
            )
            else None
        )
        if (
            baseline_credentials_sha
            != credentials_sha256
        ):
            raise CredentialMatrixError(
                "credential profiles changed since baseline"
            )
        if verification_binding is not None:
            baseline_verification = (
                baseline.get("verification")
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
                raise CredentialMatrixError(
                    "credential matrix baseline is not bound to the selected verification dossier"
                )

    baseline_cases = {
        item.get("id"): item
        for item in (
            baseline.get("cases", [])
            if isinstance(
                baseline,
                dict,
            )
            else []
        )
        if isinstance(item, dict)
        and isinstance(
            item.get("id"),
            str,
        )
    }

    observations: list[
        dict[str, Any]
    ] = []
    blockers: list[str] = []

    for case in cases:
        case_id = case["id"]
        credential_id = case[
            "credential"
        ]
        credential = credentials[
            credential_id
        ]
        try:
            execution = (
                execute_mcp_credential_canary(
                    root,
                    tool_name=case["tool"],
                    arguments=case[
                        "arguments"
                    ],
                    credential=credential,
                    server=selected_server,
                    mode=mode,
                    timeout=timeout,
                )
            )
        except UnsafeCanaryToolError:
            item = _failed_case(
                case,
                "tool_not_explicitly_read_only",
            )
            observations.append(item)
            blockers.append(
                f"{case_id}:"
                "tool_not_explicitly_read_only"
            )
            continue
        except RuntimeSmokeError as exc:
            item = _failed_case(
                case,
                "credential_execution_error",
                execution_error=exc,
            )
            observations.append(item)
            blockers.append(
                f"{case_id}:"
                "credential_execution_error"
            )
            continue

        observation = _observe(
            execution.get(
                "transport_observation"
            ),
            stable_paths=case[
                "stable_paths"
            ],
        )
        expectation_reasons = (
            _check_expectation(
                observation,
                case["expect"],
            )
        )
        behavior_sha = _json_sha256(
            observation
        )
        case_report = {
            "id": case_id,
            "credential": (
                credential_id
            ),
            "credential_kind": (
                credential["kind"]
            ),
            "tool": case["tool"],
            "arguments_sha256": (
                _json_sha256(
                    case["arguments"]
                )
            ),
            "safe_to_execute": True,
            "protocol": {
                "era": execution.get(
                    "era"
                ),
                "version": (
                    execution.get(
                        "protocol_version"
                    )
                ),
                "transport": (
                    execution.get(
                        "transport"
                    )
                ),
            },
            "observation": observation,
            "behavior_sha256": (
                behavior_sha
            ),
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
            if not isinstance(
                base,
                dict,
            ):
                case_report[
                    "baseline_matches"
                ] = False
                case_report[
                    "blocking_reasons"
                ].append(
                    "baseline_case_missing"
                )
            elif (
                base.get("credential")
                != credential_id
                or base.get("tool")
                != case["tool"]
                or base.get(
                    "arguments_sha256"
                )
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
                    base.get(
                        "behavior_sha256"
                    )
                    == behavior_sha
                )
                case_report[
                    "baseline_matches"
                ] = matches
                if not matches:
                    case_report[
                        "blocking_reasons"
                    ].append(
                        "credential_boundary_drift"
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
        observations.append(
            case_report
        )

    mode_name = (
        "replay"
        if baseline is not None
        else "record"
    )
    matrix_passed = bool(
        observations
        and not blockers
        and all(
            item.get(
                "safe_to_execute"
            )
            and item.get(
                "expectation_passed"
            )
            for item in observations
        )
    )
    if baseline is not None:
        matrix_verified = bool(
            matrix_passed
            and all(
                item.get(
                    "baseline_matches"
                )
                is True
                for item in observations
            )
        )
    else:
        matrix_verified = False

    matrix_id = _matrix_id(
        contract_sha256=contract_sha256,
        credentials_sha256=(
            credentials_sha256
        ),
        mode=mode_name,
        cases=observations,
        baseline_id=(
            baseline.get("matrix_id")
            if isinstance(
                baseline,
                dict,
            )
            else None
        ),
    )
    report = {
        "schema_version": (
            SCHEMA_VERSION
        ),
        "evidence_state": "executed",
        "matrix_id": matrix_id,
        "mode": mode_name,
        "contract": {
            "path": contract,
            "sha256": (
                contract_sha256
            ),
            "credentials_sha256": (
                credentials_sha256
            ),
            "credential_ids": sorted(
                credentials
            ),
            "case_count": len(cases),
            "raw_arguments_persisted": (
                False
            ),
            "credential_env_names_persisted": (
                False
            ),
        },
        "baseline": {
            "path": baseline_evidence,
            "matrix_id": (
                baseline.get(
                    "matrix_id"
                )
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
        "matrix_passed": matrix_passed,
        "matrix_verified": (
            matrix_verified
        ),
        "blocking_reasons": list(
            dict.fromkeys(
                blockers
            )
        ),
        "scope": (
            "read_only_credential_scope_boundary"
        ),
        "warnings": [
            (
                "M1.7 executes only streamable-HTTP tools that "
                "advertise annotations.readOnlyHint=true."
            ),
            (
                "Credential profiles may reference bearer tokens only "
                "through environment variables. Raw tokens are never "
                "read from the contract or persisted in evidence."
            ),
            (
                "Evidence stores credential profile IDs/kinds, result "
                "shape, status/error class, challenge presence/hash, "
                "and declared stable-path hashes. Environment variable "
                "names, tokens, HTTP bodies, and result values are not persisted."
            ),
            (
                "M1.7 validates only declared profiles/cases. It does "
                "not prove every account role, organization policy, "
                "or write/destructive authorization boundary."
            ),
        ],
    }

    if write_evidence:
        output = evidence_output or (
            f"{DEFAULT_EVIDENCE_DIR}/"
            f"{matrix_id}.json"
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
) -> tuple[
    dict[str, dict[str, Any]],
    list[dict[str, Any]],
]:
    raw_credentials = payload.get(
        "credentials"
    )
    if (
        not isinstance(
            raw_credentials,
            dict,
        )
        or not raw_credentials
    ):
        raise CredentialMatrixError(
            "credential matrix credentials must be a non-empty object"
        )

    credentials: dict[
        str,
        dict[str, Any],
    ] = {}
    for profile_id, raw in (
        raw_credentials.items()
    ):
        if (
            not isinstance(
                profile_id,
                str,
            )
            or not profile_id.strip()
            or not isinstance(
                raw,
                dict,
            )
        ):
            raise CredentialMatrixError(
                "credential profile ids must map to objects"
            )
        kind = raw.get("kind")
        if kind not in VALID_KINDS:
            raise CredentialMatrixError(
                f"credential profile {profile_id} has invalid kind"
            )
        allowed = (
            {"kind", "env"}
            if kind == "bearer_env"
            else {"kind"}
        )
        extra = set(raw) - allowed
        if extra:
            raise CredentialMatrixError(
                f"credential profile {profile_id} contains unsupported fields"
            )
        if kind == "bearer_env":
            env_name = raw.get(
                "env"
            )
            if (
                not isinstance(
                    env_name,
                    str,
                )
                or not env_name.strip()
            ):
                raise CredentialMatrixError(
                    f"credential profile {profile_id} bearer_env requires env"
                )
            credentials[
                profile_id
            ] = {
                "kind": kind,
                "env": env_name,
            }
        else:
            credentials[
                profile_id
            ] = {
                "kind": kind,
            }

    raw_cases = payload.get("cases")
    if (
        not isinstance(
            raw_cases,
            list,
        )
        or not raw_cases
    ):
        raise CredentialMatrixError(
            "credential matrix cases must be a non-empty list"
        )

    seen: set[str] = set()
    cases: list[
        dict[str, Any]
    ] = []
    for index, raw in enumerate(
        raw_cases
    ):
        if not isinstance(
            raw,
            dict,
        ):
            raise CredentialMatrixError(
                f"credential matrix case {index} must be an object"
            )
        case_id = raw.get("id")
        credential = raw.get(
            "credential"
        )
        tool = raw.get("tool")
        arguments = raw.get(
            "arguments",
            {},
        )
        expect = raw.get(
            "expect",
            {},
        )
        stable_paths = raw.get(
            "stable_paths",
            [],
        )

        if (
            not isinstance(
                case_id,
                str,
            )
            or not case_id.strip()
        ):
            raise CredentialMatrixError(
                f"credential matrix case {index} id is required"
            )
        if case_id in seen:
            raise CredentialMatrixError(
                f"duplicate credential matrix case id: {case_id}"
            )
        seen.add(case_id)
        if credential not in credentials:
            raise CredentialMatrixError(
                f"credential matrix case {case_id} references unknown credential"
            )
        if (
            not isinstance(
                tool,
                str,
            )
            or not tool.strip()
        ):
            raise CredentialMatrixError(
                f"credential matrix case {case_id} tool is required"
            )
        if not isinstance(
            arguments,
            dict,
        ):
            raise CredentialMatrixError(
                f"credential matrix case {case_id} arguments must be an object"
            )
        if not isinstance(
            expect,
            dict,
        ):
            raise CredentialMatrixError(
                f"credential matrix case {case_id} expect must be an object"
            )

        outcome = expect.get(
            "outcome"
        )
        if outcome not in VALID_OUTCOMES:
            raise CredentialMatrixError(
                f"credential matrix case {case_id} has invalid expect.outcome"
            )
        structured = expect.get(
            "structured_content",
            "optional",
        )
        if (
            structured
            not in VALID_STRUCTURED
        ):
            raise CredentialMatrixError(
                f"credential matrix case {case_id} has invalid expect.structured_content"
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
            raise CredentialMatrixError(
                f"credential matrix case {case_id} expect.content_types must be a string list"
            )
        auth_challenge = expect.get(
            "auth_challenge",
            "optional",
        )
        if (
            auth_challenge
            not in VALID_CHALLENGE
        ):
            raise CredentialMatrixError(
                f"credential matrix case {case_id} has invalid expect.auth_challenge"
            )
        if (
            not isinstance(
                stable_paths,
                list,
            )
            or not all(
                isinstance(item, str)
                and item.startswith("$.")
                for item in stable_paths
            )
        ):
            raise CredentialMatrixError(
                f"credential matrix case {case_id} stable_paths must contain $. paths"
            )

        cases.append(
            {
                "id": case_id,
                "credential": (
                    credential
                ),
                "tool": tool,
                "arguments": arguments,
                "stable_paths": sorted(
                    set(stable_paths)
                ),
                "expect": {
                    "outcome": outcome,
                    "protocol_error_code": (
                        expect.get(
                            "protocol_error_code"
                        )
                    ),
                    "http_status": (
                        expect.get(
                            "http_status"
                        )
                    ),
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
    return credentials, cases


def _observe(
    transport: Any,
    *,
    stable_paths: list[str],
) -> dict[str, Any]:
    if not isinstance(
        transport,
        dict,
    ):
        return {
            "outcome": (
                "transport_invalid"
            ),
            "http_status": None,
            "www_authenticate_present": (
                False
            ),
            "www_authenticate_sha256": (
                None
            ),
            "protocol_error_code": None,
            "content_types": [],
            "structured_content": {
                "present": False,
                "shape": None,
            },
            "stable_paths": {},
        }

    if (
        transport.get("kind")
        == "http_error"
    ):
        return {
            "outcome": "http_error",
            "http_status": (
                transport.get(
                    "status"
                )
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
            "stable_paths": {},
        }

    message = transport.get(
        "message"
    )
    if not isinstance(
        message,
        dict,
    ):
        message = {}
    error = message.get("error")
    if isinstance(error, dict):
        return {
            "outcome": (
                "protocol_error"
            ),
            "http_status": None,
            "www_authenticate_present": (
                False
            ),
            "www_authenticate_sha256": (
                None
            ),
            "protocol_error_code": (
                error.get("code")
            ),
            "content_types": [],
            "structured_content": {
                "present": False,
                "shape": None,
            },
            "stable_paths": {},
        }

    result = message.get("result")
    if not isinstance(
        result,
        dict,
    ):
        result = {}
    outcome = (
        "tool_error"
        if result.get("isError")
        is True
        else "success"
    )
    content = result.get("content")
    content_types = sorted(
        {
            str(item.get("type"))
            for item in content
            if isinstance(
                item,
                dict,
            )
            and item.get("type")
        }
    ) if isinstance(
        content,
        list,
    ) else []

    structured = result.get(
        "structuredContent"
    )
    present = isinstance(
        structured,
        (dict, list),
    )
    stable_hashes: dict[
        str,
        str | None,
    ] = {}
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

    meta = result.get("_meta")
    challenges = (
        meta.get(
            "mcp/www_authenticate"
        )
        if isinstance(meta, dict)
        else None
    )
    challenge_text = ""
    if isinstance(
        challenges,
        str,
    ):
        challenge_text = challenges
    elif isinstance(
        challenges,
        list,
    ):
        challenge_text = "\n".join(
            item
            for item in challenges
            if isinstance(item, str)
        )

    return {
        "outcome": outcome,
        "http_status": None,
        "www_authenticate_present": bool(
            challenge_text
        ),
        "www_authenticate_sha256": (
            hashlib.sha256(
                challenge_text.encode(
                    "utf-8"
                )
            ).hexdigest()
            if challenge_text
            else None
        ),
        "protocol_error_code": None,
        "content_types": (
            content_types
        ),
        "structured_content": {
            "present": present,
            "shape": (
                _shape(structured)
                if present
                else None
            ),
        },
        "stable_paths": (
            stable_hashes
        ),
    }


def _check_expectation(
    observation: dict[str, Any],
    expect: dict[str, Any],
) -> list[str]:
    blockers: list[str] = []
    if observation.get(
        "outcome"
    ) != expect.get("outcome"):
        blockers.append(
            "unexpected_outcome"
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
        isinstance(
            structured,
            dict,
        )
        and structured.get(
            "present"
        )
    )
    rule = expect.get(
        "structured_content"
    )
    if (
        rule == "required"
        and not present
    ):
        blockers.append(
            "structured_content_required"
        )
    if (
        rule == "forbidden"
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
    execution_error: Exception
    | None = None,
) -> dict[str, Any]:
    result = {
        "id": case["id"],
        "credential": (
            case["credential"]
        ),
        "tool": case["tool"],
        "arguments_sha256": (
            _json_sha256(
                case["arguments"]
            )
        ),
        "safe_to_execute": False,
        "expectation_passed": (
            False
        ),
        "baseline_matches": None,
        "behavior_sha256": None,
        "blocking_reasons": [
            reason
        ],
    }
    if execution_error is not None:
        result[
            "execution_error_sha256"
        ] = hashlib.sha256(
            str(
                execution_error
            ).encode("utf-8")
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
        raise CredentialMatrixError(
            "verification dossier must have evidence_state=executed"
        )
    if (
        dossier.get(
            "verification_verified"
        )
        is not True
    ):
        raise CredentialMatrixError(
            "verification dossier must be verified before recording/replaying credential matrices"
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
        raise CredentialMatrixError(
            "verification dossier is missing verification_id"
        )
    return {
        "path": (
            verification_evidence
        ),
        "verification_id": (
            verification_id
        ),
        "dossier_sha256": (
            hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
        ),
    }


def _shape(
    value: Any,
    *,
    depth: int = 0,
) -> Any:
    if depth >= 8:
        return {
            "type": "truncated"
        }
    if value is None:
        return {"type": "null"}
    if isinstance(value, bool):
        return {
            "type": "boolean"
        }
    if (
        isinstance(value, int)
        and not isinstance(
            value,
            bool,
        )
    ):
        return {
            "type": "integer"
        }
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
        unique: dict[
            str,
            Any,
        ] = {}
        for item in value[:50]:
            shaped = _shape(
                item,
                depth=depth + 1,
            )
            unique[
                _json_sha256(
                    shaped
                )
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
        "type": (
            type(value).__name__
        )
    }


def _resolve_path(
    value: Any,
    path: str,
) -> tuple[bool, Any]:
    if not path.startswith("$."):
        return False, None
    current = value
    for part in path[2:].split(
        "."
    ):
        if not isinstance(
            current,
            dict,
        ):
            return False, None
        if part not in current:
            return False, None
        current = current[part]
    return True, current


def _matrix_id(
    *,
    contract_sha256: str,
    credentials_sha256: str,
    mode: str,
    cases: list[
        dict[str, Any]
    ],
    baseline_id: Any,
) -> str:
    payload = {
        "contract_sha256": (
            contract_sha256
        ),
        "credentials_sha256": (
            credentials_sha256
        ),
        "mode": mode,
        "baseline_id": (
            baseline_id
        ),
        "cases": [
            {
                "id": item.get("id"),
                "credential": (
                    item.get(
                        "credential"
                    )
                ),
                "tool": (
                    item.get("tool")
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
        label=(
            "credential matrix evidence output"
        ),
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
            raise CredentialMatrixError(
                f"credential matrix evidence target is not a file: {target}"
            )
        current = target.read_text(
            encoding="utf-8"
        )
        if (
            current != rendered
            and not force
        ):
            raise CredentialMatrixError(
                f"credential matrix evidence differs at {target}; use --force to replace it"
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
        raise CredentialMatrixError(
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
        raise CredentialMatrixError(
            f"{label} must be a non-empty relative path"
        )
    candidate = Path(value)
    if (
        candidate.is_absolute()
        or ".." in candidate.parts
    ):
        raise CredentialMatrixError(
            f"{label} must stay inside the plugin root"
        )
    target = (
        root / candidate
    ).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise CredentialMatrixError(
            f"{label} must stay inside the plugin root"
        ) from exc
    return target


def _reject_symlink_target(
    root: Path,
    target: Path,
) -> None:
    rel = target.relative_to(
        root
    )
    current = root
    for part in rel.parts:
        current = (
            current / part
        )
        if (
            current.exists()
            and current.is_symlink()
        ):
            raise CredentialMatrixError(
                f"refusing symlinked credential matrix evidence target: {current}"
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
        raise CredentialMatrixError(
            f"unable to read {label} at {path}: {exc}"
        ) from exc
    if not isinstance(
        value,
        dict,
    ):
        raise CredentialMatrixError(
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
