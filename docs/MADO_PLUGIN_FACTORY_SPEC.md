# MADO_PLUGIN_FACTORY_SPEC.md v0.2

Status: Implementing  
Project: MADO Plugin Factory  
Repository: `madowaku/mado-plugin-factory`

## 1. Purpose

MADO Plugin Factory is a release-confidence compiler for reusable agent capabilities.

Its job is to transform an existing Skill, workflow, or MCP-backed project into a plugin artifact that is:

1. structurally valid,
2. locally testable,
3. reviewable,
4. evidence-backed,
5. ready for submission work.

The first optimization target remains skills-only plugins, because they minimize infrastructure, authentication, and remote-MCP review surface.

## 2. Packaging model

The factory treats the portable Agent Plugins package as canonical:

```text
<plugin-root>/
  plugin.json
  skills/
    <skill-name>/
      SKILL.md
  mcp.json                 # optional portable MCP
  .codex-plugin/
    plugin.json             # optional compatibility mirror
```

Rules:

- root `plugin.json` is the portable identity.
- portable packages discover root `skills/`.
- portable bundled MCP configuration lives at root `mcp.json`.
- OpenAI-specific presentation, registered-app mapping, and explicit hook settings live under `extensions.com.openai`.
- `.codex-plugin/plugin.json` is supported as a compatibility form.
- a compatibility manifest is never treated as the compiler's canonical portable source.

## 3. Minimum portable manifest

```json
{
  "$schema": "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",
  "name": "example-plugin",
  "version": "0.1.0",
  "description": "A reusable workflow.",
  "extensions": {
    "com.openai": {
      "interface": {
        "displayName": "Example Plugin",
        "shortDescription": "Reusable workflow",
        "longDescription": "A reusable workflow."
      }
    }
  }
}
```

Portable packages do not need a `skills` field to discover root `skills/`.

## 4. Pipeline

```text
SOURCE
  |
  v
Candidate Scanner                <- M0.1 complete
  |
  +--> architecture
  +--> skills
  +--> dependencies
  +--> risks
  +--> missing metadata
  |
  v
Manifest Compiler                <- M0.2 complete
  |
  +--> portable plugin.json
  +--> validation report
  +--> optional compatibility mirror
  |
  v
Submission Eval Compiler         <- M0.3
  |
  +--> 5 positive cases
  +--> 3 negative cases
  |
  v
Local Marketplace Bridge         <- M0.4
  |
  v
Submission Evidence Bundle       <- M0.5
```

## 5. MPF-M0.1 Candidate Scanner

Status: complete.

The scanner is read-only and emits one architecture:

- `skills_only`
- `mcp_only`
- `skills_plus_mcp`
- `not_ready`

It records the reason, discovered Skills, manifest/MCP surfaces, external dependencies, risk flags with evidence paths, and missing requirements.

The scanner MUST NOT:

- mutate the source candidate,
- treat files under tests/templates/examples/docs/evidence as production Skills,
- reveal matched credential or secret values.

## 6. MPF-M0.2 Manifest Compiler

Status: complete.

### 6.1 CLI

Dry-run:

```bash
mpf manifest <candidate-path> \
  --name my-plugin \
  --description "Reusable workflow" \
  --pretty
```

Metadata-driven:

```bash
mpf manifest <candidate-path> \
  --metadata ./manifest-metadata.json \
  --pretty
```

Write portable output:

```bash
mpf manifest <candidate-path> \
  --metadata ./manifest-metadata.json \
  --write
```

Write portable + compatibility output:

```bash
mpf manifest <candidate-path> \
  --metadata ./manifest-metadata.json \
  --compat \
  --write
```

A differing existing manifest is not overwritten unless `--force` is supplied.

### 6.2 Input precedence

For identity fields, precedence is:

```text
explicit metadata / CLI
  >
existing portable plugin.json
  >
deterministic inference
```

Current deterministic inference:

- `name`: candidate directory name
- `version`: `0.1.0`
- `description`: the Skill description only when exactly one described Skill exists
- `displayName`: title-cased kebab-case name
- `shortDescription`: portable description
- `longDescription`: portable description

The compiler does not invent publisher identity, legal URLs, or claims.

### 6.3 Metadata contract

Portable metadata may include:

- `name`
- `version`
- `description`
- `author`
- `homepage`
- `repository`
- `license`
- `keywords`

OpenAI interface metadata is supplied as:

```json
{
  "interface": {
    "displayName": "My Plugin",
    "shortDescription": "Short listing copy",
    "longDescription": "Longer listing copy",
    "developerName": "Publisher",
    "category": "Productivity",
    "capabilities": ["Workflow"],
    "websiteURL": "https://example.com",
    "privacyPolicyURL": "https://example.com/privacy",
    "termsOfServiceURL": "https://example.com/terms",
    "defaultPrompt": ["Use My Plugin for this workflow."],
    "brandColor": "#10A37F",
    "composerIcon": "./assets/icon.png",
    "logo": "./assets/logo.png",
    "screenshots": ["./assets/screenshot-1.png"]
  }
}
```

