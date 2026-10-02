from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from mado_plugin_factory.security import (
    SecuritySchemeGateError,
    run_security_scheme_gate,
)


class _SecurityHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(
        self,
        format: str,
        *args: object,
    ) -> None:
        return

    def _json(
        self,
        payload: dict,
    ) -> None:
        raw = json.dumps(
            payload
        ).encode("utf-8")
        self.send_response(200)
        self.send_header(
            "Content-Type",
            "application/json",
        )
        self.send_header(
            "Content-Length",
            str(len(raw)),
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
        raw = self.rfile.read(
            length
        )
        msg = json.loads(
            raw.decode("utf-8")
        )
        method = msg.get("method")
        ident = msg.get("id")

        if method == "server/discover":
            self._json(
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
                }
            )
            return

        if method == "tools/list":
            state = self.server.state
            self._json(
                {
                    "jsonrpc": "2.0",
                    "id": ident,
                    "result": {
                        "tools": [
                            {
                                "name": "scope.read",
                                "description": (
                                    "Read scoped docs."
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
                                "securitySchemes": state[
                                    "scope_schemes"
                                ],
                            },
                            {
                                "name": "admin.read",
                                "description": (
                                    "Read admin data."
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
                                "securitySchemes": [
                                    {
                                        "type": "oauth2",
                                        "scopes": [
                                            "admin.read"
                                        ],
                                    }
                                ],
                            },
                            {
                                "name": "public.search",
                                "description": (
                                    "Search public docs."
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
                                "securitySchemes": [
                                    {
                                        "type": "noauth"
                                    },
                                    {
                                        "type": "oauth2",
                                        "scopes": [
                                            "search.read"
                                        ],
                                    },
                                ],
                            },
                        ]
                    },
                }
            )
            return

        self._json(
            {
                "jsonrpc": "2.0",
                "id": ident,
                "error": {
                    "code": -32601,
                    "message": "unknown",
                },
            }
        )


class _SecurityServer(
    ThreadingHTTPServer
):
    def __init__(
        self,
        address: tuple[str, int],
    ) -> None:
        super().__init__(
            address,
            _SecurityHandler,
        )
        self.state = {
            "scope_schemes": [
                {
                    "type": "oauth2",
                    "scopes": [
                        "docs.read"
                    ],
                }
            ]
        }


class _Fixture:
    def __enter__(
        self,
    ) -> "_Fixture":
        self.server = _SecurityServer(
            ("127.0.0.1", 0)
        )
        self.thread = threading.Thread(
            target=self.server.serve_forever,
            daemon=True,
        )
        self.thread.start()
        return self

    @property
    def url(self) -> str:
        host, port = (
            self.server.server_address
        )
        return (
            f"http://{host}:{port}/mcp"
        )

    def __exit__(
        self,
        exc_type,
        exc,
        tb,
    ) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(
            timeout=2
        )


def _make_plugin(
    root: Path,
    url: str,
) -> None:
    root.mkdir(
        parents=True,
        exist_ok=True,
    )
    (root / "mcp.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "auth": {
                        "type": (
                            "streamable-http"
                        ),
                        "url": url,
                        "http_headers": {
                            "Authorization": (
                                "Bearer admin-token"
                            )
                        },
                    }
                }
            }
        ),
        encoding="utf-8",
    )


def _matrix_report() -> dict:
    return {
        "schema_version": "0.1",
        "evidence_state": "executed",
        "matrix_id": "verified-matrix",
        "mode": "replay",
        "matrix_passed": True,
        "matrix_verified": True,
        "cases": [
            {
                "id": "viewer-read",
                "credential": "viewer",
                "tool": "scope.read",
                "observation": {
                    "outcome": "success"
                },
            },
            {
                "id": "editor-read",
                "credential": "editor",
                "tool": "scope.read",
                "observation": {
                    "outcome": "success"
                },
            },
            {
                "id": "missing-scope-denied",
                "credential": (
                    "missing-scope"
                ),
                "tool": "scope.read",
                "observation": {
                    "outcome": "http_error",
                    "http_status": 401,
                },
            },
            {
                "id": "admin-read",
                "credential": "admin",
                "tool": "admin.read",
                "observation": {
                    "outcome": "success"
                },
            },
            {
                "id": "viewer-admin-denied",
                "credential": "viewer",
                "tool": "admin.read",
                "observation": {
                    "outcome": "http_error",
                    "http_status": 403,
                },
            },
            {
                "id": "anon-public",
                "credential": "anonymous",
                "tool": "public.search",
                "observation": {
                    "outcome": "success"
                },
            },
            {
                "id": "viewer-public",
                "credential": "search-viewer",
                "tool": "public.search",
                "observation": {
                    "outcome": "success"
                },
            },
        ],
    }


