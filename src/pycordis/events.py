"""Fiber-owned listeners and distinct Cordis dispatch strategies."""

from __future__ import annotations

import asyncio
import inspect
from collections import deque
from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .context import Context
    from .effects import Effect

Listener = Callable[..., object]
EventFilter = Callable[["Context"], bool]


def is_bailed(value: object) -> bool:
    """Use identity, never truthiness: zero and empty values are bail results."""
    return value is not None and value is not False


def _name(name: object) -> str:
    if not isinstance(name, str) or not name:
        raise TypeError("event names must be nonempty strings")
    return name


async def _resolve(value: object) -> object:
    # JS Promises flatten listener results; Python async callbacks may return
    # another awaitable (notably a continuation) without awaiting it themselves.
    seen: set[int] = set()
    retained: list[object] = []
    while inspect.isawaitable(value):
        if id(value) in seen:
            raise ValueError("cyclic listener awaitable result")
        seen.add(id(value))
        retained.append(value)
        previous = value
        value = await value
        if value is previous:
            # PyCordis Effect/Fiber intentionally settle to their own handle.
            return value
    return value


def _sync_result(value: object) -> object:
    if inspect.isawaitable(value):
        if inspect.iscoroutine(value):
            value.close()
        raise TypeError("synchronous event dispatch cannot use awaitable results")
    return value


@dataclass(eq=False)
class _Hook:
    ctx: Context
    callback: Listener
    global_: bool


class Events:
    """A context-scoped facade over one root's shared listener store.

    on/once return owned Effects. Explicit filter_ selects listener contexts;
    ordinary child dispatch does not imply isolation or callback rebinding.
    """

    def __init__(self, ctx: Context) -> None:
        self._ctx = ctx
        self._hooks: dict[str, list[_Hook]] = {}

    def _view(self, ctx: Context) -> Events:
        view = Events(ctx)
        view._hooks = self._hooks
        return view

    def on(
        self, name: str, listener: Listener, *, prepend: bool = False, global_: bool = False
    ) -> Effect:
        name = _name(name)
        if not callable(listener):
            raise TypeError("event listener must be callable")
        if not isinstance(prepend, bool) or not isinstance(global_, bool):
            raise TypeError("event options must be bool")

        def register() -> object:
            hook = _Hook(self._ctx, listener, global_)
            hooks = self._hooks.setdefault(name, [])
            hooks.insert(0, hook) if prepend else hooks.append(hook)

            def remove() -> None:
                hooks.remove(hook)
                if not hooks and self._hooks.get(name) is hooks:
                    del self._hooks[name]

            return remove

        return self._ctx.effect(register, f'ctx.on("{name}")')

    def once(
        self, name: str, listener: Listener, *, prepend: bool = False, global_: bool = False
    ) -> Effect:
        if not callable(listener):
            raise TypeError("event listener must be callable")
        fired = False

        def call(*args: Any) -> object:
            nonlocal fired
            # Also suppress invocations captured in an outer dispatch snapshot
            # when a recursive/concurrent dispatch reaches this once first.
            if fired:
                return None
            fired = True
            effect()
            return listener(*args)

        effect = self.on(name, call, prepend=prepend, global_=global_)
        return effect

    def _dispatch(
        self, mode: str, name: str, args: tuple[object, ...], filter_: EventFilter | None
    ) -> tuple[Listener, ...]:
        name = _name(name)
        if filter_ is not None and (not callable(filter_) or inspect.iscoroutinefunction(filter_)):
            raise TypeError("event filter must be a synchronous callable")
        if not name.startswith("internal/"):
            self.emit("internal/dispatch", mode, name, args, filter_)
        return tuple(
            hook.callback
            for hook in tuple(self._hooks.get(name, ()))
            if hook.global_ or filter_ is None or _sync_result(filter_(hook.ctx))
        )

    def emit(self, name: str, *args: object, filter_: EventFilter | None = None) -> None:
        """Call listeners inline, ignoring sync results; first error stops delivery."""
        for callback in self._dispatch("emit", name, args, filter_):
            _sync_result(callback(*args))

    def bail(self, name: str, *args: object, filter_: EventFilter | None = None) -> object:
        """Call inline and return the first result other than None/False."""
        for callback in self._dispatch("bail", name, args, filter_):
            result = _sync_result(callback(*args))
            if is_bailed(result):
                return result
        return None

    async def parallel(self, name: str, *args: object, filter_: EventFilter | None = None) -> None:
        """Await all listeners concurrently and group all failures in registration order."""

        async def run(callback: Listener) -> None:
            await _resolve(callback(*args))

        # Preserve the pinned source's historical telemetry mode 'emit'.
        results = await asyncio.gather(
            *(run(callback) for callback in self._dispatch("emit", name, args, filter_)),
            return_exceptions=True,
        )
        errors = [result for result in results if isinstance(result, BaseException)]
        if errors:
            raise BaseExceptionGroup("parallel event dispatch failed", errors)

    async def serial(self, name: str, *args: object, filter_: EventFilter | None = None) -> object:
        """Await in order; first bail result or error ends the dispatch."""
        for callback in self._dispatch("serial", name, args, filter_):
            result = await _resolve(callback(*args))
            if is_bailed(result):
                return result
        return None

    def waterfall(
        self,
        name: str,
        *args: object,
        next_: Callable[[], object],
        filter_: EventFilter | None = None,
    ) -> object:
        """Compose middleware around a zero-argument terminal; may return an awaitable."""
        if not callable(next_):
            raise TypeError("waterfall terminal must be callable")
        callbacks = deque(self._dispatch("waterfall", name, args, filter_))
        asynchronous: ContextVar[bool] = ContextVar("pycordis_waterfall_async", default=False)

        async def resolve(value: object) -> object:
            token = asynchronous.set(True)
            try:
                return await _resolve(value)
            finally:
                asynchronous.reset(token)

        def advance() -> object:
            result = callbacks.popleft()(*args, continuation) if callbacks else next_()
            return resolve(result) if inspect.isawaitable(result) else result

        async def advance_async() -> object:
            return await _resolve(advance())

        def continuation() -> object:
            return advance_async() if asynchronous.get() else advance()

        return advance()
