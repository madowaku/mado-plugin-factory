# MADO Plugin Factory

MADO Plugin Factory turns reusable Skills and MCP-backed workflows into reviewable, install-verifiable OpenAI plugin release artifacts.

## Pipeline

```text
Skill / Repo
  -> MPF-M0.1 Candidate Scanner
  -> MPF-M0.2 Manifest Compiler
  -> MPF-M0.3 Submission Eval Compiler
  -> MPF-M0.4 Local Marketplace Bridge
  -> MPF-M0.5 Submission Evidence Bundle
  -> MPF-M0.6 Extension Capability Compiler
  -> MPF-M0.7 Extension Scaffold Generator
  -> MPF-M0.8 Extension Apply / Patch Engine
  -> MPF-M0.9 Extension Runtime Smoke / Evidence
  -> MPF-M1.0 ChatGPT Host Replay / Extension Acceptance
  -> MPF-M1.1 Host Trace Capture / Normalizer
  -> MPF-M1.2 Extension Verification Orchestrator
  -> MPF-M1.3 Verification Promotion Gate / Release Bundle Bridge
  -> MPF-M1.4 Verification Freshness / Remote MCP Drift Gate
  -> MPF-M1.5 Behavioral Contract Replay / Remote MCP Canary
  -> MPF-M1.6 Authorization / Negative Contract Replay
```

## Status

- **MPF-M0.0 Skeleton** ✅
- **MPF-M0.1 Candidate Scanner** ✅
- **MPF-M0.2 Manifest Compiler** ✅
- **MPF-M0.3 Submission Eval Compiler** ✅
- **MPF-M0.4 Local Marketplace Bridge** ✅
- **MPF-M0.5 Submission Evidence Bundle** ✅
- **MPF-M0.6 Extension Capability Compiler** ✅
- **MPF-M0.7 Extension Scaffold Generator** ✅
- **MPF-M0.8 Extension Apply / Patch Engine** ✅
- **MPF-M0.9 Extension Runtime Smoke / Evidence** ✅
- **MPF-M1.0 ChatGPT Host Replay / Extension Acceptance** ✅
- **MPF-M1.1 Host Trace Capture / Normalizer** ✅
- **MPF-M1.2 Extension Verification Orchestrator** ✅
- **MPF-M1.3 Verification Promotion Gate / Release Bundle Bridge** ✅
- **MPF-M1.4 Verification Freshness / Remote MCP Drift Gate** ✅
- **MPF-M1.5 Behavioral Contract Replay / Remote MCP Canary** ✅
- **MPF-M1.6 Authorization / Negative Contract Replay** ✅

Current package version: `1.6.0`.

## M0.1 Candidate Scanner

```bash
mpf scan /path/to/plugin --pretty
```

Read-only static inspection of Skills, MCP surfaces, dependencies, risk flags, and missing packaging requirements.

Generated `evidence/` is excluded from candidate scans so evidence creation cannot change the source scan result.

## M0.2 Manifest Compiler

```bash
mpf manifest /path/to/plugin \
  --metadata ./manifest-metadata.json \
  --write
```

Compiles canonical portable `plugin.json`, validates OpenAI interface metadata, and can optionally emit a compatibility `.codex-plugin/plugin.json`.

## M0.3 Submission Eval Compiler

```bash
mpf evals /path/to/plugin \
  --metadata ./eval-metadata.json \
  --write
```

Compiles exactly five positive and three negative review cases. Generated cases stay:

```json
{
  "evidence_state": "generated",
  "review_required": true
}
```

Default evidence path:

```text
evidence/evals/test-cases.json
```

## M0.4 Local Marketplace Bridge

Stage a curated plugin package and write a local marketplace:

```bash
mpf marketplace bridge /path/to/plugin \
  --root /path/to/marketplace-root \
  --write
```

After installing from ChatGPT desktop, verify the actual cache copy:

```bash
mpf marketplace verify /path/to/plugin \
  --root /path/to/marketplace-root \
  --write-evidence
```

Successful verification records:

```json
{
  "evidence_state": "executed",
  "install_verified": true
}
```

Default install evidence:

```text
evidence/marketplace/install-verification.json
```

## M0.5 Submission Evidence Bundle

