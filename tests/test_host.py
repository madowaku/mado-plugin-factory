from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from mado_plugin_factory.host import (
    HostReplayError,
    run_host_replay,
)


def _runtime_evidence(root: Path, *, name: str = "runtime.json") -> str:
    path = root / "evidence" / "runtime" / "extensions" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": "0.1",
                "evidence_state": "executed",
                "smoke_id": "smoke-123",
                "runtime_smoke_passed": True,
                "runtime_verified": False,
                "runtime_scope": "mcp_server",
                "host_required_extensions": [
                    "deep_links",
                    "model_app_context",
                    "rich_forms",
                ],
            }
        ),
        encoding="utf-8",
    )
    return path.relative_to(root).as_posix()


def _trace(
    path: Path,
    *,
    attested: bool = True,
    include_deep_link: bool = True,
    include_model_context: bool = True,
    include_rich_form: bool = True,
    rich_action: str = "accept",
) -> None:
    events = []
    if include_deep_link:
        events.append(
            {
                "direction": "host_to_app",
                "method": "ui/initialize",
                "call_id": 0,
                "result": {
                    "hostContext": {
                        "openai/deepLink": {
                            "url": "/parts?tag=bolt"
                        }
                    }
                },
            }
        )
    if include_model_context:
        events.extend(
            [
                {
                    "direction": "app_to_host",
                    "method": "ui/update-model-context",
                    "call_id": 10,
                    "params": {
                        "content": [
                            {
                                "type": "text",
                                "text": "PRIVATE-CONTEXT",
                            }
                        ]
                    },
                },
                {
                    "direction": "host_to_app",
                    "method": "ui/update-model-context",
                    "call_id": 10,
                    "result": {
                        "_meta": {
                            "openai/modelContext": {
                                "updateId": "private-update-id"
                            }
                        }
                    },
                },
            ]
        )
    if include_rich_form:
        events.extend(
            [
                {
                    "direction": "server_to_host",
                    "method": "openai/elicitation/create",
                    "call_id": "form-1",
                    "params": {
                        "mode": "form",
                        "message": "Choose a part",
                        "requestedSchema": {
                            "type": "object",
                            "properties": {
                                "secret_choice": {
                                    "type": "string"
                                }
                            },
                        },
                    },
                },
                {
                    "direction": "host_to_server",
                    "method": "openai/elicitation/create",
                    "call_id": "form-1",
                    "result": {
                        "action": rich_action,
                        "content": {
                            "secret_choice": "PRIVATE-FORM-VALUE"
                        },
                    },
                },
            ]
        )

    path.write_text(
        json.dumps(
            {
                "schema_version": "0.1",
                "capture": {
                    "product": "chatgpt",
                    "surface": "web",
                    "mode": "developer_mode",
                    "executed": True,
                    "attested_chatgpt_capture": attested,
                },
                "events": events,
            }
        ),
        encoding="utf-8",
    )


