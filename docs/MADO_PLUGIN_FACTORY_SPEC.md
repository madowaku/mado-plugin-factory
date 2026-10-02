# MADO_PLUGIN_FACTORY_SPEC.md v0.5

Status: Implemented through M0.5  
Project: MADO Plugin Factory  
Repository: `madowaku/mado-plugin-factory`

## 1. Purpose

MADO Plugin Factory is a release-confidence compiler for reusable agent capabilities.

```text
SOURCE
  |
  v
Candidate Scanner                <- M0.1 complete
  |
  v
Manifest Compiler                <- M0.2 complete
  |
  v
Submission Eval Compiler         <- M0.3 complete
  |
  v
Local Marketplace Bridge         <- M0.4 complete
  |
  v
Submission Evidence Bundle       <- M0.5 complete
```

The factory separates "generated", "inspected", and "executed" evidence and refuses to turn missing proof into a release claim.

## 2. MPF-M0.1 Candidate Scanner

Status: complete.

The Scanner is read-only and inventories:

- architecture
- Skills
- portable/compat manifests
- MCP surfaces
- dependencies
- risk signals
- missing requirements

Generated `evidence/` is excluded from scanning. This keeps source inspection stable after later pipeline stages write evidence artifacts.

## 3. MPF-M0.2 Manifest Compiler

Status: complete.

The canonical portable package uses root `plugin.json`.

The compiler validates:

- Agent Plugins schema
- plugin identity/version
- OpenAI interface metadata
- URLs
- component paths
- asset paths
- package-level listing limits

Invalid output is never written.

## 4. MPF-M0.3 Submission Eval Compiler

Status: complete.

It compiles exactly five positive and three negative review cases.

Each positive case contains:

- user prompt
- expected Skill/tool/workflow behavior
- expected result shape
- reproducible fixture/test-account field

Each negative case contains:

- user prompt/scenario
- expected refusal/clarification/safe fallback
- reason the action should not be completed

Generated cases remain review-required until an explicit review attestation is supplied to M0.5.

## 5. MPF-M0.4 Local Marketplace Bridge

Status: complete.

It creates a repo marketplace entry, stages only curated distributable plugin files, and verifies the actual installed ChatGPT/Codex cache copy.

A local marketplace catalog is not install proof.

Successful cache verification is `executed` evidence.

## 6. MPF-M0.5 Submission Evidence Bundle

Status: complete.

### 6.1 Goal

Produce one deterministic, versioned release directory that answers:

- What exact plugin package is being submitted?
- Does the manifest validate?
- What risks did the Scanner find?
- What 5/3 review cases are attached?
- Were those cases human-reviewed?
- Was the final Skill tree tested?
- Was the local installed copy verified?
- What publication metadata is ready?
- What portal-only gates remain?
- What MCP-specific gates remain?

### 6.2 CLI

Dry-run:

```bash
mpf bundle <plugin-root> \
  --release-metadata ./release.json \
  --pretty
```

Write:

```bash
mpf bundle <plugin-root> \
  --release-metadata ./release.json \
  --write
```

Optional:

- `--eval-evidence <relative-path>`
- `--install-evidence <relative-path>`
- `--output <relative-directory>`
- `--force`

### 6.3 Default source evidence

M0.5 reads:

```text
evidence/evals/test-cases.json
evidence/marketplace/install-verification.json
```

Both paths must stay inside the plugin root.

### 6.4 Versioned bundle directory

Default:

```text
evidence/releases/<plugin-version>/
```

Artifacts:

```text
bundle.json
scanner.json
manifest-validation.json
evals.json
install-verification.json
release-metadata.json
plugin.zip
plugin.zip.sha256
```

Missing optional evidence files are not fabricated; their absence remains visible through blockers.

### 6.5 Bundle report

The top-level report includes:

- `bundle_id` = `plugin-name@version`
- `release_id`
- `submission_type`
- package file inventory
- curated package digest
- starter prompts
- evidence checks
- `upload_ready`
- `submission_ready`
- upload blockers
- submission blockers
- warnings
- artifact paths

### 6.6 Submission type

Scanner architecture maps to:

- `skills_only` for skills-only candidates
- `with_mcp` for MCP-only or skills-plus-MCP candidates

MCP-backed bundles receive the additional MCP gates in section 6.11.

### 6.7 Release metadata contract

See:

```text
templates/release/submission.json
```

Supported top-level fields:

- `availability`
- `release_notes`
- `starter_prompts`
- `listing`
- `review`
- `portal`
- `mcp`
- `policy_attestation_note`

Unknown material is not copied into the release report.

