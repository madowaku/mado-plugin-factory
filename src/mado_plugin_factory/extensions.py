from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable

from .scanner import scan_candidate

SCHEMA_VERSION = "0.1"
DEFAULT_OUTPUT = "evidence/extensions/capabilities.json"

OFFICIAL_SOURCES = [
    "https://developers.openai.com/plugins/build/extensions",
    "https://github.com/openai/mcp-extensions/blob/main/docs/spec.md",
]

IGNORED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
    ".pytest_cache",
    "__pycache__",
    ".mypy_cache",
    ".ruff_cache",
    "evidence",
    "tests",
    "test",
    "templates",
    "examples",
    "docs",
    ".github",
}

RUNTIME_TEXT_EXTENSIONS = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".json",
    ".toml",
    ".yaml",
    ".yml",
    ".md",
}

MAX_TEXT_BYTES = 512_000

EXTENSIONS = [
    {
        "id": "sidebar_app",
        "label": "Sidebar app",
        "requires_mcp": True,
        "requires_ui": True,
        "platforms": ["desktop", "web", "ios", "android"],
        "contract": '_meta["openai/ui"]["entrypoints"] += {"type": "global"}',
    },
    {
        "id": "conversation_panel",
        "label": "Conversation panel",
        "requires_mcp": True,
        "requires_ui": True,
        "platforms": ["desktop", "web", "ios", "android"],
        "contract": '_meta["openai/ui"]["entrypoints"] += {"type": "thread"}',
    },
    {
        "id": "plugin_settings",
        "label": "Plugin settings",
        "requires_mcp": True,
        "requires_ui": False,
        "platforms": ["desktop", "web", "ios", "android"],
        "contract": 'capabilities["extensions"]["openai/settings"]',
    },
    {
        "id": "file_viewer_editor",
        "label": "File viewer/editor",
        "requires_mcp": True,
        "requires_ui": True,
        "platforms": ["desktop"],
        "contract": '_meta["openai/ui"]["entrypoints"] += {"type": "file", "extensions": [".ext"]}',
    },
    {
        "id": "display_modes",
        "label": "Display modes",
        "requires_mcp": True,
        "requires_ui": True,
        "platforms": ["desktop", "web", "ios", "android"],
        "contract": '_meta["openai/ui"]["availableDisplayModes"] / preferredDisplayMode',
    },
    {
        "id": "deep_links",
        "label": "Deep links",
        "requires_mcp": True,
        "requires_ui": True,
        "platforms": ["desktop", "web", "ios"],
        "contract": 'hostContext["openai/deepLink"]',
    },
    {
        "id": "model_app_context",
        "label": "Model-App Context",
        "requires_mcp": True,
        "requires_ui": True,
        "platforms": ["desktop", "web", "ios", "android"],
        "contract": "ui/update-model-context",
    },
    {
        "id": "composer_mentions",
        "label": "Composer mentions",
        "requires_mcp": True,
        "requires_ui": False,
        "platforms": ["desktop"],
        "contract": '_meta["openai/extensions"]["mentions/search"]',
    },
    {
        "id": "rich_forms",
        "label": "Rich forms",
        "requires_mcp": True,
        "requires_ui": False,
        "platforms": ["desktop", "web"],
        "contract": "OpenAI form elicitation",
    },
    {
        "id": "plugin_onboarding",
        "label": "Plugin onboarding",
        "requires_mcp": False,
        "requires_ui": False,
        "platforms": ["desktop", "web", "ios", "android"],
        "contract": 'plugin.json extensions["com.openai"]["onboardingSkill"]',
    },
]

