# MADO_PLUGIN_FACTORY_SPEC.md v1.8

Status: Implemented through M1.8  
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
  |
  v
Extension Runtime Smoke / Evidence <- M0.9 complete
  |
  v
ChatGPT Host Replay / Acceptance   <- M1.0 complete
  |
  v
Host Trace Capture / Normalizer    <- M1.1 complete
  |
  v
Extension Verification Orchestrator <- M1.2 complete
  |
  v
Verification Promotion Gate / Release Bundle Bridge <- M1.3 complete
  |
  v
Verification Freshness / Remote MCP Drift Gate <- M1.4 complete
  |
  v
Behavioral Contract Replay / Remote MCP Canary <- M1.5 complete
  |
  v
Authorization / Negative Contract Replay <- M1.6 complete
  |
  v
Credential Matrix / Scope Boundary Replay <- M1.7 complete
  |
  v
Least-Privilege / Security Scheme Contract Gate <- M1.8 complete
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

## 10. MPF-M0.9 Extension Runtime Smoke / Evidence

Status: complete.

### 10.1 Goal

Execute the configured MCP runtime and turn protocol observations into executed extension evidence without confusing MCP-server proof with full ChatGPT-host proof.

### 10.2 CLI

```bash
mpf runtime-smoke <plugin-root> --pretty
mpf runtime-smoke <plugin-root> --write-evidence --pretty
```

Optional controls:

- `--server <name>` when more than one MCP server is configured
- `--mode auto|modern|legacy`
- `--timeout <seconds>`
- `--evidence-output <relative-file>`
- `--force`

### 10.3 Protocol eras

For stdio servers, `auto` first probes MCP `2026-07-28` using `server/discover`. If the server does not support the modern method, M0.9 restarts the process and performs the legacy `initialize` / `notifications/initialized` flow.

Streamable HTTP smoke uses the modern stateless `2026-07-28` protocol. Legacy streamable HTTP is intentionally not implemented in M0.9.

### 10.4 Directly probeable extensions

M0.9 can verify from protocol metadata:

- sidebar/global entrypoints from `tools/list` plus MCP App resource reads
- conversation/thread entrypoints
- file viewer/editor entrypoints including declared extensions
- structured settings from server capabilities plus referenced tools
- composer mentions from tool metadata and app visibility
- display modes from MCP App resource metadata

UI entrypoints require a readable resource with MIME type `text/html;profile=mcp-app`.

### 10.5 Host-required extensions

The following surfaces are not promoted to runtime-verified by server-only probing:

- deep links
- Model-App Context
- rich forms / elicitation behavior

They are recorded as `host_required` because proving them requires ChatGPT host or MCP App interaction.

Plugin onboarding is recorded as a package-only surface rather than an MCP runtime surface.

### 10.6 Evidence discipline

`runtime_smoke_passed=true` means the MCP server connected and every directly probeable statically-detected extension was observed at runtime.

`runtime_verified=true` additionally requires at least one directly probeable runtime extension and no expected host-required extension remaining.

A successful M0.9 result still has `runtime_scope: mcp_server`; it does not claim an end-to-end ChatGPT UI interaction.

### 10.7 Evidence artifact

With `--write-evidence`, successful or failed executed observations can be persisted under:

```text
evidence/runtime/extensions/<server>-<smoke-id>.json
```

The artifact records protocol era/version, server identity, tool names, resource URIs, safe resource metadata, per-extension checks, missing surfaces, host-required surfaces, and runtime verdicts. It does not store MCP App HTML bodies, bearer tokens, or configured secret values.

### 10.8 Exit codes

- `0`: directly probeable extension runtime verified
- `3`: MCP server smoke passed but host verification remains
- `2`: expected runtime metadata is missing
- `1`: runtime/configuration error

## 11. MPF-M1.0 ChatGPT Host Replay / Extension Acceptance

Status: complete.

### 11.1 Goal

Close the host-only verification gap left by M0.9 without pretending that CI can drive the ChatGPT product UI. M1.0 consumes a normalized trace captured from an executed ChatGPT session, replays the extension-specific host contracts deterministically, and combines the result with executed M0.9 server evidence.

### 11.2 CLI

```bash
mpf host-replay <plugin-root> \\
  --trace ./chatgpt-host-trace.json \\
  --runtime-evidence evidence/runtime/extensions/<runtime>.json \\
  --pretty
```

Persist evidence with `--write-evidence`. When exactly one M0.9 evidence file exists under `evidence/runtime/extensions/`, `--runtime-evidence` may be omitted.

### 11.3 Capture contract

The normalized trace declares:

- `capture.product = "chatgpt"`
- supported surface: web, desktop, iOS, Android, or API Playground
- capture mode: developer mode, installed plugin, or API Playground
- `capture.executed`: whether the session actually occurred
- `capture.attested_chatgpt_capture`: explicit provenance attestation
- normalized host/app/server events with direction, method, optional call ID, params, and result

The repository template defaults both execution and attestation to false.

### 11.4 M0.9 prerequisite

Host acceptance requires executed M0.9 evidence with:

- `evidence_state = executed`
- `runtime_scope = mcp_server`
- `runtime_smoke_passed = true`

M1.0 only accepts host-required surfaces listed by that exact runtime evidence. A host trace by itself cannot create end-to-end verification.

### 11.5 Deep-link acceptance

Deep links are accepted when the trace contains ChatGPT-to-app evidence from either UI initialization or `ui/notifications/host-context-changed` with `openai/deepLink.url` that begins with `/` and contains no fragment.

The acceptance artifact stores only a SHA-256 of the observed app-relative URL, not the URL text.

### 11.6 Model-App Context acceptance

Model-App Context is accepted when an app-to-host `ui/update-model-context` request contains content or structured content and a correlated host-to-app response with `_meta.openai/modelContext.updateId` is present.

The acceptance artifact stores the call ID and a SHA-256 of the update ID. Model context content is not persisted.

### 11.7 Rich-form acceptance

Rich forms are accepted when a server-to-host `openai/elicitation/create` or modern `elicitation/create` form request has a correlated host-to-server result whose action is `accept`, `decline`, or `cancel`.

