# ADR 0017: Publish matching GitHub tags with PyPI Trusted Publishing

- Status: accepted for requested release automation
- Date: 2026-10-04
- Reviewed base: `d7aa7cc5b5b29abf6a1589f572bca861dbfc00e0`

## Decision

Use a pushed `v*` tag as the release trigger. Reject references that do not
exactly equal `refs/tags/v` plus the version in pyproject.toml. Reuse the existing
Python 3.11–3.13 CI matrix through workflow_call. Avoid nested workflow concurrency
collisions by giving CI and publication distinct concurrency groups.

After checks pass, build and audit the distributions in a read-only job. Transfer
those files as a named artifact to a separate production publishing job in the
`pypi` environment. Only that job receives OIDC permission. Use PyPI Trusted
Publishing instead of a stored API token, and pin actions to verified revisions.

Read the expected version from checkout metadata in the isolated installation
checker so later version changes remain testable. Test exact tag matching,
including branch references and wrong versions, before enabling the workflow.

## Consequences

The maintainer must configure PyPI trust and GitHub environment settings before
pushing an authorized release tag. CI failures prevent publishing; duplicate
files remain explicit failures rather than silently skipped uploads. Local tests
and workflow lint cannot validate production authentication. Workflow creation
does not create a tag or perform an upload. See [publishing.md](../publishing.md).
