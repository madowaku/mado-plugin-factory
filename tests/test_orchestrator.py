from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from mado_plugin_factory.orchestrator import (
    VerificationOrchestratorError,
    public_verification_report,
    run_extension_verification,
    write_verification_dossier,
)


SERVER = r'''
import json
import sys

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
                        "name": "orchestrator-fixture",
                        "version": "1.0.0"
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
                        "inputSchema": {"type": "object", "properties": {}}
                    },
                    {
                        "name": "settings.update",
                        "inputSchema": {"type": "object", "properties": {}}
                    },
                    {
                        "name": "app.open",
                        "inputSchema": {"type": "object", "properties": {}},
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
                        "text": "<html></html>",
                        "_meta": {
                            "openai/ui": {
                                "availableDisplayModes": [
                                    "inline",
                                    "fullscreen"
                                ],
                                "preferredDisplayMode": "fullscreen"
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


def _make_plugin(
    root: Path,
    *,
    host_required: bool = True,
    broken_mentions: bool = False,
) -> None:
    (root / "plugin.json").write_text(
        json.dumps(
            {
                "$schema": "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",
                "name": "orchestrator-demo",
                "version": "0.1.0",
                "description": "orchestrator fixture",
                "extensions": {
                    "com.openai": {
                        "interface": {
                            "displayName": "Orchestrator Demo",
                            "shortDescription": "demo",
                            "longDescription": "demo"
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    server = root / "server.py"
    server.write_text(SERVER, encoding="utf-8")
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
    source = '''
const uri = "ui://fixture/app";
const settings = {"openai/settings": {}};
const ui = {
  "openai/ui": {
    entrypoints: [{"type": "global"}],
    availableDisplayModes: ["inline", "fullscreen"]
  }
};
'''
    if host_required:
        source += '''
const deep = "openai/deepLink";
const model = "ui/update-model-context";
const form = "openai/elicitation";
'''
    if broken_mentions:
        source += '''
