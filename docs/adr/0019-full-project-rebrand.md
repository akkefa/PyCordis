# ADR 0019: Rebrand the repository and Python package to deepseek-cordis

- Status: accepted by maintainer; supersedes ADR 0018's retained-import decision
- Date: 2026-10-04

## Decision

Use deepseek-cordis for the project, PyPI distribution and GitHub repository.
Use deepseek_cordis as the Python identifier and src package directory. Update
runtime namespace labels, imports, tests, examples, active documentation,
packaging checks and repository links. There is no legacy import shim for the
unpublished alpha. Behavioral APIs and dependencies are unchanged.

Historical source audits and ADRs retain the original project identity so their
recorded evidence remains accurate. They do not describe the current install API.
The existing local checkout directory is a filesystem location rather than an
API or project identity and is not moved by this change.

## Publishing consequence

The maintainer will rename the GitHub repository. The pending PyPI publisher
registered for akkefa/PyCordis must then be replaced with one for
akkefa/deepseek-cordis, still using release.yml and the pypi environment.
No GitHub rename, tag, upload or commit is performed as part of applying code
and documentation changes. See publishing.md for release setup.
