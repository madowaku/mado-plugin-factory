from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from mado_plugin_factory.manifest import (
    ManifestError,
    compile_manifest,
    validate_manifest,
    write_compiled_manifest,
)


def make_skill(root: Path, name: str = "hello", description: str = "Greet users.") -> None:
    path = root / "skills" / name
    path.mkdir(parents=True)
    (path / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\nDo it.\n",
        encoding="utf-8",
    )


class ManifestCompilerTests(unittest.TestCase):
    def test_compiles_portable_manifest_with_openai_interface(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "hello-plugin"
            root.mkdir()
            make_skill(root)
            report = compile_manifest(
                root,
                metadata={
                    "name": "hello-plugin",
                    "version": "0.2.0",
                    "description": "Greet users.",
                },
            )
            manifest = report["manifest"]
            self.assertTrue(report["validation"]["valid"])
            self.assertEqual(
                manifest["$schema"],
                "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",
            )
            self.assertEqual(
                manifest["extensions"]["com.openai"]["interface"]["displayName"],
                "Hello Plugin",
            )
            self.assertEqual(
                manifest["extensions"]["com.openai"]["interface"]["shortDescription"],
                "Greet users.",
            )

    def test_rejects_invalid_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "bad"
            root.mkdir()
            make_skill(root)
            report = compile_manifest(
                root,
                metadata={"name": "Bad Name", "description": "Test"},
            )
            codes = {item["code"] for item in report["validation"]["errors"]}
            self.assertIn("name_invalid", codes)

    def test_custom_interface_and_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "x"
            root.mkdir()
            make_skill(root)
            (root / ".app.json").write_text("{}", encoding="utf-8")
            (root / "hooks").mkdir()
            (root / "hooks" / "hooks.json").write_text("{}", encoding="utf-8")
            report = compile_manifest(
                root,
                metadata={
                    "name": "x-plugin",
                    "description": "Useful tool",
                    "interface": {
                        "displayName": "X Plugin",
                        "shortDescription": "Useful tool",
                        "developerName": "madowaku",
                        "brandColor": "#10A37F",
                        "defaultPrompt": ["Use X Plugin."],
                    },
                },
            )
            extension = report["manifest"]["extensions"]["com.openai"]
            self.assertEqual(extension["apps"], "./.app.json")
            self.assertEqual(extension["hooks"], "./hooks/hooks.json")
            self.assertTrue(report["validation"]["valid"])

    def test_not_ready_candidate_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(ManifestError):
                compile_manifest(
                    root,
                    metadata={"name": "empty", "description": "Empty"},
                )

    def test_compatibility_mirror_has_skills(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "hello"
            root.mkdir()
            make_skill(root)
            report = compile_manifest(
                root,
                metadata={"name": "hello-plugin", "description": "Greet"},
                compatibility=True,
            )
            compatibility = report["compatibility_manifest"]
            self.assertEqual(compatibility["skills"], "./skills/")
            self.assertEqual(compatibility["interface"]["displayName"], "Hello Plugin")
            self.assertNotIn("$schema", compatibility)

    def test_portable_mcp_does_not_invent_legacy_mcp_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "hello"
            root.mkdir()
            make_skill(root)
            (root / "mcp.json").write_text(
                json.dumps(
                    {
                        "mcpServers": {
                            "docs": {
                                "type": "streamable-http",
                                "url": "https://example.com/mcp",
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            report = compile_manifest(
                root,
                metadata={"name": "hello-plugin", "description": "Greet"},
                compatibility=True,
            )
            self.assertNotIn("mcpServers", report["compatibility_manifest"])
            codes = {item["code"] for item in report["validation"]["warnings"]}
            self.assertIn("compat_mcp_not_emitted", codes)

    def test_write_requires_force_to_replace_existing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "hello"
            root.mkdir()
            make_skill(root)
            (root / "plugin.json").write_text('{"old": true}\n', encoding="utf-8")
            report = compile_manifest(
                root,
                metadata={"name": "hello-plugin", "description": "Greet"},
            )
            with self.assertRaises(ManifestError):
                write_compiled_manifest(root, report)

            outputs = write_compiled_manifest(root, report, force=True)
            self.assertIn("plugin.json", outputs)
            data = json.loads((root / "plugin.json").read_text(encoding="utf-8"))
            self.assertEqual(data["name"], "hello-plugin")

    def test_write_compatibility_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "hello"
            root.mkdir()
            make_skill(root)
            report = compile_manifest(
                root,
                metadata={"name": "hello-plugin", "description": "Greet"},
                compatibility=True,
            )
            outputs = write_compiled_manifest(
                root,
                report,
                compatibility=True,
            )
            self.assertIn(".codex-plugin/plugin.json", outputs)
            self.assertTrue((root / ".codex-plugin" / "plugin.json").is_file())

    def test_directory_limits_are_warnings_not_package_errors(self):
        manifest = {
            "$schema": "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",
            "name": "long-plugin",
            "version": "0.1.0",
            "description": "x",
            "extensions": {
                "com.openai": {
                    "interface": {
                        "displayName": "A" * 31,
                        "shortDescription": "B" * 31,
                        "longDescription": "x",
                    }
                }
            },
        }
        result = validate_manifest(manifest)
        self.assertTrue(result["valid"])
        codes = {item["code"] for item in result["warnings"]}
        self.assertIn("display_name_directory_limit", codes)
        self.assertIn("short_description_directory_limit", codes)

    def test_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "hello"
            root.mkdir()
            make_skill(root)
            metadata = {
                "name": "hello-plugin",
                "description": "Greet users.",
                "keywords": ["hello", "workflow"],
            }
            self.assertEqual(
                compile_manifest(root, metadata=metadata),
                compile_manifest(root, metadata=metadata),
            )


class ManifestCliTests(unittest.TestCase):
    def test_cli_compile_dry_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "hello"
            root.mkdir()
            make_skill(root)
            env = dict(os.environ)
            env["PYTHONPATH"] = str(Path(__file__).parents[1] / "src")
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "mado_plugin_factory",
                    "manifest",
                    str(root),
                    "--name",
                    "hello-plugin",
                    "--description",
                    "Greet",
                    "--pretty",
                ],
                text=True,
                capture_output=True,
                env=env,
                check=False,
            )
            self.assertEqual(proc.returncode, 0)
            payload = json.loads(proc.stdout)
            self.assertTrue(payload["validation"]["valid"])
            self.assertEqual(payload["manifest"]["name"], "hello-plugin")


if __name__ == "__main__":
    unittest.main()