const mentions = {
  "openai/extensions": {"mentions/search": {}},
  "ui": {"visibility": ["app"]}
};
'''
    (active / "runtime.ts").write_text(
        source,
        encoding="utf-8",
    )


def _capture(path: Path, *, attested: bool = True, include_model: bool = True) -> None:
    events = [
        {
            "direction": "host_to_app",
            "method": "ui/initialize",
            "call_id": 0,
            "result": {
                "hostContext": {
                    "openai/deepLink": {
                        "url": "/private/item?customer=SECRET"
                    }
                }
            }
        }
    ]
    if include_model:
        events.extend(
            [
                {
                    "direction": "app_to_host",
                    "method": "ui/update-model-context",
                    "call_id": 12,
                    "params": {
                        "content": [
                            {
                                "type": "text",
                                "text": "PRIVATE MODEL VALUE"
                            }
                        ]
                    }
                },
                {
                    "direction": "host_to_app",
                    "method": "ui/update-model-context",
                    "call_id": 12,
                    "result": {
                        "_meta": {
                            "openai/modelContext": {
                                "updateId": "PRIVATE UPDATE ID"
                            }
                        }
                    }
                }
            ]
        )
    events.extend(
        [
            {
                "direction": "server_to_host",
                "method": "openai/elicitation/create",
                "call_id": 99,
                "params": {
                    "mode": "form",
                    "message": "PRIVATE FORM MESSAGE",
                    "requestedSchema": {
                        "type": "object",
                        "properties": {
                            "secret": {"type": "string"}
                        }
                    }
                }
            },
            {
                "direction": "host_to_server",
                "method": "openai/elicitation/create",
                "call_id": 99,
                "result": {
                    "action": "accept",
                    "content": {"secret": "PRIVATE FORM VALUE"}
                }
            }
        ]
    )
    path.write_text(
        json.dumps(
            {
                "capture": {
                    "product": "chatgpt",
                    "surface": "web",
                    "mode": "developer_mode",
                    "executed": True,
                    "attested_chatgpt_capture": attested
                },
                "events": events
            }
        ),
        encoding="utf-8",
    )


class ExtensionVerificationOrchestratorTests(unittest.TestCase):
    def test_runtime_pass_with_host_required_waits_for_capture(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_plugin(root)

            report = run_extension_verification(root)

            self.assertEqual(
                report["verification_state"],
                "awaiting_host_capture",
            )
            self.assertFalse(report["verification_verified"])
            self.assertTrue(report["needs_followup"])
            self.assertEqual(
                report["stages"]["runtime_smoke"]["state"],
                "passed",
            )
            self.assertEqual(
                report["stages"]["host_capture"]["state"],
                "awaiting",
            )
            self.assertIn(
                "deep_links",
                report["summary"]["host_required_extensions"],
            )

    def test_attested_capture_closes_full_verification(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_plugin(root)
            capture = root / "capture.json"
            _capture(capture)

            report = run_extension_verification(
                root,
                capture_input=capture,
                surface="web",
                capture_mode="developer_mode",
                executed=True,
                attest_chatgpt_capture=True,
            )

            self.assertEqual(
                report["verification_state"],
                "verified_chatgpt_host",
            )
            self.assertTrue(report["verification_verified"])
            self.assertFalse(report["needs_followup"])
            self.assertEqual(
                report["stages"]["host_replay"]["state"],
                "verified",
            )
            self.assertEqual(
                report["summary"]["host_missing_extensions"],
                [],
            )

    def test_unattested_capture_remains_external_followup(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_plugin(root)
            capture = root / "capture.json"
            _capture(capture, attested=False)

            report = run_extension_verification(
                root,
                capture_input=capture,
                surface="web",
                capture_mode="developer_mode",
                executed=True,
                attest_chatgpt_capture=False,
            )

            self.assertEqual(
                report["verification_state"],
                "awaiting_capture_attestation",
            )
            self.assertFalse(report["verification_verified"])
            self.assertEqual(
                report["stages"]["host_replay"]["state"],
                "replayed_unattested",
            )

    def test_missing_host_event_is_incomplete_not_attestation_wait(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_plugin(root)
            capture = root / "capture.json"
            _capture(capture, include_model=False)

            report = run_extension_verification(
                root,
                capture_input=capture,
                surface="web",
                capture_mode="developer_mode",
                executed=True,
                attest_chatgpt_capture=True,
            )

            self.assertEqual(
                report["verification_state"],
                "host_incomplete",
            )
            self.assertIn(
                "model_app_context",
                report["summary"]["host_missing_extensions"],
            )

    def test_runtime_only_extensions_can_finish_without_host_capture(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_plugin(root, host_required=False)

            report = run_extension_verification(root)

            self.assertEqual(
                report["verification_state"],
                "verified_mcp_server",
            )
            self.assertTrue(report["verification_verified"])
            self.assertEqual(
                report["stages"]["host_capture"]["state"],
                "not_required",
            )
            self.assertEqual(
                report["stages"]["host_replay"]["state"],
                "not_required",
            )

    def test_missing_runtime_metadata_stops_before_host_capture(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_plugin(
                root,
                host_required=False,
                broken_mentions=True,
            )

            report = run_extension_verification(root)

            self.assertEqual(
                report["verification_state"],
                "runtime_failed",
            )
            self.assertFalse(report["verification_verified"])
            self.assertIn(
                "composer_mentions",
                report["summary"]["runtime_missing_extensions"],
            )

    def test_dossier_write_is_private_and_force_guarded(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_plugin(root)
            capture = root / "capture.json"
            _capture(capture)

            report = run_extension_verification(
                root,
                capture_input=capture,
                surface="web",
                capture_mode="developer_mode",
                executed=True,
                attest_chatgpt_capture=True,
            )
            first = write_verification_dossier(root, report)
            second = write_verification_dossier(root, report)
            self.assertEqual(first, second)

            output = root / report["output"]
            expected = {
                "dossier.json",
                "runtime.json",
                "capture.json",
                "trace.json",
                "host.json",
            }
            self.assertEqual(
                {path.name for path in output.iterdir()},
                expected,
            )
            all_text = "\n".join(
                path.read_text(encoding="utf-8")
                for path in output.iterdir()
            )
            self.assertNotIn("PRIVATE MODEL VALUE", all_text)
            self.assertNotIn("PRIVATE FORM VALUE", all_text)
            self.assertNotIn("PRIVATE UPDATE ID", all_text)
            self.assertNotIn("/private/item", all_text)

            dossier = output / "dossier.json"
            dossier.write_text("{}\n", encoding="utf-8")
            with self.assertRaises(
                VerificationOrchestratorError
            ):
                write_verification_dossier(root, report)
            write_verification_dossier(
                root,
                report,
                force=True,
            )

    def test_capture_options_require_capture_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_plugin(root)
            with self.assertRaisesRegex(
                VerificationOrchestratorError,
                "require --capture",
            ):
                run_extension_verification(
                    root,
                    executed=True,
                )

    def test_public_report_hides_artifact_payloads(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_plugin(root)
            report = run_extension_verification(root)
            public = public_verification_report(report)
            self.assertNotIn("_artifacts", public)

    def test_cli_orchestrates_and_writes_verified_dossier(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_plugin(root)
            capture = root / "capture.json"
            _capture(capture)

            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "mado_plugin_factory",
                    "verify-extensions",
                    str(root),
                    "--capture",
                    str(capture),
                    "--surface",
                    "web",
                    "--capture-mode",
                    "developer_mode",
                    "--executed",
                    "--attest-chatgpt-capture",
                    "--write",
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            report = json.loads(proc.stdout)
            self.assertTrue(report["verification_verified"])
            self.assertTrue(
                (
                    root
                    / report["artifacts"]["dossier"]
                ).is_file()
            )


if __name__ == "__main__":
    unittest.main()
