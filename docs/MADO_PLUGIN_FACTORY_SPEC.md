# MADO_PLUGIN_FACTORY_SPEC.md v0.3

Status: Implementing  
Project: MADO Plugin Factory  
Repository: `madowaku/mado-plugin-factory`

## 1. Purpose

MADO Plugin Factory is a release-confidence compiler for reusable agent capabilities.

It transforms a Skill, workflow, or MCP-backed project into artifacts whose structure, behavior, risk surface, review materials, and evidence state can be explained.

## 2. Pipeline

```text
SOURCE
  |
  v
Candidate Scanner                <- M0.1 complete
  |
  +--> architecture
  +--> skills
  +--> dependencies
  +--> risk flags
  |
  v
Manifest Compiler                <- M0.2 complete
  |
  +--> portable plugin.json
  +--> interface metadata
  +--> validation
  |
  v
Submission Eval Compiler         <- M0.3 complete
  |
  +--> exactly 5 positive drafts
  +--> exactly 3 negative drafts
  +--> review blockers
  |
  v
Local Marketplace Bridge         <- M0.4
  |
  v
Submission Evidence Bundle       <- M0.5
```

## 3. Evidence states

Every claim belongs to one of:

- `generated`
- `inspected`
- `executed`

A compiler step MUST NOT promote evidence to a stronger state without proof.

M0.3 produces `generated` evidence only.

## 4. MPF-M0.1 Candidate Scanner

Status: complete.

The scanner:

- discovers production Skills
- distinguishes portable and compatibility packaging
- detects configured MCP surfaces
- inventories dependencies
- emits risk flags with file-path evidence
- never reveals matched secrets
- never mutates the source candidate

Architecture output:

- `skills_only`
- `mcp_only`
- `skills_plus_mcp`
- `not_ready`

## 5. MPF-M0.2 Manifest Compiler

Status: complete.

The canonical package identity is root `plugin.json`.

The compiler emits OpenAI presentation metadata under:

```text
extensions.com.openai.interface
```

It can optionally emit `.codex-plugin/plugin.json` as a compatibility mirror.

Default behavior is dry-run.

Invalid output is not written. Differing existing manifests require explicit `--force`.

## 6. MPF-M0.3 Submission Eval Compiler

Status: complete.

### 6.1 Goal

Compile a candidate's known behavior and risk surface into the review material required for plugin submission without pretending generated cases have been manually reviewed or executed.

### 6.2 CLI

Dry-run:

```bash
mpf evals <candidate-path> --pretty
```

Metadata-assisted:

```bash
mpf evals <candidate-path> \
  --metadata ./eval-metadata.json \
  --pretty
```

Write evidence:

```bash
mpf evals <candidate-path> \
  --metadata ./eval-metadata.json \
  --write
```

Default output:

```text
evidence/evals/test-cases.json
```

The output path MUST remain inside the candidate root.

### 6.3 Count target

The compiler emits exactly:

- 5 positive cases
- 3 negative cases

This satisfies the common submission requirement while matching the stricter exact-count final submission path.

### 6.4 Positive case schema

```json
{
  "id": "P1",
  "intent_key": "primary-workflow",
  "user_prompt": "...",
  "expected_behavior": "...",
  "expected_result_shape": "...",
  "fixture": "...",
  "source": "...",
  "evidence_state": "generated",
  "review_required": true
}
```

Required reviewer concepts:

- realistic user prompt
- expected Skill/tool/workflow behavior
- expected result shape
- reproducible test account or fixture data

### 6.5 Positive case source precedence

Candidate cases are assembled in deterministic order:

1. explicit `metadata.positive`
2. portable manifest `defaultPrompt`
3. discovered Skill name/description
4. deterministic workflow-focus cases

Then the compiler:

1. normalizes Unicode and whitespace,
2. removes duplicate prompts,
3. removes duplicate intent keys,
4. takes the first five unique cases,
5. assigns `P1` through `P5`.

### 6.6 Fixture contract

The compiler MUST NOT infer that a test needs no fixture.

When no default or per-case fixture is supplied, it emits:

```text
REVIEW REQUIRED: describe reproducible test account or fixture data,
or explicitly state that no special fixture is required.
```

This produces:

- validation warning `fixture_review_required`
- top-level blocker `fixture_data_requires_review`

A supplied fixture is preserved as generated review material. It is not automatically treated as executed evidence.

### 6.7 Negative case schema

```json
{
  "id": "N1",
  "intent_key": "protect-secrets",
  "user_prompt_or_scenario": "...",
  "expected_safe_behavior": "...",
  "reason_not_to_complete": "...",
  "source": "...",
  "evidence_state": "generated",
  "review_required": true
}
```

