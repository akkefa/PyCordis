# ADR 0001: Phase 0 foundation

Status: accepted for scaffold; runtime design remains proposed.

## Context

The project starts with an MIT license and title-only README. The compatibility
reference is a patched Harness Cordis snapshot, not upstream main. Modern
Python and minimal dependencies are requested.

## Decision

Use Python >=3.11, src/pycordis, uv with a committed lockfile, Hatchling for
builds, pytest/pytest-asyncio, Ruff and strict mypy. Keep runtime dependencies
empty and the scaffold version at 0.0.0 until an actual tested API exists.
Preserve the existing MIT license and include reference licenses in notices.
Pin primary Harness and secondary upstream commits in source documentation.
Create only package marker files and an import test now.

## Alternatives

uv's own backend is available; Hatchling provides a familiar independent Python
build surface. Python 3.12+ narrows support unnecessarily at this stage. A full
module tree creates placeholders that imply APIs before their design is reviewed.

## Consequences

A built/imported scaffold says nothing about runtime readiness. Lockfile/tool
versions are reproducible, but supported interpreters require later CI checks.
No publication, Git commits, or major runtime phases occur in this increment.

## Compatibility impact

No runtime behavior exists, so there is no semantic deviation yet. Service
lookup, loop binding, root shutdown, cleanup failures and async dispatch policies
remain explicitly proposed in architecture.md for review at their own phases.