Any valid user outcome proves the host round trip. Form schema and submitted form content are not copied into acceptance evidence.

### 11.8 Verification states

`host_replay_passed=true` means every host-required extension from the selected M0.9 evidence has a valid trace contract.

`end_to_end_verified=true` additionally requires an executed and explicitly attested ChatGPT capture plus successful M0.9 server smoke. Synthetic or normalized fixture replay can test the validator but cannot satisfy the provenance gate unless explicitly marked as an executed ChatGPT capture.

### 11.9 Privacy and evidence

M1.0 persists only:

- trace SHA-256
- M0.9 evidence SHA-256
- capture product/surface/mode and attestation booleans
- event count
- extension acceptance summaries
- correlation IDs and hashed host identifiers where needed

It does not persist raw trace payloads, model-context text, form content, deep-link URL text, HTML bodies, credentials, or bearer tokens.

### 11.10 Exit codes

- `0`: end-to-end host acceptance verified
- `3`: replay shape passes but ChatGPT capture is unattested
- `2`: expected host acceptance evidence is incomplete
- `1`: trace/runtime evidence error

## 12. MPF-M1.1 Host Trace Capture / Normalizer

Status: complete.

### 12.1 Goal

Convert user-supplied ChatGPT developer-mode, installed-plugin, or API Playground observations into the normalized M1.0 host trace contract without persisting raw logs or sensitive payload values.

### 12.2 CLI

```bash
mpf host-capture <plugin-root> \\
  --input ./raw-host-log.json \\
  --surface web \\
  --mode developer_mode \\
  --executed \\
  --attest-chatgpt-capture \\
  --write
```

Optional controls:

- `--format auto|json|jsonl|normalized`
- `--output-dir <relative-directory>`
- `--force`
- `--pretty`

### 12.3 Input adapters

M1.1 supports:

- an already normalized event array
- generic JSON arrays and common record containers (`events`, `records`, `logs`, `messages`, `items`)
- JSON-RPC request/response pair objects
- JSONL/NDJSON streams with sequential JSON-RPC requests and responses

The generic adapters are intentionally schema-light because ChatGPT/API Playground logging surfaces can evolve. Unknown records are counted and skipped rather than promoted into evidence.

### 12.4 Event extraction

Only host-replay-relevant methods are emitted:

- `ui/initialize`
- `ui/notifications/host-context-changed`
- `ui/update-model-context`
- `openai/elicitation/create`
- `elicitation/create`

Request/response directions are inferred only for these known contracts. Existing explicit directions are preserved.

### 12.5 Correlation normalization

Source call IDs are not persisted verbatim. M1.1 maps them deterministically in first-seen order to `call-1`, `call-2`, and so on, preserving request/response correlation while reducing accidental identifier leakage.

### 12.6 Privacy reduction

Before writing `trace.json`, M1.1:

- replaces deep-link URL text with a `/__mpf_redacted__?sha256=<digest>` path
- replaces Model-App Context text with `[redacted]`
- replaces structured model context with a shape-only marker
- hashes model-context update IDs
- replaces form messages with `[redacted]`
- replaces requested form schemas with an empty object schema
- removes submitted form content

The raw capture file is never copied into evidence.

### 12.7 Provenance

Capture product is fixed to ChatGPT. Surface and mode are explicit CLI inputs. `--attest-chatgpt-capture` is invalid unless `--executed` is also supplied.

M1.1 does not infer execution or provenance from filenames, raw log shape, or existing capture metadata. Attestation remains a deliberate operator claim for the actual observed session.

### 12.8 Output

Default:

```text
evidence/host/captures/<capture-id>/
  trace.json
  capture.json
```

`trace.json` is directly consumable by M1.0. `capture.json` stores source SHA-256, adapter, record/event counts, redaction counts, provenance flags, artifact paths, and warnings.

### 12.9 Evidence discipline

M1.1 produces `inspected` capture evidence. Successful normalization does not imply host acceptance or end-to-end verification. Only M1.0 can combine the normalized trace with executed M0.9 runtime evidence and produce host acceptance.

## 13. MPF-M1.2 Extension Verification Orchestrator

Status: complete.

### 13.1 Goal

Bind M0.9 runtime smoke, M1.1 host capture normalization, and M1.0 host replay into one verification run that reports both verdicts and the exact next action without collapsing external-evidence waits into implementation failures.

### 13.2 CLI

```bash
mpf verify-extensions <plugin-root> --write --pretty
```

Optional runtime controls:

- `--server <name>`
- `--runtime-mode auto|modern|legacy`
- `--timeout <seconds>`

Optional host-capture controls:

- `--capture <file>`
- `--capture-format auto|json|jsonl|normalized`
- `--surface web|desktop|ios|android|api_playground`
- `--capture-mode developer_mode|installed_plugin|api_playground`
- `--executed`
- `--attest-chatgpt-capture`

Output controls:

- `--output-dir <relative-directory>`
- `--write`
- `--force`
- `--pretty`

### 13.3 Orchestration flow

M1.2 executes stages in this order:

1. M0.9 MCP runtime smoke.
2. If no host-required extensions remain and M0.9 is runtime-verified, finish at MCP-server scope.
3. If host-required extensions remain and no capture is supplied, stop at `awaiting_host_capture`.
4. When a capture is supplied, normalize it with M1.1.
5. Replay the normalized trace against the exact in-memory M0.9 report using M1.0 acceptance rules.
6. Emit a verification dossier with stage digests, verdicts, blockers, and next actions.

### 13.4 Verification states

M1.2 uses explicit outcome states:

- `verified_mcp_server`: all required extension proof is complete at server scope and no host-only extension remains
- `awaiting_host_capture`: runtime passed but host-required extensions need a ChatGPT observation
- `verified_chatgpt_host`: runtime plus attested host replay are complete
- `awaiting_capture_attestation`: host contracts replay successfully but the capture provenance is not fully attested
- `host_incomplete`: required host events are missing from the normalized trace
- `capture_failed`: supplied capture could not be normalized
- `host_replay_error`: normalized capture and runtime evidence could not be evaluated together
- `runtime_failed`: runtime executed but expected protocol evidence is missing
- `runtime_error`: MCP process/configuration execution failed
- `no_verification_target`: runtime succeeded but there is no directly verifiable or host-required extension target

