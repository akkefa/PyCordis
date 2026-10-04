# Configuration validation

A plugin can declare a synchronous validator through PluginMeta.config or its
conventional Config attribute. The minimal ConfigValidator protocol is:

```python
class ConfigValidator(Protocol):
    def validate(self, value: object) -> object: ...
```

The method returns the normalized value directly, including None or False, or
raises an exception. The core does not interpret a schema-specific result envelope.
A validator instance or class with a static/class method works; a plain validator
function needs a small object adapter. No schema library is required.

```python
from deepseek_cordis import PluginMeta, ValidationError, ValidationIssue, plugin_meta


class PortConfig:
    def validate(self, value: object) -> object:
        if not isinstance(value, dict):
            raise ValidationError([ValidationIssue("expected an object")])
        port = value.get("port", 8080)
        if not isinstance(port, int) or isinstance(port, bool) or port <= 0:
            raise ValidationError([ValidationIssue("expected a positive integer", ("port",))])
        return {**value, "port": port}


@plugin_meta(PluginMeta(config=PortConfig()))
def server(ctx, config):
    print(config)
```

## Activation and ownership

Mounting checks that the declaration exposes callable validate(value) before
allocating a Fiber. It captures that callable for the mount. Validation itself
runs after the loading checkpoint and injected-service snapshot, immediately before
plugin setup or class construction. A PENDING mount does not validate. Validators
run under the mount's current_context(), so explicitly declared requirements can
be read there. Disposing a mount before activation skips validation entirely.

Every activation, including restart and service restoration, validates the original
raw input again. Fiber.raw_config retains that input by identity. Fiber.config is
raw until validation first succeeds, then retains the last successful resolution.
If a later validation fails, the last successful config remains inspectable.
Constructors, setup and Service.config receive the resolved value by identity.
Without a validator, raw input passes unchanged. Input is not copied or frozen;
validators that mutate it also change the input used on later activations.

Each mount uses its own validator even when the runtime is shared. Runtime.metadata
continues to describe the first mount, while Fiber.plugin_meta describes each mount.
The callable is captured at mounting; replacing the validator's validate attribute
later does not replace that mount's callable. Mutable validator state still follows
ordinary Python identity semantics.

Failure skips setup, drains owned resources, leaves the Fiber FAILED and retains
the same error for await/wait. The registry record remains until disposal, allowing
restart recovery. Arbitrary validator exceptions retain their original types;
ValidationError is the structured error an adapter can choose to raise. Its immutable
ValidationIssue entries include a message and copied field/index path, aggregated
as `invalid config` diagnostics. This does not use CordisError misuse codes.

Validation must be synchronous. Awaitable results fail with TypeError. Newly returned
native coroutines are closed to avoid unawaited-coroutine leaks; external Futures
and Tasks are not cancelled or adopted. Validators should not launch background work.
A validator that invalidates its Fiber cannot publish resolved config or run setup
for the stale epoch.

## Boundaries

This is a Python adaptation of Harness's synchronous Standard Schema boundary.
Defaults and transformations belong to validator implementations. Optional Pydantic,
dataclass and other schema adapters remain separate future work. There is no automatic
Standard Schema envelope, JavaScript symbol brand or library-specific conversion.

The internal/config expression waterfall, internal/update persistence hooks and
Fiber.update API remain future work with the loader. Operation intercept config
still uses explicit Service.resolve_config/merge_config; plugin validators do not
automatically validate or merge those layers. No discovery, hot reload or configuration
file reader is introduced in this phase.

Run `uv run python examples/config_validation.py`. See
[ADR 0011](adr/0011-config-validation.md) and [compatibility](compatibility.md).
