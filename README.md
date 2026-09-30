# MADO Plugin Factory

MADO Plugin Factory turns reusable Skills and MCP-backed workflows into submission-ready OpenAI plugins for ChatGPT and Codex.

## Goal

Convert an existing project or skill into a reproducible plugin release bundle:

```text
Skill / Repo
  -> Candidate Scan
  -> Plugin Contract
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
- MPF-M0.2 Manifest Compiler
- MPF-M0.3 Submission Eval Compiler
- MPF-M0.4 Local Marketplace Bridge
- MPF-M0.5 Submission Evidence Bundle

## Candidate Scanner

The scanner is read-only. It inspects a candidate directory and emits a deterministic JSON report with:

- architecture: `skills_only`, `mcp_only`, `skills_plus_mcp`, or `not_ready`
- architecture reason
- discovered skills
- portable and compatibility manifest state
- portable and legacy MCP state
- external dependencies
- risk flags with evidence paths
- missing release requirements

Run it without installation:

```bash
PYTHONPATH=src python -m mado_plugin_factory scan /path/to/candidate --pretty
```

Or install the package and use:

```bash
mpf scan /path/to/candidate --pretty
```

Use `--fail-on-not-ready` to return exit code 2 for a candidate with no discovered Skill or configured MCP server.

## Plugin packaging contract

New plugins SHOULD use the portable Agent Plugins layout:

```text
my-plugin/
  plugin.json
  skills/
    my-skill/
      SKILL.md
  mcp.json              # optional
  .codex-plugin/
    plugin.json          # optional compatibility fallback
```

The root `plugin.json` is canonical for new packages. Portable packages discover `skills/` automatically. A root `mcp.json` uses the Agent Plugins MCP schema and `mcpServers`.

The older `.codex-plugin/plugin.json` + `.mcp.json` layout remains supported as a compatibility path, and the scanner recognizes both.

## M0.1 output example

```json
{
  "architecture": "skills_only",
  "architecture_reason": "At least one SKILL.md was detected and no configured MCP server was found.",
  "skills": [
    {
      "name": "hello",
      "description": "Greet a user using a deterministic workflow.",
      "path": "skills/hello/SKILL.md",
      "has_frontmatter": true
    }
  ],
  "risk_flags": [],
  "missing": []
}
```

## Tests

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

The fixture suite currently covers:

- skills-only
- skills + portable MCP
- legacy MCP-only
- not-ready candidates
- source immutability
- template/fixture false-positive suppression
- CLI JSON and exit behavior

## Source of truth

Implementation tracks the current OpenAI Plugins documentation:

- Package your plugin: https://developers.openai.com/plugins/build/plugins
- Build skills: https://developers.openai.com/plugins/build/skills
- Submit plugins: https://developers.openai.com/plugins/deploy/submission

## Design rule

Do not optimize first for "publishing a plugin." Optimize for a deterministic transformation from a known-good Skill into a reviewable, testable, reproducible plugin artifact.

The product is a **release-confidence compiler**.