M0.5 aggregates the whole release trail and creates a deterministic plugin ZIP.

Start from the template:

```text
templates/release/submission.json
```

Dry-run:

```bash
mpf bundle /path/to/plugin \
  --release-metadata ./release.json \
  --pretty
```

Write the versioned bundle:

```bash
mpf bundle /path/to/plugin \
  --release-metadata ./release.json \
  --write
```

Default output:

```text
evidence/releases/<plugin-version>/
  bundle.json
  scanner.json
  manifest-validation.json
  evals.json
  install-verification.json
  release-metadata.json
  plugin.zip
  plugin.zip.sha256
```

### Plugin ZIP vs evidence

`plugin.zip` contains only curated distributable plugin surfaces:

- `plugin.json`
- `skills/**`
- optional `mcp.json`
- optional `.mcp.json`
- optional `.app.json`
- optional `hooks/**`
- optional `assets/**`
- optional compatibility `.codex-plugin/plugin.json`

It does **not** include repo docs, tests, or `evidence/**`.

The surrounding release directory carries the audit trail.

### Deterministic ZIP

The ZIP uses:

- sorted curated package paths
- fixed ZIP timestamps
- fixed file permissions
- deterministic compression settings

The bundle also writes:

```text
plugin.zip.sha256
```

so the upload artifact can be identified exactly.

### Two readiness levels

M0.5 deliberately separates:

#### `upload_ready`

Local release preparation is complete:

- manifest validates
- 5/3 eval evidence exists
- eval cases were explicitly reviewed
- final Skill tree was explicitly tested
- listing was reviewed
- local install verification succeeded
- availability is present
- release notes are present

#### `submission_ready`

Everything above plus final publishing/portal prerequisites are explicitly attested:

- realistic starter prompts
- final listing copy/category/logo
- public HTTPS website/support/privacy/terms URLs
- Apps Management write access
- verified publisher identity
- policy attestations complete
- bundled Skill safety scan passed

For MCP submissions, M0.5 additionally requires:

- production HTTPS MCP URL
- demo recording URL
- domain verification
- current tool scan
- reviewed tool annotations
- reviewer-access setup ready

The compiler does not fabricate these states. Every boolean defaults to false.

### Release metadata is not a secrets file

M0.5 accepts release state and attestations only. Do not put passwords, tokens, API keys, or reviewer credentials into release metadata.

Secret-bearing field names are rejected.

### Exit codes

`mpf bundle` returns:

- `0`: submission-ready
- `3`: upload-ready, but final submission blockers remain
- `2`: local/upload blockers remain
- `1`: invalid input or compiler error

### Write safety

Bundle generation is dry-run unless `--write` is supplied.

Existing differing bundle files require `--force`.

The output directory must stay inside the plugin root.

## M0.6 Extension Capability Compiler

M0.6 inspects a plugin for current OpenAI MCP Extension surfaces without claiming runtime success from static code.

Dry-run:

```bash
mpf extensions /path/to/plugin --pretty
```

Write inspected evidence:

```bash
mpf extensions /path/to/plugin --write
```

Default output:

```text
evidence/extensions/capabilities.json
```

Each extension is classified as:

- `detected`: static implementation markers are present
- `eligible`: prerequisites are present and the surface can be added
- `needs_input`: implementation is plausible but product-specific input is missing
- `blocked`: a required MCP, MCP App UI, or packaged Skill prerequisite is missing

The compiler covers sidebar apps, conversation panels, plugin settings, file viewers/editors, display modes, deep links, Model-App Context, composer mentions, rich forms, and plugin onboarding. It also preserves and validates `extensions.com.openai.onboardingSkill` during manifest compilation.

Static detection remains `inspected` evidence with `runtime_verified: false` until a later execution stage proves the feature in ChatGPT.

## M0.7 Extension Scaffold Generator

M0.7 turns the M0.6 capability report into a deterministic, reviewable scaffold pack. It does not inject generated code into the active runtime.

Dry-run all actionable extensions:

```bash
mpf scaffold /path/to/plugin --pretty
```

Select specific surfaces and provide file-handler input:

```bash
mpf scaffold /path/to/plugin \\
  --extension sidebar_app \\
  --extension file_viewer_editor \\
  --file-extension .stl \\
  --write
```

