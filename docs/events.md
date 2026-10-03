# Owned event listeners and dispatch

Each Context exposes on/once/emit/parallel/serial/bail/waterfall and a scoped
events facade with those same operations. Context views share their root's
listener store, but registration belongs to the calling view's Fiber. Separate
roots have independent buses. Event names are nonempty strings.

```python
listener = ctx.on("message", lambda value: print(value))
ctx.emit("message", "hello")
listener()  # synchronous manual removal; repeated calls return None
```

on and once return owned Effects, not bool-valued disposers. Owner unload,
restart, dependency loss, setup rollback and parent disposal remove listeners.
PENDING/LOADING registration is allowed; UNLOADING/disposed owners reject it.
Use prepend=True for insertion before existing listeners. Duplicate callbacks
have distinct registrations; each handle removes only its own entry. Once
removes before invoking its callback and guards recursive/concurrent snapshots,
so exceptions and nested delivery cannot invoke it a second time.

Every dispatch snapshots selected callbacks before invoking them. Removing a
listener during delivery does not remove it from that snapshot, and new listeners
wait until the next dispatch. Once's additional fired guard is the exception.
Ordinary child dispatch reaches sibling/root listeners without implicit filtering.

| Mode | Result and ordering |
|---|---|
| emit | Calls inline in registration order; ignores synchronous values; first error stops |
| bail | Calls inline until a result is neither None nor False; returns it or None |
| parallel | Awaits all concurrently; ignores successful values; groups all failures after settlement |
| serial | Awaits one at a time until a bail result/error; returns result or None |
| waterfall | Wraps a terminal with middleware; outermost return is the result; omission of next vetoes |

Bail uses identity, not truthiness: 0, empty strings/lists/dicts and True all bail.
Returned exception objects are ordinary values; only raised exceptions count as
parallel failures. Parallel groups even one error, using ExceptionGroup (or
BaseExceptionGroup when cancellation exceptions occur).

Python async callbacks do not run when merely called. Therefore emit/bail reject
awaitable results with TypeError and close bare coroutine results to avoid leaks.
Use parallel/serial for async listeners. Already-created Tasks/Futures are not
cancelled by this rejection; their creator still owns them. Sync callback prefixes
may already have run before a returned awaitable is rejected.

Async dispatch belongs to its caller. Await it; cancellation propagates to its
awaited callbacks and their finally blocks. Disposing a listener's owner removes
the registration but does not join an already-started dispatch. Callbacks in a
captured snapshot may still run after removal. Use owned effects for resources;
dispatch Tasks are not automatically registered as plugin-owned background work.

Explicit filter_ selects registering contexts; global_=True bypasses filtering:

```python
left = root.extend({"scope": "left"})
left.on("message", listener)
root.emit("message", value, filter_=lambda ctx: ctx.metadata["scope"] == "left")
```

Filters must be synchronous. They apply before callback delivery; errors propagate
before the dispatch starts. Listeners keep ordinary Python function/method binding;
no JavaScript thisArg or method-context rebinding is emulated. Phase 8 activates
the dispatcher view in current_context across callback awaits; use a service
operation's resolve_config to read those caller intercepts. Use service.matches_scope
as filter_ to dispatch only within that service label. Child emission still has
no implicit filtering.

Waterfall receives fixed event args, plus a shared zero-argument continuation.
Its terminal is a required keyword callback next_, invoked with no arguments:

```python
def middleware(value, next_):
    return value + next_()


ctx.on("calculate", middleware)
result = ctx.waterfall("calculate", 1, next_=lambda: 2)
```

For async middleware, await next_() before doing work with its result. Once an
async body runs, the continuation returns an awaitable even if the remaining tail
is synchronous. Sync middleware within that async tail can forward by returning
next_(), but must not perform synchronous arithmetic on an awaitable. Waterfall
returns an immediate result for sync paths and an awaitable for async paths; the
caller awaits when appropriate. Returned nested awaitables are flattened, preserving
self-settling Effect/Fiber handles and rejecting indirect result cycles.

```python
async def middleware(value, next_):
    result = await next_()
    return value + result


ctx.on("calculate", middleware)
result = await ctx.waterfall("calculate", 1, next_=lambda: 2)
```

Arguments cannot be replaced by next_(new_value). Not calling next vetoes remaining
listeners and the terminal. Repeated calls advance the same queue and invoke the
terminal again once exhausted, preserving the pinned source behavior. Async
continuations execute when awaited/returned, so calling and dropping an async
continuation is unsupported and leaves the usual Python unawaited coroutine.

Non-internal events first emit internal/dispatch(mode, name, args_tuple, filter_).
That observer may alter registrations before the public snapshot is selected.
Events beginning internal/ skip telemetry to prevent recursion. Parallel reports
mode emit, preserving the pinned diagnostic quirk. The final slot carries the
Python filter instead of JS thisArg. Listener interception and scoped update,
plugin/status/service/config producers remain future kernel work. This bus does
not claim those hooks merely because users can register their names.
