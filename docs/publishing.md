# Publish deepseek-cordis from a GitHub tag

The package is built and locally validated. `.github/workflows/release.yml`
implements production PyPI publishing when a pushed tag matches the package
version, for example `v0.1.0`. No package was uploaded while implementing this
workflow. The account and repository settings below must be configured first.

## One-time setup

1. Create or sign in to your PyPI account, verify its email address, and enable
   two-factor authentication. Keep the recovery codes in your own secure storage.
2. In the GitHub repository `akkefa/deepseek-cordis`, open Settings → Environments and
   create an environment named `pypi`. Ensure GitHub Actions can run the pinned
   actions used by the CI and release workflows.
3. For a first publication, open your PyPI account's
   [Publishing page](https://pypi.org/manage/account/publishing/) and add a pending
   GitHub publisher with these exact values:

   | Field | Value |
   | --- | --- |
   | PyPI project name | `deepseek-cordis` |
   | GitHub owner | `akkefa` |
   | Repository | `deepseek-cordis` |
   | Workflow filename | `release.yml` |
   | Environment | `pypi` |

   The filename excludes `.github/workflows/`. If you already own the PyPI project,
   add the same publisher from that project's Manage → Publishing page instead.
   A pending publisher creates the project on its first successful use. It does
   not reserve the name. The 2026-10-04 screenshot registered this distribution
   against the former repository `akkefa/PyCordis`, with environment `(Any)`.
   After renaming GitHub to `akkefa/deepseek-cordis`, replace the pending publisher
   to match the new repository as shown above. GitHub repository redirects do not
   update the publisher identity stored on PyPI. `(Any)` also permits the workflow's
   `pypi` environment; use the exact `pypi` value for environment-specific trust.
   Registration is not a completed publication or a name reservation.
4. Configure the `pypi` environment to allow release tags (`v*`). For fully
   automatic publishing, do not add required reviewers. Adding required reviewers
   intentionally makes each upload wait for approval. Environment options depend
   on the repository's visibility and GitHub plan.

Trusted Publishing uses GitHub's identity to obtain a short-lived upload token.
There is no `PYPI_API_TOKEN` secret to create or store. The publishing job alone
gets `id-token: write`. It runs in the configured `pypi` environment, separately
from tests and building, and downloads this run's checked artifact pair.

## Create a release

1. Update `[project].version` in `pyproject.toml`, refresh `uv.lock` with `uv lock`,
   and update the changelog and current documentation. For the first release,
   the prepared version is already `0.1.0`; replace its Unreleased heading with
   the actual release date when ready. Keep the alpha/partial-compatibility claims.
2. Commit and push the release workflow and version changes. Review the initial
   GitHub-hosted CI result before creating the tag.
3. Tag that exact release commit and push the tag:

   ```sh
   git tag -a v0.1.0 -m "deepseek-cordis 0.1.0"
   git push origin v0.1.0
   ```

   These are instructions for the maintainer; they were not executed as part of
   implementing publishing. A local tag does not trigger GitHub Actions until
   pushed. Creating the tag through GitHub's UI also targets a specific commit;
   that commit must contain the workflow and matching package version.
4. Watch the **Publish to PyPI** workflow in GitHub Actions. It validates the tag,
   reuses the full Python 3.11–3.13 CI matrix, builds and audits the distributions,
   and publishes them through the configured Trusted Publisher.
5. After success, check [the PyPI project](https://pypi.org/project/deepseek-cordis/) and
   install from the index in a clean environment:

   ```sh
   uv venv --no-project /tmp/deepseek_cordis-pypi-check
   uv pip install --python /tmp/deepseek_cordis-pypi-check/bin/python deepseek-cordis==0.1.0
   /tmp/deepseek_cordis-pypi-check/bin/python -I -c \
     "from importlib.metadata import version; import deepseek_cordis; print(version('deepseek-cordis'))"
   ```

The trigger is a pushed `v*` tag, not a published GitHub Release event. The workflow
publishes to PyPI; a GitHub Release page can be created separately for release
notes. New versions use a new matching tag. The clean-install checker reads the
checkout's package version, so it no longer needs a hardcoded version update.

## Failure behavior

- A mismatched tag or a branch reference fails before CI or publishing.
- Any failed matrix check or build prevents upload.
- A missing/mismatched Trusted Publisher fails authentication. Compare owner,
  repository, workflow filename and environment with the table above.
- Published filenames cannot be overwritten or reused. This workflow does not
  skip existing files silently. If an upload partially succeeds, inspect PyPI's
  files and the failed run before retrying; prepare a new version when replacement
  is needed. Do not move a published release tag to different source code.
- Local checks cannot establish that production authentication works. The first
  authorized tag publication verifies GitHub execution and PyPI trust end to end.

References: [PyPI pending publishers](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/),
[existing-project publishers](https://docs.pypi.org/trusted-publishers/adding-a-publisher/),
[Trusted Publishing workflow](https://docs.pypi.org/trusted-publishers/using-a-publisher/),
and [PyPI account help](https://pypi.org/help/).
