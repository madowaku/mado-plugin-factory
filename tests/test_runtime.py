from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from mado_plugin_factory.runtime import (
    RuntimeSmokeError,
    run_extension_runtime_smoke,
)


SERVER_TEMPLATE = r'''
import json
import sys

LEGACY = __LEGACY__

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
        if LEGACY:
            send({
                "jsonrpc": "2.0",
                "id": ident,
                "error": {"code": -32601, "message": "Method not found"},
            })
        else:
            send({
                "jsonrpc": "2.0",
                "id": ident,
                "result": {
                    "resultType": "complete",
                    "supportedVersions": ["2026-07-28"],
                    "_meta": {
                        "io.modelcontextprotocol/serverInfo": {
                            "name": "fixture-runtime",
                            "version": "1.0.0",
                        }
                    },
                    "capabilities": {
                        "tools": {},
                        "extensions": {
                            "openai/settings": {
                                "readTool": "settings.read",
                                "updateTool": "settings.update",
                            }
                        },
                    },
                },
            })
    elif method == "initialize":
        send({
            "jsonrpc": "2.0",
            "id": ident,
            "result": {
                "protocolVersion": "2025-11-25",
                "serverInfo": {
                    "name": "fixture-runtime",
                    "version": "1.0.0",
                },
                "capabilities": {
                    "tools": {},
                    "experimental": {
                        "openai/settings": {
                            "readTool": "settings.read",
                            "updateTool": "settings.update",
                        }
                    },
                },
            },
        })
    elif method == "notifications/initialized":
        pass
    elif method == "tools/list":
        send({
            "jsonrpc": "2.0",
            "id": ident,
            "result": {
                "tools": [
                    {
                        "name": "settings.read",
                        "inputSchema": {"type": "object", "properties": {}},
                    },
                    {
                        "name": "settings.update",
                        "inputSchema": {"type": "object", "properties": {}},
                    },
                    {
                        "name": "cad.library",
                        "inputSchema": {"type": "object", "properties": {}},
                        "_meta": {
                            "ui": {
                                "resourceUri": "ui://fixture/library",
                            },
                            "openai/ui": {
                                "entrypoints": [{"type": "global"}],
                            },
                        },
                    },
                ]
            },
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
                        "text": "<!doctype html><html></html>",
                        "_meta": {
                            "openai/ui": {
                                "availableDisplayModes": [
                                    "inline",
                                    "fullscreen",
                                ],
                                "preferredDisplayMode": "fullscreen",
                            }
                        },
                    }
                ]
            },
        })
    else:
        if ident is not None:
            send({
                "jsonrpc": "2.0",
                "id": ident,
                "error": {"code": -32601, "message": "Method not found"},
            })
'''


