"""Pinned events.spec.ts adaptations plus Python dispatch/lifecycle regressions."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import cast

import pytest

from pycordis import Context, CordisError, Effect, Service, is_bailed


async def resolved(value: object) -> object:
    if isinstance(value, Awaitable):
        return await value
    return value


@pytest.mark.parametrize("value", [None, False])
def test_non_bail_results(value: object) -> None:
    assert not is_bailed(value)


@pytest.mark.parametrize("value", [0, "", [], {}, True, 1, object()])
def test_bail_uses_identity_not_truthiness(value: object) -> None:
    assert is_bailed(value)


def test_root_local_bus_views_and_manual_listener_removal() -> None:
    root = Context()
    view = root.extend()
    calls: list[object] = []
    effect = view.on("event", lambda value: calls.append(value))
    assert isinstance(effect, Effect)
    root.emit("event", 1)
    view.emit("event", 2)
    Context().emit("event", 3)
    assert calls == [1, 2]
    assert view.events is not root.events
    assert effect.owner is root.fiber
    assert effect() is None
    root.emit("event", 4)
    assert calls == [1, 2]
    assert effect() is None
    assert root.fiber.get_effects() == ()


def test_prepend_order_and_return_values_ignored_by_emit() -> None:
    root = Context()
    calls: list[int] = []

    def first() -> object:
        calls.append(1)
        return "ignored"

    root.on("event", first)
    root.on("event", lambda: calls.append(2), prepend=True)
    root.on("event", lambda: calls.append(3), prepend=True)
    root.emit("event")
    assert calls == [3, 2, 1]


def test_duplicate_callback_registrations_have_independent_effect_identity() -> None:
    root = Context()
    calls: list[int] = []

    def callback() -> None:
        calls.append(1)

    first, second = root.on("event", callback), root.on("event", callback)
    second()
    root.emit("event")
    assert calls == [1]
    first()
    root.emit("event")
    assert calls == [1]


def test_snapshot_mutation_preserves_current_listeners_and_defers_new_ones() -> None:
    root = Context()
    calls: list[str] = []

    def first() -> None:
        calls.append("first")
        second()
        root.on("event", lambda: calls.append("new"))

    root.once("event", first)
    second = root.on("event", lambda: calls.append("second"))
    root.emit("event")
    assert calls == ["first", "second"]
    root.emit("event")
    assert calls == ["first", "second", "new"]


def test_once_removes_before_recursive_invocation() -> None:
    root = Context()
    calls: list[int] = []

    def callback() -> None:
        calls.append(1)
        root.emit("event")

    effect = root.once("event", callback)
    root.emit("event")
    assert calls == [1]
    assert effect() is None
    assert root.fiber.get_effects() == ()


def test_once_cannot_be_called_twice_through_outer_stale_snapshot() -> None:
    root = Context()
    calls: list[str] = []
    root.once("event", lambda: root.emit("event"))
    root.once("event", lambda: calls.append("once"))
    root.emit("event")
    assert calls == ["once"]


def test_once_throw_still_removes_listener() -> None:
    root = Context()

    def callback() -> None:
        raise ValueError("once")

    root.once("event", callback)
    with pytest.raises(ValueError):
        root.emit("event")
    root.emit("event")
    assert root.fiber.get_effects() == ()


def test_emit_error_stops_following_listeners() -> None:
    root = Context()
    calls: list[str] = []
    root.on("event", lambda: calls.append("before"))

    def callback() -> None:
        raise ValueError("sync")

    root.on("event", callback)
    root.on("event", lambda: calls.append("after"))
    with pytest.raises(ValueError, match="sync"):
        root.emit("event")
    assert calls == ["before"]


@pytest.mark.parametrize("mode", ["emit", "bail"])
def test_sync_dispatch_rejects_coroutine_results_without_leaking(mode: str) -> None:
    root = Context()
    calls: list[str] = []

    async def callback() -> object:
        calls.append("ran")
        return None

    root.on("event", callback)
    with pytest.raises(TypeError, match="awaitable"):
        getattr(root, mode)("event")
    assert calls == []


@pytest.mark.parametrize("value", [0, "", [], {}])
def test_bail_stops_on_empty_but_meaningful_values(value: object) -> None:
    root = Context()
    calls: list[str] = []
    root.on("event", lambda: None)
    root.on("event", lambda: False)
    root.on("event", lambda: value)
    root.on("event", lambda: calls.append("unexpected"))
    assert root.bail("event") is value
    assert calls == []


def test_bail_error_propagates_and_no_result_returns_none() -> None:
    root = Context()
    assert root.bail("event") is None

    def callback() -> None:
        raise ValueError("bail")

    root.on("event", callback)
    with pytest.raises(ValueError, match="bail"):
        root.bail("event")


@pytest.mark.asyncio
async def test_parallel_is_concurrent_and_joins_every_listener() -> None:
    root = Context()
    first_started, second_started, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
    calls: list[str] = []

    async def first(value: object) -> None:
        first_started.set()
        await second_started.wait()
        await release.wait()
        calls.append("first")

    async def second(value: object) -> None:
        second_started.set()
        await first_started.wait()
        await release.wait()
        calls.append("second")

    root.on("event", first)
    root.on("event", second)
    task = asyncio.create_task(root.parallel("event", "arg"))
    async with asyncio.timeout(2):
        await asyncio.gather(first_started.wait(), second_started.wait())
    assert not task.done()
    release.set()
    await task
    assert sorted(calls) == ["first", "second"]
    await root.fiber.dispose()


@pytest.mark.asyncio
async def test_parallel_groups_sync_async_errors_after_all_listeners_settle() -> None:
    root = Context()
    calls: list[str] = []

    def sync() -> None:
        raise ValueError("sync")

    async def async_error() -> None:
        await asyncio.sleep(0)
        calls.append("failed async")
        raise RuntimeError("async")

    async def success() -> None:
        await asyncio.sleep(0)
        calls.append("success")

    root.on("event", sync)
    root.on("event", async_error)
    root.on("event", success)
    with pytest.raises(ExceptionGroup) as error:
        await root.parallel("event")
    assert [str(item) for item in error.value.exceptions] == ["sync", "async"]
    assert sorted(calls) == ["failed async", "success"]
    await root.fiber.dispose()


@pytest.mark.asyncio
async def test_parallel_returning_exception_as_value_does_not_raise() -> None:
    root = Context()
    root.on("event", lambda: ValueError("ordinary value"))
    await root.parallel("event")
    await root.fiber.dispose()


@pytest.mark.asyncio
async def test_parallel_single_failure_is_still_grouped() -> None:
    root = Context()

    def callback() -> None:
        raise ValueError("one")

    root.on("event", callback)
    with pytest.raises(ExceptionGroup) as error:
        await root.parallel("event")
    assert len(error.value.exceptions) == 1
    await root.fiber.dispose()


@pytest.mark.asyncio
async def test_serial_order_and_bail() -> None:
    root = Context()
    calls: list[str] = []

    async def first() -> object:
        calls.append("first start")
        await asyncio.sleep(0)
        calls.append("first end")
        return False

    def second() -> object:
        calls.append("second")
        return 0

    root.on("event", first)
    root.on("event", second)
    root.on("event", lambda: calls.append("unexpected"))
    assert await root.serial("event") == 0
    assert calls == ["first start", "first end", "second"]
    await root.fiber.dispose()


@pytest.mark.asyncio
async def test_serial_failure_stops_peers_and_no_result_returns_none() -> None:
    root = Context()
    assert await root.serial("event") is None
    calls: list[int] = []

    async def callback() -> None:
        raise ValueError("serial")

    root.on("event", callback)
    root.on("event", lambda: calls.append(1))
    with pytest.raises(ValueError, match="serial"):
        await root.serial("event")
    assert calls == []
    await root.fiber.dispose()


def test_waterfall_wrap_order_fixed_args_and_terminal() -> None:
    root = Context()
    calls: list[str] = []

    def first(value: int, next_: Callable[[], int]) -> int:
        calls.append("first before")
        result = value + next_()
        calls.append("first after")
        return result

    def second(value: int, next_: Callable[[], int]) -> int:
        calls.append("second before")
        result = value + next_()
        calls.append("second after")
        return result

    def terminal() -> int:
        calls.append("terminal")
        return 2

    root.on("event", first)
    root.on("event", second)
    assert root.waterfall("event", 1, next_=terminal) == 4
    assert calls == ["first before", "second before", "terminal", "second after", "first after"]


def test_waterfall_veto_skips_remaining_chain_and_terminal() -> None:
    root = Context()
    root.on("event", lambda value, next_: value)
    root.on("event", lambda value, next_: pytest.fail("vetoed"))
    assert root.waterfall("event", 3, next_=lambda: pytest.fail("vetoed")) == 3


def test_waterfall_repeated_next_preserves_pinned_source_queue_semantics() -> None:
    root = Context()
    calls: list[str] = []

    def callback(next_: Callable[[], object]) -> object:
        next_()
        return next_()

    root.on("event", callback)

    def terminal() -> object:
        calls.append("terminal")
        return 2

    assert root.waterfall("event", next_=terminal) == 2
    assert calls == ["terminal", "terminal"]


@pytest.mark.asyncio
async def test_async_waterfall_can_await_sync_tail_with_correct_order() -> None:
    root = Context()
    calls: list[str] = []

    async def first(value: int, next_: Callable[[], Awaitable[int]]) -> int:
        calls.append("first before")
        result = await next_()
        calls.append("first after")
        return value + result

    def second(value: int, next_: Callable[[], object]) -> object:
        calls.append("second")
        return next_()

    root.on("event", first)
    root.on("event", second)
    result = await resolved(root.waterfall("event", 1, next_=lambda: 2))
    assert result == 3
    assert calls == ["first before", "second", "first after"]
    await root.fiber.dispose()


@pytest.mark.asyncio
async def test_async_waterfall_flattens_returned_continuation_awaitable() -> None:
    root = Context()

    async def first(next_: Callable[[], object]) -> object:
        return next_()

    root.on("event", first)

    async def terminal() -> object:
        return "terminal"

    assert await resolved(root.waterfall("event", next_=terminal)) == "terminal"
    await root.fiber.dispose()


@pytest.mark.asyncio
async def test_async_callable_waterfall_bridge_and_veto() -> None:
    class Middleware:
        async def __call__(self, next_: Callable[[], Awaitable[object]]) -> object:
            return await next_()

    root = Context()
    root.on("event", Middleware())
    assert await resolved(root.waterfall("event", next_=lambda: "ok")) == "ok"
    await root.fiber.dispose()


def test_waterfall_error_propagates() -> None:
    root = Context()

    def callback(next_: Callable[[], object]) -> None:
        raise ValueError("waterfall")

    root.on("event", callback)
    with pytest.raises(ValueError, match="waterfall"):
        root.waterfall("event", next_=lambda: None)


@pytest.mark.parametrize("mode", ["emit", "bail", "serial", "parallel", "waterfall"])
@pytest.mark.asyncio
async def test_explicit_filter_and_global_option_for_every_dispatch(mode: str) -> None:
    root = Context()
    left, right = root.extend({"scope": "left"}), root.extend({"scope": "right"})
    calls: list[str] = []

    def callback(label: str) -> Callable[..., object]:
        def call(*args: object) -> object:
            calls.append(label)
            return None

        return call

    left.on("event", callback("left"))
    right.on("event", callback("right"))
    right.on("event", callback("global"), global_=True)
    options: dict[str, object] = {"filter_": lambda ctx: ctx.metadata["scope"] == "left"}
    if mode == "waterfall":
        # Veto is intentional: the global listener is not reached in this mode.
        options["next_"] = lambda: None
    result = getattr(root, mode)("event", **options)
    await resolved(result)
    assert calls == (["left"] if mode == "waterfall" else ["left", "global"])
    await root.fiber.dispose()


def test_child_dispatch_does_not_implicitly_filter_siblings() -> None:
    root = Context()
    calls: list[str] = []
    left, right = root.extend(), root.extend()
    left.on("event", lambda: calls.append("left"))
    right.on("event", lambda: calls.append("right"))
    left.emit("event")
    assert calls == ["left", "right"]


def test_dispatch_telemetry_does_not_recurse_and_observes_before_delivery() -> None:
    root = Context()
    calls: list[object] = []
    root.on("internal/dispatch", lambda *args: calls.append(args))
    root.on("event", lambda value: calls.append(value))
    root.emit("event", "value")
    assert calls == [("emit", "event", ("value",), None), "value"]
    root.emit("internal/example")
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_parallel_telemetry_preserves_historical_emit_mode() -> None:
    root = Context()
    calls: list[object] = []
    root.on("internal/dispatch", lambda mode, *args: calls.append(mode))
    await root.parallel("event")
    assert calls == ["emit"]
    await root.fiber.dispose()


@pytest.mark.asyncio
async def test_owner_unload_removes_listeners_and_restart_restores_registration() -> None:
    root = Context()
    calls: list[int] = []

    def plugin(ctx: Context, config: object) -> None:
        ctx.on("event", lambda: calls.append(1))

    fiber = await root.plugin(plugin)
    root.emit("event")
    await fiber.restart()
    root.emit("event")
    assert calls == [1, 1]
    await fiber.dispose()
    root.emit("event")
    assert calls == [1, 1]
    assert fiber.get_effects() == ()
    await root.fiber.dispose()


@pytest.mark.asyncio
async def test_service_dependency_loss_and_start_failure_remove_listeners() -> None:
    root = Context()
    binding = root.provide("database", object())
    calls: list[int] = []

    def consumer(ctx: Context, config: object) -> None:
        ctx.on("event", lambda: calls.append(1))

    fiber = await root.inject(["database"], consumer)
    result = binding()
    assert result is not None
    await result
    root.emit("event")
    assert calls == []

    class Broken(Service):
        name = "broken"

        def start(self) -> object:
            self.ctx.on("event", lambda: calls.append(2))
            raise ValueError("failed")

    owner = root.plugin(Broken)
    with pytest.raises(ValueError):
        await owner
    root.emit("event")
    assert calls == []
    assert fiber.get_effects() == owner.get_effects() == ()
    await root.fiber.dispose()


@pytest.mark.asyncio
async def test_pending_listener_is_owned_and_disposal_removes_it() -> None:
    root = Context()
    fiber = await root.inject(["missing"], lambda ctx, cfg: None)
    calls: list[int] = []
    fiber.ctx.on("event", lambda: calls.append(1))
    root.emit("event")
    await fiber.dispose()
    root.emit("event")
    assert calls == [1]


@pytest.mark.asyncio
async def test_unloading_and_disposed_owner_reject_registration() -> None:
    root = Context()
    started, release = asyncio.Event(), asyncio.Event()

    def plugin(ctx: Context, cfg: object) -> object:
        async def cleanup() -> None:
            started.set()
            await release.wait()

        return cleanup

    fiber = await root.plugin(plugin)
    disposal = asyncio.ensure_future(fiber.dispose())
    await started.wait()
    with pytest.raises(CordisError):
        fiber.ctx.on("event", lambda: None)
    release.set()
    await disposal
    with pytest.raises(CordisError):
        fiber.ctx.once("event", lambda: None)
    assert fiber.get_effects() == ()


@pytest.mark.asyncio
async def test_async_once_removes_before_concurrent_parallel_dispatch() -> None:
    root = Context()
    calls: list[int] = []

    async def listener() -> None:
        await asyncio.sleep(0)
        calls.append(1)

    root.once("event", listener)
    await asyncio.gather(root.parallel("event"), root.parallel("event"))
    assert calls == [1]
    await root.fiber.dispose()


@pytest.mark.asyncio
async def test_parallel_cancellation_cancels_callbacks_and_runs_their_finalizers() -> None:
    root = Context()
    started = asyncio.Event()
    calls: list[str] = []

    async def listener() -> None:
        try:
            started.set()
            await asyncio.Event().wait()
        finally:
            calls.append("finalized")

    root.on("event", listener)
    task = asyncio.create_task(root.parallel("event"))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert calls == ["finalized"]
    await root.fiber.dispose()


@pytest.mark.parametrize("name", ["", None, 1])
def test_invalid_event_names_are_atomic(name: object) -> None:
    root = Context()
    with pytest.raises(TypeError):
        root.on(cast(str, name), lambda: None)
    assert root.fiber.get_effects() == ()


def test_invalid_listener_options_and_async_filter_are_rejected() -> None:
    root = Context()
    with pytest.raises(TypeError):
        root.once("event", cast(Callable[..., object], 1))
    with pytest.raises(TypeError):
        root.on("event", lambda: None, prepend=cast(bool, 1))

    async def filter_(ctx: Context) -> bool:
        return True

    with pytest.raises(TypeError, match="synchronous"):
        root.emit("event", filter_=cast(Callable[[Context], bool], filter_))
    assert root.fiber.get_effects() == ()


@pytest.mark.asyncio
async def test_async_dispatch_can_return_self_settling_effect_handles() -> None:
    root = Context()
    effects: list[Effect] = []

    def listener() -> Effect:
        effect = root.effect(lambda: None)
        effects.append(effect)
        return effect

    root.on("event", listener)
    async with asyncio.timeout(2):
        assert await root.serial("event") is effects[0]
        await root.parallel("event")
    assert len(effects) == 2
    await root.fiber.dispose()


@pytest.mark.asyncio
async def test_async_dispatch_rejects_indirect_awaitable_result_cycles() -> None:
    root = Context()
    loop = asyncio.get_running_loop()
    first: asyncio.Future[object] = loop.create_future()
    second: asyncio.Future[object] = loop.create_future()
    first.set_result(second)
    second.set_result(first)
    root.on("event", lambda: first)
    with pytest.raises(ValueError, match="cyclic"):
        await root.serial("event")
    await root.fiber.dispose()
