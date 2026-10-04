"""Harness reflect/fiber adaptations; events, scope and tracing remain future."""

from __future__ import annotations

import asyncio

import pytest

from deepseek_cordis import Context, CordisError, Effect, Fiber, FiberState


def assert_state(fiber: Fiber, state: FiberState) -> None:
    assert fiber.state is state


async def remove(effect: Effect) -> None:
    result = effect()
    if result is not None:
        await result


def test_root_provision_is_synchronous_and_preserves_identity() -> None:
    ctx = Context()
    value: list[int] = []
    effect = ctx.provide("database", value)
    assert isinstance(effect, Effect)
    assert ctx.get("database") is value
    assert ctx.extend().get("database") is value
    assert ctx.require("database") is value
    assert ctx.get("missing") is None
    assert Context().get("database") is None


@pytest.mark.asyncio
async def test_owned_provision_manual_removal_is_joined_and_single_shot() -> None:
    ctx = Context()
    effect = ctx.provide("database", object())
    await remove(effect)
    assert ctx.get("database", False) is None
    assert effect() is None
    with pytest.raises(CordisError, match="not injected"):
        ctx.require("database")
    await ctx.fiber.dispose()


@pytest.mark.asyncio
async def test_duplicate_provider_fails_without_removing_original() -> None:
    ctx = Context()
    value = object()
    first = ctx.provide("database", value)
    with pytest.raises(CordisError) as error:
        ctx.provide("database", object())
    assert error.value.code == "DUPLICATE_SERVICE"
    assert ctx.get("database") is value
    assert len(ctx.fiber.get_effects()) == 1
    await remove(first)


@pytest.mark.asyncio
async def test_set_is_owned_and_updates_snapshot_without_reloading() -> None:
    root = Context()
    root.provide("database", 1)
    calls: list[Context] = []
    fiber = await root.inject(["database"], lambda ctx, config: calls.append(ctx))
    root.extend().set("database", 2)
    assert fiber.ctx.require("database") == 2
    assert len(calls) == 1
    with pytest.raises(CordisError) as error:
        fiber.ctx.set("database", 3)
    assert error.value.code == "SERVICE_OWNER"
    with pytest.raises(CordisError) as error:
        root.set("missing", 3)
    assert error.value.code == "MISSING_SERVICE"
    await root.fiber.dispose()


@pytest.mark.asyncio
async def test_dependency_pending_available_lost_and_restored() -> None:
    root = Context()
    calls: list[tuple[str, object]] = []

    def consumer(ctx: Context, config: object) -> object:
        value = ctx.require("database")
        calls.append(("setup", value))
        return lambda: calls.append(("cleanup", ctx.require("database")))

    fiber = await root.inject(["database"], consumer)
    assert_state(fiber, FiberState.PENDING)
    assert calls == []
    value = object()
    first = root.provide("database", value)
    await fiber
    assert_state(fiber, FiberState.ACTIVE)
    assert calls == [("setup", value)]
    await remove(first)
    assert_state(fiber, FiberState.PENDING)
    assert calls == [("setup", value), ("cleanup", value)]
    with pytest.raises(CordisError) as error:
        fiber.ctx.require("database")
    assert error.value.code == "INACTIVE_SERVICE"
    replacement = object()
    root.provide("database", replacement)
    await fiber
    assert calls[-1] == ("setup", replacement)
    await root.fiber.dispose()
    assert calls[-1] == ("cleanup", replacement)
    assert_state(fiber, FiberState.DISPOSED)


@pytest.mark.asyncio
async def test_declared_class_and_callable_instance_dependencies() -> None:
    root = Context()
    seen: list[object] = []

    class Plugin:
        inject = ["database"]

        def __init__(self, ctx: Context, config: object) -> None:
            seen.append(ctx.require("database"))

    class CallablePlugin:
        inject = {"database": None}

        def __call__(self, ctx: Context, config: object) -> None:
            seen.append(ctx.require("database"))

    left = await root.plugin(Plugin)
    right = await root.plugin(CallablePlugin())
    assert left.inject == right.inject == ("database",)
    assert seen == []
    value = object()
    root.provide("database", value)
    await asyncio.gather(left.wait(), right.wait())
    assert seen == [value, value]
    await root.fiber.dispose()


