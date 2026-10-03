"""Context views with explicit metadata inheritance and shared ownership."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from types import MappingProxyType
from typing import TYPE_CHECKING, Self

if TYPE_CHECKING:
    from .fiber import Fiber


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

    __slots__ = ("_fiber", "_metadata", "_owner", "_parent", "_root")

    def __init__(self) -> None:
        self._parent: Context | None = None
        self._root: Context = self
        self._owner: Context = self
        self._metadata: Mapping[str, object] = MappingProxyType({})
        from .fiber import Fiber

        self._fiber = Fiber._create_root(self)

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

        In this foundation every root owns itself. This identifies the scope
        where a future Fiber will be bound; it is not a Fiber or a disposer.
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
        child._metadata = _Metadata(entries, self.metadata)
        return child
