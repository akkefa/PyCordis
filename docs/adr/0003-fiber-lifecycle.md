# ADR 0003: Serialized async Fiber lifecycle

Status: accepted for Phase 2; effects/registry/services remain deferred.

## Context

Pinned Harness Fiber uses provider-uid epochs, a single inertia Promise and
root restart semantics. Local patches ensure parent ownership before child
publication and wait for setup plus in-flight cleanup. Python Tasks/coroutines
have cancellation and startup behavior different from JavaScript Promises.

## Decision

Bind each runtime to one event loop on first lifecycle work. Context creates a
loop-independent root Fiber; ordinary extensions inherit it. Low-level child
Fiber construction requires a running loop, creates an owning context, registers
parent cleanup first, then schedules setup after a checkpoint. Use one Task per
Fiber, immediate epoch invalidation and shielded settlement. Preserve Harness
state names/numeric values and root restartable disposal.

Provide wait/await, restart returning Fiber itself, and disposal returning a
lazy awaitable join handle. Joined repeat disposal avoids returning None into
Python await statements. Keep setup errors separate from contained cleanup
errors. For now callback config is object, passed unchanged; typed registry
normalization and schema resolution remain later work. A minimal add_cleanup
supports ownership/rollback; full ctx.effect and iterable results remain Phase 3.

Private epoch requests represent lifecycle inputs, not implemented DI. Maintain
dependency availability separately from a failed run's inactive epoch so restart
can retry a failed setup without making unavailable dependencies ready.

Use contextvars for lifecycle execution paths and reject cyclic self/ancestor
awaits with REENTRANT_AWAIT after requesting disposal. Caller cancellation never
implicitly cancels an owner's transition. Explicit setup cancellation is treated
as setup failure. Teardown runs reverse-start concurrent sibling callbacks and
contains errors independently, matching Fiber._unload.

## Alternatives

An asyncio.Lock around setup/disposal alone does not invalidate stale queued
setup and can deadlock reentrant shutdown. Cancelling setup on epoch loss differs
from source and can lose returned cleanup. Eager execution of Python coroutine
prefixes requires fragile manual coroutine driving. A second promise wrapper can
reintroduce the mutable-wrapper identity bug. Terminal root disposal contradicts
the inspected source and needs a separately reviewed API. Swallowing a cyclic
await or pretending it drained would conceal unfinished work.

## Consequences

There is one actual Fiber state object. External waiters can cancel safely or
join repeated disposal. A setup that never settles still prevents teardown.
Cross-loop/runtime use is rejected. Reentrant lifecycle code must request work
without awaiting a cycle; an external owner settles it. Cleanup failures are
reported by logging and immutable lifetime diagnostics. No user-level event bus,
services, full effects or registry is introduced by this phase.

## Compatibility impact

Retained: state values; epoch comparison; current-work settlement; retained setup
failure; wait-for-setup before stale-run unload; parent ownership; pending work
drain; reverse-start concurrent teardown; setup failure rollback; root restart.
Python adaptations: scheduled async startup, shielded waiter cancellation,
joined repeated disposal, explicit cycle error, direct low-level Fiber API and
an owning Context identity. add_cleanup is scaffolding for effects, not the
original ctx.effect contract. Pending epochs are tested via a private input;
service injection and internal publication/status events remain future work.
