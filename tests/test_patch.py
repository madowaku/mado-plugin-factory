from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from mado_plugin_factory.patch import (
    PatchError,
    apply_extension_patch,
    compile_extension_patch,
    public_patch_report,
)
from mado_plugin_factory.scaffold import (
    compile_extension_scaffold,
    write_extension_scaffold,
)


def _make_candidate(root: Path, *, with_mcp: bool = True) -> None:
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
                        "interface": {
                            "displayName": "Demo",
                            "shortDescription": "demo",
                            "longDescription": "demo",
                        }
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    if with_mcp:
        (root / "mcp.json").write_text(
            json.dumps(
                {
                    "mcpServers": {
                        "demo": {"command": "node", "args": ["server.js"]}
                    }
                }
            ),
            encoding="utf-8",
        )


def _write_scaffold(root: Path, extensions: list[str]) -> None:
    report = compile_extension_scaffold(root, extensions=extensions)
    write_extension_scaffold(root, report)


class ExtensionPatchEngineTests(unittest.TestCase):
    def test_plan_and_apply_promotes_source_then_detects_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_candidate(root)
            _write_scaffold(root, ["plugin_settings"])

            plan = compile_extension_patch(root)
            self.assertTrue(plan["apply_ready"])
            self.assertEqual(plan["operations"][0]["action"], "create")
            self.assertFalse(plan["source_applied"])

            result = apply_extension_patch(root, plan)
            target = root / "extensions" / "openai" / "plugin_settings.ts"
            self.assertTrue(target.is_file())
            self.assertIn(
                "Applied by MADO Plugin Factory MPF-M0.8",
                target.read_text(),
            )
            self.assertTrue(result["post_apply"]["verified"])
            self.assertIn(
                "plugin_settings",
                result["post_apply"]["detected"],
            )
            self.assertFalse(result["runtime_verified"])
            self.assertTrue((root / result["evidence_output"]).is_file())

    def test_onboarding_deep_merges_manifest_and_preserves_interface(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_candidate(root, with_mcp=False)
            _write_scaffold(root, ["plugin_onboarding"])

            plan = compile_extension_patch(root)
            self.assertTrue(plan["apply_ready"])
            self.assertTrue(
                any(
                    item["action"] == "merge_manifest"
                    for item in plan["operations"]
                )
            )
            result = apply_extension_patch(root, plan)

            manifest = json.loads((root / "plugin.json").read_text())
            openai = manifest["extensions"]["com.openai"]
            self.assertEqual(
                openai["onboardingSkill"],
                "./skills/plugin-onboarding/SKILL.md",
            )
            self.assertEqual(
                openai["interface"]["displayName"],
                "Demo",
            )
            self.assertTrue(
                (
                    root
                    / "skills"
                    / "plugin-onboarding"
                    / "SKILL.md"
                ).is_file()
            )
            self.assertTrue(result["post_apply"]["verified"])
            self.assertIn(
                "plugin_onboarding",
                result["post_apply"]["detected"],
            )

    def test_differing_generated_file_requires_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_candidate(root)
            target = root / "extensions" / "openai"
            target.mkdir(parents=True)
            (target / "plugin_settings.ts").write_text(
                "// custom\n",
                encoding="utf-8",
            )
            _write_scaffold(root, ["plugin_settings"])

            plan = compile_extension_patch(root)
            self.assertEqual(
                plan["force_required"],
                ["extensions/openai/plugin_settings.ts"],
            )
            with self.assertRaises(PatchError):
                apply_extension_patch(root, plan)
            result = apply_extension_patch(root, plan, force=True)
            self.assertTrue(result["post_apply"]["verified"])

    def test_manifest_semantic_conflict_cannot_be_forced(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_candidate(root, with_mcp=False)
            scaffold = root / "evidence" / "scaffolds" / "extensions"
            apply_dir = scaffold / "apply"
            apply_dir.mkdir(parents=True)
            (scaffold / "plan.json").write_text(
                json.dumps(
                    {
                        "schema_version": "0.1",
                        "evidence_state": "generated",
                        "generated": ["plugin_onboarding"],
                        "apply_mode": "proposal_only",
                        "runtime_modified": False,
                    }
                ),
                encoding="utf-8",
            )
            (apply_dir / "manifest.patch.json").write_text(
                json.dumps(
                    {
                        "extensions": {
                            "com.openai": {
                                "interface": {
                                    "displayName": "Different"
                                }
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            plan = compile_extension_patch(root)
            self.assertFalse(plan["apply_ready"])
            self.assertEqual(
                plan["semantic_conflicts"][0]["path"],
                "extensions.com.openai.interface.displayName",
            )
            with self.assertRaises(PatchError):
                apply_extension_patch(root, plan, force=True)

    def test_target_drift_aborts_stale_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_candidate(root)
            _write_scaffold(root, ["plugin_settings"])
            plan = compile_extension_patch(root)

            target = root / "extensions" / "openai"
            target.mkdir(parents=True)
            (target / "plugin_settings.ts").write_text(
                "// appeared later\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                PatchError,
                "changed since planning",
            ):
                apply_extension_patch(root, plan, force=True)

    def test_reapply_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_candidate(root)
            _write_scaffold(root, ["plugin_settings"])
            first = compile_extension_patch(root)
            apply_extension_patch(root, first)

            second = compile_extension_patch(root)
            self.assertEqual(second["summary"]["change_count"], 0)
            self.assertEqual(
                second["operations"][0]["action"],
                "unchanged",
            )
            result = apply_extension_patch(root, second)
            self.assertEqual(result["written"], [])
            self.assertTrue(result["post_apply"]["verified"])

    def test_bad_paths_and_unsupported_artifacts_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_candidate(root)
            with self.assertRaises(PatchError):
                compile_extension_patch(root, scaffold="../escape")

            scaffold = root / "evidence" / "scaffolds" / "extensions"
            apply_dir = scaffold / "apply"
            apply_dir.mkdir(parents=True)
            (scaffold / "plan.json").write_text(
                json.dumps(
                    {
                        "schema_version": "0.1",
                        "evidence_state": "generated",
                        "generated": ["plugin_settings"],
                        "apply_mode": "proposal_only",
                        "runtime_modified": False,
                    }
                ),
                encoding="utf-8",
            )
            (apply_dir / "danger.txt").write_text(
                "nope",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                PatchError,
                "unsupported scaffold apply path",
            ):
                compile_extension_patch(root)

    def test_public_report_hides_write_payloads(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_candidate(root)
            _write_scaffold(root, ["plugin_settings"])
            plan = compile_extension_patch(root)
            public = public_patch_report(plan)
            self.assertNotIn("_rendered", public)
            self.assertNotIn("_preconditions", public)

    def test_cli_dry_run_and_apply(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_candidate(root)
            _write_scaffold(root, ["plugin_settings"])

            dry = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "mado_plugin_factory",
                    "patch",
                    str(root),
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(dry.returncode, 0, dry.stderr)
            payload = json.loads(dry.stdout)
            self.assertTrue(payload["apply_ready"])

            applied = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "mado_plugin_factory",
                    "patch",
                    str(root),
                    "--apply",
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(applied.returncode, 0, applied.stderr)
            result = json.loads(applied.stdout)
            self.assertTrue(result["source_applied"])
            self.assertTrue(result["post_apply"]["verified"])


if __name__ == "__main__":
    unittest.main()
