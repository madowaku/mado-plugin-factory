# MADO Plugin Factory

MADO Plugin Factory turns reusable Skills and MCP-backed workflows into submission-ready OpenAI plugins for ChatGPT and Codex.

## Goal

```text
Skill / Repo
  -> Candidate Scan
  -> Manifest Compile
  -> Submission Eval Compile
  -> Local Marketplace Bridge
  -> Submission Evidence Bundle
```

## Current status

- **MPF-M0.0 Skeleton** ✅
- **MPF-M0.1 Candidate Scanner** ✅
- **MPF-M0.2 Manifest Compiler** ✅
- **MPF-M0.3 Submission Eval Compiler** ✅
- **MPF-M0.4 Local Marketplace Bridge** ✅
- MPF-M0.5 Submission Evidence Bundle\n\nCurrent package version: `0.4.0`.

## M0.1 Candidate Scanner

```bash
mpf scan /path/to/candidate --pretty
```

The scanner is read-only. It classifies the candidate, inventories Skills/MCP/dependencies, and emits risk flags with evidence paths.

## M0.2 Manifest Compiler

```bash
mpf manifest /path/to/candidate \
  --metadata ./manifest-metadata.json \
  --write
```

The portable root `plugin.json` is canonical. Compilation is dry-run by default and differing output requires `--force`.

## M0.3 Submission Eval Compiler

```bash
mpf evals /path/to/candidate \
  --metadata ./eval-metadata.json \
  --write
```

It compiles exactly five positive and three negative reviewer drafts. Generated cases stay `review_required: true` and `evidence_state: generated`.

## M0.4 Local Marketplace Bridge

M0.4 turns a validated plugin package into a repo marketplace entry that ChatGPT desktop / Codex can discover.

Dry-run:

```bash
mpf marketplace bridge /path/to/plugin \
  --root /path/to/marketplace-root \
  --pretty
```

Write the bridge:

```bash
mpf marketplace bridge /path/to/plugin \
  --root /path/to/marketplace-root \
  --write
```

The bridge stages only distributable plugin files into:

```text
<marketplace-root>/
  .agents/plugins/marketplace.json
  plugins/
    <plugin-name>/
      plugin.json
      skills/
      mcp.json              # optional
      .mcp.json             # optional compatibility
      .app.json             # optional
      hooks/                # optional
      assets/               # optional
      .codex-plugin/
        plugin.json         # optional compatibility
```

The marketplace entry points at:

```text
./plugins/<plugin-name>
```

Paths must remain relative to the marketplace root.

The bridge preserves unrelated existing plugin entries in the same catalog. A differing staged plugin or marketplace catalog is not replaced unless `--force` is explicit.

### Install verification

Writing the catalog is **not** treated as proof that ChatGPT installed the plugin.

After restarting ChatGPT desktop and installing from the local marketplace, verify the actual installed cache copy:

```bash
mpf marketplace verify /path/to/plugin \
  --root /path/to/marketplace-root \
  --pretty
```

By default, M0.4 checks:

```text
~/.codex/plugins/cache/<marketplace-name>/<plugin-name>/local/
```

The verifier checks:

- marketplace catalog validity
- expected plugin entry
- staged package presence
- installed cache directory
- installed `plugin.json`
- plugin identity
- SHA-256 package digest equality between staged and installed copies

Only an exact cache match returns:

```json
{
  "evidence_state": "executed",
  "install_verified": true,
  "blocking_reasons": []
}
```

A missing cache, invalid installed manifest, or stale installed copy is also recorded as executed evidence, but `install_verified` remains false.

Persist the verification:

```bash
mpf marketplace verify /path/to/plugin \
  --root /path/to/marketplace-root \
  --write-evidence
```

Default evidence path:

```text
evidence/marketplace/install-verification.json
```

The evidence output cannot escape the plugin root.

### Why the cache check matters

For local marketplace plugins, ChatGPT installs a copy under `~/.codex/plugins/cache/` and loads that installed copy rather than the marketplace source directory directly. M0.4 therefore verifies the cache copy instead of assuming catalog visibility equals successful installation.

## Evidence discipline

The factory uses:

- `generated`
- `inspected`
- `executed`

A stronger evidence state is never claimed without corresponding proof.

## Tests

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

Coverage includes:

- candidate architecture scanning
- portable/compatibility manifest compilation
- 5/3 submission eval generation
- marketplace catalog generation
- package staging filters
- existing-catalog merge
- overwrite protection
- missing-cache verification
- exact installed-cache verification
- stale-cache detection
- evidence path containment
- CLI dry-run behavior

## Source of truth

Implementation tracks:

- https://developers.openai.com/plugins/build/plugins
- https://developers.openai.com/plugins/build/skills
- https://developers.openai.com/plugins/deploy/submission
- https://developers.openai.com/plugins/deploy/submission-errors

## Design rule

Do not optimize first for "publishing a plugin."

Optimize for a deterministic transformation from a known-good Skill into a reviewable, testable, install-verifiable plugin artifact.

The product is a **release-confidence compiler**.
