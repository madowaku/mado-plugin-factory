from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from mado_plugin_factory.behavior import (
    CanaryError,
    run_behavior_canary,
)


SERVER = r'''
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).parent
STATE = json.loads((ROOT / "remote-state.json").read_text())
MARKER = ROOT / "unsafe-called.txt"

def send(value):
    sys.stdout.write(json.dumps(value) + "\n")
    sys.stdout.flush()

TOOLS = [
    {
        "name": "fixture.read",
        "description": "Read deterministic fixture data.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "token": {"type": "string"}
            }
        },
        "outputSchema": {
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "version": {"type": "string"},
                "items": {"type": "array"}
            }
        },
        "annotations": {
            "readOnlyHint": True,
            "openWorldHint": False,
            "destructiveHint": False
        }
    },
    {
        "name": "fixture.tool_error",
        "description": "Return a deterministic tool error.",
        "inputSchema": {"type": "object", "properties": {}},
        "annotations": {
            "readOnlyHint": True,
            "openWorldHint": False,
            "destructiveHint": False
        }
    },
    {
        "name": "fixture.protocol_error",
        "description": "Return a deterministic protocol error.",
        "inputSchema": {"type": "object", "properties": {}},
        "annotations": {
            "readOnlyHint": True,
            "openWorldHint": False,
            "destructiveHint": False
        }
    },
    {
        "name": "fixture.unsafe",
        "description": "Unsafe fixture tool.",
        "inputSchema": {"type": "object", "properties": {}},
        "annotations": {
            "readOnlyHint": False,
            "destructiveHint": True
        }
    }
]

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
                "capabilities": {"tools": {}}
            }
        })
    elif method == "tools/list":
        send({
            "jsonrpc": "2.0",
            "id": ident,
            "result": {"tools": TOOLS}
        })
    elif method == "tools/call":
        params = msg.get("params") or {}
        name = params.get("name")
        if name == "fixture.read":
            structured = {
                "status": "ok",
                "version": STATE.get("version", "v1"),
                "items": [
                    {"id": "a", "count": 1}
                ]
            }
            if STATE.get("shape") == "changed":
                structured["extra"] = {"enabled": True}
            send({
                "jsonrpc": "2.0",
                "id": ident,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": "PRIVATE RESULT TEXT"
                        }
                    ],
                    "structuredContent": structured,
                    "isError": False
                }
            })
        elif name == "fixture.tool_error":
            send({
                "jsonrpc": "2.0",
                "id": ident,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": "PRIVATE ERROR DETAIL"
                        }
                    ],
                    "isError": True
                }
            })
        elif name == "fixture.protocol_error":
            send({
                "jsonrpc": "2.0",
                "id": ident,
                "error": {
                    "code": -32042,
                    "message": "PRIVATE PROTOCOL DETAIL"
                }
            })
        elif name == "fixture.unsafe":
            MARKER.write_text("called")
            send({
                "jsonrpc": "2.0",
                "id": ident,
                "result": {
                    "content": [
                        {"type": "text", "text": "unsafe"}
                    ]
                }
            })
        else:
            send({
                "jsonrpc": "2.0",
                "id": ident,
                "error": {
                    "code": -32601,
                    "message": "unknown"
                }
            })
'''