MARKER_PATTERNS = {
    "mcp_app_ui": [
        re.compile(r"ui://", re.I),
        re.compile(r"resourceUri", re.I),
        re.compile(r"text/html;profile=mcp-app", re.I),
        re.compile(r"@modelcontextprotocol/ext-apps", re.I),
        re.compile(r"\bOpenAIExtensions\s*\(", re.I),
    ],
    "sidebar_app": [
        re.compile(r'["\']type["\']\s*:\s*["\']global["\']', re.I),
    ],
    "conversation_panel": [
        re.compile(r'["\']type["\']\s*:\s*["\']thread["\']', re.I),
    ],
    "file_viewer_editor": [
        re.compile(r'["\']type["\']\s*:\s*["\']file["\']', re.I),
    ],
    "plugin_settings": [
        re.compile(r"openai/settings", re.I),
        re.compile(r"\bSettingsCapability\b", re.I),
    ],
    "display_modes": [
        re.compile(r"availableDisplayModes", re.I),
        re.compile(r"preferredDisplayMode", re.I),
    ],
    "deep_links": [
        re.compile(r"openai/deepLink", re.I),
        re.compile(r"(?:chatgpt|codex)://plugins/", re.I),
    ],
    "model_app_context": [
        re.compile(r"ui/update-model-context", re.I),
        re.compile(r"openai/modelContext", re.I),
        re.compile(r"\bupdateModelContext\b", re.I),
    ],
    "composer_mentions": [
        re.compile(r"mentions/search", re.I),
        re.compile(r"\bmentions\.setHandler\b", re.I),
        re.compile(r"\bmentions\.search\b", re.I),
    ],
    "rich_forms": [
        re.compile(r"openai/elicitation", re.I),
        re.compile(r"\brequestedSchema\b", re.I),
        re.compile(r"x-openai-(?:thumbnail|suggestions|input)", re.I),
    ],
}

SDK_PACKAGES = {
    "@openai/mcp-extensions",
    "openai-mcp-extensions",
    "@modelcontextprotocol/ext-apps",
}


class ExtensionError(ValueError):
    pass


def compile_extension_capabilities(root: Path) -> dict:
    root = root.expanduser().resolve()
    if not root.exists():
        raise ExtensionError(f"candidate path does not exist: {root}")
    if not root.is_dir():
        raise ExtensionError(f"candidate path is not a directory: {root}")

    scan = scan_candidate(root)
    runtime_files = list(_iter_runtime_text(root))
    evidence = _detect_marker_evidence(runtime_files)
    onboarding = _detect_onboarding(root)

    if onboarding["declared"]:
        evidence["plugin_onboarding"] = ["plugin.json"]

    has_mcp = bool(scan["components"]["mcp"]["configured"])
    has_skills = bool(scan["skills"])
    has_ui = bool(scan["components"]["apps"]["path"] or evidence.get("mcp_app_ui"))
    sdk_packages = _detect_sdk_packages(scan)

    capabilities = []
    for spec in EXTENSIONS:
        capabilities.append(
            _compile_capability(
                spec,
                has_mcp=has_mcp,
                has_skills=has_skills,
                has_ui=has_ui,
                evidence=evidence,
                onboarding=onboarding,
            )
        )

    summary = {
        status: [item["id"] for item in capabilities if item["status"] == status]
        for status in ("detected", "eligible", "needs_input", "blocked")
    }
    summary["actionable_count"] = sum(
        len(summary[status]) for status in ("detected", "eligible", "needs_input")
    )

    warnings = [
        "Detection is static inspection only; it does not prove that an extension executed successfully in ChatGPT."
    ]
    if has_mcp and not sdk_packages:
        warnings.append(
            "No OpenAI MCP Extensions SDK package was detected. Raw protocol implementations may still be valid."
        )
    if any(item["id"] == "rich_forms" and item["status"] != "blocked" for item in capabilities):
        warnings.append(
            "OpenAI-registered MCP servers require MCP 2026-07-28 or later with MRTR for form elicitation."
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "evidence_state": "inspected",
        "source": {
            "root": str(root),
            "runtime_files_inspected": len(runtime_files),
        },
        "architecture": scan["architecture"],
        "prerequisites": {
            "mcp_server": has_mcp,
            "mcp_app_ui": has_ui,
            "packaged_skills": len(scan["skills"]),
            "sdk_packages_detected": sdk_packages,
            "onboarding": onboarding,
        },
        "capabilities": capabilities,
        "summary": summary,
        "warnings": warnings,
        "official_sources": OFFICIAL_SOURCES,
    }


