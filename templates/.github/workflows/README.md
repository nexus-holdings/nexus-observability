# Template Workflows — NO default publishing

This directory is scaffolded into every new company repo created from this template. **It intentionally contains no image-publish or release workflows.**

## Why

Publishing from CI during the dev phase of Nexus is a class of catastrophic data leak. The 2026-04-16 npm publish incident (see `docs/incidents/2026-04-16-npm-publish-audit.md` in the nexus monorepo) was benign only by two layers of luck — a forked repo had inherited a dormant `publish.yml` that auto-fired `npm publish --access public` to the public registry on every push to `main`. The class of risk (npm, pypi, docker registries, GitHub Releases, GitHub Pages) is broader than npm alone.

On 2026-04-17 Ian formalized the no-publishing policy: no workflow in any `nexus-holdings` repo publishes to external destinations during the dev phase. Scaffolding a publish workflow into every new repo — even one gated behind release tags — leaves ambient risk that could fire accidentally.

## What this template provides

- `ci.yml` — PR + push-to-main: lint, test, security scan. No publish.

## What this template intentionally does NOT provide

- `deploy.yml` — removed. If a company repo needs to deploy, the repo owner adds a deploy workflow explicitly, with a sole-control destination (see `project_negotiagent_legal_cleared.md` for the EU residency + self-controlled-infra constraint).
- `publish.yml` / `release.yml` — never scaffolded.
- Image push to `ghcr.io` or any other registry — not in CI.

## If a downstream repo legitimately needs to publish

1. Ask Ian.
2. Add a publish workflow explicitly (don't fork it from somewhere).
3. Point it at a destination under Negotiagent's sole control (EU residency).
4. Set `"private": true` in the manifest. Use scoped names for defense in depth.
5. Document the decision — what ships, to where, gated by what.

## References

- Nexus ticket 97635207 — "Fix template workflows to prevent auto-push to ghcr.io"
- `docs/incidents/2026-04-16-npm-publish-audit.md` (in the nexus monorepo)
- No-publishing policy memory: `project_no_publishing_policy.md` (claude-state)
- Cross-repo policy enforcement (planned): NEXA-53 PolicyWatch
