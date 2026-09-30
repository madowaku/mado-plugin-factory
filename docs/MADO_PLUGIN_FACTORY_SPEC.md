# MADO_PLUGIN_FACTORY_SPEC.md v0.4

Status: Implementing  
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
Submission Evidence Bundle       <- M0.5
```

## 2. Evidence states

Every claim belongs to one of:

- `generated`
- `inspected`
- `executed`

Writing a marketplace catalog does not prove installation. Install verification requires observing the installed cache copy.

## 3. M0.1 Candidate Scanner

Status: complete.

Outputs architecture, Skills, MCP surfaces, dependencies, risks, and missing requirements without mutating the source candidate.

## 4. M0.2 Manifest Compiler

Status: complete.

Compiles canonical portable `plugin.json`, validates OpenAI interface metadata, and can emit an optional Codex compatibility mirror.

## 5. M0.3 Submission Eval Compiler

Status: complete.

Compiles exactly five positive and three negative reviewer drafts. Generated cases remain review-required and never self-promote to executed evidence.

## 6. MPF-M0.4 Local Marketplace Bridge

Status: complete.

### 6.1 Goal

Connect a validated plugin package to the local marketplace structure used for authoring/testing, then verify the actual installed cache copy.

### 6.2 Official marketplace shape

For a repo marketplace:

```text
<marketplace-root>/
  .agents/
    plugins/
      marketplace.json
  plugins/
    <plugin-name>/
      ...
```

A local marketplace entry uses a root-relative `./` path:

```json
{
  "name": "my-plugin",
  "source": {
    "source": "local",
    "path": "./plugins/my-plugin"
  },
  "policy": {
    "installation": "AVAILABLE",
    "authentication": "ON_INSTALL"
  },
  "category": "Productivity"
}
```

The path is resolved relative to the marketplace root, not relative to `.agents/plugins/`.

### 6.3 Bridge CLI

Dry-run:

```bash
mpf marketplace bridge <plugin-root> \
  --root <marketplace-root> \
  --pretty
```

Write:

```bash
mpf marketplace bridge <plugin-root> \
  --root <marketplace-root> \
  --write
```

Optional controls:

- `--marketplace-name`
- `--marketplace-display-name`
- `--category`
- `--installation`
- `--authentication`
- `--force`

### 6.4 Staging contract

The bridge stages only distributable package surfaces:

- `plugin.json`
- `mcp.json`
- `.mcp.json`
- `.app.json`
- `.codex-plugin/plugin.json`
- `skills/**`
- `hooks/**`
- `assets/**`

It intentionally does not copy unrelated repo material such as:

- tests
- docs
- evidence
- README
- build caches

Symlinked plugin files/directories are rejected.

### 6.5 Catalog merge

If `.agents/plugins/marketplace.json` already exists:

- its top-level marketplace name must match
- unrelated plugin entries are preserved
- the current plugin entry is replaced deterministically in the compiled catalog
- differing disk content is not overwritten unless `--force` is explicit

### 6.6 Marketplace validation

Validation checks:

- kebab-case marketplace id
- non-empty marketplace display name
- non-empty plugin list
- unique plugin names
- local source type
- `./`-prefixed source path
- source path containment within marketplace root
- installation policy shape
- authentication policy shape
- non-empty category

### 6.7 Install verification

ChatGPT local marketplace installs are verified against:

```text
~/.codex/plugins/cache/<marketplace>/<plugin>/<version>/
```

For local plugins, the normal version directory is:

```text
local
```

CLI:

```bash
mpf marketplace verify <plugin-root> \
  --root <marketplace-root> \
  --pretty
```

Optional:

- `--marketplace-name`
- `--cache-root`
- `--cache-version`
- `--write-evidence`
- `--evidence-output`
- `--force`

### 6.8 Verification contract

The verifier executes checks for:

1. marketplace catalog existence/validity
2. matching plugin catalog entry
3. staged plugin directory
4. installed cache directory
5. installed portable manifest
6. installed plugin identity
7. staged package SHA-256 digest
8. installed package SHA-256 digest
9. exact digest equality

A successful result:

```json
{
  "mode": "verify",
  "evidence_state": "executed",
  "install_verified": true,
  "blocking_reasons": []
}
```

An unsuccessful check remains `executed` evidence because the filesystem verification actually ran, but it records blockers such as:

- `marketplace_catalog_invalid`
- `marketplace_name_mismatch`
- `plugin_entry_missing`
- `staged_plugin_missing`
- `installed_cache_missing`
- `installed_manifest_invalid`
- `installed_plugin_name_mismatch`
- `installed_copy_differs_from_staged`

### 6.9 Digest contract

The package digest covers only distributable plugin surfaces and hashes:

```text
relative-path + NUL + file-bytes + NUL
```

for each sorted packaged file.

This allows the bridge to distinguish:

- no installation
- correct installation
- stale/different installed copy

without treating unrelated repository files as plugin content.

### 6.10 Install evidence artifact

`--write-evidence` writes:

```text
evidence/marketplace/install-verification.json
```

The artifact can only be written from an executed verify report.

The output path:

- must be relative
- cannot contain `..`
- must resolve inside the plugin root
- cannot replace differing evidence without `--force`

### 6.11 Human/UI boundary

M0.4 does not claim to click the ChatGPT desktop Plugins Directory.

The expected local loop is:

```text
mpf marketplace bridge --write
        |
restart ChatGPT desktop
        |
choose local marketplace
        |
install plugin
        |
mpf marketplace verify
        |
executed install evidence
```

This prevents "catalog generated" from being mislabeled "plugin installed."

## 7. Safety rules

M0.4 MUST NOT:

- treat a marketplace catalog as install proof
- copy unrelated repo evidence into the plugin package
- follow package symlinks
- allow source paths to escape marketplace root
- allow evidence output to escape plugin root
- silently replace differing staged/catalog/evidence files
- claim an installed package matches unless staged and cache digests are equal

## 8. Milestones

### MPF-M0.0 Skeleton

Status: complete.

### MPF-M0.1 Candidate Scanner

Status: complete.

### MPF-M0.2 Manifest Compiler

Status: complete.

### MPF-M0.3 Submission Eval Compiler

Status: complete.

### MPF-M0.4 Local Marketplace Bridge

Status: complete.

Acceptance satisfied:

- emits repo marketplace catalog entry
- uses `./` path relative to marketplace root
- stages a curated plugin package
- preserves unrelated catalog entries
- validates marketplace metadata
- records bridge writes separately from install verification
- verifies the actual installed cache copy
- records successful or failed install checks as executed evidence
- detects stale installed copies by digest
- evidence output stays inside plugin root
- overwrite requires explicit force

### MPF-M0.5 Submission Evidence Bundle

Acceptance:

- one command produces a versioned evidence directory
- aggregates scanner, manifest, eval, marketplace/install evidence
- every claim is tagged generated, inspected, or executed
- unreviewed eval cases block submission-ready
- missing publication/legal material blocks submission-ready
- failed local install verification remains visible

## 9. North star

```text
"I have a useful Skill"
        ->
"I have a plugin whose package, metadata, review cases,
local installation, and evidence trail I can explain."
```

MADO Plugin Factory is a **release-confidence compiler**.
