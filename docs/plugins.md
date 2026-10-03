# Plugin mounting and runtime identity

`ctx.plugin(plugin, config=None)` returns a new Fiber immediately. Await it to
settle setup and expose setup errors. Mounting requires a running event loop.
The child Context inherits the mounting view's metadata, belongs to its parent
Fiber, and shares its root Registry. Disposing a parent joins its children even
when they are still setting up or unloading.

```python
fiber = await ctx.plugin(worker, {"label": "worker"})
await fiber.restart()
await fiber.dispose()
```

Functions and callable instances receive `(ctx, config)` and may return any
supported effect result. Objects with callable `apply(ctx, config)` also work.
Callable objects take precedence over their apply attribute. Classes construct
with `(ctx, config)` on every activation; an optional zero-argument `start()`
method may return an effect result, including an awaitable. The constructed
instance itself is not a disposer. Constructor resources belong in ctx.effect.

Each executable callback has one PluginRuntime per root. Every mount still has
its own Fiber, uid, config and resources. Python bound methods use instance and
function identity, so repeated reads of an object's apply method share a record.
Equal or unhashable callable instances remain distinct. Names come from the
first mount's string name, otherwise the callback name; apply/lambda names are
omitted. Separate roots never share records.

`ctx.registry.get(plugin)` returns its record or None. `has`, `size`, `len`,
`keys`, `values`, `entries` and iteration inspect the registry. Collection results
and runtime.fibers are immutable snapshots. Fiber.runtime is None for root and
direct low-level Fibers; registered mounts retain their record for inspection
through teardown. Restart keeps the same runtime. Failed setup stays registered
until disposal, allowing lifecycle inspection or retry.

Disposal removes a mount from the registry immediately; completion of cleanup
requires awaiting disposal. The last mount removes the record. Parent ownership
continues until actual teardown completes. A remount during old teardown creates
a new record that old cleanup cannot erase.

To delete all mounts of a callback and join their cleanup:

```python
runtime = ctx.registry.get(worker)
if runtime is not None:
    mounted = runtime.fibers
    ctx.registry.delete(worker)
    for fiber in mounted:
        await fiber.dispose()
```

Delete is synchronous, returns the removed record (or None), and requests each
mount's disposal. Capture fibers before deletion: the returned record's fibers
are already empty. Independent cleanup starts in reverse order and may complete
concurrently. Within a collected effect, cleanup is sequential.

Phase 5 adds reactive services: declare inject as a list/tuple of names or a
name-to-None mapping. Context.inject(dependencies, callback) mounts the same
callback form conveniently. See services.md for availability and snapshots.
Config schemas still fail explicitly. Config objects pass by identity without
validation. Internal events and terminal Context disposal remain future work;
root Fiber disposal preserves restart semantics.
