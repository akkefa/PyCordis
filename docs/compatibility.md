# Compatibility status

Phase 4 implements Context views, Fiber lifecycle, reversible effects and
plugin registry. Services and events remain unimplemented.
Primary target: Harness 639ed015397290b3745d163aafe02ffee4aa3f84.
Upstream baseline: 56b3d4f725681cf4556c1a8695a709cc3b6eed74.

| Feature | Status | Evidence / planned classification |
|---|---|---|
| Importable typed src package | Scaffold | Python packaging adaptation |
| Context hierarchy | Partial: implemented | Root/parent/owner and extend metadata; Python adaptation; no Fiber or proxy services |
| Fiber lifecycle | Partial: implemented | State/epoch transitions, setup/cleanup, ownership, restart/disposal; no services/publication events |
| Effects | Implemented with explicit deviations | Manual/automatic, generators, rollback and in-flight joins; drain-all and Python finalization differ |
| Registry/plugin forms | Implemented with Python adaptations | Functions, callable objects, apply methods, classes, nested mounts, shared runtimes |
| Services and injection | Future | service.spec.ts, reflect.spec.ts; required-service snapshot and inactive access |
| Reactive reload | Future | fiber.spec.ts provider disposal/loading races; isolate.spec.ts service restoration |
| Events | Future | events.spec.ts modes/filtering/errors; preserve zero/empty-string bail |
| Isolation/intercept | Future | isolate.spec.ts independent/shared labels and filtered events |
| Traced service methods | Future | shadow/associate/invoke suites; Python adaptation required |
| Decorators/metadata | Future | decorator.spec.ts; explicit Python declarations to evaluate |
| Config validation/lazy resolution | Future | Harness fiber.ts and boot integration tests |
| Loader/volatile config | Future | Separate loader; documented Harness patches |
| JS cross-realm Symbol brand, Proxy machinery | Not mechanically portable | Behavioral equivalents where needed; JS-specific representation inapplicable |

## Test adaptation plan

Each future ported test must record source commit, file and test title and one
classification: identical semantic behavior, Python-specific adaptation,
not applicable, or future work. Context and low-level Fiber are partially implemented; effects are implemented
with documented deviations. Other runtime rows remain future work.
Do not label tests implemented merely because their source was read.

Start with pinned upstream test bodies, then add Harness-specific regressions:
reentrant owner restart waits for setup and cleanup; sync setup rollback removes
owner entry; async rollback is joined; public synchronous disposal is single-shot;
cleanup-time effect creation is rejected; PENDING/LOADING registration is legal;
observer-added dependencies resolve before activation; publication failure rolls
back ownership; teardown observers cannot starve peers; loading parent joins
child teardown; unpublished pending child never executes after parent disposal.

Current upstream tests for duplicate waterfall continuation, failed-fiber latch,
wrapper identity and update result are comparison tests, not automatically the
Harness contract. Use explicit review before adopting these fixes.

The v0.1 milestone will need provider removal/restoration with a new identity,
listener/resource/child/task cleanup, setup errors, reentrant and concurrent
shutdown, and no stale snapshots. Phase 2 claims only the lifecycle behavior tested below; no reactive-service claim.

## Phase 1 evidence

`tests/test_context.py` adapts `vendor/cordis/src/context.ts` constructor and
extend at the pinned Harness commit. Root identity, inherited entries,
shadowing, shallow entry copying and shared ownership preserve the intended
observable foundation. The source copies JS property descriptors; Python
instead copies plain mapping entries. JS getters/symbol metadata are not
implemented. Metadata is namespaced and read-only in Python; relationships
are protected properties rather than shadowable metadata entries.

Pinned upstream `packages/core/tests/reflect.spec.ts`, test `service injection`,
uses `ctx.extend({baz: 2})` before mounting a child. Its metadata inheritance is
adapted; service lookup and mounting remain future work. `plugin.spec.ts`,
`nested plugins`, remains future work in full because it tests listeners and
child Fiber disposal, neither implemented here. No TypeScript suite was run.