The emitted portable location is:

```text
extensions.com.openai.interface
```

### 6.4 Component inference

If an existing candidate contains `.app.json`, the compiler emits:

```json
{
  "extensions": {
    "com.openai": {
      "apps": "./.app.json"
    }
  }
}
```

If `hooks/hooks.json` exists, it may emit:

```json
{
  "extensions": {
    "com.openai": {
      "hooks": "./hooks/hooks.json"
    }
  }
}
```

Portable `skills/` and `mcp.json` are fixed package surfaces and are not redundantly declared in the root portable manifest.

### 6.5 Compatibility mirror

`--compat` compiles an optional `.codex-plugin/plugin.json` mirror.

It may contain:

- identity and publisher metadata,
- `skills: "./skills/"`,
- `mcpServers: "./.mcp.json"` only when an actual legacy `.mcp.json` exists,
- `apps`,
- `hooks`,
- `interface`.

The compiler MUST NOT invent `.mcp.json` from portable `mcp.json`.

When portable MCP exists without legacy MCP and compatibility output is requested, emit a warning rather than a fake compatibility path.

### 6.6 Validation levels

Validation returns:

```json
{
  "valid": true,
  "errors": [],
  "warnings": []
}
```

Errors block `--write`.

Current error checks include:

- supported Agent Plugins `$schema`,
- kebab-case `name`,
- semantic version shape,
- non-empty portable description,
- OpenAI extension/interface structure,
- package-level display-name limit,
- package-level short-description limit,
- single-line short description,
- relative component/asset paths,
- paths escaping plugin root,
- basic URL shape,
- capabilities and starter-prompt shape,
- six-digit brand color,
- referenced apps/hooks file existence.

Warnings include stricter final public-directory limits where package validation can still succeed.

### 6.7 Write safety

Default behavior is compile-only.

`--write`:

- writes only after successful validation,
- writes root `plugin.json`,
- optionally writes `.codex-plugin/plugin.json`,
- refuses to replace differing existing output without `--force`,
- permits an idempotent write when content is already identical.

### 6.8 Determinism

Given the same:

- source candidate,
- metadata,
- compatibility option,

the compiler MUST return the same report and manifest content.

No timestamps, random IDs, or environment-derived publisher metadata are inserted.

## 7. Submission eval contract

M0.3 will compile at least five positive and three negative cases.

Positive case fields:

- id
- user_prompt
- expected_behavior
- expected_result_shape
- fixture

Negative case fields:

- id
- user_prompt_or_scenario
- expected_safe_behavior
- reason_not_to_complete

Generated cases remain `review_required: true` until inspected or executed.

## 8. Evidence bundle

A release evidence bundle SHOULD contain:

```text
evidence/<release-id>/
  manifest/
    plugin.json
    compatibility-plugin.json
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

Evidence claims use:

- `generated`
- `inspected`
- `executed`

The factory MUST NOT upgrade one evidence state to another without proof.

## 9. Safety rules

The factory MUST NOT:

- fabricate successful test results,
- mark a generated case as executed,
- infer a privacy or legal URL that does not exist,
- invent publisher identity,
- hide destructive or open-world behavior,
- include secrets/tokens/private fixtures in evidence bundles,
- claim a local-only dependency is publicly available,
- mutate source candidates during scanning,
- overwrite a differing manifest without explicit force.

## 10. Milestones

### MPF-M0.0 Skeleton

Status: complete.

### MPF-M0.1 Candidate Scanner

Status: complete.

### MPF-M0.2 Manifest Compiler

Status: complete.

Acceptance satisfied:

- generates root portable `plugin.json`
- validates supported Agent Plugins `$schema`
- validates kebab-case identity
- emits OpenAI interface metadata under `extensions.com.openai`
- optionally emits a compatibility `.codex-plugin/plugin.json`
- does not treat compatibility output as canonical
- dry-run is the default
- invalid output is not written
- overwrite requires explicit force
- output is deterministic

### MPF-M0.3 Submission Eval Compiler

Acceptance:

- outputs 5 positive and 3 negative cases
- no duplicate intents
- generated cases remain review-required
- fixture references are supported
- cases can consume M0.1 risk/missing data and M0.2 manifest metadata

### MPF-M0.4 Local Marketplace Bridge

Acceptance:

- generated plugin can be referenced by a repo or personal marketplace
- marketplace path stays relative and inside its root
- install test is recorded as evidence, never assumed

### MPF-M0.5 Submission Evidence Bundle

Acceptance:

- one command produces a versioned evidence directory
- every claim is tagged generated, inspected, or executed
- missing publication/legal metadata prevents submission-ready status

## 11. North star

The product is not a plugin generator.

The product is a **release-confidence compiler**:

```text
"I have a useful Skill"
        ->
"I have a plugin artifact whose structure, behavior,
metadata, tests, risks, and release evidence I can explain."
```
