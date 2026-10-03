# Packaging PyCordis

Phase 14 prepares `0.1.0` as an alpha package. The Context/Fiber, plugin,
service, event, config and loader APIs form a tested, coherent starting point.
Cordis/Harness compatibility remains partial; see [compatibility.md](compatibility.md).
The artifacts are prepared locally and have not been published.

## Metadata and archive contents

`pyproject.toml` defines Python >=3.11, MIT licensing, author, Python 3.11–3.13
classifiers, project URLs, and the alpha development status. Runtime dependencies
and optional adapter extras are empty. The `dev` and opt-in `packaging` dependency
groups are maintainer tools, not installed package dependencies.

`README.pypi.md` supplies the package-index description with a complete first
plugin and absolute documentation links. `README.md` remains the repository
learning path. Keep their introductory example and compatibility claims aligned.
Links refer to the repository's `main` branch; they require these changes to land.

The pure-Python wheel contains runtime modules, `py.typed`, metadata, and both
`LICENSE` and `THIRD_PARTY_NOTICES.md`. The explicitly selected source archive also
contains tests, documentation, examples, verification scripts, the lockfile and
repository README. It excludes environments, caches and repository internals.
Both targets explicitly use core metadata 2.4: the installed Twine 6.2 validator
rejects the builder's current default 2.5. Version 2.4 retains the license
expression and license-file fields used here.

## Build and validate

From the repository root:

```sh
uv sync --locked --group packaging
uv run --locked --group packaging pytest
uv run --locked --group packaging ruff check .
uv run --locked --group packaging ruff format --check .
uv run --locked --group packaging mypy src tests examples scripts
uv build
uv run --locked --group packaging python scripts/check_distribution.py \
  dist/pycordis-0.1.0-py3-none-any.whl dist/pycordis-0.1.0.tar.gz
uv run --locked --group packaging twine check --strict \
  dist/pycordis-0.1.0-py3-none-any.whl dist/pycordis-0.1.0.tar.gz
```

The standard-library distribution checker compares archive contents with the
checkout, checks metadata and license payloads, verifies every wheel RECORD hash
and size, rejects unexpected files, and prints artifact SHA-256 hashes.
Twine independently validates metadata and the package-index description.
Select the exact versioned pair; older files in `dist/` are not release inputs.

## Verify the installed wheel

Use a new environment without development tools or dependencies. Substitute
absolute paths for the wheel, environment, and checker below:

```sh
uv venv --no-project --python 3.11 /tmp/pycordis-wheel-311
uv pip install --no-deps --python /tmp/pycordis-wheel-311/bin/python \
  /absolute/path/to/PyCordis/dist/pycordis-0.1.0-py3-none-any.whl
cd /tmp
/tmp/pycordis-wheel-311/bin/python -I \
  /absolute/path/to/PyCordis/scripts/check_installation.py
```

Repeat with Python 3.12 and 3.13 and distinct environment paths. `-I` excludes
checkout and user import paths. The checker requires the installed module to
live inside the environment, version `0.1.0`, only the PyCordis distribution,
a non-editable wheel install, no runtime dependencies, public exports and the
typing marker. It exercises validation, consumer-before-provider loading,
service injection, event delivery and cleanup through installed public APIs.

Phase 14 verification passed the 379-test suite on Python 3.11.15 and clean wheel
installation checks on Python 3.11.15, 3.12.13 and 3.13.13. These installation
checks are smoke checks; a full multi-version CI matrix belongs to Phase 15.

## Publication boundary

No upload, tag, commit or release is created by these checks. A read-only PyPI
JSON lookup on 2026-10-03 returned HTTP 404 for `pycordis`; that does not reserve
the name or establish publishing permissions. Publication requires a separate
explicit request and fresh verification of package ownership and release state.

References: [PyPA metadata guide](https://packaging.python.org/en/latest/guides/writing-pyproject-toml/)
and [uv package guide](https://docs.astral.sh/uv/guides/package/).
