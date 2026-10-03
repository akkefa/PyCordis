"""Pinned context/isolate/service adaptations and task-local scope regressions."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Mapping
from typing import cast

import pytest

from pycordis import Context, CordisError, FiberState, ScopeLabel, Service, current_context


class Database(Service):
    name = "database"


async def remove(registration: object) -> None:
    assert callable(registration)
    result = registration()
    if result is not None:
        await result


def test_isolation_preserves_ownership_and_other_services() -> None:
    root = Context()
    root.provide("database", "global")
    root.provide("logger", "shared")
    child = root.isolate("database")
    assert child.parent is root
    assert child.root is root
    assert child.owner is root.owner
    assert child.fiber is root.fiber
    assert child.get("database") is None
    assert child.get("logger") == "shared"
    assert child.extend().service_scope("database") is child.service_scope("database")
    assert child.service_scope("database") is not root.service_scope("database")
    assert root.get("database") == "global"


@pytest.mark.asyncio
async def test_isolated_providers_same_owner_are_independent_in_require_and_set() -> None:
    root = Context()
    left, right = root.isolate("database"), root.isolate("database")
    root.provide("database", "global")
    left.provide("database", "left")
    right.provide("database", "right")
    assert root.require("database") == "global"
    assert left.require("database") == "left"
    assert right.require("database") == "right"
    left.set("database", "changed")
    assert left.get("database") == "changed"
    assert root.get("database") == "global"
    assert right.get("database") == "right"
    await root.fiber.dispose()
    assert (
        root.get("database", False)
        is left.get("database", False)
        is right.get("database", False)
        is None
    )


@pytest.mark.asyncio
async def test_default_and_two_isolated_consumers_refresh_only_matching_slot() -> None:
    root = Context()
    left, right = root.isolate("database"), root.isolate("database")
    calls: list[tuple[str, object]] = []

    def consumer(ctx: Context, cfg: object) -> object:
        value = ctx.require("database")
        calls.append(("setup", value))
        return lambda: calls.append(("cleanup", ctx.require("database")))

    fibers = [await ctx.inject(["database"], consumer) for ctx in (root, left, right)]
    global_service = root.provide("database", "global")
    await fibers[0]
    assert calls == [("setup", "global")]
    left.provide("database", "left")
    await fibers[1]
    assert calls[-1] == ("setup", "left")
    assert fibers[2].state is FiberState.PENDING
    await remove(global_service)
    assert fibers[0].state is FiberState.PENDING
    assert fibers[1].state is FiberState.ACTIVE
    assert calls[-1] == ("cleanup", "global")
    right.provide("database", "right")
    await fibers[2]
    assert calls[-1] == ("setup", "right")
    await root.fiber.dispose()
    assert root.registry.size == 0


@pytest.mark.asyncio
async def test_shared_label_joins_views_and_removal_wakes_both() -> None:
    root = Context()
    label = ScopeLabel()
    left, right = root.isolate("database", label), root.isolate("database", label)
    first = await left.inject(["database"], lambda ctx, cfg: None)
    second = await right.inject(["database"], lambda ctx, cfg: None)
    service = left.provide("database", object())
    await asyncio.gather(first.wait(), second.wait())
    assert first.state is second.state is FiberState.ACTIVE
    assert right.get("database") is left.get("database")
    with pytest.raises(CordisError) as error:
        right.provide("database", object())
    assert error.value.code == "DUPLICATE_SERVICE"
    await remove(service)
    assert [first.state, second.state] == [FiberState.PENDING, FiberState.PENDING]
    await root.fiber.dispose()


@pytest.mark.asyncio
async def test_same_label_does_not_alias_different_service_names_or_roots() -> None:
    root, other = Context(), Context()
    label = ScopeLabel()
    scope = root.isolate("database", label).isolate("logger", label)
    foreign = other.isolate("database", label)
    scope.provide("database", "db")
    scope.provide("logger", "log")
    foreign.provide("database", "foreign")
    assert scope.get("database") == "db"
    assert scope.get("logger") == "log"
    assert foreign.get("database") == "foreign"
    await root.fiber.dispose()
    await other.fiber.dispose()


@pytest.mark.asyncio
async def test_isolated_service_classes_and_scope_event_filter() -> None:
    root = Context()
    isolated = root.isolate("database")
    await root.plugin(Database)
    await isolated.plugin(Database)
    service = isolated.get("database")
    assert isinstance(service, Database)
    calls: list[str] = []
    root.on("event", lambda: calls.append("global scope"))
    isolated.on("event", lambda: calls.append("isolated scope"))
    root.on("event", lambda: calls.append("global listener"), global_=True)
    isolated.emit("event", filter_=service.matches_scope)
    assert calls == ["isolated scope", "global listener"]
    calls.clear()
    isolated.emit("event")
    assert calls == ["global scope", "isolated scope", "global listener"]
    assert (
        service.matches_scope(Context().isolate("database", isolated.service_scope("database")))
        is False
    )
    await root.fiber.dispose()


@pytest.mark.asyncio
async def test_snapshot_access_cannot_cross_changed_isolation_boundary() -> None:
    root = Context()
    root.provide("database", "global")
    parent = await root.inject(["database"], lambda ctx, cfg: None)
    view = parent.ctx.isolate("database")
    assert view.get("database") is None
    with pytest.raises(CordisError):
        view.require("database")
    child = await view.plugin(lambda ctx, cfg: None)
    with pytest.raises(CordisError) as error:
        child.ctx.require("database")
    assert error.value.code == "UNDECLARED_SERVICE"
    # A separate requirement in the isolated label remains pending.
    consumer = await view.inject(["database"], lambda ctx, cfg: None)
    assert consumer.state is FiberState.PENDING
    view.provide("database", "private")
    await consumer
    assert consumer.ctx.require("database") == "private"
    await root.fiber.dispose()


@pytest.mark.asyncio
async def test_isolated_removal_restore_during_cleanup_keeps_correct_snapshot() -> None:
    root = Context()
    left, right = root.isolate("database"), root.isolate("database")
    left_service = left.provide("database", "old")
    right.provide("database", "right")
    started, release = asyncio.Event(), asyncio.Event()
    calls: list[object] = []

    def consumer(ctx: Context, cfg: object) -> object:
        value = ctx.require("database")

        async def cleanup() -> None:
            if value == "old":
                started.set()
                await release.wait()
            calls.append(ctx.require("database"))

        return cleanup

    left_consumer = await left.inject(["database"], consumer)
    right_consumer = await right.inject(["database"], consumer)
    result = left_service()
    assert result is not None
    await started.wait()
    left.provide("database", "new")
    assert right_consumer.state is FiberState.ACTIVE
    assert left_consumer.ctx.require("database") == "old"
    release.set()
    await result
    await left_consumer
    assert calls == ["old"]
    assert left_consumer.ctx.require("database") == "new"
    await root.fiber.dispose()


@pytest.mark.asyncio
async def test_scoped_refresh_predicate_does_not_touch_sibling_label() -> None:
    root = Context()
    left, right = root.isolate("database"), root.isolate("database")
    ready = False
    left.provide("database", object(), check=lambda: ready)
    right.provide("database", object())
    first = await left.inject(["database"], lambda ctx, cfg: None)
    second = await right.inject(["database"], lambda ctx, cfg: None)
    ready = True
    assert left.refresh_services("database") == (first,)
    await first
    assert second.state is FiberState.ACTIVE
    await root.fiber.dispose()


def test_intercept_precedence_and_immutable_copied_entries() -> None:
    root = Context()
    mutable: dict[str, object] = {"timeout": 2, "nested": []}
    parent = root.intercept("database", mutable)
    child = parent.extend().intercept("database", {"timeout": 3, "child": True})
    mutable["timeout"] = 99
    result = child.resolve_config("database", {"timeout": 1, "base": True}, {"head": True})
    assert result == {"timeout": 3, "nested": [], "base": True, "child": True, "head": True}
    assert result["nested"] is mutable["nested"]
    result["timeout"] = 100
    assert parent.resolve_config("database")["timeout"] == 2
    assert child.resolve_config("database")["timeout"] == 3
    assert root.resolve_config("database") == {}
    assert child.resolve_config("logger") == {}
    assert child.resolve_config("database", head={"timeout": 4})["timeout"] == 4
    assert child.fiber is root.fiber


@pytest.mark.asyncio
async def test_inject_mapping_adds_per_mount_intercept_over_ancestor_config() -> None:
    root = Context().intercept("database", {"timeout": 1, "shared": True})
    await root.plugin(Database)
    configs: list[dict[str, object]] = []

    def consumer(ctx: Context, config: object) -> None:
        service = ctx.require("database")
        assert isinstance(service, Database)
        assert current_context() is ctx
        configs.append(service.resolve_config())

    declaration: dict[str, object] = {"database": {"timeout": 2}}
    first = root.inject(declaration, consumer)
    declaration["database"] = {"timeout": 3}
    second = root.inject(declaration, consumer)
    await asyncio.gather(first.wait(), second.wait())
    assert first.runtime is second.runtime
    assert configs == [{"timeout": 2, "shared": True}, {"timeout": 3, "shared": True}]
    assert root.resolve_config("database")["timeout"] == 1
    await root.fiber.dispose()


@pytest.mark.asyncio
async def test_service_resolves_explicit_or_active_caller_without_rebinding_owner() -> None:
    root = Context().intercept("database", {"timeout": 1})
    await root.plugin(Database)
    service = root.get("database")
    assert isinstance(service, Database)
    request = root.intercept("database", {"timeout": 2})
    assert service.resolve_config()["timeout"] == 1
    assert service.resolve_config(ctx=request)["timeout"] == 2
    with request.scope():
        assert service.resolve_config()["timeout"] == 2
        assert service.ctx is not request
    assert current_context() is None
    assert service.resolve_config()["timeout"] == 1
    with pytest.raises(ValueError, match="another service scope"):
        service.resolve_config(ctx=root.isolate("database"))
    with pytest.raises(ValueError):
        service.resolve_config(ctx=Context())
    await root.fiber.dispose()


@pytest.mark.asyncio
async def test_custom_service_merge_hook_receives_ancestor_order() -> None:
    class Merged(Database):
        @staticmethod
        def merge_config(*layers: Mapping[str, object]) -> dict[str, object]:
            return {"values": [layer["value"] for layer in layers]}

    root = (
        Context()
        .intercept("database", {"value": "parent"})
        .intercept("database", {"value": "child"})
    )
    await root.plugin(Merged)
    service = root.get("database")
    assert isinstance(service, Merged)
    assert service.resolve_config({"value": "base"}, {"value": "head"}) == {
        "values": ["base", "parent", "child", "head"]
    }
    await root.fiber.dispose()


def test_nested_scopes_restore_after_errors() -> None:
    root = Context()
    child = root.extend()
    assert current_context() is None
    with root.scope() as active:
        assert active is root
        assert current_context() is root
        with pytest.raises(ValueError):
            with child.scope():
                assert current_context() is child
                raise ValueError("scope")
        assert current_context() is root
    assert current_context() is None


@pytest.mark.asyncio
async def test_concurrent_caller_contexts_do_not_bleed_across_awaits() -> None:
    root = Context()
    await root.plugin(Database)
    service = root.get("database")
    assert isinstance(service, Database)
    left = root.intercept("database", {"request": "left"})
    right = root.intercept("database", {"request": "right"})

    async def call(ctx: Context) -> object:
        with ctx.scope():
            await asyncio.sleep(0)
            assert current_context() is ctx
            return service.resolve_config()["request"]

    assert list(await asyncio.gather(call(left), call(right))) == ["left", "right"]
    assert current_context() is None
    await root.fiber.dispose()


@pytest.mark.asyncio
async def test_cancelled_task_scope_restores_context_and_finalizer_sees_caller() -> None:
    root = Context()
    started = asyncio.Event()
    seen: list[Context | None] = []

    async def call() -> None:
        with root.scope():
            try:
                started.set()
                await asyncio.Event().wait()
            finally:
                seen.append(current_context())
        seen.append(current_context())

    task = asyncio.create_task(call())
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert seen == [root]
    assert current_context() is None


@pytest.mark.asyncio
async def test_async_setup_and_cleanup_use_defining_context() -> None:
    root = Context().intercept("database", {"request": "plugin"})
    caller = root.intercept("database", {"request": "unrelated caller"})
    contexts: list[Context | None] = []

    async def plugin(ctx: Context, cfg: object) -> object:
        await asyncio.sleep(0)
        contexts.append(current_context())

        async def cleanup() -> None:
            await asyncio.sleep(0)
            contexts.append(current_context())

        return cleanup

    with caller.scope():
        fiber = await root.plugin(plugin)
        assert current_context() is caller
        await fiber.dispose()
        assert current_context() is caller
    assert contexts == [fiber.ctx, fiber.ctx]
    assert current_context() is None


@pytest.mark.asyncio
async def test_effect_setup_and_cleanup_capture_registering_view() -> None:
    root = Context()
    view = root.intercept("database", {"timeout": 2})
    seen: list[Context | None] = []

    async def setup() -> object:
        await asyncio.sleep(0)
        seen.append(current_context())

        async def cleanup() -> None:
            await asyncio.sleep(0)
            seen.append(current_context())

        return cleanup

    effect = view.effect(setup)
    await effect
    assert current_context() is None
    await root.fiber.dispose()
    assert seen == [view, view]


@pytest.mark.parametrize("mode", ["emit", "bail", "serial", "parallel", "waterfall"])
@pytest.mark.asyncio
async def test_event_callbacks_resolve_dispatcher_intercepts(mode: str) -> None:
    root = Context()
    await root.plugin(Database)
    service = root.get("database")
    assert isinstance(service, Database)
    seen: list[object] = []

    def listener(*args: object) -> object:
        seen.append(service.resolve_config()["request"])
        return None

    root.on("event", listener)
    dispatcher = root.intercept("database", {"request": "caller"})
    options = {"next_": lambda: None} if mode == "waterfall" else {}
    result = getattr(dispatcher, mode)("event", **options)
    if inspect.isawaitable(result):
        await result
    assert seen == ["caller"]
    assert current_context() is None
    await root.fiber.dispose()


@pytest.mark.asyncio
async def test_async_event_and_waterfall_keep_dispatcher_scope_across_awaits() -> None:
    root = Context()
    dispatch = root.intercept("database", {"request": "dispatcher"})
    seen: list[Context | None] = []

    async def listener() -> None:
        await asyncio.sleep(0)
        seen.append(current_context())

    root.on("event", listener)
    await dispatch.parallel("event")

    async def middleware(next_: object) -> object:
        await asyncio.sleep(0)
        seen.append(current_context())
        assert callable(next_)
        return await next_()

    root.on("chain", middleware)
    result = dispatch.waterfall("chain", next_=lambda: "terminal")
    assert inspect.isawaitable(result)
    assert await result == "terminal"
    assert seen == [dispatch, dispatch]
    assert current_context() is None
    await root.fiber.dispose()


@pytest.mark.asyncio
async def test_availability_predicate_reads_consumer_intercept_scope() -> None:
    class Checked(Database):
        def check(self) -> bool:
            return self.resolve_config().get("allowed") is True

    root = Context()
    await root.plugin(Checked)
    allowed = root.intercept("database", {"allowed": True})
    denied = root.intercept("database", {"allowed": False})
    first = await allowed.inject(["database"], lambda ctx, cfg: None)
    second = await denied.inject(["database"], lambda ctx, cfg: None)
    assert first.state is FiberState.ACTIVE
    assert second.state is FiberState.PENDING
    assert current_context() is None
    await root.fiber.dispose()


@pytest.mark.parametrize("config", [1, None, {1: "invalid"}])
def test_invalid_intercept_mappings_are_rejected(config: object) -> None:
    root = Context()
    with pytest.raises(TypeError):
        root.intercept("database", cast(Mapping[str, object], config))
    assert root.resolve_config("database") == {}


def test_invalid_isolation_label_and_name_are_rejected() -> None:
    root = Context()
    with pytest.raises(TypeError):
        root.isolate("database", cast(ScopeLabel, "shared"))
    with pytest.raises(TypeError):
        root.isolate("")
    assert root.get("database") is None


@pytest.mark.asyncio
async def test_isolated_provider_disposal_does_not_unload_default_consumer() -> None:
    root = Context()
    isolated = root.isolate("database")
    await root.plugin(Database)
    owner = await isolated.plugin(Database)
    first = await root.inject(["database"], lambda ctx, cfg: None)
    second = await isolated.inject(["database"], lambda ctx, cfg: None)
    await owner.dispose()
    assert first.state is FiberState.ACTIVE
    assert second.state is FiberState.PENDING
    assert isinstance(root.get("database"), Database)
    assert isolated.get("database", False) is None
    await root.fiber.dispose()


@pytest.mark.asyncio
async def test_async_service_operation_uses_task_local_intercept_config() -> None:
    class Query(Database):
        async def query(self) -> object:
            await asyncio.sleep(0)
            return self.resolve_config()["prefix"]

    root = Context()
    await root.plugin(Query)
    service = root.get("database")
    assert isinstance(service, Query)

    async def operation(prefix: str) -> object:
        with root.intercept("database", {"prefix": prefix}).scope():
            return await service.query()

    assert list(await asyncio.gather(operation("first"), operation("second"))) == [
        "first",
        "second",
    ]
    assert current_context() is None
    await root.fiber.dispose()
