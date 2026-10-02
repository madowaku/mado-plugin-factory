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

Current package version: `1.1.0`.

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

Coverage includes the full M0.1-M1.1 pipeline, including deterministic ZIP generation, bundle overwrite safety, MCP-specific submission blockers, local install evidence, path containment, and secret-bearing metadata rejection.

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
