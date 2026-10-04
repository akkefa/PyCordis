> The retained-import decision below was superseded by ADR 0019 at the maintainer's request.

# ADR 0018: Separate the PyPI distribution and Python import names

- Status: accepted by maintainer
- Date: 2026-10-04

## Context

PyPI rejected the provisional pycordis project name as too similar to an existing
project. The maintainer registered a pending publisher for deepseek-cordis and
confirmed that name. The repository and existing import API remain PyCordis and
pycordis respectively.

## Decision

Set the distribution metadata name to deepseek-cordis. Retain src/pycordis and
all existing Python imports. Normalize the distribution name independently for
wheel metadata directories and source archive prefixes, and audit runtime files
under the unchanged import package. Read distribution identity from pyproject.toml
in clean-install checks. Update the release URL, lockfile and current packaging
instructions, while preserving historical phase records.

Keep independent-project attribution explicit: this is not an official DeepSeek
package. The supplied publisher record specifies release.yml and any environment;
that permits the workflow's pypi environment. Restricting trust to pypi remains
an optional account setting. No tag or publication is part of this rename.