### 6.8 Human review contract

`review` contains explicit booleans:

- `eval_cases_reviewed`
- `skills_final_tree_tested`
- `listing_reviewed`

All default to false.

When eval validation passes and `eval_cases_reviewed=true`, the bundle may describe the eval review check as `inspected`.

M0.5 does not alter the original M0.3 cases or relabel their generated origin.

### 6.9 Upload-ready contract

`upload_ready=true` requires no local blockers.

Current local blockers include:

- invalid manifest
- unresolved Scanner requirements
- missing/invalid eval evidence
- eval cases not reviewed
- final Skill tree not tested
- listing not reviewed
- missing/invalid install evidence
- local install not verified
- missing availability
- missing release notes

This state means the local package/review materials are coherent enough to prepare for portal upload.

### 6.10 Submission-ready contract

`submission_ready=true` requires all upload-ready checks plus publication and portal gates.

Publication checks include:

- starter prompts
- complete listing copy
- logo readiness
- HTTPS website URL
- HTTPS support URL
- HTTPS privacy policy URL
- HTTPS terms URL

Portal attestations include:

- Apps Management write access
- verified developer/business identity
- policy attestations complete
- bundled Skill safety scan passed

All portal values default to false and must be explicitly supplied after the corresponding external state is known.

### 6.11 MCP-specific gates

For `with_mcp` bundles, final readiness additionally requires:

- production HTTPS MCP URL
- demo recording URL
- domain verification complete
- current tool scan
- tool annotations reviewed
- reviewer access setup ready

These are release-state attestations. Credentials themselves MUST NOT be stored in the release metadata.

### 6.12 Secret handling

Release metadata is not a credential store.

Fields whose keys indicate passwords, tokens, API keys, client secrets, authorization material, or credential values are rejected.

Boolean readiness flags such as `reviewer_credentials_ready` are allowed because they contain no credential material.

### 6.13 Deterministic plugin ZIP

M0.5 produces `plugin.zip` from the same curated package inventory used by M0.4.

Included surfaces:

- `plugin.json`
- `mcp.json`
- `.mcp.json`
- `.app.json`
- `.codex-plugin/plugin.json`
- `skills/**`
- `hooks/**`
- `assets/**`

Excluded surfaces include:

- evidence
- tests
- docs
- README
- build caches

ZIP determinism uses:

- sorted paths
- fixed ZIP timestamp `1980-01-01 00:00:00`
- fixed regular-file permissions
- fixed deflate compression settings

A SHA-256 checksum is written beside the ZIP.

### 6.14 Write safety

Default behavior is dry-run.

Bundle output:

- must be a relative path
- cannot contain parent traversal
- must resolve inside the plugin root
- cannot replace differing files unless `--force` is explicit
- supports idempotent rewrites when bytes are already identical

### 6.15 Exit codes

- `0`: submission-ready
- `3`: upload-ready but final submission blockers remain
- `2`: local/upload blockers remain
- `1`: compiler/input error

### 6.16 Evidence-state rules

M0.5 uses:

- Scanner / manifest validation: `inspected`
- generated evals without review: `generated`
- explicitly reviewed valid evals: review check `inspected`
- marketplace verification evidence: `executed` only when M0.4 actually ran verification
- release/portal booleans: `inspected` attestations

No stage may claim a stronger state than its evidence source supports.

## 7. Safety rules

M0.5 MUST NOT:

- put internal evidence inside the plugin ZIP
- invent missing eval or install evidence
- mark a failed local install as verified
- infer human review from generated cases
- infer publisher identity or portal permissions
- store credentials/secrets in release metadata
- treat a missing portal scan as passed
- treat MCP domain/tool checks as complete without explicit state
- write outside the plugin root
- silently overwrite a differing release bundle

## 8. Acceptance

MPF-M0.5 is complete when:

- one command compiles a versioned release report
- one command writes a deterministic versioned release directory
- scanner, manifest, eval, install, and release metadata are aggregated
- exact plugin ZIP is generated separately from internal evidence
- ZIP SHA-256 is emitted
- readiness blockers are explicit
- upload-ready and submission-ready are distinct
- MCP-specific gates are architecture-aware
- generated/inspected/executed states remain traceable
- failed install verification remains visible
- evidence creation does not perturb subsequent source scans
- unit/CI tests cover idempotence and safety boundaries

## 9. North star

```text
"I have a useful Skill"
        ->
"I have the exact package and an auditable release dossier
that says what was generated, what was reviewed,
what actually ran, and exactly what still blocks submission."
```

MADO Plugin Factory is a **release-confidence compiler**.
