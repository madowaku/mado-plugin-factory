# Plugin Release Checklist

## Structure

- [ ] Root `plugin.json` exists for the portable Agent Plugins package.
- [ ] Root `plugin.json` declares the supported Agent Plugins `$schema`.
- [ ] Plugin name is stable and kebab-case.
- [ ] Skills are under `skills/<name>/SKILL.md`.
- [ ] Root `mcp.json` uses the portable Agent Plugins MCP schema when bundled MCP is used.
- [ ] Any `.codex-plugin/plugin.json` is an optional compatibility mirror, not the canonical portable manifest.

## Candidate scan

- [ ] `mpf scan` completed successfully.
- [ ] Architecture classification is expected.
- [ ] Architecture reason was reviewed.
- [ ] External dependencies were reviewed.
- [ ] Risk flags and evidence paths were reviewed.
- [ ] Source candidate remained unmodified.

## Manifest compile

- [ ] `mpf manifest` completed with `validation.valid: true`.
- [ ] Portable `plugin.json` is canonical.
- [ ] `extensions.com.openai.interface.displayName` is present.
- [ ] `extensions.com.openai.interface.shortDescription` is present and single-line.
- [ ] Package-level validation errors are empty.
- [ ] Final-directory warnings were reviewed.
- [ ] Publisher identity and legal URLs were supplied rather than invented.
- [ ] Component/asset paths stay inside the plugin root.
- [ ] Compatibility output does not invent a legacy MCP path.
- [ ] Existing manifests were not overwritten without explicit `--force`.

## Submission eval compile

- [ ] `mpf evals` completed with `validation.valid: true`.
- [ ] Exactly five positive cases exist.
- [ ] Exactly three negative cases exist.
- [ ] Positive prompts are unique after normalization.
- [ ] Negative scenarios are unique after normalization.
- [ ] Intent keys are unique.
- [ ] Every positive case has prompt, expected behavior, result shape, and fixture/test-account field.
- [ ] Every negative case has scenario, safe behavior, and reason not to complete.
- [ ] Scanner risk flags were compared with negative-case coverage.
- [ ] Manifest starter prompts were compared with positive-case coverage.
- [ ] Any `REVIEW REQUIRED` fixture placeholders were resolved.
- [ ] Generated cases still say `evidence_state: generated`.
- [ ] Generated cases still say `review_required: true`.
- [ ] No generated eval has been mislabeled as executed.
- [ ] Evidence output stayed inside the candidate root.
- [ ] Existing eval evidence was not overwritten without explicit `--force`.

## Human review

- [ ] Each positive case is realistic and reproducible without internal context.
- [ ] Each negative case exercises a genuine boundary for this plugin.
- [ ] Test accounts/fixtures are reviewer-accessible.
- [ ] Authenticated review fixtures require no MFA, SMS, email confirmation, or private-network access.
- [ ] Results were manually inspected or actually executed before any evidence-state promotion.

## Publication metadata

- [ ] Display name is final.
- [ ] Short and long descriptions are final.
- [ ] Starter prompts are realistic.
- [ ] Website URL is real and reachable when required.
- [ ] Support path is defined.
- [ ] Privacy policy exists when required.
- [ ] Terms of service exist when required.
- [ ] Availability countries/regions are selected.
- [ ] Release notes are prepared.

## MCP checks, when applicable

- [ ] Every MCP tool has accurate `readOnlyHint`.
- [ ] Every MCP tool has accurate `openWorldHint`.
- [ ] Every MCP tool has accurate `destructiveHint`.
- [ ] No tool response leaks secrets, debug payloads, unnecessary identifiers, or undisclosed personal data.
- [ ] Public endpoint and domain ownership requirements are satisfied.

## Evidence state

For every checked item, record one of:

- `generated`
- `inspected`
- `executed`

A submission candidate MUST NOT claim a stronger evidence state than the available proof supports.
