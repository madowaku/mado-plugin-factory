from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from .runtime import RuntimeSmokeError, run_extension_runtime_smoke

SCHEMA_VERSION = "0.1"
DEFAULT_EVIDENCE_DIR = "evidence/security/extensions"
VALID_ACCESS = {"oauth_required", "optional_auth", "noauth"}


class SecuritySchemeGateError(ValueError):
    pass


def run_security_scheme_gate(
    root: Path,
    *,
    contract: str,
    matrix_evidence: str | None = None,
    matrix_report: dict[str, Any] | None = None,
    server: str | None = None,
    mode: str = "auto",
    timeout: float = 5.0,
    write_evidence: bool = False,
    evidence_output: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    root = root.expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise SecuritySchemeGateError(
            f"candidate path is not a directory: {root}"
        )

    contract_path = _safe_existing_file(
        root,
        contract,
        label="security scheme contract",
    )
    contract_bytes = contract_path.read_bytes()
    contract_sha256 = hashlib.sha256(
        contract_bytes
    ).hexdigest()
    contract_payload = _load_json_object(
        contract_path,
        "security scheme contract",
    )
    profiles, tool_policies = _validate_contract(
        contract_payload
    )

    if matrix_report is None:
        if not matrix_evidence:
            raise SecuritySchemeGateError(
                "security scheme gate requires matrix_evidence or matrix_report"
            )
        matrix_path = _safe_existing_file(
            root,
            matrix_evidence,
            label="credential matrix evidence",
        )
        matrix_report = _load_json_object(
            matrix_path,
            "credential matrix evidence",
        )
        matrix_sha256 = hashlib.sha256(
            matrix_path.read_bytes()
        ).hexdigest()
    else:
        matrix_sha256 = _json_sha256(
            matrix_report
        )

    if matrix_report.get("evidence_state") != "executed":
        raise SecuritySchemeGateError(
            "credential matrix evidence must have evidence_state=executed"
        )
    if matrix_report.get("mode") != "replay":
        raise SecuritySchemeGateError(
            "security scheme gate requires credential matrix replay evidence"
        )
    if matrix_report.get("matrix_verified") is not True:
        raise SecuritySchemeGateError(
            "credential matrix replay must be verified before security scheme analysis"
        )

    matrix_cases = {
        item.get("id"): item
        for item in matrix_report.get("cases", [])
        if isinstance(item, dict)
        and isinstance(item.get("id"), str)
    }

    contract_server = contract_payload.get("server")
    selected_server = server or (
        contract_server
        if isinstance(contract_server, str)
        and contract_server
        else None
    )
    try:
        runtime = run_extension_runtime_smoke(
            root,
            server=selected_server,
            mode=mode,
            timeout=timeout,
            write_evidence=False,
        )
    except RuntimeSmokeError as exc:
        raise SecuritySchemeGateError(
            str(exc)
        ) from exc

    if runtime.get("runtime_smoke_passed") is not True:
        raise SecuritySchemeGateError(
            "runtime smoke did not pass during security scheme gate"
        )

    tool_observations = {
        item.get("name"): item
        for item in (
            runtime.get("observations", {}).get("tools", [])
            if isinstance(runtime.get("observations"), dict)
            else []
        )
        if isinstance(item, dict)
        and isinstance(item.get("name"), str)
    }

    tool_reports: list[dict[str, Any]] = []
    blockers: list[str] = []

    for policy in tool_policies:
        tool_name = policy["tool"]
        descriptor = tool_observations.get(
            tool_name
        )
        if not isinstance(descriptor, dict):
            tool_report = {
                "tool": tool_name,
                "passed": False,
                "blocking_reasons": [
                    "tool_descriptor_missing"
                ],
            }
            tool_reports.append(tool_report)
            blockers.append(
                f"{tool_name}:tool_descriptor_missing"
            )
            continue

        schemes = _normalize_security_schemes(
            descriptor.get("securitySchemes")
        )
        access_blockers = _check_access_mode(
            schemes,
            policy["access"],
        )
        scope_blockers, evidence = _check_scope_evidence(
            tool_name=tool_name,
            schemes=schemes,
            policy=policy,
            profiles=profiles,
            matrix_cases=matrix_cases,
        )
        reasons = list(
            dict.fromkeys(
                access_blockers + scope_blockers
            )
        )
        tool_report = {
            "tool": tool_name,
            "access": policy["access"],
            "declared_security_schemes": schemes,
            "declared_security_sha256": _json_sha256(
                schemes
            ),
            "scope_evidence": evidence,
            "passed": not reasons,
            "blocking_reasons": reasons,
        }
        tool_reports.append(tool_report)
        blockers.extend(
            f"{tool_name}:{reason}"
            for reason in reasons
        )

    gate_passed = bool(
        tool_reports
        and not blockers
        and all(
            item.get("passed") is True
            for item in tool_reports
        )
    )
    gate_id = _gate_id(
        contract_sha256=contract_sha256,
        matrix_sha256=matrix_sha256,
        runtime_fingerprint=(
            runtime.get("runtime_fingerprint", {}).get("sha256")
            if isinstance(runtime.get("runtime_fingerprint"), dict)
            else None
        ),
        tools=tool_reports,
    )

    report = {
        "schema_version": SCHEMA_VERSION,
        "evidence_state": "executed",
        "gate_id": gate_id,
        "gate_passed": gate_passed,
        "contract": {
            "path": contract,
            "sha256": contract_sha256,
            "profile_ids": sorted(profiles),
            "tool_count": len(tool_policies),
            "raw_credentials_persisted": False,
        },
        "matrix": {
            "path": matrix_evidence,
            "matrix_id": matrix_report.get("matrix_id"),
            "sha256": matrix_sha256,
            "matrix_verified": True,
        },
        "runtime": {
            "server": runtime.get("source", {}).get("server")
            if isinstance(runtime.get("source"), dict)
            else None,
            "smoke_id": runtime.get("smoke_id"),
            "fingerprint_sha256": (
                runtime.get("runtime_fingerprint", {}).get("sha256")
                if isinstance(runtime.get("runtime_fingerprint"), dict)
                else None
            ),
        },
        "tools": tool_reports,
        "blocking_reasons": list(
            dict.fromkeys(blockers)
        ),
        "scope": "least_privilege_security_scheme_contract",
        "warnings": [
            (
                "M1.8 compares live per-tool securitySchemes with explicit "
                "scope evidence from a verified M1.7 credential matrix."
            ),
            (
                "Scope names are treated as permission labels, not secrets. "
                "Tokens and credential environment-variable names are never persisted."
            ),
            (
                "A successful profile proves that every declared OAuth scope "
                "for at least one advertised alternative must be contained in "
                "that profile's asserted scope set. An insufficient-scope case "
                "must not already satisfy an advertised OAuth alternative."
            ),
            (
                "Role, organization, row-level, or policy constraints that are "
                "not modeled as OAuth scopes should be excluded from insufficient_scope_cases."
            ),
        ],
    }

    if write_evidence:
        output = evidence_output or (
            f"{DEFAULT_EVIDENCE_DIR}/{gate_id}.json"
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
) -> tuple[
    dict[str, set[str]],
    list[dict[str, Any]],
]:
    raw_profiles = payload.get("profiles")
    if (
        not isinstance(raw_profiles, dict)
        or not raw_profiles
    ):
        raise SecuritySchemeGateError(
            "security scheme contract profiles must be a non-empty object"
        )

    profiles: dict[str, set[str]] = {}
    for profile_id, raw in raw_profiles.items():
        if (
            not isinstance(profile_id, str)
            or not profile_id.strip()
            or not isinstance(raw, dict)
        ):
            raise SecuritySchemeGateError(
                "security scheme profile ids must map to objects"
            )
        if set(raw) != {"scopes"}:
            raise SecuritySchemeGateError(
                f"security scheme profile {profile_id} supports only scopes"
            )
        scopes = raw.get("scopes")
        if (
            not isinstance(scopes, list)
            or not all(
                isinstance(item, str)
                and item.strip()
                for item in scopes
            )
        ):
            raise SecuritySchemeGateError(
                f"security scheme profile {profile_id} scopes must be a string list"
            )
        profiles[profile_id] = set(scopes)

    raw_tools = payload.get("tools")
    if (
        not isinstance(raw_tools, list)
        or not raw_tools
    ):
        raise SecuritySchemeGateError(
            "security scheme contract tools must be a non-empty list"
        )

    seen: set[str] = set()
    tools: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_tools):
        if not isinstance(raw, dict):
            raise SecuritySchemeGateError(
                f"security scheme tool policy {index} must be an object"
            )
        tool = raw.get("tool")
        access = raw.get("access")
        sufficient_cases = raw.get(
            "sufficient_cases",
            [],
        )
        insufficient_cases = raw.get(
            "insufficient_scope_cases",
            [],
        )

        if (
            not isinstance(tool, str)
            or not tool.strip()
        ):
            raise SecuritySchemeGateError(
                f"security scheme tool policy {index} tool is required"
            )
        if tool in seen:
            raise SecuritySchemeGateError(
                f"duplicate security scheme tool policy: {tool}"
            )
        seen.add(tool)
        if access not in VALID_ACCESS:
            raise SecuritySchemeGateError(
                f"security scheme tool {tool} has invalid access"
            )
        for label, values in (
            ("sufficient_cases", sufficient_cases),
            ("insufficient_scope_cases", insufficient_cases),
        ):
            if (
                not isinstance(values, list)
                or not all(
                    isinstance(item, str)
                    and item.strip()
                    for item in values
                )
            ):
                raise SecuritySchemeGateError(
                    f"security scheme tool {tool} {label} must be a string list"
                )
        if access != "noauth" and not sufficient_cases:
            raise SecuritySchemeGateError(
                f"security scheme tool {tool} requires at least one sufficient case"
            )
        tools.append(
            {
                "tool": tool,
                "access": access,
                "sufficient_cases": list(
                    dict.fromkeys(
                        sufficient_cases
                    )
                ),
                "insufficient_scope_cases": list(
                    dict.fromkeys(
                        insufficient_cases
                    )
                ),
            }
        )
    return profiles, tools