### 13.5 Evidence binding

The dossier stores SHA-256 digests for each available stage snapshot. Host replay is evaluated against the same in-memory runtime report produced by the run, not an independently selected stale evidence file.

The verification ID is derived from the runtime, capture, normalized trace, host replay, outcome state, and stage-error digests. A rerun that materially changes executed evidence produces a different verification ID.

### 13.6 External evidence is not a runtime failure

When M0.9 passes but reports host-required extensions, absence of a ChatGPT capture is represented as `awaiting_host_capture`, not `runtime_failed`.

Likewise, a structurally complete host replay from an unattested capture is `awaiting_capture_attestation`, not a protocol failure.

This separation allows automation and humans to distinguish code defects from evidence still needing to be collected in ChatGPT.

### 13.7 Dossier output

Default:

```text
evidence/verifications/extensions/<verification-id>/
  dossier.json
  runtime.json
  capture.json
  trace.json
  host.json
```

Only artifacts for stages that actually ran are written. Runtime-only verification therefore writes `runtime.json` plus `dossier.json`; a host-complete run includes all five files.

The raw host capture is never copied into the dossier. `trace.json` is the privacy-reduced M1.1 trace.

### 13.8 Dossier contract

`dossier.json` records:

- verification ID/state/scope
- verification verdict and follow-up requirement
- per-stage state and SHA-256
- runtime-verified and runtime-missing extensions
- host-required, host-accepted, and host-missing extensions
- stage errors
- next actions
- artifact paths
- warnings inherited from completed stages

### 13.9 Exit codes

- `0`: verification complete and verified
- `3`: external ChatGPT capture or capture attestation is still required
- `2`: runtime/host verification failed or is incomplete
- `1`: orchestrator input or write error

### 13.10 Write safety

The dossier writer:

- writes only inside the plugin root
- rejects absolute paths and parent traversal
- rejects symlinked targets
- is idempotent for identical bytes
- requires `--force` before replacing differing dossier artifacts

### 13.11 Evidence discipline

M1.2 does not strengthen any stage beyond its source evidence. M0.9 remains the MCP runtime proof, M1.1 remains inspected capture normalization, and M1.0 remains the host acceptance gate. M1.2 only binds these stages into one run and one operator-facing verdict.

## 14. MPF-M1.3 Verification Promotion Gate / Release Bundle Bridge

Status: complete.

### 14.1 Goal

Promote a successful M1.2 verification run into the release dossier without confusing MPF verification policy with OpenAI portal submission requirements, and without allowing a verification result to survive package or evidence drift.

### 14.2 CLI

```bash
mpf promote <plugin-root> \\
  --release-metadata ./release.json \\
  --verification-evidence evidence/verifications/extensions/<id>/dossier.json \\
  --write
```

Optional controls:

- `--requirement auto|mcp_server|chatgpt_host`
- `--eval-evidence <relative-file>`
- `--install-evidence <relative-file>`
- `--output <relative-release-directory>`
- `--force`
- `--pretty`

### 14.3 Package binding

M1.2 records `source.plugin_package_digest` and incorporates it into the verification ID. M1.3 recomputes the current `plugin_package_digest` and requires an exact match before verification can pass the promotion gate.

A package change after verification therefore produces `verification_package_digest_mismatch`. Older M1.2 dossiers that lack the package digest are rejected with `verification_package_digest_missing` rather than being grandfathered into a stronger claim.

This digest binds the packaged plugin surfaces. Remote MCP server deployments remain independently mutable; after a server change, operators should rerun M1.2 to refresh runtime evidence before promotion.

### 14.4 Verification policy

M1.3 supports three policies:

- `mcp_server`: accept `verified_mcp_server` or the stronger `verified_chatgpt_host`
- `chatgpt_host`: require `verified_chatgpt_host`
- `auto`: require `chatgpt_host` when `host_required_extensions` is non-empty, otherwise require `mcp_server`

The selected verification state must also have `verification_verified=true`.

### 14.5 Stage artifact integrity

M1.3 reopens each stage artifact referenced by the M1.2 dossier and canonicalizes the JSON using the same sorted compact representation used by M1.2 digests.

When present, the following bindings are checked:

- runtime stage → `runtime.json`
- capture stage → `capture.json`
- normalized trace → `trace.json`
- host replay stage → `host.json`

A missing, invalid, or digest-mismatched stage artifact blocks promotion.

### 14.6 Release bridge

M1.3 compiles the ordinary M0.5 submission bundle first, then augments a copy of that report with an `extension_verification` check and a `promotion` section.

The existing `upload_ready` and `submission_ready` verdicts retain their M0.5 meaning. M1.3 adds `promotion_ready`, which requires both:

- ordinary M0.5 `submission_ready=true`
- M1.3 verification gate passed

This is an MPF quality gate. It is not represented as an additional OpenAI portal requirement.

### 14.7 Promoted release output

A promoted release writes the normal deterministic release directory and adds:

```text
evidence/releases/<version>/
  promotion.json
  verification/
    dossier.json
    runtime.json
    capture.json
    trace.json
    host.json
```

Only stage artifacts that exist in the selected M1.2 run are copied. The plugin ZIP remains curated by M0.5 and never contains `evidence/**`, `promotion.json`, or the verification directory.

### 14.8 Promotion identity

`promotion_id` is derived from:

- bundle ID
- current plugin package digest
- selected verification dossier SHA-256
- resolved verification requirement

Changing any of these produces a new promotion identity.

### 14.9 Exit codes

- `0`: release plus verification are promotion-ready
- `3`: M0.5 submission material is ready but the M1.3 verification gate blocks promotion
- `2`: the underlying M0.5 submission bundle is not submission-ready
- `1`: promotion input, validation, or write error

### 14.10 Evidence discipline

M1.3 does not replace OpenAI review or claim that promotion guarantees approval. It records that MPF release material and the selected verification evidence satisfy the configured internal promotion policy for the exact package digest.

