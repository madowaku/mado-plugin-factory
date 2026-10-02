from __future__ import annotations

import hashlib
import json
import re
import shutil
from copy import deepcopy
from pathlib import Path
from typing import Any

from .manifest import validate_manifest

DEFAULT_MARKETPLACE_NAME = "local-repo"
DEFAULT_MARKETPLACE_DISPLAY_NAME = "Local Plugins"
DEFAULT_CATEGORY = "Productivity"
DEFAULT_INSTALLATION = "AVAILABLE"
DEFAULT_AUTHENTICATION = "ON_INSTALL"
DEFAULT_CACHE_ROOT = "~/.codex/plugins/cache"
DEFAULT_EVIDENCE_OUTPUT = "evidence/marketplace/install-verification.json"

MARKETPLACE_NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
INSTALLATION_VALUES = {"AVAILABLE", "INSTALLED_BY_DEFAULT", "NOT_AVAILABLE"}
AUTHENTICATION_VALUES = {"ON_INSTALL", "ON_FIRST_USE", "NONE"}

PACKAGE_FILES = (
    "plugin.json",
    "mcp.json",
    ".mcp.json",
    ".app.json",
)
PACKAGE_DIRS = (
    "skills",
    "hooks",
    "assets",
)
COMPAT_MANIFEST = ".codex-plugin/plugin.json"


class MarketplaceError(ValueError):
    pass


def compile_marketplace_bridge(
    plugin_root: Path,
    marketplace_root: Path,
    *,
    marketplace_name: str = DEFAULT_MARKETPLACE_NAME,
    marketplace_display_name: str = DEFAULT_MARKETPLACE_DISPLAY_NAME,
    category: str | None = None,
    installation: str = DEFAULT_INSTALLATION,
    authentication: str = DEFAULT_AUTHENTICATION,
) -> dict[str, Any]:
    plugin_root = plugin_root.expanduser().resolve()
    marketplace_root = marketplace_root.expanduser().resolve()
    manifest = _load_plugin_manifest(plugin_root)
    manifest_validation = validate_manifest(manifest, root=plugin_root)
    if not manifest_validation["valid"]:
        raise MarketplaceError(
            "plugin.json is not valid enough for marketplace bridging: "
            + "; ".join(item["message"] for item in manifest_validation["errors"])
        )

    plugin_name = manifest["name"]
    interface = _openai_interface(manifest)
    display_name = interface.get("displayName") or _display_name(plugin_name)
    resolved_category = category or interface.get("category") or DEFAULT_CATEGORY

    entry = {
        "name": plugin_name,
        "source": {
            "source": "local",
            "path": f"./plugins/{plugin_name}",
        },
        "policy": {
            "installation": installation,
            "authentication": authentication,
        },
        "category": resolved_category,
    }

    existing = _load_marketplace_if_present(marketplace_root)
    catalog = _merge_catalog(
        existing=existing,
        marketplace_name=marketplace_name,
        marketplace_display_name=marketplace_display_name,
        entry=entry,
    )
    validation = validate_marketplace_catalog(catalog, root=marketplace_root)

    package_files = _package_file_list(plugin_root)
    if not package_files:
        raise MarketplaceError("candidate contains no distributable plugin files")

    return {
        "schema_version": "0.4",
        "mode": "bridge",
        "source": {
            "plugin_root": str(plugin_root),
            "marketplace_root": str(marketplace_root),
            "manifest": "plugin.json",
        },
        "plugin": {
            "name": plugin_name,
            "display_name": display_name,
            "package_files": package_files,
            "package_digest": _package_digest(plugin_root),
        },
        "marketplace": {
            "name": marketplace_name,
            "display_name": marketplace_display_name,
            "catalog_path": ".agents/plugins/marketplace.json",
            "staged_plugin_path": f"plugins/{plugin_name}",
            "entry_source_path": f"./plugins/{plugin_name}",
            "catalog": catalog,
        },
        "evidence_state": "generated",
        "install_verified": False,
        "validation": validation,
        "next_actions": [
            f"Write the bridge, then restart ChatGPT desktop and choose marketplace '{marketplace_name}'.",
            f"Install '{plugin_name}' from that marketplace.",
            "Run mpf marketplace verify to inspect the installed cache copy.",
        ],
    }


