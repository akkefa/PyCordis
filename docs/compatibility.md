# Compatibility status

Phase 11 implements explicit deterministic loading, synchronous configuration validation, explicit plugin metadata plus Context/Fiber/effects, registry, scoped reactive services,
Service classes, events and explicit intercept config/caller scopes. Kernel event
hooks, automatic method injection, loader config resolution and proxy tracing remain unimplemented.
Primary target: Harness 639ed015397290b3745d163aafe02ffee4aa3f84.
Upstream baseline: 56b3d4f725681cf4556c1a8695a709cc3b6eed74.

| Feature | Status | Evidence / planned classification |
|---|---|---|
| Importable typed src package | Scaffold | Python packaging adaptation |
| Context hierarchy | Partial: implemented | Root/parent/owner and extend metadata; Python adaptation; no Fiber or proxy services |
| Fiber lifecycle | Partial: implemented | State/epoch transitions, setup/cleanup, ownership, restart/disposal; no services/publication events |
| Effects | Implemented with explicit deviations | Manual/automatic, generators, rollback and in-flight joins; drain-all and Python finalization differ |
| Registry/plugin forms | Implemented with Python adaptations | Functions, callable objects, apply methods, classes, nested mounts, shared runtimes |
| Services and injection | Implemented with isolation labels | Owned bindings, scoped snapshots/notifications, reactive inject with config |
| Service abstraction | Implemented core with Python adaptations | Constructor-owned instance, start/check, native callable subclasses; advanced helpers deferred |
| Reactive reload | Implemented for scoped bindings | Provider loss/restoration, generation epochs and isolated loading/unloading races |
| Events | Implemented public dispatch with Python policies | Owned listeners, five modes, explicit filtering, error groups; kernel hooks future |
| Isolation/intercept | Implemented explicit core | Identity labels, config layers/merge, Service predicates and ContextVar callers; proxy tracing future |
| Traced service methods | Future | shadow/associate/invoke suites; Python adaptation required |
| Decorators/metadata | Python adaptation | Immutable explicit records and identity-preserving plugin decorators; automatic method injection future |
| Config validation/lazy resolution | Python validation adaptation; lazy loader resolution future | Synchronous protocol, defaults/transforms, reload/failure handling; internal/config and update hooks deferred |
| Loader/volatile config | Explicit ordered Python loader; advanced features future | Real Fiber ownership, preflight/rollback; volatile config, nested groups and HMR deferred |
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

## Phase 5 evidence

41 test_services.py cases adapt Harness reflect.ts/fiber.ts/registry.ts at
639ed015397290b3745d163aafe02ffee4aa3f84. Pinned upstream baseline
56b3d4f725681cf4556c1a8695a709cc3b6eed74 supplies these source test themes:

| Source test | Python coverage / classification |
|---|---|
| reflect.spec.ts: access check | Duplicate registration and owner-only set; require substitutes explicit snapshot access for attributes |
| reflect.spec.ts: service injection | Owned provide/get/set and child inherited snapshots; mixins and tracing future |
| reflect.spec.ts: service inject leak | Disposed/inactive required snapshot rejection; Python adaptation |
| service.spec.ts: pending inject | Loading provider blocks consumers; uses owned provide instead of future Service class/events |
| service.spec.ts: multiple injects | Multi-requirement activation and transitive loss/restoration; Python adaptation |
| fiber.spec.ts: inertia lock 1/2/3 | Real binding changes during loading/unloading; Python Event barriers replace timers |
| Harness lifecycle ownership rules | Shutdown joins dependent cleanup, cancelled waiters preserve owned removal, stale checkpoint skips setup |

Total Python suite: 151 passing cases. No TypeScript suite or live Harness boot
integration was executed. Older phase evidence above describes historical scope.

Retained: duplicate bindings rejected, registration is an owned effect, strict
get returns only ACTIVE providers, get bypasses injection requirements, set is
owner-only and does not reload, missing requirements settle PENDING, activation
publishes services, dependency loss unloads, restoration reloads, old snapshots
survive cleanup, failed consumers can retry on notification, predicate failures
are logged and block consumers.

