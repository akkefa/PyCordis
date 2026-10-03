# Deterministic plugin loading

The loader is an optional module over the existing kernel. Import it from
`pycordis.loader`; it does not install a loader service or alter Context.

```python
from pycordis import Context
from pycordis.loader import Loader, PluginEntry

loader = Loader(Context())
batch = await loader.load(
    [
        PluginEntry("database", "myapp.plugins:Database", {"timeout": 5}),
        PluginEntry("worker", "myapp.worker"),
    ]
)
worker_fiber = batch.fibers["worker"]
await batch.dispose()
```

## References and rows

A PluginEntry has a nonempty id, plugin, config=None and enabled=True. IDs must
be unique within a batch, including disabled rows. Entries are frozen records;
plugin/config values retain their identity. IDs identify rows, not service names
or callback identity. Existing PluginSpec declarations work unchanged.

plugin can be an existing executable or a string reference:

- `package.module` imports a module exposing apply and conventional metadata.
- `package.module:attribute.path` selects an exported function, class or object.

References use absolute Python names. Imports use normal importlib caching and
sys.path; the loader does not add paths or reimport modules. Module metadata applies
to a bare module; an attribute reference uses that attribute's declaration. There
is no implicit search for default exports. resolve_plugin exposes import resolution
alone; executable/declaration checks happen during loading.

`await loader.load_config(rows)` accepts an ordered iterable of mappings with
exactly id/plugin and optional config/enabled. Unknown fields fail explicitly.
The caller supplies parsed rows; file reading, JSON/YAML parsing and expressions
are outside the loader. Disabled entries are omitted from batch.fibers and never
imported or validated. Input iteration order is preserved; IDs are not sorted.

## Ownership and settlement

Each load allocates a dedicated child Fiber beneath Loader.ctx. Entries mount as
children of that owner, inheriting the caller view's service scopes and intercepts.
All enabled entries mount in input order before any setup is awaited. Setup may
complete concurrently according to existing Fiber semantics; completion order is
not guaranteed for asynchronous plugins.

Settlement revisits entries until no LOADING/UNLOADING transitions remain. This
lets consumers appear before providers, including dependency chains. Absent or
cyclic dependencies remain PENDING and do not block loading indefinitely. They
can activate later through normal service notifications. Long-running setup still
needs to finish; the loader does not impose a timeout.

LoadedPlugins.owner and its read-only fibers mapping expose the actual kernel
Fibers. Calling batch.dispose joins that owner's teardown and is safe to repeat.
Disposing the parent also disposes the batch. Multiple loads have separate owners,
even when their plugin callbacks share runtime records. External consumers may
react to removal of a batch's providers under ordinary service semantics.

## Failure and cancellation

Rows, references, executable declarations and validator shape are preflighted
before mounting. Python imports can execute module code; those side effects are
not reversible, and imported modules remain in sys.modules after a later failure.
Metadata reflection may read Python properties. This is not an import sandbox.

Mount/setup/configuration failures dispose the entire newly created batch and
join owned cleanup before rethrowing the original error. Existing plugins outside
the batch are not directly disposed. Configuration validation runs during normal
activation, after requirements become available, using Phase 10 semantics.

Cancellation requests batch teardown and joins in-flight setup and cleanup through
existing shielded Fiber waits. It does not forcibly cancel plugin lifecycle Tasks;
a blocked setup can delay cancellation cleanup until it cooperates. Repeated
cancellation can interrupt the caller's cleanup wait while owned teardown continues.

Run `uv run python examples/plugin_loader.py`. See
[ADR 0012](adr/0012-deterministic-loader.md) for evidence and adaptations.

Package entry-point discovery, automatic scanning, nested configuration groups,
include files, internal/config expressions, update/persistence, watch and hot reload
remain future work. This phase adds no runtime dependencies or import hooks.