@pytest.mark.asyncio
async def test_multiple_requirements_all_must_be_available() -> None:
    root = Context()
    seen: list[int] = []
    fiber = await root.inject(["foo", "bar", "foo"], lambda ctx, cfg: seen.append(1))
    assert fiber.inject == ("foo", "bar")
    first = root.provide("foo", False)
    await fiber
    assert_state(fiber, FiberState.PENDING)
    root.provide("bar", None)
    await fiber
    assert seen == [1]  # None/False service values still have valid bindings.
    await remove(first)
    assert_state(fiber, FiberState.PENDING)
    await root.fiber.dispose()


@pytest.mark.asyncio
async def test_loading_provider_not_available_until_setup_finishes() -> None:
    root = Context()
    started, release = asyncio.Event(), asyncio.Event()

    async def provider(ctx: Context, config: object) -> None:
        ctx.provide("database", "value")
        started.set()
        await release.wait()

    consumer = await root.inject(["database"], lambda ctx, cfg: None)
    owner = root.plugin(provider)
    await started.wait()
    assert root.get("database") is None
    assert root.get("database", False) == "value"
    assert_state(consumer, FiberState.PENDING)
    release.set()
    await owner
    await consumer
    assert_state(consumer, FiberState.ACTIVE)
    await root.fiber.dispose()


@pytest.mark.asyncio
async def test_provider_failure_rolls_back_without_activating_consumer() -> None:
    root = Context()
    calls: list[int] = []
    consumer = await root.inject(["database"], lambda ctx, cfg: calls.append(1))

    def provider(ctx: Context, config: object) -> None:
        ctx.provide("database", 1)
        raise ValueError("failed provider")

    fiber = root.plugin(provider)
    with pytest.raises(ValueError):
        await fiber
    assert calls == []
    assert_state(consumer, FiberState.PENDING)
    assert root.get("database", False) is None
    await root.fiber.dispose()


@pytest.mark.asyncio
async def test_loading_consumer_provider_loss_waits_then_unloads_old_snapshot() -> None:
    root = Context()
    value = object()
    service = root.provide("database", value)
    started, release = asyncio.Event(), asyncio.Event()
    calls: list[object] = []

    async def consumer(ctx: Context, config: object) -> object:
        started.set()
        await release.wait()
        return lambda: calls.append(ctx.require("database"))

    fiber = root.inject(["database"], consumer)
    await started.wait()
    task = service()
    assert task is not None
    await asyncio.sleep(0)
    waiter = asyncio.ensure_future(task)
    assert not waiter.done()
    assert root.get("database") is None
    release.set()
    await waiter
    assert calls == [value]
    assert_state(fiber, FiberState.PENDING)
    await root.fiber.dispose()


@pytest.mark.asyncio
async def test_replacement_during_loading_uses_new_binding_generation() -> None:
    root = Context()
    service = root.provide("database", "old")
    started, release = asyncio.Event(), asyncio.Event()
    calls: list[tuple[str, object]] = []

    async def consumer(ctx: Context, config: object) -> object:
        value = ctx.require("database")
        calls.append(("setup", value))
        if value == "old":
            started.set()
            await release.wait()
        return lambda: calls.append(("cleanup", ctx.require("database")))

    fiber = root.inject(["database"], consumer)
    await started.wait()
    task = service()
    assert task is not None
    await asyncio.sleep(0)  # async removal first removes the old root binding
    root.provide("database", "new")
    release.set()
    await task
    await fiber
    assert calls == [("setup", "old"), ("cleanup", "old"), ("setup", "new")]
    await root.fiber.dispose()


@pytest.mark.asyncio
async def test_service_removal_joins_async_consumer_cleanup_and_keeps_snapshot() -> None:
    root = Context()
    service = root.provide("database", "old")
    started, release = asyncio.Event(), asyncio.Event()
    seen: list[object] = []

    def consumer(ctx: Context, config: object) -> object:
        async def cleanup() -> None:
            started.set()
            await release.wait()
            seen.append(ctx.require("database"))

        return cleanup

    fiber = await root.inject(["database"], consumer)
    task = service()
    assert task is not None
    await started.wait()
    waiter = asyncio.ensure_future(task)
    assert not waiter.done()
    assert_state(fiber, FiberState.UNLOADING)
    assert root.get("database") is None
    release.set()
    await waiter
    assert seen == ["old"]
    await root.fiber.dispose()