## 15. MPF-M1.4 Verification Freshness / Remote MCP Drift Gate

Status: complete.

### 15.1 Goal

Detect remote MCP drift that cannot be seen through the packaged plugin digest, and require a live-fresh runtime surface before CLI promotion can succeed.

### 15.2 Runtime fingerprint

M0.9 now emits `runtime_fingerprint` with one overall SHA-256 plus component hashes for:

- negotiated protocol version/era
- advertised server capabilities
- normalized tool descriptors
- referenced MCP App resource observations

Tool descriptors include names, titles, descriptions, input/output schemas, annotations, security metadata, and relevant OpenAI/UI metadata. Resource observations include MIME/UI metadata and a SHA-256 of returned content without persisting raw HTML/blob content.

`serverInfo` is not part of the gate fingerprint because it is self-reported display/debug metadata.

### 15.3 Freshness CLI

```bash
mpf freshness <plugin-root> \\
  --verification-evidence evidence/verifications/extensions/<id>/dossier.json \\
  --pretty
```

Optional controls:

- `--server <name>`
- `--mode auto|modern|legacy`
- `--timeout <seconds>`
- `--write-evidence`
- `--evidence-output <relative-file>`
- `--force`

The selected server must match the server recorded by the M1.2 runtime artifact.

### 15.4 Drift verdict

Freshness is verified only when:

- the baseline runtime artifact is still bound to the dossier hash
- the baseline contains an M1.4 runtime fingerprint
- the current MCP runtime smoke passes
- the current overall fingerprint exactly matches the baseline fingerprint

The report lists changed fingerprint components and added/removed tool names and resource URIs.

### 15.5 Promotion integration

`mpf promote` now runs a live M1.4 freshness probe automatically before compiling the final promotion verdict. A stale or missing fingerprint adds a verification freshness blocker even when M1.3 package/evidence checks otherwise pass.

The lower-level static `compile_verification_promotion()` API remains available for compatibility. Live CLI promotion uses the new freshness-aware wrapper.

### 15.6 Promoted release evidence

When live promotion runs, `verification/freshness.json` is copied beside the M1.2 verification evidence. It remains outside `plugin.zip`.

### 15.7 Scope boundary

M1.4 proves freshness of the **advertised MCP surface**. It does not prove that tool business behavior, external dependencies, or authorization enforcement are unchanged when those changes do not alter the advertised protocol/tool/resource surface.

## 16. MPF-M1.5 Behavioral Contract Replay / Remote MCP Canary

Status: complete.

### 16.1 Goal

Detect behavioral drift that does not change the advertised MCP surface by executing explicit, deterministic read-only fixture calls and comparing privacy-reduced result contracts against a recorded baseline.

### 16.2 Canary contract

Start from:

```text
templates/canary/contract.json
```

Each case declares:

- stable case id
- MCP tool name
- fixture arguments
- expected outcome: `success`, `tool_error`, or `protocol_error`
- whether `structuredContent` is required/optional/forbidden
- expected returned content types
- optional expected protocol error code
- optional `stable_paths` inside structured content whose values should remain stable

The contract file itself may contain fixture values, but executed evidence stores only an arguments SHA-256, never raw arguments.

### 16.3 Read-only execution gate

Before sending `tools/call`, M1.5 inspects the live tool descriptor and requires:

```text
annotations.readOnlyHint = true
```

A tool lacking this explicit annotation is refused before invocation. Write/destructive canaries are out of scope for M1.5.

### 16.4 Record baseline

```bash
mpf canary <plugin-root> \
  --contract ./canary-contract.json \
  --verification-evidence evidence/verifications/extensions/<id>/dossier.json \
  --write-evidence
```

Record mode executes each safe case, validates declared expectations, and writes executed canary evidence under:

```text
evidence/canary/extensions/<canary-id>.json
```

When `--verification-evidence` is supplied, the baseline stores the verification ID and dossier SHA-256. Promotion can therefore require that the canary baseline was recorded against the same M1.2 verification run.

### 16.5 Replay

```bash
mpf canary <plugin-root> \
  --contract ./canary-contract.json \
  --baseline evidence/canary/extensions/<baseline-id>.json \
  --verification-evidence evidence/verifications/extensions/<id>/dossier.json
```

Replay requires the contract SHA-256 to match the baseline. When a verification dossier is supplied, the baseline dossier SHA-256 must also match.

### 16.6 Privacy-reduced behavior observation

M1.5 does not persist raw tool results. For each case it records:

- outcome class
- protocol error code when applicable
- returned content types
- recursive type/key shape of structured content
- SHA-256 values for explicitly declared stable paths
- overall behavior SHA-256

Tool-result text, structured values outside declared stable paths, and protocol error messages are not persisted.

### 16.7 Behavioral drift

Replay is verified only when:

- every case is safe to execute
- every declared expectation still passes
- every case matches the recorded behavior SHA-256
- the baseline contract still matches
- the selected verification binding still matches when present

A changed structured-content shape, error class/code, content type, or stable-path value produces behavioral drift even when M1.4 runtime metadata remains fresh.

### 16.8 Promotion integration

Behavioral promotion is opt-in because fixture design is product-specific.

```bash
mpf promote <plugin-root> \
  --verification-evidence evidence/verifications/extensions/<id>/dossier.json \
  --canary-contract ./canary-contract.json \
  --canary-baseline evidence/canary/extensions/<baseline-id>.json
```

Both canary flags are required together. Live promotion still performs M1.4 freshness first, then M1.5 replay. A failed replay adds `verification_behavior_canary_stale`.

When enabled, promoted release evidence includes:

```text
verification/canary-baseline.json
verification/canary-replay.json
```

Both remain outside `plugin.zip`.

### 16.9 Scope boundary

M1.5 proves only the declared read-only fixture contracts. It does not automatically exercise write/destructive tools, does not prove all authorization behavior, and does not claim exhaustive business-semantic equivalence.

## 17. MPF-M1.6 Authorization / Negative Contract Replay

Status: complete.

### 17.1 Goal

