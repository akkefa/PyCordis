"""Explicit loader adapters; ownership stays in the existing kernel."""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Mapping
from dataclasses import FrozenInstanceError
from pathlib import Path
from types import ModuleType
from typing import cast

import pytest

from deepseek_cordis import (
    Context,
    FiberState,
    PluginMeta,
    PluginSpec,
    Service,
    ValidationError,
    ValidationIssue,
)
from deepseek_cordis.loader import Loader, PluginEntry, resolve_plugin


def test_entry_copies_structure_but_preserves_config_identity() -> None:
    config = object()
    entry = PluginEntry.from_mapping({"id": "worker", "plugin": object(), "config": config})
    assert entry.config is config and entry.enabled is True
    with pytest.raises(FrozenInstanceError):
        entry.id = "changed"  # type: ignore[misc]


@pytest.mark.parametrize(
    "row",
    [
        {},
        {"id": "x"},
        {"id": "", "plugin": object()},
        {"id": 1, "plugin": object()},
        {"id": "x", "plugin": object(), "enabled": 1},
        {"id": "x", "plugin": object(), "group": True},
    ],
)
def test_invalid_config_rows_fail(row: Mapping[str, object]) -> None:
    with pytest.raises(TypeError):
        PluginEntry.from_mapping(row)


@pytest.mark.parametrize(
    "reference", ["", ".relative", "module:", "module:a..b", "module:a:b", "a/b"]
)
def test_invalid_import_references_fail(reference: str) -> None:
    with pytest.raises(ValueError):
        resolve_plugin(reference)


def test_resolver_preserves_supplied_object() -> None:
    plugin = object()
    assert resolve_plugin(plugin) is plugin


def test_imports_real_module_without_changing_path_or_reloading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "phase11_fixture.py"
    path.write_text("def apply(ctx, config):\n    pass\nname = 'fixture'\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    old_path = list(sys.path)
    first = resolve_plugin("phase11_fixture")
    assert isinstance(first, ModuleType)
    assert resolve_plugin("phase11_fixture:apply") is first.apply
    path.write_text("raise RuntimeError('must not reload')\n")
    assert resolve_plugin("phase11_fixture") is first
    assert sys.path == old_path
    monkeypatch.delitem(sys.modules, "phase11_fixture")


@pytest.mark.asyncio
async def test_config_imports_module_metadata_and_keeps_actual_fibers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = ModuleType("phase11_plugin")
    seen: list[object] = []
    module.apply = lambda ctx, config: seen.append(config)  # type: ignore[attr-defined]
    module.name = "display"  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, module.__name__, module)
    root = Context()
    config = object()
    batch = await Loader(root).load_config(
        [{"id": "entry", "plugin": module.__name__, "config": config}]
    )
    fiber = batch.fibers["entry"]
    assert fiber.raw_config is config
    assert fiber.name == "display"
    assert seen == [config]
    assert root.registry.get(module) is fiber.runtime
    assert fiber.parent.fiber is batch.owner
    with pytest.raises(TypeError):
        batch.fibers["extra"] = fiber  # type: ignore[index]
    await batch.dispose()
    assert fiber.state is batch.owner.state is FiberState.DISPOSED


@pytest.mark.asyncio
async def test_mount_and_setup_order_follow_entries_without_sorting_ids() -> None:
    order: list[object] = []

    def plugin(ctx: Context, config: object) -> object:
        order.append(config)
        return lambda: order.append(("cleanup", config))

    root = Context()
    batch = await Loader(root).load([PluginEntry("z", plugin, 1), PluginEntry("a", plugin, 2)])
    assert list(batch.fibers) == ["z", "a"]
    assert order == [1, 2]
    assert batch.fibers["z"].runtime is batch.fibers["a"].runtime
    await batch.dispose()
    assert order == [1, 2, ("cleanup", 2), ("cleanup", 1)]


@pytest.mark.asyncio
async def test_disabled_entries_skip_imports_and_are_omitted() -> None:
    root = Context()
    batch = await Loader(root).load([PluginEntry("off", "missing_phase11_plugin", enabled=False)])
    assert not batch.fibers
    await batch.dispose()
    assert root.registry.size == 0


