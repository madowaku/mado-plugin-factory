# MADO Plugin Factory

MADO Plugin Factory turns reusable Skills and MCP-backed workflows into submission-ready OpenAI plugins for ChatGPT and Codex.

## Goal

Convert an existing project or skill into a reproducible plugin release bundle:

```text
Skill / Repo
  -> Candidate Scan
  -> Manifest Compile
  -> Submission Eval Compile
  -> Local marketplace validation
  -> Submission evidence bundle
```

## Current status

- **MPF-M0.0 Skeleton** ✅
- **MPF-M0.1 Candidate Scanner** ✅
- **MPF-M0.2 Manifest Compiler** ✅
- **MPF-M0.3 Submission Eval Compiler** ✅
- MPF-M0.4 Local Marketplace Bridge
- MPF-M0.5 Submission Evidence Bundle

## MPF-M0.1 Candidate Scanner

The scanner is read-only and emits deterministic JSON describing:

- architecture: `skills_only`, `mcp_only`, `skills_plus_mcp`, or `not_ready`
- discovered Skills and packaging surfaces
- external dependencies
- risk flags with evidence paths
- missing release requirements

```bash
mpf scan /path/to/candidate --pretty
```

## MPF-M0.2 Manifest Compiler

The manifest compiler creates the portable root `plugin.json`.

```bash
mpf manifest /path/to/candidate \
  --metadata ./manifest-metadata.json \
  --write
```

Compilation is a dry-run unless `--write` is supplied. A differing existing manifest is protected unless `--force` is explicit.

OpenAI install-surface metadata is emitted under:

```text
extensions.com.openai.interface
```

An optional compatibility mirror can be generated with `--compat`.

## MPF-M0.3 Submission Eval Compiler

The eval compiler turns the candidate's Skills, manifest starter prompts, and scanner risk signals into reviewer-facing test-case drafts.

```bash
mpf evals /path/to/candidate --pretty
```

Provide reviewed fixture/test-account context with:

```bash
mpf evals /path/to/candidate \
  --metadata ./eval-metadata.json \
  --pretty
```

Write the evidence artifact only after validation:

```bash
mpf evals /path/to/candidate \
  --metadata ./eval-metadata.json \
  --write
```

Default output:

```text
evidence/evals/test-cases.json
```

Use `--output <relative-path>` to change the evidence location and `--force` to replace a differing existing report.

### Eval contract

The compiler targets exactly:

- 5 positive cases
- 3 negative cases

Positive cases contain:

- `id`
- `intent_key`
- `user_prompt`
- `expected_behavior`
- `expected_result_shape`
- `fixture`
- `source`
- `evidence_state`
- `review_required`

Negative cases contain:

- `id`
- `intent_key`
- `user_prompt_or_scenario`
- `expected_safe_behavior`
- `reason_not_to_complete`
- `source`
- `evidence_state`
- `review_required`

### Evidence discipline

M0.3 deliberately does **not** mark generated test cases as submission-ready.

Every compiled case starts as:

```json
{
  "evidence_state": "generated",
  "review_required": true
}
```

The top-level report therefore starts with:

```json
{
  "submission_ready": false,
  "blocking_reasons": [
    "generated_cases_require_review"
  ]
}
```

If no fixture/test-account information is provided, positive cases contain a visible `REVIEW REQUIRED` fixture placeholder and add `fixture_data_requires_review` as a blocker.

The compiler never silently assumes that no fixture is needed.

### Positive case sources

Candidate generation priority is deterministic:

1. explicit cases from eval metadata
2. `extensions.com.openai.interface.defaultPrompt`
3. discovered Skill name/description pairs
4. deterministic valid-workflow focus cases

Duplicate normalized prompts and duplicate intent keys are removed before the final five cases are selected.

### Negative case sources

Explicit negative cases are used first.

Scanner risk signals then generate boundary cases for:

- authentication / secret exposure
- destructive operations
- user-data disclosure
- unrelated external network access
- fabricated MCP success

If fewer than three risk-derived cases exist, deterministic generic boundary cases fill the remainder:

- out-of-scope work
- missing required context
- fabricated execution success

See `templates/evals/metadata.json` for reviewer-supplied fixture and case overrides.

## Portable plugin packaging

New packages target:

```text
my-plugin/
  plugin.json
  skills/
    my-skill/
      SKILL.md
  mcp.json                 # optional portable MCP
  .codex-plugin/
    plugin.json             # optional compatibility mirror
```

The root `plugin.json` is canonical.

## Safety and determinism

The factory separates evidence into:

- `generated`
- `inspected`
- `executed`

Current guarantees:

- scanning does not mutate source candidates
- manifest compilation is dry-run by default
- differing manifest replacement requires `--force`
- eval compilation is dry-run by default
- generated evals remain review-required
- no fixture requirement is silently waived
- evidence output cannot escape the candidate root
- differing eval evidence replacement requires `--force`
- deterministic inputs produce deterministic reports

## Tests

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

The suite covers Scanner, Manifest Compiler, and Submission Eval Compiler behavior including:

- all four architecture states
- portable/compatibility manifest behavior
- overwrite protection
- exact 5/3 eval counts
- manifest starter-prompt ingestion
- risk-derived negative cases
- fixture review blockers
- duplicate prompt suppression
- evidence path safety
- deterministic output
- CLI dry-run behavior

## Source of truth

Implementation tracks:

- https://developers.openai.com/plugins/build/plugins
- https://developers.openai.com/plugins/build/skills
- https://developers.openai.com/plugins/deploy/submission
- https://developers.openai.com/plugins/deploy/submission-errors

## Design rule

Do not optimize first for "publishing a plugin."

Optimize for a deterministic transformation from a known-good Skill into a reviewable, testable, reproducible plugin artifact.

The product is a **release-confidence compiler**.
