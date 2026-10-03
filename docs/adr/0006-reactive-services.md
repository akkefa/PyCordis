# ADR 0006: Owned bindings and reactive activation snapshots

Status: accepted for Phase 5.

## Context

Harness reflect.ts registers each implementation through an owned effect, checks
ACTIVE provider state, notifies consumer Fibers, and joins their transitions on
removal. fiber.ts separates candidate dependencies from the loaded store and
uses provider-uid epochs. Explicit get bypasses injection while attribute lookup
walks declared/ancestor snapshots. Python has explicit APIs and scheduled Tasks;
service attributes, tracing and isolation are later phases.

## Decision

Keep a private root-shared ServiceRegistry in services.py. Context exposes
provide/get/set/require/inject/refresh_services. Binding records retain name,
value, owner, generation and optional synchronous availability predicate.
Provide is an Effect, so the existing rollback/ownership engine owns removal.
Set changes only the owning binding and does not notify consumers.

Normalize list/tuple and name-to-None dependency declarations before mounting.
Give each mount an immutable ordered requirements tuple and candidate binding map.
The Fiber driver copies candidates into an activation snapshot, keeping it through
cleanup and clearing it afterwards. Missing requirements produce an unavailable
epoch. Provider activity and registration/removal refresh affected registry mounts.
Failed consumers retain existing Harness retry-on-notification behavior.

Keep get as the explicit source escape hatch. Add require for snapshot access,
including ancestor/owned bindings, without introducing optional attribute lookup.
Missing get uses None, while binding presence makes provided None valid for inject.
Predicates use zero-argument closures; refresh_services requests re-evaluation.
Non-None inject mapping values reject until intercept configuration is implemented.

Use binding generations for epochs, deliberately strengthening provider uid
identity when one owner replaces a binding during loading. Async removal joins
affected consumers before dropping its owner snapshot entry, but excludes
structural ancestors/current execution owners: their teardown already owns the
removal and joining them would introduce a cycle. Effect/Fiber shielded waiters
and contained cleanup errors remain in force.

## Alternatives

Startup-only get would fail reactive injection. Sharing the live candidate map
with a loaded plugin would replace its cleanup dependencies mid-flight. Enforcing
injection in get would change the source's documented escape hatch. Automatic
attribute lookup would obscure collisions and imply incomplete proxy/tracing
compatibility. Always joining ancestors can deadlock structural shutdown.
Provider-uid-only epochs can miss same-owner replacement before setup completes.

## Consequences

Services are root-wide until scope/isolation work. Extensions share ownership and
bindings. Providers and consumers may finish their independent transitions at
different times, so callers await consumers after provider activation. Removal
can wait for async setup/cleanup, including a concurrently restored activation.
Async removal starts in a Task, unlike JS's immediate async prefix. Cleanup
snapshots reference binding records; set updates are observable without reload.
Strict get checks ACTIVE state, while predicates only gate consumer activation.
Availability checks must be synchronous; failed checks are logged and unavailable.
Service abstractions, events, config validation, optional dependencies and tracing
are not implemented or emulated by this decision.

## Validation

Real binding tests cover pending/activation/loss/restoration, transitive chains,
loading and unloading replacement, rollback, inactive access, manual removal,
shutdown joins, cancellations, predicates, ownership, loop affinity and stale
checkpoints. Tests adapt pinned source semantics rather than claiming that mocked
Python coverage proves full Harness integration.
