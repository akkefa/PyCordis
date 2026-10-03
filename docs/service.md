# Service classes

Service builds on owned service bindings; it does not introduce another lifecycle.
Subclasses declare a name and mount through the existing plugin registry:

```python
from pycordis import Context, Service


class Database(Service):
    name = "database"

    async def start(self) -> object:
        # Finish initialization before dependents may run.
        return self.ctx.effect(lambda: lambda: print("release owned resource"))


fiber = await ctx.plugin(Database, config)
database = ctx.get("database")
```

The inherited constructor accepts `(ctx, config=None, *, name=None)`. It stores the
defining context/config, validates a nonempty service name, and registers self
through ctx.provide. The class declaration may be inherited; keyword name can
explicitly override a single instance's binding name without changing the class.
Second positional arguments are config, not service names. A custom constructor
must call super().__init__(ctx, config), optionally passing name by keyword.
Class plugin diagnostics use the class's declared name; an instance override
changes only that instance's binding name. Changing instance.name later does not
rename the binding that was registered.

`service.ctx` and `service.config` are read-only references. Config passes by
identity and is not validated or frozen. The defining context owns effects made
by service methods. Method calls do not rebind ctx to the caller. Resources should
be registered through self.ctx.effect or returned/yielded from start.

The existing class-plugin adapter calls `start()` after construction and awaits
its supported effect result. Override start synchronously or asynchronously;
it may return a disposer, Effect, iterable or async iterable. Base start returns
None. The service binding can be inspected with get(name, False) during startup,
but strict get and dependent plugins see it only after its Fiber becomes ACTIVE.
Startup errors roll back owned registration and resources. Cleanup callbacks are
owned by the Fiber, including those collected during startup before failure.

`check()` is a synchronous availability predicate, defaulting to True. Override
it to gate dependent plugins while the provider itself is ACTIVE. False results
and logged exceptions leave dependents pending; strict get still returns the
active service. After changing predicate state, use
self.ctx.refresh_services(self.name) and await the returned consumers. Async
checks are unsupported. Inherited inject declarations use the Phase 5 API.

`service.registration` exposes the owned Effect for manually removing its binding.
Calling it requests removal; await the result when non-None. This unloads dependent
consumers but leaves the service plugin and other owned resources running. To
release the whole service, dispose its mounting Fiber. Restart unloads the old
instance and constructs a fresh one, preserving config identity. Retained Python
references to old instances are not invalidated or wrapped.

Direct `Database(ctx, config)` construction also registers synchronously, but it
does not call start. On an ACTIVE root, the binding is immediately available to
consumers. Use ctx.plugin for async initialization and automatic full lifecycle
coordination. Direct construction requires no loop until async removal or other
loop-bound work occurs. Name collisions reject the new registration and preserve
the original binding. Two mounts of one class share a plugin runtime but cannot
provide the same name in the same service label simultaneously.

A callable service defines ordinary __call__; get/require return that same
instance. Python isinstance recognizes the subclass without Cordis's special
proxy logic. A constructor's returned instance is never treated as a cleanup
callback, including when it is callable.

Service is a convenience base, not an abstract resource manager: there is no
implicit close/stop/destructor hook. Owned effects supply cleanup. Caller-context tracing, prototype extension helpers, decorators and attribute
service lookup remain later work. Phase 8 adds explicit label isolation,
matches_scope, and resolve_config; see scope.md. The defining context remains
unchanged when resolving caller configuration. See services.md for reactive teardown.
