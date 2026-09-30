# Plugin Release Checklist

## Structure

- [ ] `.codex-plugin/plugin.json` exists.
- [ ] Plugin name is stable and kebab-case.
- [ ] Component paths are relative to plugin root and begin with `./`.
- [ ] Skills are under `skills/<name>/SKILL.md`.
- [ ] Only `plugin.json` is stored inside `.codex-plugin/`.

## Behavior

- [ ] Final skill tree has been inspected.
- [ ] Five positive test cases exist.
- [ ] Three negative test cases exist.
- [ ] Each positive case states prompt, expected behavior, result shape, and fixture.
- [ ] Each negative case states scenario, safe behavior, and why completion is inappropriate.
- [ ] Generated cases are not mislabeled as executed tests.

## Publication metadata

- [ ] Display name is final.
- [ ] Short and long descriptions are final.
- [ ] Starter prompts are realistic.
- [ ] Website URL is real and reachable.
- [ ] Support path is defined.
- [ ] Privacy policy exists when required.
- [ ] Terms of service exist when required.
- [ ] Availability countries/regions are selected.
- [ ] Release notes are prepared.

## MCP-only checks, when applicable

- [ ] Every MCP tool has accurate `readOnlyHint`.
- [ ] Every MCP tool has accurate `openWorldHint`.
- [ ] Every MCP tool has accurate `destructiveHint`.
- [ ] No tool response leaks secrets, debug payloads, unnecessary identifiers, or undisclosed personal data.
- [ ] Public endpoint and domain ownership requirements are satisfied.

## Evidence state

For every checked item, record one of:

- `generated` - synthesized by the factory
- `inspected` - verified by static inspection
- `executed` - verified by an actual test/run

A submission candidate MUST NOT claim `executed` evidence when only `generated` or `inspected` evidence exists.
