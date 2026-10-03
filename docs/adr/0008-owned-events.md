# ADR 0008: Owned listeners and explicit dispatch policies

Status: accepted for Phase 7.

## Context

Pinned Harness events.ts uses owned listener effects, callback snapshots, explicit
thisArg-based filtering, and five distinct strategies. Parallel gathers all
failures; serial/bail use non-null/non-false results; waterfall shares a fixed-args
continuation queue. JS async functions start prefixes immediately, while Python
calls produce dormant coroutines. Python also reserves global as a keyword.

## Decision

Add scoped Events facades over one root-shared listener store. Context delegates
to its facade; extend creates a facade for the new registering context without
creating lifecycle work. on/once return owned Effects using record identity, with
keyword prepend/global_ options. Explicit synchronous filter_ predicates inspect
registering contexts and global_ bypasses them. No implicit child isolation or
callback-context rebinding is inferred.

Keep emit/bail inline and reject awaitable results; close bare coroutines to avoid
leaks. parallel awaits all callback results and groups all failures, while serial
awaits in order until a meaningful result. None/False checks use identity. Async
dispatch is caller-owned and cancellable; registration ownership does not silently
claim or shield active dispatch Tasks.

Waterfall keeps fixed event args and a zero-argument continuation; next_ is a
required terminal keyword. A sync chain returns immediately. Async bodies execute
under a dispatch-local ContextVar so their continuations bridge a synchronous tail.
Flatten returned awaitables, preserving self-settling PyCordis handles and rejecting
indirect cycles. Repeated continuation calls preserve the pinned source shared queue;
newer upstream duplicate guards are not adopted.

Once removes before invocation and adds a fired guard for stale recursive/concurrent
snapshots. This strengthens source removal-only behavior while honoring at-most-once
registration intent. Non-internal dispatch emits diagnostic internal/dispatch first;
parallel retains its historical emit mode. Diagnostic arguments are an immutable
tuple and the final slot carries filter_ rather than JS thisArg.

## Alternatives

Fire-and-forget emit requires a new background-task/error/shutdown policy and can
hide callback failures. Making emit async loses immediate sync delivery. Truthiness
would wrongly skip zero/empty bail results. Using one serial implementation for all
modes loses concurrency, error grouping and sync semantics. Callback equality or
identity removal can conflate registrations without the source tracing wrappers.
Automatic scope filtering would claim Phase 8 behavior before isolation exists.

## Consequences

Async listeners require parallel/serial or waterfall. Dispatch callbacks may remain
active after owner unload; callers coordinate them explicitly. Once is stronger in
reentrant snapshots than the source implementation. Async waterfall continuations
must be awaited/returned; sync wrappers around async tails must forward awaitables.
Strings/keywords/ExceptionGroup/native method binding replace JS symbols/options/
AggregateError/this. Kernel listener/config/update/plugin/status/service producers
and proxy interception are explicit future work, not emulated by this public bus.

## Validation

57 tests adapt the pinned five dispatch-mode tests and add order, mutation, filter,
recursive once, grouped errors, cancellation, awaitable cycles, async waterfall,
owner state, startup rollback, provider loss and restart regressions. No TypeScript
suite or live Harness integration was executed.
