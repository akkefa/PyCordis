# Changelog

## 0.1.0 — Unreleased

- Phase 15: GitHub Actions checks for Python 3.11, 3.12 and 3.13; locked tools,
  warnings-as-errors tests, lint/format/type checks, builds, distribution audits,
  strict metadata validation and isolated wheel installation.
- Expanded contribution guidance and GitHub readiness checklist. Source archives
  now include CONTRIBUTING.md; runtime behavior and dependencies are unchanged.

- Added opt-in packaging tools, strict metadata validation, and reproducible
  archive and clean-wheel installation checkers.

- Phase 14: alpha package metadata/version, project URLs, package-index README,
  explicit source archive contents, distribution integrity checks and clean wheel
  installation verification. Zero runtime dependencies and no implemented extras.
- Package artifacts are prepared locally; nothing is uploaded or published.

- Phase 13: README ownership-first walkthrough, checkout installation, services,
  dependency/reactive lifecycle, effects, events, waterfall and lifecycle diagram.
- Mental-model guide, ordered index for 16 runnable examples, five beginner examples,
  current guide wording and attribution; no runtime behavior changes.

- Phase 12: 23 pinned-source behavioral compatibility cases and a catalog integrity
  check; 72 classified source tests with commits, lines, fingerprints and Python
  evidence. Current compatibility matrix replaces stale status with explicit gaps.
- Historical phase evidence moved to compatibility-history.md; pinned decorator
  source wording corrected. No runtime behavior changed and no full parity claim made.

- Phase 11: separate deterministic Loader, PluginEntry records/config rows, explicit
  Python imports, batch ownership and actual Fiber inspection, preflight/rollback,
  dependency settlement and cancellation cleanup; 34 new cases, guide, ADR and example.
- Discovery, file formats, nested configuration groups, expressions/update hooks
  and HMR remain deferred. No runtime dependencies added.

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
