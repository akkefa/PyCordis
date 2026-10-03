# ADR 0004: Owned effect handles and reliable cleanup

Status: accepted for Phase 3.

## Context

Harness fiber.ts at 639ed015397290b3745d163aafe02ffee4aa3f84 registers wrappers
before setup, keeps async teardown owner-visible, rolls back failed setup and
joins in-flight cleanup internally. Public disposal stays single-shot. Its
nested cleanup sequence may stop after a callback throws, whereas Fiber._unload
contains sibling effect errors. Python awaitables and generator finalization
also differ from JavaScript Promises/iterators.

## Decision

Separate the effect engine into effects.py. Context.effect delegates to its
Fiber; Effect is a callable, awaitable handle registered before setup. Awaiting
settles setup and returns the handle. Calling invokes cleanup synchronously
until an awaitable is encountered, then schedules and tracks the remaining
sequential chain. Repeat public calls return None; internal structural joins
always await existing cleanup. Keep entries until async work finishes.

Support callable, awaitable, sync iterable and async iterable setup results,
with callable precedence. Transfer collected nested handles into their parent's
cleanup tree and reject cross-owner/duplicate/cyclic transfers. Diagnostic
EffectMeta trees are immutable snapshots. Fiber plugin setup uses this engine
and a private epoch-validity predicate for async iterator checkpoints.

Use contextvars to track executing effects and reject cyclic awaits. Shield
waiters and observe dropped async exceptions. Explicitly close Python generators
and stop async iteration after an invalidated collection checkpoint.

Intentionally drain all collected cleanup callbacks in reverse sequential order,
then rethrow a single error or aggregate multiple errors. This departs from the
source's fail-fast nested sequence to honor the project's no-abandoned-resource
cleanup goal. Fiber sibling cleanup remains concurrent. Async setup/cleanup
requires the owner loop; synchronous effects work without a loop.

## Alternatives

Returning only an async function loses immediate sync setup/cleanup. Always
joining repeat public calls differs from the required source single-shot handle.
Removing the wrapper at disposal start can let parent unload miss active cleanup.
An untracked asyncio Task can lose setup errors or resources. Automatically
collecting all effects created in a setup body differs from source's explicit
yield/return transfer. Preserving fail-fast nested cleanup leaves owned callbacks
undrained; that difference is deliberate and tested here.

## Consequences

Python callers must distinguish await effect (setup) from effect() (cleanup).
Await the call result only when non-None. Async function prefixes execute in
Tasks, not synchronously as in JS. Generator finally blocks run deterministically,
an explicit Python adaptation. Cleanup may report grouped exceptions after
releasing remaining resources. Objects shared across different Fibers must not
transfer ownership through a collected handle; instead keep original ownership.

## Compatibility impact

Retained: registration before setup; owner-state guards; public single-shot sync
cleanup; awaiting setup; rollback; reverse collection; structural in-flight joins;
explicit nested collection; async generator checkpoint invalidation.
Adaptations/deviations: scheduled Python coroutine startup, deterministic generator
close, drain-all plus aggregate errors, same-owner transfer validation, immutable
metadata trees and explicit cycle errors. No registry, events or service behavior
is added or inferred by this phase.
