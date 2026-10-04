"""Fiber-owned reversible setup with joined teardown and nested collection."""

from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import AsyncIterable, Awaitable, Callable, Generator, Iterable
from contextvars import ContextVar
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .errors import CordisError
from .scope import _current_context

if TYPE_CHECKING:
    from .context import Context
    from .fiber import Cleanup, Fiber

_active_effects: ContextVar[tuple[Effect, ...]] = ContextVar("deepseek_cordis_effects", default=())


@dataclass(frozen=True)
class EffectMeta:
    """Immutable diagnostic snapshot of a live effect's collected children."""

    label: str
    children: tuple[EffectMeta, ...] = ()


class _Join:
    def __init__(self, effect: Effect) -> None:
        self.effect = effect

    def __await__(self) -> Generator[object, None, None]:
        return self.effect._join().__await__()


class Effect:
    """Callable single-shot disposer; awaiting it waits for setup, not teardown.

    Construct through ctx.effect or fiber.effect. Sync cleanup runs inline.
    Async setup/cleanup requires the owner's event loop. Internal ownership
    joins an in-flight disposal even when the public callable returns None.
    """

    def __init__(
        self,
        owner: Fiber,
        setup: Callable[[], object],
        label: str = "anonymous",
        *,
        _valid: Callable[[], bool] | None = None,
        _context: Context | None = None,
    ) -> None:
        owner._assert_registration()
        if not callable(setup):
            raise TypeError("effect setup must be callable")
        if not isinstance(label, str):
            raise TypeError("effect label must be a string")
        self._context = _context if _context is not None else owner.ctx
        self._valid = _valid or (lambda: True)
        self._owner = owner
        self._label = label
        self._callbacks: list[Cleanup] = []
        self._children: list[Effect] = []
        self._setup_task: asyncio.Task[None] | None = None
        self._dispose_task: asyncio.Task[None] | None = None
        self._setup_error: BaseException | None = None
        self._cleanup_error: BaseException | None = None
        self._requested = False
        self._finished = False
        self._collected_by: Effect | None = None
        owner.add_cleanup(self)  # Before any setup code or reentrant owner disposal.
        scope_token = _current_context.set(self._context)
        token = _active_effects.set((*_active_effects.get(), self))
        try:
            result = setup()
            if (inspect.isawaitable(result) or isinstance(result, AsyncIterable)) and not callable(
                result
            ):
                try:
                    loop = owner._bind_loop()
                except BaseException:
                    if inspect.iscoroutine(result):
                        result.close()
                    raise
                self._setup_task = loop.create_task(self._setup_async(result))
                self._setup_task.add_done_callback(self._observe)
            else:
                self._consume_sync(result)
        except (Exception, asyncio.CancelledError) as error:
            self._setup_error = error
            self._requested = True
            try:
                self._begin_cleanup()
            except (Exception, asyncio.CancelledError) as cleanup_error:
                self._record_cleanup_error(cleanup_error)
            raise
        finally:
            _active_effects.reset(token)
            _current_context.reset(scope_token)

    @property
    def owner(self) -> Fiber:
        return self._owner

    @property
    def label(self) -> str:
        return self._label

    @property
    def metadata(self) -> EffectMeta:
        return EffectMeta(self.label, tuple(child.metadata for child in self._children))

    def _collect(self, callback: object) -> None:
        if callback is None:
            return
        if not callable(callback):
            raise TypeError("effect must produce cleanup callables or None")
        if isinstance(callback, Effect):
            if callback is self or callback.owner is not self.owner:
                raise ValueError("collected effects must be distinct and have the same Fiber owner")
            if callback._collected_by is not None:
                raise ValueError("an effect may be collected only once")
            cursor: Effect | None = self
            while cursor is not None:
                if cursor is callback:
                    raise ValueError("effect collection cannot contain cycles")
                cursor = cursor._collected_by
            callback._collected_by = self
            self._children.append(callback)
            callback._detach()
        self._callbacks.append(callback)

    def _consume_sync(self, result: object) -> None:
        if result is None or callable(result):
            self._collect(result)
        elif isinstance(result, Iterable) and not isinstance(result, (str, bytes, dict)):
            iterator = iter(result)
            try:
                while True:
                    try:
                        value = next(iterator)
                    except StopIteration as done:
                        self._collect(done.value)
                        return
                    self._collect(value)
            finally:
                if inspect.isgenerator(iterator):
                    iterator.close()
        else:
            raise TypeError("invalid effect setup result: expected a cleanup callable or iterable")

    async def _setup_async(self, result: object) -> None:
        scope_token = _current_context.set(self._context)
        token = _active_effects.set((*_active_effects.get(), self))
        try:
            if inspect.isawaitable(result):
                self._collect(await result)
            elif isinstance(result, AsyncIterable):
                iterator = aiter(result)
                try:
                    while not self._requested and self._valid():
                        try:
                            value = await anext(iterator)
                        except StopAsyncIteration:
                            break
                        self._collect(value)
                finally:
                    # Python async generators require deterministic finalization.
                    close = getattr(iterator, "aclose", None)
                    if close is not None:
                        await close()
        except (Exception, asyncio.CancelledError) as error:
            self._setup_error = error
            if not self._requested:
                self._requested = True
                try:
                    cleanup = self._begin_cleanup()
                    if cleanup is not None:
                        # This cleanup does not join its own failing setup Task.
                        if self._dispose_task is not None:
                            await asyncio.shield(self._dispose_task)
                except (Exception, asyncio.CancelledError) as cleanup_error:
                    self._record_cleanup_error(cleanup_error)
            raise
        finally:
            _active_effects.reset(token)
            _current_context.reset(scope_token)

    def _observe(self, task: asyncio.Task[None]) -> None:
        if not task.cancelled():
            error = task.exception()
            if error is not None:
                logging.getLogger("deepseek_cordis").error(
                    "Effect %s async work failed", self.label, exc_info=error
                )

    def _detach(self) -> None:
        try:
            self.owner._cleanups.remove(self)
        except ValueError:
            pass  # Already in an unload snapshot or transferred to an outer effect.

    def _finish(self) -> None:
        self._finished = True
        self._detach()

    def _record_cleanup_error(self, error: BaseException) -> None:
        self._cleanup_error = error
        logging.getLogger("deepseek_cordis").error(
            "Effect %s cleanup failed", self.label, exc_info=error
        )

    @staticmethod
    def _combine(errors: list[BaseException]) -> BaseException:
        return (
            errors[0] if len(errors) == 1 else BaseExceptionGroup("effect cleanup failed", errors)
        )

    def _begin_cleanup(self) -> Awaitable[None] | None:
        callbacks = self._callbacks[::-1]
        self._callbacks.clear()
        errors: list[BaseException] = []
        for index, callback in enumerate(callbacks):
            try:
                result = callback._dispose_owned() if isinstance(callback, Effect) else callback()
                if inspect.isawaitable(result):
                    try:
                        loop = self.owner._bind_loop()
                    except BaseException:
                        if inspect.iscoroutine(result):
                            result.close()
                        raise
                    self._dispose_task = loop.create_task(
                        self._cleanup_async(result, callbacks[index + 1 :], errors)
                    )
                    self._dispose_task.add_done_callback(self._observe)
                    return _Join(self)
            except (Exception, asyncio.CancelledError) as error:
                errors.append(error)
        self._finish()
        if errors:
            combined = self._combine(errors)
            self._cleanup_error = combined
            raise combined
        return None

    async def _cleanup_async(
        self, first: Awaitable[object], remaining: list[Cleanup], errors: list[BaseException]
    ) -> None:
        scope_token = _current_context.set(self._context)
        token = _active_effects.set((*_active_effects.get(), self))
        try:
            try:
                await first
            except (Exception, asyncio.CancelledError) as error:
                errors.append(error)
            for callback in remaining:
                try:
                    result = (
                        callback._dispose_owned() if isinstance(callback, Effect) else callback()
                    )
                    if inspect.isawaitable(result):
                        await result
                except (Exception, asyncio.CancelledError) as error:
                    errors.append(error)
            if errors:
                self._cleanup_error = self._combine(errors)
                raise self._cleanup_error
        finally:
            self._finish()
            _active_effects.reset(token)
            _current_context.reset(scope_token)

    async def _dispose_after_setup(self) -> None:
        scope_token = _current_context.set(self._context)
        token = _active_effects.set((*_active_effects.get(), self))
        try:
            if self._setup_task is not None:
                try:
                    await asyncio.shield(self._setup_task)
                except (Exception, asyncio.CancelledError):
                    pass  # Rollback first; rethrow the retained setup error below.
            # Don't let _begin_cleanup replace our task and cause self-joining.
            callbacks = self._callbacks[::-1]
            self._callbacks.clear()
            errors: list[BaseException] = []
            for callback in callbacks:
                try:
                    result = (
                        callback._dispose_owned() if isinstance(callback, Effect) else callback()
                    )
                    if inspect.isawaitable(result):
                        await result
                except (Exception, asyncio.CancelledError) as error:
                    errors.append(error)
            if errors:
                self._cleanup_error = self._combine(errors)
                raise self._cleanup_error
            if self._setup_error is not None:
                raise self._setup_error
        finally:
            self._finish()
            _active_effects.reset(token)
            _current_context.reset(scope_token)

    def __call__(self) -> Awaitable[None] | None:
        if self._requested:
            return None
        # Check loop availability before changing state for an async disposal.
        if self._setup_task is not None and not self._setup_task.done():
            loop = self.owner._bind_loop()
            self._requested = True
            self._dispose_task = loop.create_task(self._dispose_after_setup())
            self._dispose_task.add_done_callback(self._observe)
            return _Join(self)
        self._requested = True
        scope_token = _current_context.set(self._context)
        token = _active_effects.set((*_active_effects.get(), self))
        try:
            return self._begin_cleanup()
        finally:
            _active_effects.reset(token)
            _current_context.reset(scope_token)

    def _dispose_owned(self) -> Awaitable[None] | None:
        result = self()
        return (
            _Join(self)
            if self._dispose_task is not None or self._cleanup_error is not None
            else result
        )

    async def _join(self) -> None:
        if self in _active_effects.get():
            raise CordisError("REENTRANT_AWAIT", "cannot await own effect setup or cleanup")
        if self._dispose_task is not None:
            self.owner._bind_loop()
            await asyncio.shield(self._dispose_task)
        elif self._cleanup_error is not None:
            raise self._cleanup_error

    async def wait(self) -> Effect:
        """Wait for setup, returning this callable disposer without disposing it."""
        if self in _active_effects.get():
            raise CordisError("REENTRANT_AWAIT", "cannot await own effect setup or cleanup")
        if self._setup_task is not None:
            self.owner._bind_loop()
            await asyncio.shield(self._setup_task)
        if self._setup_error is not None:
            raise self._setup_error
        return self

    def __await__(self) -> Generator[object, None, Effect]:
        return self.wait().__await__()
