from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from mado_plugin_factory.behavior import run_behavior_canary
from mado_plugin_factory.evals import (
    compile_submission_evals,
    write_submission_evals,
)
from mado_plugin_factory.orchestrator import (
    run_extension_verification,
    write_verification_dossier,
)
from mado_plugin_factory.promotion import (
    PromotionError,
    compile_verification_promotion,
    run_verification_promotion,
    public_promotion_report,
    write_promoted_release,
)


SERVER = r'''
import json
import sys

BEHAVIOR = "v1"

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
                        "name": "promotion-fixture",
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
                        "name": "canary.read",
                        "description": "Read deterministic promotion canary.",
                        "inputSchema": {"type": "object", "properties": {}},
                        "outputSchema": {
                            "type": "object",
                            "properties": {"status": {"type": "string"}}
                        },
                        "annotations": {
                            "readOnlyHint": True,
                            "openWorldHint": False,
                            "destructiveHint": False
                        }
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
    elif method == "tools/call":
        params = msg.get("params") or {}
        if params.get("name") == "canary.read":
            send({
                "jsonrpc": "2.0",
                "id": ident,
                "result": {
                    "content": [{"type": "text", "text": "canary"}],
                    "structuredContent": {"status": BEHAVIOR},
                    "isError": False
                }
            })
        else:
            send({
                "jsonrpc": "2.0",
                "id": ident,
                "error": {"code": -32601, "message": "Method not found"}
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


def _make_plugin(
    root: Path,
    *,
    with_mcp: bool = True,
    host_required: bool = True,
) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "plugin.json").write_text(
        json.dumps(
            {
                "$schema": "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",
                "name": "promotion-demo",
                "version": "1.3.0",
                "description": "Promotion bridge fixture.",
                "extensions": {
                    "com.openai": {
                        "interface": {
                            "displayName": "Promotion Demo",
                            "shortDescription": "Promotion fixture",
                            "longDescription": "Promotion bridge fixture.",
                            "category": "Developer Tools",
                            "defaultPrompt": [
                                "Inspect the promotion fixture."
                            ]
                        }
                    }
                }
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    skill = root / "skills" / "promotion"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\nname: promotion\ndescription: Promotion fixture.\n---\n\n"
        "Use the fixture.\n",
        encoding="utf-8",
    )
    if with_mcp:
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
            )
            + "\n",
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
        (active / "runtime.ts").write_text(
            source,
            encoding="utf-8",
        )


def _make_release_evidence(root: Path) -> None:
    eval_report = compile_submission_evals(
        root,
        metadata={
            "default_fixture": "Fixture: tests/fixtures/promotion.json"
        },
    )
    write_submission_evals(root, eval_report)
    install = root / "evidence" / "marketplace"
    install.mkdir(parents=True, exist_ok=True)
    (install / "install-verification.json").write_text(
        json.dumps(
            {
                "schema_version": "0.4",
                "mode": "verify",
                "evidence_state": "executed",
                "install_verified": True,
                "blocking_reasons": [],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _release_metadata() -> dict:
    return {
        "availability": ["JP", "US"],
        "release_notes": "Promote verified extension build.",
        "listing": {
            "website_url": "https://example.com",
            "support_url": "https://example.com/support",
            "privacy_policy_url": "https://example.com/privacy",
            "terms_url": "https://example.com/terms",
            "logo_ready": True,
        },
        "review": {
            "eval_cases_reviewed": True,
            "skills_final_tree_tested": True,
            "listing_reviewed": True,
        },
        "portal": {
            "apps_management_write_access": True,
            "developer_identity_verified": True,
            "policy_attestations_complete": True,
            "skill_safety_scan_passed": True,
        },
        "mcp": {
            "production_url": "https://mcp.example.com/mcp",
            "demo_recording_url": "https://example.com/demo",
            "domain_verified": True,
            "tool_scan_current": True,
            "tool_annotations_reviewed": True,
            "reviewer_credentials_ready": True,
        },
        "policy_attestation_note": "Review material verified.",
    }


def _capture(path: Path, *, attested: bool = True) -> None:
    path.write_text(
        json.dumps(
            {
                "capture": {
                    "product": "chatgpt",
                    "surface": "web",
                    "mode": "developer_mode",
                    "executed": True,
                    "attested_chatgpt_capture": attested,
                },
                "events": [
                    {
                        "direction": "host_to_app",
                        "method": "ui/initialize",
                        "call_id": 1,
                        "result": {
                            "hostContext": {
                                "openai/deepLink": {
                                    "url": "/parts/private?id=1"
                                }
                            }
                        },
                    },
                    {
                        "direction": "app_to_host",
                        "method": "ui/update-model-context",
                        "call_id": 2,
                        "params": {
                            "content": [
                                {
                                    "type": "text",
                                    "text": "PRIVATE CONTEXT",
                                }
                            ]
                        },
                    },
                    {
                        "direction": "host_to_app",
                        "method": "ui/update-model-context",
                        "call_id": 2,
                        "result": {
                            "_meta": {
                                "openai/modelContext": {
                                    "updateId": "PRIVATE UPDATE"
                                }
                            }
                        },
                    },
                    {
                        "direction": "server_to_host",
                        "method": "openai/elicitation/create",
                        "call_id": 3,
                        "params": {
                            "mode": "form",
                            "message": "PRIVATE FORM",
                            "requestedSchema": {
                                "type": "object",
                                "properties": {
                                    "value": {"type": "string"}
                                },
                            },
                        },
                    },
                    {
                        "direction": "host_to_server",
                        "method": "openai/elicitation/create",
                        "call_id": 3,
                        "result": {
                            "action": "accept",
                            "content": {
                                "value": "PRIVATE VALUE"
                            },
                        },
                    },
                ],
            }
        ),
        encoding="utf-8",
    )



def _canary_baseline(root: Path) -> tuple[str, str]:
    contract = root / "canary-contract.json"
    contract.write_text(
        json.dumps(
            {
                "server": "fixture",
                "cases": [
                    {
                        "id": "promotion-canary",
                        "tool": "canary.read",
                        "arguments": {},
                        "expect": {
                            "outcome": "success",
                            "structured_content": "required",
                            "content_types": ["text"]
                        },
                        "stable_paths": ["$.status"]
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    report = run_behavior_canary(
        root,
        contract="canary-contract.json",
        write_evidence=True,
    )
    if not report["canary_passed"]:
        raise AssertionError(report)
    return "canary-contract.json", report["evidence_output"]



def _verification(
    root: Path,
    *,
    host_required: bool,
    attested: bool = True,
) -> str:
    capture = None
    if host_required:
        capture = root / "host-capture.json"
        _capture(capture, attested=attested)

    report = run_extension_verification(
        root,
        capture_input=capture,
        surface="web" if capture else None,
        capture_mode="developer_mode" if capture else None,
        executed=bool(capture),
        attest_chatgpt_capture=bool(
            capture and attested
        ),
    )
    write_verification_dossier(root, report)
    return report["artifacts"]["dossier"]


class VerificationPromotionGateTests(unittest.TestCase):
    def test_auto_requires_host_when_host_extensions_exist(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "plugin"
            _make_plugin(root, host_required=True)
            _make_release_evidence(root)
            dossier = _verification(
                root,
                host_required=True,
            )

            report = compile_verification_promotion(
                root,
                release_metadata=_release_metadata(),
                verification_evidence=dossier,
            )

            self.assertEqual(
                report["requirement"]["resolved"],
                "chatgpt_host",
            )
            self.assertTrue(
                report["verification"]["passed"]
            )
            self.assertTrue(report["promotion_ready"])
            self.assertTrue(
                report["release"]["submission_ready"]
            )

    def test_runtime_only_verification_promotes_at_server_scope(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "plugin"
            _make_plugin(root, host_required=False)
            _make_release_evidence(root)
            dossier = _verification(
                root,
                host_required=False,
            )

            report = compile_verification_promotion(
                root,
                release_metadata=_release_metadata(),
                verification_evidence=dossier,
            )

            self.assertEqual(
                report["requirement"]["resolved"],
                "mcp_server",
            )
            self.assertTrue(report["promotion_ready"])

    def test_package_drift_blocks_old_verification(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "plugin"
            _make_plugin(root, host_required=False)
            _make_release_evidence(root)
            dossier = _verification(
                root,
                host_required=False,
            )

            skill = root / "skills" / "promotion" / "SKILL.md"
            skill.write_text(
                skill.read_text(encoding="utf-8")
                + "\nChanged after verification.\n",
                encoding="utf-8",
            )

            report = compile_verification_promotion(
                root,
                release_metadata=_release_metadata(),
                verification_evidence=dossier,
            )
            self.assertFalse(report["promotion_ready"])
            self.assertFalse(
                report["verification"][
                    "package_digest_matches"
                ]
            )
            self.assertIn(
                "verification_package_digest_mismatch",
                report["blocking_reasons"],
            )

    def test_unverified_host_capture_cannot_promote(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "plugin"
            _make_plugin(root, host_required=True)
            _make_release_evidence(root)
            dossier = _verification(
                root,
                host_required=True,
                attested=False,
            )

            report = compile_verification_promotion(
                root,
                release_metadata=_release_metadata(),
                verification_evidence=dossier,
            )

            self.assertFalse(report["promotion_ready"])
            self.assertEqual(
                report["requirement"]["resolved"],
                "chatgpt_host",
            )
            self.assertIn(
                "verification_not_verified",
                report["blocking_reasons"],
            )

    def test_tampered_stage_artifact_blocks_promotion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "plugin"
            _make_plugin(root, host_required=False)
            _make_release_evidence(root)
            dossier = _verification(
                root,
                host_required=False,
            )
            dossier_payload = json.loads(
                (root / dossier).read_text(encoding="utf-8")
            )
            runtime_path = (
                root
                / dossier_payload["artifacts"]["runtime"]
            )
            runtime_path.write_text(
                json.dumps({"tampered": True}),
                encoding="utf-8",
            )

            report = compile_verification_promotion(
                root,
                release_metadata=_release_metadata(),
                verification_evidence=dossier,
            )

            self.assertFalse(report["promotion_ready"])
            self.assertIn(
                "verification_runtime_digest_mismatch",
                report["blocking_reasons"],
            )

    def test_old_dossier_without_package_digest_is_not_promotable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "plugin"
            _make_plugin(root, host_required=False)
            _make_release_evidence(root)
            dossier = _verification(
                root,
                host_required=False,
            )
            path = root / dossier
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["source"].pop(
                "plugin_package_digest",
                None,
            )
            path.write_text(
                json.dumps(payload, indent=2) + "\n",
                encoding="utf-8",
            )

            report = compile_verification_promotion(
                root,
                release_metadata=_release_metadata(),
                verification_evidence=dossier,
            )

            self.assertFalse(report["promotion_ready"])
            self.assertIn(
                "verification_package_digest_missing",
                report["blocking_reasons"],
            )

    def test_write_promoted_release_bridges_verification_outside_zip(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "plugin"
            _make_plugin(root, host_required=True)
            _make_release_evidence(root)
            dossier = _verification(
                root,
                host_required=True,
            )

            report = compile_verification_promotion(
                root,
                release_metadata=_release_metadata(),
                verification_evidence=dossier,
            )
            result = write_promoted_release(
                root,
                report,
            )
            release = Path(result["bundle_root"])

            self.assertTrue(
                (release / "promotion.json").is_file()
            )
            self.assertTrue(
                (
                    release
                    / "verification"
                    / "dossier.json"
                ).is_file()
            )
            self.assertTrue(
                (
                    release
                    / "verification"
                    / "runtime.json"
                ).is_file()
            )
            self.assertTrue(
                (
                    release
                    / "verification"
                    / "host.json"
                ).is_file()
            )

            with zipfile.ZipFile(
                release / "plugin.zip",
                "r",
            ) as archive:
                names = set(archive.namelist())
            self.assertFalse(
                any(
                    name.startswith("evidence/")
                    for name in names
                )
            )
            self.assertNotIn(
                "promotion.json",
                names,
            )

            second = write_promoted_release(
                root,
                report,
            )
            self.assertEqual(
                second["promotion_written"],
                [],
            )

    def test_skills_only_plugin_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "plugin"
            _make_plugin(
                root,
                with_mcp=False,
                host_required=False,
            )
            _make_release_evidence(root)
            fake = (
                root
                / "evidence"
                / "verifications"
                / "extensions"
                / "fake"
            )
            fake.mkdir(parents=True)
            (fake / "dossier.json").write_text(
                json.dumps(
                    {
                        "evidence_state": "executed",
                        "verification_id": "fake",
                        "verification_state": "verified_mcp_server",
                        "verification_verified": True,
                        "source": {
                            "plugin_package_digest": "fake"
                        },
                        "stages": {},
                        "summary": {
                            "host_required_extensions": []
                        },
                        "artifacts": {},
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                PromotionError,
                "requires a plugin with MCP",
            ):
                compile_verification_promotion(
                    root,
                    release_metadata={
                        **_release_metadata(),
                        "mcp": {},
                    },
                    verification_evidence=(
                        "evidence/verifications/extensions/fake/dossier.json"
                    ),
                )

    def test_public_report_hides_verification_payloads(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "plugin"
            _make_plugin(root, host_required=False)
            _make_release_evidence(root)
            dossier = _verification(
                root,
                host_required=False,
            )
            report = compile_verification_promotion(
                root,
                release_metadata=_release_metadata(),
                verification_evidence=dossier,
            )
            public = public_promotion_report(report)
            self.assertNotIn(
                "_verification_dossier",
                public,
            )
            self.assertNotIn(
                "_verification_artifacts",
                public,
            )

    def test_live_promotion_blocks_remote_mcp_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "plugin"
            _make_plugin(root, host_required=False)
            _make_release_evidence(root)
            dossier = _verification(
                root,
                host_required=False,
            )

            server = root / "server.py"
            server.write_text(
                server.read_text(encoding="utf-8").replace(
                    '"name": "app.open",',
                    '"name": "app.open.changed",',
                ),
                encoding="utf-8",
            )

            report = run_verification_promotion(
                root,
                release_metadata=_release_metadata(),
                verification_evidence=dossier,
            )
            self.assertFalse(report["promotion_ready"])
            self.assertIn(
                "verification_freshness_stale",
                report["blocking_reasons"],
            )

    def test_behavior_drift_blocks_live_promotion_after_freshness_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "plugin"
            _make_plugin(root, host_required=False)
            _make_release_evidence(root)
            dossier = _verification(
                root,
                host_required=False,
            )
            contract, baseline = _canary_baseline(root)

            server = root / "server.py"
            server.write_text(
                server.read_text(encoding="utf-8").replace(
                    'BEHAVIOR = "v1"',
                    'BEHAVIOR = "v2"',
                ),
                encoding="utf-8",
            )

            report = run_verification_promotion(
                root,
                release_metadata=_release_metadata(),
                verification_evidence=dossier,
                canary_contract=contract,
                canary_baseline=baseline,
            )

            self.assertFalse(report["promotion_ready"])
            self.assertTrue(
                report["verification"]["freshness"][
                    "freshness_verified"
                ]
            )
            self.assertFalse(
                report["verification"]["behavior_canary"][
                    "canary_verified"
                ]
            )
            self.assertIn(
                "verification_behavior_canary_stale",
                report["blocking_reasons"],
            )

    def test_cli_promotes_verified_release(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "plugin"
            _make_plugin(root, host_required=False)
            _make_release_evidence(root)
            dossier = _verification(
                root,
                host_required=False,
            )
            metadata = root / "release.json"
            metadata.write_text(
                json.dumps(_release_metadata()),
                encoding="utf-8",
            )

            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "mado_plugin_factory",
                    "promote",
                    str(root),
                    "--release-metadata",
                    str(metadata),
                    "--verification-evidence",
                    dossier,
                    "--write",
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertTrue(payload["promotion_ready"])
            self.assertTrue(
                (
                    Path(payload["write_result"]["bundle_root"])
                    / "promotion.json"
                ).is_file()
            )


if __name__ == "__main__":
    unittest.main()
