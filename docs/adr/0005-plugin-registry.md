# ADR 0005: Callback identity and scoped plugin mounting

Status: accepted for Phase 4.

## Context

Harness registry.ts at 639ed015397290b3745d163aafe02ffee4aa3f84 resolves
functions or object apply callbacks, shares their runtime, and creates a Fiber
per mount. Fiber disposal unregisters before asynchronous teardown completes.
The source uses dynamically scoped service methods and a PromiseLike facade;
Python bound methods create new wrapper objects on each access.

## Decision

Each root Context owns a Registry shared by context extensions and children.
Context.plugin delegates to Registry.mount with an explicit mounting parent.
Return the actual awaitable Fiber, preserving the existing lifecycle API.
PluginRuntime stores the original callback, first-mount name and live mounted
Fibers, exposed through read-only properties and tuple snapshots.

Use identity keys, never user equality/hash. Python methods key by instance and
function; other callbacks key by object identity. Records strongly retain the
callback, preventing object-id reuse while registered. Callable objects take
precedence over apply. Classes construct with ctx/config and optionally execute
start(), a Python substitute for the source's Symbol init hook.

Attach unregister to Fiber disposal. Remove the runtime synchronously when its
last mount goes away, but retain parent ownership until teardown finishes.
Record-identity checks prevent old cleanup from removing a replacement runtime.
Registry.delete snapshots mounts and requests each disposal; callers retain
Fiber references to await completion. Validate before mutating registry state
and roll back a newly created record if Fiber construction fails.

## Alternatives

A singleton plugin instance would lose per-mount config and ownership. Hashing
plugin objects would conflate equal callables and reject unhashable ones. Bound
method wrapper identity would split repeated mounts. Delayed unregister would
block fresh records while cleanup is pending. Returning a facade would hide
existing Fiber APIs and duplicate its await machinery.

## Consequences and compatibility

Every mount requires a running event loop; async setup follows existing Task
semantics. Collection inspection snapshots replace JS live iterators. Optional
class start replaces JS init; constructor return objects are not treated as
effects. Config passes unchanged. Nonempty inject and Config are rejected until
service/validation phases; notification observers and reactive dependencies are
not partially emulated. Registry lifetime and parent ownership are deliberately
separate so immediate unregister never weakens teardown joins.