def _write_matrix(
    root: Path,
) -> str:
    path = root / "matrix-replay.json"
    path.write_text(
        json.dumps(
            _matrix_report()
        ),
        encoding="utf-8",
    )
    return (
        path.relative_to(
            root
        ).as_posix()
    )


def _write_contract(
    root: Path,
    *,
    hidden_scope: bool = False,
    optional_auth: bool = False,
) -> str:
    missing_scopes = (
        ["docs.read"]
        if hidden_scope
        else []
    )
    tools = [
        {
            "tool": "scope.read",
            "access": "oauth_required",
            "sufficient_cases": [
                "viewer-read",
                "editor-read",
            ],
            "insufficient_scope_cases": [
                "missing-scope-denied"
            ],
        },
        {
            "tool": "admin.read",
            "access": "oauth_required",
            "sufficient_cases": [
                "admin-read"
            ],
            "insufficient_scope_cases": [
                "viewer-admin-denied"
            ],
        },
    ]
    if optional_auth:
        tools.append(
            {
                "tool": "public.search",
                "access": "optional_auth",
                "sufficient_cases": [
                    "anon-public",
                    "viewer-public",
                ],
                "insufficient_scope_cases": [],
            }
        )

    path = root / "security-contract.json"
    path.write_text(
        json.dumps(
            {
                "server": "auth",
                "profiles": {
                    "anonymous": {
                        "auth": "anonymous",
                        "scopes": [],
                    },
                    "viewer": {
                        "auth": "oauth",
                        "scopes": [
                            "docs.read"
                        ],
                    },
                    "editor": {
                        "auth": "oauth",
                        "scopes": [
                            "docs.read",
                            "docs.write",
                        ],
                    },
                    "admin": {
                        "auth": "oauth",
                        "scopes": [
                            "docs.read",
                            "admin.read",
                        ],
                    },
                    "missing-scope": {
                        "auth": "oauth",
                        "scopes": (
                            missing_scopes
                        ),
                    },
                    "search-viewer": {
                        "auth": "oauth",
                        "scopes": [
                            "search.read"
                        ],
                    },
                },
                "tools": tools,
            }
        ),
        encoding="utf-8",
    )
    return (
        path.relative_to(
            root
        ).as_posix()
    )


