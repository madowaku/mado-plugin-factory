from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .scanner import scan_candidate

PLUGIN_SCHEMA_URL = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SEMVER_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$")
HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")

PORTABLE_TOP_LEVEL_KEYS = (
    "author",
    "homepage",
    "repository",
    "license",
    "keywords",
)
INTERFACE_KEYS = (
    "displayName",
    "shortDescription",
    "longDescription",
    "developerName",
    "category",
    "capabilities",
    "websiteURL",
    "privacyPolicyURL",
    "termsOfServiceURL",
    "defaultPrompt",
    "brandColor",
    "composerIcon",
    "logo",
    "screenshots",
)


class ManifestError(ValueError):
    pass


def load_metadata(path: Path) -> dict[str, Any]:
    path = path.expanduser().resolve()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ManifestError(f"unable to read manifest metadata from {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ManifestError("manifest metadata must be a JSON object")
    return data


def compile_manifest(
    root: Path,
    *,
    metadata: dict[str, Any] | None = None,
    compatibility: bool = False,
) -> dict[str, Any]:
    root = root.expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise ManifestError(f"candidate path is not a directory: {root}")

    scan = scan_candidate(root)
    if scan["architecture"] == "not_ready":
        raise ManifestError("candidate has no discoverable Skill or configured MCP server")

    metadata = deepcopy(metadata or {})
    existing = _load_existing_portable(root)

    name = _first_nonempty(metadata.get("name"), existing.get("name"), root.name)
    version = _first_nonempty(metadata.get("version"), existing.get("version"), "0.1.0")
    description = _first_nonempty(
        metadata.get("description"),
        existing.get("description"),
        _inferred_description(scan),
    )
    if not description:
        raise ManifestError("description is required; provide metadata.description or a described Skill")

    manifest: dict[str, Any] = {
        "$schema": PLUGIN_SCHEMA_URL,
        "name": name,
        "version": version,
        "description": description,
    }

    for key in PORTABLE_TOP_LEVEL_KEYS:
        value = metadata[key] if key in metadata else existing.get(key)
        if value not in (None, "", [], {}):
            manifest[key] = deepcopy(value)

    interface_seed: dict[str, Any] = {}
    existing_interface = _portable_interface(existing)
    if existing_interface:
        interface_seed.update(existing_interface)
    supplied_interface = metadata.get("interface")
    if supplied_interface is not None:
        if not isinstance(supplied_interface, dict):
            raise ManifestError("metadata.interface must be a JSON object")
        interface_seed.update(supplied_interface)

    interface = _compile_interface(
        name=name,
        description=description,
        supplied=interface_seed,
    )
    openai_extension: dict[str, Any] = {"interface": interface}

    apps_path = metadata.get("apps")
    if apps_path is None and scan["components"]["apps"]["path"]:
        apps_path = "./.app.json"
    if apps_path:
        openai_extension["apps"] = apps_path

    hooks_value = metadata.get("hooks")
    if hooks_value is None and scan["components"]["hooks"]["present"] and (root / "hooks" / "hooks.json").is_file():
        hooks_value = "./hooks/hooks.json"
    if hooks_value:
        openai_extension["hooks"] = deepcopy(hooks_value)

    manifest["extensions"] = {"com.openai": openai_extension}

    validation = validate_manifest(manifest, root=root)
    compat_manifest = None
    compat_warnings: list[dict[str, str]] = []
    if compatibility:
        compat_manifest, compat_warnings = _compile_compatibility_manifest(
            manifest=manifest,
            scan=scan,
            root=root,
        )

    return {
        "schema_version": "0.2",
        "source": {"root": str(root), "architecture": scan["architecture"]},
        "manifest": manifest,
        "compatibility_manifest": compat_manifest,
        "validation": {
            **validation,
            "warnings": validation["warnings"] + compat_warnings,
        },
    }


def write_compiled_manifest(
    root: Path,
    report: dict[str, Any],
    *,
    compatibility: bool = False,
    force: bool = False,
) -> dict[str, str]:
    root = root.expanduser().resolve()
    validation = report.get("validation") or {}
    if not validation.get("valid"):
        raise ManifestError("refusing to write an invalid manifest")

    outputs = [(root / "plugin.json", report["manifest"])]
    if compatibility:
        compat = report.get("compatibility_manifest")
        if compat is None:
            raise ManifestError("compatibility output was requested but was not compiled")
        outputs.append((root / ".codex-plugin" / "plugin.json", compat))

    for path, payload in outputs:
        rendered = _render_json(payload)
        if path.exists():
            current = path.read_text(encoding="utf-8")
            if current == rendered:
                continue
            if not force:
                raise ManifestError(f"refusing to overwrite existing {path}; use --force")

    written: dict[str, str] = {}
    for path, payload in outputs:
        path.parent.mkdir(parents=True, exist_ok=True)
        rendered = _render_json(payload)
        if not path.exists() or path.read_text(encoding="utf-8") != rendered:
            path.write_text(rendered, encoding="utf-8")
        written[path.relative_to(root).as_posix()] = "written"
    return written


def validate_manifest(manifest: dict[str, Any], *, root: Path | None = None) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []

    def error(code: str, message: str) -> None:
        errors.append({"code": code, "message": message})

    def warn(code: str, message: str) -> None:
        warnings.append({"code": code, "message": message})

    if manifest.get("$schema") != PLUGIN_SCHEMA_URL:
        error("schema_invalid", f"$schema must be {PLUGIN_SCHEMA_URL}")

    name = manifest.get("name")
    if not isinstance(name, str) or not NAME_RE.fullmatch(name):
        error("name_invalid", "name must be stable kebab-case using lowercase letters, digits, and hyphens")

    version = manifest.get("version")
    if not isinstance(version, str) or not SEMVER_RE.fullmatch(version):
        error("version_invalid", "version must be semantic version text such as 0.1.0")

    description = manifest.get("description")
    if not isinstance(description, str) or not description.strip():
        error("description_missing", "description must be a non-empty string")

    author = manifest.get("author")
    if author is not None:
        if not isinstance(author, dict):
            error("author_invalid", "author must be an object")
        else:
            if "name" in author and (not isinstance(author["name"], str) or not author["name"].strip()):
                error("author_name_invalid", "author.name must be non-empty when provided")
            if "email" in author and (not isinstance(author["email"], str) or "@" not in author["email"]):
                error("author_email_invalid", "author.email must look like an email address")
            if "url" in author and not _valid_http_url(author["url"]):
                error("author_url_invalid", "author.url must be an http(s) URL")

    for key in ("homepage", "repository"):
        value = manifest.get(key)
        if value is not None and not _valid_http_url(value):
            error(f"{key}_invalid", f"{key} must be an http(s) URL")

    keywords = manifest.get("keywords")
    if keywords is not None:
        if not isinstance(keywords, list) or not all(isinstance(x, str) and x.strip() for x in keywords):
            error("keywords_invalid", "keywords must be a list of non-empty strings")

    extensions = manifest.get("extensions")
    if not isinstance(extensions, dict):
        error("extensions_missing", "extensions must contain com.openai metadata")
        openai_ext = None
    else:
        openai_ext = extensions.get("com.openai")
        if not isinstance(openai_ext, dict):
            error("openai_extension_missing", "extensions.com.openai must be an object")
            openai_ext = None

    if openai_ext is not None:
        _validate_component_path(openai_ext.get("apps"), "apps", error)
        hooks = openai_ext.get("hooks")
        if isinstance(hooks, list):
            for idx, item in enumerate(hooks):
                if isinstance(item, str):
                    _validate_component_path(item, f"hooks[{idx}]", error)
        elif isinstance(hooks, str):
            _validate_component_path(hooks, "hooks", error)

        interface = openai_ext.get("interface")
        if not isinstance(interface, dict):
            error("interface_missing", "extensions.com.openai.interface must be an object")
        else:
            _validate_interface(interface, error, warn)

    if root is not None and openai_ext is not None:
        root = root.resolve()
        for key in ("apps",):
            value = openai_ext.get(key)
            if isinstance(value, str) and _valid_component_path(value):
                target = root / value[2:]
                if not target.is_file():
                    error(f"{key}_file_missing", f"{value} does not exist in the candidate root")
        hooks = openai_ext.get("hooks")
        if isinstance(hooks, str) and _valid_component_path(hooks):
            target = root / hooks[2:]
            if not target.is_file():
                error("hooks_file_missing", f"{hooks} does not exist in the candidate root")

    return {"valid": not errors, "errors": errors, "warnings": warnings}


def _compile_interface(*, name: str, description: str, supplied: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "displayName": supplied.get("displayName") or _display_name(name),
        "shortDescription": supplied.get("shortDescription") or description,
        "longDescription": supplied.get("longDescription") or description,
    }
    for key in INTERFACE_KEYS:
        if key in {"displayName", "shortDescription", "longDescription"}:
            continue
        value = supplied.get(key)
        if value not in (None, "", [], {}):
            result[key] = deepcopy(value)
    return result


def _compile_compatibility_manifest(*, manifest: dict[str, Any], scan: dict[str, Any], root: Path) -> tuple[dict[str, Any], list[dict[str, str]]]:
    result: dict[str, Any] = {
        "name": manifest["name"],
        "version": manifest["version"],
        "description": manifest["description"],
    }
    for key in PORTABLE_TOP_LEVEL_KEYS:
        if key in manifest:
            result[key] = deepcopy(manifest[key])

    if scan["skills"]:
        result["skills"] = "./skills/"

    legacy_mcp = scan["components"]["mcp"]["legacy"]
    warnings: list[dict[str, str]] = []
    if legacy_mcp and legacy_mcp.get("server_count", 0) > 0:
        result["mcpServers"] = "./.mcp.json"
    elif scan["components"]["mcp"]["portable"] and scan["components"]["mcp"]["portable"].get("server_count", 0) > 0:
        warnings.append(
            {
                "code": "compat_mcp_not_emitted",
                "message": "Portable mcp.json is canonical; compatibility mcpServers was not emitted because .mcp.json is absent.",
            }
        )

    openai_ext = manifest["extensions"]["com.openai"]
    for key in ("apps", "hooks"):
        if key in openai_ext:
            result[key] = deepcopy(openai_ext[key])
    result["interface"] = deepcopy(openai_ext["interface"])
    return result, warnings


def _validate_interface(interface: dict[str, Any], error, warn) -> None:
    display = interface.get("displayName")
    if not isinstance(display, str) or not display.strip():
        error("display_name_missing", "interface.displayName is required")
    elif len(display) > 80:
        error("display_name_too_long", "interface.displayName must be 80 characters or fewer for package validation")
    elif len(display) > 30:
        warn("display_name_directory_limit", "interface.displayName exceeds the 30-character final directory limit")

    short = interface.get("shortDescription")
    if not isinstance(short, str) or not short.strip():
        error("short_description_missing", "interface.shortDescription is required")
    elif "\n" in short or "\r" in short:
        error("short_description_multiline", "interface.shortDescription must fit on one line")
    elif len(short) > 240:
        error("short_description_too_long", "interface.shortDescription must be 240 characters or fewer for package validation")
    elif len(short) > 30:
        warn("short_description_directory_limit", "interface.shortDescription exceeds the 30-character final directory limit")

    long_desc = interface.get("longDescription")
    if long_desc is not None and (not isinstance(long_desc, str) or not long_desc.strip()):
        error("long_description_invalid", "interface.longDescription must be a non-empty string when provided")

    for key in ("developerName", "category"):
        value = interface.get(key)
        if value is not None and (not isinstance(value, str) or not value.strip()):
            error(f"{key}_invalid", f"interface.{key} must be a non-empty string when provided")

    capabilities = interface.get("capabilities")
    if capabilities is not None and (
        not isinstance(capabilities, list)
        or not all(isinstance(x, str) and x.strip() for x in capabilities)
    ):
        error("capabilities_invalid", "interface.capabilities must be a list of non-empty strings")

    for key in ("websiteURL", "privacyPolicyURL", "termsOfServiceURL"):
        value = interface.get(key)
        if value is not None:
            if not _valid_http_url(value):
                error(f"{key}_invalid", f"interface.{key} must be an http(s) URL")
            elif len(value) > 2048:
                error(f"{key}_too_long", f"interface.{key} must be 2048 characters or fewer")
            elif len(value) > 1024:
                warn(f"{key}_directory_limit", f"interface.{key} exceeds the 1024-character final directory limit")

    prompts = interface.get("defaultPrompt")
    if prompts is not None and (
        not isinstance(prompts, list)
        or not prompts
        or not all(isinstance(x, str) and x.strip() for x in prompts)
    ):
        error("default_prompt_invalid", "interface.defaultPrompt must be a non-empty list of non-empty strings")

    color = interface.get("brandColor")
    if color is not None and (not isinstance(color, str) or not HEX_COLOR_RE.fullmatch(color)):
        error("brand_color_invalid", "interface.brandColor must be a six-digit hex color such as #10A37F")

    for key in ("composerIcon", "logo"):
        value = interface.get(key)
        if value is not None:
            _validate_component_path(value, f"interface.{key}", error)
    screenshots = interface.get("screenshots")
    if screenshots is not None:
        if not isinstance(screenshots, list) or not screenshots:
            error("screenshots_invalid", "interface.screenshots must be a non-empty list")
        else:
            for idx, value in enumerate(screenshots):
                _validate_component_path(value, f"interface.screenshots[{idx}]", error)


def _validate_component_path(value: Any, label: str, error) -> None:
    if value is None:
        return
    if not isinstance(value, str) or not _valid_component_path(value):
        error(f"{label.replace('.', '_')}_path_invalid", f"{label} must be a ./-prefixed path that stays inside the plugin root")


def _valid_component_path(value: str) -> bool:
    if not value.startswith("./") or "\\" in value:
        return False
    parts = Path(value[2:]).parts
    return bool(parts) and all(part not in {"", ".", ".."} for part in parts)


def _valid_http_url(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc) and not parsed.username and not parsed.password


def _load_existing_portable(root: Path) -> dict[str, Any]:
    path = root / "plugin.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _portable_interface(manifest: dict[str, Any]) -> dict[str, Any]:
    extensions = manifest.get("extensions")
    if not isinstance(extensions, dict):
        return {}
    openai_ext = extensions.get("com.openai")
    if not isinstance(openai_ext, dict):
        return {}
    interface = openai_ext.get("interface")
    return deepcopy(interface) if isinstance(interface, dict) else {}


def _inferred_description(scan: dict[str, Any]) -> str | None:
    skills = scan.get("skills") or []
    if len(skills) == 1:
        description = skills[0].get("description")
        if isinstance(description, str) and description.strip():
            return description.strip()
    return None


def _display_name(name: str) -> str:
    return " ".join(part.capitalize() for part in name.split("-") if part)


def _first_nonempty(*values: Any) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return None


def _render_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False) + "\n"
