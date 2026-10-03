# Services and reactive injection

A service is a named binding owned by a Fiber. Context views share one root-wide
service store with slots keyed by service name and label. Extend preserves
ownership and labels; isolate changes only the selected service label. Values pass by identity and may be any Python object, including
None, False or zero. A binding exists independently of its value's truthiness.

```python
registration = root.provide("database", database)
fiber = await root.inject(["database"], consumer)
```

Functions, callable objects, apply objects and constructor classes may declare
inject as a list/tuple of names or a name-to-None mapping. Context.inject is a
convenience mount with the same callback `(ctx, config)` signature. Requirements
are copied, deduplicated in order and exposed as fiber.inject. Mapping values add copied per-mount intercept configuration in Phase 8; None adds
only a requirement.

When any requirement is unavailable, awaiting the Fiber settles PENDING without
running setup. Awaiting does not wait for future availability. Provider activation
schedules setup. Loss unloads the consumer; restoration runs it again with the
original config and a new binding snapshot. Disposal is terminal, so a disposed
pending consumer never starts later. Restart rechecks current requirements.

```python
def consumer(ctx, config):
    database = ctx.require("database")
    return lambda: database.close_consumer_resource()
```

`provide(name, value=None, check=None)` immediately creates a binding and returns
an Effect. Calling the handle requests removal; await its result when non-None.
Removal is also automatic on owner unload, setup failure or parent disposal.
Duplicate names in one service label raise DUPLICATE_SERVICE and preserve the first
binding. Names must be nonempty strings. A synchronous root can provide without
an event loop, but asynchronous removal and plugin mounting require one.

A provider is visible to consumers only while ACTIVE. Values registered during
setup remain hidden until it completes. Leaving ACTIVE notifies dependents even
before registration cleanup runs. Removal waits for affected consumer lifecycle
work before releasing the provider's snapshot entry; parent ownership continues
joining resources already unloading. Independent cleanups still run concurrently.
Service removal does not impose global ordering on arbitrary provider cleanup.

`get(name, strict=True)` returns the current ACTIVE provider's value or None.
It bypasses injection requirements, matching Cordis's explicit get. With strict
False it can inspect a pending/loading/unloading binding until removal runs.
Availability predicates affect dependency loading, not get. Missing and provided
None both return None; inject/require distinguish them through binding presence.

`require(name)` reads an owned or declared binding from the activation snapshot,
walking ancestor Fiber snapshots for inherited access. A declared requirement in
an inactive context raises INACTIVE_SERVICE; an undeclared unrelated binding
raises UNDECLARED_SERVICE. Cleanup retains access to the old implementation even
if a replacement is already globally visible. Snapshot entries reference mutable
binding records, so owner set is visible to current consumers without restarting.
Python objects are not wrapped or traced and can outlive runtime ownership.

`set(name, value)` changes only this Fiber's binding, including through an
extended view with the same owner. It raises MISSING_SERVICE for an absent binding
or SERVICE_OWNER for a different owner. Set does not recheck consumers. Remove
then provide to replace a binding and reactively reload dependents.

An optional synchronous zero-argument check predicate controls dependency
availability. False results or logged exceptions leave consumers pending. Use
`ctx.refresh_services("database")` after changing predicate state and await the
returned Fibers to settle. Async predicates are unsupported. A provider's wait
settles its own lifecycle; await downstream consumers separately after publication.
Removal of an old binding joins all affected lifecycle work, including restoration
that was requested while their old cleanup was still in flight.

Every registration has a generation identity. This deliberately strengthens
Cordis's provider-uid epochs: a same-owner replacement during async startup must
invalidate the old snapshot. Structural ancestors/current execution owners are
excluded from removal's dependency joins because they already own the cleanup;
joining them would wait for that same removal. Declared dependency cycles with
no available seed bindings remain pending; the runtime does not solve cycles automatically.

See [Service classes](service.md) for the convenience base and [scope](scope.md)
for isolation/intercept configuration.
Attribute service lookup, accessors/mixins, traceable methods and internal events remain
future work. Root Fiber disposal restarts its lifecycle; it is not terminal
Context shutdown. Loop-bound service mutations cannot move to another loop.

require checks binding labels while walking ancestors, so changing a view's
isolation cannot read a snapshot from its prior label. Owned bindings are tracked
by slot separately from dependency snapshots, allowing one Fiber to provide the
same name in multiple labels. Scoped removal retains each owned entry through
its matching consumers' teardown. refresh_services affects only the caller's labels.
