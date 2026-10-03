"""Context views with explicit metadata inheritance and shared ownership."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from types import MappingProxyType
from typing import TYPE_CHECKING, Self

if TYPE_CHECKING:
    from .effects import Effect
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

    __slots__ = ("_fiber", "_metadata", "_owner", "_parent", "_registry", "_root", "_services")

    def __init__(self) -> None:
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
        return self._services.get(name, strict)

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
        return self._services.notify(tuple(_name(name) for name in names))

    def effect(self, setup: Callable[[], object], label: str = "anonymous") -> Effect:
        """Create a reversible effect owned by this context's Fiber."""
        return self.fiber.effect(setup, label)

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
        child._parent = self
        child._root = self.root
        child._owner = self.owner
        child._fiber = self.fiber
        child._registry = self.registry
        child._services = self._services
        child._metadata = _Metadata(entries, self.metadata)
        return child
