# Plugin metadata and reflection

`PluginMeta` is an immutable declaration, `PluginSpec` pairs it with an executable,
`plugin_meta(meta)` decorates the original executable, and `inspect_plugin(plugin)`
returns a normalized snapshot without mounting or invoking setup.

```python
from pycordis import PluginMeta, PluginSpec, plugin_meta, inspect_plugin


@plugin_meta(PluginMeta(name="worker", inject={"database": {"timeout": 5}}))
def worker(ctx, config):
    database = ctx.require("database")
    return ctx.effect(lambda: lambda: database.close_worker())


manifest = inspect_plugin(worker)
fiber = ctx.plugin(PluginSpec(worker, PluginMeta(inject=["database"])))
```

A spec or decorator supplies a complete declaration; it does not merge missing
fields with conventional attributes. A spec overrides a decorator. Otherwise
name/inject/provide/intercept/Config attributes remain supported with ordinary
Python inheritance. An unspecified display name falls back to the executable's
name, except apply and lambda. No method scanning or method injection occurs.

## Fields and behavior

| Field | Behavior |
|---|---|
| name | Optional display name; does not identify the executable or service slot |
| inject | Required service names or name-to-config mappings; drives each mount's reactive dependencies and intercept layers |
| provide | Copied, ordered, deduplicated service names; descriptive for general plugins |
| intercept | Copied name-to-bool capability declarations; does not install handlers or config layers |
| config | Synchronous validator reference, conventionally Config; validate(value) normalizes each activation |

Mapping entries are read-only shallow copies; nested config values and the
validator reference retain identity. This is declaration validation, not plugin
configuration validation. Source reusable/singleton behavior is not invented:
the inspected core does not use a reusable flag, and every mount creates a Fiber.

Service subclasses can declare one provide name when their class name is empty.
The precedence is explicit constructor name, nonempty class name, then a single
provide name. A class name also supplies an inferred provide declaration when
there is no explicit declaration. Multiple provide names need an explicit binding
name; the base Service registers only one slot. Generic provide metadata never
creates a binding automatically.

## Identity and inspection

PluginSpec unwraps to its executable before registry lookup, deletion or mounting.
The decorator returns the exact original object. Classes, callable objects and
bound apply methods retain the existing callback identity rules. Use a spec for
slotted objects that cannot accept a decorator attribute.

`runtime.metadata` holds the first mount's snapshot and `runtime.name` uses it.
`fiber.plugin_meta` holds that mount's snapshot, so shared runtimes may contain
Fibers with different declarations. Later attribute edits affect subsequent mounts
only. Restart retains the mount declaration. Root and direct low-level Fibers
have no plugin_meta. These inspection properties cannot be reassigned.

Invalid declarations and validators without callable validate fail before allocating a Fiber or
mutating the registry. Reflection may read ordinary Python properties; it is not
an evaluation sandbox. Config values pass through by identity without a validator;
see [config.md](config.md) for optional normalization and structured failures.

Run `uv run python examples/plugin_metadata.py`. See
[ADR 0010](adr/0010-plugin-metadata.md) for source evidence and deferred behavior.