def validate_marketplace_catalog(
    catalog: dict[str, Any],
    *,
    root: Path | None = None,
) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []

    def error(code: str, message: str) -> None:
        errors.append({"code": code, "message": message})

    name = catalog.get("name")
    if not isinstance(name, str) or not MARKETPLACE_NAME_RE.fullmatch(name):
        error("marketplace_name_invalid", "marketplace name must be stable kebab-case")

    interface = catalog.get("interface")
    if not isinstance(interface, dict):
        error("marketplace_interface_missing", "marketplace interface must be an object")
    else:
        display_name = interface.get("displayName")
        if not isinstance(display_name, str) or not display_name.strip():
            error("marketplace_display_name_missing", "interface.displayName is required")

    plugins = catalog.get("plugins")
    if not isinstance(plugins, list) or not plugins:
        error("plugins_missing", "marketplace plugins must be a non-empty list")
        plugins = []

    seen_names: set[str] = set()
    for idx, entry in enumerate(plugins):
        prefix = f"plugins[{idx}]"
        if not isinstance(entry, dict):
            error("plugin_entry_invalid", f"{prefix} must be an object")
            continue

        plugin_name = entry.get("name")
        if not isinstance(plugin_name, str) or not MARKETPLACE_NAME_RE.fullmatch(plugin_name):
            error("plugin_name_invalid", f"{prefix}.name must be kebab-case")
        elif plugin_name in seen_names:
            error("plugin_name_duplicate", f"{prefix}.name duplicates {plugin_name}")
        else:
            seen_names.add(plugin_name)

        source = entry.get("source")
        if isinstance(source, str):
            source_path = source
        elif isinstance(source, dict):
            if source.get("source") != "local":
                error(
                    "source_type_invalid",
                    f"{prefix}.source.source must be 'local' for a local bridge",
                )
            source_path = source.get("path")
        else:
            source_path = None
            error("source_missing", f"{prefix}.source is required")

        if source_path is not None:
            if not isinstance(source_path, str) or not _valid_relative_source_path(source_path):
                error(
                    "source_path_invalid",
                    f"{prefix}.source.path must start with ./ and stay inside the marketplace root",
                )
            elif root is not None:
                target = (root.resolve() / source_path[2:]).resolve()
                try:
                    target.relative_to(root.resolve())
                except ValueError:
                    error(
                        "source_path_escape",
                        f"{prefix}.source.path resolves outside the marketplace root",
                    )

        policy = entry.get("policy")
        if not isinstance(policy, dict):
            error("policy_missing", f"{prefix}.policy is required")
        else:
            installation = policy.get("installation")
            authentication = policy.get("authentication")
            if installation not in INSTALLATION_VALUES:
                error(
                    "installation_policy_invalid",
                    f"{prefix}.policy.installation must be one of {sorted(INSTALLATION_VALUES)}",
                )
            if authentication not in AUTHENTICATION_VALUES:
                error(
                    "authentication_policy_invalid",
                    f"{prefix}.policy.authentication must be one of {sorted(AUTHENTICATION_VALUES)}",
                )

        category = entry.get("category")
        if not isinstance(category, str) or not category.strip():
            error("category_missing", f"{prefix}.category is required")

    return {"valid": not errors, "errors": errors, "warnings": warnings}


