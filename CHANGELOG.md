# Changelog

## Unreleased

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
- No services or events implemented; no release published.
