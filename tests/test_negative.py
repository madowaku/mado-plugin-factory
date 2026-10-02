from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from mado_plugin_factory.negative import (
    NegativeContractError,
    run_negative_contract,
)


STDIO_SERVER = r'''
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).parent
STATE = json.loads((ROOT / "negative-state.json").read_text())
MARKER = ROOT / "unsafe-negative-called.txt"

def send(value):
    sys.stdout.write(json.dumps(value) + "\n")
    sys.stdout.flush()

TOOLS = [
    {
        "name": "fixture.invalid",
        "description": "Reject invalid fixture input.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "identifier": {"type": "string"}
            }
        },
        "annotations": {
            "readOnlyHint": True,
            "openWorldHint": False,
            "destructiveHint": False
        }
    },
    {
        "name": "fixture.not_found",
        "description": "Return deterministic not-found failure.",
        "inputSchema": {"type": "object", "properties": {}},
        "annotations": {
            "readOnlyHint": True,
            "openWorldHint": False,
            "destructiveHint": False
        }
    },
    {
        "name": "fixture.recoverable",
        "description": "Return deterministic recoverable failure.",
        "inputSchema": {"type": "object", "properties": {}},
        "annotations": {
            "readOnlyHint": True,
            "openWorldHint": False,
            "destructiveHint": False
        }
    },
    {
        "name": "fixture.unsafe",
        "description": "Unsafe negative fixture.",
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
        if name == "fixture.invalid":
            if STATE.get("invalid_success"):
                send({
                    "jsonrpc": "2.0",
                    "id": ident,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": "PRIVATE SUCCESS VALUE"
                            }
                        ],
                        "isError": False
                    }
                })
            else:
                send({
                    "jsonrpc": "2.0",
                    "id": ident,
                    "error": {
                        "code": STATE.get("invalid_code", -32602),
                        "message": "PRIVATE INVALID INPUT DETAIL"
                    }
                })
        elif name == "fixture.not_found":
            send({
                "jsonrpc": "2.0",
                "id": ident,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": "PRIVATE NOT FOUND DETAIL"
                        }
                    ],
                    "structuredContent": {
                        "kind": "not_found",
                        "retryable": False
                    },
                    "isError": True
                }
            })
        elif name == "fixture.recoverable":
            send({
                "jsonrpc": "2.0",
                "id": ident,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": "PRIVATE RETRY LATER DETAIL"
                        }
                    ],
                    "isError": True
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
                    ],
                    "isError": True
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


def _make_stdio_plugin(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    server = root / "server.py"
    server.write_text(
        STDIO_SERVER,
        encoding="utf-8",
    )
    (root / "negative-state.json").write_text(
        json.dumps(
            {
                "invalid_code": -32602,
                "invalid_success": False,
            }
        ),
        encoding="utf-8",
    )
    (root / "mcp.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "fixture": {
                        "type": "stdio",
                        "command": sys.executable,
                        "args": [str(server)],
                    }
                }
            }
        ),
        encoding="utf-8",
    )


def _stdio_contract(root: Path) -> str:
    path = root / "negative-contract.json"
    path.write_text(
        json.dumps(
            {
                "server": "fixture",
                "cases": [
                    {
                        "id": "invalid-input",
                        "category": "invalid_input",
                        "tool": "fixture.invalid",
                        "arguments": {
                            "identifier": "PRIVATE INVALID VALUE"
                        },
                        "expect": {
                            "outcome": "protocol_error",
                            "protocol_error_code": -32602,
                            "structured_content": "forbidden",
                            "content_types": [],
                        },
                    },
                    {
                        "id": "not-found",
                        "category": "not_found",
                        "tool": "fixture.not_found",
                        "arguments": {},
                        "expect": {
                            "outcome": "tool_error",
                            "structured_content": "required",
                            "content_types": ["text"],
                        },
                    },
                    {
                        "id": "recoverable",
                        "category": "recoverable_error",
                        "tool": "fixture.recoverable",
                        "arguments": {},
                        "expect": {
                            "outcome": "tool_error",
                            "structured_content": "forbidden",
                            "content_types": ["text"],
                        },
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    return path.relative_to(root).as_posix()


def _verification(
    root: Path,
    *,
    name: str,
    verification_id: str,
) -> str:
    path = root / name
    path.write_text(
        json.dumps(
            {
                "evidence_state": "executed",
                "verification_verified": True,
                "verification_id": verification_id,
            }
        ),
        encoding="utf-8",
    )
    return path.relative_to(root).as_posix()


class _AuthHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: object) -> None:
        return

    def _json(
        self,
        status: int,
        payload: dict,
        *,
        challenge: str | None = None,
    ) -> None:
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header(
            "Content-Type",
            "application/json",
        )
        self.send_header(
            "Content-Length",
            str(len(raw)),
        )
        if challenge is not None:
            self.send_header(
                "WWW-Authenticate",
                challenge,
            )
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self) -> None:
        length = int(
            self.headers.get(
                "Content-Length",
                "0",
            )
        )
        body = self.rfile.read(length)
        msg = json.loads(
            body.decode("utf-8")
        )
        method = msg.get("method")
        ident = msg.get("id")
        authorized = (
            self.headers.get(
                "Authorization"
            )
            == "Bearer fixture-token"
        )

        if method in {
            "server/discover",
            "tools/list",
        } and not authorized:
            self._json(
                401,
                {
                    "error": "PRIVATE AUTH BODY"
                },
                challenge=(
                    'Bearer resource_metadata='
                    '"https://private.example/.well-known/'
                    'oauth-protected-resource"'
                ),
            )
            return

        if method == "server/discover":
            self._json(
                200,
                {
                    "jsonrpc": "2.0",
                    "id": ident,
                    "result": {
                        "resultType": "complete",
                        "supportedVersions": [
                            "2026-07-28"
                        ],
                        "capabilities": {
                            "tools": {}
                        },
                    },
                },
            )
            return

        if method == "tools/list":
            self._json(
                200,
                {
                    "jsonrpc": "2.0",
                    "id": ident,
                    "result": {
                        "tools": [
                            {
                                "name": "private.read",
                                "description": (
                                    "Read private fixture data."
                                ),
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {},
                                },
                                "annotations": {
                                    "readOnlyHint": True,
                                    "openWorldHint": False,
                                    "destructiveHint": False,
                                },
                            }
                        ]
                    },
                },
            )
            return

        if method == "tools/call" and not authorized:
            self._json(
                401,
                {
                    "error": "PRIVATE AUTH BODY"
                },
                challenge=(
                    'Bearer resource_metadata='
                    '"https://private.example/.well-known/'
                    'oauth-protected-resource"'
                ),
            )
            return

        self._json(
            200,
            {
                "jsonrpc": "2.0",
                "id": ident,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": "PRIVATE AUTHORIZED DATA",
                        }
                    ],
                    "isError": False,
                },
            },
        )


class _HttpFixture:
    def __enter__(self) -> "_HttpFixture":
        self.server = ThreadingHTTPServer(
            ("127.0.0.1", 0),
            _AuthHandler,
        )
        self.thread = threading.Thread(
            target=self.server.serve_forever,
            daemon=True,
        )
        self.thread.start()
        return self

    @property
    def url(self) -> str:
        host, port = self.server.server_address
        return f"http://{host}:{port}/mcp"

    def __exit__(
        self,
        exc_type,
        exc,
        tb,
    ) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)


def _make_http_plugin(
    root: Path,
    url: str,
) -> str:
    root.mkdir(parents=True, exist_ok=True)
    (root / "mcp.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "auth": {
                        "type": "streamable-http",
                        "url": url,
                        "http_headers": {
                            "Authorization": (
                                "Bearer fixture-token"
                            )
                        },
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    contract = root / "auth-negative.json"
    contract.write_text(
        json.dumps(
            {
                "server": "auth",
                "cases": [
                    {
                        "id": "anonymous-private-read",
                        "category": "unauthorized",
                        "tool": "private.read",
                        "request_context": "anonymous",
                        "arguments": {},
                        "expect": {
                            "outcome": "http_error",
                            "http_status": 401,
                            "auth_challenge": "required",
                            "structured_content": "forbidden",
                            "content_types": [],
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return contract.relative_to(root).as_posix()


class NegativeContractReplayTests(unittest.TestCase):
    def test_record_then_replay_negative_contracts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "plugin"
            _make_stdio_plugin(root)
            contract = _stdio_contract(root)

            baseline = run_negative_contract(
                root,
                contract=contract,
                write_evidence=True,
            )
            self.assertEqual(
                baseline["mode"],
                "record",
            )
            self.assertTrue(
                baseline["negative_passed"]
            )
            self.assertFalse(
                baseline["negative_verified"]
            )

            replay = run_negative_contract(
                root,
                contract=contract,
                baseline_evidence=baseline[
                    "evidence_output"
                ],
            )
            self.assertEqual(
                replay["mode"],
                "replay",
            )
            self.assertTrue(
                replay["negative_verified"]
            )
            self.assertEqual(
                replay["blocking_reasons"],
                [],
            )

    def test_protocol_error_drift_is_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "plugin"
            _make_stdio_plugin(root)
            contract = _stdio_contract(root)
            baseline = run_negative_contract(
                root,
                contract=contract,
                write_evidence=True,
            )

            (root / "negative-state.json").write_text(
                json.dumps(
                    {
                        "invalid_code": -32001,
                        "invalid_success": False,
                    }
                ),
                encoding="utf-8",
            )
            replay = run_negative_contract(
                root,
                contract=contract,
                baseline_evidence=baseline[
                    "evidence_output"
                ],
            )
            self.assertFalse(
                replay["negative_verified"]
            )
            self.assertTrue(
                any(
                    "unexpected_protocol_error_code"
                    in item
                    or "negative_contract_drift"
                    in item
                    for item in replay[
                        "blocking_reasons"
                    ]
                )
            )

    def test_negative_case_success_is_a_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "plugin"
            _make_stdio_plugin(root)
            contract = _stdio_contract(root)
            (root / "negative-state.json").write_text(
                json.dumps(
                    {
                        "invalid_code": -32602,
                        "invalid_success": True,
                    }
                ),
                encoding="utf-8",
            )

            report = run_negative_contract(
                root,
                contract=contract,
            )
            self.assertFalse(
                report["negative_passed"]
            )
            self.assertIn(
                "invalid-input:"
                "negative_case_unexpectedly_succeeded",
                report["blocking_reasons"],
            )

    def test_non_read_only_negative_tool_is_never_called(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "plugin"
            _make_stdio_plugin(root)
            contract = root / "unsafe.json"
            contract.write_text(
                json.dumps(
                    {
                        "cases": [
                            {
                                "id": "unsafe",
                                "category": "recoverable_error",
                                "tool": "fixture.unsafe",
                                "arguments": {},
                                "expect": {
                                    "outcome": "tool_error",
                                    "content_types": [],
                                },
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            report = run_negative_contract(
                root,
                contract="unsafe.json",
            )
            self.assertFalse(
                report["negative_passed"]
            )
            self.assertFalse(
                (
                    root
                    / "unsafe-negative-called.txt"
                ).exists()
            )
            self.assertIn(
                "unsafe:"
                "tool_not_explicitly_read_only",
                report["blocking_reasons"],
            )

    def test_unauthorized_http_requires_401_challenge(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "plugin"
            with _HttpFixture() as fixture:
                contract = _make_http_plugin(
                    root,
                    fixture.url,
                )
                report = run_negative_contract(
                    root,
                    contract=contract,
                    write_evidence=True,
                )

            self.assertTrue(
                report["negative_passed"]
            )
            observation = report["cases"][0][
                "observation"
            ]
            self.assertEqual(
                observation["outcome"],
                "http_error",
            )
            self.assertEqual(
                observation["http_status"],
                401,
            )
            self.assertTrue(
                observation[
                    "www_authenticate_present"
                ]
            )
            self.assertIsNotNone(
                observation[
                    "www_authenticate_sha256"
                ]
            )

            text = (
                root / report["evidence_output"]
            ).read_text(encoding="utf-8")
            self.assertNotIn(
                "fixture-token",
                text,
            )
            self.assertNotIn(
                "PRIVATE AUTH BODY",
                text,
            )
            self.assertNotIn(
                "private.example",
                text,
            )

    def test_baseline_verification_binding_is_enforced(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "plugin"
            _make_stdio_plugin(root)
            contract = _stdio_contract(root)
            one = _verification(
                root,
                name="verification-one.json",
                verification_id="one",
            )
            two = _verification(
                root,
                name="verification-two.json",
                verification_id="two",
            )
            baseline = run_negative_contract(
                root,
                contract=contract,
                verification_evidence=one,
                write_evidence=True,
            )

            with self.assertRaisesRegex(
                NegativeContractError,
                "not bound",
            ):
                run_negative_contract(
                    root,
                    contract=contract,
                    baseline_evidence=baseline[
                        "evidence_output"
                    ],
                    verification_evidence=two,
                )

    def test_evidence_hides_arguments_and_error_details(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "plugin"
            _make_stdio_plugin(root)
            contract = _stdio_contract(root)
            report = run_negative_contract(
                root,
                contract=contract,
                write_evidence=True,
            )
            text = (
                root / report["evidence_output"]
            ).read_text(encoding="utf-8")
            self.assertNotIn(
                "PRIVATE INVALID VALUE",
                text,
            )
            self.assertNotIn(
                "PRIVATE INVALID INPUT DETAIL",
                text,
            )
            self.assertNotIn(
                "PRIVATE NOT FOUND DETAIL",
                text,
            )
            self.assertNotIn(
                "PRIVATE RETRY LATER DETAIL",
                text,
            )

    def test_cli_record_and_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "plugin"
            _make_stdio_plugin(root)
            contract = _stdio_contract(root)

            record = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "mado_plugin_factory",
                    "negative",
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
            baseline = json.loads(
                record.stdout
            )

            replay = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "mado_plugin_factory",
                    "negative",
                    str(root),
                    "--contract",
                    contract,
                    "--baseline",
                    baseline[
                        "evidence_output"
                    ],
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
            payload = json.loads(
                replay.stdout
            )
            self.assertTrue(
                payload["negative_verified"]
            )


if __name__ == "__main__":
    unittest.main()