def _make_plugin(
    root: Path,
    *,
    legacy: bool = False,
    extra_source: str = "",
    two_servers: bool = False,
) -> None:
    (root / "plugin.json").write_text(
        json.dumps(
            {
                "$schema": "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",
                "name": "runtime-demo",
                "version": "0.1.0",
                "description": "runtime smoke fixture",
                "extensions": {
                    "com.openai": {
                        "interface": {
                            "displayName": "Runtime Demo",
                            "shortDescription": "runtime demo",
                            "longDescription": "runtime demo",
                        }
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    server_path = root / "runtime_server.py"
    server_path.write_text(
        SERVER_TEMPLATE.replace(
            "__LEGACY__",
            "True" if legacy else "False",
        ),
        encoding="utf-8",
    )
    servers = {
        "fixture": {
            "type": "stdio",
            "command": sys.executable,
            "args": [str(server_path)],
        }
    }
    if two_servers:
        servers["other"] = dict(servers["fixture"])
    (root / "mcp.json").write_text(
        json.dumps(
            {
                "$schema": "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json",
                "mcpServers": servers,
            }
        ),
        encoding="utf-8",
    )
    active = root / "extensions" / "openai"
    active.mkdir(parents=True)
    (active / "runtime.ts").write_text(
        '''
const uri = "ui://fixture/library";
const metadata = {
  "openai/ui": {
    entrypoints: [{"type": "global"}],
    availableDisplayModes: ["inline", "fullscreen"]
  },
  "openai/settings": {}
};
'''
        + extra_source,
        encoding="utf-8",
    )


class ExtensionRuntimeSmokeTests(unittest.TestCase):
    def test_modern_stdio_verifies_probeable_extensions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_plugin(root)
            report = run_extension_runtime_smoke(root)

            self.assertEqual(
                report["protocol"]["negotiated_version"],
                "2026-07-28",
            )
            self.assertEqual(report["protocol"]["era"], "modern")
            self.assertTrue(report["runtime_smoke_passed"])
            self.assertTrue(report["runtime_verified"])
            self.assertIn(
                "sidebar_app",
                report["verified_extensions"],
            )
            self.assertIn(
                "plugin_settings",
                report["verified_extensions"],
            )
            self.assertIn(
                "display_modes",
                report["verified_extensions"],
            )
            self.assertEqual(report["missing_extensions"], [])
            self.assertEqual(
                report["observations"]["tool_count"],
                3,
            )

    def test_auto_falls_back_to_legacy_stdio(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_plugin(root, legacy=True)
            report = run_extension_runtime_smoke(root)

            self.assertEqual(report["protocol"]["era"], "legacy")
            self.assertEqual(
                report["protocol"]["negotiated_version"],
                "2025-11-25",
            )
            self.assertTrue(report["runtime_verified"])

    def test_host_required_extension_prevents_full_runtime_verified(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_plugin(
                root,
                extra_source='\nconst deep = "openai/deepLink";\n',
            )
            report = run_extension_runtime_smoke(root)

            self.assertTrue(report["runtime_smoke_passed"])
            self.assertFalse(report["runtime_verified"])
            self.assertIn(
                "deep_links",
                report["host_required_extensions"],
            )
            check = {
                item["id"]: item for item in report["extension_checks"]
            }
            self.assertEqual(
                check["deep_links"]["state"],
                "host_required",
            )

    def test_missing_runtime_advertisement_fails_smoke(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_plugin(
                root,
                extra_source='''
const mentions = {
  "openai/extensions": {"mentions/search": {}},
  "ui": {"visibility": ["app"]}
};
''',
            )
            report = run_extension_runtime_smoke(root)

            self.assertFalse(report["runtime_smoke_passed"])
            self.assertFalse(report["runtime_verified"])
            self.assertIn(
                "composer_mentions",
                report["missing_extensions"],
            )

    def test_evidence_write_is_contained_and_force_guarded(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_plugin(root)
            report = run_extension_runtime_smoke(
                root,
                write_evidence=True,
            )
            evidence = root / report["evidence_output"]
            self.assertTrue(evidence.is_file())
            payload = json.loads(evidence.read_text(encoding="utf-8"))
            self.assertTrue(payload["runtime_verified"])

            evidence.write_text("{}\n", encoding="utf-8")
            with self.assertRaises(RuntimeSmokeError):
                run_extension_runtime_smoke(
                    root,
                    write_evidence=True,
                )
            run_extension_runtime_smoke(
                root,
                write_evidence=True,
                force=True,
            )

            with self.assertRaises(RuntimeSmokeError):
                run_extension_runtime_smoke(
                    root,
                    write_evidence=True,
                    evidence_output="../escape.json",
                )

    def test_multiple_servers_require_explicit_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_plugin(root, two_servers=True)
            with self.assertRaisesRegex(
                RuntimeSmokeError,
                "select an MCP server",
            ):
                run_extension_runtime_smoke(root)

            report = run_extension_runtime_smoke(
                root,
                server="fixture",
            )
            self.assertTrue(report["runtime_verified"])

    def test_cli_executes_and_writes_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_plugin(root)
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "mado_plugin_factory",
                    "runtime-smoke",
                    str(root),
                    "--write-evidence",
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            report = json.loads(proc.stdout)
            self.assertTrue(report["runtime_verified"])
            self.assertTrue(
                (root / report["evidence_output"]).is_file()
            )


if __name__ == "__main__":
    unittest.main()