Default output:

```text
evidence/scaffolds/extensions/
  plan.json
  README.md
  apply/
    extensions/openai/*.ts
    skills/plugin-onboarding/SKILL.md
    manifest.patch.json
```

The `apply/` tree is a proposal mirror, not an active package tree. M0.7 skips detected capabilities, refuses blocked capabilities, and keeps missing product inputs explicit. Existing differing scaffold files require `--force`.

## M0.8 Extension Apply / Patch Engine

M0.8 promotes an M0.7 proposal pack into active plugin source with an inspect-first patch plan, hash preconditions, conflict detection, and post-apply M0.6 verification.

Inspect without changing source:

```bash
mpf patch /path/to/plugin --pretty
```

Apply after reviewing the plan:

```bash
mpf patch /path/to/plugin --apply --pretty
```

Differing generated source files require explicit `--force`. Semantic manifest conflicts are never force-overwritten.

Successful apply writes executed evidence under:

```text
evidence/patches/extensions/<patch-id>.json
```

M0.8 distinguishes **source applied** from **runtime verified**. It re-runs M0.6 and requires promoted extension markers to become statically `detected`, while keeping `runtime_verified: false` until a later ChatGPT execution stage proves behavior.

## M0.9 Extension Runtime Smoke / Evidence

M0.9 executes the configured MCP server and collects runtime evidence from the protocol itself.

```bash
mpf runtime-smoke /path/to/plugin --pretty
```

Persist the executed evidence:

```bash
mpf runtime-smoke /path/to/plugin --write-evidence --pretty
```

For stdio servers, `auto` first probes the modern MCP `2026-07-28` `server/discover` flow and falls back to the legacy initialize flow when needed. Streamable HTTP smoke uses the modern stateless protocol.

The smoke checks direct protocol evidence for sidebar/thread/file entrypoints, structured settings, composer mentions, and display-mode resource metadata. It also reads advertised MCP App resources and verifies `text/html;profile=mcp-app` where entrypoints require an app resource.

Deep links, Model-App Context, and rich-form behavior need ChatGPT host or MCP App interaction, so M0.9 records them as `host_required` instead of inventing success.

Exit codes:

- `0`: directly probeable extension runtime verified
- `3`: MCP server smoke passed, but host-only extension verification remains
- `2`: expected runtime metadata is missing
- `1`: runtime/configuration error

Default evidence path:

```text
evidence/runtime/extensions/<server>-<smoke-id>.json
```

## M1.0 ChatGPT Host Replay / Extension Acceptance

M1.0 closes the host-only gap left by M0.9. It replays a normalized trace captured from an executed ChatGPT developer-mode, installed-plugin, or API Playground session and combines that trace with successful M0.9 runtime evidence.

Start from:

```text
templates/host-replay/trace.json
```

The template is deliberately unattested. Replace the normalized events with observations from the real ChatGPT session, then set `capture.executed` and `capture.attested_chatgpt_capture` only when that capture actually occurred.

Replay without writing evidence:

```bash
mpf host-replay /path/to/plugin \\
  --trace ./chatgpt-host-trace.json \\
  --runtime-evidence evidence/runtime/extensions/<runtime>.json \\
  --pretty
```

Persist acceptance evidence:

```bash
mpf host-replay /path/to/plugin \\
  --trace ./chatgpt-host-trace.json \\
  --runtime-evidence evidence/runtime/extensions/<runtime>.json \\
  --write-evidence \\
  --pretty
```

M1.0 verifies the three host-required surfaces from M0.9:

- Deep links: ChatGPT supplies a valid `openai/deepLink` host-context path during UI initialization or a host-context change notification.
- Model-App Context: an app `ui/update-model-context` request has a correlated host response containing an `openai/modelContext.updateId`.
- Rich forms: an elicitation request has a correlated ChatGPT response with `accept`, `decline`, or `cancel`.

The acceptance artifact stores the trace SHA-256, capture metadata, correlation evidence, and verdicts. It does **not** copy model-context text, form content, deep-link path text, raw host logs, or credentials.

