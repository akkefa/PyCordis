"""Adapted from pinned dispose.spec.ts and Harness cordis-lifecycle.spec.ts.

Reference: Harness 639ed015397290b3745d163aafe02ffee4aa3f84. Drain-all cleanup
and Python async-generator finalization are intentional compatibility deviations.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Generator

import pytest

from deepseek_cordis import Context, CordisError, Effect, EffectMeta, Fiber, FiberState


async def join(value: Awaitable[None] | None) -> None:
    if value is not None:
        await value


def test_sync_setup_and_cleanup_are_immediate_single_shot() -> None:
    calls: list[str] = []
    ctx = Context()

    def setup() -> object:
        calls.append("setup")
        return lambda: calls.append("cleanup")

    effect = ctx.effect(setup, "resource")
    assert calls == ["setup"]
    assert ctx.fiber.get_effects() == (EffectMeta("resource"),)
    assert effect() is None
    assert calls == ["setup", "cleanup"]
    assert effect() is None
    assert ctx.fiber.get_effects() == ()


def test_nested_generator_transfers_ownership_and_reverses_cleanup() -> None:
    calls: list[int] = []
    ctx = Context()

    def setup() -> Generator[object, None, None]:
        yield lambda: calls.append(1)
        yield ctx.effect(lambda: lambda: calls.append(2), "child")
        yield lambda: calls.append(3)

    effect = ctx.effect(setup, "outer")
    assert ctx.fiber.get_effects() == (EffectMeta("outer", (EffectMeta("child"),)),)
    assert effect() is None
    assert calls == [3, 2, 1]
    assert ctx.fiber.get_effects() == ()


def test_generator_return_value_is_collected() -> None:
    calls: list[int] = []

    def setup() -> Generator[object, None, object]:
        yield lambda: calls.append(1)
        return lambda: calls.append(2)

    Context().effect(setup)()
    assert calls == [2, 1]


def test_sync_setup_failure_rolls_back_and_detaches() -> None:
    calls: list[str] = []
    ctx = Context()

    def setup() -> Generator[object, None, None]:
        yield lambda: calls.append("rollback")
        raise ValueError("setup failure")

    with pytest.raises(ValueError, match="setup failure"):
        ctx.effect(setup)
    assert calls == ["rollback"]
    assert ctx.fiber.get_effects() == ()


@pytest.mark.parametrize("result", [1, "invalid", {"invalid": 1}, [1]])
def test_invalid_setup_result_is_rejected(result: object) -> None:
    ctx = Context()
    with pytest.raises(TypeError):
        ctx.effect(lambda: result)
    assert ctx.fiber.get_effects() == ()


def test_cleanup_errors_drain_all_and_aggregate() -> None:
    calls: list[int] = []

    def fail(value: int) -> None:
        calls.append(value)
        raise ValueError(str(value))

    def setup() -> object:
        return [lambda: calls.append(1), lambda: fail(2), lambda: fail(3)]

    effect = Context().effect(setup)
    with pytest.raises(ExceptionGroup) as failure:
        effect()
    assert calls == [3, 2, 1]
    assert len(failure.value.exceptions) == 2
    assert effect() is None


@pytest.mark.asyncio
async def test_await_effect_settles_setup_without_disposing() -> None:
    calls: list[str] = []

    async def setup() -> object:
        await asyncio.sleep(0)
        calls.append("setup")
        return lambda: calls.append("cleanup")

    ctx = Context()
    effect = ctx.effect(setup)
    assert await effect is effect
    assert calls == ["setup"]
    await join(effect())
    assert calls == ["setup", "cleanup"]


@pytest.mark.asyncio
async def test_owner_unload_waits_for_effect_setup_and_async_cleanup() -> None:
    ctx = Context()
    started, setup_gate = asyncio.Event(), asyncio.Event()
    cleanup_started, cleanup_gate = asyncio.Event(), asyncio.Event()

    async def setup() -> object:
        ctx.fiber.restart()  # Owner request made inside effect setup.
        started.set()
        await setup_gate.wait()

        async def cleanup() -> None:
            cleanup_started.set()
            await cleanup_gate.wait()

        return cleanup

    ctx.effect(setup)
    await started.wait()
    waiter = asyncio.create_task(ctx.fiber.wait())
    setup_gate.set()
    await cleanup_started.wait()
    assert not waiter.done()
    cleanup_gate.set()
    await waiter
    assert ctx.fiber.state is FiberState.ACTIVE
    assert ctx.fiber.get_effects() == ()


@pytest.mark.asyncio
async def test_manual_cleanup_remains_visible_until_owner_joins_it() -> None:
    ctx = Context()
    started, release = asyncio.Event(), asyncio.Event()
    calls = 0

    async def cleanup() -> None:
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()

    effect = ctx.effect(lambda: cleanup, "inflight")
    first = effect()
    await started.wait()
    assert effect() is None  # Public handle is single-shot, not an awaitable join.
    assert ctx.fiber.get_effects() == (EffectMeta("inflight"),)
    owner = asyncio.create_task(ctx.fiber.restart().wait())
    await asyncio.sleep(0)
    assert not owner.done()
    release.set()
    await join(first)
    await owner
    assert calls == 1
    assert ctx.fiber.get_effects() == ()


@pytest.mark.asyncio
async def test_outer_joins_child_cleanup_already_running() -> None:
    ctx = Context()
    started, release = asyncio.Event(), asyncio.Event()
    effects: list[Effect] = []
    calls: list[str] = []

    async def cleanup() -> None:
        started.set()
        await release.wait()
        calls.append("child")

    def setup() -> object:
        child = ctx.effect(lambda: cleanup, "child")
        effects.append(child)
        return [child]

    outer = ctx.effect(setup, "outer")
    first = effects[0]()
    await started.wait()
    waiter = asyncio.create_task(join(outer()))
    await asyncio.sleep(0)
    assert not waiter.done()
    release.set()
    await join(first)
    await waiter
    assert calls == ["child"]
    assert ctx.fiber.get_effects() == ()


@pytest.mark.asyncio
async def test_sync_failure_async_rollback_stays_owned_during_restart() -> None:
    ctx = Context()
    started, release = asyncio.Event(), asyncio.Event()

    async def cleanup() -> None:
        started.set()
        await release.wait()

    def setup() -> Generator[object, None, None]:
        yield cleanup
        ctx.fiber.restart()
        raise ValueError("setup failure")

    with pytest.raises(ValueError):
        ctx.effect(setup, "rollback")
    await started.wait()
    waiter = asyncio.create_task(ctx.fiber.wait())
    await asyncio.sleep(0)
    assert not waiter.done()
    release.set()
    await waiter
    assert ctx.fiber.get_effects() == ()


@pytest.mark.asyncio
async def test_async_generator_stops_after_inflight_yield_and_closes() -> None:
    ctx = Context()
    started, release = asyncio.Event(), asyncio.Event()
    calls: list[str] = []

    async def setup() -> AsyncIterator[object]:
        try:
            started.set()
            await release.wait()
            calls.append("yield")
            yield lambda: calls.append("cleanup")
            calls.append("escaped")
        finally:
            calls.append("closed")

    effect = ctx.effect(setup)
    await started.wait()
    disposal = effect()
    release.set()
    await join(disposal)
    assert calls == ["yield", "closed", "cleanup"]
    assert ctx.fiber.get_effects() == ()


@pytest.mark.asyncio
async def test_async_setup_failure_rolls_back_before_wait_rethrows() -> None:
    calls: list[str] = []

    async def setup() -> AsyncIterator[object]:
        async def cleanup() -> None:
            await asyncio.sleep(0)
            calls.append("cleanup")

        yield cleanup
        raise ValueError("async setup failed")

    ctx = Context()
    effect = ctx.effect(setup)
    with pytest.raises(ValueError, match="async setup failed"):
        await effect
    assert calls == ["cleanup"]
    assert ctx.fiber.get_effects() == ()


@pytest.mark.asyncio
async def test_cleanup_cannot_escape_owner_unload_but_manual_cleanup_can_register() -> None:
    ctx = Context()
    created: list[Effect] = []
    first = ctx.effect(lambda: lambda: created.append(ctx.effect(lambda: None)))
    first()
    assert len(created) == 1

    def cleanup() -> None:
        ctx.effect(lambda: None)

    ctx.effect(lambda: cleanup)
    await ctx.fiber.dispose()
    assert isinstance(ctx.fiber.cleanup_errors[0], CordisError)
    assert ctx.fiber.get_effects() == ()


@pytest.mark.asyncio
async def test_effects_are_legal_pending_and_loading_and_drain_after_failure() -> None:
    calls: list[str] = []

    def setup(ctx: Context, config: object) -> None:
        ctx.effect(lambda: lambda: calls.append("loading"))
        raise ValueError("failure")

    fiber = Fiber(Context(), setup)
    fiber._set_epoch(None)
    await fiber
    fiber.ctx.effect(lambda: lambda: calls.append("pending"))
    fiber._set_epoch(())
    with pytest.raises(ValueError):
        await fiber
    assert calls == ["loading", "pending"]
    await fiber.dispose()


@pytest.mark.asyncio
async def test_plugin_generator_cleanup_integrates_with_fiber() -> None:
    calls: list[int] = []

    def setup(ctx: Context, config: object) -> Generator[object, None, None]:
        yield lambda: calls.append(1)
        yield ctx.effect(lambda: lambda: calls.append(2))

    fiber = await Fiber(Context(), setup)
    await fiber.dispose()
    assert calls == [2, 1]


@pytest.mark.asyncio
async def test_cancelled_setup_and_cleanup_waiters_do_not_cancel_effect() -> None:
    ctx = Context()
    started, release = asyncio.Event(), asyncio.Event()
    calls: list[str] = []

    async def setup() -> object:
        started.set()
        await release.wait()
        return lambda: calls.append("cleanup")

    effect = ctx.effect(setup)
    await started.wait()
    waiter = asyncio.create_task(effect.wait())
    await asyncio.sleep(0)
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter
    disposal = effect()
    cleanup_wait = asyncio.create_task(join(disposal))
    await asyncio.sleep(0)
    cleanup_wait.cancel()
    with pytest.raises(asyncio.CancelledError):
        await cleanup_wait
    release.set()
    await ctx.fiber.dispose()
    assert calls == ["cleanup"]
    assert ctx.fiber.get_effects() == ()


@pytest.mark.asyncio
async def test_reentrant_owner_await_from_effect_is_rejected_without_leak() -> None:
    ctx = Context()

    async def setup() -> None:
        await ctx.fiber.restart()

    effect = ctx.effect(setup)
    with pytest.raises(CordisError, match="own or ancestor"):
        await effect
    await ctx.fiber
    assert ctx.fiber.get_effects() == ()


@pytest.mark.asyncio
async def test_effect_owner_is_explicit_context_not_ambient_task() -> None:
    root = Context()
    child = await Fiber(root, lambda ctx, config: None)
    calls: list[str] = []
    root.effect(lambda: lambda: calls.append("root"))
    child.ctx.extend().effect(lambda: lambda: calls.append("child"))
    await child.dispose()
    assert calls == ["child"]
    await root.fiber.dispose()
    assert calls == ["child", "root"]


@pytest.mark.asyncio
async def test_nested_cross_owner_transfer_is_rejected_and_original_owner_retains_it() -> None:
    root = Context()
    child = await Fiber(root, lambda ctx, config: None)
    calls: list[str] = []
    nested = child.ctx.effect(lambda: lambda: calls.append("child"))
    with pytest.raises(ValueError, match="same Fiber"):
        root.effect(lambda: nested)
    await root.fiber.dispose()
    assert calls == ["child"]


@pytest.mark.asyncio
async def test_async_cleanup_errors_continue_sequence_and_surface_original_error() -> None:
    calls: list[int] = []

    async def fail() -> None:
        calls.append(2)
        await asyncio.sleep(0)
        raise ValueError("async cleanup")

    effect = Context().effect(lambda: [lambda: calls.append(1), fail])
    with pytest.raises(ValueError, match="async cleanup"):
        await join(effect())
    assert calls == [2, 1]


@pytest.mark.asyncio
async def test_draining_effects_leaves_no_background_tasks() -> None:
    current = asyncio.current_task()
    before = asyncio.all_tasks() - {current}
    ctx = Context()

    async def setup() -> object:
        await asyncio.sleep(0)
        return lambda: None

    ctx.effect(setup)
    await ctx.fiber.dispose()
    assert asyncio.all_tasks() - {current} == before
    assert ctx.fiber.get_effects() == ()


def test_sync_generator_is_closed_on_invalid_yield() -> None:
    calls: list[str] = []

    def setup() -> Generator[object, None, None]:
        try:
            yield lambda: calls.append("cleanup")
            yield 1
        finally:
            calls.append("closed")

    with pytest.raises(TypeError):
        Context().effect(setup)
    assert calls == ["closed", "cleanup"]


def test_async_setup_without_loop_rejects_and_detaches() -> None:
    ctx = Context()

    async def setup() -> None:
        pass

    with pytest.raises(RuntimeError, match="running event loop"):
        ctx.effect(setup)
    assert ctx.fiber.get_effects() == ()


@pytest.mark.asyncio
async def test_async_generator_plugin_epoch_loss_stops_at_checkpoint() -> None:
    started, release = asyncio.Event(), asyncio.Event()
    calls: list[str] = []

    async def setup(ctx: Context, config: object) -> AsyncIterator[object]:
        try:
            started.set()
            await release.wait()
            calls.append("yield")
            yield lambda: calls.append("cleanup")
            calls.append("escaped")
        finally:
            calls.append("closed")

    fiber = Fiber(Context(), setup)
    await started.wait()
    fiber._set_epoch(None)
    release.set()
    await fiber
    assert fiber.state is FiberState.PENDING
    assert calls == ["yield", "closed", "cleanup"]
    await fiber.dispose()


@pytest.mark.asyncio
async def test_async_setup_failure_and_bad_rollback_still_drains_remaining_cleanup() -> None:
    calls: list[str] = []

    async def fail() -> None:
        raise ValueError("rollback error")

    async def setup() -> AsyncIterator[object]:
        yield lambda: calls.append("cleanup")
        yield fail
        raise TypeError("setup error")

    ctx = Context()
    effect = ctx.effect(setup)
    with pytest.raises(TypeError, match="setup error"):
        await effect
    assert calls == ["cleanup"]
    assert ctx.fiber.get_effects() == ()
