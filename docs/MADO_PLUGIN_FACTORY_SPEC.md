# MADO_PLUGIN_FACTORY_SPEC.md v0.8

Status: Implemented through M0.8  
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
  |
  v
Extension Capability Compiler     <- M0.6 complete
  |
  v
Extension Scaffold Generator      <- M0.7 complete
  |
  v
Extension Apply / Patch Engine    <- M0.8 complete
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

## 7. MPF-M0.6 Extension Capability Compiler

Status: complete.

### 7.1 Goal

Inspect a plugin candidate against the current OpenAI MCP Extensions contract and answer, per extension surface:

- Is implementation evidence already present?
- Are the prerequisites present to add it?
- Is product-specific input still required?
- What prerequisite blocks it?
- What protocol or manifest contract should the next implementation step target?

### 7.2 CLI

```bash
mpf extensions <plugin-root> --pretty
mpf extensions <plugin-root> --write
```

Default evidence output:

```text
evidence/extensions/capabilities.json
```

### 7.3 Capability states

M0.6 uses four capability states:

- `detected`: static source/manifest markers match the extension contract
- `eligible`: required architecture is present but no implementation marker was found
- `needs_input`: architecture is present but product-specific configuration is still missing
- `blocked`: a required MCP server, MCP App UI, or packaged Skill is absent

A `detected` capability remains `inspected` evidence. It MUST NOT be called runtime-verified.

### 7.4 Covered surfaces

The compiler covers:

- sidebar/global entrypoint
- conversation/thread entrypoint
- structured plugin settings
- file viewer/editor entrypoint
- display modes
- deep links
- Model-App Context
- composer mentions
- rich forms / OpenAI elicitation
- plugin onboarding

### 7.5 Onboarding manifest preservation

The Manifest Compiler preserves an existing `extensions.com.openai.onboardingSkill` or accepts `metadata.onboardingSkill`, validates that the path stays inside the package, and requires it to resolve to a packaged `SKILL.md`.

### 7.6 Evidence discipline

The compiler may identify static markers such as `openai/ui`, `openai/settings`, `mentions/search`, `ui/update-model-context`, and `openai/elicitation`.

It MUST NOT infer that ChatGPT successfully rendered or executed the extension from those markers alone.

### 7.7 Platform-aware notes

The report records the documented platform surface for each extension. File handlers and composer mentions remain desktop-only in the current extension spec, while OpenAI form elicitation is documented for desktop and web. Registered MCP servers also require MCP 2026-07-28 or later with MRTR for form elicitation.

## 8. MPF-M0.7 Extension Scaffold Generator

Status: complete.

### 8.1 Goal

Turn M0.6 capability inspection into deterministic implementation proposals without silently modifying the active plugin runtime.

### 8.2 CLI

```bash
mpf scaffold <plugin-root> --pretty
mpf scaffold <plugin-root> --write
```

Optional controls:

- repeat `--extension <id>` to select surfaces
- repeat `--file-extension .ext` for file viewer/editor scaffolds
- `--output <relative-directory>`
- `--force`

### 8.3 Default output

```text
evidence/scaffolds/extensions/
  plan.json
  README.md
  apply/
    extensions/openai/<extension>.ts
    skills/plugin-onboarding/SKILL.md
    manifest.patch.json
```

The output lives under evidence by default so Scanner and M0.6 do not mistake proposed code for active implementation evidence.

### 8.4 Generation rules

- `detected` capabilities are skipped as already implemented
- `blocked` capabilities are skipped with their blockers preserved
- `eligible` capabilities receive a scaffold
- `needs_input` capabilities generate only when required input is supplied or another selected scaffold satisfies the dependency
- file viewer/editor requires at least one explicit suffix
- deep links can scaffold when a sidebar/global entrypoint is already detected or is generated in the same pack
- onboarding produces a proposed Skill plus a manifest patch rather than silently editing `plugin.json`

### 8.5 Evidence discipline

Generated scaffold files are `generated` evidence. They MUST NOT upgrade an extension to detected or runtime-verified until the proposal is deliberately applied to the active package and later inspected/executed.

### 8.6 Write safety

The scaffold writer:

- only writes inside the plugin root
- rejects absolute paths and parent traversal
- refuses symlink targets
- is idempotent for identical bytes
- requires `--force` to replace differing generated files

## 9. MPF-M0.8 Extension Apply / Patch Engine

Status: complete.

### 9.1 Goal

Promote an M0.7 scaffold proposal into active plugin source without equating source mutation with runtime execution.

### 9.2 CLI

```bash
mpf patch <plugin-root> --pretty
mpf patch <plugin-root> --apply --pretty
```

Optional controls:

- `--scaffold <relative-directory>`
- `--force` for differing generated source files
- `--evidence-output <relative-file>`

### 9.3 Patch plan

Dry-run compilation reads the scaffold `plan.json` plus `apply/` tree and emits deterministic operations with source hash, target-before hash, target-after hash, operation kind, explicit force requirements, semantic conflicts, and a deterministic `patch_id`.

### 9.4 Manifest merge contract

`apply/manifest.patch.json` is deep-merged into live `plugin.json` only when existing values are absent or already equal. A differing semantic value is a hard conflict and is not overridden by `--force`.

### 9.5 Source promotion

Generated TypeScript proposal modules are promoted to `extensions/openai/`. Their M0.7 proposal header is rewritten to an M0.8 source-applied header that explicitly states runtime verification is still pending.

Onboarding artifacts are promoted to `skills/plugin-onboarding/SKILL.md` and the manifest patch is merged separately.

### 9.6 Drift guard

Before writing, M0.8 rechecks every target against the hashes observed during planning. Any source drift aborts the apply rather than applying a stale plan.

### 9.7 Post-apply verification

After writes, M0.8 re-runs M0.6. Every extension listed as generated by the scaffold must be statically `detected`. The resulting evidence is `executed` for the filesystem patch action, while `runtime_verified` remains false.

### 9.8 Evidence

Successful apply writes `evidence/patches/extensions/<patch-id>.json`. The evidence records operations, written files, manifest validation, M0.6 detection results, and the separation between source application and runtime verification.

## 10. Safety rules

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

## 11. Acceptance

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

### MPF-M0.6 acceptance

MPF-M0.6 is complete when:

- one command emits a deterministic extension capability report
- all ten documented extension surfaces are represented
- static implementation evidence is separated from runtime verification
- missing MCP/App UI/Skill prerequisites stay explicit
- file handlers remain input-gated until file extensions are known
- onboardingSkill is preserved and validated by the Manifest Compiler
- evidence output stays inside the plugin root and is overwrite-safe
- scanner output remains stable after writing extension evidence
- unit/CI tests cover detection, eligibility, blockers, onboarding, path safety, and CLI behavior

### MPF-M0.7 acceptance

MPF-M0.7 is complete when:

- one command compiles a deterministic scaffold plan
- default selection follows M0.6 actionable capabilities
- explicit extension selection is validated
- detected and blocked capabilities are never silently scaffolded
- file viewer/editor requires explicit suffix input
- deep-link dependency on a global entrypoint is modeled across the same scaffold pack
- onboarding emits a proposed Skill and manifest patch without editing the live manifest
- proposed files are isolated from active source detection by default
- writes are contained, idempotent, and overwrite-safe
- unit/CI tests cover selection, prerequisites, generated content, path safety, and CLI behavior

### MPF-M0.8 acceptance

MPF-M0.8 is complete when:

- dry-run emits a deterministic patch plan before mutation
- apply only accepts a written M0.7 scaffold pack
- target paths remain inside the plugin root
- scaffold symlinks and target symlink escapes are rejected
- identical targets are idempotent
- differing generated files require explicit force
- semantic manifest conflicts cannot be forced
- stale target hashes abort application
- successful apply re-runs M0.6 and verifies static detection
- executed patch evidence is written outside the distributable package
- source-applied and runtime-verified states remain distinct
- unit/CI tests cover create, replace, manifest merge, conflict, drift, containment, idempotence, verification, and CLI behavior

## 12. North star

```text
"I have a useful Skill"
        ->
"I have the exact package and an auditable release dossier
that says what was generated, what was reviewed,
what actually ran, and exactly what still blocks submission."
```

MADO Plugin Factory is a **release-confidence compiler**.