`end_to_end_verified=true` requires all of the following: successful M0.9 `runtime_smoke_passed`, at least one host-required extension, complete replay evidence for every expected host-required extension, and an explicit attestation that the trace came from an executed ChatGPT capture.

Exit codes:

- `0`: end-to-end host acceptance verified
- `3`: replay shape passes but ChatGPT capture is unattested
- `2`: expected host acceptance evidence is incomplete
- `1`: trace/runtime evidence error

Default output:

```text
evidence/host/extensions/<acceptance-id>.json
```

## M1.1 Host Trace Capture / Normalizer

M1.1 converts observed ChatGPT/API Playground logs into the privacy-reduced trace contract consumed by M1.0.

```bash
mpf host-capture /path/to/plugin \\
  --input ./raw-host-log.json \\
  --surface web \\
  --mode developer_mode \\
  --executed \\
  --attest-chatgpt-capture \\
  --write \\
  --pretty
```

Supported adapters are `auto`, `json`, `jsonl`, and `normalized`. Generic JSON adapters understand direct normalized events, arrays/record containers, JSON-RPC request/response pairs, and sequential JSON-RPC request/response records.

M1.1 canonicalizes call IDs and removes sensitive values before writing the normalized trace. Deep-link paths become hash-bearing redacted paths; Model-App Context text/structured content is replaced with shape-only placeholders; update IDs are hashed; form messages, schemas, and submitted content are reduced to the minimum shape needed by M1.0.

Default output:

```text
evidence/host/captures/<capture-id>/
  trace.json
  capture.json
```

`trace.json` is the M1.0 input. `capture.json` records the source SHA-256, adapter, record/event counts, redaction counts, capture provenance flags, and warnings. The raw input is never copied into evidence.

Capture provenance is explicit. `--attest-chatgpt-capture` is rejected unless `--executed` is also supplied. M1.1 normalization success does not itself grant end-to-end verification; M1.0 remains the acceptance gate.

## M1.2 Extension Verification Orchestrator

M1.2 binds M0.9 runtime smoke, M1.1 host capture normalization, and M1.0 host replay into one verification run and one auditable dossier.

Runtime-only verification:

```bash
mpf verify-extensions /path/to/plugin --write --pretty
```

When M0.9 reports host-required extensions, the same command stops cleanly at `awaiting_host_capture` and records the exact next action instead of treating missing external evidence as a runtime failure.

Provide a real ChatGPT capture to close the host stage:

```bash
mpf verify-extensions /path/to/plugin \\
  --capture ./raw-host-log.json \\
  --surface web \\
  --capture-mode developer_mode \\
  --executed \\
  --attest-chatgpt-capture \\
  --write \\
  --pretty
```

The orchestrator distinguishes implementation/runtime failures from external-evidence waits with states such as:

- `verified_mcp_server`
- `awaiting_host_capture`
- `verified_chatgpt_host`
- `awaiting_capture_attestation`
- `host_incomplete`
- `runtime_failed`

Default output:

```text
evidence/verifications/extensions/<verification-id>/
  dossier.json
  runtime.json
  capture.json     # when a capture was supplied
  trace.json       # privacy-reduced normalized trace
  host.json        # when host replay ran
```

`dossier.json` contains stage digests, verdicts, missing extensions, stage errors, and next actions. It never copies the raw host log. A runtime-only plugin can complete at MCP-server scope; plugins with host-required extensions only become fully verified after M1.0 accepts an attested ChatGPT capture.

Exit codes:

- `0`: verification complete and verified
- `3`: external ChatGPT capture or capture attestation still needed
- `2`: runtime/host verification failed or remains incomplete
- `1`: orchestrator input/write error

## M1.3 Verification Promotion Gate / Release Bundle Bridge

M1.3 promotes an M1.2 verification dossier into the M0.5-style release dossier only when the verification is still bound to the exact current plugin package.

```bash
mpf promote /path/to/plugin \\
  --release-metadata ./release.json \\
  --verification-evidence evidence/verifications/extensions/<verification-id>/dossier.json \\
  --write \\
  --pretty
```

Verification policy can be selected explicitly:

```bash
--requirement auto|mcp_server|chatgpt_host
```

`auto` requires ChatGPT-host verification whenever the dossier contains host-required extensions; otherwise MCP-server verification is sufficient. A fully host-verified run also satisfies an explicit `mcp_server` policy.