@pytest.mark.asyncio
async def test_reactive_chain_unloads_and_restores_transitively() -> None:
    root = Context()
    calls: list[str] = []

    def middle(ctx: Context, config: object) -> object:
        assert ctx.require("database") is not None
        ctx.provide("search", object())
        calls.append("middle setup")
        return lambda: calls.append("middle cleanup")

    def leaf(ctx: Context, config: object) -> object:
        ctx.require("search")
        calls.append("leaf setup")
        return lambda: calls.append("leaf cleanup")

    parent = await root.inject(["database"], middle)
    child = await root.inject(["search"], leaf)
    first = root.provide("database", object())
    await parent
    await child
    assert calls == ["middle setup", "leaf setup"]
    await remove(first)
    assert parent.state is child.state is FiberState.PENDING
    assert "leaf cleanup" in calls and "middle cleanup" in calls
    assert root.get("search", False) is None
    root.provide("database", object())
    await parent
    await child
    assert calls[-2:] == ["middle setup", "leaf setup"]
    await root.fiber.dispose()
    assert root.registry.size == 0


@pytest.mark.asyncio
async def test_root_shutdown_with_live_chain_has_no_dependency_join_cycle() -> None:
    root = Context()
    root.provide("database", object())
    middle = await root.inject(["database"], lambda ctx, cfg: ctx.provide("search", object()))
    leaf = await root.inject(["search"], lambda ctx, cfg: None)
    async with asyncio.timeout(2):
        await root.fiber.dispose()
    assert middle.state is leaf.state is FiberState.DISPOSED
    assert not root.fiber.cleanup_errors
    assert root.get("database", False) is root.get("search", False) is None


@pytest.mark.asyncio
async def test_child_inherits_parent_snapshot_without_declaring_again() -> None:
    root = Context()
    root.provide("database", "value")
    children: list[Fiber] = []

    async def parent(ctx: Context, config: object) -> None:
        children.append(await ctx.plugin(lambda inner, cfg: inner.require("database") and None))

    fiber = await root.inject(["database"], parent)
    assert children[0].ctx.require("database") == "value"
    await fiber.dispose()
    await root.fiber.dispose()


@pytest.mark.asyncio
async def test_get_escape_hatch_and_require_enforcement() -> None:
    root = Context()
    root.provide("database", object())
    fiber = await root.plugin(lambda ctx, cfg: None)
    assert fiber.ctx.get("database") is root.get("database")
    # Root-owned bindings are inherited like Cordis's root Fiber store.
    assert fiber.ctx.require("database") is root.get("database")

    async def provider(ctx: Context, cfg: object) -> None:
        ctx.provide("private", object())

    await root.plugin(provider)
    assert fiber.ctx.get("private") is not None
    with pytest.raises(CordisError) as error:
        fiber.ctx.require("private")
    assert error.value.code == "UNDECLARED_SERVICE"
    await root.fiber.dispose()


@pytest.mark.asyncio
async def test_pending_disposal_never_runs_after_provider_appears() -> None:
    root = Context()
    seen: list[int] = []
    fiber = await root.inject(["database"], lambda ctx, cfg: seen.append(1))
    await fiber.dispose()
    root.provide("database", object())
    await asyncio.sleep(0)
    assert seen == []
    assert_state(fiber, FiberState.DISPOSED)
    await root.fiber.dispose()


@pytest.mark.asyncio
async def test_restart_missing_requirements_stays_pending() -> None:
    root = Context()
    fiber = await root.inject(["database"], lambda ctx, cfg: None)
    await fiber.restart()
    assert_state(fiber, FiberState.PENDING)
    await root.fiber.dispose()


@pytest.mark.asyncio
async def test_failed_consumer_can_retry_on_dependency_notification() -> None:
    root = Context()
    root.provide("database", object())
    calls: list[int] = []

    def consumer(ctx: Context, config: object) -> None:
        calls.append(1)
        if len(calls) == 1:
            raise ValueError("retry")

    fiber = root.inject(["database"], consumer)
    with pytest.raises(ValueError):
        await fiber
    root.refresh_services("database")
    await fiber
    assert_state(fiber, FiberState.ACTIVE)
    assert calls == [1, 1]
    await root.fiber.dispose()


