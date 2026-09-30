# Plugin Release Checklist

## Structure

- [ ] Root `plugin.json` exists.
- [ ] Portable schema and plugin identity validate.
- [ ] Skills and optional MCP/app/hook/assets surfaces are intentional.
- [ ] Compatibility output, if present, is not treated as canonical.

## Candidate scan

- [ ] `mpf scan` completed.
- [ ] Architecture is expected.
- [ ] Dependencies and risk flags were reviewed.
- [ ] Source candidate remained unmodified.

## Manifest compile

- [ ] `mpf manifest` reports `validation.valid: true`.
- [ ] OpenAI install-surface metadata was reviewed.
- [ ] Legal/publisher metadata was supplied rather than invented.
- [ ] Existing manifest replacement used explicit `--force` when needed.

## Submission eval compile

- [ ] Exactly five positive cases exist.
- [ ] Exactly three negative cases exist.
- [ ] Prompts/scenarios and intent keys are unique.
- [ ] Fixtures/test-account requirements are reproducible.
- [ ] Generated cases remain `generated` and `review_required: true`.
- [ ] Scanner risks are represented in negative-case review.

## Local marketplace bridge

- [ ] `mpf marketplace bridge` reports a valid catalog.
- [ ] Marketplace id and display name are intentional.
- [ ] Entry source is `./plugins/<plugin-name>`.
- [ ] Source path stays inside marketplace root.
- [ ] `policy.installation`, `policy.authentication`, and `category` are present.
- [ ] Staged package contains only distributable plugin surfaces.
- [ ] No symlinked plugin content was staged.
- [ ] Existing unrelated marketplace entries were preserved.
- [ ] Differing staged/catalog content was not overwritten without explicit `--force`.

## Local install verification

- [ ] ChatGPT desktop was restarted after marketplace changes.
- [ ] Plugin was installed from the intended local marketplace.
- [ ] `mpf marketplace verify` was run after installation.
- [ ] Marketplace catalog was valid at verification time.
- [ ] Matching plugin entry existed.
- [ ] Installed cache directory existed.
- [ ] Installed portable manifest was valid.
- [ ] Installed plugin identity matched.
- [ ] Staged and installed package digests matched.
- [ ] `install_verified: true`.
- [ ] Install verification evidence was saved when needed.
- [ ] A stale/different cache copy was not accepted as success.

## Human review

- [ ] Positive cases are realistic and reproducible.
- [ ] Negative cases exercise genuine boundaries.
- [ ] Reviewer fixtures/accounts need no MFA, SMS, email confirmation, or private-network access when applicable.
- [ ] Evidence-state promotion is supported by actual inspection/execution.

## Publication metadata

- [ ] Display name and descriptions are final.
- [ ] Starter prompts are realistic.
- [ ] Website/support/privacy/terms requirements are satisfied.
- [ ] Availability and release notes are ready.

## MCP checks, when applicable

- [ ] Tool annotations are accurate.
- [ ] Auth/data-flow behavior is documented.
- [ ] No tool response leaks secrets or unnecessary personal data.
- [ ] Endpoint/domain requirements are satisfied.

## Evidence state

Allowed states:

- `generated`
- `inspected`
- `executed`

A stronger state MUST NOT be claimed without corresponding proof.
