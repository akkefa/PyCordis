"""Lifecycle adaptations of pinned Cordis fiber.spec.ts and Harness regressions.

Harness: 639ed015397290b3745d163aafe02ffee4aa3f84. Epoch tests use a private
lifecycle input; they do not claim implemented service injection or effects.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

import pytest

from deepseek_cordis import Context, CordisError, Fiber, FiberState


def assert_state(fiber: Fiber, expected: FiberState) -> None:
    assert fiber.state is expected


async def settle_disposal(disposal: Awaitable[None]) -> None:
    await disposal


def test_root_is_active_without_a_loop() -> None:
    ctx = Context()
    assert ctx.fiber.uid == 0
    assert ctx.fiber.state is FiberState.ACTIVE
    assert ctx.fiber.ctx is ctx
    assert ctx.extend().fiber is ctx.fiber
    assert ctx.fiber.name == "root"


def test_mount_without_running_loop_does_not_change_root() -> None:
    ctx = Context()
    with pytest.raises(RuntimeError, match="running event loop"):
        Fiber(ctx, lambda ctx, config: None)
    assert ctx.fiber.state is FiberState.ACTIVE


@pytest.mark.asyncio
async def test_sync_setup_context_config_and_identity() -> None:
    root = Context().extend({"label": "parent"})
    seen: list[tuple[Context, object]] = []
    config: dict[str, object] = {}
    fiber = Fiber(root, lambda ctx, config: seen.append((ctx, config)), config, name="worker")
    assert_state(fiber, FiberState.LOADING)
    assert seen == []
    assert await fiber is fiber
    assert_state(fiber, FiberState.ACTIVE)
    assert fiber.ctx.parent is root
    assert fiber.ctx.root is root.root
    assert fiber.ctx.owner is fiber.ctx
    assert fiber.ctx.fiber is fiber
    assert fiber.ctx.extend().fiber is fiber
    assert fiber.ctx.metadata["label"] == "parent"
    assert seen == [(fiber.ctx, config)]
    assert seen[0][1] is config
    assert fiber.name == "worker"
    await root.fiber.dispose()


@pytest.mark.asyncio
async def test_async_setup_and_cleanup_are_awaited() -> None:
    started, release = asyncio.Event(), asyncio.Event()
    sequence: list[str] = []

    async def setup(ctx: Context, config: object) -> object:
        started.set()
        await release.wait()
        sequence.append("setup")

        async def cleanup() -> None:
            await asyncio.sleep(0)
            sequence.append("cleanup")

        return cleanup

    fiber = Fiber(Context(), setup)
    await started.wait()
    assert_state(fiber, FiberState.LOADING)
    release.set()
    await fiber
    await fiber.dispose()
    assert sequence == ["setup", "cleanup"]
    assert_state(fiber, FiberState.DISPOSED)
    assert fiber.uid is None


@pytest.mark.asyncio
async def test_pending_is_settled_and_does_not_execute_setup() -> None:
    calls: list[str] = []
    fiber = Fiber(Context(), lambda ctx, config: calls.append("setup"))
    fiber._set_epoch(None)
    await fiber
    assert_state(fiber, FiberState.PENDING)
    assert calls == []
    await fiber.restart()
    assert_state(fiber, FiberState.PENDING)
    await fiber.dispose()


@pytest.mark.asyncio
async def test_disposal_before_checkpoint_skips_setup() -> None:
    calls: list[str] = []
    fiber = Fiber(Context(), lambda ctx, config: calls.append("setup"))
    disposal = fiber.dispose()
    assert fiber.uid is None
    await disposal
    assert calls == []
    assert_state(fiber, FiberState.DISPOSED)


@pytest.mark.asyncio
async def test_pending_cleanup_drains_on_disposal() -> None:
    calls: list[str] = []
    fiber = Fiber(Context(), lambda ctx, config: None)
    fiber._set_epoch(None)
    await fiber
    fiber.add_cleanup(lambda: calls.append("pending cleanup"))
    await fiber.dispose()
    assert calls == ["pending cleanup"]


@pytest.mark.asyncio
async def test_setup_failure_rolls_back_registered_cleanup_and_surfaces_error() -> None:
    failure = ValueError("setup failed")
    calls: list[str] = []

    def setup(ctx: Context, config: object) -> None:
        ctx.fiber.add_cleanup(lambda: calls.append("rollback"))
        raise failure

    fiber = Fiber(Context(), setup)
    with pytest.raises(ValueError, match="setup failed"):
        await fiber
    assert_state(fiber, FiberState.FAILED)
    assert fiber.error is failure
    assert calls == ["rollback"]
    await fiber.dispose()
    assert calls == ["rollback"]
    assert_state(fiber, FiberState.DISPOSED)
    with pytest.raises(ValueError):
        await fiber


@pytest.mark.asyncio
async def test_restart_recovers_from_setup_failure() -> None:
    calls = 0

    def setup(ctx: Context, config: object) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ValueError("first run")

    fiber = Fiber(Context(), setup)
    with pytest.raises(ValueError):
        await fiber
    await fiber.restart()
    assert_state(fiber, FiberState.ACTIVE)
    assert fiber.error is None
    assert calls == 2
    await fiber.dispose()


@pytest.mark.asyncio
async def test_invalid_setup_result_is_failure() -> None:
    fiber = Fiber(Context(), lambda ctx, config: 1)
    with pytest.raises(TypeError, match="cleanup callable"):
        await fiber
    assert_state(fiber, FiberState.FAILED)
    await fiber.dispose()


@pytest.mark.asyncio
async def test_cleanup_starts_reverse_order_and_does_not_starve_after_failure() -> None:
    starts: list[int] = []
    gate = asyncio.Event()
    started = asyncio.Event()

    async def async_cleanup() -> None:
        starts.append(3)
        started.set()
        await gate.wait()

    def fail() -> None:
        starts.append(2)
        raise ValueError("cleanup failure")

    fiber = await Fiber(Context(), lambda ctx, config: None)
    fiber.add_cleanup(lambda: starts.append(1))
    fiber.add_cleanup(fail)
    fiber.add_cleanup(async_cleanup)
    waiter = asyncio.create_task(settle_disposal(fiber.dispose()))
    await started.wait()
    await asyncio.sleep(0)
    assert starts == [3, 2, 1]
    assert not waiter.done()
    gate.set()
    await waiter
    assert_state(fiber, FiberState.DISPOSED)
    assert len(fiber.cleanup_errors) == 1
    assert isinstance(fiber.cleanup_errors[0], ValueError)


@pytest.mark.asyncio
async def test_repeated_disposal_joins_one_cleanup() -> None:
    started, release = asyncio.Event(), asyncio.Event()
    calls = 0

    async def cleanup() -> None:
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()

    fiber = await Fiber(Context(), lambda ctx, config: cleanup)
    first = asyncio.create_task(settle_disposal(fiber.dispose()))
    await started.wait()
    second = asyncio.create_task(settle_disposal(fiber.dispose()))
    await asyncio.sleep(0)
    assert not first.done() and not second.done()
    release.set()
    await asyncio.gather(first, second)
    await fiber.dispose()
    assert calls == 1


@pytest.mark.asyncio
async def test_parent_disposal_joins_child_disposal_started_earlier() -> None:
    root = Context()
    started, release = asyncio.Event(), asyncio.Event()

    async def cleanup() -> None:
        started.set()
        await release.wait()

    parent = await Fiber(root, lambda ctx, config: None)
    child = await Fiber(parent.ctx, lambda ctx, config: cleanup)
    child_wait = asyncio.create_task(settle_disposal(child.dispose()))
    await started.wait()
    parent_wait = asyncio.create_task(settle_disposal(parent.dispose()))
    await asyncio.sleep(0)
    assert not parent_wait.done()
    release.set()
    await asyncio.gather(child_wait, parent_wait)
    assert child.state is parent.state is FiberState.DISPOSED


@pytest.mark.asyncio
async def test_child_created_during_setup_owned_before_parent_disposal() -> None:
    root = Context()
    children: list[Fiber] = []
    calls: list[str] = []

    def setup(ctx: Context, config: object) -> None:
        children.append(Fiber(ctx, lambda ctx, config: calls.append("child setup")))
        ctx.fiber.dispose()  # Request without awaiting our own transition.

    parent = Fiber(root, setup)
    await parent
    assert parent.state is FiberState.DISPOSED
    assert children[0].state is FiberState.DISPOSED
    assert calls == []


@pytest.mark.asyncio
async def test_loss_during_loading_waits_for_setup_then_unloads() -> None:
    started, release = asyncio.Event(), asyncio.Event()
    calls: list[str] = []

    async def setup(ctx: Context, config: object) -> object:
        started.set()
        await release.wait()
        calls.append("setup")
        return lambda: calls.append("cleanup")

    fiber = Fiber(Context(), setup)
    await started.wait()
    fiber._set_epoch(None)
    assert_state(fiber, FiberState.LOADING)
    release.set()
    await fiber
    assert_state(fiber, FiberState.PENDING)
    assert calls == ["setup", "cleanup"]
    await fiber.dispose()


@pytest.mark.asyncio
async def test_identity_change_during_loading_unloads_then_reloads() -> None:
    started, release = asyncio.Event(), asyncio.Event()
    calls: list[str] = []

    async def setup(ctx: Context, config: object) -> object:
        calls.append("setup")
        if len(calls) == 1:
            started.set()
            await release.wait()
        return lambda: calls.append("cleanup")

    fiber = Fiber(Context(), setup)
    await started.wait()
    fiber._set_epoch((2,))
    release.set()
    await fiber
    assert calls == ["setup", "cleanup", "setup"]
    assert_state(fiber, FiberState.ACTIVE)
    await fiber.dispose()


@pytest.mark.asyncio
async def test_return_to_same_epoch_during_loading_keeps_activation() -> None:
    started, release = asyncio.Event(), asyncio.Event()
    calls: list[str] = []

    async def setup(ctx: Context, config: object) -> object:
        started.set()
        await release.wait()
        return lambda: calls.append("cleanup")

    fiber = Fiber(Context(), setup)
    await started.wait()
    fiber._set_epoch(None)
    fiber._set_epoch(())
    release.set()
    await fiber
    assert_state(fiber, FiberState.ACTIVE)
    assert calls == []
    await fiber.dispose()


@pytest.mark.asyncio
async def test_restoration_during_unload_waits_for_cleanup_before_loading() -> None:
    started, release = asyncio.Event(), asyncio.Event()
    calls: list[str] = []

    async def cleanup() -> None:
        started.set()
        await release.wait()
        calls.append("cleanup")

    def setup(ctx: Context, config: object) -> object:
        calls.append("setup")
        return cleanup

    fiber = await Fiber(Context(), setup)
    fiber._set_epoch(None)
    await started.wait()
    fiber._set_epoch((3,))
    assert_state(fiber, FiberState.UNLOADING)
    assert calls == ["setup"]
    release.set()
    await fiber
    assert calls == ["setup", "cleanup", "setup"]
    assert_state(fiber, FiberState.ACTIVE)
    await fiber.dispose()


@pytest.mark.asyncio
async def test_reentrant_await_fails_instead_of_deadlocking_and_still_disposes() -> None:
    async def setup(ctx: Context, config: object) -> None:
        await ctx.fiber.dispose()

    fiber = Fiber(Context(), setup)
    with pytest.raises(CordisError, match="own or ancestor"):
        await fiber
    assert_state(fiber, FiberState.DISPOSED)
    assert isinstance(fiber.error, CordisError)


@pytest.mark.asyncio
async def test_cleanup_cannot_register_more_cleanup_or_children() -> None:
    errors: list[str] = []

    def cleanup() -> None:
        callbacks: list[Callable[[], object]] = [
            lambda: fiber.add_cleanup(lambda: None),
            lambda: Fiber(fiber.ctx, lambda ctx, config: None),
        ]
        for callback in callbacks:
            try:
                callback()
            except CordisError as error:
                errors.append(error.code)

    fiber = await Fiber(Context(), lambda ctx, config: cleanup)
    await fiber.restart()
    assert errors == ["INACTIVE_EFFECT", "INACTIVE_EFFECT"]
    await fiber.dispose()


@pytest.mark.asyncio
async def test_cleanup_self_disposal_await_is_contained() -> None:
    async def cleanup() -> None:
        await fiber.dispose()

    fiber = await Fiber(Context(), lambda ctx, config: cleanup)
    await fiber.dispose()
    assert_state(fiber, FiberState.DISPOSED)
    assert isinstance(fiber.cleanup_errors[0], CordisError)


@pytest.mark.asyncio
async def test_cancelling_waiter_does_not_cancel_setup_or_disposal() -> None:
    started, release = asyncio.Event(), asyncio.Event()

    async def setup(ctx: Context, config: object) -> None:
        started.set()
        await release.wait()

    fiber = Fiber(Context(), setup)
    await started.wait()
    waiter = asyncio.create_task(fiber.wait())
    await asyncio.sleep(0)
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter
    disposal = asyncio.create_task(settle_disposal(fiber.dispose()))
    await asyncio.sleep(0)
    disposal.cancel()
    with pytest.raises(asyncio.CancelledError):
        await disposal
    release.set()
    await fiber.dispose()
    assert_state(fiber, FiberState.DISPOSED)
    assert fiber.error is None


@pytest.mark.asyncio
async def test_root_disposal_restarts_root_and_disposes_children() -> None:
    root = Context()
    child = await Fiber(root, lambda ctx, config: None)
    await root.fiber.dispose()
    assert child.state is FiberState.DISPOSED
    assert root.fiber.state is FiberState.ACTIVE
    assert root.fiber.uid == 0
    later = await Fiber(root, lambda ctx, config: None)
    assert later.uid == 2
    await root.fiber.dispose()


@pytest.mark.asyncio
async def test_restart_disposed_fiber_is_rejected() -> None:
    fiber = await Fiber(Context(), lambda ctx, config: None)
    await fiber.dispose()
    with pytest.raises(CordisError) as error:
        fiber.restart()
    assert error.value.code == "INACTIVE_EFFECT"


@pytest.mark.asyncio
async def test_dispose_during_setup_waits_for_setup_and_returned_cleanup() -> None:
    setup_started, setup_release = asyncio.Event(), asyncio.Event()
    cleanup_started, cleanup_release = asyncio.Event(), asyncio.Event()

    async def setup(ctx: Context, config: object) -> object:
        setup_started.set()
        await setup_release.wait()

        async def cleanup() -> None:
            cleanup_started.set()
            await cleanup_release.wait()

        return cleanup

    fiber = Fiber(Context(), setup)
    await setup_started.wait()
    waiter = asyncio.create_task(settle_disposal(fiber.dispose()))
    await asyncio.sleep(0)
    assert not waiter.done()
    setup_release.set()
    await cleanup_started.wait()
    assert not waiter.done()
    cleanup_release.set()
    await waiter
    assert_state(fiber, FiberState.DISPOSED)


@pytest.mark.asyncio
async def test_setup_cancellation_becomes_retained_failure_and_rolls_back() -> None:
    cleaned: list[str] = []

    async def setup(ctx: Context, config: object) -> None:
        ctx.fiber.add_cleanup(lambda: cleaned.append("cleanup"))
        raise asyncio.CancelledError("setup cancelled itself")

    fiber = Fiber(Context(), setup)
    with pytest.raises(asyncio.CancelledError):
        await fiber
    assert_state(fiber, FiberState.FAILED)
    assert cleaned == ["cleanup"]
    assert isinstance(fiber.error, asyncio.CancelledError)
    await fiber.dispose()


@pytest.mark.asyncio
async def test_failed_fiber_can_retry_when_epoch_is_refreshed() -> None:
    calls = 0

    def setup(ctx: Context, config: object) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ValueError("initial failure")

    fiber = Fiber(Context(), setup)
    with pytest.raises(ValueError):
        await fiber
    fiber._set_epoch((2,))
    await fiber
    assert calls == 2
    assert_state(fiber, FiberState.ACTIVE)
    await fiber.dispose()


@pytest.mark.asyncio
async def test_cleanup_awaiting_ancestor_disposal_is_contained() -> None:
    parent = await Fiber(Context(), lambda ctx, config: None)

    async def cleanup() -> None:
        await parent.dispose()

    child = await Fiber(parent.ctx, lambda ctx, config: cleanup)
    await parent.dispose()
    assert_state(parent, FiberState.DISPOSED)
    assert_state(child, FiberState.DISPOSED)
    assert isinstance(child.cleanup_errors[0], CordisError)


@pytest.mark.asyncio
async def test_settled_runtime_leaves_no_lifecycle_tasks() -> None:
    current = asyncio.current_task()
    before = asyncio.all_tasks() - {current}
    root = Context()
    parent = await Fiber(root, lambda ctx, config: None)
    child = await Fiber(parent.ctx, lambda ctx, config: None)
    await root.fiber.dispose()
    assert_state(parent, FiberState.DISPOSED)
    assert_state(child, FiberState.DISPOSED)
    assert asyncio.all_tasks() - {current} == before


def test_live_fiber_cannot_be_reused_on_another_event_loop() -> None:
    root = Context()

    async def first() -> None:
        await Fiber(root, lambda ctx, config: None)
        await root.fiber.dispose()

    async def second() -> None:
        with pytest.raises(RuntimeError, match="event loops"):
            Fiber(root, lambda ctx, config: None)

    asyncio.run(first())
    asyncio.run(second())
