from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from mado_plugin_factory.scanner import ScanError, scan_candidate

FIXTURES = Path(__file__).parent / "fixtures"


class CandidateScannerTests(unittest.TestCase):
    def test_skill_only(self):
        result = scan_candidate(FIXTURES / "skill_only")
        self.assertEqual(result["architecture"], "skills_only")
        self.assertEqual(result["skills"][0]["name"], "hello")
        self.assertTrue(result["components"]["manifest"]["portable"]["valid_json"])
        self.assertFalse(result["components"]["mcp"]["configured"])
        self.assertEqual(result["missing"], [])

    def test_skills_plus_mcp_and_risks(self):
        result = scan_candidate(FIXTURES / "skill_mcp")
        self.assertEqual(result["architecture"], "skills_plus_mcp")
        codes = {risk["code"] for risk in result["risk_flags"]}
        self.assertIn("mcp_runtime_dependency", codes)
        self.assertIn("external_network", codes)
        self.assertIn("auth_or_secret_dependency", codes)

    def test_legacy_mcp_only(self):
        result = scan_candidate(FIXTURES / "mcp_only")
        self.assertEqual(result["architecture"], "mcp_only")
        self.assertTrue(result["components"]["mcp"]["configured"])
        missing = {item["code"] for item in result["missing"]}
        self.assertIn("portable_manifest_missing", missing)

    def test_not_ready(self):
        result = scan_candidate(FIXTURES / "not_ready")
        self.assertEqual(result["architecture"], "not_ready")
        missing = {item["code"] for item in result["missing"]}
        self.assertIn("no_capability", missing)

    def test_source_is_not_mutated(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = root / "skills" / "x"
            skill.mkdir(parents=True)
            p = skill / "SKILL.md"
            p.write_text("---\nname: x\ndescription: test\n---\n", encoding="utf-8")
            before = {
                x.relative_to(root).as_posix(): x.read_bytes()
                for x in root.rglob("*")
                if x.is_file()
            }
            scan_candidate(root)
            after = {
                x.relative_to(root).as_posix(): x.read_bytes()
                for x in root.rglob("*")
                if x.is_file()
            }
            self.assertEqual(before, after)

    def test_template_skills_do_not_define_candidate_architecture(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = root / "templates" / "sample" / "skills" / "x"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text(
                "---\nname: x\ndescription: template\n---\n",
                encoding="utf-8",
            )
            result = scan_candidate(root)
            self.assertEqual(result["architecture"], "not_ready")
            self.assertEqual(result["skills"], [])

    def test_bad_path(self):
        with self.assertRaises(ScanError):
            scan_candidate(FIXTURES / "does-not-exist")

    def test_cli_emits_json_and_not_ready_exit_code(self):
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "mado_plugin_factory",
                "scan",
                str(FIXTURES / "not_ready"),
                "--fail-on-not-ready",
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 2)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["architecture"], "not_ready")


if __name__ == "__main__":
    unittest.main()