def _normalize_security_schemes(
    raw: Any,
) -> list[dict[str, Any]]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        return [
            {
                "type": "invalid",
                "scopes": [],
            }
        ]

    normalized: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            normalized.append(
                {
                    "type": "invalid",
                    "scopes": [],
                }
            )
            continue
        kind = item.get("type")
        if kind == "noauth":
            normalized.append(
                {
                    "type": "noauth",
                    "scopes": [],
                }
            )
        elif kind == "oauth2":
            scopes = item.get("scopes", [])
            normalized.append(
                {
                    "type": "oauth2",
                    "scopes": sorted(
                        {
                            scope
                            for scope in scopes
                            if isinstance(scope, str)
                            and scope.strip()
                        }
                    ) if isinstance(scopes, list) else [],
                }
            )
        else:
            normalized.append(
                {
                    "type": (
                        str(kind)
                        if kind is not None
                        else "invalid"
                    ),
                    "scopes": [],
                }
            )
    return normalized


def _check_access_mode(
    schemes: list[dict[str, Any]],
    access: str,
) -> list[str]:
    blockers: list[str] = []
    has_noauth = any(
        item.get("type") == "noauth"
        for item in schemes
    )
    has_oauth = any(
        item.get("type") == "oauth2"
        for item in schemes
    )
    has_invalid = any(
        item.get("type")
        not in {"noauth", "oauth2"}
        for item in schemes
    )
    if has_invalid:
        blockers.append(
            "unsupported_security_scheme"
        )
    if access == "oauth_required":
        if not has_oauth:
            blockers.append(
                "oauth2_scheme_required"
            )
        if has_noauth:
            blockers.append(
                "noauth_scheme_not_allowed"
            )
    elif access == "optional_auth":
        if not has_oauth:
            blockers.append(
                "oauth2_scheme_required"
            )
        if not has_noauth:
            blockers.append(
                "noauth_scheme_required"
            )
    elif access == "noauth":
        if not has_noauth:
            blockers.append(
                "noauth_scheme_required"
            )
        if has_oauth:
            blockers.append(
                "oauth2_scheme_not_expected"
            )
    return blockers