@pytest.mark.asyncio
async def test_check_predicate_reacts_only_when_refreshed_and_get_is_unrestricted() -> None:
    root = Context()
    available = False
    root.provide("database", "value", check=lambda: available)
    fiber = await root.inject(["database"], lambda ctx, cfg: None)
    assert root.get("database") == "value"
    assert_state(fiber, FiberState.PENDING)
    available = True
    assert root.refresh_services("database") == (fiber,)
    await fiber
    assert_state(fiber, FiberState.ACTIVE)
    available = False
    root.refresh_services("database")
    await fiber
    assert_state(fiber, FiberState.PENDING)
    await root.fiber.dispose()


@pytest.mark.asyncio
async def test_throwing_check_blocks_dependency_and_logs(caplog: pytest.LogCaptureFixture) -> None:
    root = Context()

    def check() -> bool:
        raise ValueError("not ready")

    root.provide("database", object(), check=check)
    fiber = await root.inject(["database"], lambda ctx, cfg: None)
    assert_state(fiber, FiberState.PENDING)
    assert "availability check failed" in caplog.text
    await root.fiber.dispose()


@pytest.mark.parametrize("declaration", ["database", 1, [1], [""], {1: None}])
@pytest.mark.asyncio
async def test_invalid_dependency_declarations_are_atomic(declaration: object) -> None:
    root = Context()
    with pytest.raises(TypeError):
        root.inject(declaration, lambda ctx, cfg: None)
    assert root.registry.size == 0
    assert root.fiber.get_effects() == ()


@pytest.mark.asyncio
async def test_invalid_intercept_configs_are_rejected() -> None:
    root = Context()
    with pytest.raises(TypeError):
        root.inject({"database": 1}, lambda ctx, cfg: None)
    assert root.registry.size == 0


@pytest.mark.parametrize("name", ["", None, 1])
@pytest.mark.asyncio
async def test_invalid_service_names_do_not_mutate_storage(name: object) -> None:
    root = Context()
    with pytest.raises(TypeError):
        root.provide(name)  # type: ignore[arg-type]
    assert root.fiber.get_effects() == ()


@pytest.mark.asyncio
async def test_unloading_provider_rejects_new_services_and_cleanups_drain() -> None:
    root = Context()
    failures: list[str] = []

    def provider(ctx: Context, config: object) -> object:
        ctx.provide("database", object())

        def cleanup() -> None:
            with pytest.raises(CordisError):
                ctx.provide("illegal", object())
            failures.append("cleanup")

        return cleanup

    fiber = await root.plugin(provider)
    await fiber.dispose()
    assert failures == ["cleanup"]
    assert root.get("database", False) is root.get("illegal", False) is None
    assert not fiber.cleanup_errors


@pytest.mark.asyncio
async def test_declarations_copied_per_mount_even_for_shared_callback() -> None:
    root = Context()
    requirements = ["database"]

    def callback(ctx: Context, cfg: object) -> None:
        pass

    first = await root.inject(requirements, callback)
    requirements.append("search")
    second = await root.inject(requirements, callback)
    assert first.runtime is second.runtime
    assert first.inject == ("database",)
    assert second.inject == ("database", "search")
    root.provide("database", object())
    await first
    await second
    assert_state(first, FiberState.ACTIVE)
    assert_state(second, FiberState.PENDING)
    await root.fiber.dispose()


@pytest.mark.asyncio
async def test_provider_restart_unloads_consumer_and_republishes_fresh_service() -> None:
    root = Context()
    values: list[object] = []

    def provider(ctx: Context, config: object) -> None:
        value = object()
        values.append(value)
        ctx.provide("database", value)

    owner = await root.plugin(provider)
    seen: list[object] = []
    consumer = await root.inject(
        ["database"], lambda ctx, cfg: seen.append(ctx.require("database"))
    )
    await owner.restart()
    await consumer
    assert seen == values
    assert len(seen) == 2
    assert seen[0] is not seen[1]
    await root.fiber.dispose()


@pytest.mark.asyncio
async def test_service_cleanup_error_does_not_starve_other_consumers() -> None:
    root = Context()
    service = root.provide("database", object())
    calls: list[str] = []

    def failing(ctx: Context, cfg: object) -> object:
        def cleanup() -> None:
            calls.append("failed")
            raise ValueError("cleanup error")

        return cleanup

    first = await root.inject(["database"], failing)
    second = await root.inject(["database"], lambda ctx, cfg: lambda: calls.append("released"))
    await remove(service)
    assert sorted(calls) == ["failed", "released"]
    assert first.state is second.state is FiberState.PENDING
    assert len(first.cleanup_errors) == 1
    await root.fiber.dispose()