@pytest.mark.asyncio
async def test_duplicate_ids_including_disabled_fail_before_setup() -> None:
    root = Context()
    entries = [
        PluginEntry("x", lambda ctx, config: pytest.fail("must not run")),
        PluginEntry("x", "missing", enabled=False),
    ]
    with pytest.raises(ValueError, match="duplicate"):
        await Loader(root).load(entries)
    assert root.registry.size == 0
    assert root.fiber.get_effects() == ()


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", ["missing_phase11_plugin", "sys:missing_phase11_attr", object()])
async def test_resolution_failure_preflights_all_entries_without_mounts(bad: object) -> None:
    root = Context()
    with pytest.raises((ModuleNotFoundError, AttributeError, TypeError)):
        await Loader(root).load(
            [
                PluginEntry("good", lambda ctx, config: pytest.fail("must not run")),
                PluginEntry("bad", bad),
            ]
        )
    assert root.registry.size == 0
    assert root.fiber.get_effects() == ()


@pytest.mark.asyncio
async def test_bad_validator_preflight_preserves_existing_work() -> None:
    root = Context()
    existing = await root.plugin(lambda ctx, config: None)
    effects = root.fiber.get_effects()
    with pytest.raises(TypeError, match="callable validate"):
        await Loader(root).load(
            [PluginEntry("bad", PluginSpec(lambda ctx, config: None, PluginMeta(config=object())))]
        )
    assert root.registry.size == 1
    assert root.fiber.get_effects() == effects
    await existing.dispose()


@pytest.mark.asyncio
async def test_consumer_before_provider_and_chain_settle_to_active() -> None:
    root = Context()
    seen: list[str] = []

    class Database(Service):
        name = "database"

        async def start(self) -> None:
            await asyncio.sleep(0)
            seen.append("database")

    def middle(ctx: Context, config: object) -> None:
        assert isinstance(ctx.require("database"), Database)
        ctx.provide("middle", object())
        seen.append("middle")

    def leaf(ctx: Context, config: object) -> None:
        assert ctx.require("middle") is not None
        seen.append("leaf")

    batch = await Loader(root).load(
        [
            PluginEntry("leaf", PluginSpec(leaf, PluginMeta(inject=["middle"]))),
            PluginEntry("middle", PluginSpec(middle, PluginMeta(inject=["database"]))),
            PluginEntry("database", Database),
        ]
    )
    assert seen == ["database", "middle", "leaf"]
    assert all(fiber.state is FiberState.ACTIVE for fiber in batch.fibers.values())
    await batch.dispose()
    assert root.get("database") is root.get("middle") is None


@pytest.mark.asyncio
async def test_missing_dependency_remains_pending_and_can_activate_later() -> None:
    root = Context()
    seen: list[object] = []
    batch = await Loader(root).load(
        [
            PluginEntry(
                "waiting",
                PluginSpec(
                    lambda ctx, config: seen.append(ctx.require("late")),
                    PluginMeta(inject=["late"]),
                ),
            )
        ]
    )
    fiber = batch.fibers["waiting"]
    assert fiber.state is FiberState.PENDING
    service = object()
    root.provide("late", service)
    await fiber
    assert seen == [service]
    await batch.dispose()
    await root.fiber.dispose()


@pytest.mark.asyncio
async def test_validation_error_rolls_back_batch_without_disposing_other_plugins() -> None:
    root = Context()
    cleaned: list[str] = []
    existing = await root.plugin(lambda ctx, config: lambda: cleaned.append("existing"))
    error = ValidationError([ValidationIssue("invalid")])

    class Schema:
        def validate(self, value: object) -> object:
            raise error

    with pytest.raises(ValidationError) as caught:
        await Loader(root).load(
            [
                PluginEntry("good", lambda ctx, config: lambda: cleaned.append("batch")),
                PluginEntry(
                    "bad",
                    PluginSpec(
                        lambda ctx, config: pytest.fail("must not run"), PluginMeta(config=Schema())
                    ),
                ),
            ]
        )
    assert caught.value is error
    assert cleaned == ["batch"]
    assert root.registry.size == 1
    assert existing.state is FiberState.ACTIVE
    await existing.dispose()


@pytest.mark.asyncio
async def test_async_setup_failure_drains_listeners_resources_and_nested_children() -> None:
    root = Context()
    cleaned: list[str] = []

    async def failure(ctx: Context, config: object) -> None:
        ctx.on("event", lambda: cleaned.append("leaked"))
        ctx.effect(lambda: lambda: cleaned.append("resource"))
        ctx.plugin(lambda inner, cfg: lambda: cleaned.append("child"))
        await asyncio.sleep(0)
        raise ValueError("setup failed")

    with pytest.raises(ValueError, match="setup failed"):
        await Loader(root).load([PluginEntry("bad", failure)])
    assert set(cleaned) == {"resource", "child"}
    root.emit("event")
    assert root.registry.size == 0
    assert root.fiber.get_effects() == ()


