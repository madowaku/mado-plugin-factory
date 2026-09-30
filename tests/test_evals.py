from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from mado_plugin_factory.evals import (
    EvalError,
    compile_submission_evals,
    write_submission_evals,
)


def make_skill(
    root: Path,
    *,
    name: str = "hello",
    description: str = "Greet a user using the documented workflow.",
    body: str = "Return the requested greeting.",
) -> None:
    skill = root / "skills" / name
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\n{body}\n",
        encoding="utf-8",
    )


def make_manifest(root: Path, prompts: list[str] | None = None) -> None:
    (root / "plugin.json").write_text(
        json.dumps(
            {
                "$schema": "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",
                "name": "hello-plugin",
                "version": "0.3.0",
                "description": "Greet users with a repeatable workflow.",
                "extensions": {
                    "com.openai": {
                        "interface": {
                            "displayName": "Hello Plugin",
                            "shortDescription": "Repeatable greetings",
                            "longDescription": "Greet users with a repeatable workflow.",
                            "defaultPrompt": prompts or ["Create a friendly greeting for the supplied fixture."],
                        }
                    }
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


class SubmissionEvalCompilerTests(unittest.TestCase):
    def test_compiles_exact_case_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "hello"
            root.mkdir()
            make_skill(root)
            make_manifest(root)
            report = compile_submission_evals(root)
            self.assertEqual(len(report["positive"]), 5)
            self.assertEqual(len(report["negative"]), 3)
            self.assertTrue(report["validation"]["valid"])

    def test_uses_manifest_starter_prompt_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "hello"
            root.mkdir()
            make_skill(root)
            make_manifest(root, ["Use the greeting fixture to produce the final message."])
            report = compile_submission_evals(root)
            prompts = [case["user_prompt"] for case in report["positive"]]
            self.assertIn("Use the greeting fixture to produce the final message.", prompts)

    def test_scanner_risk_generates_negative_case(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "secure"
            root.mkdir()
            make_skill(
                root,
                body="Read the API_KEY from the environment but never reveal it to the user.",
            )
            make_manifest(root)
            report = compile_submission_evals(root)
            sources = {case["source"] for case in report["negative"]}
            self.assertIn("scanner.risk_flags:auth_or_secret_dependency", sources)

    def test_generated_cases_remain_review_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "hello"
            root.mkdir()
            make_skill(root)
            report = compile_submission_evals(root)
            cases = report["positive"] + report["negative"]
            self.assertTrue(all(case["review_required"] is True for case in cases))
            self.assertTrue(all(case["evidence_state"] == "generated" for case in cases))
            self.assertFalse(report["submission_ready"])
            self.assertIn("generated_cases_require_review", report["blocking_reasons"])

    def test_fixture_placeholder_is_a_warning_and_blocker(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "hello"
            root.mkdir()
            make_skill(root)
            report = compile_submission_evals(root)
            self.assertTrue(report["validation"]["fixture_review_required"])
            self.assertIn("fixture_data_requires_review", report["blocking_reasons"])

    def test_explicit_fixture_removes_fixture_placeholder_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "hello"
            root.mkdir()
            make_skill(root)
            report = compile_submission_evals(
                root,
                metadata={"default_fixture": "Fixture: tests/fixtures/greeting.json"},
            )
            self.assertFalse(report["validation"]["fixture_review_required"])
            self.assertNotIn("fixture_data_requires_review", report["blocking_reasons"])
            self.assertTrue(
                all(
                    case["fixture"] == "Fixture: tests/fixtures/greeting.json"
                    for case in report["positive"]
                )
            )

    def test_duplicate_explicit_positive_prompt_is_deduped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "hello"
            root.mkdir()
            make_skill(root)
            duplicate = {
                "user_prompt": "Run the primary greeting workflow.",
                "expected_behavior": "Use the hello skill.",
                "expected_result_shape": "A greeting.",
                "fixture": "Fixture A",
            }
            report = compile_submission_evals(
                root,
                metadata={"positive": [duplicate, duplicate]},
            )
            prompts = [case["user_prompt"].casefold() for case in report["positive"]]
            self.assertEqual(len(prompts), len(set(prompts)))
            self.assertEqual(len(prompts), 5)

    def test_not_ready_candidate_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(EvalError):
                compile_submission_evals(Path(tmp))

    def test_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "hello"
            root.mkdir()
            make_skill(root)
            make_manifest(root)
            metadata = {"default_fixture": "Fixture A"}
            self.assertEqual(
                compile_submission_evals(root, metadata=metadata),
                compile_submission_evals(root, metadata=metadata),
            )

    def test_write_requires_force_and_rejects_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "hello"
            root.mkdir()
            make_skill(root)
            report = compile_submission_evals(root)
            outputs = write_submission_evals(root, report)
            self.assertIn("evidence/evals/test-cases.json", outputs)

            target = root / "evidence" / "evals" / "test-cases.json"
            target.write_text("{}\n", encoding="utf-8")
            with self.assertRaises(EvalError):
                write_submission_evals(root, report)
            write_submission_evals(root, report, force=True)

            with self.assertRaises(EvalError):
                write_submission_evals(root, report, output="../escape.json")

    def test_cli_dry_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "hello"
            root.mkdir()
            make_skill(root)
            env = dict(os.environ)
            env["PYTHONPATH"] = str(Path(__file__).parents[1] / "src")
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "mado_plugin_factory",
                    "evals",
                    str(root),
                    "--pretty",
                ],
                text=True,
                capture_output=True,
                env=env,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(len(payload["positive"]), 5)
            self.assertEqual(len(payload["negative"]), 3)


if __name__ == "__main__":
    unittest.main()