def _check_scope_evidence(
    *,
    tool_name: str,
    schemes: list[dict[str, Any]],
    policy: dict[str, Any],
    profiles: dict[str, set[str]],
    matrix_cases: dict[str, dict[str, Any]],
) -> tuple[
    list[str],
    dict[str, Any],
]:
    blockers: list[str] = []
    oauth_sets = [
        set(item.get("scopes", []))
        for item in schemes
        if item.get("type") == "oauth2"
    ]

    sufficient: list[dict[str, Any]] = []
    insufficient: list[dict[str, Any]] = []

    for case_id in policy["sufficient_cases"]:
        case = matrix_cases.get(case_id)
        if not isinstance(case, dict):
            blockers.append(
                f"sufficient_case_missing:{case_id}"
            )
            continue
        if case.get("tool") != tool_name:
            blockers.append(
                f"sufficient_case_tool_mismatch:{case_id}"
            )
            continue
        profile_id = case.get("credential")
        scopes = profiles.get(profile_id)
        if scopes is None:
            blockers.append(
                f"sufficient_case_profile_missing:{case_id}"
            )
            continue
        observation = case.get("observation")
        outcome = (
            observation.get("outcome")
            if isinstance(observation, dict)
            else None
        )
        if outcome != "success":
            blockers.append(
                f"sufficient_case_not_success:{case_id}"
            )
        compatible = (
            True
            if policy["access"] == "noauth"
            else any(
                declared.issubset(scopes)
                for declared in oauth_sets
            )
        )
        if not compatible:
            blockers.append(
                f"declared_scope_not_supported_by_success:{case_id}"
            )
        sufficient.append(
            {
                "case_id": case_id,
                "profile": profile_id,
                "scopes": sorted(scopes),
                "outcome": outcome,
                "compatible": compatible,
            }
        )

    for case_id in policy[
        "insufficient_scope_cases"
    ]:
        case = matrix_cases.get(case_id)
        if not isinstance(case, dict):
            blockers.append(
                f"insufficient_case_missing:{case_id}"
            )
            continue
        if case.get("tool") != tool_name:
            blockers.append(
                f"insufficient_case_tool_mismatch:{case_id}"
            )
            continue
        profile_id = case.get("credential")
        scopes = profiles.get(profile_id)
        if scopes is None:
            blockers.append(
                f"insufficient_case_profile_missing:{case_id}"
            )
            continue
        observation = case.get("observation")
        outcome = (
            observation.get("outcome")
            if isinstance(observation, dict)
            else None
        )
        if outcome == "success":
            blockers.append(
                f"insufficient_scope_case_succeeded:{case_id}"
            )
        already_satisfies = (
            any(
                declared.issubset(scopes)
                for declared in oauth_sets
            )
            if oauth_sets
            else False
        )
        if already_satisfies:
            blockers.append(
                f"runtime_requires_undeclared_permission:{case_id}"
            )
        insufficient.append(
            {
                "case_id": case_id,
                "profile": profile_id,
                "scopes": sorted(scopes),
                "outcome": outcome,
                "satisfies_declared_scheme": already_satisfies,
            }
        )

    scheme_support: list[dict[str, Any]] = []
    for declared in oauth_sets:
        supporters = [
            item["case_id"]
            for item in sufficient
            if declared.issubset(
                set(item["scopes"])
            )
        ]
        scheme_support.append(
            {
                "scopes": sorted(declared),
                "supported_by_cases": supporters,
            }
        )
        if not supporters:
            blockers.append(
                "declared_oauth_alternative_has_no_success_evidence"
            )

    return blockers, {
        "oauth_scope_alternatives": [
            sorted(item)
            for item in oauth_sets
        ],
        "sufficient_cases": sufficient,
        "insufficient_scope_cases": insufficient,
        "scheme_support": scheme_support,
    }


