from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from mado_plugin_factory.credentials import (
    CredentialMatrixError,
    run_credential_matrix,
)


class _CredentialHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(
        self,
        format: str,
        *args: object,
    ) -> None:
        return

    def _json(
        self,
        status: int,
        payload: dict,
        *,
        challenge: str | None = None,
    ) -> None:
        raw = json.dumps(
            payload
        ).encode("utf-8")
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

    def _role(self) -> str | None:
        auth = self.headers.get(
            "Authorization"
        )
        mapping = {
            "Bearer admin-token": "admin",
            "Bearer editor-token": "editor",
            "Bearer viewer-token": "viewer",
            "Bearer expired-token": "expired",
            "Bearer wrong-aud-token": "wrong-aud",
            "Bearer missing-scope-token": "missing-scope",
        }
        return mapping.get(auth)

    def _challenge(self) -> str:
        return (
            'Bearer resource_metadata="'
            'https://private.example/.well-known/'
            'oauth-protected-resource", '
            'scope="docs.read"'
        )

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
        role = self._role()

        if method in {
            "server/discover",
            "tools/list",
        }:
            if role != "admin":
                self._json(
                    401,
                    {
                        "error": (
                            "PRIVATE DISCOVERY AUTH ERROR"
                        )
                    },
                    challenge=self._challenge(),
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
                            "tools": {},
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
                                "name": "scope.read",
                                "description": (
                                    "Read scoped fixture data."
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
                                            "docs.read"
                                        ],
                                    }
                                ],
                            },
                            {
                                "name": "admin.read",
                                "description": (
                                    "Read admin-only fixture data."
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
                                "name": "unsafe.write",
                                "description": (
                                    "Unsafe fixture tool."
                                ),
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {},
                                },
                                "annotations": {
                                    "readOnlyHint": False,
                                    "destructiveHint": True,
                                },
                            },
                        ]
                    },
                },
            )
            return

        if method != "tools/call":
            self._json(
                200,
                {
                    "jsonrpc": "2.0",
                    "id": ident,
                    "error": {
                        "code": -32601,
                        "message": "unknown",
                    },
                },
            )
            return

        params = msg.get(
            "params"
        ) or {}
        name = params.get("name")

        if name == "unsafe.write":
            self.server.state[
                "unsafe_called"
            ] = True
            self._json(
                200,
                {
                    "jsonrpc": "2.0",
                    "id": ident,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": "unsafe",
                            }
                        ]
                    },
                },
            )
            return

        if role in {
            None,
            "expired",
            "wrong-aud",
            "missing-scope",
        }:
            self._json(
                401,
                {
                    "error": (
                        "PRIVATE TOKEN FAILURE BODY"
                    )
                },
                challenge=self._challenge(),
            )
            return

        if (
            name == "scope.read"
            and role == "viewer"
            and not self.server.state[
                "viewer_scope_allowed"
            ]
        ):
            self._json(
                403,
                {
                    "error": (
                        "PRIVATE VIEWER POLICY BODY"
                    )
                },
            )
            return

        if name == "scope.read":
            self._json(
                200,
                {
                    "jsonrpc": "2.0",
                    "id": ident,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    "PRIVATE SCOPED DATA"
                                ),
                            }
                        ],
                        "structuredContent": {
                            "scope": "docs.read",
                            "role": role,
                        },
                        "isError": False,
                    },
                },
            )
            return

        if name == "admin.read":
            if role != "admin":
                self._json(
                    403,
                    {
                        "error": (
                            "PRIVATE ADMIN DENIAL"
                        )
                    },
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
                                "text": (
                                    "PRIVATE ADMIN DATA"
                                ),
                            }
                        ],
                        "structuredContent": {
                            "scope": "admin.read",
                            "role": "admin",
                        },
                        "isError": False,
                    },
                },
            )
            return

        self._json(
            200,
            {
                "jsonrpc": "2.0",
                "id": ident,
                "error": {
                    "code": -32601,
                    "message": "unknown",
                },
            },
        )


