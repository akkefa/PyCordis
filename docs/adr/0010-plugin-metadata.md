# ADR 0010: explicit plugin declarations separate from identity

Status: accepted for Phase 9.

## Evidence

Target: DeepSeek Harness 639ed015397290b3745d163aafe02ffee4aa3f84,
vendored Cordis 4.0.4. registry.ts resolves function/class/object.apply identity,
Plugin.Base declares name, inject, provide, intercept and Config, and Inject.resolve
normalizes array/object dependencies. service.ts uses name/provide for a Service
binding. The inspected core does not implement a reusable flag.

Pinned upstream 56b3d4f725681cf4556c1a8695a709cc3b6eed74,
packages/core/tests/decorator.spec.ts, contains the @Inject on class method case. Class dependency declarations are
instead informed by registry.ts and service.spec.ts multiple injects. Its method
decorator creates a child
injection mount and uses context shadow rebinding; this is more than metadata.

## Decision

Use frozen PluginMeta snapshots, PluginSpec for explicit pairing, a decorator
that returns the original executable, and inspect_plugin for normalization.
Existing attributes remain supported. Explicit records are complete declarations;
ordinary Python inheritance replaces the source's additive class-decorator merge.
Store the first declaration on PluginRuntime and each mount's declaration on Fiber.
Identity belongs to the original callback and remains independent of declarations.

Inject requirements/config drive existing reactive lifecycle behavior. Provide
and intercept remain descriptive except for one provide-name fallback on Service.
Config is preserved for inspection and rejected on mount until Phase 10. Do not
add unrelated validators or dependencies.

## Consequences and compatibility classification

The metadata tests are Python adaptations, not a claim that the TypeScript
suite passes. They cover class/function declarations, immutable copies, explicit
inheritance/replacement, per-mount dependency configs, original callback sharing,
Service fallback, reserved validators and atomic failures. The apply getter is
resolved once per mount to keep metadata and executable identity consistent.

Automatic method injection, additive @Inject inheritance, prototype extension,
traced/shadow service rebinding, and internal publication hooks remain future work.
The declaration decorator deliberately exposes no method scheduling API. No
TypeScript suite or full DeepSeek Harness boot was run for this phase.
