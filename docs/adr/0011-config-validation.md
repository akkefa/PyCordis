# ADR 0011: synchronous library-independent configuration validation

Status: accepted for Phase 10.

## Source evidence

Target: DeepSeek Harness 639ed015397290b3745d163aafe02ffee4aa3f84,
vendored Cordis 4.0.4, fiber.ts resolveConfig, ValidationError and _reload.
The source applies Standard Schema synchronously, rejects promise results,
aggregates issue messages/paths, preserves input without a schema, and resolves
config after a checkpoint under an injected-service snapshot before plugin execution.
Restart validates raw input again. Failure enters existing unload/error handling.

Harness packages/web/tool-web/src/index.ts declares defaults in Config before its
apply callback. packages/spill/spill-local/src/index.ts uses static Config to supply
cleanupPeriodDays before LocalSpillStore construction. Boot config-reload.spec.ts
constructs a Standard Schema fixture. These justify default/transform support through
a validator, rather than coupling Python to one schema library. The internal/config
expression waterfall and update hooks require additional loader integration.

## Decision

Export ConfigValidator with synchronous validate(value) returning the normalized
value directly. Export ValidationIssue and ValidationError for optional structured
diagnostics. Preserve other exception identities rather than wrapping schema bugs.
Resolve a callable before mount allocation, then invoke it once per valid activation.
Store original raw input separately from the latest successful resolved config.
Apply the per-mount metadata declaration, preserving Phase 9 independent manifests.

Do not add runtime dependencies. Reject awaitable validator results, closing native
coroutines but leaving independently owned Tasks/Futures alone. Recheck the lifecycle
epoch after validation to prevent disposed work from entering setup.

## Compatibility classification and limits

The new tests are Python-specific adaptations of the source configuration/lifecycle
behavior. Python adapters raise instead of returning Standard Schema issue envelopes.
Per-mount validators follow the existing explicit metadata design; source Config is
stored on the shared runtime. Immutable field/index paths replace JavaScript issues
and cross-realm symbol branding. The full TypeScript suite and Harness boot were not
executed. Internal/config, internal/update, Fiber.update, loader expressions and
schema-aware intercept merging remain future work.