class _CredentialServer(ThreadingHTTPServer):
    def __init__(
        self,
        address: tuple[str, int],
    ) -> None:
        super().__init__(
            address,
            _CredentialHandler,
        )
        self.state = {
            "viewer_scope_allowed": True,
            "unsafe_called": False,
        }


class _HttpFixture:
    def __enter__(
        self,
    ) -> "_HttpFixture":
        self.server = _CredentialServer(
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
) -> str:
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
    contract = root / "matrix.json"
    contract.write_text(
        json.dumps(
            {
                "server": "auth",
                "credentials": {
                    "anonymous": {
                        "kind": "anonymous",
                    },
                    "viewer": {
                        "kind": (
                            "bearer_env"
                        ),
                        "env": (
                            "MPF_TEST_VIEWER_TOKEN"
                        ),
                    },
                    "editor": {
                        "kind": (
                            "bearer_env"
                        ),
                        "env": (
                            "MPF_TEST_EDITOR_TOKEN"
                        ),
                    },
                    "admin": {
                        "kind": (
                            "configured"
                        ),
                    },
                    "expired": {
                        "kind": (
                            "bearer_env"
                        ),
                        "env": (
                            "MPF_TEST_EXPIRED_TOKEN"
                        ),
                    },
                    "wrong-audience": {
                        "kind": (
                            "bearer_env"
                        ),
                        "env": (
                            "MPF_TEST_WRONG_AUD_TOKEN"
                        ),
                    },
                    "missing-scope": {
                        "kind": (
                            "bearer_env"
                        ),
                        "env": (
                            "MPF_TEST_MISSING_SCOPE_TOKEN"
                        ),
                    },
                },
                "cases": [
                    {
                        "id": "viewer-read",
                        "credential": "viewer",
                        "tool": "scope.read",
                        "arguments": {},
                        "expect": {
                            "outcome": "success",
                            "structured_content": "required",
                            "content_types": [
                                "text"
                            ],
                            "auth_challenge": "optional",
                        },
                        "stable_paths": [
                            "$.scope",
                            "$.role",
                        ],
                    },
                    {
                        "id": "editor-read",
                        "credential": "editor",
                        "tool": "scope.read",
                        "arguments": {},
                        "expect": {
                            "outcome": "success",
                            "structured_content": "required",
                            "content_types": [
                                "text"
                            ],
                        },
                        "stable_paths": [
                            "$.scope",
                            "$.role",
                        ],
                    },
                    {
                        "id": "admin-read",
                        "credential": "admin",
                        "tool": "admin.read",
                        "arguments": {},
                        "expect": {
                            "outcome": "success",
                            "structured_content": "required",
                            "content_types": [
                                "text"
                            ],
                        },
                        "stable_paths": [
                            "$.scope",
                            "$.role",
                        ],
                    },
                    {
                        "id": "viewer-admin-denied",
                        "credential": "viewer",
                        "tool": "admin.read",
                        "arguments": {},
                        "expect": {
                            "outcome": "http_error",
                            "http_status": 403,
                            "structured_content": "forbidden",
                            "content_types": [],
                        },
                    },
                    {
                        "id": "anonymous-denied",
                        "credential": "anonymous",
                        "tool": "scope.read",
                        "arguments": {},
                        "expect": {
                            "outcome": "http_error",
                            "http_status": 401,
                            "auth_challenge": "required",
                            "structured_content": "forbidden",
                            "content_types": [],
                        },
                    },
                    {
                        "id": "expired-denied",
                        "credential": "expired",
                        "tool": "scope.read",
                        "arguments": {},
                        "expect": {
                            "outcome": "http_error",
                            "http_status": 401,
                            "auth_challenge": "required",
                            "structured_content": "forbidden",
                            "content_types": [],
                        },
                    },
                    {
                        "id": "wrong-audience-denied",
                        "credential": (
                            "wrong-audience"
                        ),
                        "tool": "scope.read",
                        "arguments": {},
                        "expect": {
                            "outcome": "http_error",
                            "http_status": 401,
                            "auth_challenge": "required",
                            "structured_content": "forbidden",
                            "content_types": [],
                        },
                    },
                    {
                        "id": "missing-scope-denied",
                        "credential": (
                            "missing-scope"
                        ),
                        "tool": "scope.read",
                        "arguments": {},
                        "expect": {
                            "outcome": "http_error",
                            "http_status": 401,
                            "auth_challenge": "required",
                            "structured_content": "forbidden",
                            "content_types": [],
                        },
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    return (
        contract.relative_to(
            root
        ).as_posix()
    )


def _env() -> dict[str, str]:
    return {
        "MPF_TEST_VIEWER_TOKEN": (
            "viewer-token"
        ),
        "MPF_TEST_EDITOR_TOKEN": (
            "editor-token"
        ),
        "MPF_TEST_EXPIRED_TOKEN": (
            "expired-token"
        ),
        "MPF_TEST_WRONG_AUD_TOKEN": (
            "wrong-aud-token"
        ),
        "MPF_TEST_MISSING_SCOPE_TOKEN": (
            "missing-scope-token"
        ),
    }


def _verification(
    root: Path,
    name: str = "verification.json",
) -> str:
    path = root / name
    path.write_text(
        json.dumps(
            {
                "evidence_state": (
                    "executed"
                ),
                "verification_verified": (
                    True
                ),
                "verification_id": (
                    "matrix-verification"
                ),
            }
        ),
        encoding="utf-8",
    )
    return (
        path.relative_to(
            root
        ).as_posix()
    )


class CredentialMatrixTests(
    unittest.TestCase
):
    def test_record_then_replay_full_scope_matrix(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = (
                Path(tmp) / "plugin"
            )
            with _HttpFixture() as fixture:
                contract = _make_plugin(
                    root,
                    fixture.url,
                )
                with patch.dict(
                    os.environ,
                    _env(),
                    clear=False,
                ):
                    baseline = run_credential_matrix(
                        root,
                        contract=contract,
                        write_evidence=True,
                    )
                    self.assertTrue(
                        baseline[
                            "matrix_passed"
                        ]
                    )
                    self.assertFalse(
                        baseline[
                            "matrix_verified"
                        ]
                    )

                    replay = run_credential_matrix(
                        root,
                        contract=contract,
                        baseline_evidence=baseline[
                            "evidence_output"
                        ],
                    )

            self.assertTrue(
                replay[
                    "matrix_verified"
                ]
            )
            self.assertEqual(
                replay[
                    "blocking_reasons"
                ],
                [],
            )

    def test_scope_boundary_drift_is_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = (
                Path(tmp) / "plugin"
            )
            with _HttpFixture() as fixture:
                contract = _make_plugin(
                    root,
                    fixture.url,
                )
                with patch.dict(
                    os.environ,
                    _env(),
                    clear=False,
                ):
                    baseline = run_credential_matrix(
                        root,
                        contract=contract,
                        write_evidence=True,
                    )
                    fixture.server.state[
                        "viewer_scope_allowed"
                    ] = False
                    replay = run_credential_matrix(
                        root,
                        contract=contract,
                        baseline_evidence=baseline[
                            "evidence_output"
                        ],
                    )

            self.assertFalse(
                replay[
                    "matrix_verified"
                ]
            )
            self.assertTrue(
                any(
                    (
                        "viewer-read:"
                        "unexpected_outcome"
                    )
                    in reason
                    or (
                        "viewer-read:"
                        "credential_boundary_drift"
                    )
                    in reason
                    for reason in replay[
                        "blocking_reasons"
                    ]
                )
            )

    def test_evidence_does_not_persist_env_names_or_tokens(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = (
                Path(tmp) / "plugin"
            )
            with _HttpFixture() as fixture:
                contract = _make_plugin(
                    root,
                    fixture.url,
                )
                with patch.dict(
                    os.environ,
                    _env(),
                    clear=False,
                ):
                    report = run_credential_matrix(
                        root,
                        contract=contract,
                        write_evidence=True,
                    )

            text = (
                root
                / report[
                    "evidence_output"
                ]
            ).read_text(
                encoding="utf-8"
            )
            for secret in [
                "viewer-token",
                "editor-token",
                "expired-token",
                "wrong-aud-token",
                "missing-scope-token",
                "MPF_TEST_VIEWER_TOKEN",
                "MPF_TEST_EDITOR_TOKEN",
                "MPF_TEST_EXPIRED_TOKEN",
                "MPF_TEST_WRONG_AUD_TOKEN",
                "MPF_TEST_MISSING_SCOPE_TOKEN",
                "PRIVATE SCOPED DATA",
                "private.example",
            ]:
                self.assertNotIn(
                    secret,
                    text,
                )

    def test_contract_rejects_raw_secret_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = (
                Path(tmp) / "plugin"
            )
            root.mkdir()
            path = root / "bad.json"
            path.write_text(
                json.dumps(
                    {
                        "credentials": {
                            "viewer": {
                                "kind": (
                                    "bearer_env"
                                ),
                                "env": "TOKEN_ENV",
                                "token": "raw-secret",
                            }
                        },
                        "cases": [
                            {
                                "id": "x",
                                "credential": "viewer",
                                "tool": "scope.read",
                                "expect": {
                                    "outcome": "success"
                                },
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                CredentialMatrixError,
                "unsupported fields",
            ):
                run_credential_matrix(
                    root,
                    contract="bad.json",
                )

    def test_verification_binding_is_enforced(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = (
                Path(tmp) / "plugin"
            )
            with _HttpFixture() as fixture:
                contract = _make_plugin(
                    root,
                    fixture.url,
                )
                one = _verification(
                    root,
                    "one.json",
                )
                two_path = (
                    root / "two.json"
                )
                two_path.write_text(
                    json.dumps(
                        {
                            "evidence_state": (
                                "executed"
                            ),
                            "verification_verified": (
                                True
                            ),
                            "verification_id": (
                                "other-verification"
                            ),
                        }
                    ),
                    encoding="utf-8",
                )
                two = (
                    two_path.relative_to(
                        root
                    ).as_posix()
                )
                with patch.dict(
                    os.environ,
                    _env(),
                    clear=False,
                ):
                    baseline = run_credential_matrix(
                        root,
                        contract=contract,
                        verification_evidence=one,
                        write_evidence=True,
                    )
                    with self.assertRaisesRegex(
                        CredentialMatrixError,
                        "not bound",
                    ):
                        run_credential_matrix(
                            root,
                            contract=contract,
                            baseline_evidence=baseline[
                                "evidence_output"
                            ],
                            verification_evidence=two,
                        )

    def test_non_read_only_tool_is_never_called(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = (
                Path(tmp) / "plugin"
            )
            with _HttpFixture() as fixture:
                _make_plugin(
                    root,
                    fixture.url,
                )
                unsafe = (
                    root / "unsafe.json"
                )
                unsafe.write_text(
                    json.dumps(
                        {
                            "server": "auth",
                            "credentials": {
                                "admin": {
                                    "kind": "configured"
                                }
                            },
                            "cases": [
                                {
                                    "id": "unsafe",
                                    "credential": "admin",
                                    "tool": "unsafe.write",
                                    "arguments": {},
                                    "expect": {
                                        "outcome": "success",
                                        "content_types": [],
                                    },
                                }
                            ],
                        }
                    ),
                    encoding="utf-8",
                )
                report = run_credential_matrix(
                    root,
                    contract="unsafe.json",
                )

                self.assertFalse(
                    report[
                        "matrix_passed"
                    ]
                )
                self.assertFalse(
                    fixture.server.state[
                        "unsafe_called"
                    ]
                )

    def test_cli_record_and_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = (
                Path(tmp) / "plugin"
            )
            with _HttpFixture() as fixture:
                contract = _make_plugin(
                    root,
                    fixture.url,
                )
                env = os.environ.copy()
                env.update(_env())
                record = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "mado_plugin_factory",
                        "credential-matrix",
                        str(root),
                        "--contract",
                        contract,
                        "--write-evidence",
                    ],
                    text=True,
                    capture_output=True,
                    check=False,
                    env=env,
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
                        "credential-matrix",
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
                    env=env,
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
                payload[
                    "matrix_verified"
                ]
            )


if __name__ == "__main__":
    unittest.main()
