"""Pinned Harness lifecycle regressions; publication-hook portions stay deferred."""

from __future__ import annotations

import asyncio
from collections.abc import Generator

import pytest

from deepseek_cordis import Context, FiberState

pytestmark = [pytest.mark.asyncio, pytest.mark.compatibility]


async def test_reentrant_restart_joins_effect_setup_and_returned_cleanup() -> None:
    root = Context()
    entered = asyncio.Event()
    setup_release = asyncio.Event()
    cleanup_entered = asyncio.Event()
    cleanup_release = asyncio.Event()
    finished: list[str] = []

    async def setup() -> object:
        root.fiber.restart()
        entered.set()
        await setup_release.wait()
        finished.append("setup")

        async def cleanup() -> None:
            cleanup_entered.set()
            await cleanup_release.wait()
            finished.append("cleanup")

        return cleanup

    root.effect(setup, "reentrant-restart")
    await entered.wait()
    waiting = asyncio.create_task(root.fiber.wait())
    await asyncio.sleep(0)
    assert not waiting.done()
    setup_release.set()
    await cleanup_entered.wait()
    assert finished == ["setup"]
    assert not waiting.done()
    cleanup_release.set()
    await waiting
    assert finished == ["setup", "cleanup"]
    assert root.fiber.get_effects() == ()
    assert root.fiber.state is FiberState.ACTIVE


async def test_reentrant_restart_joins_async_rollback_after_sync_setup_error() -> None:
    root = Context()
    entered = asyncio.Event()
    release = asyncio.Event()

    async def cleanup() -> None:
        entered.set()
        await release.wait()

    def setup() -> Generator[object, None, None]:
        yield cleanup
        root.fiber.restart()
        raise ValueError("setup failed after restart")

    with pytest.raises(ValueError, match="setup failed after restart"):
        root.effect(setup, "reentrant-throw")
    await entered.wait()
    waiting = asyncio.create_task(root.fiber.wait())
    await asyncio.sleep(0)
    assert not waiting.done()
    release.set()
    await waiting
    assert root.fiber.get_effects() == ()


async def test_parent_disposal_joins_pending_child_cleanup_without_running_setup() -> None:
    root = Context()
    owner = await root.plugin(lambda ctx, config: None)
    child = await owner.ctx.inject(["missing"], lambda ctx, config: pytest.fail("child ran"))
    entered = asyncio.Event()
    release = asyncio.Event()
    finished: list[bool] = []

    async def cleanup() -> None:
        entered.set()
        await release.wait()
        finished.append(True)

    child.ctx.effect(lambda: cleanup, "pending-child-cleanup")
    disposal = owner.dispose()
    await entered.wait()
    waiting = asyncio.create_task(owner.wait())
    await asyncio.sleep(0)
    assert not waiting.done()
    release.set()
    await disposal
    await waiting
    assert finished == [True]
    assert child.state is owner.state is FiberState.DISPOSED
    assert root.registry.size == 0
