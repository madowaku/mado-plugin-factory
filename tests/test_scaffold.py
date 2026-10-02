from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from mado_plugin_factory.scaffold import (
    ScaffoldError,
    compile_extension_scaffold,
    public_scaffold_report,
    write_extension_scaffold,
)

FIXTURES = Path(__file__).parent / "fixtures"


class ExtensionScaffoldGeneratorTests(unittest.TestCase):
    def test_default_selection_scaffolds_actionable_server_surfaces(self):
        report = compile_extension_scaffold(FIXTURES / "skill_mcp")
        self.assertIn("plugin_settings", report["generated"])
        self.assertIn("composer_mentions", report["generated"])
        self.assertIn("rich_forms", report["generated"])
        self.assertNotIn("file_viewer_editor", report["selection"])
        self.assertNotIn("sidebar_app", report["selection"])
        self.assertTrue(report["output"].startswith("evidence/"))
        self.assertFalse(report["runtime_modified"])

    def test_file_handler_requires_suffix_then_renders_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "plugin.json").write_text(json.dumps({
                "$schema": "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",
                "name": "demo",
                "version": "0.1.0",
                "description": "demo",
            }), encoding="utf-8")
            (root / "mcp.json").write_text(json.dumps({
                "mcpServers": {"demo": {"command": "node", "args": ["server.js"]}}
            }), encoding="utf-8")
            (root / "app.ts").write_text('const uri = "ui://demo";', encoding="utf-8")

            missing = compile_extension_scaffold(
                root,
                extensions=["file_viewer_editor"],
            )
            self.assertEqual(missing["summary"]["generated_count"], 0)
            self.assertEqual(missing["skipped"][0]["reason"], "input_required")

            report = compile_extension_scaffold(
                root,
                extensions=["file_viewer_editor"],
                file_extensions=["stl", ".obj"],
            )
            self.assertEqual(report["generated"], ["file_viewer_editor"])
            content = report["_artifacts"]["apply/extensions/openai/file_viewer_editor.ts"]
            self.assertIn('".obj"', content)
            self.assertIn('".stl"', content)

    def test_deep_link_can_be_scaffolded_with_sidebar_in_same_pack(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "plugin.json").write_text(json.dumps({
                "$schema": "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",
                "name": "demo",
                "version": "0.1.0",
                "description": "demo",
            }), encoding="utf-8")
            (root / "mcp.json").write_text(json.dumps({
                "mcpServers": {"demo": {"command": "node", "args": ["server.js"]}}
            }), encoding="utf-8")
            (root / "app.ts").write_text('const uri = "ui://demo";', encoding="utf-8")
            report = compile_extension_scaffold(
                root,
                extensions=["deep_links", "sidebar_app"],
            )
            self.assertIn("deep_links", report["generated"])
            self.assertIn("sidebar_app", report["generated"])

    def test_onboarding_is_proposal_not_live_manifest_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = root / "skills" / "hello"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text(
                "---\nname: hello\ndescription: hello\n---\n",
                encoding="utf-8",
            )
            original = {
                "$schema": "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",
                "name": "demo",
                "version": "0.1.0",
                "description": "demo",
            }
            (root / "plugin.json").write_text(json.dumps(original), encoding="utf-8")
            report = compile_extension_scaffold(
                root,
                extensions=["plugin_onboarding"],
            )
            self.assertIn("plugin_onboarding", report["generated"])
            self.assertIn("apply/skills/plugin-onboarding/SKILL.md", report["_artifacts"])
            self.assertIn("apply/manifest.patch.json", report["_artifacts"])
            self.assertEqual(json.loads((root / "plugin.json").read_text()), original)

    def test_detected_and_blocked_surfaces_are_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = root / "skills" / "setup"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text(
                "---\nname: setup\ndescription: setup\n---\n",
                encoding="utf-8",
            )
            (root / "plugin.json").write_text(json.dumps({
                "$schema": "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",
                "name": "demo",
                "version": "0.1.0",
                "description": "demo",
                "extensions": {"com.openai": {"onboardingSkill": "./skills/setup/SKILL.md"}},
            }), encoding="utf-8")
            report = compile_extension_scaffold(
                root,
                extensions=["plugin_onboarding", "sidebar_app"],
            )
            skipped = {item["id"]: item for item in report["skipped"]}
            self.assertEqual(skipped["plugin_onboarding"]["reason"], "already_detected")
            self.assertEqual(skipped["sidebar_app"]["reason"], "blocked")

    def test_unknown_extension_and_bad_suffix_are_rejected(self):
        with self.assertRaises(ScaffoldError):
            compile_extension_scaffold(
                FIXTURES / "skill_mcp",
                extensions=["not_real"],
            )
        with self.assertRaises(ScaffoldError):
            compile_extension_scaffold(
                FIXTURES / "skill_mcp",
                file_extensions=["../bad"],
            )

    def test_write_is_contained_idempotent_and_force_guarded(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = root / "skills" / "hello"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text(
                "---\nname: hello\ndescription: hello\n---\n",
                encoding="utf-8",
            )
            (root / "plugin.json").write_text(json.dumps({
                "$schema": "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",
                "name": "demo",
                "version": "0.1.0",
                "description": "demo",
            }), encoding="utf-8")
            report = compile_extension_scaffold(
                root,
                extensions=["plugin_onboarding"],
            )
            first = write_extension_scaffold(root, report)
            second = write_extension_scaffold(root, report)
            self.assertEqual(first, second)

            target = root / report["output"] / "README.md"
            target.write_text("changed\n", encoding="utf-8")
            with self.assertRaises(ScaffoldError):
                write_extension_scaffold(root, report)
            write_extension_scaffold(root, report, force=True)

            with self.assertRaises(ScaffoldError):
                compile_extension_scaffold(root, output="../escape")

    def test_public_report_hides_rendered_source(self):
        report = compile_extension_scaffold(
            FIXTURES / "skill_mcp",
            extensions=["plugin_settings"],
        )
        public = public_scaffold_report(report)
        self.assertNotIn("_artifacts", public)
        self.assertEqual(public["summary"]["generated_count"], 1)

    def test_cli_dry_run(self):
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "mado_plugin_factory",
                "scaffold",
                str(FIXTURES / "skill_mcp"),
                "--extension",
                "plugin_settings",
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["summary"]["generated_count"], 1)
        self.assertNotIn("_artifacts", payload)


if __name__ == "__main__":
    unittest.main()
