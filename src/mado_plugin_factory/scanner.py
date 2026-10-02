from __future__ import annotations

import json
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

SCHEMA_VERSION = "0.1"

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
}

TEXT_EXTENSIONS = {
    ".md",
    ".txt",
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".sh",
    ".bash",
    ".zsh",
    ".ps1",
    ".json",
    ".toml",
    ".yaml",
    ".yml",
}

MAX_TEXT_BYTES = 512_000

AUTH_PATTERNS = [
    re.compile(r"\b(api[_-]?key|access[_-]?token|secret[_-]?key|oauth|bearer|authorization)\b", re.I),
    re.compile(r"\b[A-Z][A-Z0-9_]*(?:TOKEN|SECRET|API_KEY|ACCESS_KEY)\b"),
]
NETWORK_PATTERNS = [
    re.compile(r"https?://", re.I),
    re.compile(r"\b(requests\.|httpx\.|urllib\.|fetch\s*\(|curl\s+|wget\s+)", re.I),
]
DESTRUCTIVE_PATTERNS = [
    re.compile(r"\brm\s+-rf\b", re.I),
    re.compile(r"\b(shutil\.rmtree|os\.remove|os\.unlink|Path\([^\n]*\)\.unlink)\b"),
    re.compile(r"\b(delete|destroy|drop)\s+(?:file|directory|table|database|resource|account)s?\b", re.I),
]
USER_DATA_PATTERNS = [
    re.compile(r"\b(email|inbox|calendar|contacts?|messages?|customer records?|personal data|user data)\b", re.I),
]


class ScanError(ValueError):
    pass


@dataclass(frozen=True)
class TextFile:
    path: str
    text: str


def scan_candidate(root: Path) -> dict:
    root = root.expanduser().resolve()
    if not root.exists():
        raise ScanError(f"candidate path does not exist: {root}")
    if not root.is_dir():
        raise ScanError(f"candidate path is not a directory: {root}")

    files = list(_iter_files(root))
    rel_paths = {p.relative_to(root).as_posix() for p in files}
    text_files = [_read_text_file(root, p) for p in files if _is_text_candidate(p)]
    text_files = [f for f in text_files if f is not None]

    skills = _discover_skills(root, files)
    components = _discover_components(root, rel_paths)
    dependencies = _discover_dependencies(root, rel_paths, text_files)
    risk_flags = _discover_risks(text_files, components)

    has_skills = bool(skills)
    has_mcp = bool(components["mcp"]["configured"])
    architecture, reason = _classify(has_skills=has_skills, has_mcp=has_mcp)
    missing = _missing_requirements(architecture, components, skills)

    return {
        "schema_version": SCHEMA_VERSION,
        "source": {
            "root": str(root),
            "scanned_files": len(files),
        },
        "architecture": architecture,
        "architecture_reason": reason,
        "skills": skills,
        "components": components,
        "external_dependencies": dependencies,
        "risk_flags": risk_flags,
        "missing": missing,
    }


