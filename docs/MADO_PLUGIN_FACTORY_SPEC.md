# MADO_PLUGIN_FACTORY_SPEC.md v0.1

Status: Implementing  
Project: MADO Plugin Factory  
Repository: `madowaku/mado-plugin-factory`

## 1. Purpose

MADO Plugin Factory is a release-confidence compiler for reusable agent capabilities.

Its job is to take an existing Skill, workflow, or MCP-backed project and transform it into a plugin artifact that is:

1. structurally valid,
2. locally testable,
3. reviewable,
4. evidence-backed,
5. ready for OpenAI plugin submission work.

The first optimization target is a **skills-only plugin**, because it minimizes infrastructure, auth, and remote-MCP review surface.

## 2. Canonical plugin contract

For new packages, the canonical portable layout is:

```text
<plugin-root>/
  plugin.json
  skills/
    <skill-name>/
      SKILL.md
  mcp.json                 # optional
  .codex-plugin/
    plugin.json             # optional compatibility fallback
```

Rules:

- root `plugin.json` is the canonical identity for new Agent Plugins packages.
- portable packages discover skills from root `skills/`.
- portable MCP configuration lives at root `mcp.json`.
- `.codex-plugin/plugin.json` remains a supported compatibility fallback.
- compatibility MCP configuration may use root `.mcp.json`.
- OpenAI-specific presentation and registered-app settings belong under `extensions.com.openai` in the portable manifest.

## 3. Minimum portable manifest

```json
{
  "$schema": "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",
  "name": "example-plugin",
  "version": "0.1.0",
  "description": "A reusable workflow."
}
```

Portable packages do not need a `skills` field to discover root `skills/`.

## 4. Inputs

The factory accepts one of:

### 4.1 Existing Skill

Minimum:
- a `SKILL.md`
- a stable purpose
- an identifiable trigger/use case

Optional:
- references
- scripts
- assets
- fixtures
- tests

### 4.2 Existing repo

The scanner identifies:
- reusable skills
- portable and compatibility manifests
- portable and legacy MCP configuration
- external package dependencies
- external network hints
- auth/secret dependency hints
- destructive-operation hints
- user-data-access hints
- missing packaging metadata

## 5. Architecture classification

The Candidate Scanner emits one of:

- `skills_only`
- `mcp_only`
- `skills_plus_mcp`
- `not_ready`

Classification is based only on actual discovered capability surfaces:

- at least one candidate `SKILL.md`
- at least one configured MCP server

Files under documentation, templates, examples, evidence, and test fixture roots are not treated as production Skill surfaces.

## 6. MPF-M0.1 Candidate Scanner

Status: implemented.

### 6.1 CLI

```bash
mpf scan <candidate-path> --pretty
```

Optional:

```bash
mpf scan <candidate-path> --fail-on-not-ready
```

Exit behavior:

- `0`: scan completed
- `1`: invalid input / scan error
- `2`: scan completed but architecture is `not_ready` and `--fail-on-not-ready` was supplied

### 6.2 Output contract

```json
{
  "schema_version": "0.1",
  "source": {
    "root": "/absolute/path",
    "scanned_files": 12
  },
  "architecture": "skills_only",
  "architecture_reason": "At least one SKILL.md was detected and no configured MCP server was found.",
  "skills": [],
  "components": {
    "manifest": {
      "portable": null,
      "codex_compat": null,
      "recommended": "plugin.json"
    },
    "mcp": {
      "portable": null,
      "legacy": null,
      "configured": false
    },
    "apps": {
      "path": null
    },
    "hooks": {
      "present": false
    }
  },
  "external_dependencies": [],
  "risk_flags": [],
  "missing": []
}
```

### 6.3 Read-only guarantee

The scanner MUST NOT mutate the source candidate.

Tests compare the candidate file map before and after scanning.

### 6.4 Risk evidence rule

Risk flags are heuristics, not verdicts.

Each risk includes:
- code
- severity
- reason
- evidence paths

The scanner MUST NOT emit matched secret values or file contents in risk output.

### 6.5 Current risk flags