def _gate_id(
    *,
    contract_sha256: str,
    matrix_sha256: str,
    runtime_fingerprint: Any,
    tools: list[dict[str, Any]],
) -> str:
    payload = {
        "contract_sha256": contract_sha256,
        "matrix_sha256": matrix_sha256,
        "runtime_fingerprint": runtime_fingerprint,
        "tools": [
            {
                "tool": item.get("tool"),
                "declared_security_sha256": item.get(
                    "declared_security_sha256"
                ),
                "blocking_reasons": item.get(
                    "blocking_reasons"
                ),
            }
            for item in tools
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
        label="security scheme evidence output",
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
            raise SecuritySchemeGateError(
                f"security scheme evidence target is not a file: {target}"
            )
        current = target.read_text(
            encoding="utf-8"
        )
        if current != rendered and not force:
            raise SecuritySchemeGateError(
                f"security scheme evidence differs at {target}; use --force to replace it"
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
        raise SecuritySchemeGateError(
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
        raise SecuritySchemeGateError(
            f"{label} must be a non-empty relative path"
        )
    candidate = Path(value)
    if (
        candidate.is_absolute()
        or ".." in candidate.parts
    ):
        raise SecuritySchemeGateError(
            f"{label} must stay inside the plugin root"
        )
    target = (
        root / candidate
    ).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise SecuritySchemeGateError(
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
        current = current / part
        if (
            current.exists()
            and current.is_symlink()
        ):
            raise SecuritySchemeGateError(
                f"refusing symlinked security scheme evidence target: {current}"
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
        raise SecuritySchemeGateError(
            f"unable to read {label} at {path}: {exc}"
        ) from exc
    if not isinstance(
        value,
        dict,
    ):
        raise SecuritySchemeGateError(
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