Python adaptations: explicit require rather than attribute Proxy access, immutable
ordered dependency tuples, list/tuple or name-to-None maps, synchronous predicate
closures, refresh_services for predicate changes, None for missing services,
scheduled async removal, and explicit loop affinity. Root/ancestor-owned bindings
are available through require without redeclaration, following source store walks.

Intentional strengthening: epochs use unique binding generations instead of
provider uids, preventing stale activation when the same provider replaces its
binding during loading. Removal skips joining structural ancestors and current
execution owners because they already own that teardown; this prevents cyclic
self-joins during root shutdown. Other affected consumers are joined before the
provider snapshot entry is released. Existing drain-all nested cleanup applies.

Future: Service abstraction (Phase 6), accessor/mixin/property syntax, tracing,
isolation/intercept labels/config, optional dependencies, event notifications,
config validation and terminal Context disposal. Mapping intercept values fail
explicitly rather than being silently ignored. Services share a single root scope;
Context.extend only inherits metadata/ownership and does not isolate bindings.

## Phase 6 evidence

25 test_service.py cases adapt service.ts/fiber.ts at Harness
639ed015397290b3745d163aafe02ffee4aa3f84 and service.spec.ts at upstream
56b3d4f725681cf4556c1a8695a709cc3b6eed74. Total Python suite: 176 cases.
No TypeScript suite or live Harness boot integration was executed.

| Source behavior/test | Coverage and classification |
|---|---|
| service.ts constructor / named provider | Self registration by identity and owned removal; Python name declaration and config adaptation |
| service.spec.ts: pending inject | Async start gates consumers until ACTIVE; Event barrier substitutes event listener |
| service.spec.ts: multiple injects | Service-class chain activates, unloads and restores with fresh instances |
| service.spec.ts: compare snapshot | Owned effects/registry drained after disposal; nested child consumer starts after parent activation; event-hook snapshot future |
| service.ts check symbol / reflect.ts predicates | Bound synchronous check gates consumers, failures logged; explicit refresh_services |
| service.ts invoke / hasInstance | Native __call__ and isinstance; proxy-aware identity machinery not applicable |
| service.spec.ts: traceable effect with/without inject | Explicit declared get/require and ordinary method ownership exercised; trace wrappers NOT implemented |

Additional Python regressions cover config identity, inherited/overridden names,
invalid names, duplicate provider rollback, constructor/start failures, effect
collection from start, cancelled startup waiters, disposal during startup, manual
registration removal, cleanup errors and fresh instances on restart.

Retained core: constructor immediately registers self using an owned effect,
class initialization precedes ACTIVE publication, inherited dependency declarations,
availability predicate, owned cleanup and reactive restoration. Python adaptations:
Service(ctx, config=None, *, name=None), string class name, start/check in place of
Symbols, native callability/type checks, read-only defining ctx/config and public
registration handle. Name is ordinary instance data: mutating it does not rename
the registered binding. A direct constructor does not call start, matching source
separation of construction from class-plugin initialization.

Deferred: Service filter/extend helpers, interceptor config merge, decorators/init
hook metadata, callable proxy tracing and caller-context association. Services
remain unwrapped Python objects with a defining context. Events are Phase 7.

## Phase 7 evidence

57 test_events.py cases adapt Harness events.ts at
639ed015397290b3745d163aafe02ffee4aa3f84 and upstream events.spec.ts at
56b3d4f725681cf4556c1a8695a709cc3b6eed74. Total Python suite: 233 cases.
No TypeScript suite or live Harness integration was executed.