M1.2 now records the plugin package digest in its dossier and includes that digest in the verification ID. M1.3 recomputes the current package digest and refuses promotion when the package changed after verification. Dossiers created before this binding field existed are visible but not promotable.

M1.3 also recomputes the SHA-256 of the runtime/capture/trace/host stage JSON and compares it with the digests recorded by the dossier. A dossier whose stage artifacts were edited after verification is blocked.

Promotion is an MPF quality gate, not an additional OpenAI submission requirement. The existing M0.5 `submission_ready` verdict remains intact; M1.3 adds a separate `promotion_ready` verdict so official portal readiness and MPF verification policy do not get conflated.

A promoted release directory contains the normal deterministic release bundle plus:

```text
evidence/releases/<version>/
  promotion.json
  verification/
    dossier.json
    runtime.json
    capture.json    # when applicable
    trace.json      # when applicable
    host.json       # when applicable
```

None of these verification artifacts are placed inside `plugin.zip`.

Exit codes:

- `0`: release and verification gate are promotion-ready
- `3`: normal submission material is ready but the M1.3 verification gate is not
- `2`: underlying release submission material is not ready
- `1`: promotion input/validation/write error

## M1.4 Verification Freshness / Remote MCP Drift Gate

M1.4 detects MCP server drift that package hashing cannot see. M0.9 now records a privacy-safe `runtime_fingerprint` over the negotiated protocol, advertised capabilities, tool descriptors, and referenced MCP App resource digests.

Standalone freshness check:

```bash
mpf freshness /path/to/plugin \\
  --verification-evidence evidence/verifications/extensions/<verification-id>/dossier.json \\
  --pretty
```

The fingerprint includes tool names/descriptions/schemas/annotations/security metadata, OpenAI/UI extension metadata, and SHA-256 digests of referenced resource content. Raw UI HTML is still not persisted. `serverInfo` is intentionally excluded from the drift verdict because it is self-reported metadata.

`mpf promote` now performs this live re-probe automatically before promotion. If the current advertised MCP surface differs from the runtime snapshot used by M1.2, promotion is blocked with `verification_freshness_stale`, even when the plugin package digest itself is unchanged.

Freshness evidence can also be persisted under:

```text
evidence/freshness/extensions/<freshness-id>.json
```

The drift report identifies changed fingerprint components plus added/removed tool names and resource URIs. Its scope is deliberately `advertised_mcp_surface`: it detects metadata/resource drift, but does not claim unchanged business behavior or authorization enforcement.

## M1.5 Behavioral Contract Replay / Remote MCP Canary

M1.5 executes explicit, deterministic **read-only** MCP canaries so a server can fail promotion even when its advertised metadata is unchanged.

Start from:

```text
templates/canary/contract.json
```

Record a behavioral baseline:

```bash
mpf canary /path/to/plugin \
  --contract ./canary-contract.json \
  --verification-evidence evidence/verifications/extensions/<verification-id>/dossier.json \
  --write-evidence \
  --pretty
```

Replay it later:

```bash
mpf canary /path/to/plugin \
  --contract ./canary-contract.json \
  --baseline evidence/canary/extensions/<canary-id>.json \
  --verification-evidence evidence/verifications/extensions/<verification-id>/dossier.json \
  --pretty
```

Only tools that explicitly advertise `annotations.readOnlyHint=true` are callable. M1.5 refuses every other tool **before** sending `tools/call`.

Canary contracts declare representative fixture inputs and expectations for success/tool-error/protocol-error behavior. Evidence never stores raw arguments or raw tool results. It stores:

- argument SHA-256
- success/tool-error/protocol-error class
- protocol error code
- returned content types
- structuredContent type/shape
- SHA-256 values for explicitly declared `stable_paths`

A baseline may be bound to a verified M1.2 dossier. Promotion requires that binding when a behavioral canary is enabled, so a baseline from another verification run cannot be reused accidentally.

Behavioral promotion is opt-in because safe deterministic fixture calls are product-specific:

```bash
mpf promote /path/to/plugin \
  --release-metadata ./release.json \
  --verification-evidence evidence/verifications/extensions/<verification-id>/dossier.json \
  --canary-contract ./canary-contract.json \
  --canary-baseline evidence/canary/extensions/<baseline-id>.json \
  --write
```

