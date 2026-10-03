# ADR 0014: teach ownership before individual APIs

Status: accepted for Phase 13.

## Context

The Phase 12 checkout 8771fdeaaadbad339e6e37d257e3738f272bd677 has 379 passing
Python cases and an explicit compatibility catalog. Earlier guides retain wording
from their initial phases, while the README introduces many APIs without complete
beginner walkthroughs. That makes current support and lifetime boundaries harder
to understand.

## Decision

Use the README as an executable introduction: checkout installation, first plugin,
Service instance, declared dependency, reactive replacement, reversible cleanup,
owned events and fixed-argument waterfall. Copy complete entry-point code into its
Python blocks so snippets can be executed independently.

Add a mental-model guide explaining Context views, Fiber owners, shared callback
records, effect resources, service snapshots and caller scopes. Show mounted-child
lifecycle transitions and explicitly distinguish root restart from terminal child
disposal. Keep advanced contracts in their focused guides.

Provide five beginner examples and an ordered index for all 16 standalone examples.
Retain loader_plugins.py as an import fixture, not an entry point. Execute examples
and README Python blocks during this phase's verification. Retain the expected
validation-error log in the validation example and describe it in the index.

## Boundaries

Update stale guide wording and source attribution without changing runtime behavior.
Use the existing compatibility matrix rather than treating examples as parity tests.
The package remains version 0.0.0 and unpublished; packaging preparation is Phase 14.
No new runtime dependencies, tests duplicating documentation, or publication actions
are introduced here.