class SecuritySchemeGateTests(
    unittest.TestCase
):
    def test_valid_least_privilege_contract_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = (
                Path(tmp) / "plugin"
            )
            with _Fixture() as fixture:
                _make_plugin(
                    root,
                    fixture.url,
                )
                matrix = _write_matrix(
                    root
                )
                contract = _write_contract(
                    root
                )
                report = (
                    run_security_scheme_gate(
                        root,
                        contract=contract,
                        matrix_evidence=matrix,
                    )
                )

            self.assertTrue(
                report["gate_passed"]
            )
            self.assertEqual(
                report[
                    "blocking_reasons"
                ],
                [],
            )

    def test_overdeclared_scope_is_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = (
                Path(tmp) / "plugin"
            )
            with _Fixture() as fixture:
                fixture.server.state[
                    "scope_schemes"
                ] = [
                    {
                        "type": "oauth2",
                        "scopes": [
                            "docs.read",
                            "admin.read",
                        ],
                    }
                ]
                _make_plugin(
                    root,
                    fixture.url,
                )
                matrix = _write_matrix(
                    root
                )
                contract = _write_contract(
                    root
                )
                report = (
                    run_security_scheme_gate(
                        root,
                        contract=contract,
                        matrix_evidence=matrix,
                    )
                )

            self.assertFalse(
                report["gate_passed"]
            )
            self.assertTrue(
                any(
                    "declared_scope_not_supported_by_success"
                    in reason
                    for reason in report[
                        "blocking_reasons"
                    ]
                )
            )

    def test_hidden_runtime_scope_requirement_is_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = (
                Path(tmp) / "plugin"
            )
            with _Fixture() as fixture:
                _make_plugin(
                    root,
                    fixture.url,
                )
                matrix = _write_matrix(
                    root
                )
                contract = _write_contract(
                    root,
                    hidden_scope=True,
                )
                report = (
                    run_security_scheme_gate(
                        root,
                        contract=contract,
                        matrix_evidence=matrix,
                    )
                )

            self.assertFalse(
                report["gate_passed"]
            )
            self.assertTrue(
                any(
                    "runtime_requires_undeclared_permission"
                    in reason
                    for reason in report[
                        "blocking_reasons"
                    ]
                )
            )

    def test_noauth_scheme_conflicts_with_oauth_required_policy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = (
                Path(tmp) / "plugin"
            )
            with _Fixture() as fixture:
                fixture.server.state[
                    "scope_schemes"
                ] = [
                    {
                        "type": "noauth"
                    },
                    {
                        "type": "oauth2",
                        "scopes": [
                            "docs.read"
                        ],
                    },
                ]
                _make_plugin(
                    root,
                    fixture.url,
                )
                matrix = _write_matrix(
                    root
                )
                contract = _write_contract(
                    root
                )
                report = (
                    run_security_scheme_gate(
                        root,
                        contract=contract,
                        matrix_evidence=matrix,
                    )
                )

            self.assertFalse(
                report["gate_passed"]
            )
            self.assertIn(
                "scope.read:"
                "noauth_scheme_not_allowed",
                report[
                    "blocking_reasons"
                ],
            )

    def test_optional_auth_with_noauth_and_oauth_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = (
                Path(tmp) / "plugin"
            )
            with _Fixture() as fixture:
                _make_plugin(
                    root,
                    fixture.url,
                )
                matrix = _write_matrix(
                    root
                )
                contract = _write_contract(
                    root,
                    optional_auth=True,
                )
                report = (
                    run_security_scheme_gate(
                        root,
                        contract=contract,
                        matrix_evidence=matrix,
                    )
                )

            public = next(
                item
                for item in report[
                    "tools"
                ]
                if item["tool"]
                == "public.search"
            )
            self.assertTrue(
                public["passed"]
            )
            self.assertTrue(
                report["gate_passed"]
            )

    def test_unverified_matrix_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = (
                Path(tmp) / "plugin"
            )
            with _Fixture() as fixture:
                _make_plugin(
                    root,
                    fixture.url,
                )
                matrix = _matrix_report()
                matrix[
                    "matrix_verified"
                ] = False
                path = (
                    root
                    / "matrix-replay.json"
                )
                path.write_text(
                    json.dumps(matrix),
                    encoding="utf-8",
                )
                contract = _write_contract(
                    root
                )
                with self.assertRaisesRegex(
                    SecuritySchemeGateError,
                    "must be verified",
                ):
                    run_security_scheme_gate(
                        root,
                        contract=contract,
                        matrix_evidence=(
                            "matrix-replay.json"
                        ),
                    )

    def test_cli_writes_security_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = (
                Path(tmp) / "plugin"
            )
            with _Fixture() as fixture:
                _make_plugin(
                    root,
                    fixture.url,
                )
                matrix = _write_matrix(
                    root
                )
                contract = _write_contract(
                    root
                )
                proc = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "mado_plugin_factory",
                        "security-gate",
                        str(root),
                        "--contract",
                        contract,
                        "--matrix-evidence",
                        matrix,
                        "--write-evidence",
                    ],
                    text=True,
                    capture_output=True,
                    check=False,
                )

            self.assertEqual(
                proc.returncode,
                0,
                proc.stderr,
            )
            payload = json.loads(
                proc.stdout
            )
            self.assertTrue(
                payload["gate_passed"]
            )
            self.assertTrue(
                (
                    root
                    / payload[
                        "evidence_output"
                    ]
                ).is_file()
            )


if __name__ == "__main__":
    unittest.main()