def write_marketplace_bridge(
    plugin_root: Path,
    marketplace_root: Path,
    report: dict[str, Any],
    *,
    force: bool = False,
) -> dict[str, Any]:
    plugin_root = plugin_root.expanduser().resolve()
    marketplace_root = marketplace_root.expanduser().resolve()
    validation = report.get("validation") or {}
    if not validation.get("valid"):
        raise MarketplaceError("refusing to write an invalid marketplace bridge")

    expected_plugin_name = report["plugin"]["name"]
    staged_root = marketplace_root / "plugins" / expected_plugin_name
    catalog_path = marketplace_root / ".agents" / "plugins" / "marketplace.json"

    marketplace_root.mkdir(parents=True, exist_ok=True)
    stage_result = _stage_plugin(plugin_root, staged_root, force=force)
    catalog_result = _write_json_file(
        catalog_path,
        report["marketplace"]["catalog"],
        force=force,
    )

    return {
        "evidence_state": "executed",
        "staging": stage_result,
        "catalog": {
            "path": catalog_path.relative_to(marketplace_root).as_posix(),
            "status": catalog_result,
        },
        "marketplace_root": str(marketplace_root),
    }


def verify_marketplace_install(
    plugin_root: Path,
    marketplace_root: Path,
    *,
    marketplace_name: str = DEFAULT_MARKETPLACE_NAME,
    cache_root: Path | None = None,
    cache_version: str = "local",
) -> dict[str, Any]:
    plugin_root = plugin_root.expanduser().resolve()
    marketplace_root = marketplace_root.expanduser().resolve()
    cache_root = (
        (cache_root or Path(DEFAULT_CACHE_ROOT)).expanduser().resolve()
    )

    manifest = _load_plugin_manifest(plugin_root)
    plugin_name = manifest["name"]
    catalog_path = marketplace_root / ".agents" / "plugins" / "marketplace.json"
    if not catalog_path.is_file():
        raise MarketplaceError(f"marketplace catalog does not exist: {catalog_path}")

    catalog = _load_json_object(catalog_path, "marketplace catalog")
    validation = validate_marketplace_catalog(catalog, root=marketplace_root)
    matching = [
        entry
        for entry in catalog.get("plugins", [])
        if isinstance(entry, dict) and entry.get("name") == plugin_name
    ]

    catalog_entry_present = len(matching) == 1
    configured_source = (
        marketplace_root / "plugins" / plugin_name
    ).resolve()
    cache_path = (
        cache_root / marketplace_name / plugin_name / cache_version
    ).resolve()

    installed = cache_path.is_dir()
    cache_manifest_valid = False
    installed_name_matches = False
    content_match: bool | None = None
    source_digest: str | None = None
    cache_digest: str | None = None
    blockers: list[str] = []

    if not validation["valid"]:
        blockers.append("marketplace_catalog_invalid")
    if catalog.get("name") != marketplace_name:
        blockers.append("marketplace_name_mismatch")
    if not catalog_entry_present:
        blockers.append("plugin_entry_missing")
    if not configured_source.is_dir():
        blockers.append("staged_plugin_missing")

    if not installed:
        blockers.append("installed_cache_missing")
    else:
        installed_manifest_path = cache_path / "plugin.json"
        if installed_manifest_path.is_file():
            try:
                installed_manifest = _load_json_object(
                    installed_manifest_path,
                    "installed plugin manifest",
                )
                installed_validation = validate_manifest(
                    installed_manifest,
                    root=cache_path,
                )
                cache_manifest_valid = installed_validation["valid"]
                installed_name_matches = installed_manifest.get("name") == plugin_name
            except MarketplaceError:
                cache_manifest_valid = False

        if not cache_manifest_valid:
            blockers.append("installed_manifest_invalid")
        if cache_manifest_valid and not installed_name_matches:
            blockers.append("installed_plugin_name_mismatch")

        if configured_source.is_dir() and cache_manifest_valid and installed_name_matches:
            source_digest = _package_digest(configured_source)
            cache_digest = _package_digest(cache_path)
            content_match = source_digest == cache_digest
            if not content_match:
                blockers.append("installed_copy_differs_from_staged")

    install_verified = bool(
        installed
        and cache_manifest_valid
        and installed_name_matches
        and content_match is True
        and validation["valid"]
        and catalog_entry_present
    )

    return {
        "schema_version": "0.4",
        "mode": "verify",
        "evidence_state": "executed",
        "marketplace": {
            "name": marketplace_name,
            "root": str(marketplace_root),
            "catalog_path": str(catalog_path),
            "catalog_valid": validation["valid"],
            "plugin_entry_present": catalog_entry_present,
            "staged_plugin_path": str(configured_source),
        },
        "plugin": {
            "name": plugin_name,
            "source_digest": source_digest,
        },
        "cache": {
            "root": str(cache_root),
            "version": cache_version,
            "path": str(cache_path),
            "exists": installed,
            "manifest_valid": cache_manifest_valid,
            "plugin_name_matches": installed_name_matches,
            "digest": cache_digest,
            "content_match": content_match,
        },
        "install_verified": install_verified,
        "blocking_reasons": blockers,
    }


