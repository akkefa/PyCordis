# Reversible effects

An effect registers resource setup and cleanup with the Context's Fiber.
Registration precedes setup, so a reentrant owner unload cannot miss it.

```python
from pycordis import Context

ctx = Context()
resources = []


def setup():
    resources.append("open")
    return lambda: resources.append("closed")


effect = ctx.effect(setup, "resource")
assert resources == ["open"]
effect()  # Immediate synchronous cleanup; returns None.
effect()  # Single-shot: no repeated cleanup.
```

For async resources, create and dispose effects on the owner's running loop:

```python
async def setup():
    resource = await acquire()
    return resource.aclose


effect = ctx.effect(setup, "resource")
await effect  # Wait for setup, without disposing.
result = effect()
if result is not None:
    await result
```

The handle is callable and awaitable, but they mean different operations.
`await effect` settles setup and returns the callable handle. `effect()` requests
cleanup immediately: it returns None for sync cleanup, or an awaitable for async
cleanup. Repeated public calls return None, including while cleanup is running.
The Fiber and collected outer effects use an internal join operation, so their
teardown still waits for cleanup another caller already started.

## Accepted setup results

- None (no cleanup), or one cleanup callable.
- An awaitable resolving to None or a cleanup callable.
- A synchronous iterable yielding cleanup callables or None.
- An asynchronous iterable yielding cleanup callables or None.

A returned Effect handle is a cleanup callable first, even though it is also
awaitable. Async setup resolving to an iterable is not automatically expanded:
its resolved value follows the source's single-disposer contract. Strings,
bytes and dicts are rejected. Invalid yields trigger rollback. Python generator
return values can provide a final disposer. Sync generators are consumed
immediately; Python async function bodies begin in scheduled Tasks.

## Nested collection and ownership

```python
def setup():
    yield cleanup_a
    yield ctx.effect(child_setup, "child")
    yield cleanup_b


outer = ctx.effect(setup, "outer")
```

Yielding/returning the child transfers its cleanup out of the Fiber's top-level
list into outer. The Fiber then owns one tree, avoiding duplicate child teardown.
Creating a child without yielding/returning it leaves it separately owned by the
Fiber. Both must have the same Fiber owner; cross-owner, duplicate and cyclic
collection are rejected. Explicit Context ownership controls registration;
contextvars track executing setup/cleanup, not a global current owner.

`fiber.get_effects()` returns immutable EffectMeta trees (label and child tuple)
for live top-level effects. Setup rollback or completed cleanup removes the tree;
async cleanup remains registered until it settles or an owner snapshot drains
it. Metadata snapshots do not expose mutable ownership lists. Fiber setup now
uses the same engine, accepting generator setup and labeled "plugin setup" trees.

## Disposal and errors

Collected cleanups run sequentially in reverse order. Fiber-level sibling
effects retain reverse-start concurrent unloading. Setup is joined before
cleanup; disposal does not forcibly cancel an in-flight await. Async iterators
stop before their next advance once disposal invalidates collection; an advance
already in flight may yield one final cleanup, which is collected and drained.
Python generators are closed deterministically to run finally blocks.

Sync setup failure rolls back immediately where possible and rethrows the
original error. Async rollback stays owned until it completes. Awaiting a failed
async effect observes its setup error after rollback. Dropped async failures are
retrieved and logged, rather than escaping as unobserved Task exceptions.
Cleanup failure is retained for structural joins. A single cleanup error is
re-raised unchanged; multiple errors form a BaseExceptionGroup (ExceptionGroup
when all members are ordinary Exceptions).

**Intentional deviation:** source nested cleanup can fail fast. PyCordis instead
drains all collected callbacks before reporting errors. This prevents remaining
owned resources from being abandoned after one failure. Ownership/drain-all
behavior has explicit tests and is not claimed as identical compatibility.

New effect registration is rejected during owner UNLOADING or after disposal,
but remains legal for PENDING/LOADING/ACTIVE/FAILED owners. Manual cleanup while
the owner is ACTIVE can register another separately owned effect, matching the
source's state guard. A cleanup-time registration during owner unload is rejected.

Cancelled waiters shield setup/cleanup Tasks, allowing structural owners to
finish drainage. Waiting for your own effect's setup/cleanup, or awaiting the
owning Fiber's in-flight unload from an effect, raises REENTRANT_AWAIT rather
than deadlocking. Request owner shutdown without awaiting the cycle and let an
external owner settle it. An effect whose setup never settles can block drain,
consistent with source. Async setup and async cleanup require a running owner
loop; dispose async resources inside that loop. Arbitrary user-created background
Tasks are not automatically owned; register an explicit cleanup for them.

## Test evidence

The effect tests cover sync/async setup and cleanup, manual/automatic disposal, single-shot behavior,
collection order, nested ownership and metadata, sync/async rollback, invalid
results, in-flight owner/outer joins, generator abortion/finalization, plugin
generator setup, pending/loading registration, cleanup-time rejection, waiter
cancellation, explicit ownership, cross-owner rejection, reentrancy, cleanup
error drainage and no remaining effect Tasks in the tested complete drain.
Later registry, service, event and compatibility tests exercise integration with
this effect engine. No TypeScript suite was run; [compatibility](compatibility.md)
contains the current source-indexed evidence and intentional differences.
