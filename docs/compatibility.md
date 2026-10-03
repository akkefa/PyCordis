# Compatibility status

Phase 12 adds a source-indexed compatibility suite over the implemented Python
kernel and explicit loader. This is partial behavioral compatibility, not a claim
of full Cordis compatibility or DeepSeek Harness boot support.

Primary target: DeepSeek Harness `639ed015397290b3745d163aafe02ffee4aa3f84`,
vendored Cordis 4.0.4. Test baseline: upstream
`56b3d4f725681cf4556c1a8695a709cc3b6eed74`. Newer upstream tests are comparisons,
not silently substituted contracts.

## Current behavior matrix

| Cordis feature | PyCordis | Evidence / boundary |
|---|---|---|
| Context | Python adaptation | Root/parent/owner, immutable metadata views and subclass identity; no attribute/service proxies |
| Fiber lifecycle | Implemented scoped core | Serialized setup/unload/restart, owned child drain, retained failures and shielded waits; publication hooks future |
| Effects | Implemented with deviations | Callable/awaitable handles, sync/async generators, joined rollback; nested cleanup drains all after errors |
| Registry/plugin forms | Python adaptation | Functions, objects/apply, classes/start; original callbacks share runtimes, mounts own distinct Fibers |
| provide/get/set/require | Explicit Python APIs | Owned scoped slots and loaded snapshots; property traps, mixins and associated types future |
| inject/reactive reload | Implemented scoped core | Required bindings, startup gating, provider loss/restoration and joined snapshots; generations strengthen source uid epochs |
| Service | Python adaptation | Named self registration, start/check and native callability; transparent method tracing and prototype extension future |
| emit/parallel/serial/bail | Python adaptation | Owned listeners, snapshots, explicit filtering, all-settled parallel errors; emit/bail reject awaitables |
| waterfall | Python adaptation | Fixed arguments, veto and zero-argument continuation; async bridge and pinned repeated-next policy documented |
| isolate | Explicit Python labels | Scoped slots and shared ScopeLabel; explicit event filtering replaces source thisArg routing |
| intercept | Explicit configuration layers | Caller ContextVar, config merging and Service.matches_scope; automatic get/set/method interception future |
| Metadata/decorators | Explicit records | PluginMeta/PluginSpec/plugin-wide decorator; source method @Inject is not implemented |
| Configuration | Synchronous Python protocol | Defaults/transforms, raw/resolved config, reload validation and structured errors; Fiber.update/internal/config future |
| Loader | Explicit deterministic subset | Ordered references/rows, real Fibers, batch rollback/disposal; includes, expression trees, discovery, nested config groups and HMR future |
| Logger/association/tracing | Future | Python failure logs do not implement Cordis LoggerService, exporter, tracker or proxy contracts |

## Source-indexed evidence

[The readable catalog](compatibility-cases.md) and
[its structured data](compatibility-cases.json) enumerate all 61 literal tests
across the 11 core spec files at the pinned upstream commit, plus all 11 tests in
Harness's `packages/extensions/tool-cordis/tests/cordis-lifecycle.spec.ts` at the
pinned Harness commit. Each of the 72 records includes source commit, file, line,
exact test title, classification, Python evidence and remaining gaps. File SHA-256
fingerprints capture the inspected sources. Unrelated Harness integration suites,
loader suites, compile-time type fixtures and newer upstream specs are outside this
inventory; they are not assumed covered.

| Classification | Source cases | Meaning |
|---|---:|---|
| identical semantic behavior | 5 | The listed case's observed assertions are retained; API spelling/representation may differ |
| Python-specific adaptation | 43 | An explicit Python equivalent or deviation is recorded; some cases have only partial evidence |
| not applicable in Python | 2 | JS/Node-specific representation contracts, with a reason |
| future work | 22 | Full source behavior still needs unimplemented APIs or a port; partial related evidence may exist |

Coverage is tracked separately: 40 records have ports, 15 have partial evidence,
and 17 have no executable port. These are source-case bookkeeping counts, not a
compatibility percentage or counts of Python test invocations. A partial record
must not be described as a complete source test passing. In particular, property
association, retained-method tracing, logger naming, method decorators and
publication observers remain gaps despite related core tests passing.

## Running and maintaining the suite

```sh
uv run pytest -m compatibility
uv run pytest -W error
uv run ruff check .
uv run ruff format --check .
uv run mypy src tests examples
```

Phase 12 adds 23 behavioral cases in tests/compatibility/test_upstream.py and
test_harness.py, plus one catalog integrity check. The focused selection has 24
cases; the full suite has 379. Source ports include nested plugin listener
ownership, effect listener trees, ordinary error rollback, Service initialization
through an event, inactive snapshots, scoped activation, fixed-argument waterfall,
retained failures/logging, and reentrant parent/effect cleanup barriers.

The catalog integrity test checks pinned provenance, unique source records,
classifications/coverage consistency, source inventory counts, existence of linked
Python test definitions, and evidence links for every new behavioral port. It is
bookkeeping verification, not a behavioral port. It runs without either TypeScript
checkout or network access. To add a port, inspect the pinned body, update its
record and readable table, record deviations, and run the focused and full suites.

No TypeScript suite or live Harness boot was executed. Passing Python tests verify
this checkout's Python behavior only. [Historical phase notes](compatibility-history.md)
retain earlier evidence and counts; this page and the catalog are the current view.

## Intentional differences and remaining work

- Nested cleanup drains peers after failures; Python aggregates errors after draining.
- Binding generations detect same-provider replacements; the source same-uid inertia
  scenario is only partially equivalent at the public service API.
- Scope slots include service name and label, and require checks label boundaries.
- once guards recursive stale snapshots. Async waterfall bridges synchronous tails.
- Explicit caller scopes do not rebind Service.ctx or retained methods automatically.
- Metadata and validators belong to each mount; shared runtime inspection describes
  the first mount. Config adapters raise instead of returning JS schema envelopes.
- Batch failure rolls back owned mounts, while normal Python imports remain cached
  and module-level side effects cannot be undone.

Internal/plugin, internal/status, internal/service, internal/listener,
internal/config and internal/update producers/interceptors remain future work.
A passing structural parent cleanup port does not substantiate a publication-hook
race. Missing async-generator timer scenarios remain explicitly partial. General
background-task ownership, update/persistence, HMR, schema adapters and transparent
proxy/tracker behavior also remain future work.