Verify that invalid, unauthorized, missing, and recoverable-error scenarios continue to fail in the expected way, so a release cannot be promoted merely because successful read-only behavior still works.

### 17.2 Negative contract categories

M1.6 supports four explicit categories:

- `invalid_input`
- `unauthorized`
- `not_found`
- `recoverable_error`

Every case declares a stable id, read-only tool, fixture arguments, request context, and expected failure contract.

Negative cases may expect only:

- `tool_error`
- `protocol_error`
- `http_error`

A negative case that returns success is always a blocker.

### 17.3 Contract template

Start from:

```text
templates/negative/contract.json
```

A case can constrain:

- protocol error code
- HTTP status
- whether `WWW-Authenticate` is required/optional/forbidden
- structured-content presence
- returned content types

### 17.4 Read-only safety gate

Before any `tools/call`, M1.6 requires the live descriptor to advertise:

```text
annotations.readOnlyHint = true
```

Tools that do not explicitly satisfy this condition are refused before invocation.

### 17.5 Authorization replay

`category=unauthorized` requires:

```text
request_context = anonymous
```

and is supported only for streamable-HTTP MCP servers.

The authorization replay flow is:

1. connect using the configured MCP authentication
2. discover/list tools and verify that the selected tool is explicitly read-only
3. construct a fresh HTTP client with the `Authorization` header omitted
4. send exactly one negative `tools/call`
5. observe only HTTP status and privacy-reduced challenge metadata

For 401 contracts, `WWW-Authenticate` is required by default. 401 and 403 are the supported authorization statuses.

M1.6 removes only the standard `Authorization` header. It does not claim to model arbitrary proprietary authentication headers or every OAuth scope/role combination.

### 17.6 Record baseline

```bash
mpf negative <plugin-root> \
  --contract ./negative-contract.json \
  --verification-evidence evidence/verifications/extensions/<id>/dossier.json \
  --write-evidence
```

Record mode executes the safe negative fixtures, validates the declared failure expectations, and writes:

```text
evidence/negative/extensions/<negative-id>.json
```

When a verification dossier is supplied, its verification ID and dossier SHA-256 are stored in the negative baseline.

### 17.7 Replay

```bash
mpf negative <plugin-root> \
  --contract ./negative-contract.json \
  --baseline evidence/negative/extensions/<baseline-id>.json \
  --verification-evidence evidence/verifications/extensions/<id>/dossier.json
```

Replay requires the contract SHA-256 to match the baseline. When verification binding is supplied, the baseline dossier SHA-256 must match the selected M1.2 dossier.

### 17.8 Privacy-reduced failure observation

M1.6 does not persist raw negative inputs or raw error bodies.

Per case it records only:

- argument SHA-256
- request context
- outcome class
- protocol error code
- HTTP status
- `WWW-Authenticate` presence
- SHA-256 of `WWW-Authenticate` when present
- returned content types
- recursive structured-content type/key shape
- overall behavior SHA-256

It does not persist bearer tokens, challenge text, HTTP bodies, tool-result values, protocol error messages, or tool-error text.

### 17.9 Drift semantics

Replay is verified only when:

- every tool passes the read-only safety gate
- every negative expectation still passes
- no negative case unexpectedly succeeds
- every case matches its recorded behavior SHA-256
- the contract still matches the baseline
- the verification binding still matches when present

Examples of drift include:

- protocol error code changes
- 401 becomes success
- required `WWW-Authenticate` disappears
- 401 changes to an unexpected status
- tool-error structured shape changes
- failure content types change

### 17.10 Promotion integration

Negative replay is opt-in because safe fixture design and authorization setup are product-specific.

```bash
mpf promote <plugin-root> \
  --verification-evidence evidence/verifications/extensions/<id>/dossier.json \
  --negative-contract ./negative-contract.json \
  --negative-baseline evidence/negative/extensions/<baseline-id>.json
```

Both flags are required together.

Live promotion ordering becomes:

1. M1.3 package/evidence gate
2. M1.4 remote MCP freshness
3. optional M1.5 positive behavioral replay
4. optional M1.6 negative/authorization replay
5. promotion verdict

A failed M1.6 replay adds `verification_negative_contract_stale`.

### 17.11 Promoted release evidence

When M1.6 promotion is enabled, the release evidence directory additionally contains:

```text
verification/negative-baseline.json
verification/negative-replay.json
```

These files remain outside `plugin.zip`.

### 17.12 Scope boundary

M1.6 validates only declared read-only negative fixtures and the anonymous/no-`Authorization` boundary for HTTP MCP tools. It does not automatically execute write/destructive tools, brute-force rate limits, test all account roles/scopes, or prove complete authorization correctness.

## 18. MPF-M1.7 Credential Matrix / Scope Boundary Replay

Status: complete.

### 18.1 Goal

Verify role/scope/account-state authorization boundaries across multiple credentials without storing access tokens or executing write/destructive tools.

M1.7 extends M1.6 from the anonymous/no-Authorization edge into an explicit matrix of credential profiles such as viewer, editor, admin, expired token, wrong audience, and missing scope.

### 18.2 Credential profiles

Credential contracts support exactly three profile kinds:

- `configured`: reuse the authorization configured for the MCP server in `mcp.json`
- `anonymous`: perform the canary call without `Authorization`
- `bearer_env`: obtain a bearer token from an environment variable at execution time

Raw token fields are not supported in contract JSON. Unknown profile fields are rejected.

For `bearer_env`, the environment variable name exists only in the input contract and in process memory. Executed evidence stores only the credential profile ID/kind and a SHA-256 of the complete credential-definition map; it does not persist environment variable names or token values.

### 18.3 Contract template

Start from:

```text
templates/credentials/matrix.json
```

Each case declares:

- stable case ID
- credential profile ID
- read-only MCP tool
- fixture arguments
- expected outcome: `success`, `tool_error`, `protocol_error`, or `http_error`
- optional HTTP status or protocol error code
- authentication-challenge requirement
- structured-content presence requirement
- expected content types
- optional stable paths within structured content

### 18.4 Execution model

