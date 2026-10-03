# ADR 0016: Keep first-release CI small and reproducible

- Status: accepted for Phase 15
- Date: 2026-10-03
- Reviewed base: `a592f35b8fd3f12f818a0d360c20177cab3c0d4b`

## Context

The alpha package has local artifact checks and installation evidence. The final
planned phase calls for contribution guidance and CI over Python 3.11–3.13,
without complicating the first workflow or publishing a release.

## Decision

Use one Linux GitHub Actions matrix with full tests, lint, formatting, strict
types, package building, archive audits and isolated installation checks for
all three Python versions. Reuse the existing uv lockfile and packaging checkers.
Pin external actions by commit and uv by the locally verified version. Allow
read-only repository access, avoid persisted checkout credentials, and include
no release/upload steps. Trigger on main pushes, pull requests and manual runs.

Expand contribution guidance with source-evidence requirements, focused changes,
matching local checks and clear limits on compatibility and release claims.
Include CONTRIBUTING.md in the explicitly selected source archive and its audit.

## Consequences

Reviewers get one consistent checks job per Python version. Repeating the small
static checks and builds in all three jobs keeps the workflow easy to understand.
Local macOS matrix results remain separate from remote Linux execution evidence.
Branch protection, release credentials, publication and remote CI execution are
outside the repository changes in this phase. Runtime behavior is unchanged.
See [github-readiness.md](../github-readiness.md) for the checklist and evidence.
