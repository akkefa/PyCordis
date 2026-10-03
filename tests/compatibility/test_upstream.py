"""Behavioral ports pinned by docs/compatibility-cases.json source records."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import AsyncIterator, Callable, Generator
from types import SimpleNamespace
from typing import cast

import pytest

from pycordis import Context, CordisError, Effect, FiberState, Service

pytestmark = [pytest.mark.asyncio, pytest.mark.compatibility]


async def remove(effect: Effect) -> None:
    result = effect()
    if inspect.isawaitable(result):
        await result


@pytest.mark.parametrize("form", ["function", "object"])
async def test_plugin_forms_pass_original_config_once(form: str) -> None:
    root = Context()
    config = {"foo": "bar"}
    calls: list[tuple[Context, object]] = []

    def apply(ctx: Context, value: object) -> None:
        calls.append((ctx, value))

    plugin = apply if form == "function" else SimpleNamespace(apply=apply)
    fiber = await root.plugin(plugin, config)
    assert len(calls) == 1
    assert calls[0][0] is fiber.ctx
    assert calls[0][1] is config
    await root.fiber.dispose()


async def test_nested_plugins_remove_only_owned_listeners() -> None:
    root = Context()
    calls: list[bool] = []
    root.on("event", lambda: calls.append(True))

    def leaf(ctx: Context, config: object) -> None:
        ctx.on("event", lambda: calls.append(True))

    async def middle(ctx: Context, config: object) -> None:
        ctx.on("event", lambda: calls.append(True))
        await ctx.plugin(leaf)

    async def outer(ctx: Context, config: object) -> None:
        ctx.on("event", lambda: calls.append(True))
        await ctx.plugin(middle)

    fiber = await root.plugin(outer)
    assert root.registry.size == 3
    root.emit("event")
    assert len(calls) == 4
    await fiber.dispose()
    assert root.registry.size == 0
    calls.clear()
    root.emit("event")
    assert calls == [True]
    await fiber.dispose()
    calls.clear()
    root.emit("event")
    assert calls == [True]
    await root.fiber.dispose()


async def test_remount_restores_owned_listener_effect_snapshot() -> None:
    root = Context()
    calls: list[str] = []
    before = root.fiber.get_effects()

    def child(ctx: Context, config: object) -> None:
        ctx.on("event", lambda: calls.append("child"))

    async def parent(ctx: Context, config: object) -> None:
        ctx.on("event", lambda: calls.append("parent"))
        await ctx.plugin(child)

    first = await root.plugin(parent)
    first_children = first.get_effects()
    assert root.registry.size == 2
    root.registry.delete(parent)
    await first.dispose()
    assert root.fiber.get_effects() == before
    assert root.registry.size == 0
    root.emit("event")
    assert not calls
    second = await root.plugin(parent)
    assert second.get_effects() == first_children
    root.emit("event")
    assert calls == ["parent", "child"]
    await root.fiber.dispose()


async def test_root_disposal_preserves_root_identity_and_drains_children_once() -> None:
    root = Context()
    calls: list[bool] = []
    fiber = await root.plugin(lambda ctx, config: lambda: calls.append(True))
    assert root.fiber.uid == 0 and fiber.uid == 1
    assert root.registry.size == 1
    assert fiber.parent is root
    await root.fiber.dispose()
    assert root.fiber.uid == 0 and fiber.uid is None
    assert calls == [True]
    assert root.fiber.get_effects() == ()
    await root.fiber.dispose()
    assert calls == [True]
    assert root.fiber.state is FiberState.ACTIVE


async def test_failed_mount_removes_its_listener_but_successful_peer_keeps_listener(
    caplog: pytest.LogCaptureFixture,
) -> None:
    root = Context()
    calls: list[object] = []

    def plugin(ctx: Context, config: object) -> None:
        ctx.on("event", lambda: calls.append(config))
        if config is None:
            raise ValueError("plugin error")

    bad = root.plugin(plugin)
    good = root.plugin(plugin, True)
    with pytest.raises(ValueError, match="plugin error"):
        await bad
    await good
    assert bad.state is FiberState.FAILED and good.state is FiberState.ACTIVE
    assert bad.runtime is good.runtime
    root.emit("event")
    assert calls == [True]
    assert len([record for record in caplog.records if record.levelname == "ERROR"]) == 1
    await root.fiber.dispose()


async def test_nested_effect_listener_tree_and_reverse_cleanup() -> None:
    root = Context()
    sequence: list[int] = []
    events: list[str] = []

    def inner() -> Generator[object, None, None]:
        yield root.on("event", lambda: events.append("inner"))
        yield lambda: sequence.append(3)

    def outer() -> Generator[object, None, None]:
        yield lambda: sequence.append(1)
        yield root.on("event", lambda: events.append("outer"))
        yield lambda: sequence.append(2)
        yield root.effect(inner)

    effect = root.effect(outer)
    root.on("event", lambda: events.append("root"))
    snapshot = root.fiber.get_effects()
    assert len(snapshot) == 2 and len(snapshot[0].children) == 2
    assert len(snapshot[0].children[1].children) == 1
    root.emit("event")
    assert events == ["outer", "inner", "root"]
    await remove(effect)
    assert sequence == [3, 2, 1]
    events.clear()
    root.emit("event")
    assert events == ["root"]
    await remove(effect)
    assert sequence == [3, 2, 1]
    await root.fiber.dispose()


async def test_async_effect_disposal_before_setup_finishes_runs_returned_cleanup() -> None:
    root = Context()
    entered = asyncio.Event()
    release = asyncio.Event()
    sequence: list[int] = []

    async def setup() -> object:
        entered.set()
        await release.wait()
        sequence.append(1)
        return lambda: sequence.append(2)

    effect = root.effect(setup)
    disposal = effect()
    assert inspect.isawaitable(disposal)
    await entered.wait()
    assert sequence == []
    release.set()
    await disposal
    assert sequence == [1, 2]
    assert root.fiber.get_effects() == ()


async def test_service_initialization_event_gates_dependent_activation() -> None:
    root = Context()
    listening = asyncio.Event()
    calls: list[bool] = []

    class Provider(Service):
        name = "foo"

        async def start(self) -> None:
            ready = asyncio.Event()
            self.ctx.on("ready", ready.set)
            listening.set()
            await ready.wait()

    consumer = await root.inject(["foo"], lambda ctx, config: calls.append(True))
    provider = root.plugin(Provider)
    await listening.wait()
    assert consumer.state is FiberState.PENDING
    assert calls == []
    root.emit("ready")
    await provider
    await consumer
    assert calls == [True]
    await root.fiber.dispose()


async def test_isolated_provider_updates_only_matching_consumers() -> None:
    root = Context()
    first, second = root.isolate("foo"), root.isolate("foo")
    started: list[int] = []
    stopped: list[int] = []

    def plugin(ctx: Context, config: object) -> object:
        value = ctx.require("foo")
        assert isinstance(value, int)
        started.append(value)
        return lambda: stopped.append(value)

    fibers = [await view.inject(["foo"], plugin) for view in (root, first, second)]
    global_binding = root.provide("foo", 100)
    await fibers[0]
    assert started == [100]
    assert first.get("foo") is second.get("foo") is None
    first.provide("foo", 200)
    await fibers[1]
    assert started == [100, 200]
    await remove(global_binding)
    assert stopped == [100]
    second.provide("foo", 300)
    await fibers[2]
    assert started == [100, 200, 300]
    assert root.get("foo") is None
    await root.fiber.dispose()


async def test_waterfall_fixed_arguments_and_veto_match_source_sequence() -> None:
    root = Context()
    counts = [0, 0, 0, 0]

    def layer(index: int) -> Callable[..., object]:
        def callback(value: int, next_: Callable[[], object]) -> object:
            counts[index] += 1
            if index == 2:
                return value
            result = next_()
            assert isinstance(result, int)
            return value + result

        return callback

    root.on("waterfall", layer(0))
    root.on("waterfall", layer(1))
    assert root.waterfall("waterfall", 1, next_=lambda: 2) == 4
    assert counts == [1, 1, 0, 0]
    counts[:] = [0, 0, 0, 0]
    root.on("waterfall", layer(2))
    root.on("waterfall", layer(3))
    assert root.waterfall("waterfall", 1, next_=lambda: 2) == 3
    assert counts == [1, 1, 1, 0]
    await root.fiber.dispose()


async def test_access_check_rejects_undeclared_reads_and_nonowner_writes() -> None:
    root = Context()
    root.provide("foo", 1)

    def plugin(ctx: Context, config: object) -> None:
        with pytest.raises(CordisError) as read:
            ctx.require("undeclared")
        assert read.value.code == "UNDECLARED_SERVICE"
        with pytest.raises(CordisError) as write:
            ctx.set("foo", 0)
        assert write.value.code == "SERVICE_OWNER"
        ctx.provide("bar", 1)
        with pytest.raises(CordisError):
            ctx.provide("bar", 2)
        ctx.set("bar", 3)
        assert ctx.require("bar") == 3

    await root.plugin(plugin)
    await root.fiber.dispose()


async def test_loading_provider_removal_joins_consumer_cleanup() -> None:
    root = Context()
    entered = asyncio.Event()
    release = asyncio.Event()
    cleanup_entered = asyncio.Event()
    cleanup_release = asyncio.Event()
    calls: list[str] = []

    class Provider(Service):
        name = "foo"

    async def plugin(ctx: Context, config: object) -> object:
        entered.set()
        await release.wait()
        calls.append("setup")

        async def cleanup() -> None:
            assert isinstance(ctx.require("foo"), Provider)
            cleanup_entered.set()
            await cleanup_release.wait()
            calls.append("cleanup")

        return cleanup

    provider = await root.plugin(Provider)
    consumer = root.inject(["foo"], plugin)
    await entered.wait()
    removing = provider.dispose()
    release.set()
    await cleanup_entered.wait()
    assert consumer.state is FiberState.UNLOADING
    cleanup_release.set()
    await removing
    await consumer
    assert cast(FiberState, consumer.state) is FiberState.PENDING
    assert calls == ["setup", "cleanup"]
    await root.fiber.dispose()


async def test_context_subclass_uses_native_type_identity() -> None:
    class SubContext(Context):
        pass

    root = SubContext()
    assert isinstance(root, Context)
    assert isinstance(root.extend(), SubContext)


async def test_disposed_consumer_cannot_read_required_snapshot() -> None:
    root = Context()
    root.provide("foo", {"bar": 1})
    fiber = await root.inject(["foo"], lambda ctx, config: None)
    assert fiber.ctx.require("foo") is root.get("foo")
    await fiber.dispose()
    with pytest.raises(CordisError) as caught:
        fiber.ctx.require("foo")
    assert caught.value.code == "INACTIVE_SERVICE"
    await root.fiber.dispose()


@pytest.mark.parametrize("mode", ["return", "yield", "async-return", "async-yield"])
async def test_effect_setup_error_rolls_back_only_collected_resources(mode: str) -> None:
    root = Context()
    cleaned: list[bool] = []

    def fail_return() -> object:
        raise ValueError("test")

    def fail_yield() -> Generator[object, None, None]:
        yield lambda: cleaned.append(True)
        raise ValueError("test")

    async def fail_async_return() -> object:
        raise ValueError("test")

    async def fail_async_yield() -> AsyncIterator[object]:
        yield lambda: cleaned.append(True)
        raise ValueError("test")

    setup = {
        "return": fail_return,
        "yield": fail_yield,
        "async-return": fail_async_return,
        "async-yield": fail_async_yield,
    }[mode]
    with pytest.raises(ValueError, match="test"):
        effect = root.effect(setup)
        await effect
    assert cleaned == ([True] if "yield" in mode else [])
    assert root.fiber.get_effects() == ()


async def test_disposal_error_is_logged_once_and_does_not_reject(
    caplog: pytest.LogCaptureFixture,
) -> None:
    root = Context()
    error = ValueError("test")
    calls: list[bool] = []

    def cleanup() -> None:
        calls.append(True)
        raise error

    fiber = await root.plugin(lambda ctx, config: cleanup)
    await fiber.dispose()
    assert calls == [True]
    assert fiber.cleanup_errors == (error,)
    assert len([record for record in caplog.records if record.levelname == "ERROR"]) == 1
    await fiber.dispose()
    assert calls == [True]
    assert root.registry.size == 0
