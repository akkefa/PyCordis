"""Root-local plugin identity and mounted runtime records."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Iterator
from typing import TYPE_CHECKING, cast

from .fiber import Fiber, Setup
from .services import normalize_inject

if TYPE_CHECKING:
    from .context import Context


class PluginRuntime:
    """Read-only inspection of a shared plugin callback and its mounted Fibers."""

    def __init__(self, callback: Setup, name: str | None) -> None:
        self._callback = callback
        self._name = name
        self._fibers: list[Fiber] = []

    @property
    def callback(self) -> Setup:
        return self._callback

    @property
    def name(self) -> str | None:
        return self._name

    @property
    def fibers(self) -> tuple[Fiber, ...]:
        return tuple(self._fibers)


class Registry:
    """One registry per root, shared by context views and mounted children.

    Context.plugin is the scoped mounting API. Registry.mount takes its parent
    explicitly; get/has/delete accept the original plugin shape.
    """

    def __init__(self, root: Context) -> None:
        self._root = root
        self._records: dict[tuple[int, ...], PluginRuntime] = {}

    @staticmethod
    def resolve(plugin: object) -> Setup | None:
        """Resolve an executable callback without propagating apply getter errors."""
        try:
            if callable(plugin):
                return cast(Setup, plugin)
            callback = getattr(plugin, "apply", None)
            if callable(callback):
                return cast(Setup, callback)
        except Exception:
            pass
        return None

    @staticmethod
    def _key(callback: Setup) -> tuple[int, ...]:
        if inspect.ismethod(callback):
            return (id(callback.__self__), id(callback.__func__))
        return (id(callback),)

    @property
    def size(self) -> int:
        return len(self._records)

    def __len__(self) -> int:
        return self.size

    def get(self, plugin: object) -> PluginRuntime | None:
        callback = self.resolve(plugin)
        return None if callback is None else self._records.get(self._key(callback))

    def has(self, plugin: object) -> bool:
        return self.get(plugin) is not None

    def keys(self) -> tuple[Setup, ...]:
        return tuple(record.callback for record in self._records.values())

    def values(self) -> tuple[PluginRuntime, ...]:
        return tuple(self._records.values())

    def entries(self) -> tuple[tuple[Setup, PluginRuntime], ...]:
        return tuple((record.callback, record) for record in self._records.values())

    def __iter__(self) -> Iterator[Setup]:
        return iter(self.keys())

    def mount(self, parent: Context, plugin: object, config: object = None) -> Fiber:
        """Mount a fresh Fiber while reusing the callback's shared runtime."""
        callback = self.resolve(plugin)
        if callback is None:
            raise TypeError("invalid plugin: expected a callable or an object with callable apply")
        if parent.root is not self._root:
            raise ValueError("mounting context belongs to another root")
        # All fallible validation precedes registry mutation.
        loop = asyncio.get_running_loop()
        parent.fiber._assert_registration()
        parent.fiber._bind_loop(loop)
        inject = normalize_inject(getattr(plugin, "inject", None))
        if getattr(plugin, "Config", None) is not None:
            raise NotImplementedError("plugin Config schemas require the validation phase")
        key = self._key(callback)
        runtime = self._records.get(key)
        created = runtime is None
        if runtime is None:
            name = getattr(plugin, "name", None)
            if name is None:
                name = getattr(callback, "__name__", None)
            if name in ("apply", "<lambda>"):
                name = None
            if name is not None and not isinstance(name, str):
                raise TypeError("plugin name must be a string")
            runtime = PluginRuntime(callback, name)
            self._records[key] = runtime
        try:
            fiber = Fiber(
                parent,
                self._setup(runtime.callback),
                config,
                name=runtime.name,
                _dependencies=inject,
            )
            runtime._fibers.append(fiber)
            fiber._runtime = runtime
            fiber._unregister = lambda: self._remove(key, runtime, fiber)
            parent._services.refresh(fiber)
            return fiber
        except BaseException:
            if created and self._records.get(key) is runtime and not runtime._fibers:
                del self._records[key]
            raise

    @staticmethod
    def _setup(callback: Setup) -> Setup:
        if not inspect.isclass(callback):
            return callback

        constructor = cast(Setup, callback)

        def construct(ctx: Context, config: object) -> object:
            instance = constructor(ctx, config)
            start = getattr(instance, "start", None)
            if start is None:
                return None
            if not callable(start):
                raise TypeError("class plugin start must be callable")
            return start()

        return construct

    def _remove(self, key: tuple[int, ...], runtime: PluginRuntime, fiber: Fiber) -> None:
        try:
            runtime._fibers.remove(fiber)
        except ValueError:
            return
        if not runtime._fibers and self._records.get(key) is runtime:
            del self._records[key]

    def delete(self, plugin: object) -> PluginRuntime | None:
        """Remove a runtime and request all its Fibers' disposal immediately.

        Snapshot runtime.fibers before deletion if you need to await their
        disposal. This method returns the now-unregistered record; it is
        synchronous and does not promise completed teardown.
        """
        runtime = self.get(plugin)
        if runtime is None:
            return None
        fibers = runtime.fibers
        # Check loop affinity before removing a live runtime or requesting disposal.
        loop = asyncio.get_running_loop()
        for fiber in fibers:
            fiber._bind_loop(loop)
        key = self._key(runtime.callback)
        del self._records[key]
        for fiber in fibers:
            fiber.dispose()
        return runtime
