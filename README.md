# MADO Plugin Factory

MADO Plugin Factory turns reusable Skills and MCP-backed workflows into submission-ready OpenAI plugins for ChatGPT and Codex.

## Goal

Convert an existing project or skill into a reproducible plugin release bundle:

```text
Skill / Repo
  -> Candidate Scan
  -> Plugin Contract
  -> .codex-plugin/plugin.json
  -> Skills / MCP wiring
  -> Positive + Negative eval cases
  -> Listing + legal checklist
  -> Local marketplace validation
  -> Submission evidence bundle
```

## M0 scope

M0 focuses on the safest, smallest release path: **skills-only plugins**.

Deliverables:

- canonical plugin folder skeleton
- submission contract
- 5 positive + 3 negative test-case template
- release evidence checklist
- local marketplace readiness notes

## Source of truth

Implementation should track the current OpenAI Plugins documentation, especially:

- Package your plugin: https://developers.openai.com/plugins/build/plugins
- Submit plugins: https://developers.openai.com/plugins/deploy/submission

## Layout

```text
docs/
  MADO_PLUGIN_FACTORY_SPEC.md
templates/
  skills-only/
    .codex-plugin/
      plugin.json
    skills/
      example/
        SKILL.md
  submission/
    test-cases.yaml
    release-checklist.md
```

## Milestones

- **MPF-M0.0 Skeleton**: repository contract and templates
- **MPF-M0.1 Candidate Scanner**: inspect an existing Skill/repo and classify plugin architecture
- **MPF-M0.2 Manifest Compiler**: generate and validate `.codex-plugin/plugin.json`
- **MPF-M0.3 Submission Eval Compiler**: generate/review 5 positive + 3 negative cases
- **MPF-M0.4 Local Marketplace Bridge**: make generated plugins installable from a local marketplace
- **MPF-M0.5 Submission Evidence Bundle**: produce a review-ready release package

## Design rule

Do not optimize first for "publishing a plugin." Optimize for a deterministic transformation from a known-good Skill into a reviewable, testable, reproducible plugin artifact.
