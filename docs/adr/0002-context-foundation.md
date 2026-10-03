# ADR 0002: Explicit Context hierarchy and metadata

Status: accepted for Phase 1. Service and lifecycle APIs remain deferred.

## Context

Harness context.ts (commit 639ed015397290b3745d163aafe02ffee4aa3f84)
creates a root Context with a root Fiber and built-in services. extend uses
Object.create and copies own metadata descriptors; the new view inherits root
and Fiber ownership. Phase 1 must establish this foundation without prematurely
implementing Fiber, Registry or services. ReflectService's proxy distinguishes
real context members from service properties.

## Decision

Expose Context(), extend(mapping), parent, root, owner and metadata. Store
metadata in a separate read-only Mapping[str, object] with explicit inheritance.
Shallow-copy supplied entries, retain value identity and allow local None/False
values to shadow parents. Use a private Mapping implementation over the parent
view; no mutable registry or task-local/global current context is needed.

Define owner as the owning Context identity, shared by ordinary extensions.
Root owns itself. This is a foundation for later Fiber binding, not a placeholder
Fiber with invented behavior. parent/root/owner/metadata are read-only public
properties. Creating child views preserves their Python class without rerunning
constructors; arbitrary subclass instance state is not inherited.

Metadata does not participate in attribute lookup. Future services should begin
with explicit get/provide; their precise injection enforcement, missing-service
result and optional attribute access must be reviewed in the service phase.
No get/provide implementation or simple metadata-as-service substitute is added.

## Alternatives

__getattr__/__setattr__ forwarding to parents resembles JS prototypes but creates
collisions with Context APIs, forwards methods/state ambiguously, and risks
implementing partial service access checks. A flat dictionary snapshot loses the
explicit inherited view. Deep copying breaks shared resource identity. ChainMap
is a mutable interface even if wrapped, so an explicit read-only Mapping better
expresses the typing contract. Creating a root Fiber now crosses the phase gate.

## Consequences

Context construction is loop-independent. Views share ownership and values,
while supplied entry dictionaries and sibling overrides stay independent.
Metadata is immutable at entry level; mutable values remain caller-owned.
Subclasses with extra mandatory instance state need a later derivation contract;
class identity preservation does not initialize that state.

## Compatibility impact

Root identity, inherited/shadowed entries, shallow copied entries and unchanged
extension ownership are retained in explicit Python form. Namespaced read-only
metadata and string keys differ intentionally from JS arbitrary own properties,
property descriptors and Symbols. A separate parent property and owning-context
identity are Python API additions. Fiber binding, tracing, service visibility,
isolate/intercept and lifecycle await/disposal remain unimplemented and unclaimed.
