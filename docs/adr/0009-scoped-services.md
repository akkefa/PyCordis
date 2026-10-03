# ADR 0009: Named isolation slots and task-local config callers

Status: accepted for Phase 8.

## Context

Harness context.ts creates isolate/intercept views without changing Fiber lifetime.
Reflect slots and notifications use per-service labels. Service.resolveConfig merges
ancestor intercepts, and Service.filter selects matching listener contexts. Python
currently has explicit service APIs and owned event/effect engines, without the
source's proxy method tracing. Several isolated slots may belong to one owner.

## Decision

Add ScopeLabel identity tokens and per-view immutable isolation maps, with root
lazy defaults. Store bindings by (service name, label). Scoped lookup, mutation,
requirements and notifications select exactly that slot. Separate Fiber-owned
slot maps from loaded dependency snapshots; removal retains owned slots through
matching consumers' cleanup. require checks binding labels at every snapshot and
ancestor boundary, including an isolated view of the same Fiber.

Intercept appends immutable layers containing copied string-key config mappings.
Injection maps add per-mount layers. Resolve base, ancestor entries, then head into
a new shallow dict, with Service.merge_config as an explicit custom hook. Mount
config itself is unchanged. Non-mapping config values reject before mutation.

Use Context.scope/current_context backed by a ContextVar. Explicit config callers
win over the active caller, then defining context is fallback. Check root/label
compatibility before Service resolution. Plugin/effect setup and cleanup activate
defining/registering views, predicates activate consumer views, and events activate
dispatcher views. Service.ctx remains its defining owner. Service.matches_scope
supplies explicit event filtering without an implicit child-dispatch rule.

## Alternatives

A private dict per child would isolate every service, losing shared-label behavior.
Global mutable current-context state would mix concurrent calls. Overwriting a
single name-keyed owner snapshot cannot represent several slots owned by one Fiber.
Transparent method proxies would imply tracing/shadowing not yet defined in Python.
Automatically filtering all child events differs from the source's explicit filter.
Schema Config hooks belong to later validation work; a plain merge hook is sufficient.

## Consequences and compatibility

ScopeLabel replaces Symbols. Default labels are created on lookup/inspection too.
Including service name in the slot key deliberately prevents label-only cross-name
aliasing. Snapshot label validation strengthens isolation and avoids prior-owner
snapshot leaks from changed views. Nested config objects remain shared; copying
entries is not deep freeze or validation. Caller intercepts affect operations only
when they resolve config explicitly or execute middleware; get/set are not globally
intercepted. Tasks inherit ContextVars normally, and ownership remains structural.
Advanced proxy tracing, shadow rebinding, prototype extension, brands/decorators,
Config schema merge and internal kernel producers are explicitly deferred.

## Validation

31 scope cases cover independent/shared labels, scoped reactive changes, same-owner
slots, snapshot boundaries, replacement during cleanup, event filtering, config
precedence/copying/inject maps/custom merge, explicit caller checks, concurrent async
operations, cancellation restoration and setup/cleanup/dispatch execution contexts.
Existing phases run unchanged except the now-supported inject-config guard test.
No TypeScript suite or live Harness integration was executed.
