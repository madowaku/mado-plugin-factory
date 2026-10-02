# Plugin Release Checklist

## Package

- [ ] Root `plugin.json` validates.
- [ ] Plugin identity/version are final.
- [ ] Curated package inventory is intentional.
- [ ] Final Skill tree is the tree that was locally tested.
- [ ] Generated `evidence/` does not affect source scanning.

## Candidate scan

- [ ] `mpf scan` completed.
- [ ] Architecture is expected.
- [ ] Dependencies and risk flags were reviewed.
- [ ] Scanner missing requirements are resolved or documented.

## Manifest

- [ ] `mpf manifest` reports valid.
- [ ] Display name, descriptions, and category are final.
- [ ] Starter prompts are realistic.
- [ ] Logo/brand assets are ready.
- [ ] Publisher/legal URLs were supplied rather than invented.

## Submission evals

- [ ] Exactly five positive cases exist.
- [ ] Exactly three negative cases exist.
- [ ] Prompts/scenarios and intent keys are unique.
- [ ] Fixtures/test-account requirements are reproducible.
- [ ] Risk-derived negative cases were reviewed.
- [ ] Human reviewer explicitly reviewed the final 5/3 set.
- [ ] Generated case origin was not mislabeled as executed evidence.

## Local install

- [ ] Local marketplace bridge was written.
- [ ] Plugin was installed from the intended marketplace.
- [ ] `mpf marketplace verify` was run.
- [ ] Installed manifest identity matched.
- [ ] Staged and installed package digests matched.
- [ ] `install_verified: true`.
- [ ] Verification evidence was saved.

## Release metadata

- [ ] Availability countries/regions are final.
- [ ] Release notes explain purpose, initial/update status, changes, and reviewer setup.
- [ ] Listing review is attested.
- [ ] Final Skill-tree testing is attested.
- [ ] Eval review is attested.
- [ ] No passwords, tokens, API keys, or reviewer credentials are stored in release metadata.

## Publication URLs

- [ ] Website is public HTTPS.
- [ ] Support URL is public HTTPS.
- [ ] Privacy policy is public HTTPS.
- [ ] Terms URL is public HTTPS.
- [ ] URLs match the publisher identity.

## Portal prerequisites

- [ ] Submitter has Apps Management write access.
- [ ] Publisher identity is verified.
- [ ] Policy attestations are complete.
- [ ] Bundled Skill safety/security scan passed.

## MCP-only / MCP-plus-Skills

- [ ] Production MCP URL is HTTPS and publicly reachable.
- [ ] Demo recording URL is ready.
- [ ] Domain verification is complete.
- [ ] Current tool scan passed.
- [ ] Tool names/descriptions/schemas match behavior.
- [ ] `readOnlyHint`, `openWorldHint`, and `destructiveHint` were reviewed.
- [ ] Reviewer access works without MFA/SMS/email confirmation/private network where applicable.
- [ ] Tool responses do not expose unnecessary personal data, auth secrets, debug payloads, or internal identifiers.

## M0.5 bundle

- [ ] `mpf bundle` was run with final release metadata.
- [ ] `upload_ready: true`.
- [ ] Submission blockers were reviewed.
- [ ] `submission_ready: true` only after external/portal gates are actually satisfied.
- [ ] Versioned bundle directory was written.
- [ ] `plugin.zip` excludes internal evidence/docs/tests.
- [ ] `plugin.zip.sha256` matches the ZIP.
- [ ] Re-running bundle generation is idempotent.
- [ ] Differing release artifacts were not overwritten without explicit `--force`.

## Evidence states

Allowed states:

- `generated`
- `inspected`
- `executed`

A stronger state MUST NOT be claimed without proof or explicit human review attestation.
