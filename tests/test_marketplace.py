from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from mado_plugin_factory.marketplace import (
    MarketplaceError,
    compile_marketplace_bridge,
    verify_marketplace_install,
    write_install_evidence,
    write_marketplace_bridge,
)


def make_plugin(root: Path, *, name: str = "hello-plugin") -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "plugin.json").write_text(
        json.dumps(
            {
                "$schema": "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",
                "name": name,
                "version": "0.4.0",
                "description": "A local marketplace fixture.",
                "extensions": {
                    "com.openai": {
                        "interface": {
                            "displayName": "Hello Plugin",
                            "shortDescription": "Marketplace fixture",
                            "longDescription": "A local marketplace fixture.",
                            "category": "Productivity",
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
        "---\nname: hello\ndescription: Greet the user.\n---\n\nGreet the user.\n",
        encoding="utf-8",
    )
    (root / "README.md").write_text("not part of plugin package\n", encoding="utf-8")
    evidence = root / "evidence"
    evidence.mkdir()
    (evidence / "old.json").write_text("{}\n", encoding="utf-8")


class MarketplaceBridgeTests(unittest.TestCase):
    def test_compile_repo_marketplace_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            plugin = base / "source"
            market = base / "market"
            make_plugin(plugin)
            report = compile_marketplace_bridge(plugin, market)
            self.assertTrue(report["validation"]["valid"])
            entry = report["marketplace"]["catalog"]["plugins"][0]
            self.assertEqual(entry["source"]["path"], "./plugins/hello-plugin")
            self.assertEqual(entry["policy"]["installation"], "AVAILABLE")
            self.assertEqual(entry["policy"]["authentication"], "ON_INSTALL")
            self.assertEqual(report["evidence_state"], "generated")
            self.assertFalse(report["install_verified"])

    def test_dry_run_does_not_create_marketplace_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            plugin = base / "source"
            market = base / "market"
            make_plugin(plugin)
            compile_marketplace_bridge(plugin, market)
            self.assertFalse(market.exists())

    def test_write_stages_only_distributable_plugin_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            plugin = base / "source"
            market = base / "market"
            make_plugin(plugin)
            report = compile_marketplace_bridge(plugin, market)
            written = write_marketplace_bridge(plugin, market, report)
            staged = market / "plugins" / "hello-plugin"
            self.assertTrue((staged / "plugin.json").is_file())
            self.assertTrue((staged / "skills" / "hello" / "SKILL.md").is_file())
            self.assertFalse((staged / "README.md").exists())
            self.assertFalse((staged / "evidence").exists())
            self.assertTrue((market / ".agents" / "plugins" / "marketplace.json").is_file())
            self.assertEqual(written["evidence_state"], "executed")

    def test_existing_catalog_preserves_other_plugins(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            plugin = base / "source"
            market = base / "market"
            make_plugin(plugin)
            catalog_path = market / ".agents" / "plugins"
            catalog_path.mkdir(parents=True)
            (catalog_path / "marketplace.json").write_text(
                json.dumps(
                    {
                        "name": "local-repo",
                        "interface": {"displayName": "Local Plugins"},
                        "plugins": [
                            {
                                "name": "other-plugin",
                                "source": {
                                    "source": "local",
                                    "path": "./plugins/other-plugin",
                                },
                                "policy": {
                                    "installation": "AVAILABLE",
                                    "authentication": "ON_INSTALL",
                                },
                                "category": "Productivity",
                            }
                        ],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            report = compile_marketplace_bridge(plugin, market)
            names = [item["name"] for item in report["marketplace"]["catalog"]["plugins"]]
            self.assertEqual(names, ["other-plugin", "hello-plugin"])

    def test_staging_overwrite_requires_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            plugin = base / "source"
            market = base / "market"
            make_plugin(plugin)
            report = compile_marketplace_bridge(plugin, market)
            write_marketplace_bridge(plugin, market, report)
            (market / "plugins" / "hello-plugin" / "plugin.json").write_text(
                "{}\n",
                encoding="utf-8",
            )
            with self.assertRaises(MarketplaceError):
                write_marketplace_bridge(plugin, market, report)
            write_marketplace_bridge(plugin, market, report, force=True)

    def test_verify_reports_missing_cache_as_executed_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            plugin = base / "source"
            market = base / "market"
            cache = base / "cache"
            make_plugin(plugin)
            bridge = compile_marketplace_bridge(plugin, market)
            write_marketplace_bridge(plugin, market, bridge)
            report = verify_marketplace_install(
                plugin,
                market,
                cache_root=cache,
            )
            self.assertEqual(report["evidence_state"], "executed")
            self.assertFalse(report["install_verified"])
            self.assertIn("installed_cache_missing", report["blocking_reasons"])

    def test_verify_exact_installed_cache_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            plugin = base / "source"
            market = base / "market"
            cache = base / "cache"
            make_plugin(plugin)
            bridge = compile_marketplace_bridge(plugin, market)
            write_marketplace_bridge(plugin, market, bridge)

            staged = market / "plugins" / "hello-plugin"
            installed = cache / "local-repo" / "hello-plugin" / "local"
            installed.parent.mkdir(parents=True)
            shutil.copytree(staged, installed)

            report = verify_marketplace_install(
                plugin,
                market,
                cache_root=cache,
            )
            self.assertTrue(report["install_verified"])
            self.assertTrue(report["cache"]["content_match"])
            self.assertEqual(report["blocking_reasons"], [])

    def test_verify_detects_stale_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            plugin = base / "source"
            market = base / "market"
            cache = base / "cache"
            make_plugin(plugin)
            bridge = compile_marketplace_bridge(plugin, market)
            write_marketplace_bridge(plugin, market, bridge)

            staged = market / "plugins" / "hello-plugin"
            installed = cache / "local-repo" / "hello-plugin" / "local"
            installed.parent.mkdir(parents=True)
            shutil.copytree(staged, installed)
            (installed / "skills" / "hello" / "SKILL.md").write_text(
                "---\nname: hello\ndescription: Stale copy.\n---\n",
                encoding="utf-8",
            )

            report = verify_marketplace_install(
                plugin,
                market,
                cache_root=cache,
            )
            self.assertFalse(report["install_verified"])
            self.assertFalse(report["cache"]["content_match"])
            self.assertIn(
                "installed_copy_differs_from_staged",
                report["blocking_reasons"],
            )

    def test_write_executed_install_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            plugin = base / "source"
            market = base / "market"
            cache = base / "cache"
            make_plugin(plugin)
            bridge = compile_marketplace_bridge(plugin, market)
            write_marketplace_bridge(plugin, market, bridge)
            installed = cache / "local-repo" / "hello-plugin" / "local"
            installed.parent.mkdir(parents=True)
            shutil.copytree(market / "plugins" / "hello-plugin", installed)

            report = verify_marketplace_install(plugin, market, cache_root=cache)
            outputs = write_install_evidence(plugin, report)
            self.assertIn(
                "evidence/marketplace/install-verification.json",
                outputs,
            )
            saved = json.loads(
                (plugin / "evidence" / "marketplace" / "install-verification.json")
                .read_text(encoding="utf-8")
            )
            self.assertEqual(saved["evidence_state"], "executed")
            self.assertTrue(saved["install_verified"])

            with self.assertRaises(MarketplaceError):
                write_install_evidence(plugin, report, output="../escape.json")

    def test_cli_bridge_dry_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            plugin = base / "source"
            market = base / "market"
            make_plugin(plugin)
            env = dict(os.environ)
            env["PYTHONPATH"] = str(Path(__file__).parents[1] / "src")
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "mado_plugin_factory",
                    "marketplace",
                    "bridge",
                    str(plugin),
                    "--root",
                    str(market),
                    "--pretty",
                ],
                text=True,
                capture_output=True,
                env=env,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertTrue(payload["validation"]["valid"])
            self.assertFalse(market.exists())


if __name__ == "__main__":
    unittest.main()