Phase 1 adds 24 Context test cases plus the original import test. They exercise
roots, parent chains, owner identity, shallow mapping copies, shared mutable
values, explicit false/None shadowing, read-only APIs, collision isolation,
invalid inputs, subclass type preservation and asynchronous sibling views.
These do not substantiate Fiber cleanup, reactive injection or global shutdown.

## Phase 2 evidence

All of `tests/test_fiber.py` is classified as Python-specific adaptation because
mounts use direct Fiber and private epochs, not the original registry/services.

| Source behavior | Tests / status |
|---|---|
| fiber.ts FiberState, constructor/root branch | root identity, numeric enum, child ownership |
| upstream fiber.spec.ts inertia lock 1/2/3 | pending/loading/unloading epoch races adapted; real provider tests future |
| upstream fiber.spec.ts plugin error / dispose error | setup rollback/retained error and contained cleanup failures adapted |
| upstream plugin.spec.ts nested plugins / root dispose | direct child draining and root restart adapted; listener/registry portions future |
| Harness cordis-lifecycle.spec.ts pending work and child ownership | pending callback drain, checkpoint invalidation, parent joining child adapted |
| Harness full effect barriers, publication observers | Effect barriers added in Phase 3; event publication remains future |
| newer upstream failed-fiber latch | Intentionally not adopted; Harness epoch refresh can retry |
| Python cancellation/loop/reentrant semantics | additional tests for shielded waiters, setup cancellation, cross-loop rejection and explicit cycle errors |

Phase 2 added 30 Fiber cases to 25 existing cases. Phase 3 adds effect composition.
Service snapshots, config hooks, internal status/plugin
notifications and registry identity remain future work. Tests inspect absence of
leftover transition Tasks only after the tested complete shutdown scenario;
there is no general background-task ownership API yet.

## Phase 3 evidence

29 effect cases in test_effects.py adapt pinned upstream dispose.spec.ts (manual,
plugin-owned, yielded, async return/yield, aborted setup and setup errors) and
Harness cordis-lifecycle.spec.ts (reentrant owner restart, async rollback,
in-flight visibility, single-shot public cleanup and registration guards).
No TypeScript tests were executed. Total Python suite: 84 passing cases.

Identical intended behavior: immediate sync setup/cleanup, single-shot public
handle, registration before setup, joined structural cleanup, rollback, reverse
collected cleanup, PENDING/LOADING legality and UNLOADING rejection.
Python-specific adaptation: scheduled async startup, callable-awaitable handles,
immutable metadata snapshots, explicit loop/cycle errors, same-owner transfers,
Python generator finalization and shielded waiters.
Intentional semantic deviation: nested callback failures do not stop cleanup;
remaining callbacks drain, then one original or a grouped error is raised.
Future work: registry-based mounting, public service injection, internal events,
service visibility, user background-task ownership helpers and advanced tracing.

## Phase 4 evidence

26 cases in tests/test_registry.py adapt registry.ts/fiber.ts at Harness
639ed015397290b3745d163aafe02ffee4aa3f84 and plugin.spec.ts at upstream
56b3d4f725681cf4556c1a8695a709cc3b6eed74. Source test themes: function plugin,
object plugin, class plugin, invalid plugin, nested plugins, root dispose,
plugin error and multiple mounts. Tests replace source listener assertions with
owned effects; event assertions remain future work. No TypeScript suite was run.
Total Python suite: 110 cases.

Retained behavior: one runtime per executable callback, distinct Fibers/configs
per mount, scoped child ownership, first-runtime naming, immediate unregister,
restart retaining the record, failed setup retaining the record until disposal,
and delete requesting disposal of all mounted Fibers.
Python adaptations: callable-instance precedence, instance/function identity for
Python bound methods, optional class start() instead of Symbol-based init,
immutable inspection tuples, explicit parent in Registry.mount and actual
awaitable Fiber instead of a PromiseLike facade. Async startup remains scheduled.

Additional safety cases cover unhashable/equal callable instances, cross-root
mount rejection, invalid apply getters, mount atomicity, owner-state guards and
remount during old teardown. These are Python-specific regression coverage.
Nonempty inject and Config declarations raise NotImplementedError until their
phases. Dependency epochs, schema validation, internal notifications, Config
metadata and event filters are not claimed by registry coverage.
