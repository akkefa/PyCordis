# GitHub readiness

Phase 15 prepares the repository for contributor review and a future first
public release. Version `0.1.0` remains an unpublished alpha with partial
Cordis/Harness compatibility. No commit, push, tag, GitHub release or PyPI upload
is created by this phase.

## Repository checklist

| Required input | Location and purpose |
| --- | --- |
| Introduction and examples | `README.md`, `README.pypi.md`, `examples/` |
| Licensing and retained attribution | `LICENSE`, `THIRD_PARTY_NOTICES.md` |
| Change history | `CHANGELOG.md` |
| Contribution guidance | `CONTRIBUTING.md` |
| Generated-file exclusions | `.gitignore` |
| Package metadata and locked tools | `pyproject.toml`, `uv.lock` |
| Behavioral and compatibility tests | `tests/` |
| API contracts and design decisions | `docs/`, `docs/adr/` |
| Continuous integration | `.github/workflows/ci.yml` |
| Archive and installation verification | `scripts/check_distribution.py`, `scripts/check_installation.py` |

Source archives include contribution guidance. The wheel remains limited to
runtime modules, typing metadata and license notices. CI configuration stays in
the repository rather than the installed package or source archive.

## CI scope

One GitHub Actions job matrix runs on Python 3.11, 3.12 and 3.13 using
`ubuntu-latest`. Triggers are pushes to `main`, pull requests, and manual dispatch.
Each job installs the committed lockfile with the development and packaging
groups, then runs:

1. Full pytest suite with warnings treated as errors.
2. Ruff lint and formatting checks.
3. Strict mypy checks over runtime, tests, examples and scripts, using the matrix
   Python version.
4. A source distribution build and a wheel built from that source archive.
5. Archive contents, metadata, license and RECORD verification.
6. Strict Twine validation of both artifacts and their package-index description.
7. Wheel installation without dependencies into a fresh environment, followed by
   isolated public-API checks outside the checkout.

The build starts in a fresh checkout and produces one artifact pair, so CI can
use version-independent globs. Local work may retain old builds; use the exact
versioned paths in [packaging.md](packaging.md) and [CONTRIBUTING.md](../CONTRIBUTING.md).
The installed-wheel checker still intentionally validates the current release
version; update that assertion when preparing a new version.

Actions are pinned to verified commit hashes, uv is pinned to the locally tested
0.12.2, and dependency synchronization uses `--locked`. The workflow uses
read-only repository permissions and does not persist checkout credentials.
It has no release secrets or publication steps. Superseded runs are canceled,
but failures in one Python version do not cancel the other matrix jobs.

## Evidence and release boundary

Local validation covers the complete command sequence on macOS with Python
3.11.15, 3.12.13 and 3.13.13. Each version passes all 379 tests, static checks,
build/audit validation and isolated wheel checks. The workflow also passes
Actionlint validation. These results do not establish a successful GitHub-hosted
Linux run; that requires the workflow to be committed and pushed.

Before an actual release, review the first remote CI results, the changelog,
compatibility claims and versioned artifacts. Maintainer-controlled branch
protection and publishing permissions are repository settings, not changes made
by this phase. Publishing requires a separate explicit request.
The original Phase 0–15 implementation roadmap is complete; later work should
be selected as a named feature, compatibility gap or release task.

Workflow references: [uv's GitHub Actions integration](https://docs.astral.sh/uv/guides/integration/github/)
and [GitHub job matrices](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/run-job-variations).
