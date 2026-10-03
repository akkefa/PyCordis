"""Owned service bindings and reactive dependency resolution (one root scope)."""

from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .effects import _active_effects
from .errors import CordisError
from .fiber import FiberState, _executing

if TYPE_CHECKING:
    from .context import Context
    from .effects import Effect
    from .fiber import Fiber


def _name(name: object) -> str:
    if not isinstance(name, str) or not name:
        raise TypeError("service names must be nonempty strings")
    return name


def normalize_inject(declaration: object) -> tuple[str, ...]:
    """Copy ordered requirements; intercept configuration is a later phase."""
    names: Iterable[object]
    if declaration is None:
        return ()
    if isinstance(declaration, Mapping):
        if any(value is not None for value in declaration.values()):
            raise NotImplementedError("dependency intercept config requires the scope phase")
        names = declaration.keys()
    elif isinstance(declaration, (list, tuple)):
        names = declaration
    else:
        raise TypeError("inject must be a list, tuple or name-to-None mapping")
    return tuple(dict.fromkeys(_name(name) for name in names))


@dataclass(eq=False)
class _Binding:
    name: str
    value: object
    fiber: Fiber
    generation: int
    check: Callable[[], bool] | None


class ServiceRegistry:
    """Private root-shared service storage; Context exposes the scoped API."""

    def __init__(self, root: Context) -> None:
        self._root = root
        self._bindings: dict[str, _Binding] = {}
        self._generation = 0

    def _assert_loop(self) -> None:
        if self._root.fiber._loop is not None:
            self._root.fiber._bind_loop()

    def get(self, name: str, strict: bool = True) -> object:
        binding = self._bindings.get(_name(name))
        if binding is None or (strict and not self._available(binding)):
            return None
        return binding.value

    @staticmethod
    def _available(binding: _Binding) -> bool:
        return binding.fiber.state is FiberState.ACTIVE and binding.fiber.uid is not None

    def require(self, ctx: Context, name: str) -> object:
        name = _name(name)
        fiber = ctx.fiber
        while True:
            if fiber._store is not None and name in fiber._store:
                return fiber._store[name].value
            if name in fiber._inject:
                raise CordisError("INACTIVE_SERVICE", f'required service "{name}" is inactive')
            if fiber is self._root.fiber:
                raise CordisError("UNDECLARED_SERVICE", f'service "{name}" was not injected')
            fiber = fiber.parent.fiber

    def set(self, ctx: Context, name: str, value: object) -> None:
        self._assert_loop()
        binding = self._bindings.get(_name(name))
        if binding is None:
            raise CordisError("MISSING_SERVICE", f'service "{name}" was not provided')
        if binding.fiber is not ctx.fiber:
            raise CordisError("SERVICE_OWNER", f'service "{name}" belongs to another Fiber')
        binding.value = value

    def provide(
        self, ctx: Context, name: str, value: object, check: Callable[[], bool] | None
    ) -> Effect:
        name = _name(name)
        self._assert_loop()
        if check is not None and (not callable(check) or inspect.iscoroutinefunction(check)):
            raise TypeError("service availability check must be a synchronous callable")

        def register() -> object:
            if name in self._bindings:
                raise CordisError("DUPLICATE_SERVICE", f'service "{name}" is already provided')
            self._generation += 1
            binding = _Binding(name, value, ctx.fiber, self._generation, check)
            self._bindings[name] = binding
            if ctx.fiber._store is None:
                ctx.fiber._store = {}
            ctx.fiber._store[name] = binding
            if self._available(binding):
                self.notify((name,))

            async def remove() -> None:
                if self._bindings.get(name) is binding:
                    del self._bindings[name]
                affected = self.notify((name,))
                # Structural ancestors already own this teardown. Joining them
                # here would await our own cleanup through a dependency cycle.
                ancestors: set[Fiber] = {ctx.fiber}
                parent = ctx.fiber
                while parent is not self._root.fiber:
                    parent = parent.parent.fiber
                    ancestors.add(parent)
                ancestors.update(_executing.get())
                ancestors.update(effect.owner for effect in _active_effects.get())
                await asyncio.gather(
                    *(fiber._settle() for fiber in affected if fiber not in ancestors),
                    return_exceptions=True,
                )
                store = ctx.fiber._store
                if store is not None and store.get(name) is binding:
                    del store[name]

            return remove

        return ctx.effect(register, f'ctx.provide("{name}")')

    def refresh(self, fiber: Fiber) -> None:
        if fiber.uid is None:
            return
        candidates: dict[str, _Binding] = {}
        for name in fiber._inject:
            binding = self._bindings.get(name)
            if binding is None or not self._available(binding):
                continue
            try:
                if binding.check is not None:
                    result = binding.check()
                    if inspect.isawaitable(result):
                        if inspect.iscoroutine(result):
                            result.close()
                        raise TypeError("service availability checks must be synchronous")
                    if not result:
                        continue
            except Exception:
                logging.getLogger("pycordis").exception(
                    "Service %s availability check failed", name
                )
                continue
            if self._bindings.get(name) is binding and self._available(binding):
                candidates[name] = binding
        if fiber.uid is None:
            return
        fiber._bindings = candidates
        epoch = (
            tuple(candidates[name].generation for name in fiber._inject)
            if len(candidates) == len(fiber._inject)
            else None
        )
        fiber._set_epoch(epoch)

    def notify(self, names: tuple[str, ...]) -> tuple[Fiber, ...]:
        affected = []
        for runtime in self._root.registry.values():
            for fiber in runtime.fibers:
                if any(name in fiber._inject for name in names):
                    self.refresh(fiber)
                    affected.append(fiber)
        return tuple(affected)

    def owner_changed(self, fiber: Fiber) -> None:
        names = tuple(name for name, binding in self._bindings.items() if binding.fiber is fiber)
        if names:
            self.notify(names)
