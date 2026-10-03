"""Adaptations of pinned plugin.spec.ts/registry.ts; no service/event claims."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest

from pycordis import Context, CordisError, Fiber, FiberState


def test_registry_is_root_local_and_shared_by_extensions() -> None:
    first, second = Context(), Context()
    assert first.registry is first.extend().registry
    assert first.registry is not second.registry
    assert first.registry.size == len(first.registry) == 0
    assert first.registry.keys() == ()
    assert first.registry.values() == ()
    assert first.registry.entries() == ()
    assert tuple(first.registry) == ()


@pytest.mark.asyncio
async def test_function_mount_passes_config_by_identity_and_returns_actual_fiber() -> None:
    ctx = Context()
    seen: list[tuple[Context, object]] = []
    config: dict[str, object] = {}

    def plugin(inner: Context, options: object) -> None:
        seen.append((inner, options))

    fiber = ctx.plugin(plugin, config)
    assert isinstance(fiber, Fiber)
    assert ctx.registry.has(plugin)
    assert await fiber is fiber
    assert seen == [(fiber.ctx, config)]
    assert seen[0][1] is config
    assert fiber.ctx.registry is ctx.registry
    assert fiber.runtime is ctx.registry.get(plugin)
    await fiber.dispose()
    assert ctx.registry.size == 0


@pytest.mark.asyncio
async def test_multiple_mounts_share_record_but_keep_distinct_fibers_and_config() -> None:
    ctx = Context()
    configs: list[object] = []

    async def plugin(inner: Context, config: object) -> None:
        await asyncio.sleep(0)
        configs.append(config)

    first, second = ctx.plugin(plugin, 1), ctx.plugin(plugin, 2)
    assert first.uid != second.uid
    assert first.runtime is second.runtime
    runtime = ctx.registry.get(plugin)
    assert runtime is not None
    assert list(runtime.fibers) == [first, second]
    await asyncio.gather(first.wait(), second.wait())
    assert configs == [1, 2]
    await first.dispose()
    assert list(runtime.fibers) == [second]
    assert ctx.registry.has(plugin)
    await second.dispose()
    assert list(runtime.fibers) == []
    assert not ctx.registry.has(plugin)


@pytest.mark.asyncio
async def test_bound_apply_method_identity_is_stable_across_reads() -> None:
    ctx = Context()

    class Plugin:
        def apply(self, inner: Context, config: object) -> None:
            pass

    plugin = Plugin()
    first, second = ctx.plugin(plugin), ctx.plugin(plugin)
    assert first.runtime is second.runtime
    assert ctx.registry.get(plugin.apply) is first.runtime
    assert ctx.registry.resolve(plugin) is not ctx.registry.resolve(plugin)
    await ctx.fiber.dispose()
    assert ctx.registry.size == 0


@pytest.mark.asyncio
async def test_callable_instances_with_equal_values_and_no_hash_keep_distinct_identity() -> None:
    @dataclass
    class Plugin:
        value: int

        def __call__(self, ctx: Context, config: object) -> None:
            pass

    ctx = Context()
    first, second = Plugin(1), Plugin(1)
    assert first == second
    left, right = ctx.plugin(first), ctx.plugin(second)
    assert left.runtime is not right.runtime
    assert ctx.registry.size == 2
    await ctx.fiber.dispose()


@pytest.mark.asyncio
async def test_async_callable_instance_runs_normally() -> None:
    calls: list[str] = []

    class Plugin:
        async def __call__(self, ctx: Context, config: object) -> object:
            await asyncio.sleep(0)
            calls.append("setup")
            return lambda: calls.append("cleanup")

    ctx = Context()
    fiber = await ctx.plugin(Plugin())
    await fiber.dispose()
    assert calls == ["setup", "cleanup"]


@pytest.mark.asyncio
async def test_objects_sharing_plain_apply_function_share_callback_record() -> None:
    def apply(ctx: Context, config: object) -> None:
        pass

    class Plugin:
        def __init__(self) -> None:
            self.apply = apply

    ctx = Context()
    first, second = Plugin(), Plugin()
    left, right = ctx.plugin(first), ctx.plugin(second)
    assert left.runtime is right.runtime
    await ctx.fiber.dispose()


@pytest.mark.asyncio
async def test_class_constructor_and_start_own_resources() -> None:
    calls: list[str] = []
    configs: list[object] = []

    class Plugin:
        def __init__(self, ctx: Context, config: object) -> None:
            configs.append(config)
            ctx.effect(lambda: lambda: calls.append("constructor cleanup"))

        async def start(self) -> object:
            calls.append("start")
            return lambda: calls.append("start cleanup")

    ctx = Context()
    fiber = await ctx.plugin(Plugin, "config")
    assert configs == ["config"]
    assert fiber.name == "Plugin"
    await fiber.dispose()
    assert calls[0] == "start"
    assert sorted(calls[1:]) == ["constructor cleanup", "start cleanup"]


@pytest.mark.asyncio
async def test_class_without_start_does_not_return_instance_as_effect() -> None:
    calls: list[str] = []

    class Plugin:
        def __init__(self, ctx: Context, config: object) -> None:
            calls.append("constructor")

    ctx = Context()
    fiber = await ctx.plugin(Plugin)
    assert fiber.state is FiberState.ACTIVE
    assert calls == ["constructor"]
    await ctx.fiber.dispose()


@pytest.mark.parametrize("plugin", [None, {}, 1, "invalid"])
def test_invalid_plugin_is_rejected_without_mutation(plugin: object) -> None:
    ctx = Context()
    with pytest.raises(TypeError, match="invalid plugin"):
        ctx.plugin(plugin)
    assert ctx.registry.size == 0


def test_raising_apply_getter_is_invalid_for_inspection_and_mount() -> None:
    class Plugin:
        @property
        def apply(self) -> object:
            raise ValueError("getter")

    ctx = Context()
    plugin = Plugin()
    assert ctx.registry.resolve(plugin) is None
    assert ctx.registry.get(plugin) is None
    assert not ctx.registry.has(plugin)
    with pytest.raises(TypeError):
        ctx.plugin(plugin)
    assert ctx.registry.delete(plugin) is None


def test_mount_without_loop_does_not_create_runtime() -> None:
    ctx = Context()
    with pytest.raises(RuntimeError, match="running event loop"):
        ctx.plugin(lambda inner, config: None)
    assert ctx.registry.size == 0


@pytest.mark.asyncio
async def test_config_metadata_is_rejected_and_injection_remains_pending() -> None:
    ctx = Context()

    class Injected:
        inject = ["database"]

        def __call__(self, inner: Context, config: object) -> None:
            raise AssertionError("must not run")

    class Validated:
        Config = object()

        def __call__(self, inner: Context, config: object) -> None:
            raise AssertionError("must not run")

    fiber = await ctx.plugin(Injected())
    assert fiber.state is FiberState.PENDING
    with pytest.raises(NotImplementedError):
        ctx.plugin(Validated())
    await fiber.dispose()
    assert ctx.registry.size == 0


@pytest.mark.asyncio
async def test_context_plugin_mounts_from_calling_view_not_root() -> None:
    root = Context()
    view = root.extend({"scope": "worker"})
    fiber = await view.plugin(lambda inner, config: None)
    assert fiber.parent is view
    assert fiber.ctx.metadata["scope"] == "worker"
    assert fiber.ctx.registry is root.registry
    await root.fiber.dispose()


@pytest.mark.asyncio
async def test_nested_plugins_drained_with_parent() -> None:
    root = Context()
    calls: list[str] = []
    children: list[Fiber] = []

    def child(ctx: Context, config: object) -> object:
        return lambda: calls.append("child")

    async def parent(ctx: Context, config: object) -> object:
        children.append(await ctx.plugin(child))
        return lambda: calls.append("parent")

    fiber = await root.plugin(parent)
    assert root.registry.size == 2
    await fiber.dispose()
    assert children[0].uid is None
    assert root.registry.size == 0
    assert sorted(calls) == ["child", "parent"]
    await fiber.dispose()
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_restart_preserves_runtime_and_registration() -> None:
    root = Context()
    calls: list[str] = []

    def plugin(ctx: Context, config: object) -> object:
        calls.append("setup")
        return lambda: calls.append("cleanup")

    fiber = await root.plugin(plugin)
    runtime = fiber.runtime
    await fiber.restart()
    assert fiber.runtime is runtime is root.registry.get(plugin)
    assert calls == ["setup", "cleanup", "setup"]
    await fiber.dispose()


@pytest.mark.asyncio
async def test_failed_setup_retains_record_until_disposal_and_cleans_resources() -> None:
    calls: list[str] = []

    def plugin(ctx: Context, config: object) -> None:
        ctx.effect(lambda: lambda: calls.append("rollback"))
        raise ValueError("failure")

    root = Context()
    fiber = root.plugin(plugin)
    with pytest.raises(ValueError):
        await fiber
    assert root.registry.has(plugin)
    assert calls == ["rollback"]
    await fiber.dispose()
    assert not root.registry.has(plugin)


@pytest.mark.asyncio
async def test_delete_requests_disposal_and_remount_survives_old_cleanup() -> None:
    root = Context()
    started, release = asyncio.Event(), asyncio.Event()

    async def cleanup() -> None:
        started.set()
        await release.wait()

    def plugin(ctx: Context, config: object) -> object:
        return cleanup

    old = await root.plugin(plugin)
    old_runtime = old.runtime
    assert root.registry.delete(plugin) is old_runtime
    assert not root.registry.has(plugin)
    assert old.uid is None
    await started.wait()
    new = await root.plugin(plugin)
    assert new.runtime is not old_runtime
    release.set()
    await old.dispose()
    assert root.registry.get(plugin) is new.runtime
    await new.dispose()


@pytest.mark.asyncio
async def test_delete_all_mounts_and_missing_delete() -> None:
    root = Context()

    def plugin(ctx: Context, config: object) -> None:
        pass

    first, second = await root.plugin(plugin), await root.plugin(plugin)
    runtime = root.registry.get(plugin)
    assert runtime is not None
    fibers = runtime.fibers
    assert root.registry.delete(plugin) is runtime
    assert root.registry.delete(plugin) is None
    await asyncio.gather(*(fiber.dispose() for fiber in fibers))
    assert first.state is second.state is FiberState.DISPOSED
    assert list(runtime.fibers) == []


@pytest.mark.asyncio
async def test_inspection_returns_stable_immutable_snapshots() -> None:
    root = Context()

    def plugin(ctx: Context, config: object) -> None:
        pass

    fiber = await root.plugin(plugin)
    runtime = fiber.runtime
    assert runtime is not None
    snapshot = root.registry.values()
    assert root.registry.keys() == (plugin,)
    assert root.registry.entries() == ((plugin, runtime),)
    await fiber.dispose()
    assert snapshot == (runtime,)
    assert root.registry.values() == ()


@pytest.mark.asyncio
async def test_mount_from_disposed_or_unloading_owner_is_rejected() -> None:
    root = Context()
    errors: list[str] = []

    def cleanup() -> None:
        try:
            fiber.ctx.plugin(lambda inner, config: None)
        except CordisError as error:
            errors.append(error.code)

    fiber = await root.plugin(lambda inner, config: cleanup)
    await fiber.restart()
    assert errors == ["INACTIVE_EFFECT"]
    await fiber.dispose()
    with pytest.raises(CordisError):
        fiber.ctx.plugin(lambda inner, config: None)
    assert root.registry.size == 0


@pytest.mark.asyncio
async def test_failed_constructor_mount_rolls_back_new_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def broken(*args: object, **kwargs: object) -> Fiber:
        raise RuntimeError("construction failed")

    monkeypatch.setattr("pycordis.registry.Fiber", broken)
    root = Context()
    with pytest.raises(RuntimeError, match="construction failed"):
        root.plugin(lambda inner, config: None)
    assert root.registry.size == 0


@pytest.mark.asyncio
async def test_registry_mount_rejects_another_root_context() -> None:
    first, second = Context(), Context()
    with pytest.raises(ValueError, match="another root"):
        first.registry.mount(second, lambda inner, config: None)
    assert first.registry.size == second.registry.size == 0
