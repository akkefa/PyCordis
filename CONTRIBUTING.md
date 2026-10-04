# Contributing to deepseek-cordis

deepseek-cordis is an independent Python implementation of the Cordis runtime model
used by DeepSeek Harness. Its `0.1.0` API is alpha and compatibility is partial.
Start with [the mental model](docs/mental-model.md),
[the compatibility matrix](docs/compatibility.md), and
[the architecture decisions](docs/adr/0001-phase-0-foundation.md).

## Set up a checkout

Use Python 3.11, 3.12 or 3.13 and uv. From a local clone:

```sh
uv sync --locked --python 3.11 --group packaging
uv run --locked --group packaging python examples/first_plugin.py
```

The lockfile is committed. `dev` supplies test, lint and type tools; the opt-in
`packaging` group supplies Twine. Neither group adds runtime dependencies.
Do not update dependency versions as a side effect of unrelated changes. For an
intentional dependency change, update `pyproject.toml` and regenerate `uv.lock`.

## Make a focused change

Work one reviewed phase or issue at a time. Before changing runtime behavior,
inspect the pinned vendored Harness source and corresponding Cordis tests.
Describe the observed contract and how Python will express it, then add a
behavior test that exercises public APIs. Cover failure and cleanup paths when
resource ownership, cancellation or dependency activation changes.

Keep upstream fixes distinct from the primary compatibility target. Record
deliberate deviations in `docs/adr/`, and update the compatibility matrix and
source-indexed catalog when changing compatibility claims. Preserve source
attribution and third-party notices. Avoid framework and agent dependencies in
the kernel. Do not claim full Cordis parity or live Harness support from Python
unit tests alone.

Keep API guides and runnable examples aligned with behavior. Update the changelog
for user-facing changes. For design background, use the relevant existing ADR
rather than documenting a second conflicting contract.

## Check before proposing a change

Run the same checks as CI:

```sh
uv run --locked --group packaging pytest -W error
uv run --locked --group packaging ruff check .
uv run --locked --group packaging ruff format --check .
uv run --locked --group packaging mypy --python-version 3.11 src tests examples scripts
uv build
uv run --locked --group packaging python scripts/check_distribution.py \
  dist/deepseek_cordis-0.1.0-py3-none-any.whl dist/deepseek_cordis-0.1.0.tar.gz
uv run --locked --group packaging twine check --strict \
  dist/deepseek_cordis-0.1.0-py3-none-any.whl dist/deepseek_cordis-0.1.0.tar.gz
```

For a full local version matrix, set `export UV_PYTHON=3.12`, run
`uv sync --locked --group packaging`, then repeat the checks with mypy
`--python-version 3.12`. Repeat with `UV_PYTHON=3.13` and the matching mypy flag.
Keep `UV_PYTHON` set for every check so `uv run` uses the selected interpreter.
Use `unset UV_PYTHON` afterward to restore uv's normal selection. Synchronization
replaces the project environment when its Python version changes.
For wheel installation checks, follow [packaging.md](docs/packaging.md): use a
fresh environment containing only the built distribution, then run
`scripts/check_installation.py` outside the checkout with isolated Python imports.

CI runs on pushes to `main`, pull requests, and manual dispatch. It checks all
three Python versions on Linux, including a fresh wheel installation. Local
macOS results and GitHub-hosted results are reported separately. See
[GitHub readiness](docs/github-readiness.md) for the checklist and workflow scope.

## Propose a pull request

Describe the concrete problem, changed behavior, relevant source evidence and
Python-specific decisions. Include checks run, their Python versions, and any
remaining gaps. Keep changes conceptually focused and avoid unrelated refactors.
The maintainer reviews release decisions; preparing artifacts does not authorize
publishing them. In agent-assisted work, suggest a commit message and do not
commit or publish without the maintainer's explicit request.