def _make_plugin(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    server = root / "server.py"
    server.write_text(SERVER, encoding="utf-8")
    (root / "remote-state.json").write_text(
        json.dumps({"version": "v1", "shape": "stable"}),
        encoding="utf-8",
    )
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


def _contract(root: Path) -> str:
    path = root / "canary-contract.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "0.1",
                "server": "fixture",
                "cases": [
                    {
                        "id": "read-shape",
                        "tool": "fixture.read",
                        "arguments": {
                            "token": "PRIVATE INPUT"
                        },
                        "expect": {
                            "outcome": "success",
                            "structured_content": "required",
                            "content_types": ["text"]
                        },
                        "stable_paths": ["$.version"]
                    },
                    {
                        "id": "tool-error",
                        "tool": "fixture.tool_error",
                        "arguments": {},
                        "expect": {
                            "outcome": "tool_error",
                            "structured_content": "forbidden",
                            "content_types": ["text"]
                        }
                    },
                    {
                        "id": "protocol-error",
                        "tool": "fixture.protocol_error",
                        "arguments": {},
                        "expect": {
                            "outcome": "protocol_error",
                            "structured_content": "forbidden",
                            "content_types": [],
                            "protocol_error_code": -32042
                        }
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return path.relative_to(root).as_posix()


class BehavioralCanaryTests(unittest.TestCase):
    def test_record_then_replay_unchanged_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "plugin"
            _make_plugin(root)
            contract = _contract(root)

            baseline = run_behavior_canary(
                root,
                contract=contract,
                write_evidence=True,
            )
            self.assertEqual(baseline["mode"], "record")
            self.assertTrue(baseline["canary_passed"])
            self.assertFalse(baseline["canary_verified"])

            replay = run_behavior_canary(
                root,
                contract=contract,
                baseline_evidence=baseline["evidence_output"],
            )
            self.assertEqual(replay["mode"], "replay")
            self.assertTrue(replay["canary_verified"])
            self.assertEqual(replay["blocking_reasons"], [])

    def test_stable_path_value_drift_is_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "plugin"
            _make_plugin(root)
            contract = _contract(root)
            baseline = run_behavior_canary(
                root,
                contract=contract,
                write_evidence=True,
            )

            (root / "remote-state.json").write_text(
                json.dumps(
                    {"version": "v2", "shape": "stable"}
                ),
                encoding="utf-8",
            )
            replay = run_behavior_canary(
                root,
                contract=contract,
                baseline_evidence=baseline["evidence_output"],
            )
            self.assertFalse(replay["canary_verified"])
            self.assertTrue(
                any(
                    "behavior_contract_drift" in reason
                    for reason in replay["blocking_reasons"]
                )
            )

    def test_structured_shape_drift_is_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "plugin"
            _make_plugin(root)
            contract = _contract(root)
            baseline = run_behavior_canary(
                root,
                contract=contract,
                write_evidence=True,
            )

            (root / "remote-state.json").write_text(
                json.dumps(
                    {"version": "v1", "shape": "changed"}
                ),
                encoding="utf-8",
            )
            replay = run_behavior_canary(
                root,
                contract=contract,
                baseline_evidence=baseline["evidence_output"],
            )
            self.assertFalse(replay["canary_verified"])

    def test_non_read_only_tool_is_never_called(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "plugin"
            _make_plugin(root)
            contract_path = root / "unsafe.json"
            contract_path.write_text(
                json.dumps(
                    {
                        "cases": [
                            {
                                "id": "unsafe",
                                "tool": "fixture.unsafe",
                                "arguments": {},
                                "expect": {
                                    "outcome": "success",
                                    "content_types": []
                                }
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            report = run_behavior_canary(
                root,
                contract="unsafe.json",
            )
            self.assertFalse(report["canary_passed"])
            self.assertFalse(
                (root / "unsafe-called.txt").exists()
            )
            self.assertIn(
                "unsafe:tool_not_explicitly_read_only",
                report["blocking_reasons"],
            )

    def test_contract_drift_rejects_old_baseline(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "plugin"
            _make_plugin(root)
            contract = _contract(root)
            baseline = run_behavior_canary(
                root,
                contract=contract,
                write_evidence=True,
            )
            path = root / contract
            payload = json.loads(
                path.read_text(encoding="utf-8")
            )
            payload["cases"][0]["stable_paths"] = []
            path.write_text(
                json.dumps(payload),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                CanaryError,
                "contract changed",
            ):
                run_behavior_canary(
                    root,
                    contract=contract,
                    baseline_evidence=baseline["evidence_output"],
                )

    def test_evidence_does_not_store_raw_arguments_or_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "plugin"
            _make_plugin(root)
            contract = _contract(root)
            report = run_behavior_canary(
                root,
                contract=contract,
                write_evidence=True,
            )
            text = (
                root / report["evidence_output"]
            ).read_text(encoding="utf-8")
            self.assertNotIn("PRIVATE INPUT", text)
            self.assertNotIn("PRIVATE RESULT TEXT", text)
            self.assertNotIn("PRIVATE ERROR DETAIL", text)
            self.assertNotIn("PRIVATE PROTOCOL DETAIL", text)

    def test_cli_record_and_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "plugin"
            _make_plugin(root)
            contract = _contract(root)

            record = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "mado_plugin_factory",
                    "canary",
                    str(root),
                    "--contract",
                    contract,
                    "--write-evidence",
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(
                record.returncode,
                0,
                record.stderr,
            )
            baseline = json.loads(record.stdout)

            replay = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "mado_plugin_factory",
                    "canary",
                    str(root),
                    "--contract",
                    contract,
                    "--baseline",
                    baseline["evidence_output"],
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(
                replay.returncode,
                0,
                replay.stderr,
            )
            payload = json.loads(replay.stdout)
            self.assertTrue(payload["canary_verified"])


if __name__ == "__main__":
    unittest.main()