def write_extension_report(
    root: Path,
    report: dict,
    *,
    output: str = DEFAULT_OUTPUT,
    force: bool = False,
) -> str:
    root = root.expanduser().resolve()
    target = _safe_output_path(root, output)
    if target.is_symlink():
        raise ExtensionError(f"refusing to write through symlink: {target}")

    content = (
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")

    if target.exists():
        current = target.read_bytes()
        if current == content:
            return target.relative_to(root).as_posix()
        if not force:
            raise ExtensionError(
                f"output already exists with different content: {target}; use --force to replace it"
            )

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    return target.relative_to(root).as_posix()


def _compile_capability(
    spec: dict,
    *,
    has_mcp: bool,
    has_skills: bool,
    has_ui: bool,
    evidence: dict[str, list[str]],
    onboarding: dict,
) -> dict:
    extension_id = spec["id"]
    blockers: list[str] = []
    requirements: list[str] = []
    detected_evidence = sorted(evidence.get(extension_id, []))

    if spec["requires_mcp"]:
        requirements.append("configured MCP server")
        if not has_mcp:
            blockers.append("mcp_server_missing")
    if spec["requires_ui"]:
        requirements.append("MCP App UI resource")
        if not has_ui:
            blockers.append("mcp_app_ui_missing")

    if extension_id == "plugin_onboarding":
        requirements.append("packaged onboarding Skill")
        if onboarding["declared"]:
            if onboarding["valid"]:
                status = "detected"
            else:
                status = "needs_input"
                blockers.extend(onboarding["blockers"])
        elif has_skills:
            status = "eligible"
        else:
            status = "blocked"
            blockers.append("packaged_skill_missing")
    elif detected_evidence:
        status = "detected"
    elif blockers:
        status = "blocked"
    elif extension_id == "file_viewer_editor":
        status = "needs_input"
        blockers.append("file_extensions_unspecified")
    elif extension_id == "deep_links" and not evidence.get("sidebar_app"):
        status = "needs_input"
        blockers.append("global_entrypoint_not_detected")
    else:
        status = "eligible"

    if extension_id == "rich_forms":
        requirements.append(
            "MCP 2026-07-28+ with MRTR when using an OpenAI-registered MCP server"
        )
    if extension_id == "composer_mentions":
        requirements.append('mention tool visibility includes "app"')
    if extension_id == "deep_links":
        requirements.append("global sidebar entrypoint")
    if extension_id == "file_viewer_editor":
        requirements.append("explicit file extensions such as .stl")

    return {
        "id": extension_id,
        "label": spec["label"],
        "status": status,
        "evidence": detected_evidence,
        "requirements": requirements,
        "blockers": sorted(set(blockers)),
        "platforms": spec["platforms"],
        "scaffold_contract": spec["contract"],
        "runtime_verified": False,
    }


def _detect_marker_evidence(files: list[tuple[str, str]]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for key, patterns in MARKER_PATTERNS.items():
        matched = []
        for path, text in files:
            if any(pattern.search(text) for pattern in patterns):
                matched.append(path)
        if matched:
            result[key] = sorted(set(matched))
    return result


def _detect_onboarding(root: Path) -> dict:
    path = root / "plugin.json"
    result = {
        "declared": False,
        "skill_path": None,
        "valid": False,
        "blockers": [],
    }
    if not path.exists():
        return result

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return result
    if not isinstance(data, dict):
        return result

    extensions = data.get("extensions")
    com_openai = extensions.get("com.openai") if isinstance(extensions, dict) else None
    raw = com_openai.get("onboardingSkill") if isinstance(com_openai, dict) else None
    if not isinstance(raw, str) or not raw.strip():
        return result

    result["declared"] = True
    result["skill_path"] = raw
    rel = raw.strip()
    if rel.startswith("./"):
        rel = rel[2:]
    candidate = Path(rel)
    if candidate.is_absolute() or ".." in candidate.parts:
        result["blockers"].append("onboarding_skill_path_invalid")
        return result

    resolved = (root / candidate).resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        result["blockers"].append("onboarding_skill_path_escapes_root")
        return result

    if not resolved.is_file() or resolved.name != "SKILL.md":
        result["blockers"].append("onboarding_skill_missing")
        return result

    result["valid"] = True
    return result


def _detect_sdk_packages(scan: dict) -> list[str]:
    packages: set[str] = set()
    for dep in scan.get("external_dependencies", []):
        raw = dep.get("packages")
        if isinstance(raw, list):
            packages.update(item for item in raw if isinstance(item, str))
    return sorted(packages & SDK_PACKAGES)


def _iter_runtime_text(root: Path) -> Iterable[tuple[str, str]]:
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        if not path.is_file() or path.is_symlink():
            continue
        rel = path.relative_to(root)
        if any(part in IGNORED_DIRS for part in rel.parts[:-1]):
            continue
        if path.suffix.lower() not in RUNTIME_TEXT_EXTENSIONS:
            continue
        try:
            if path.stat().st_size > MAX_TEXT_BYTES:
                continue
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        yield rel.as_posix(), text


def _safe_output_path(root: Path, output: str) -> Path:
    candidate = Path(output)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ExtensionError("output must be a relative path inside the candidate root")
    target = (root / candidate).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ExtensionError("output must stay inside the candidate root") from exc
    return target