def _iter_files(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*"), key=lambda p: p.as_posix()):
        if not path.is_file() or path.is_symlink():
            continue
        try:
            rel_parts = path.relative_to(root).parts
        except ValueError:
            continue
        if any(part in IGNORED_DIRS for part in rel_parts[:-1]):
            continue
        yield path


def _is_text_candidate(path: Path) -> bool:
    return path.suffix.lower() in TEXT_EXTENSIONS or path.name in {
        "SKILL.md",
        "requirements.txt",
        "Dockerfile",
    }


def _read_text_file(root: Path, path: Path) -> TextFile | None:
    try:
        if path.stat().st_size > MAX_TEXT_BYTES:
            return None
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    return TextFile(path=path.relative_to(root).as_posix(), text=text)


def _discover_skills(root: Path, files: list[Path]) -> list[dict]:
    results: list[dict] = []
    for path in files:
        if path.name != "SKILL.md":
            continue
        rel_path = path.relative_to(root)
        if rel_path.parts and rel_path.parts[0] in {
            "tests",
            "test",
            "templates",
            "examples",
            "docs",
            "evidence",
            ".github",
        }:
            continue
        rel = rel_path.as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            text = ""
        metadata = _frontmatter_metadata(text)
        inferred = path.parent.name
        results.append(
            {
                "name": metadata.get("name") or inferred,
                "description": metadata.get("description") or "",
                "path": rel,
                "has_frontmatter": text.startswith("---\n") or text.startswith("---\r\n"),
            }
        )
    return sorted(results, key=lambda item: item["path"])


def _frontmatter_metadata(text: str) -> dict[str, str]:
    if not (text.startswith("---\n") or text.startswith("---\r\n")):
        return {}
    lines = text.splitlines()
    try:
        end = lines[1:].index("---") + 1
    except ValueError:
        return {}
    result: dict[str, str] = {}
    for line in lines[1:end]:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        if key in {"name", "description"}:
            result[key] = value.strip().strip("\"'")
    return result


def _discover_components(root: Path, rel_paths: set[str]) -> dict:
    portable_manifest = _json_summary(root / "plugin.json") if "plugin.json" in rel_paths else None
    compat_manifest = (
        _json_summary(root / ".codex-plugin" / "plugin.json")
        if ".codex-plugin/plugin.json" in rel_paths
        else None
    )

    portable_mcp = _mcp_summary(root / "mcp.json", portable=True) if "mcp.json" in rel_paths else None
    legacy_mcp = _mcp_summary(root / ".mcp.json", portable=False) if ".mcp.json" in rel_paths else None
    configured = bool((portable_mcp or {}).get("server_count") or (legacy_mcp or {}).get("server_count"))

    return {
        "manifest": {
            "portable": portable_manifest,
            "codex_compat": compat_manifest,
            "recommended": "plugin.json",
        },
        "mcp": {
            "portable": portable_mcp,
            "legacy": legacy_mcp,
            "configured": configured,
        },
        "apps": {
            "path": ".app.json" if ".app.json" in rel_paths else None,
        },
        "hooks": {
            "present": any(p == "hooks/hooks.json" or p.startswith("hooks/") for p in rel_paths),
        },
    }


def _json_summary(path: Path) -> dict:
    result = {
        "path": path.name if path.parent.name != ".codex-plugin" else ".codex-plugin/plugin.json",
        "valid_json": False,
    }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        result["error"] = exc.__class__.__name__
        return result
    result["valid_json"] = isinstance(data, dict)
    if isinstance(data, dict):
        for key in ("name", "version", "description", "$schema"):
            if key in data:
                result[key] = data[key]
    return result


def _mcp_summary(path: Path, *, portable: bool) -> dict:
    rel = "mcp.json" if portable else ".mcp.json"
    result = {"path": rel, "valid_json": False, "server_count": 0}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        result["error"] = exc.__class__.__name__
        return result
    result["valid_json"] = isinstance(data, dict)
    if not isinstance(data, dict):
        return result

    servers = data.get("mcpServers")
    result["server_count"] = len(servers) if isinstance(servers, dict) else 0
    return result


def _discover_dependencies(root: Path, rel_paths: set[str], text_files: list[TextFile]) -> list[dict]:
    deps: list[dict] = []

    if "requirements.txt" in rel_paths:
        text = (root / "requirements.txt").read_text(encoding="utf-8", errors="ignore")
        names = []
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("-"):
                continue
            names.append(re.split(r"[<>=!~\[]", line, 1)[0].strip())
        deps.append(
            {
                "kind": "python",
                "source": "requirements.txt",
                "packages": sorted(set(filter(None, names))),
            }
        )

    if "pyproject.toml" in rel_paths:
        packages: list[str] = []
        try:
            data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
            data = {}
        project = data.get("project") if isinstance(data, dict) else None
        raw = project.get("dependencies") if isinstance(project, dict) else None
        if isinstance(raw, list):
            for item in raw:
                if not isinstance(item, str):
                    continue
                name = re.split(r"[<>=!~; \[]", item, 1)[0].strip()
                if name:
                    packages.append(name)
        deps.append(
            {
                "kind": "python-manifest",
                "source": "pyproject.toml",
                "packages": sorted(set(packages)),
            }
        )

    if "package.json" in rel_paths:
        try:
            data = json.loads((root / "package.json").read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            data = {}
        packages: set[str] = set()
        if isinstance(data, dict):
            for key in ("dependencies", "optionalDependencies", "peerDependencies"):
                value = data.get(key)
                if isinstance(value, dict):
                    packages.update(value.keys())
        deps.append({"kind": "node", "source": "package.json", "packages": sorted(packages)})

    runtime_files = [f for f in text_files if _is_runtime_evidence(f.path)]
    network_evidence = sorted(
        {f.path for f in runtime_files if _matches_any(f.text, NETWORK_PATTERNS)}
    )
    if network_evidence:
        deps.append(
            {
                "kind": "network",
                "source": "static-scan",
                "evidence": network_evidence,
            }
        )

    return deps


def _discover_risks(text_files: list[TextFile], components: dict) -> list[dict]:
    risks: list[dict] = []
    runtime_files = [f for f in text_files if _is_runtime_evidence(f.path)]
    specs = [
        (
            "auth_or_secret_dependency",
            "medium",
            AUTH_PATTERNS,
            "Candidate references authentication, credentials, or secret material.",
        ),
        (
            "external_network",
            "medium",
            NETWORK_PATTERNS,
            "Candidate appears to access external network resources.",
        ),
        (
            "destructive_operation",
            "high",
            DESTRUCTIVE_PATTERNS,
            "Candidate contains a potentially destructive operation.",
        ),
        (
            "user_data_access",
            "medium",
            USER_DATA_PATTERNS,
            "Candidate references user or personal data surfaces.",
        ),
    ]
    for code, severity, patterns, reason in specs:
        evidence = sorted(
            {f.path for f in runtime_files if _matches_any(f.text, patterns)}
        )
        if evidence:
            risks.append(
                {
                    "code": code,
                    "severity": severity,
                    "reason": reason,
                    "evidence": evidence,
                }
            )

    if components["mcp"]["configured"]:
        risks.append(
            {
                "code": "mcp_runtime_dependency",
                "severity": "info",
                "reason": "Candidate declares one or more MCP servers; runtime/server review is required.",
                "evidence": [
                    x["path"]
                    for x in (
                        components["mcp"]["portable"],
                        components["mcp"]["legacy"],
                    )
                    if x and x.get("server_count", 0) > 0
                ],
            }
        )
    return risks


def _is_runtime_evidence(path: str) -> bool:
    """Limit risk heuristics to files that can describe or perform runtime behavior."""
    name = Path(path).name
    suffix = Path(path).suffix.lower()
    if name in {
        "SKILL.md",
        "mcp.json",
        ".mcp.json",
        ".app.json",
        "requirements.txt",
        "Dockerfile",
    }:
        return True
    return suffix in {
        ".py",
        ".js",
        ".ts",
        ".tsx",
        ".jsx",
        ".sh",
        ".bash",
        ".zsh",
        ".ps1",
    }


def _matches_any(text: str, patterns: list[re.Pattern[str]]) -> bool:
    return any(pattern.search(text) for pattern in patterns)


def _classify(*, has_skills: bool, has_mcp: bool) -> tuple[str, str]:
    if has_skills and has_mcp:
        return (
            "skills_plus_mcp",
            "At least one SKILL.md and one configured MCP server were detected.",
        )
    if has_skills:
        return (
            "skills_only",
            "At least one SKILL.md was detected and no configured MCP server was found.",
        )
    if has_mcp:
        return (
            "mcp_only",
            "Configured MCP server(s) were detected and no SKILL.md was found.",
        )
    return "not_ready", "No SKILL.md or configured MCP server was detected."


def _missing_requirements(architecture: str, components: dict, skills: list[dict]) -> list[dict]:
    missing: list[dict] = []
    if architecture == "not_ready":
        missing.append(
            {
                "code": "no_capability",
                "message": "Add at least one skill or a configured MCP server.",
            }
        )

    portable = components["manifest"]["portable"]
    if portable is None:
        missing.append(
            {
                "code": "portable_manifest_missing",
                "message": "Add root plugin.json for the recommended portable Agent Plugins package.",
            }
        )
    elif not portable.get("valid_json"):
        missing.append(
            {
                "code": "portable_manifest_invalid",
                "message": "Root plugin.json exists but is not a valid JSON object.",
            }
        )
    elif not portable.get("$schema"):
        missing.append(
            {
                "code": "portable_manifest_schema_missing",
                "message": "Declare the Agent Plugins $schema in root plugin.json.",
            }
        )

    for label in ("portable", "legacy"):
        mcp = components["mcp"][label]
        if mcp is not None and not mcp.get("valid_json"):
            missing.append(
                {
                    "code": f"{label}_mcp_manifest_invalid",
                    "message": f"{mcp['path']} exists but is not a valid JSON object.",
                }
            )

    invalid_skills = [
        skill["path"]
        for skill in skills
        if not skill["has_frontmatter"] or not skill["description"]
    ]
    if invalid_skills:
        missing.append(
            {
                "code": "skill_metadata_incomplete",
                "message": "Add YAML frontmatter with name and description to each skill.",
                "evidence": invalid_skills,
            }
        )
    return missing
