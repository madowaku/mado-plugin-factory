from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from mado_plugin_factory.capture import (
    HostCaptureError,
    normalize_host_capture,
    public_capture_report,
    write_host_capture,
)


def _normalized_source(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "capture": {
                    "product": "chatgpt",
                    "surface": "web",
                    "mode": "developer_mode",
                    "executed": True,
                    "attested_chatgpt_capture": True,
                },
                "events": [
                    {
                        "direction": "host_to_app",
                        "method": "ui/initialize",
                        "call_id": 99,
                        "result": {
                            "hostContext": {
                                "openai/deepLink": {
                                    "url": "/private/project?id=123"
                                }
                            }
                        },
                    },
                    {
                        "direction": "app_to_host",
                        "method": "ui/update-model-context",
                        "call_id": "secret-call",
                        "params": {
                            "content": [
                                {
                                    "type": "text",
                                    "text": "PRIVATE MODEL CONTEXT",
                                }
                            ],
                            "structuredContent": {
                                "customer": "PRIVATE CUSTOMER"
                            },
                        },
                    },
                    {
                        "direction": "host_to_app",
                        "method": "ui/update-model-context",
                        "call_id": "secret-call",
                        "result": {
                            "_meta": {
                                "openai/modelContext": {
                                    "updateId": "PRIVATE UPDATE ID"
                                }
                            }
                        },
                    },
                    {
                        "direction": "server_to_host",
                        "method": "openai/elicitation/create",
                        "call_id": "secret-form",
                        "params": {
                            "mode": "form",
                            "message": "PRIVATE FORM PROMPT",
                            "requestedSchema": {
                                "type": "object",
                                "properties": {
                                    "secret": {"type": "string"}
                                },
                            },
                        },
                    },
                    {
                        "direction": "host_to_server",
                        "method": "openai/elicitation/create",
                        "call_id": "secret-form",
                        "result": {
                            "action": "accept",
                            "content": {
                                "secret": "PRIVATE FORM VALUE"
                            },
                        },
                    },
                ],
            }
        ),
        encoding="utf-8",
    )