M1.7 supports modern streamable-HTTP MCP only.

For every case it:

1. connects using the normally configured MCP credential
2. performs discovery/tool listing
3. verifies the target tool advertises `annotations.readOnlyHint=true`
4. creates the requested credential context
5. executes one `tools/call`
6. records a privacy-reduced observation

The descriptor inspection therefore does not depend on whether the credential under test is allowed to list tools.

### 18.5 Scope-boundary examples

A single matrix can express boundaries such as:

- anonymous → 401 + challenge
- viewer → normal read success
- viewer → admin-only read denied
- editor → read success
- admin → privileged read success
- expired token → 401 + challenge
- wrong audience → 401 + challenge
- missing scope → authorization failure

These are examples, not hard-coded roles. Product teams define the profile IDs and expected boundaries appropriate to their authorization model.

### 18.6 Record baseline

```bash
mpf credential-matrix <plugin-root> \
  --contract ./credential-matrix.json \
  --verification-evidence evidence/verifications/extensions/<id>/dossier.json \
  --write-evidence
```

Evidence is written under:

```text
evidence/credentials/extensions/<matrix-id>.json
```

When a verification dossier is supplied, the baseline stores its verification ID and dossier SHA-256.

### 18.7 Replay

```bash
mpf credential-matrix <plugin-root> \
  --contract ./credential-matrix.json \
  --baseline evidence/credentials/extensions/<baseline-id>.json \
  --verification-evidence evidence/verifications/extensions/<id>/dossier.json
```

Replay requires:

- identical contract SHA-256
- identical credential-definition SHA-256
- identical M1.2 dossier SHA-256 when verification binding is supplied
- each case expectation still passes
- each behavior SHA-256 still matches the baseline

### 18.8 Privacy-reduced observations

M1.7 evidence records:

- credential profile ID and kind
- argument SHA-256
- outcome class
- HTTP status
- protocol error code
- authentication-challenge presence/hash
- content types
- recursive structured-content type/key shape
- hashes of explicitly declared stable-path values
- overall behavior SHA-256

It does not persist access tokens, raw arguments, environment variable names, raw HTTP bodies, challenge text, tool-result values, or error messages.

### 18.9 Drift semantics

Examples of credential-boundary drift include:

- viewer changes from success to denial
- viewer unexpectedly gains admin-only access
- expired/wrong-audience token starts succeeding
- missing-scope response loses its challenge
- authorization status changes
- successful result shape changes
- declared stable-path values change

M1.7 reports these as case blockers and, during replay, `credential_boundary_drift`.

### 18.10 Promotion integration

Credential Matrix promotion is opt-in:

```bash
mpf promote <plugin-root> \
  --verification-evidence evidence/verifications/extensions/<id>/dossier.json \
  --credential-matrix ./credential-matrix.json \
  --credential-baseline evidence/credentials/extensions/<baseline-id>.json
```

Both flags are required together.

Live promotion ordering becomes:

1. M1.3 package/evidence gate
2. M1.4 advertised-surface freshness
3. optional M1.5 positive behavioral replay
4. optional M1.6 negative/authorization replay
5. optional M1.7 credential/scope matrix replay
6. promotion verdict

A failed replay adds `verification_credential_matrix_stale`.

### 18.11 Promoted release evidence

When M1.7 promotion is enabled, the release evidence directory additionally contains:

```text
verification/credential-matrix-baseline.json
verification/credential-matrix-replay.json
```

These files remain outside `plugin.zip`.

### 18.12 Scope boundary

M1.7 verifies only declared read-only HTTP fixtures and credential profiles. It does not automatically execute write/destructive tools, discover all real-world roles, enumerate every OAuth scope, or prove organization/workspace policy correctness.

## 19. MPF-M1.8 Least-Privilege / Security Scheme Contract Gate

Status: complete.

### 19.1 Goal

Compare live per-tool MCP `securitySchemes` with observed allow/deny scope evidence from a verified M1.7 credential matrix, and block release promotion when declarations request unnecessary scopes, omit an observed scope requirement, or advertise the wrong authentication mode.

### 19.2 Official contract alignment

M1.8 models per-tool declarations with the currently supported OpenAI/MCP security scheme types:

- `noauth`
- `oauth2` with an explicit scope list

Multiple schemes are treated as alternatives. A `noauth` plus `oauth2` declaration represents optional authentication.

The declaration is metadata only. Runtime authorization remains the MCP server's responsibility and is tested separately by M1.6/M1.7.

### 19.3 Security contract

Start from:

```text
templates/security/contract.json
```

The contract contains only public authorization-model metadata:

- profile IDs
- profile auth class: `anonymous` or `oauth`
- asserted OAuth scope labels
- per-tool access mode
- M1.7 sufficient-case IDs
- M1.7 insufficient-scope-case IDs

Supported access modes:

- `oauth_required`
- `optional_auth`
- `noauth`

### 19.4 Standalone CLI

```bash
mpf security-gate <plugin-root> \
  --contract ./security-contract.json \
  --matrix-evidence evidence/credentials/extensions/<matrix-id>.json \
  --write-evidence
```

The selected matrix evidence must be:

- `evidence_state=executed`
- `mode=replay`
- `matrix_verified=true`

M1.8 re-probes the live MCP server and reads current tool descriptors rather than trusting the historical matrix descriptor.

### 19.5 Access-mode checks

For each tool:

`oauth_required` requires at least one `oauth2` scheme and forbids `noauth`.

`optional_auth` requires both `noauth` and `oauth2`.

`noauth` requires `noauth` and rejects OAuth-only declaration in the M1.8 contract.

Unsupported/unknown security scheme types block the gate.

### 19.6 Sufficient-scope evidence

Each `sufficient_case` references a verified M1.7 case for the same tool.

The case must currently have a successful outcome.

For an OAuth-authenticated profile, at least one advertised OAuth alternative must be a subset of the profile's asserted scope set.

If a successful profile does not contain all scopes of any advertised OAuth alternative, M1.8 reports:

```text
declared_scope_not_supported_by_success
```

This detects a descriptor that requests more permission than the observed successful credential requires.