@pytest.mark.asyncio
async def test_cancelled_service_removal_waiter_does_not_cancel_cleanup() -> None:
    root = Context()
    service = root.provide("database", object())
    started, release = asyncio.Event(), asyncio.Event()

    def consumer(ctx: Context, cfg: object) -> object:
        async def cleanup() -> None:
            started.set()
            await release.wait()

        return cleanup

    fiber = await root.inject(["database"], consumer)
    result = service()
    assert result is not None
    waiter = asyncio.ensure_future(result)
    await started.wait()
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter
    release.set()
    await root.fiber.dispose()  # structural ownership still joins the service effect
    assert_state(fiber, FiberState.DISPOSED)
    assert root.get("database", False) is None


def test_service_mutations_reject_different_event_loops() -> None:
    root = Context()

    async def first_loop() -> None:
        root.provide("database", object())
        fiber = await root.inject(["database"], lambda ctx, cfg: None)
        await fiber.dispose()

    asyncio.run(first_loop())

    async def second_loop() -> None:
        with pytest.raises(RuntimeError, match="event loops"):
            root.provide("search", object())
        with pytest.raises(RuntimeError, match="event loops"):
            root.set("database", object())
        with pytest.raises(RuntimeError, match="event loops"):
            root.refresh_services("database")

    asyncio.run(second_loop())
    assert root.get("search") is None


@pytest.mark.asyncio
async def test_pending_owned_service_stays_hidden_and_disposal_drains_it() -> None:
    root = Context()
    fiber = await root.inject(["missing"], lambda ctx, cfg: None)
    fiber.ctx.provide("database", "value")
    assert root.get("database") is None
    assert root.get("database", False) == "value"
    await fiber.dispose()
    assert root.get("database", False) is None


@pytest.mark.asyncio
async def test_provider_loss_before_consumer_checkpoint_skips_setup() -> None:
    root = Context()
    service = root.provide("database", object())
    calls: list[int] = []
    result = service()  # removal Task precedes the consumer's startup checkpoint
    assert result is not None
    fiber = root.inject(["database"], lambda ctx, cfg: calls.append(1))
    await result
    await fiber
    assert calls == []
    assert_state(fiber, FiberState.PENDING)
    await root.fiber.dispose()


@pytest.mark.asyncio
async def test_unload_restore_during_slow_cleanup_keeps_old_snapshot_until_done() -> None:
    root = Context()
    service = root.provide("database", "old")
    started, release = asyncio.Event(), asyncio.Event()
    calls: list[tuple[str, object]] = []

    def consumer(ctx: Context, cfg: object) -> object:
        value = ctx.require("database")
        calls.append(("setup", value))

        async def cleanup() -> None:
            if value == "old":
                started.set()
                await release.wait()
            calls.append(("cleanup", ctx.require("database")))

        return cleanup

    fiber = await root.inject(["database"], consumer)
    result = service()
    assert result is not None
    await started.wait()
    root.provide("database", "new")
    assert fiber.ctx.require("database") == "old"
    release.set()
    await result
    await fiber
    assert calls == [("setup", "old"), ("cleanup", "old"), ("setup", "new")]
    await root.fiber.dispose()


@pytest.mark.asyncio
async def test_async_predicates_are_rejected_without_coroutine_leaks(
    caplog: pytest.LogCaptureFixture,
) -> None:
    root = Context()

    async def check() -> bool:
        return True

    with pytest.raises(TypeError, match="synchronous"):
        root.provide("database", object(), check=check)  # type: ignore[arg-type]

    class AsyncCheck:
        async def __call__(self) -> bool:
            return True

    root.provide("database", object(), check=AsyncCheck())  # type: ignore[arg-type]
    fiber = await root.inject(["database"], lambda ctx, cfg: None)
    assert_state(fiber, FiberState.PENDING)
    assert "must be synchronous" in caplog.text
    await root.fiber.dispose()


@pytest.mark.asyncio
async def test_reentrant_availability_check_can_dispose_consumer_safely() -> None:
    root = Context()
    fiber = await root.inject(["database"], lambda ctx, cfg: pytest.fail("disposed"))

    def check() -> bool:
        fiber.dispose()
        return True

    service = root.provide("database", object(), check=check)
    await fiber.dispose()
    assert_state(fiber, FiberState.DISPOSED)
    assert root.registry.size == 0
    await remove(service)
