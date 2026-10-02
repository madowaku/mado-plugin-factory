from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from mado_plugin_factory.extensions import (
    ExtensionError,
    compile_extension_capabilities,
    write_extension_report,
)
from mado_plugin_factory.manifest import compile_manifest

FIXTURES = Path(__file__).parent / "fixtures"


def _by_id(report: dict) -> dict[str, dict]:
    return {item["id"]: item for item in report["capabilities"]}


class ExtensionCapabilityCompilerTests(unittest.TestCase):
    def test_skills_only_keeps_onboarding_available_without_mcp(self):
        report = compile_extension_capabilities(FIXTURES / "skill_only")
        items = _by_id(report)
        self.assertEqual(report["architecture"], "skills_only")
        self.assertEqual(items["plugin_onboarding"]["status"], "eligible")
        self.assertEqual(items["sidebar_app"]["status"], "blocked")
        self.assertIn("mcp_server_missing", items["sidebar_app"]["blockers"])

    def test_mcp_without_app_ui_exposes_server_side_extensions(self):
        report = compile_extension_capabilities(FIXTURES / "skill_mcp")
        items = _by_id(report)
        self.assertEqual(items["plugin_settings"]["status"], "eligible")
        self.assertEqual(items["composer_mentions"]["status"], "eligible")
        self.assertEqual(items["rich_forms"]["status"], "eligible")
        self.assertEqual(items["sidebar_app"]["status"], "blocked")
        self.assertIn("mcp_app_ui_missing", items["sidebar_app"]["blockers"])

    def test_detects_ui_extension_markers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "plugin.json").write_text(
                json.dumps(
                    {
                        "$schema": "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",
                        "name": "demo",
                        "version": "0.1.0",
                        "description": "demo",
                    }
                ),
                encoding="utf-8",
            )
            (root / "mcp.json").write_text(
                json.dumps(
                    {
                        "mcpServers": {
                            "demo": {
                                "command": "node",
                                "args": ["server.js"],
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            (root / "server.ts").write_text(
                """
const uri = "ui://parts/library";
const meta = {
  "openai/ui": {
    entrypoints: [
      {"type": "global"},
      {"type": "thread"},
      {"type": "file", "extensions": [".stl"]}
    ],
    availableDisplayModes: ["inline", "fullscreen"]
  },
  "openai/settings": {},
  "openai/extensions": {"mentions/search": {}}
};
const deep = "openai/deepLink";
const context = "ui/update-model-context";
const form = "openai/elicitation/create";
""",
                encoding="utf-8",
            )
            report = compile_extension_capabilities(root)
            items = _by_id(report)
            for extension_id in (
                "sidebar_app",
                "conversation_panel",
                "plugin_settings",
                "file_viewer_editor",
                "display_modes",
                "deep_links",
                "model_app_context",
                "composer_mentions",
                "rich_forms",
            ):
                self.assertEqual(items[extension_id]["status"], "detected", extension_id)
                self.assertFalse(items[extension_id]["runtime_verified"])

    def test_detects_valid_manifest_onboarding_skill(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = root / "skills" / "setup"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text(
                "---\nname: setup\ndescription: setup plugin\n---\n",
                encoding="utf-8",
            )
            (root / "plugin.json").write_text(
                json.dumps(
                    {
                        "$schema": "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",
                        "name": "demo",
                        "version": "0.1.0",
                        "description": "demo",
                        "extensions": {
                            "com.openai": {
                                "onboardingSkill": "./skills/setup/SKILL.md"
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            report = compile_extension_capabilities(root)
            onboarding = _by_id(report)["plugin_onboarding"]
            self.assertEqual(onboarding["status"], "detected")
            self.assertEqual(onboarding["evidence"], ["plugin.json"])
            self.assertTrue(report["prerequisites"]["onboarding"]["valid"])

    def test_manifest_compile_preserves_onboarding_skill(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = root / "skills" / "setup"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text(
                "---\nname: setup\ndescription: setup plugin\n---\n",
                encoding="utf-8",
            )
            (root / "plugin.json").write_text(
                json.dumps(
                    {
                        "$schema": "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",
                        "name": "demo",
                        "version": "0.1.0",
                        "description": "demo",
                        "extensions": {
                            "com.openai": {
                                "onboardingSkill": "./skills/setup/SKILL.md"
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            compiled = compile_manifest(root)
            openai_ext = compiled["manifest"]["extensions"]["com.openai"]
            self.assertEqual(openai_ext["onboardingSkill"], "./skills/setup/SKILL.md")
            self.assertTrue(compiled["validation"]["valid"])

    def test_missing_onboarding_skill_remains_visible(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = root / "skills" / "hello"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text(
                "---\nname: hello\ndescription: hello\n---\n",
                encoding="utf-8",
            )
            (root / "plugin.json").write_text(
                json.dumps(
                    {
                        "$schema": "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",
                        "name": "demo",
                        "version": "0.1.0",
                        "description": "demo",
                        "extensions": {
                            "com.openai": {
                                "onboardingSkill": "./skills/setup/SKILL.md"
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            report = compile_extension_capabilities(root)
            onboarding = _by_id(report)["plugin_onboarding"]
            self.assertEqual(onboarding["status"], "needs_input")
            self.assertIn("onboarding_skill_missing", onboarding["blockers"])

    def test_write_is_idempotent_and_contained(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = root / "skills" / "hello"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text(
                "---\nname: hello\ndescription: hello\n---\n",
                encoding="utf-8",
            )
            (root / "plugin.json").write_text(
                json.dumps(
                    {
                        "$schema": "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",
                        "name": "demo",
                        "version": "0.1.0",
                        "description": "demo",
                    }
                ),
                encoding="utf-8",
            )
            report = compile_extension_capabilities(root)
            written = write_extension_report(root, report)
            self.assertEqual(written, "evidence/extensions/capabilities.json")
            self.assertEqual(write_extension_report(root, report), written)

            target = root / written
            target.write_text("{}\n", encoding="utf-8")
            with self.assertRaises(ExtensionError):
                write_extension_report(root, report)
            self.assertEqual(write_extension_report(root, report, force=True), written)

            with self.assertRaises(ExtensionError):
                write_extension_report(root, report, output="../escape.json")

    def test_cli_emits_report(self):
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "mado_plugin_factory",
                "extensions",
                str(FIXTURES / "skill_mcp"),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["evidence_state"], "inspected")
        self.assertIn("plugin_settings", payload["summary"]["eligible"])


if __name__ == "__main__":
    unittest.main()