def write_install_evidence(
    plugin_root: Path,
    report: dict[str, Any],
    *,
    output: str = DEFAULT_EVIDENCE_OUTPUT,
    force: bool = False,
) -> dict[str, str]:
    plugin_root = plugin_root.expanduser().resolve()
    if report.get("mode") != "verify" or report.get("evidence_state") != "executed":
        raise MarketplaceError("install evidence must come from an executed verify report")

    target = _safe_output_path(plugin_root, output)
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=False) + "\n"
    if target.exists():
        current = target.read_text(encoding="utf-8")
        if current != rendered and not force:
            raise MarketplaceError(
                f"refusing to overwrite existing {target}; use --force"
            )

    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists() or target.read_text(encoding="utf-8") != rendered:
        target.write_text(rendered, encoding="utf-8")
    return {target.relative_to(plugin_root).as_posix(): "written"}


def _stage_plugin(source_root: Path, destination_root: Path, *, force: bool) -> dict[str, Any]:
    source_files = _package_file_list(source_root)
    if not source_files:
        raise MarketplaceError("no distributable plugin files found")

    if destination_root.is_symlink():
        raise MarketplaceError("refusing to stage into a symlink destination")

    if destination_root.exists():
        current_digest = _package_digest(destination_root)
        source_digest = _package_digest(source_root)
        if current_digest == source_digest:
            return {
                "path": str(destination_root),
                "status": "unchanged",
                "package_digest": source_digest,
                "files": source_files,
            }
        if not force:
            raise MarketplaceError(
                f"staged plugin differs at {destination_root}; use --force"
            )
        shutil.rmtree(destination_root)

    destination_root.mkdir(parents=True, exist_ok=True)
    for rel in source_files:
        src = source_root / rel
        dst = destination_root / rel
        if src.is_symlink():
            raise MarketplaceError(f"refusing to stage symlinked plugin file: {rel}")
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    return {
        "path": str(destination_root),
        "status": "written",
        "package_digest": _package_digest(destination_root),
        "files": source_files,
    }


def _package_file_list(root: Path) -> list[str]:
    root = root.resolve()
    files: list[str] = []

    for rel in PACKAGE_FILES:
        path = root / rel
        if path.is_file():
            if path.is_symlink():
                raise MarketplaceError(f"refusing symlinked plugin file: {rel}")
            files.append(rel)

    compat = root / COMPAT_MANIFEST
    if compat.is_file():
        if compat.is_symlink():
            raise MarketplaceError(f"refusing symlinked plugin file: {COMPAT_MANIFEST}")
        files.append(COMPAT_MANIFEST)

    for dirname in PACKAGE_DIRS:
        directory = root / dirname
        if not directory.exists():
            continue
        if directory.is_symlink():
            raise MarketplaceError(f"refusing symlinked plugin directory: {dirname}")
        if not directory.is_dir():
            raise MarketplaceError(f"plugin component is not a directory: {dirname}")
        for path in sorted(directory.rglob("*"), key=lambda p: p.as_posix()):
            if path.is_symlink():
                raise MarketplaceError(
                    f"refusing symlinked plugin content: {path.relative_to(root).as_posix()}"
                )
            if path.is_file():
                files.append(path.relative_to(root).as_posix())

    return sorted(set(files))