| Source test/behavior | Python coverage/classification |
|---|---|
| ctx.on() / ctx.once() | Owned registration, manual removal, repeated calls and lifecycle cleanup; Effect return adapts disposer |
| ctx.parallel() | Concurrent callbacks, all-settled sync/async errors, explicit filter; ExceptionGroup adapts AggregateError |
| ctx.emit() | Inline notification, errors stop subsequent callbacks; async results deliberately rejected |
| ctx.serial() / ctx.bail() | Ordered first meaningful result/error; identity checks preserve zero/empty bail values |
| ctx.waterfall() | Before/after order, fixed arguments, zero-argument continuation, veto; async bridge is Python adaptation |
| dispatch filtering / EventOptions | Explicit filter_(registering_context), prepend, global_ bypass; no JS this binding |
| internal/dispatch | Telemetry before public snapshot, no internal-event recursion; parallel retains historical emit mode |

Additional cases cover snapshot mutation, duplicate callback ownership, recursive
and concurrent once, listener cleanup on provider loss/startup failure/restart,
PENDING registration and inactive guards, dispatch cancellation, async callable
waterfall, returned awaitables, self-settling handles and indirect awaitable cycles.

Retained: callback snapshots, prepend order, root-shared listener storage, owned
removal, synchronous errors stopping emit/bail, all-settled parallel aggregation,
serial bail, fixed waterfall args and veto. Repeated next calls preserve the
pinned shared-queue/terminal-repeat behavior; newer upstream guards are not adopted.

Python adaptations: strings for event names, keyword options, scoped Events
facades, owned Effect handles (no disposer bool result), explicit filter_ rather
than thisArg/Context.filter, immutable diagnostic argument tuples and filter
predicate in the fourth diagnostic slot. parallel raises ExceptionGroup even for
one failure; cancelled listeners use BaseExceptionGroup. Cancelling an async
dispatch cancels its awaited callbacks and runs Python finally blocks. It does
not dispose listener registrations or shield dispatch work like Fiber settlement.

Intentional policies: emit/bail reject and close returned bare coroutines, instead
of scheduling/ignoring Promise results. Already-created Tasks/Futures remain caller
owned. Async waterfall continuations bridge sync tails and flatten nested awaitable
results; self-settling Effect/Fiber handles are preserved and indirect cycles raise.
Once guards against invocation twice through an outer stale snapshot, strengthening
the source wrapper's removal-only behavior under reentrant dispatch.

Deferred: internal/listener interception, scoped internal/update routing, kernel
plugin/status/service/config notifications, proxy get/set events and telemetry
this binding. Scope/isolation/interception is Phase 8. Event filters already supply
an explicit callback-context seam; they do not establish isolation labels.

## Phase 8 evidence

31 test_scope.py cases adapt Harness context.ts/reflect.ts/service.ts/registry.ts
at 639ed015397290b3745d163aafe02ffee4aa3f84. Source suites at upstream baseline
56b3d4f725681cf4556c1a8695a709cc3b6eed74 supply isolation/config themes.
Total Python suite: 264 cases. No TypeScript suite or live Harness integration ran.

| Source behavior/test | Python coverage / classification |
|---|---|
| isolate.spec.ts: isolated context | Independent labels hide default provider; scoped activation/removal/set; explicit get/require adaptation |
| isolate.spec.ts: shared label | ScopeLabel reuse joins views, duplicate rejection, both consumers unload |
| isolate.spec.ts: isolated event | Service.matches_scope explicitly filters listeners; global option bypass preserved |
| context.ts extend/isolate/intercept | View ownership, inheritance, copied entries and ancestor precedence |
| service.ts resolveConfig | Base/intercepts/head order, fresh dict, custom merge_config hook; explicit caller API replaces tracing |
| registry.ts Inject.resolve / Fiber constructor intercept map | Per-mount injection mappings layer over ancestor config and preserve callback identity |
| invoke.spec.ts / logger.spec.ts intercept themes | Explicit async operation caller scope tested; callable proxies/logger tracing future |

Additional cases cover matching-label replacement during async cleanup, isolated
provider disposal, root boundaries, multiple same-owner slots, label reuse across
names, scope restoration after exceptions/cancellation, concurrent requests,
async setup/cleanup, registering effect views, dispatcher callback views and
consumer-context availability checks. The Phase 5 deferred-config test now verifies
invalid non-mapping config rejection; valid mappings are implemented.