class ChatGPTHostReplayTests(unittest.TestCase):
    def test_full_attested_trace_verifies_host_required_extensions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime = _runtime_evidence(root)
            trace = root / "chatgpt-trace.json"
            _trace(trace)

            report = run_host_replay(
                root,
                trace,
                runtime_evidence=runtime,
            )

            self.assertTrue(report["capture_attested"])
            self.assertTrue(report["host_replay_passed"])
            self.assertTrue(report["end_to_end_verified"])
            self.assertEqual(
                report["accepted_extensions"],
                [
                    "deep_links",
                    "model_app_context",
                    "rich_forms",
                ],
            )
            self.assertEqual(report["missing_extensions"], [])

    def test_unattested_trace_never_becomes_end_to_end_verified(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime = _runtime_evidence(root)
            trace = root / "trace.json"
            _trace(trace, attested=False)

            report = run_host_replay(
                root,
                trace,
                runtime_evidence=runtime,
            )

            self.assertTrue(report["host_replay_passed"])
            self.assertFalse(report["capture_attested"])
            self.assertFalse(report["end_to_end_verified"])
            self.assertEqual(
                report["verification_scope"],
                "unattested_host_trace_replay",
            )

    def test_missing_host_event_remains_visible(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime = _runtime_evidence(root)
            trace = root / "trace.json"
            _trace(trace, include_model_context=False)

            report = run_host_replay(
                root,
                trace,
                runtime_evidence=runtime,
            )

            self.assertFalse(report["host_replay_passed"])
            self.assertFalse(report["end_to_end_verified"])
            self.assertEqual(
                report["missing_extensions"],
                ["model_app_context"],
            )

    def test_model_context_requires_correlated_response(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime = _runtime_evidence(root)
            trace = root / "trace.json"
            _trace(trace)
            payload = json.loads(trace.read_text(encoding="utf-8"))
            for event in payload["events"]:
                if (
                    event["direction"] == "host_to_app"
                    and event["method"] == "ui/update-model-context"
                ):
                    event["call_id"] = 999
            trace.write_text(json.dumps(payload), encoding="utf-8")

            report = run_host_replay(
                root,
                trace,
                runtime_evidence=runtime,
            )
            self.assertIn(
                "model_app_context",
                report["missing_extensions"],
            )

    def test_rich_form_decline_still_proves_host_form_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime = _runtime_evidence(root)
            trace = root / "trace.json"
            _trace(trace, rich_action="decline")

            report = run_host_replay(
                root,
                trace,
                runtime_evidence=runtime,
            )
            checks = {
                item["id"]: item
                for item in report["extension_checks"]
            }
            self.assertEqual(
                checks["rich_forms"]["state"],
                "accepted",
            )
            self.assertEqual(
                checks["rich_forms"]["evidence"][0]["action"],
                "decline",
            )

    def test_deep_link_fragment_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime = _runtime_evidence(root)
            trace = root / "trace.json"
            _trace(trace)
            payload = json.loads(trace.read_text(encoding="utf-8"))
            payload["events"][0]["result"]["hostContext"][
                "openai/deepLink"
            ]["url"] = "/parts#fragment"
            trace.write_text(json.dumps(payload), encoding="utf-8")

            report = run_host_replay(
                root,
                trace,
                runtime_evidence=runtime,
            )
            self.assertIn(
                "deep_links",
                report["missing_extensions"],
            )

    def test_written_evidence_does_not_copy_sensitive_trace_payloads(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime = _runtime_evidence(root)
            trace = root / "trace.json"
            _trace(trace)

            report = run_host_replay(
                root,
                trace,
                runtime_evidence=runtime,
                write_evidence=True,
            )
            evidence = root / report["evidence_output"]
            text = evidence.read_text(encoding="utf-8")
            self.assertNotIn("PRIVATE-CONTEXT", text)
            self.assertNotIn("PRIVATE-FORM-VALUE", text)
            self.assertNotIn("private-update-id", text)
            self.assertIn("trace_sha256", text)

            evidence.write_text("{}\n", encoding="utf-8")
            with self.assertRaises(HostReplayError):
                run_host_replay(
                    root,
                    trace,
                    runtime_evidence=runtime,
                    write_evidence=True,
                )
            run_host_replay(
                root,
                trace,
                runtime_evidence=runtime,
                write_evidence=True,
                force=True,
            )

    def test_runtime_evidence_auto_selection_requires_exactly_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _runtime_evidence(root, name="one.json")
            trace = root / "trace.json"
            _trace(trace)

            report = run_host_replay(root, trace)
            self.assertTrue(report["end_to_end_verified"])

            _runtime_evidence(root, name="two.json")
            with self.assertRaisesRegex(
                HostReplayError,
                "select runtime evidence",
            ):
                run_host_replay(root, trace)

    def test_runtime_evidence_must_be_executed_smoke(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime = _runtime_evidence(root)
            runtime_path = root / runtime
            payload = json.loads(runtime_path.read_text())
            payload["runtime_smoke_passed"] = False
            runtime_path.write_text(json.dumps(payload))
            trace = root / "trace.json"
            _trace(trace)

            with self.assertRaisesRegex(
                HostReplayError,
                "runtime_smoke_passed=true",
            ):
                run_host_replay(
                    root,
                    trace,
                    runtime_evidence=runtime,
                )

    def test_cli_replay_and_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime = _runtime_evidence(root)
            trace = root / "trace.json"
            _trace(trace)

            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "mado_plugin_factory",
                    "host-replay",
                    str(root),
                    "--trace",
                    str(trace),
                    "--runtime-evidence",
                    runtime,
                    "--write-evidence",
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            report = json.loads(proc.stdout)
            self.assertTrue(report["end_to_end_verified"])
            self.assertTrue(
                (root / report["evidence_output"]).is_file()
            )


if __name__ == "__main__":
    unittest.main()