For an anonymous sufficient case, the access policy must allow anonymous access and the live descriptor must advertise `noauth`.

### 19.7 Insufficient-scope evidence

Each `insufficient_scope_case` must reference an OAuth profile that is intentionally denied because its OAuth scope set is insufficient.

If that denied profile already contains every scope of an advertised OAuth alternative, the runtime appears to require an undeclared permission or hidden scope.

M1.8 reports:

```text
runtime_requires_undeclared_permission
```

Role, organization, ownership, row-level policy, token expiry, wrong audience, and similar non-scope denials must not be used as insufficient-scope evidence.

### 19.8 Alternative-scheme support

Each advertised OAuth alternative must have at least one successful OAuth case whose asserted profile scopes contain that alternative.

An alternative with no supporting success evidence reports:

```text
declared_oauth_alternative_has_no_success_evidence
```

This prevents dead or gratuitously privileged OAuth alternatives from silently passing the gate.

### 19.9 Evidence

Default output:

```text
evidence/security/extensions/<gate-id>.json
```

Evidence includes:

- security contract SHA-256
- verified matrix ID/SHA-256
- live runtime smoke/fingerprint IDs
- normalized per-tool `securitySchemes`
- declared scope alternatives
- supporting sufficient cases
- insufficient-scope cases
- per-tool blocker reasons
- overall gate verdict

Scope names may be stored because they are permission labels. Tokens and credential environment-variable names are never persisted.

### 19.10 Promotion integration

M1.8 promotion is opt-in and depends on M1.7:

```bash
mpf promote <plugin-root> \
  --verification-evidence evidence/verifications/extensions/<id>/dossier.json \
  --credential-matrix ./credential-matrix.json \
  --credential-baseline evidence/credentials/extensions/<baseline-id>.json \
  --security-contract ./security-contract.json
```

Live promotion ordering becomes:

1. M1.3 package/evidence gate
2. M1.4 advertised-surface freshness
3. optional M1.5 positive behavioral replay
4. optional M1.6 negative/authorization replay
5. optional M1.7 credential/scope matrix replay
6. optional M1.8 least-privilege/security-scheme contract gate
7. promotion verdict

A failed M1.8 gate adds:

```text
verification_security_scheme_contract_failed
```

### 19.11 Promoted release evidence

When enabled, promoted evidence adds:

```text
verification/security-scheme-gate.json
```

The file remains outside `plugin.zip`.

### 19.12 Scope boundary

M1.8 checks evidence-backed OAuth declarations. It does not infer hidden business roles or claim that the mathematical intersection of successful credentials is the unique globally minimal permission set. Teams explicitly identify which denied M1.7 cases are scope-related.

## 20. Safety rules

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

## 21. Acceptance

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

### MPF-M0.9 acceptance

MPF-M0.9 is complete when:

- one command executes a real configured MCP process or modern HTTP endpoint
- modern stdio `server/discover` is supported
- legacy stdio initialization fallback is supported
- modern streamable HTTP probing is supported without storing auth material
- tool metadata and MCP App resources are inspected from runtime responses
- settings capability references are matched to actual tools
- entrypoints require readable MCP App resources
- host-only surfaces remain explicitly unverified
- executed evidence omits HTML bodies and credentials
- evidence output is contained and overwrite-safe
- CLI exit codes distinguish verified, host-required, missing, and execution-error states
- unit/CI tests use a live fixture MCP process and cover modern, legacy, missing metadata, host-required, evidence safety, server selection, and CLI behavior

### MPF-M1.0 acceptance

MPF-M1.0 is complete when:

- one command replays a normalized captured ChatGPT host trace
- executed M0.9 runtime evidence is a mandatory prerequisite for end-to-end verification
- deep links require valid ChatGPT host-context delivery
- Model-App Context requires a correlated request/response and host update ID
- rich forms require a correlated elicitation round trip
- valid decline/cancel outcomes prove form rendering without being treated as user approval
- unattested traces can exercise replay but cannot become end-to-end verified
- raw trace payloads and sensitive form/model-context values are not persisted
- trace and runtime evidence hashes bind the acceptance artifact to its sources
- evidence output stays inside the plugin root and is overwrite-safe
- CLI exit codes distinguish verified, unattested, incomplete, and invalid states
- unit/CI tests cover full acceptance, missing events, correlation failure, decline flow, deep-link validation, privacy, runtime provenance, automatic evidence selection, and CLI behavior

### MPF-M1.1 acceptance

MPF-M1.1 is complete when:

- one command normalizes supported raw/log formats into the M1.0 trace contract
- auto format selection supports JSON, JSONL/NDJSON, and already-normalized input
- request/response pairs preserve semantic direction and correlation
- source call IDs are canonicalized before persistence
- irrelevant records remain visible as skipped counts
- no relevant host events results in a hard normalization error
- deep-link, model-context, and form payloads are privacy-reduced before writing
- capture attestation cannot be set without executed-session attestation
- raw input is never copied into evidence
- output paths remain inside the plugin root and symlinks/overwrite conflicts fail closed
- written `trace.json` can feed M1.0 without manual restructuring
- unit/CI tests cover normalized input, JSON pairs, JSONL pairing, notifications, privacy, provenance, empty/irrelevant input, write safety, and CLI behavior

### MPF-M1.2 acceptance

MPF-M1.2 is complete when:

- one command executes M0.9 runtime verification and conditionally continues through M1.1 and M1.0
- runtime-only extension sets can complete without unnecessary host capture
- host-required extension sets stop at an explicit external-evidence wait when capture is absent
- supplied captures are normalized before host replay and raw input is never written to the dossier
- host replay is bound to the exact runtime result produced by the same run
- runtime failures, host evidence gaps, and unattested captures receive distinct states
- stage digests and artifact paths are recorded in one dossier
- next actions are explicit for every non-verified terminal state
- dossier writes are contained, idempotent, symlink-safe, and overwrite-guarded
- CLI exit codes distinguish verified, external-evidence wait, verification failure, and orchestrator error
- unit/CI tests cover runtime-only success, host wait, full host verification, unattested capture, missing host event, runtime metadata failure, privacy, write safety, and CLI behavior