def _package_digest(root: Path) -> str:
    files = _package_file_list(root)
    digest = hashlib.sha256()
    for rel in files:
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        with (root / rel).open("rb") as handle:
            while True:
                chunk = handle.read(65536)
                if not chunk:
                    break
                digest.update(chunk)
        digest.update(b"\0")
    return digest.hexdigest()


def _load_plugin_manifest(plugin_root: Path) -> dict[str, Any]:
    path = plugin_root / "plugin.json"
    if not path.is_file():
        raise MarketplaceError(f"portable plugin manifest does not exist: {path}")
    return _load_json_object(path, "plugin manifest")


def _load_marketplace_if_present(root: Path) -> dict[str, Any] | None:
    path = root / ".agents" / "plugins" / "marketplace.json"
    if not path.is_file():
        return None
    return _load_json_object(path, "marketplace catalog")


def _merge_catalog(
    *,
    existing: dict[str, Any] | None,
    marketplace_name: str,
    marketplace_display_name: str,
    entry: dict[str, Any],
) -> dict[str, Any]:
    if not MARKETPLACE_NAME_RE.fullmatch(marketplace_name):
        raise MarketplaceError("marketplace name must be stable kebab-case")
    if not isinstance(marketplace_display_name, str) or not marketplace_display_name.strip():
        raise MarketplaceError("marketplace display name must be non-empty")

    if existing is None:
        plugins: list[dict[str, Any]] = []
    else:
        existing_name = existing.get("name")
        if existing_name != marketplace_name:
            raise MarketplaceError(
                f"existing marketplace name {existing_name!r} does not match {marketplace_name!r}"
            )
        raw_plugins = existing.get("plugins", [])
        if not isinstance(raw_plugins, list):
            raise MarketplaceError("existing marketplace plugins must be a list")
        plugins = [
            deepcopy(item)
            for item in raw_plugins
            if isinstance(item, dict) and item.get("name") != entry["name"]
        ]

    plugins.append(deepcopy(entry))
    return {
        "name": marketplace_name,
        "interface": {"displayName": marketplace_display_name},
        "plugins": plugins,
    }


def _write_json_file(path: Path, payload: dict[str, Any], *, force: bool) -> str:
    rendered = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False) + "\n"
    if path.exists():
        current = path.read_text(encoding="utf-8")
        if current == rendered:
            return "unchanged"
        if not force:
            raise MarketplaceError(f"refusing to overwrite existing {path}; use --force")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rendered, encoding="utf-8")
    return "written"


def _load_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MarketplaceError(f"unable to read {label} at {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise MarketplaceError(f"{label} at {path} must be a JSON object")
    return value


def _openai_interface(manifest: dict[str, Any]) -> dict[str, Any]:
    extensions = manifest.get("extensions")
    if not isinstance(extensions, dict):
        return {}
    openai_extension = extensions.get("com.openai")
    if not isinstance(openai_extension, dict):
        return {}
    interface = openai_extension.get("interface")
    return interface if isinstance(interface, dict) else {}


def _valid_relative_source_path(value: str) -> bool:
    if not value.startswith("./") or "\\" in value:
        return False
    parts = Path(value[2:]).parts
    return bool(parts) and all(part not in {"", ".", ".."} for part in parts)


def _safe_output_path(root: Path, output: str) -> Path:
    if not isinstance(output, str) or not output.strip():
        raise MarketplaceError("output path must be a non-empty relative path")
    candidate = Path(output)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise MarketplaceError("output path must stay inside the plugin root")
    target = (root / candidate).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise MarketplaceError("output path must stay inside the plugin root") from exc
    return target


def _display_name(name: str) -> str:
    return " ".join(part.capitalize() for part in name.split("-") if part)


def plugin_package_files(root: Path) -> list[str]:
    """Return the curated distributable plugin file list."""
    return _package_file_list(root.expanduser().resolve())


def plugin_package_digest(root: Path) -> str:
    """Return the SHA-256 digest for the curated distributable plugin package."""
    return _package_digest(root.expanduser().resolve())