Expected safe behavior may be:

- refusal
- clarification
- explicit confirmation gate
- scoped fallback
- truthful tool/runtime failure handling

### 6.8 Negative case source precedence

Candidate cases are assembled in deterministic order:

1. explicit `metadata.negative`
2. M0.1 risk-derived cases
3. generic boundary cases

Risk-to-case mappings include:

- `auth_or_secret_dependency` -> secret exposure
- `destructive_operation` -> irreversible action without confirmation
- `user_data_access` -> unrelated private-data disclosure
- `external_network` -> unrelated endpoint/data egress
- `mcp_runtime_dependency` -> fabricated tool success

Generic fallback intents are:

- out-of-scope work
- missing required context
- fabricated execution success

The final three unique cases receive `N1` through `N3`.

### 6.9 Validation

Validation errors include:

- wrong positive count
- wrong negative count
- non-sequential IDs
- missing required text fields
- duplicate intent keys
- duplicate normalized positive prompts
- duplicate normalized negative scenarios
- non-generated evidence state at compile time
- a generated case with `review_required: false`

Warnings include unresolved fixture review.

### 6.10 Review state

M0.3 output always begins with:

```json
{
  "review_required": true,
  "evidence_state": "generated",
  "submission_ready": false
}
```

At minimum the blocker is:

```text
generated_cases_require_review
```

The compiler never marks its own generated cases submission-ready.

### 6.11 Write safety

Default behavior is dry-run.

`--write`:

- writes only a validation-valid eval report
- creates the parent evidence directory if needed
- refuses to overwrite differing evidence unless `--force` is explicit
- allows idempotent writes when bytes are already identical
- rejects absolute paths and `..` traversal

### 6.12 Determinism

Given the same:

- source candidate
- portable manifest
- scanner-observable files
- eval metadata

M0.3 MUST return identical test-case ordering and content.

No timestamps, random IDs, or environment-derived test claims are inserted.

## 7. Metadata input

Example:

```json
{
  "default_fixture": "Fixture: tests/fixtures/sample.json",
  "positive": [
    {
      "intent_key": "primary-reviewed-workflow",
      "user_prompt": "Run the documented workflow on the sample fixture.",
      "expected_behavior": "Use the intended Skill and preserve the supplied constraints.",
      "expected_result_shape": "A structured user-facing result.",
      "fixture": "Fixture: tests/fixtures/sample.json"
    }
  ],
  "negative": [
    {
      "intent_key": "reviewed-boundary",
      "user_prompt_or_scenario": "Ask for an unsupported irreversible action.",
      "expected_safe_behavior": "Do not execute it without the required safety gate.",
      "reason_not_to_complete": "The request crosses a documented safety boundary."
    }
  ]
}
```

All compiled cases remain `generated` and `review_required`, even when their text came from metadata.

## 8. Safety rules

The factory MUST NOT:

- fabricate successful test execution
- label generated review material as inspected or executed
- silently declare fixtures unnecessary
- fabricate reviewer credentials or test accounts
- reveal detected secrets in evidence
- hide a risk-derived negative case to make a candidate look safer
- write evidence outside the candidate root
- overwrite differing evidence without explicit force

## 9. Milestones

### MPF-M0.0 Skeleton

Status: complete.

### MPF-M0.1 Candidate Scanner

Status: complete.

### MPF-M0.2 Manifest Compiler

Status: complete.

### MPF-M0.3 Submission Eval Compiler

Status: complete.

Acceptance satisfied:

- emits exactly 5 positive and 3 negative cases
- validates required submission fields
- deduplicates normalized prompts and intent keys
- all generated cases remain review-required
- fixture references are supported
- missing fixture information becomes a visible blocker
- M0.1 risk flags feed negative cases
- M0.2 starter prompts feed positive cases
- output is deterministic
- write path stays inside the candidate root
- overwrite requires explicit force

### MPF-M0.4 Local Marketplace Bridge

Acceptance:

- generated plugin can be referenced by a local/repo marketplace
- install path remains relative and inside its root
- actual install result is recorded as executed evidence

### MPF-M0.5 Submission Evidence Bundle

Acceptance:

- one command produces a versioned evidence directory
- every claim is tagged generated, inspected, or executed
- unreviewed eval cases prevent submission-ready status
- missing publication/legal material prevents submission-ready status

## 10. North star

```text
"I have a useful Skill"
        ->
"I have a plugin artifact whose structure, behavior,
metadata, tests, risks, review state, and evidence I can explain."
```

MADO Plugin Factory is a **release-confidence compiler**.