@pytest.mark.asyncio
async def test_cancellation_joins_inflight_setup_and_cleanup() -> None:
    root = Context()
    entered = asyncio.Event()
    released = asyncio.Event()
    cleaned: list[bool] = []

    async def slow(ctx: Context, config: object) -> object:
        entered.set()
        await released.wait()
        return lambda: cleaned.append(True)

    loading = asyncio.create_task(Loader(root).load([PluginEntry("slow", slow)]))
    await entered.wait()
    loading.cancel()
    await asyncio.sleep(0)
    assert not loading.done()
    released.set()
    with pytest.raises(asyncio.CancelledError):
        await loading
    assert cleaned == [True]
    assert root.registry.size == 0
    assert root.fiber.get_effects() == ()


@pytest.mark.asyncio
async def test_scoped_parent_ownership_and_parent_disposal() -> None:
    root = Context()
    private = root.isolate("database")

    class Database(Service):
        name = "database"

    loader = Loader(private)
    batch = await loader.load([PluginEntry("db", Database)])
    assert loader.ctx is private
    assert root.get("database") is None
    assert isinstance(private.get("database"), Database)
    await root.fiber.dispose()
    assert batch.owner.state is FiberState.DISPOSED
    assert all(fiber.state is FiberState.DISPOSED for fiber in batch.fibers.values())
    await batch.dispose()


@pytest.mark.asyncio
async def test_repeated_batches_share_callback_runtime_but_dispose_independently() -> None:
    root = Context()
    loader = Loader(root)

    def plugin(ctx: Context, config: object) -> None:
        pass

    first = await loader.load([PluginEntry("same", plugin)])
    second = await loader.load([PluginEntry("same", plugin)])
    a, b = first.fibers["same"], second.fibers["same"]
    assert a.runtime is b.runtime
    await first.dispose()
    await first.dispose()
    assert a.state is FiberState.DISPOSED and b.state is FiberState.ACTIVE
    await second.dispose()
    assert root.registry.size == 0


@pytest.mark.asyncio
async def test_invalid_rows_and_iterables_fail_before_imports_or_mounting() -> None:
    root = Context()
    loader = Loader(root)
    with pytest.raises(TypeError):
        await loader.load(cast(list[PluginEntry], [object()]))
    with pytest.raises(TypeError):
        await loader.load_config([{"id": "first", "plugin": "missing_phase11_plugin"}, {}])
    assert root.registry.size == 0
    assert root.fiber.get_effects() == ()


@pytest.mark.asyncio
async def test_late_consumer_failure_is_reported_and_batch_rolled_back() -> None:
    root = Context()
    error = ValueError("late consumer failure")

    class Provider(Service):
        name = "dependency"

    def consumer(ctx: Context, config: object) -> None:
        raise error

    with pytest.raises(ValueError) as caught:
        await Loader(root).load(
            [
                PluginEntry("consumer", PluginSpec(consumer, PluginMeta(inject=["dependency"]))),
                PluginEntry("provider", Provider),
            ]
        )
    assert caught.value is error
    assert root.registry.size == 0
    assert root.get("dependency") is None
    assert root.fiber.get_effects() == ()


@pytest.mark.asyncio
async def test_cyclic_dependencies_remain_pending_without_hanging() -> None:
    root = Context()
    batch = await Loader(root).load(
        [
            PluginEntry(
                "a", PluginSpec(lambda ctx, config: ctx.provide("a"), PluginMeta(inject=["b"]))
            ),
            PluginEntry(
                "b", PluginSpec(lambda ctx, config: ctx.provide("b"), PluginMeta(inject=["a"]))
            ),
        ]
    )
    assert all(fiber.state is FiberState.PENDING for fiber in batch.fibers.values())
    await batch.dispose()
    assert root.registry.size == 0


@pytest.mark.asyncio
async def test_async_setup_failure_leaves_no_loader_waiter_tasks() -> None:
    root = Context()
    baseline = asyncio.all_tasks()

    async def failure(ctx: Context, config: object) -> None:
        await asyncio.sleep(0)
        raise ValueError("failure")

    async def peer(ctx: Context, config: object) -> None:
        await asyncio.sleep(0)
        await asyncio.sleep(0)

    with pytest.raises(ValueError):
        await Loader(root).load([PluginEntry("bad", failure), PluginEntry("peer", peer)])
    assert asyncio.all_tasks() <= baseline
    assert root.registry.size == 0
