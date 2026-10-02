from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from mado_plugin_factory.bundle import (
    BundleError,
    compile_submission_bundle,
    load_release_metadata,
    write_submission_bundle,
)
from mado_plugin_factory.evals import compile_submission_evals, write_submission_evals


def make_plugin(root: Path, *, with_mcp: bool = False) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "plugin.json").write_text(
        json.dumps(
            {
                "$schema": "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",
                "name": "hello-plugin",
                "version": "0.5.0",
                "description": "Prepare a reviewed greeting workflow.",
                "extensions": {
                    "com.openai": {
                        "interface": {
                            "displayName": "Hello Plugin",
                            "shortDescription": "Prepare reviewed greetings",
                            "longDescription": "Prepare a reviewed greeting workflow.",
                            "category": "Productivity",
                            "defaultPrompt": [
                                "Prepare a friendly greeting from the supplied fixture."
                            ],
                        }
                    }
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    skill = root / "skills" / "hello"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\nname: hello\ndescription: Prepare a friendly greeting.\n---\n\n"
        "Use the supplied fixture and prepare the greeting.\n",
        encoding="utf-8",
    )
    (root / "README.md").write_text("not packaged\n", encoding="utf-8")
    if with_mcp:
        (root / "mcp.json").write_text(
            json.dumps(
                {
                    "mcpServers": {
                        "hello": {
                            "type": "streamable-http",
                            "url": "https://mcp.example.com/mcp",
                        }
                    }
                }
            )
            + "\n",
            encoding="utf-8",
        )


def make_evidence(root: Path, *, install_verified: bool = True) -> None:
    eval_report = compile_submission_evals(
        root,
        metadata={"default_fixture": "Fixture: tests/fixtures/hello.json"},
    )
    write_submission_evals(root, eval_report)
    install_path = root / "evidence" / "marketplace"
    install_path.mkdir(parents=True)
    (install_path / "install-verification.json").write_text(
        json.dumps(
            {
                "schema_version": "0.4",
                "mode": "verify",
                "evidence_state": "executed",
                "install_verified": install_verified,
                "blocking_reasons": [] if install_verified else ["installed_cache_missing"],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def complete_metadata(*, with_mcp: bool = False) -> dict:
    value = {
        "availability": ["JP", "US"],
        "release_notes": "Initial submission of the greeting workflow.",
        "listing": {
            "website_url": "https://example.com",
            "support_url": "https://example.com/support",
            "privacy_policy_url": "https://example.com/privacy",
            "terms_url": "https://example.com/terms",
            "logo_ready": True,
        },
        "review": {
            "eval_cases_reviewed": True,
            "skills_final_tree_tested": True,
            "listing_reviewed": True,
        },
        "portal": {
            "apps_management_write_access": True,
            "developer_identity_verified": True,
            "policy_attestations_complete": True,
            "skill_safety_scan_passed": True,
        },
        "policy_attestation_note": "Listing, skills, tests, and availability reviewed.",
    }
    if with_mcp:
        value["mcp"] = {
            "production_url": "https://mcp.example.com/mcp",
            "demo_recording_url": "https://example.com/demo",
            "domain_verified": True,
            "tool_scan_current": True,
            "tool_annotations_reviewed": True,
            "reviewer_credentials_ready": True,
        }
    return value


class SubmissionBundleTests(unittest.TestCase):
    def test_missing_evidence_and_attestations_block_upload(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "plugin"
            make_plugin(root)
            report = compile_submission_bundle(root)
            self.assertFalse(report["upload_ready"])
            self.assertFalse(report["submission_ready"])
            self.assertIn(
                "eval_evidence_missing",
                report["blocking_reasons"]["upload"],
            )
            self.assertIn(
                "install_evidence_missing",
                report["blocking_reasons"]["upload"],
            )

    def test_complete_skills_only_bundle_can_be_submission_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "plugin"
            make_plugin(root)
            make_evidence(root)
            report = compile_submission_bundle(
                root,
                release_metadata=complete_metadata(),
            )
            self.assertEqual(report["submission_type"], "skills_only")
            self.assertTrue(report["upload_ready"])
            self.assertTrue(report["submission_ready"])
            self.assertEqual(report["blocking_reasons"]["submission"], [])

    def test_failed_install_remains_visible_and_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "plugin"
            make_plugin(root)
            make_evidence(root, install_verified=False)
            report = compile_submission_bundle(
                root,
                release_metadata=complete_metadata(),
            )
            self.assertFalse(report["upload_ready"])
            self.assertIn(
                "local_install_not_verified",
                report["blocking_reasons"]["upload"],
            )
            self.assertEqual(
                report["checks"]["local_install"]["evidence_state"],
                "executed",
            )

    def test_mcp_submission_requires_extra_portal_material(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "plugin"
            make_plugin(root, with_mcp=True)
            make_evidence(root)
            metadata = complete_metadata()
            report = compile_submission_bundle(root, release_metadata=metadata)
            self.assertEqual(report["submission_type"], "with_mcp")
            self.assertTrue(report["upload_ready"])
            self.assertFalse(report["submission_ready"])
            blockers = report["blocking_reasons"]["submission"]
            self.assertIn("mcp_production_url_missing", blockers)
            self.assertIn("mcp_domain_verified_pending", blockers)

    def test_complete_mcp_material_can_be_submission_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "plugin"
            make_plugin(root, with_mcp=True)
            make_evidence(root)
            report = compile_submission_bundle(
                root,
                release_metadata=complete_metadata(with_mcp=True),
            )
            self.assertTrue(report["upload_ready"])
            self.assertTrue(report["submission_ready"])

    def test_write_bundle_creates_deterministic_zip_and_excludes_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "plugin"
            make_plugin(root)
            make_evidence(root)
            report = compile_submission_bundle(
                root,
                release_metadata=complete_metadata(),
            )
            first = write_submission_bundle(root, report)
            bundle_root = Path(first["bundle_root"])
            self.assertTrue((bundle_root / "bundle.json").is_file())
            self.assertTrue((bundle_root / "plugin.zip").is_file())
            digest_one = first["plugin_zip_sha256"]

            with zipfile.ZipFile(bundle_root / "plugin.zip") as archive:
                names = sorted(archive.namelist())
            self.assertIn("plugin.json", names)
            self.assertIn("skills/hello/SKILL.md", names)
            self.assertNotIn("README.md", names)
            self.assertFalse(any(name.startswith("evidence/") for name in names))

            second = write_submission_bundle(root, report)
            self.assertEqual(second["plugin_zip_sha256"], digest_one)
            self.assertEqual(second["written"], [])

    def test_write_bundle_requires_force_for_conflict(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "plugin"
            make_plugin(root)
            make_evidence(root)
            report = compile_submission_bundle(
                root,
                release_metadata=complete_metadata(),
            )
            result = write_submission_bundle(root, report)
            bundle_root = Path(result["bundle_root"])
            (bundle_root / "bundle.json").write_text("{}\n", encoding="utf-8")
            with self.assertRaises(BundleError):
                write_submission_bundle(root, report)
            write_submission_bundle(root, report, force=True)

    def test_output_path_cannot_escape_plugin_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "plugin"
            make_plugin(root)
            make_evidence(root)
            report = compile_submission_bundle(
                root,
                release_metadata=complete_metadata(),
            )
            with self.assertRaises(BundleError):
                write_submission_bundle(root, report, output="../outside")

    def test_release_metadata_rejects_secret_bearing_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "release.json"
            path.write_text(
                json.dumps({"reviewer_password": "do-not-store"}),
                encoding="utf-8",
            )
            with self.assertRaises(BundleError):
                load_release_metadata(path)

    def test_release_metadata_requires_https_urls(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "plugin"
            make_plugin(root)
            make_evidence(root)
            metadata = complete_metadata()
            metadata["listing"]["website_url"] = "http://example.com"
            with self.assertRaises(BundleError):
                compile_submission_bundle(root, release_metadata=metadata)

    def test_cli_returns_zero_for_submission_ready_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "plugin"
            make_plugin(root)
            make_evidence(root)
            metadata_path = Path(tmp) / "release.json"
            metadata_path.write_text(
                json.dumps(complete_metadata()),
                encoding="utf-8",
            )
            env = dict(os.environ)
            env["PYTHONPATH"] = str(Path(__file__).parents[1] / "src")
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "mado_plugin_factory",
                    "bundle",
                    str(root),
                    "--release-metadata",
                    str(metadata_path),
                    "--pretty",
                ],
                text=True,
                capture_output=True,
                env=env,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertTrue(payload["submission_ready"])


if __name__ == "__main__":
    unittest.main()