Promotion then requires both M1.4 runtime freshness and M1.5 behavioral replay. A handler-only change that leaves tool descriptors and UI resources identical can therefore produce `verification_behavior_canary_stale`.

The M1.5 scope is deliberately `read_only_behavior_contract`. It does not auto-execute write/destructive tools and does not claim exhaustive authorization or business-semantic coverage.

## M1.6 Authorization / Negative Contract Replay

M1.6 verifies that supported failures remain failures. It records and replays explicit read-only negative contracts for:

- `invalid_input`
- `unauthorized`
- `not_found`
- `recoverable_error`

Start from:

```text
templates/negative/contract.json
```

Record a negative baseline:

```bash
mpf negative /path/to/plugin \
  --contract ./negative-contract.json \
  --verification-evidence evidence/verifications/extensions/<verification-id>/dossier.json \
  --write-evidence \
  --pretty
```

Replay it later:

```bash
mpf negative /path/to/plugin \
  --contract ./negative-contract.json \
  --baseline evidence/negative/extensions/<negative-id>.json \
  --verification-evidence evidence/verifications/extensions/<verification-id>/dossier.json \
  --pretty
```

Negative cases must expect `tool_error`, `protocol_error`, or `http_error`. If a negative case unexpectedly succeeds, the run fails even if the returned shape is otherwise stable.

Like M1.5, M1.6 refuses any tool without `annotations.readOnlyHint=true` before sending `tools/call`.

For authorization replay, `category=unauthorized` uses `request_context=anonymous` and is supported only for streamable-HTTP MCP servers. MPF first uses the configured authenticated connection to inspect the live tool descriptor, then performs one tool call with the `Authorization` header omitted. A 401 contract requires `WWW-Authenticate` by default.

Evidence stores only:

- argument SHA-256
- failure outcome class
- protocol error code
- HTTP status
- whether `WWW-Authenticate` was present
- SHA-256 of the challenge header when present
- content types
- privacy-reduced structured-content shape

Raw arguments, access tokens, HTTP bodies, challenge text, tool-result values, and error messages are not persisted.

Negative baselines may be SHA-bound to an M1.2 verification dossier. Promotion can then require the exact same verification binding:

```bash
mpf promote /path/to/plugin \
  --release-metadata ./release.json \
  --verification-evidence evidence/verifications/extensions/<verification-id>/dossier.json \
  --negative-contract ./negative-contract.json \
  --negative-baseline evidence/negative/extensions/<baseline-id>.json \
  --write
```

When enabled, M1.6 runs after the M1.4 freshness gate. A changed error code, missing auth challenge, unexpected success, or other negative-contract drift adds `verification_negative_contract_stale`.

Promoted release evidence includes `verification/negative-baseline.json` and `verification/negative-replay.json`, both outside `plugin.zip`.

M1.6 deliberately does not auto-execute write/destructive tools or exhaustively test every OAuth scope/role combination. Its authorization replay covers the anonymous/no-Authorization boundary for explicitly read-only HTTP tools.

## Evidence states

The factory uses only:

- `generated`
- `inspected`
- `executed`

A stronger evidence state is never claimed without corresponding proof or explicit review attestation.

## Tests

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

Coverage includes the full M0.1-M1.6 pipeline, including deterministic ZIP generation, bundle overwrite safety, MCP-specific submission blockers, local install evidence, path containment, and secret-bearing metadata rejection.

## Source of truth

Implementation tracks current OpenAI plugin documentation:

- https://developers.openai.com/plugins/build/plugins
- https://developers.openai.com/plugins/build/skills
- https://developers.openai.com/plugins/deploy/submission
- https://developers.openai.com/plugins/deploy/submission-errors
- https://developers.openai.com/plugins/build/extensions
- https://github.com/openai/mcp-extensions/blob/main/docs/spec.md

## Design rule

The product is not a plugin generator.

It is a **release-confidence compiler**:

```text
"I have a useful Skill"
        ->
"I have the exact ZIP, review cases, local-install proof,
release metadata, blockers, and evidence trail needed
to explain what is ready and what is not."
```