Retained core: one-service label isolation, shared labels, unchanged ownership,
other services inherited, scoped notifications, snapshots retained through cleanup,
ancestor-first config merge and explicit event-filter behavior.
Python adaptations: ScopeLabel objects, immutable copied mapping layers, string-key
configs, resolve_config/merge_config helpers, Context.scope/current_context using
ContextVars. Explicit ctx overrides active caller, then defining context is fallback.
Service method ctx/ownership are not rebound. Setup/cleanup activate their defining
views; predicates activate consumer views; events activate dispatcher views.

Intentional strengthening: slots key by (service name, label), preventing the
source's label-only cross-name aliasing. require verifies snapshot labels and does
not cross an isolation boundary, including changed views of the same Fiber. Owned
slot maps prevent same-owner provisions from overwriting dependency snapshots.
Default labels are created lazily on inspection/lookup as well as provision.
Config entries are shallow-copied; nested object identities remain shared.

Deferred: transparent attribute proxies, automatic method shadow/rebinding,
Service prototype extension, cross-realm brands, Config-schema merge/validation,
plugin metadata decorators, and internal kernel event producers/interceptors.
Interception here means service-specific config resolution; it is not an automatic
hook on every get/set or arbitrary operation. Middleware dispatch is still explicit.

## Phase 9 evidence

The pinned Harness registry.ts Plugin.Base/Inject.resolve/callback resolution and
service.ts name/provide fallback guide metadata normalization. Thirty new cases in
tests/test_metadata.py are Python-specific adaptations: copied/frozen declarations,
legacy attributes, decorator identity/inheritance, independent mount requirements,
Service fallback, Config rejection, atomic errors and one apply-getter resolution.
The full Python suite has 294 cases. No TypeScript suite or Harness boot was run.

Pinned upstream decorator.spec.ts class injection motivates explicit inject
declarations. Python declarations are authoritative complete replacements rather
than additive @Inject inheritance. Its method injection test remains future work
because it requires child mounting and context shadow rebinding. No reusable flag
or singleton mount behavior is inferred from unused conventions. Provide/intercept
are descriptive for general plugins; configuration validation is Phase 10.

## Phase 10 evidence

Twenty-seven new cases in tests/test_config.py adapt Harness fiber.ts
resolveConfig/ValidationError/_reload: identity passthrough, defaults and transforms
before Service construction, structured paths, dependency-delayed validation, caller
scope, failed validation cleanup, retained errors, restart/recovery, provider
restoration, independent validators, awaitable rejection and disposal checkpoints.
The existing invalid-Config metadata/registry cases now assert protocol errors.
The Python suite totals 321 passing cases.

Harness tool-web Config defaults and LocalSpillStore static Config demonstrate
normalization before setup/constructors. Python validators return values directly
and may raise ValidationError; no Standard Schema envelope or JavaScript symbol
brand is emulated. Per-mount validators follow Phase 9 rather than the source
shared runtime Config. No TypeScript suite or full Harness boot was executed.
Internal/config expressions, internal/update, Fiber.update and schema library
adapters remain future work.

## Phase 11 evidence

Thirty-four new cases in tests/test_loader.py adapt explicit source EntryOptions,
Entry._init import/mount and actual-Fiber retention, plus group ownership from the
pinned Harness loader. They test Python imports/cache/reference validation, mapping
rows/disabled/duplicate entries, ordered mounting, independent batches, provider
chains, missing services, failure rollback, owned listeners/children/resources,
cancellation joins and parent-scoped disposal. The Python suite totals 355 cases.

All cases are Python-specific adaptations. Atomic batch rollback strengthens source
import-failure logging. A structural owner provides grouping without serialized
nested tree behavior. Module side effects remain outside rollback. No TypeScript
suite or Harness boot was executed. Discovery/entry points, includes, expression
resolution, update/persistence, volatile config and hot reload remain future work.