class HostCaptureNormalizerTests(unittest.TestCase):
    def test_normalized_input_is_redacted_and_call_ids_are_canonical(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "raw.json"
            _normalized_source(source)

            report = normalize_host_capture(
                root,
                source,
                source_format="normalized",
                surface="web",
                mode="developer_mode",
                executed=True,
                attest_chatgpt_capture=True,
            )
            trace = report["_trace"]
            rendered = json.dumps(trace)

            self.assertTrue(report["capture_attested"])
            self.assertTrue(report["normalization_ready"])
            self.assertNotIn("PRIVATE MODEL CONTEXT", rendered)
            self.assertNotIn("PRIVATE CUSTOMER", rendered)
            self.assertNotIn("PRIVATE UPDATE ID", rendered)
            self.assertNotIn("PRIVATE FORM PROMPT", rendered)
            self.assertNotIn("PRIVATE FORM VALUE", rendered)
            self.assertNotIn("/private/project", rendered)
            self.assertIn("/__mpf_redacted__?sha256=", rendered)

            ids = [
                event["call_id"]
                for event in trace["events"]
                if event["call_id"] is not None
            ]
            self.assertIn("call-1", ids)
            self.assertEqual(
                trace["events"][1]["call_id"],
                trace["events"][2]["call_id"],
            )
            self.assertEqual(
                trace["events"][3]["call_id"],
                trace["events"][4]["call_id"],
            )
            redactions = report["normalization"]["redactions"]
            self.assertEqual(redactions["deep_link_urls"], 1)
            self.assertEqual(redactions["form_content"], 1)

    def test_request_response_pairs_are_normalized(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "pairs.json"
            source.write_text(
                json.dumps(
                    {
                        "records": [
                            {
                                "request": {
                                    "jsonrpc": "2.0",
                                    "id": 1,
                                    "method": "ui/initialize",
                                    "params": {},
                                },
                                "response": {
                                    "jsonrpc": "2.0",
                                    "id": 1,
                                    "result": {
                                        "hostContext": {
                                            "openai/deepLink": {
                                                "url": "/parts/one"
                                            }
                                        }
                                    },
                                },
                            },
                            {
                                "request": json.dumps(
                                    {
                                        "jsonrpc": "2.0",
                                        "id": 2,
                                        "method": "openai/elicitation/create",
                                        "params": {
                                            "mode": "form",
                                            "message": "secret",
                                            "requestedSchema": {
                                                "type": "object",
                                                "properties": {},
                                            },
                                        },
                                    }
                                ),
                                "response": json.dumps(
                                    {
                                        "jsonrpc": "2.0",
                                        "id": 2,
                                        "result": {
                                            "action": "decline",
                                            "content": {},
                                        },
                                    }
                                ),
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )

            report = normalize_host_capture(
                root,
                source,
                surface="api_playground",
                mode="api_playground",
                executed=True,
                attest_chatgpt_capture=True,
            )
            events = report["_trace"]["events"]

            self.assertEqual(report["source"]["adapter"], "json")
            self.assertEqual(len(events), 4)
            initialize_response = [
                item
                for item in events
                if item["method"] == "ui/initialize"
                and item["direction"] == "host_to_app"
            ]
            self.assertEqual(len(initialize_response), 1)
            form_response = [
                item
                for item in events
                if item["method"] == "openai/elicitation/create"
                and item["direction"] == "host_to_server"
            ]
            self.assertEqual(
                form_response[0]["result"]["action"],
                "decline",
            )

    def test_jsonl_pairs_responses_with_prior_requests(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "playground.jsonl"
            source.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "jsonrpc": "2.0",
                                "id": "a",
                                "method": "ui/update-model-context",
                                "params": {
                                    "content": [
                                        {
                                            "type": "text",
                                            "text": "secret",
                                        }
                                    ]
                                },
                            }
                        ),
                        json.dumps(
                            {
                                "jsonrpc": "2.0",
                                "id": "a",
                                "result": {
                                    "_meta": {
                                        "openai/modelContext": {
                                            "updateId": "u-1"
                                        }
                                    }
                                },
                            }
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            report = normalize_host_capture(
                root,
                source,
                surface="api_playground",
                mode="api_playground",
                executed=True,
            )
            events = report["_trace"]["events"]
            self.assertEqual(report["source"]["adapter"], "jsonl")
            self.assertEqual(len(events), 2)
            self.assertEqual(
                events[0]["direction"],
                "app_to_host",
            )
            self.assertEqual(
                events[1]["direction"],
                "host_to_app",
            )
            self.assertEqual(
                events[0]["call_id"],
                events[1]["call_id"],
            )

    def test_direct_host_context_notification_is_supported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "notification.json"
            source.write_text(
                json.dumps(
                    [
                        {
                            "direction": "host_to_app",
                            "method": "ui/notifications/host-context-changed",
                            "params": {
                                "openai/deepLink": {
                                    "url": "/private/path"
                                }
                            },
                        }
                    ]
                ),
                encoding="utf-8",
            )
            report = normalize_host_capture(
                root,
                source,
                surface="desktop",
                mode="installed_plugin",
                executed=True,
            )
            event = report["_trace"]["events"][0]
            self.assertEqual(
                event["direction"],
                "host_to_app",
            )
            self.assertTrue(
                event["params"]["openai/deepLink"]["url"].startswith(
                    "/__mpf_redacted__?sha256="
                )
            )

    def test_attestation_requires_executed_capture(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "raw.json"
            _normalized_source(source)
            with self.assertRaisesRegex(
                HostCaptureError,
                "attestation requires",
            ):
                normalize_host_capture(
                    root,
                    source,
                    surface="web",
                    mode="developer_mode",
                    executed=False,
                    attest_chatgpt_capture=True,
                )

    def test_irrelevant_input_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "irrelevant.json"
            source.write_text(
                json.dumps(
                    [
                        {
                            "jsonrpc": "2.0",
                            "id": 1,
                            "method": "tools/list",
                            "params": {},
                        }
                    ]
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                HostCaptureError,
                "no host-replay-relevant",
            ):
                normalize_host_capture(
                    root,
                    source,
                    surface="web",
                    mode="developer_mode",
                )

    def test_write_is_private_idempotent_and_force_guarded(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "raw.json"
            _normalized_source(source)
            report = normalize_host_capture(
                root,
                source,
                surface="web",
                mode="developer_mode",
                executed=True,
                attest_chatgpt_capture=True,
            )

            first = write_host_capture(root, report)
            second = write_host_capture(root, report)
            self.assertEqual(
                sorted(first),
                sorted(second),
            )

            trace_path = root / report["artifacts"]["trace"]
            capture_path = root / report["artifacts"]["report"]
            trace_text = trace_path.read_text(encoding="utf-8")
            capture_text = capture_path.read_text(encoding="utf-8")
            self.assertNotIn("PRIVATE MODEL CONTEXT", trace_text)
            self.assertNotIn("PRIVATE FORM VALUE", trace_text)
            self.assertNotIn("PRIVATE MODEL CONTEXT", capture_text)
            self.assertNotIn("_trace", capture_text)

            capture_path.write_text("{}\n", encoding="utf-8")
            with self.assertRaises(HostCaptureError):
                write_host_capture(root, report)
            write_host_capture(root, report, force=True)

            with self.assertRaises(HostCaptureError):
                normalize_host_capture(
                    root,
                    source,
                    surface="web",
                    mode="developer_mode",
                    output_dir="../escape",
                )

    def test_public_report_hides_normalized_trace(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "raw.json"
            _normalized_source(source)
            report = normalize_host_capture(
                root,
                source,
                surface="web",
                mode="developer_mode",
            )
            public = public_capture_report(report)
            self.assertNotIn("_trace", public)
            self.assertTrue(public["normalization_ready"])

    def test_cli_normalizes_and_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "raw.json"
            _normalized_source(source)

            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "mado_plugin_factory",
                    "host-capture",
                    str(root),
                    "--input",
                    str(source),
                    "--surface",
                    "web",
                    "--mode",
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
            self.assertTrue(report["capture_attested"])
            self.assertTrue(
                (root / report["artifacts"]["trace"]).is_file()
            )


if __name__ == "__main__":
    unittest.main()
