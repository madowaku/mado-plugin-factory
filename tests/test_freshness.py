from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from mado_plugin_factory.freshness import (
    FreshnessError,
    run_verification_freshness,
)
from mado_plugin_factory.orchestrator import (
    run_extension_verification,
    write_verification_dossier,
)
from mado_plugin_factory.marketplace import plugin_package_digest


SERVER = r'''
import json
import sys

TOOL_DESCRIPTION = "__DESCRIPTION__"
SERVER_VERSION = "__SERVER_VERSION__"
HTML = "__HTML__"

def send(value):
    sys.stdout.write(json.dumps(value) + "\n")
    sys.stdout.flush()

for line in sys.stdin:
    try:
        msg = json.loads(line)
    except Exception:
        continue
    method = msg.get("method")
    ident = msg.get("id")
    if method == "server/discover":
        send({
            "jsonrpc": "2.0",
            "id": ident,
            "result": {
                "resultType": "complete",
                "supportedVersions": ["2026-07-28"],
                "_meta": {
                    "io.modelcontextprotocol/serverInfo": {
                        "name": "freshness-fixture",
                        "version": SERVER_VERSION
                    }
                },
                "capabilities": {
                    "tools": {},
                    "extensions": {
                        "openai/settings": {
                            "readTool": "settings.read",
                            "updateTool": "settings.update"
                        }
                    }
                }
            }
        })
    elif method == "tools/list":
        send({
            "jsonrpc": "2.0",
            "id": ident,
            "result": {
                "tools": [
                    {
                        "name": "settings.read",
                        "description": "Read settings",
                        "inputSchema": {"type": "object", "properties": {}}
                    },
                    {
                        "name": "settings.update",
                        "description": "Update settings",
                        "inputSchema": {"type": "object", "properties": {}}
                    },
                    {
                        "name": "app.open",
                        "description": TOOL_DESCRIPTION,
                        "inputSchema": {"type": "object", "properties": {}},
                        "annotations": {"readOnlyHint": True},
                        "_meta": {
                            "ui": {"resourceUri": "ui://fixture/app"},
                            "openai/ui": {
                                "entrypoints": [{"type": "global"}]
                            }
                        }
                    }
                ]
            }
        })
    elif method == "resources/read":
        uri = (msg.get("params") or {}).get("uri")
        send({
            "jsonrpc": "2.0",
            "id": ident,
            "result": {
                "contents": [
                    {
                        "uri": uri,
                        "mimeType": "text/html;profile=mcp-app",
                        "text": HTML,
                        "_meta": {
                            "openai/ui": {
                                "availableDisplayModes": [
                                    "inline",
                                    "fullscreen"
                                ]
                            }
                        }
                    }
                ]
            }
        })
    elif ident is not None:
        send({
            "jsonrpc": "2.0",
            "id": ident,
            "error": {"code": -32601, "message": "Method not found"}
        })
'''


def _write_server(
    path: Path,
    *,
    description: str = "Open app v1",
    server_version: str = "1.0.0",
    html: str = "<html>v1</html>",
) -> None:
    path.write_text(
        SERVER.replace("__DESCRIPTION__", description)
        .replace("__SERVER_VERSION__", server_version)
        .replace("__HTML__", html),
        encoding="utf-8",
    )


def _make_plugin(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "plugin.json").write_text(
        json.dumps(
            {
                "$schema": "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",
                "name": "freshness-demo",
                "version": "1.4.0",
                "description": "Freshness fixture",
                "extensions": {
                    "com.openai": {
                        "interface": {
                            "displayName": "Freshness Demo",
                            "shortDescription": "Freshness demo",
                            "longDescription": "Freshness fixture"
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    skill = root / "skills" / "freshness"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\nname: freshness\ndescription: Freshness fixture.\n---\n",
        encoding="utf-8",
    )
    server = root / "server.py"
    _write_server(server)
    (root / "mcp.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "fixture": {
                        "type": "stdio",
                        "command": sys.executable,
                        "args": [str(server)]
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    active = root / "extensions" / "openai"
    active.mkdir(parents=True)
    (active / "runtime.ts").write_text(
        '''
const uri = "ui://fixture/app";
const settings = {"openai/settings": {}};
const ui = {
  "openai/ui": {
    entrypoints: [{"type": "global"}],
    availableDisplayModes: ["inline", "fullscreen"]
  }
};
''',
        encoding="utf-8",
    )
    return server


def _verified_dossier(root: Path) -> str:
    report = run_extension_verification(root)
    if not report["verification_verified"]:
        raise AssertionError(report)
    write_verification_dossier(root, report)
    return report["artifacts"]["dossier"]


class RuntimeFreshnessTests(unittest.TestCase):
    def test_unchanged_runtime_is_fresh(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "plugin"
            _make_plugin(root)
            dossier = _verified_dossier(root)

            report = run_verification_freshness(
                root,
                verification_evidence=dossier,
            )

            self.assertTrue(report["freshness_verified"])
            self.assertEqual(
                report["drift"]["changed_components"],
                [],
            )
            self.assertEqual(report["blocking_reasons"], [])

    def test_tool_descriptor_drift_is_detected_without_package_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "plugin"
            server = _make_plugin(root)
            before_digest = plugin_package_digest(root)
            dossier = _verified_dossier(root)

            _write_server(
                server,
                description="Open app v2 changed",
            )
            self.assertEqual(
                before_digest,
                plugin_package_digest(root),
            )

            report = run_verification_freshness(
                root,
                verification_evidence=dossier,
            )

            self.assertFalse(report["freshness_verified"])
            self.assertIn(
                "remote_mcp_surface_drift",
                report["blocking_reasons"],
            )
            self.assertIn(
                "tools",
                report["drift"]["changed_components"],
            )

    def test_ui_resource_content_drift_is_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "plugin"
            server = _make_plugin(root)
            dossier = _verified_dossier(root)

            _write_server(
                server,
                html="<html>v2 changed UI</html>",
            )
            report = run_verification_freshness(
                root,
                verification_evidence=dossier,
            )

            self.assertFalse(report["freshness_verified"])
            self.assertIn(
                "resources",
                report["drift"]["changed_components"],
            )

    def test_server_info_only_change_does_not_make_surface_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "plugin"
            server = _make_plugin(root)
            dossier = _verified_dossier(root)

            _write_server(
                server,
                server_version="9.9.9",
            )
            report = run_verification_freshness(
                root,
                verification_evidence=dossier,
            )

            self.assertTrue(report["freshness_verified"])
            self.assertEqual(
                report["drift"]["changed_components"],
                [],
            )

    def test_tampered_runtime_baseline_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "plugin"
            _make_plugin(root)
            dossier = _verified_dossier(root)
            payload = json.loads(
                (root / dossier).read_text(encoding="utf-8")
            )
            runtime_path = (
                root / payload["artifacts"]["runtime"]
            )
            runtime_path.write_text(
                json.dumps({"tampered": True}),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                FreshnessError,
                "does not match dossier",
            ):
                run_verification_freshness(
                    root,
                    verification_evidence=dossier,
                )

    def test_evidence_write_and_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "plugin"
            _make_plugin(root)
            dossier = _verified_dossier(root)

            report = run_verification_freshness(
                root,
                verification_evidence=dossier,
                write_evidence=True,
            )
            self.assertTrue(
                (root / report["evidence_output"]).is_file()
            )

            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "mado_plugin_factory",
                    "freshness",
                    str(root),
                    "--verification-evidence",
                    dossier,
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertTrue(payload["freshness_verified"])


if __name__ == "__main__":
    unittest.main()
