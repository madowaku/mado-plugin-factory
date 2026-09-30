# MADO_PLUGIN_FACTORY_SPEC.md v0.1

Status: Draft  
Project: MADO Plugin Factory  
Repository: `madowaku/mado-plugin-factory`

## 1. Purpose

MADO Plugin Factory is a release compiler for reusable agent capabilities.

Its job is to take an existing Skill, workflow, or MCP-backed project and transform it into a plugin artifact that is:

1. structurally valid,
2. locally testable,
3. reviewable,
4. evidence-backed,
5. ready for OpenAI plugin submission work.

The first target is a **skills-only plugin**, because it minimizes infrastructure, auth, and remote-MCP review surface.

## 2. Canonical plugin contract

Every generated plugin MUST have:

```text
<plugin-root>/
  .codex-plugin/
    plugin.json
```

A skills-only plugin SHOULD also have:

```text
<plugin-root>/
  .codex-plugin/
    plugin.json
  skills/
    <skill-name>/
      SKILL.md
```

Only `plugin.json` belongs inside `.codex-plugin/`. Skills, hooks, assets, `.mcp.json`, and `.app.json` live at plugin root when used.

## 3. Minimum manifest

```json
{
  "name": "example-plugin",
  "version": "0.1.0",
  "description": "A reusable workflow.",
  "skills": "./skills/"
}
```

Rules:

- `name` is stable and kebab-case.
- paths are relative to plugin root.
- component paths start with `./`.
- published candidates SHOULD include richer interface metadata before submission.

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
- MCP dependencies
- external network dependencies
- auth requirements
- destructive actions
- user-data access
- fixtures/evidence already present

## 5. Architecture classification

The Candidate Scanner emits one of:

- `skills_only`
- `mcp_only`
- `skills_plus_mcp`
- `not_ready`

M0 optimizes for `skills_only`.

A candidate SHOULD be classified `skills_only` when its useful behavior can be expressed as repeatable instructions/workflows without requiring a dedicated remote tool service.

## 6. Compilation pipeline

```text
SOURCE
  |
  v
Candidate Scanner
  |
  v
Capability Contract
  |
  +--> architecture classification
  +--> risk flags
  +--> missing metadata
  |
  v
Manifest Compiler
  |
  v
Skill Packager
  |
  v
Submission Eval Compiler
  |
  +--> 5 positive cases
  +--> 3 negative cases
  |
  v
Local Validation
  |
  v
Evidence Bundle
```

## 7. Submission eval contract

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

Generation is allowed. Blind generation is not.

The compiler MUST mark generated cases `review_required: true` until a human or deterministic validator confirms they match actual plugin behavior.

## 8. Evidence bundle

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

## 9. Safety rules

The factory MUST NOT:

- fabricate successful test results,
- mark a generated case as executed when it was only synthesized,
- infer a privacy policy URL that does not exist,
- silently omit destructive or open-world behavior,
- include secrets, tokens, private fixtures, or auth material in evidence bundles,
- convert a local-only dependency into a claim of public availability.

## 10. Milestones

### MPF-M0.0 Skeleton

Acceptance:
- repo has canonical docs and templates
- manifest template uses `.codex-plugin/plugin.json`
- submission eval template contains 5 positive and 3 negative slots
- release checklist distinguishes generated vs verified evidence

### MPF-M0.1 Candidate Scanner

Input:
- local/repo Skill tree metadata

Output:
```json
{
  "architecture": "skills_only",
  "skills": [],
  "external_dependencies": [],
  "risk_flags": [],
  "missing": []
}
```

Acceptance:
- deterministic scan result
- no mutation of source repo
- reason for architecture classification is recorded

### MPF-M0.2 Manifest Compiler

Acceptance:
- compiles minimal valid manifest
- validates kebab-case name
- validates `./` component paths
- rejects missing `.codex-plugin/plugin.json` destination contract

### MPF-M0.3 Submission Eval Compiler

Acceptance:
- outputs 5 positive and 3 negative cases
- no duplicate intents
- all generated cases marked review-required
- supports fixture references

### MPF-M0.4 Local Marketplace Bridge

Acceptance:
- generated plugin can be referenced by a repo-scoped or personal marketplace catalog
- marketplace path is relative and `./`-prefixed
- install test is recorded as evidence, not assumed

### MPF-M0.5 Submission Evidence Bundle

Acceptance:
- one command produces a versioned evidence directory
- every claim is tagged as generated, inspected, or executed
- missing publication/legal metadata blocks "submission-ready" status

## 11. North star

The product is not a plugin generator.

The product is a **release-confidence compiler**:

```text
"I have a useful Skill"
        ->
"I have a plugin artifact whose structure, behavior,
tests, risks, and release evidence I can explain."
```
