# Changelog

## Unreleased

- Phase 10: synchronous ConfigValidator protocol, structured ValidationIssue /
  ValidationError, raw and resolved Fiber config, validation before each valid
  activation, failure cleanup/restart recovery, 27 new cases, guide, ADR and example.
- No schema runtime dependencies; async validation, loader expression/update hooks
  and schema-aware operation config merging remain future work.

- Phase 9: immutable PluginMeta, PluginSpec, identity-preserving plugin_meta
  decorator, inspect_plugin, per-runtime/per-mount snapshots, Service provide-name
  fallback, 30 metadata cases, guide, ADR and runnable example.
- Explicit declarations replace conventional attributes; provide/intercept remain
  descriptive for generic plugins. Validator execution and automatic method
  injection remain deferred.

- Phase 8: identity ScopeLabel isolation, slot-specific reactive notifications,
  owned bindings separated from dependency snapshots, inherited/copied intercept
  mappings and inject config, Service config merge/filter helpers, task-local
  caller scopes across setup/cleanup/events, 31 scope test cases, docs and example.
- Deliberate scope strengthening: slots key by service name plus label; require
  verifies snapshot labels to prevent crossing changed isolation boundaries.


- Phase 7: scoped Events facade, owned on/once, prepend/global/filter options,
  emit/parallel/serial/bail/waterfall, dispatch diagnostics, 57 event test cases,
  guide, ADR and runnable example.
- Python event policy: emit/bail reject awaitable results; async waterfall bridges
  synchronous tails; once guards recursive stale snapshots. Async dispatch is
  caller-owned and cancellable, distinct from shielded Fiber lifecycle waits.


- Phase 6: exported Service base class with declared/overridden name, defining
  context, original config, owned registration, start/check hooks and native
  callable subclasses; 25 service-class cases, guide, ADR and runnable example.


- Phase 5: owned service bindings, get/set/require, reactive inject declarations,
  activation/cleanup snapshots, provider availability notifications, joined
  dependent teardown, 41 service cases, guide, ADR and runnable example.
- Intentional compatibility strengthening: binding generation epochs detect
  same-provider replacement during loading; structural ancestors are excluded
  from service-removal joins to prevent awaiting their own cleanup.


- Phase 4: root-local Registry, Context.plugin mounting, shared PluginRuntime
  inspection, function/object/class forms, synchronous unregister with joined
  teardown, 26 registry test cases, guide, ADR and runnable example.

- Phase 3: Context/Fiber effects, nested sync/async collection, rollback and
  joined in-flight cleanup, immutable diagnostics, 29 effect test cases and docs.
- Deliberate compatibility deviation: drain remaining nested cleanup callbacks
  after errors, then report single/aggregated failures.

- Phase 2: root and mounted Fiber ownership, serialized lifecycle epochs,
  setup/cleanup rollback, await/restart/disposal, reentrancy/cancellation policy,
  30 Fiber tests, guide, ADR and example.

- Phase 1: public Context with root/parent/owner identity, read-only inherited
  metadata, shallow-copy extend, Context tests, guide, example and design ADR.

- Phase 0: source audit, compatibility plan, uv-managed typed package scaffold,
  development checks, and import smoke test.
- Kernel event publication hooks, advanced method reflection and tracing remain future work; no release published.
