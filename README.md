# MADO Plugin Factory

MADO Plugin Factory turns reusable Skills and MCP-backed workflows into submission-ready OpenAI plugins for ChatGPT and Codex.

## Goal

Convert an existing project or skill into a reproducible plugin release bundle:

```text
Skill / Repo
  -> Candidate Scan
  -> Manifest Compile
  -> plugin.json
  -> Skills / MCP wiring
  -> Positive + Negative eval cases
  -> Listing + legal checklist
  -> Local marketplace validation
  -> Submission evidence bundle
```

## Current status

- **MPF-M0.0 Skeleton** ✅
- **MPF-M0.1 Candidate Scanner** ✅
- **MPF-M0.2 Manifest Compiler** ✅
- MPF-M0.3 Submission Eval Compiler
- MPF-M0.4 Local Marketplace Bridge
- MPF-M0.5 Submission Evidence Bundle

## Candidate Scanner

The scanner is read-only. It inspects a candidate directory and emits deterministic JSON with:

- architecture: `skills_only`, `mcp_only`, `skills_plus_mcp`, or `not_ready`
- architecture reason
- discovered skills
- portable and compatibility manifest state
- portable and legacy MCP state
- external dependencies
- risk flags with evidence paths
- missing release requirements

Run it with:

```bash
PYTHONPATH=src python -m mado_plugin_factory scan /path/to/candidate --pretty
```

Or after installation:

```bash
mpf scan /path/to/candidate --pretty
```

## Manifest Compiler

M0.2 compiles the scanner result into a portable root `plugin.json`.

Dry-run by default:

```bash
mpf manifest /path/to/candidate \
  --name my-plugin \
  --description "Reusable workflow" \
  --pretty
```

Write only after validation:

```bash
mpf manifest /path/to/candidate \
  --metadata ./manifest-metadata.json \
  --write
```

Generate an optional compatibility mirror:

```bash
mpf manifest /path/to/candidate \
  --metadata ./manifest-metadata.json \
  --compat \
  --write
```

If a differing manifest already exists, the compiler refuses to overwrite it unless `--force` is supplied.

### Metadata input

See `templates/manifest/metadata.json`.

Supported portable metadata includes:

- `name`
- `version`
- `description`
- `author`
- `homepage`
- `repository`
- `license`
- `keywords`

OpenAI install-surface metadata is emitted under:

```text
extensions.com.openai.interface
```

The compiler supports fields such as:

- `displayName`
- `shortDescription`
- `longDescription`
- `developerName`
- `category`
- `capabilities`
- `websiteURL`
- `privacyPolicyURL`
- `termsOfServiceURL`
- `defaultPrompt`
- `brandColor`
- `composerIcon`
- `logo`
- `screenshots`

### Validation behavior

The compiler validates:

- supported Agent Plugins schema URL
- stable kebab-case plugin identity
- semantic version shape
- non-empty description
- OpenAI interface presence
- package-level display-name and short-description limits
- final public-directory length limits as warnings
- `./`-prefixed component paths that stay inside the plugin root
- basic publisher URLs, asset paths, prompts, capabilities, and brand color

Invalid manifests are never written.

## Plugin packaging contract

New packages target the portable Agent Plugins layout:

```text
my-plugin/
  plugin.json
  skills/
    my-skill/
      SKILL.md
  mcp.json              # optional portable MCP
  .codex-plugin/
    plugin.json          # optional compatibility mirror
```

The root `plugin.json` is canonical for the portable package. Portable packages discover `skills/` automatically and use root `mcp.json` for bundled MCP configuration.

MADO Plugin Factory also recognizes and can emit Codex compatibility packaging where needed, but compatibility output never becomes the compiler's canonical source.

## Safety and determinism

The factory separates three evidence states:

- `generated`
- `inspected`
- `executed`

M0.1 scanning does not mutate source candidates.

M0.2 compilation is a dry-run unless `--write` is explicitly requested. A differing existing manifest requires `--force` before replacement.

## Tests

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

The suite covers Candidate Scanner behavior plus Manifest Compiler behavior including:

- portable manifest generation
- OpenAI interface compilation
- invalid identity detection
- compatibility mirror generation
- portable MCP / legacy MCP separation
- no invented compatibility MCP path
- overwrite protection
- deterministic output
- CLI dry-run behavior

## Source of truth

Implementation tracks the current OpenAI Plugins documentation:

- Package your plugin: https://developers.openai.com/plugins/build/plugins
- Build skills: https://developers.openai.com/plugins/build/skills
- Submit plugins: https://developers.openai.com/plugins/deploy/submission
- Submission errors: https://developers.openai.com/plugins/deploy/submission-errors

## Design rule

Do not optimize first for "publishing a plugin." Optimize for a deterministic transformation from a known-good Skill into a reviewable, testable, reproducible plugin artifact.

The product is a **release-confidence compiler**.
