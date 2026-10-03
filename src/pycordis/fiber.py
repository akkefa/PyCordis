"""Serialized Fiber lifecycle with owned effects, prior to registry and services."""

from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import Awaitable, Callable, Generator
from contextvars import ContextVar
from enum import IntEnum
from typing import TYPE_CHECKING, TypeAlias

from .effects import Effect, EffectMeta, _active_effects
from .errors import CordisError

if TYPE_CHECKING:
    from .context import Context

Cleanup: TypeAlias = Callable[[], object]
Setup: TypeAlias = Callable[["Context", object], object]
Epoch: TypeAlias = tuple[int, ...] | None
_executing: ContextVar[tuple[Fiber, ...]] = ContextVar("pycordis_lifecycle", default=())


class FiberState(IntEnum):
    """State names and numeric values from the pinned Harness implementation."""

    PENDING = 0
    LOADING = 1
    ACTIVE = 2
    FAILED = 3
    DISPOSED = 4
    UNLOADING = 5


class _Disposal:
    def __init__(self, fiber: Fiber) -> None:
        self._fiber = fiber

    def __await__(self) -> Generator[object, None, None]:
        return self._wait().__await__()

    async def _wait(self) -> None:
        await self._fiber._settle()


class Fiber:
    """One child mount, or the special root owner created by Context.

    Direct construction is the low-level Phase 2 API. It starts setup on the
    running loop after a checkpoint. Setup may be synchronous or asynchronous
    and produce cleanup callables or sync/async iterables through the effect
    engine. Registry normalization and services remain deferred.
    """

    _uid: int | None
    _counter: int

    def __init__(
        self, parent: Context, setup: Setup, config: object = None, *, name: str | None = None
    ) -> None:
        # Validate before changing parent ownership or allocating a uid.
        loop = asyncio.get_running_loop()
        parent.fiber._assert_registration()
        parent.fiber._bind_loop(loop)
        if not callable(setup):
            raise TypeError("fiber setup must be callable")
        self._initialize(parent, setup, config, name, root=False)
        owner = parent.root.fiber
        owner._counter += 1
        self._uid = owner._counter
        self._ctx = parent.extend()
        self._ctx._owner = self._ctx
        self._ctx._fiber = self
        self._parent_cleanup: Cleanup | None = self.dispose
        parent.fiber.add_cleanup(self._parent_cleanup)
        self._set_epoch((), loop=loop)

    @classmethod
    def _create_root(cls, ctx: Context) -> Fiber:
        self = object.__new__(cls)
        self._initialize(ctx, None, None, "root", root=True)
        return self

    def _initialize(
        self, parent: Context, setup: Setup | None, config: object, name: str | None, *, root: bool
    ) -> None:
        self._parent = parent
        self._ctx = parent
        self._setup = setup
        self._config = config
        self._name = name
        self._root = root
        self._uid = 0 if root else None
        self._counter = 0
        self._state = FiberState.ACTIVE if root else FiberState.PENDING
        self._epoch: Epoch = () if root else None
        self._dependency_epoch: Epoch = self._epoch
        self._task: asyncio.Task[None] | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._error: BaseException | None = None
        self._cleanup_errors: list[BaseException] = []
        self._cleanups: list[Cleanup] = []
        self._parent_cleanup = None

    @property
    def parent(self) -> Context:
        return self._parent

    @property
    def ctx(self) -> Context:
        return self._ctx

    @property
    def config(self) -> object:
        return self._config

    @property
    def uid(self) -> int | None:
        return self._uid

    @property
    def name(self) -> str:
        return self._name or self.parent.fiber.name

    @property
    def state(self) -> FiberState:
        return self._state

    @property
    def error(self) -> BaseException | None:
        """Retained setup failure, rethrown by wait/await, even after disposal."""
        return self._error

    @property
    def cleanup_errors(self) -> tuple[BaseException, ...]:
        """Contained teardown errors over this Fiber's lifetime."""
        return tuple(self._cleanup_errors)

    def _assert_registration(self) -> None:
        if self.uid is None or self.state is FiberState.UNLOADING:
            raise CordisError("INACTIVE_EFFECT")

    def add_cleanup(self, cleanup: Cleanup) -> None:
        """Register a lifecycle cleanup; not the full Cordis effect API.

        Legal during PENDING, LOADING, ACTIVE and FAILED; rejected during
        UNLOADING or after disposal. Sibling cleanups start in reverse order
        and are awaited concurrently. Returns no manual effect disposer.
        """
        self._assert_registration()
        if not callable(cleanup):
            raise TypeError("cleanup must be callable")
        self._cleanups.append(cleanup)

    def effect(self, setup: Callable[[], object], label: str = "anonymous") -> Effect:
        """Register reversible setup before invoking its synchronous body."""
        return Effect(self, setup, label)

    def get_effects(self) -> tuple[EffectMeta, ...]:
        """Diagnostic snapshots of currently owner-visible effect trees."""
        return tuple(cleanup.metadata for cleanup in self._cleanups if isinstance(cleanup, Effect))

    def _bind_loop(
        self, loop: asyncio.AbstractEventLoop | None = None
    ) -> asyncio.AbstractEventLoop:
        current = loop or asyncio.get_running_loop()
        if self._loop is not None and self._loop is not current:
            raise RuntimeError("a Fiber cannot move between event loops")
        self._loop = current
        return current

    def _set_epoch(self, epoch: Epoch, *, loop: asyncio.AbstractEventLoop | None = None) -> None:
        """Private input for later reactive service wiring; None means unavailable."""
        self._request_epoch(epoch, loop=loop)
        self._dependency_epoch = epoch

    def _request_epoch(
        self, epoch: Epoch, *, loop: asyncio.AbstractEventLoop | None = None
    ) -> None:
        if self.uid is None and epoch is not None:
            raise CordisError("INACTIVE_EFFECT")
        if epoch == self._epoch:
            return
        current = self._bind_loop(loop)
        old = self._epoch
        self._epoch = epoch
        if self._task is not None:
            return
        self._state = (
            FiberState.LOADING if old is None and epoch is not None else FiberState.UNLOADING
        )
        self._task = current.create_task(self._drive())

    def _setup_effect(self, epoch: Epoch) -> Effect:
        setup = self._setup
        assert setup is not None
        return Effect(
            self,
            lambda: setup(self.ctx, self.config),
            "plugin setup",
            _valid=lambda: self.uid is not None and self._epoch == epoch,
        )

    async def _drive(self) -> None:
        token = _executing.set((*_executing.get(), self))
        try:
            while True:
                if self.state is FiberState.LOADING:
                    epoch = self._epoch
                    await asyncio.sleep(0)
                    if epoch is not None and self.uid is not None and self._epoch == epoch:
                        try:
                            if self._setup is not None:
                                effect = self._setup_effect(epoch)
                                await effect
                            self._error = None
                        except (Exception, asyncio.CancelledError) as error:
                            self._error = error
                            self._epoch = None
                            logging.getLogger("pycordis").error(
                                "Fiber %s setup failed", self.name, exc_info=error
                            )
                    if (
                        epoch is not None
                        and self.uid is not None
                        and self._epoch == epoch
                        and self._error is None
                    ):
                        self._state = FiberState.ACTIVE
                        return
                    self._state = FiberState.UNLOADING

                await self._unload()
                if self.uid is None:
                    self._state = FiberState.DISPOSED
                    self._detach()
                    return
                if self._epoch is None:
                    self._state = (
                        FiberState.FAILED if self._error is not None else FiberState.PENDING
                    )
                    return
                self._state = FiberState.LOADING
        finally:
            self._task = None
            _executing.reset(token)

    async def _unload(self) -> None:
        cleanups = self._cleanups[::-1]
        self._cleanups.clear()
        results = await asyncio.gather(
            *(self._run_cleanup(cb) for cb in cleanups), return_exceptions=True
        )
        for result in results:
            if isinstance(result, BaseException):
                self._cleanup_errors.append(result)
                logging.getLogger("pycordis").error(
                    "Fiber %s cleanup failed", self.name, exc_info=result
                )

    async def _run_cleanup(self, cleanup: Cleanup) -> None:
        result = cleanup._dispose_owned() if isinstance(cleanup, Effect) else cleanup()
        if inspect.isawaitable(result):
            await result

    def _detach(self) -> None:
        cleanup = self._parent_cleanup
        if cleanup is not None:
            try:
                self.parent.fiber._cleanups.remove(cleanup)
            except ValueError:
                pass  # The parent's unload snapshot already owns this cleanup.
            self._parent_cleanup = None

    async def _settle(self) -> None:
        if self._task is not None:
            self._bind_loop()
            if self in _executing.get() or any(
                effect.owner is self for effect in _active_effects.get()
            ):
                raise CordisError("REENTRANT_AWAIT", "cannot await own or ancestor lifecycle work")
        while self._task is not None:
            await asyncio.shield(self._task)

    async def wait(self) -> Fiber:
        """Settle current transitions; PENDING is settled, not future activation."""
        await self._settle()
        if self.error is not None:
            raise self.error
        return self

    def __await__(self) -> Generator[object, None, Fiber]:
        return self.wait().__await__()

    def dispose(self) -> Awaitable[None]:
        """Request disposal immediately; awaiting joins cleanup without cancellation.

        Root disposal retains Cordis's restart behavior. Child disposal is
        terminal. Repeated child disposal joins the same in-flight transition.
        """
        if self._root:
            self.restart()
            return _Disposal(self)
        if self.uid is not None:
            loop = self._bind_loop()
            self._uid = None
            self._epoch = None
            if self._task is None:
                self._state = FiberState.UNLOADING
                self._task = loop.create_task(self._drive())
        return _Disposal(self)

    def restart(self) -> Fiber:
        """Request an unload/reload and return this awaitable Fiber."""
        if self.uid is None:
            raise CordisError("INACTIVE_EFFECT")
        self._request_epoch(None)
        self._request_epoch(self._dependency_epoch)
        return self
