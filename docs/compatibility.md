# Compatibility status

Phase 1 implements only Context hierarchy and metadata views. Fiber, services,
effects and other runtime features remain unimplemented.
Primary target: Harness 639ed015397290b3745d163aafe02ffee4aa3f84.
Upstream baseline: 56b3d4f725681cf4556c1a8695a709cc3b6eed74.

| Feature | Status | Evidence / planned classification |
|---|---|---|
| Importable typed src package | Scaffold | Python packaging adaptation |
| Context hierarchy | Partial: implemented | Root/parent/owner and extend metadata; Python adaptation; no Fiber or proxy services |
| Fiber lifecycle | Future | fiber.spec.ts inertia locks, setup failure and cleanup; Harness regressions |
| Effects | Future | dispose.spec.ts manual/double disposal, generators, async/aborted setup; Harness regressions |
| Registry/plugin forms | Future | plugin.spec.ts functions, object apply, invalid/nested plugins, shared runtimes |
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
not applicable, or future work. All runtime rows except the Context foundation above remain future work.
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
shutdown, and no stale snapshots. No lifecycle or reactive-service claims are made in Phase 1.

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