- `auth_or_secret_dependency`
- `external_network`
- `destructive_operation`
- `user_data_access`
- `mcp_runtime_dependency`

### 6.6 Missing-state hints

Current missing codes include:

- `no_capability`
- `portable_manifest_missing`
- `portable_manifest_invalid`
- `portable_manifest_schema_missing`
- `portable_mcp_manifest_invalid`
- `legacy_mcp_manifest_invalid`
- `skill_metadata_incomplete`

These are diagnostic hints. Full manifest conformance belongs to MPF-M0.2.

## 7. Compilation pipeline

```text
SOURCE
  |
  v
Candidate Scanner                <- M0.1 implemented
  |
  +--> architecture classification
  +--> risk flags + evidence paths
  +--> dependency inventory
  +--> missing metadata
  |
  v
Manifest Compiler                <- M0.2
  |
  v
Skill Packager
  |
  v
Submission Eval Compiler         <- M0.3
  |
  +--> 5 positive cases
  +--> 3 negative cases
  |
  v
Local Validation                 <- M0.4
  |
  v
Evidence Bundle                  <- M0.5
```

## 8. Submission eval contract

Each release candidate MUST include at least five positive and three negative cases.

### Positive case fields

- id
- user_prompt
- expected_behavior
- expected_result_shape
- fixture

### Negative case fields

- id
- user_prompt_or_scenario
- expected_safe_behavior
- reason_not_to_complete

Generation is allowed. Blind promotion is not.

The compiler MUST mark generated cases `review_required: true` until a human or deterministic validator confirms they match actual plugin behavior.

## 9. Evidence bundle

A release evidence bundle SHOULD contain:

```text
evidence/<release-id>/
  manifest/
    plugin.json
  inventory/
    file-tree.txt
    skills.json
  evals/
    test-cases.yaml
    results.json
  checks/
    release-checklist.md
    validation.json
  release/
    release-notes.md
```

For MCP plugins, later milestones add:
- tool inventory
- tool annotations
- endpoint/domain evidence
- auth behavior
- privacy/data-flow notes

## 10. Safety rules

The factory MUST NOT:

- fabricate successful test results,
- mark a generated case as executed when it was only synthesized,
- infer a privacy policy URL that does not exist,
- silently omit destructive or open-world behavior,
- include secrets, tokens, private fixtures, or auth material in evidence bundles,
- convert a local-only dependency into a claim of public availability,
- mutate source repositories during candidate scanning.

## 11. Milestones

### MPF-M0.0 Skeleton

Status: complete.

### MPF-M0.1 Candidate Scanner

Status: complete.

Acceptance:
- deterministic architecture classification
- source repo is not mutated
- architecture reason is recorded
- portable + compatibility packaging surfaces are distinguished
- risk flags include evidence paths without exposing secret values
- fixture/template Skills do not create production capability false positives
- CLI supports machine-readable JSON
- unit tests cover all four architecture states

### MPF-M0.2 Manifest Compiler

Acceptance:
- generates root portable `plugin.json`
- validates Agent Plugins `$schema`
- validates kebab-case identity
- emits OpenAI interface metadata under `extensions.com.openai`
- can optionally emit a compatibility `.codex-plugin/plugin.json`
- never treats compatibility output as the canonical portable source

### MPF-M0.3 Submission Eval Compiler

Acceptance:
- outputs 5 positive and 3 negative cases
- no duplicate intents
- all generated cases marked review-required
- supports fixture references

### MPF-M0.4 Local Marketplace Bridge

Acceptance:
- generated plugin can be referenced by a local or repo marketplace
- install test is recorded as evidence, not assumed

### MPF-M0.5 Submission Evidence Bundle

Acceptance:
- one command produces a versioned evidence directory
- every claim is tagged as generated, inspected, or executed
- missing publication/legal metadata blocks "submission-ready" status

## 12. North star

The product is not a plugin generator.

The product is a **release-confidence compiler**:

```text
"I have a useful Skill"
        ->
"I have a plugin artifact whose structure, behavior,
tests, risks, and release evidence I can explain."
```
