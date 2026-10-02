from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from .extensions import compile_extension_capabilities
from .manifest import validate_manifest
from .scaffold import DEFAULT_OUTPUT as DEFAULT_SCAFFOLD_OUTPUT

SCHEMA_VERSION = "0.1"
DEFAULT_SCAFFOLD = DEFAULT_SCAFFOLD_OUTPUT
DEFAULT_EVIDENCE_DIR = "evidence/patches/extensions"

ALLOWED_APPLY_PREFIXES = (
    "extensions/openai/",
    "skills/plugin-onboarding/",
)


class PatchError(ValueError):
    pass


def compile_extension_patch(
    root: Path,
    *,
    scaffold: str = DEFAULT_SCAFFOLD,
) -> dict[str, Any]:
    root = root.expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise PatchError(f"candidate path is not a directory: {root}")

    scaffold_dir = _safe_relative(root, scaffold, label="scaffold directory")
    if not scaffold_dir.is_dir():
        raise PatchError(f"scaffold directory does not exist: {scaffold_dir}")
    if scaffold_dir.is_symlink():
        raise PatchError("refusing symlinked scaffold directory")

    plan_path = scaffold_dir / "plan.json"
    if not plan_path.is_file() or plan_path.is_symlink():
        raise PatchError(f"scaffold plan does not exist: {plan_path}")
    scaffold_plan = _load_json_object(plan_path, "scaffold plan")
    _validate_scaffold_plan(scaffold_plan)

    apply_dir = scaffold_dir / "apply"
    if not apply_dir.is_dir() or apply_dir.is_symlink():
        raise PatchError(f"scaffold apply directory does not exist: {apply_dir}")

    operations: list[dict[str, Any]] = []
    rendered: dict[str, str] = {}
    preconditions: dict[str, str | None] = {}
    semantic_conflicts: list[dict[str, str]] = []

    apply_files = _collect_apply_files(apply_dir)
    manifest_patch = None
    for rel, source_path in apply_files:
        if rel == "manifest.patch.json":
            manifest_patch = _load_json_object(source_path, "manifest patch")
            continue
        if not any(rel.startswith(prefix) for prefix in ALLOWED_APPLY_PREFIXES):
            raise PatchError(f"unsupported scaffold apply path: {rel}")

        target = _safe_relative(root, rel, label="patch target")
        _reject_symlink_target(root, target)
        source_text = _read_utf8(source_path, f"scaffold source {rel}")
        promoted = _promote_text(rel, source_text)
        source_sha = _sha256(source_text.encode("utf-8"))
        after_sha = _sha256(promoted.encode("utf-8"))
        before_sha = _file_sha256(target) if target.is_file() else None

        if target.exists() and not target.is_file():
            raise PatchError(f"patch target exists but is not a file: {target}")

        if before_sha is None:
            action = "create"
            requires_force = False
        elif before_sha == after_sha:
            action = "unchanged"
            requires_force = False
        else:
            action = "replace"
            requires_force = True

        operations.append(
            {
                "path": rel,
                "action": action,
                "source_sha256": source_sha,
                "target_before_sha256": before_sha,
                "target_after_sha256": after_sha,
                "requires_force": requires_force,
            }
        )
        rendered[rel] = promoted
        preconditions[rel] = before_sha

    if manifest_patch is not None:
        manifest_path = root / "plugin.json"
        if not manifest_path.is_file() or manifest_path.is_symlink():
            raise PatchError("live plugin.json is required for manifest patching")
        live_manifest = _load_json_object(manifest_path, "plugin manifest")
        merged_manifest, conflicts = _deep_merge(live_manifest, manifest_patch)
        semantic_conflicts.extend(conflicts)
        before_text = manifest_path.read_text(encoding="utf-8")
        after_text = json.dumps(
            merged_manifest, ensure_ascii=False, indent=2, sort_keys=False
        ) + "\n"
        before_sha = _sha256(before_text.encode("utf-8"))
        after_sha = _sha256(after_text.encode("utf-8"))
        operations.append(
            {
                "path": "plugin.json",
                "action": "unchanged" if before_sha == after_sha else "merge_manifest",
                "source_sha256": _sha256(
                    json.dumps(
                        manifest_patch,
                        ensure_ascii=False,
                        sort_keys=True,
                    ).encode("utf-8")
                ),
                "target_before_sha256": before_sha,
                "target_after_sha256": after_sha,
                "requires_force": False,
            }
        )
        rendered["plugin.json"] = after_text
        preconditions["plugin.json"] = before_sha

    if not operations:
        raise PatchError("scaffold apply directory contains no patchable artifacts")

    canonical = {
        "scaffold_plan": scaffold_plan,
        "operations": operations,
        "semantic_conflicts": semantic_conflicts,
    }
    patch_id = _sha256(
        json.dumps(
            canonical,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )[:20]

    change_count = sum(
        1
        for item in operations
        if item["action"] in {"create", "replace", "merge_manifest"}
    )
    force_required = [
        item["path"] for item in operations if item.get("requires_force")
    ]
    apply_ready = not semantic_conflicts

    return {
        "schema_version": SCHEMA_VERSION,
        "evidence_state": "inspected",
        "patch_id": patch_id,
        "source": {
            "root": str(root),
            "scaffold": scaffold_dir.relative_to(root).as_posix(),
        },
        "scaffold_generated": list(scaffold_plan.get("generated") or []),
        "operations": operations,
        "semantic_conflicts": semantic_conflicts,
        "force_required": force_required,
        "apply_ready": apply_ready,
        "summary": {
            "operation_count": len(operations),
            "change_count": change_count,
            "conflict_count": len(semantic_conflicts),
            "force_required_count": len(force_required),
        },
        "source_applied": False,
        "runtime_verified": False,
        "_rendered": rendered,
        "_preconditions": preconditions,
    }


def apply_extension_patch(
    root: Path,
    report: dict[str, Any],
    *,
    force: bool = False,
    evidence_output: str | None = None,
) -> dict[str, Any]:
    root = root.expanduser().resolve()
    if report.get("evidence_state") != "inspected":
        raise PatchError("apply requires an inspected patch report")
    if not report.get("apply_ready"):
        raise PatchError("patch plan has semantic conflicts and cannot be applied")

    rendered = report.get("_rendered")
    preconditions = report.get("_preconditions")
    if not isinstance(rendered, dict) or not isinstance(preconditions, dict):
        raise PatchError("patch report is missing internal rendered/precondition data")

    force_required = report.get("force_required") or []
    if force_required and not force:
        raise PatchError(
            "differing generated files require --force: "
            + ", ".join(force_required)
        )

    for rel, expected in sorted(preconditions.items()):
        target = _safe_relative(root, rel, label="patch target")
        _reject_symlink_target(root, target)
        current = _file_sha256(target) if target.is_file() else None
        if current != expected:
            raise PatchError(
                f"patch target changed since planning: {rel}; re-run mpf patch"
            )

    written: list[str] = []
    unchanged: list[str] = []
    for operation in report["operations"]:
        rel = operation["path"]
        target = _safe_relative(root, rel, label="patch target")
        content = rendered[rel]
        data = content.encode("utf-8")
        current = target.read_bytes() if target.is_file() else None
        if current == data:
            unchanged.append(rel)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        written.append(rel)

    post = compile_extension_capabilities(root)
    by_id = {item["id"]: item for item in post["capabilities"]}
    expected_ids = sorted(set(report.get("scaffold_generated") or []))
    detected = [
        extension_id
        for extension_id in expected_ids
        if by_id.get(extension_id, {}).get("status") == "detected"
    ]
    not_detected = [
        extension_id
        for extension_id in expected_ids
        if extension_id not in detected
    ]

    manifest = _load_json_object(root / "plugin.json", "plugin manifest")
    manifest_validation = validate_manifest(manifest, root=root)

    result = public_patch_report(report)
    result.update(
        {
            "evidence_state": "executed",
            "applied": True,
            "source_applied": True,
            "runtime_verified": False,
            "written": written,
            "unchanged": unchanged,
            "post_apply": {
                "verified": not not_detected and manifest_validation["valid"],
                "detected": detected,
                "not_detected": not_detected,
                "manifest_valid": manifest_validation["valid"],
                "manifest_errors": manifest_validation["errors"],
            },
        }
    )

    evidence_path = evidence_output or (
        f"{DEFAULT_EVIDENCE_DIR}/{report['patch_id']}.json"
    )
    target = _safe_relative(
        root,
        evidence_path,
        label="patch evidence output",
    )
    _reject_symlink_target(root, target)
    evidence_text = (
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    if target.exists():
        current = target.read_text(encoding="utf-8")
        if current != evidence_text and not force:
            raise PatchError(
                f"patch evidence differs at {target}; use --force to replace it"
            )
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists() or target.read_text(encoding="utf-8") != evidence_text:
        target.write_text(evidence_text, encoding="utf-8")
    result["evidence_output"] = target.relative_to(root).as_posix()
    return result


def public_patch_report(report: dict[str, Any]) -> dict[str, Any]:
    return {
        key: deepcopy(value)
        for key, value in report.items()
        if key not in {"_rendered", "_preconditions"}
    }


def _validate_scaffold_plan(plan: dict[str, Any]) -> None:
    if plan.get("evidence_state") != "generated":
        raise PatchError("scaffold plan must be generated evidence")
    if plan.get("apply_mode") != "proposal_only":
        raise PatchError("scaffold plan must be proposal_only")
    if plan.get("runtime_modified") is not False:
        raise PatchError("scaffold plan must not claim prior runtime mutation")
    generated = plan.get("generated")
    if not isinstance(generated, list) or not generated:
        raise PatchError("scaffold plan has no generated extensions")


def _collect_apply_files(apply_dir: Path) -> list[tuple[str, Path]]:
    result: list[tuple[str, Path]] = []
    for path in sorted(
        apply_dir.rglob("*"),
        key=lambda item: item.as_posix(),
    ):
        if path.is_symlink():
            raise PatchError(f"refusing symlinked scaffold artifact: {path}")
        if not path.is_file():
            continue
        rel = path.relative_to(apply_dir).as_posix()
        result.append((rel, path))
    return result


def _promote_text(rel: str, text: str) -> str:
    if rel.startswith("extensions/openai/") and rel.endswith(".ts"):
        old = (
            "// Generated by MADO Plugin Factory MPF-M0.7.\n"
            "// Proposal only: copy/adapt this contract into your active MCP/App code after review.\n"
            "// Generated evidence is not runtime verification.\n\n"
        )
        new = (
            "// Applied by MADO Plugin Factory MPF-M0.8.\n"
            "// Active source contract module; integrate it with the real MCP/App runtime after review.\n"
            "// Source application is not runtime verification.\n\n"
        )
        if text.startswith(old):
            return new + text[len(old):]
    return text


def _deep_merge(
    existing: dict[str, Any],
    patch: dict[str, Any],
    *,
    path: tuple[str, ...] = (),
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    result = deepcopy(existing)
    conflicts: list[dict[str, str]] = []
    for key, patch_value in patch.items():
        key_path = path + (str(key),)
        dotted = ".".join(key_path)
        if key not in result:
            result[key] = deepcopy(patch_value)
            continue
        current = result[key]
        if isinstance(current, dict) and isinstance(patch_value, dict):
            merged, nested = _deep_merge(
                current,
                patch_value,
                path=key_path,
            )
            result[key] = merged
            conflicts.extend(nested)
        elif current == patch_value:
            continue
        else:
            conflicts.append(
                {
                    "path": dotted,
                    "reason": "existing_value_differs",
                }
            )
    return result, conflicts


def _safe_relative(root: Path, value: str, *, label: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise PatchError(f"{label} must be a non-empty relative path")
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise PatchError(f"{label} must stay inside the plugin root")
    target = (root / candidate).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise PatchError(f"{label} must stay inside the plugin root") from exc
    return target


def _reject_symlink_target(root: Path, target: Path) -> None:
    try:
        rel = target.relative_to(root)
    except ValueError as exc:
        raise PatchError("patch target escapes plugin root") from exc
    current = root
    for part in rel.parts:
        current = current / part
        if current.exists() and current.is_symlink():
            raise PatchError(f"refusing symlinked patch target: {current}")


def _load_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PatchError(f"unable to read {label} at {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise PatchError(f"{label} at {path} must be a JSON object")
    return value


def _read_utf8(path: Path, label: str) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise PatchError(f"unable to read {label}: {exc}") from exc


def _file_sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    return _sha256(path.read_bytes())


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
