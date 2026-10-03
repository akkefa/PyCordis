# ADR 0015: Prepare the first alpha distribution

- Status: accepted for Phase 14
- Date: 2026-10-03
- Reviewed base: `040c34962fd8dcbda5c7fedc64944b1c1037be8f`

## Context

Phases 0–13 establish a coherent public Python runtime and documentation, but
version `0.0.0` and planning metadata do not describe its current state. The
next requested phase prepares package artifacts without publishing them.

## Decision

Prepare `0.1.0` with alpha status and retain explicit partial Cordis/Harness
compatibility. Keep the zero-dependency runtime and no adapter extras. Use a
separate concise package-index README with absolute links. Select source archive
contents explicitly and include the typing marker and both license notices in
the wheel. Emit metadata 2.4 for compatibility with the installed Twine validator.
Keep Twine in an opt-in packaging dependency group rather than package extras.

Add independent standard-library archive and clean-install checkers. Verify
wheel RECORD hashes, source parity, metadata and licenses, then exercise the
installed public APIs outside the checkout on Python 3.11, 3.12 and 3.13.
The distribution build uses the source archive, so wheel generation also checks
that the selected source inputs are sufficient for building.

## Consequences

The first alpha can be reviewed and installed from local versioned artifacts.
Two README introductions need to stay aligned. Installation smoke checks do not
claim full-suite coverage on all Python versions. Phase 15 owns GitHub readiness
and CI. Package publication, credentials, tags and releases remain separate work.
See [packaging.md](../packaging.md) for reproducible checks and limitations.
