from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .extensions import EXTENSIONS, compile_extension_capabilities

SCHEMA_VERSION = "0.1"
DEFAULT_OUTPUT = "evidence/scaffolds/extensions"

VALID_EXTENSION_IDS = {item["id"] for item in EXTENSIONS}


class ScaffoldError(ValueError):
    pass


def compile_extension_scaffold(
    root: Path,
    *,
    extensions: list[str] | None = None,
    file_extensions: list[str] | None = None,
    output: str = DEFAULT_OUTPUT,
) -> dict[str, Any]:
    root = root.expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise ScaffoldError(f"candidate path is not a directory: {root}")

    output_path = _safe_output_dir(root, output)
    capabilities = compile_extension_capabilities(root)
    by_id = {item["id"]: item for item in capabilities["capabilities"]}

    selected = _normalize_selection(extensions, by_id)
    file_suffixes = _normalize_file_extensions(file_extensions or [])

    generated: list[str] = []
    skipped: list[dict[str, Any]] = []
    artifacts: dict[str, str] = {}

    sidebar_available = (
        by_id["sidebar_app"]["status"] == "detected"
        or "sidebar_app" in selected
    )

    for extension_id in selected:
        capability = by_id[extension_id]
        status = capability["status"]

        if status == "detected":
            skipped.append(
                {
                    "id": extension_id,
                    "reason": "already_detected",
                    "blockers": [],
                }
            )
            continue
        if status == "blocked":
            skipped.append(
                {
                    "id": extension_id,
                    "reason": "blocked",
                    "blockers": capability["blockers"],
                }
            )
            continue
        if extension_id == "file_viewer_editor" and not file_suffixes:
            skipped.append(
                {
                    "id": extension_id,
                    "reason": "input_required",
                    "blockers": ["file_extensions_unspecified"],
                }
            )
            continue
        if extension_id == "deep_links" and not sidebar_available:
            skipped.append(
                {
                    "id": extension_id,
                    "reason": "dependency_required",
                    "blockers": ["global_entrypoint_not_detected_or_selected"],
                }
            )
            continue

        generated.append(extension_id)
        if extension_id == "plugin_onboarding":
            artifacts.update(_onboarding_artifacts())
        else:
            rel = f"apply/extensions/openai/{extension_id}.ts"
            artifacts[rel] = _render_typescript_scaffold(
                extension_id,
                file_extensions=file_suffixes,
            )

    plan = {
        "schema_version": SCHEMA_VERSION,
        "evidence_state": "generated",
        "source": {
            "root": str(root),
            "capability_schema_version": capabilities["schema_version"],
        },
        "selection": selected,
        "inputs": {
            "file_extensions": file_suffixes,
        },
        "generated": generated,
        "skipped": skipped,
        "apply_mode": "proposal_only",
        "runtime_modified": False,
        "output": output_path.relative_to(root).as_posix(),
    }

    artifacts["plan.json"] = _json_text(plan)
    artifacts["README.md"] = _render_readme(plan)

    file_inventory = []
    for rel, content in sorted(artifacts.items()):
        encoded = content.encode("utf-8")
        file_inventory.append(
            {
                "path": rel,
                "bytes": len(encoded),
                "sha256": hashlib.sha256(encoded).hexdigest(),
            }
        )

    return {
        **plan,
        "summary": {
            "generated_count": len(generated),
            "skipped_count": len(skipped),
            "artifact_count": len(artifacts),
        },
        "files": file_inventory,
        "_artifacts": artifacts,
    }


def write_extension_scaffold(
    root: Path,
    report: dict[str, Any],
    *,
    force: bool = False,
) -> list[str]:
    root = root.expanduser().resolve()
    output = report.get("output")
    if not isinstance(output, str) or not output:
        raise ScaffoldError("scaffold report is missing output")

    output_dir = _safe_output_dir(root, output)
    artifacts = report.get("_artifacts")
    if not isinstance(artifacts, dict) or not artifacts:
        raise ScaffoldError("scaffold report has no rendered artifacts")

    rendered: list[tuple[Path, bytes]] = []
    for rel, content in sorted(artifacts.items()):
        if not isinstance(rel, str) or not isinstance(content, str):
            raise ScaffoldError("scaffold artifacts must map relative paths to text")
        target = _safe_child(output_dir, rel)
        if target.is_symlink():
            raise ScaffoldError(f"refusing to write through symlink: {target}")
        data = content.encode("utf-8")
        if target.exists() and target.read_bytes() != data and not force:
            raise ScaffoldError(
                f"scaffold file already exists with different content: {target}; use --force to replace it"
            )
        rendered.append((target, data))

    written: list[str] = []
    for target, data in rendered:
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists() or target.read_bytes() != data:
            target.write_bytes(data)
        written.append(target.relative_to(root).as_posix())
    return written


def public_scaffold_report(report: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in report.items() if key != "_artifacts"}


def _normalize_selection(
    requested: list[str] | None,
    by_id: dict[str, dict[str, Any]],
) -> list[str]:
    if requested:
        unknown = sorted(set(requested) - VALID_EXTENSION_IDS)
        if unknown:
            raise ScaffoldError(
                "unknown extension id(s): " + ", ".join(unknown)
            )
        return sorted(set(requested))

    return sorted(
        extension_id
        for extension_id, item in by_id.items()
        if item["status"] in {"eligible", "needs_input"}
    )


