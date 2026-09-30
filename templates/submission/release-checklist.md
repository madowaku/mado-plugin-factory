# Plugin Release Checklist

## Structure

- [ ] Root `plugin.json` exists for the portable Agent Plugins package.
- [ ] Root `plugin.json` declares the supported Agent Plugins `$schema`.
- [ ] Plugin name is stable and kebab-case.
- [ ] Skills are under `skills/<name>/SKILL.md`.
- [ ] Root `mcp.json` uses the portable Agent Plugins MCP schema when bundled MCP is used.
- [ ] Any `.codex-plugin/plugin.json` is treated as an optional compatibility mirror, not the canonical portable manifest.
- [ ] Only `plugin.json` is stored inside `.codex-plugin/`.

## Candidate scan

- [ ] `mpf scan` completed successfully.
- [ ] Architecture classification is expected.
- [ ] Architecture reason was reviewed.
- [ ] External dependencies were reviewed.
- [ ] Risk flags and evidence paths were reviewed.
- [ ] Missing requirements are empty or intentionally documented.
- [ ] Source candidate remained unmodified.

## Manifest compile

- [ ] `mpf manifest` completed with `validation.valid: true`.
- [ ] Portable `plugin.json` is the canonical output.
- [ ] `extensions.com.openai.interface.displayName` is present.
- [ ] `extensions.com.openai.interface.shortDescription` is present and single-line.
- [ ] Package-level validation errors are empty.
- [ ] Final-directory length warnings were reviewed.
- [ ] Publisher identity and legal URLs were supplied, not inferred.
- [ ] Component and asset paths begin with `./` and stay inside the plugin root.
- [ ] Compatibility output, if generated, mirrors portable intent and does not invent `.mcp.json`.
- [ ] Existing manifests were not overwritten without explicit `--force`.

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