### MPF-M1.3 acceptance

MPF-M1.3 is complete when:

- one command combines M0.5 release compilation with an M1.2 verification gate
- M1.2 verification IDs and dossiers are bound to the plugin package digest
- package drift after verification blocks promotion
- older dossiers without package binding are not silently accepted
- auto policy requires host verification only when host-required extensions exist
- explicit server and host verification policies are supported
- runtime/capture/trace/host artifact digests are revalidated before promotion
- M0.5 submission readiness remains distinct from MPF promotion readiness
- promoted release directories contain a self-contained privacy-reduced verification evidence copy
- verification artifacts never enter the plugin ZIP
- promotion writes remain overwrite-safe and contained inside the plugin root
- CLI exit codes distinguish promoted, verification-blocked, release-blocked, and invalid states
- unit/CI tests cover host/server policy, package drift, unattested host evidence, stage tampering, legacy dossier rejection, ZIP isolation, skills-only rejection, public report privacy, and CLI behavior

### MPF-M1.4 acceptance

MPF-M1.4 is complete when:

- M0.9 records deterministic protocol/tool/resource fingerprints
- raw resource content remains out of evidence while content drift remains detectable
- serverInfo-only changes do not create a freshness failure
- unchanged runtime surfaces pass a standalone freshness probe
- tool descriptor and UI resource content drift fail freshness even when package digest is unchanged
- baseline runtime artifacts remain dossier-hash bound before comparison
- CLI promotion automatically performs a live freshness check
- stale remote MCP surfaces block promotion without changing M0.5 submission readiness semantics
- promoted release evidence includes the freshness report outside the plugin ZIP
- freshness evidence writes are contained and overwrite-safe
- unit/CI tests cover fresh, tool drift, resource drift, serverInfo exclusion, baseline tamper, standalone CLI, and live promotion blocking

### MPF-M1.5 acceptance

MPF-M1.5 is complete when:

- one command records a behavioral baseline and one command replays it
- only explicitly read-only tools can reach `tools/call`
- representative success, tool-error, and protocol-error contracts are supported
- raw canary arguments and raw tool results never enter evidence
- structured-content shape and declared stable-path values are comparable across runs
- contract drift invalidates an old baseline
- canary baselines can be SHA-bound to the exact M1.2 verification dossier
- M1.4 metadata freshness can remain green while M1.5 detects handler-only behavior drift
- live promotion optionally requires both M1.4 freshness and M1.5 canary verification
- canary baseline/replay evidence remains outside the plugin ZIP
- unit/CI tests prove pre-call refusal of non-read-only tools, unchanged replay, stable-value drift, shape drift, privacy, contract drift, CLI behavior, and promotion blocking

### MPF-M1.6 acceptance

MPF-M1.6 is complete when:

- one command records negative contract evidence and one command replays it
- invalid-input, unauthorized, not-found, and recoverable-error categories are modeled explicitly
- a negative case that unexpectedly succeeds always fails the gate
- only explicitly read-only tools can reach `tools/call`
- anonymous authorization replay strips `Authorization` only after authenticated descriptor inspection
- 401 contracts can require `WWW-Authenticate`
- raw arguments, tokens, error bodies, result text, and challenge text never enter evidence
- contract drift invalidates an old baseline
- negative baselines can be SHA-bound to the exact M1.2 verification dossier
- M1.4 advertised-surface freshness can remain green while M1.6 detects failure-contract drift
- live promotion can optionally require M1.6 replay
- negative baseline/replay evidence remains outside the plugin ZIP
- unit/CI tests cover invalid/not-found/recoverable failures, unexpected success, unsafe-tool pre-call refusal, 401 challenge behavior, privacy, verification binding, CLI record/replay, promotion blocking, and promoted evidence isolation

### MPF-M1.7 acceptance

MPF-M1.7 is complete when:

- one command records a credential/scope matrix and one command replays it
- configured, anonymous, and bearer-env profiles are supported without raw-token contract fields
- bearer-env values are loaded only at execution time
- executed evidence omits token values and credential environment-variable names
- only explicitly read-only streamable-HTTP tools can reach `tools/call`
- allow and deny expectations are expressible for the same tool across multiple profiles
- success, tool-error, protocol-error, and HTTP-error outcomes are supported
- 401/403 and authentication-challenge behavior can be asserted
- contract/profile drift invalidates an old baseline
- credential baselines can be SHA-bound to the exact M1.2 verification dossier
- role/scope drift is detected even when M1.4 advertised metadata remains unchanged
- live promotion can optionally require the M1.7 matrix
- credential baseline/replay evidence remains outside the plugin ZIP
- unit/CI tests cover viewer/editor/admin/anonymous/expired/wrong-audience/missing-scope boundaries, drift, privacy, raw-secret rejection, verification binding, unsafe-tool pre-call refusal, and CLI record/replay

### MPF-M1.8 acceptance

MPF-M1.8 is complete when:

- one command compares a verified M1.7 matrix with live per-tool security schemes
- noauth, oauth-required, and optional-auth declarations are modeled explicitly
- successful OAuth cases prove advertised scope alternatives are not over-declared
- intentionally insufficient-scope cases detect hidden/undeclared runtime permission requirements
- every advertised OAuth alternative requires positive success evidence
- anonymous success is validated against noauth declaration rather than OAuth scope inference
- role/policy denials are kept separate from scope-insufficiency evidence
- unsupported security scheme types fail closed
- the gate re-probes live descriptors instead of trusting historical declarations
- promotion can optionally require M1.8 after M1.7
- security-scheme evidence remains outside the plugin ZIP
- unit/CI tests cover valid least privilege, over-declaration, undeclared permission requirements, auth-mode mismatch, optional-auth alternatives, unverified matrices, CLI evidence writes, promotion blocking, and release-evidence isolation

## 22. North star

```text
"I have a useful Skill"
        ->
"I have the exact package and an auditable release dossier
that says what was generated, what was reviewed,
what actually ran, and exactly what still blocks submission."
```

MADO Plugin Factory is a **release-confidence compiler**.
