# Service scopes and caller interception

Context.extend, isolate and intercept create views; they retain the same root,
registry and Fiber owner. Mounting a plugin below a view creates a child Fiber
with that view's service labels and config layers. View creation itself creates
no new lifetime or private container.

## Service labels

```python
private = root.isolate("database")
root.provide("database", global_database)
private.provide("database", private_database)
```

Isolate changes only database's label. Other services remain inherited. A fresh
label hides the parent's database binding; there is no fallback across that label.
Reuse a ScopeLabel to join sibling views:

```python
label = ScopeLabel()
first = root.isolate("database", label)
second = root.isolate("database", label)
```

service_scope(name) inspects the effective identity label. Separate roots have
separate stores, even if a caller passes the same label to both. Slots key by name
and label, so reusing one label for different names does not alias implementations.
This strengthens the source's label-only storage. Labels are identity objects,
not strings or metadata values; default labels are created lazily on first lookup.

get/provide/set and injected requirements use the calling view's label. Duplicate
providers are rejected within a slot, not across independent labels. One Fiber
can own several slots of the same name through different views. require checks
loaded snapshot labels and owned slots, and stops at incompatible ancestor
boundaries. It cannot read an old snapshot after a view changes that service label.

Provider activation, loss, removal and refresh_services notify only consumers
whose requirement uses the same label. Old snapshots remain available through
cleanup even while a replacement is globally visible in that slot. Shared labels
share providers but do not change ownership; unloading one view's provider still
removes the owned binding and unloads all matching consumers. Root disposal drains
all slots and children through existing structural ownership.

## Intercept configuration

```python
caller = root.intercept("database", {"timeout": 10})
caller = caller.intercept("database", {"timeout": 5, "read_only": True})
options = caller.resolve_config("database", base={"retries": 2}, head={"timeout": 1})
```

Configuration order is base, ancestor intercepts from root toward caller, then
head. Default merging is shallow and returns a fresh dict. Entries are copied
from string-key mappings and protected against entry mutation; nested values are
shared by identity. Parent/sibling views remain unchanged. No schema validation
or implicit merge of the plugin mount config occurs.

Inject mappings support copied service config:

```python
fiber = ctx.inject({"database": {"timeout": 5}}, consumer)
```

They still declare a required service, and their config adds the latest layer
on that mount's context. None adds only a requirement. Lists/tuples continue to
work. Configuration is resolved by a service operation, not passed as a replacement
for plugin config. Unrelated services' config layers are omitted.

Service.resolve_config(base=None, head=None, ctx=None) selects explicit ctx,
otherwise current_context(), otherwise its defining ctx. It validates the caller's
root and service label. Service.merge_config(*layers) is an overridable static
hook; default shallow merging matches the source fallback. This hook substitutes
for custom merge behavior without pretending Config schemas are implemented.

## Execution context and ownership

```python
with caller.scope():
    result = await database.query()
```

scope() activates a ContextVar and restores it after normal exit, exceptions and
cancellation. current_context() returns None outside active work. Concurrent Tasks
have independent contexts; a newly created Task inherits its creator's current
context according to normal Python rules. The scope manager creates no Task,
service or cleanup resource and does not change Fiber ownership.

Plugin setup and cleanup activate the defining plugin context. Context.effect
captures its registering view across async setup/cleanup. Service availability
predicates execute under the candidate consumer context. Event listeners, filters
and terminals execute under their dispatcher context, retaining it across awaits.
Callbacks still receive the same arguments and retain ordinary Python bindings.

Service.ctx remains the defining resource owner. Its methods may use resolve_config
to apply the current caller's intercepts, but creating effects through self.ctx
continues to assign them to the service's Fiber. Arbitrary retained service methods
are not transparently rebound or proxied. Use explicit ctx= to resolve config
without entering a scope; cross-root or incompatible-label callers are rejected.

## Scoped events

```python
private.emit("database-event", filter_=private_database.matches_scope)
```

Service.matches_scope accepts contexts in the same root/service label and can be
used as filter_. global_=True listeners bypass it. Without an explicit filter,
child emission still reaches all root listeners. Isolation does not automatically
filter every event and intercept config does not install middleware handlers.

This phase provides explicit scope/config APIs. Attribute proxies, method tracing
and shadow rebinding, Service prototype extension, automatic method injection, config
schemas and internal kernel interception hooks remain future work.

Phase 9 adds plugin-wide declaration decorators; their inject mappings use these
existing per-mount intercept layers. Metadata intercept flags describe capabilities
and do not create configuration or event handlers.
