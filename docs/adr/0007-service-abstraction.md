# ADR 0007: A thin Service base over owned bindings

Status: accepted for Phase 6.

## Context

Harness service.ts registers self in its constructor through reflect.provide,
passes a Symbol check hook, and optionally constructs a callable proxy with
tracing metadata. fiber.ts invokes a separate Symbol init after construction.
Python already has class-plugin start(), owned Context.provide and native callable
instances. Isolation/config merge and method tracing are not yet implemented.

## Decision

Add an exported Service base in service.py. Use a plain string name declaration,
with an optional keyword name override in Service(ctx, config=None, *, name=None).
The positional signature matches registry class construction and retains config
by identity. Custom constructors explicitly call super. Store read-only defining
ctx/config references and expose the owned registration Effect for manual removal.
Name remains ordinary data, as in the source; changing it does not rename a binding.

Register self with ctx.provide and bound check. Provide default start returning
None and synchronous check returning True. The existing class adapter calls start;
no Service-specific Fiber path or new lifecycle driver is necessary. Native
__call__ and isinstance replace callable/proxy identity machinery. Inherited inject
metadata flows through existing dependency normalization and snapshot wiring.

Direct construction performs registration only, matching separation of constructor
and class-plugin init. Full startup coordination requires ctx.plugin(ServiceClass).
Restart constructs a fresh instance. Failed startup and constructor errors inside
mounting use the existing effect rollback and Fiber-owned cleanup engine.

## Alternatives

A class-definition service keyword requires a subclass/metaclass hook without
improving this small API. Interpreting the second positional argument as a name
conflicts with mounted config. Auto-running async startup from __init__ loses a
clear completion barrier and cannot return awaitables correctly. Automatic stop
or destructor cleanup adds a second ownership mechanism absent from the source.
Proxy-wrapping methods now would imply caller-context behavior that scope/tracing
phases have not defined.

## Consequences and compatibility

This class is a convenience base, not an abstract class requiring method overrides.
Name validation and binding collision rules stay in the service store. Constructor
state should be initialized before publication; mounted bindings remain hidden
until start completes. Direct construction on an active root publishes immediately.
Service methods always use the defining context, not a traced caller context.
Config is not frozen/validated. Start supports the existing effect-result algebra;
manual registration removal affects only the binding, not the whole plugin.
No proxy extension/filtering, interceptor config merge or decorator hooks are
partially emulated. These limitations are explicit in the compatibility guide.

## Validation

25 tests cover inherited default constructors, config/instance identity, declared
and overridden names, duplicate rejection, async startup barriers, dependent
chains, rollback, collected resources, cancellation, loading disposal, restart,
manual removal, callable instances, nested owned consumers and cleanup failures.
Pinned source tests supply semantics; Python adaptations do not claim execution
of the TypeScript suite or live Harness integration.
