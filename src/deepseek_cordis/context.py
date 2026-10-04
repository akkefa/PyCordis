"""Context views with explicit metadata inheritance and shared ownership."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from types import MappingProxyType
from typing import TYPE_CHECKING, Self

from .scope import ScopeLabel, _config, _current_context

if TYPE_CHECKING:
    from .effects import Effect
    from .events import EventFilter, Events, Listener
    from .fiber import Fiber
    from .registry import Registry


class _Metadata(Mapping[str, object]):
    """Read-only local entries over a read-only parent view."""

    __slots__ = ("_local", "_parent")

    def __init__(self, local: dict[str, object], parent: Mapping[str, object]) -> None:
        self._local = MappingProxyType(local)
        self._parent = parent

    def __getitem__(self, key: str) -> object:
        if key in self._local:
            return self._local[key]
        return self._parent[key]

    def __iter__(self) -> Iterator[str]:
        yield from self._local
        for key in self._parent:
            if key not in self._local:
                yield key

    def __len__(self) -> int:
        return sum(1 for _ in self)


class Context:
    """A root scope or an extended view of another context.

    Construction is synchronous and requires no event loop. Metadata is a
    separate namespace from services and Context attributes. Extensions share
    their parent's root and owning context; they do not create lifecycle work.
    """

    __slots__ = (
        "_default_labels",
        "_intercepts",
        "_isolation",
        "_events",
        "_fiber",
        "_metadata",
        "_owner",
        "_parent",
        "_registry",
        "_root",
        "_services",
    )

    def __init__(self) -> None:
        self._default_labels: dict[str, ScopeLabel] = {}
        self._isolation: Mapping[str, ScopeLabel] = MappingProxyType({})
        self._intercepts: tuple[Mapping[str, Mapping[str, object]], ...] = ()
        self._parent: Context | None = None
        self._root: Context = self
        self._owner: Context = self
        self._metadata: Mapping[str, object] = MappingProxyType({})
        from .fiber import Fiber

        self._fiber = Fiber._create_root(self)
        from .registry import Registry

        self._registry = Registry(self)

        from .services import ServiceRegistry

        self._services = ServiceRegistry(self)
        from .events import Events

        self._events = Events(self)

    @property
    def parent(self) -> Context | None:
        """The immediate context extended by this view, or None for a root."""
        return self._parent

    @property
    def root(self) -> Context:
        """The root shared by this context and all of its descendants."""
        return self._root

    @property
    def owner(self) -> Context:
        """The owning context, shared by ordinary extensions.

        Roots own themselves; plugin contexts own their mounted Fiber.
        Ordinary extensions keep that owning context.
        """
        return self._owner

    @property
    def fiber(self) -> Fiber:
        """Lifecycle owner shared by ordinary extensions."""
        return self._fiber

    @property
    def metadata(self) -> Mapping[str, object]:
        """Read-only inherited entries, with local entries taking precedence.

        Entry values are shared by identity, not deep-copied or frozen.
        """
        return self._metadata

    @property
    def registry(self) -> Registry:
        """Root-local runtime records shared by ordinary views and plugin scopes."""
        return self._registry

    def plugin(self, plugin: object, config: object = None) -> Fiber:
        """Mount a plugin in this context and return its actual awaitable Fiber."""
        return self.registry.mount(self, plugin, config)

    def provide(
        self, name: str, value: object = None, *, check: Callable[[], bool] | None = None
    ) -> Effect:
        """Register an owned service; calling the Effect requests removal."""
        return self._services.provide(self, name, value, check)

    def get(self, name: str, strict: bool = True) -> object:
        """Read a service without injection enforcement; missing returns None."""
        return self._services.get(self, name, strict)

    def require(self, name: str) -> object:
        """Read a declared/owned binding from the activation snapshot."""
        return self._services.require(self, name)

    def set(self, name: str, value: object) -> None:
        """Change only this Fiber's service value; no dependency restart."""
        self._services.set(self, name, value)

    def inject(self, dependencies: object, callback: Callable[[Context, object], object]) -> Fiber:
        """Mount a callback that reloads when its required bindings change."""
        from types import SimpleNamespace

        return self.plugin(SimpleNamespace(inject=dependencies, apply=callback))

    def refresh_services(self, *names: str) -> tuple[Fiber, ...]:
        """Recheck dynamic availability predicates; await returned Fibers to settle."""
        from .services import _name

        self._services._assert_loop()
        return self._services.notify(
            tuple((_name(name), self.service_scope(name)) for name in names)
        )

    @property
    def events(self) -> Events:
        """Scoped event facade; listener storage is shared by the root."""
        return self._events

    def on(
        self, name: str, listener: Listener, *, prepend: bool = False, global_: bool = False
    ) -> Effect:
        return self.events.on(name, listener, prepend=prepend, global_=global_)

    def once(
        self, name: str, listener: Listener, *, prepend: bool = False, global_: bool = False
    ) -> Effect:
        return self.events.once(name, listener, prepend=prepend, global_=global_)

    def emit(self, name: str, *args: object, filter_: EventFilter | None = None) -> None:
        self.events.emit(name, *args, filter_=filter_)

    def bail(self, name: str, *args: object, filter_: EventFilter | None = None) -> object:
        return self.events.bail(name, *args, filter_=filter_)

    async def parallel(self, name: str, *args: object, filter_: EventFilter | None = None) -> None:
        await self.events.parallel(name, *args, filter_=filter_)

    async def serial(self, name: str, *args: object, filter_: EventFilter | None = None) -> object:
        return await self.events.serial(name, *args, filter_=filter_)

    def waterfall(
        self,
        name: str,
        *args: object,
        next_: Callable[[], object],
        filter_: EventFilter | None = None,
    ) -> object:
        return self.events.waterfall(name, *args, next_=next_, filter_=filter_)

    def effect(self, setup: Callable[[], object], label: str = "anonymous") -> Effect:
        """Create a reversible effect owned by this context's Fiber."""
        from .effects import Effect

        return Effect(self.fiber, setup, label, _context=self)

    def service_scope(self, name: str) -> ScopeLabel:
        """Inspect this view's identity label for one named service."""
        from .services import _name

        name = _name(name)
        label = self._isolation.get(name)
        if label is None:
            label = self.root._default_labels.setdefault(name, ScopeLabel())
        return label

    def isolate(self, name: str, label: ScopeLabel | None = None) -> Self:
        """Extend with a fresh or shared identity scope for just this service."""
        from .services import _name

        name = _name(name)
        if label is not None and not isinstance(label, ScopeLabel):
            raise TypeError("isolation label must be a ScopeLabel")
        child = self.extend()
        child._isolation = MappingProxyType(
            {**self._isolation, name: label if label is not None else ScopeLabel()}
        )
        return child

    def intercept(self, name: str, config: Mapping[str, object]) -> Self:
        """Extend with copied service config, merged ancestor first."""
        from .services import _name

        name = _name(name)
        entry = _config(config)
        child = self.extend()
        child._intercepts = (*self._intercepts, MappingProxyType({name: entry}))
        return child

    def _config_layers(
        self, name: str, base: Mapping[str, object] | None, head: Mapping[str, object] | None
    ) -> tuple[Mapping[str, object], ...]:
        from .services import _name

        name = _name(name)
        return (
            *((_config(base),) if base is not None else ()),
            *(layer[name] for layer in self._intercepts if name in layer),
            *((_config(head),) if head is not None else ()),
        )

    def resolve_config(
        self,
        name: str,
        base: Mapping[str, object] | None = None,
        head: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        """Shallow merge base, ancestor intercepts and head into a fresh dict."""
        result: dict[str, object] = {}
        for layer in self._config_layers(name, base, head):
            result.update(layer)
        return result

    @contextmanager
    def scope(self) -> Iterator[Self]:
        """Activate this caller context across awaits; restore it on every exit."""
        token = _current_context.set(self)
        try:
            yield self
        finally:
            _current_context.reset(token)

    def extend(self, meta: Mapping[str, object] | None = None) -> Self:
        """Create a child view without changing this context or its ownership.

        The supplied mapping is shallow-copied. Keys must be strings. A child
        keeps this context's Python type without rerunning its constructor;
        subclass instance state is not inherited as JavaScript properties are.
        """
        if meta is not None and not isinstance(meta, Mapping):
            raise TypeError("context metadata must be a mapping")
        entries = {} if meta is None else dict(meta)
        if any(not isinstance(key, str) for key in entries):
            raise TypeError("context metadata keys must be strings")

        child = object.__new__(type(self))
        child._default_labels = self.root._default_labels
        child._isolation = self._isolation
        child._intercepts = self._intercepts
        child._parent = self
        child._root = self.root
        child._owner = self.owner
        child._fiber = self.fiber
        child._registry = self.registry
        child._services = self._services
        child._events = self.events._view(child)
        child._metadata = _Metadata(entries, self.metadata)
        return child