def _normalize_file_extensions(values: list[str]) -> list[str]:
    result: set[str] = set()
    for raw in values:
        if not isinstance(raw, str) or not raw.strip():
            continue
        value = raw.strip().lower()
        if not value.startswith("."):
            value = "." + value
        if value in {".", ".."} or "/" in value or "\\" in value or " " in value:
            raise ScaffoldError(f"invalid file extension: {raw}")
        result.add(value)
    return sorted(result)


def _render_typescript_scaffold(
    extension_id: str,
    *,
    file_extensions: list[str],
) -> str:
    header = (
        "// Generated by MADO Plugin Factory MPF-M0.7.\n"
        "// Proposal only: copy/adapt this contract into your active MCP/App code after review.\n"
        "// Generated evidence is not runtime verification.\n\n"
    )
    bodies = {
        "sidebar_app": """export const sidebarApp = {
  _meta: {
    "openai/ui": {
      entrypoints: [{ type: "global" }],
    },
  },
};
""",
        "conversation_panel": """export const conversationPanel = {
  _meta: {
    "openai/ui": {
      entrypoints: [{ type: "thread" }],
    },
  },
};
""",
        "plugin_settings": """export const pluginSettingsCapability = {
  capabilities: {
    extensions: {
      "openai/settings": {
        // Replace with your settings schema/defaults.
        schema: { type: "object", properties: {} },
      },
    },
  },
};
""",
        "file_viewer_editor": """export const fileViewerEditor = {
  _meta: {
    "openai/ui": {
      entrypoints: [
        {
          type: "file",
          extensions: __FILE_EXTENSIONS__,
        },
      ],
    },
  },
};
""".replace("__FILE_EXTENSIONS__", json.dumps(file_extensions)),
        "display_modes": """export const displayModes = {
  _meta: {
    "openai/ui": {
      availableDisplayModes: ["inline", "fullscreen"],
      preferredDisplayMode: "inline",
    },
  },
};
""",
        "deep_links": """export function readDeepLink(hostContext: Record<string, unknown>) {
  return hostContext["openai/deepLink"];
}

// Route the returned deep-link payload inside your global sidebar app.
""",
        "model_app_context": """export const MODEL_CONTEXT_METHOD = "ui/update-model-context";

// Send this notification from the MCP App when UI state should be visible to the model.
export function modelContextPayload(content: unknown) {
  return { method: MODEL_CONTEXT_METHOD, params: { content } };
}
""",
        "composer_mentions": """export const composerMentions = {
  _meta: {
    "openai/extensions": {
      "mentions/search": {
        // Register the search tool and ensure its visibility includes "app".
        tool: "search_mentions",
      },
    },
  },
};
""",
        "rich_forms": """export const FORM_ELICITATION_METHOD = "openai/elicitation/create";

export function formElicitation(requestedSchema: Record<string, unknown>) {
  return {
    method: FORM_ELICITATION_METHOD,
    params: { requestedSchema },
  };
}

// OpenAI-registered MCP servers need MCP 2026-07-28+ with MRTR for form elicitation.
""",
    }
    body = bodies.get(extension_id)
    if body is None:
        raise ScaffoldError(f"no scaffold renderer for extension: {extension_id}")
    return header + body


def _onboarding_artifacts() -> dict[str, str]:
    skill = """---
name: plugin-onboarding
description: Guide the user through the minimum setup needed to use this plugin.
---

# Plugin onboarding

Use this Skill only for first-run setup or when the user asks to configure the plugin.

1. Explain the minimum required setup in plain language.
2. Ask only for information that is actually required.
3. Never request secrets in chat when OAuth or a secure settings surface should be used.
4. Confirm what was configured and what remains optional.
"""
    patch = {
        "extensions": {
            "com.openai": {
                "onboardingSkill": "./skills/plugin-onboarding/SKILL.md"
            }
        }
    }
    return {
        "apply/skills/plugin-onboarding/SKILL.md": skill,
        "apply/manifest.patch.json": _json_text(patch),
    }


def _render_readme(plan: dict[str, Any]) -> str:
    generated = "\n".join(f"- {item}" for item in plan["generated"]) or "- none"
    skipped = (
        "\n".join(
            f"- {item['id']}: {item['reason']}"
            + (f" ({', '.join(item['blockers'])})" if item["blockers"] else "")
            for item in plan["skipped"]
        )
        or "- none"
    )
    return f"""# Extension Scaffold Pack

Generated by MPF-M0.7.

This directory is a proposal pack. Nothing under \`apply/\` is active until it is deliberately copied or integrated into the plugin source.

## Generated

{generated}

## Skipped

{skipped}

## Apply rule

Review each file, adapt it to the real MCP server/App SDK, then move the accepted implementation into the active package. Re-run \`mpf extensions\` afterward to inspect the applied source.

Do not treat this scaffold as runtime evidence.
"""


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _safe_output_dir(root: Path, output: str) -> Path:
    candidate = Path(output)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ScaffoldError("output must be a relative path inside the candidate root")
    target = (root / candidate).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ScaffoldError("output must stay inside the candidate root") from exc
    return target


def _safe_child(parent: Path, relative: str) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ScaffoldError("artifact path must stay inside the scaffold output")
    target = (parent / candidate).resolve()
    try:
        target.relative_to(parent)
    except ValueError as exc:
        raise ScaffoldError("artifact path must stay inside the scaffold output") from exc
    return target
