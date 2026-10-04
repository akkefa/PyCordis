"""Pinned service.ts/service.spec.ts adaptations; no tracing or scope claims."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator

import pytest

from deepseek_cordis import Context, CordisError, Fiber, FiberState, Service


def assert_state(fiber: Fiber, state: FiberState) -> None:
    assert fiber.state is state


class Database(Service):
    name = "database"


def test_direct_construction_registers_instance_synchronously() -> None:
    root = Context()
    config: dict[str, object] = {}
    service = Database(root, config)
    assert root.get("database") is service
    assert root.require("database") is service
    assert service.ctx is root
    assert service.config is config
    assert service.name == "database"
    assert isinstance(service, Service)
    assert service.check() is True
    assert service.start() is None


@pytest.mark.asyncio
async def test_default_constructor_mounts_class_and_owns_binding() -> None:
    root = Context()
    config = object()
    fiber = await root.plugin(Database, config)
    service = root.get("database")
    assert isinstance(service, Database)
    assert service.ctx is fiber.ctx
    assert service.config is config
    assert fiber.name == "database"
    assert len(fiber.get_effects()) == 2  # registration and plugin setup
    await fiber.dispose()
    assert root.get("database", False) is None
    assert fiber.get_effects() == ()
    assert root.registry.size == 0


@pytest.mark.asyncio
async def test_inherited_name_and_explicit_override_are_per_instance() -> None:
    class Replica(Database):
        pass

    root = Context()
    default = Replica(root)
    other = Replica(root, name="replica")
    assert root.get("database") is default
    assert root.get("replica") is other
    assert Replica.name == Database.name == "database"
    assert other.name == "replica"
    await root.fiber.dispose()


@pytest.mark.parametrize("name", ["", 1, None])
@pytest.mark.asyncio
async def test_invalid_declared_name_is_atomic(name: object) -> None:
    class Invalid(Service):
        pass

    Invalid.name = name  # type: ignore[assignment]
    root = Context()
    with pytest.raises(TypeError, match="nonempty strings"):
        Invalid(root)
    assert root.fiber.get_effects() == ()
    assert root.get("database") is None


@pytest.mark.asyncio
async def test_duplicate_service_mount_rolls_back_preserving_first_instance() -> None:
    root = Context()
    first = await root.plugin(Database)
    service = root.get("database")
    second = root.plugin(Database)
    with pytest.raises(CordisError) as error:
        await second
    assert error.value.code == "DUPLICATE_SERVICE"
    assert root.get("database") is service
    assert_state(first, FiberState.ACTIVE)
    assert_state(second, FiberState.FAILED)
    assert second.get_effects() == ()
    await root.fiber.dispose()


@pytest.mark.asyncio
async def test_async_start_blocks_dependents_until_complete() -> None:
    root = Context()
    started, release = asyncio.Event(), asyncio.Event()
    instances: list[Service] = []

    class Slow(Database):
        async def start(self) -> object:
            instances.append(self)
            started.set()
            await release.wait()
            return None

    seen: list[object] = []
    consumer = await root.inject(
        ["database"], lambda ctx, cfg: seen.append(ctx.require("database"))
    )
    owner = root.plugin(Slow)
    await started.wait()
    assert root.get("database") is None
    assert root.get("database", False) is instances[0]
    assert_state(consumer, FiberState.PENDING)
    release.set()
    await owner
    await consumer
    assert seen == instances
    await root.fiber.dispose()


@pytest.mark.asyncio
async def test_direct_construction_does_not_call_start() -> None:
    calls: list[str] = []

    class Direct(Database):
        def start(self) -> object:
            calls.append("start")
            return lambda: calls.append("cleanup")

    root = Context()
    Direct(root)
    assert calls == []
    await root.fiber.dispose()
    assert calls == []


@pytest.mark.asyncio
async def test_custom_constructor_and_start_resources_are_owned() -> None:
    calls: list[str] = []

    class Owned(Database):
        def __init__(self, ctx: Context, config: object = None) -> None:
            super().__init__(ctx, config)
            ctx.effect(lambda: lambda: calls.append("constructor cleanup"))

        async def start(self) -> object:
            calls.append("start")
            return lambda: calls.append("start cleanup")

    root = Context()
    owner = await root.plugin(Owned)
    await owner.dispose()
    assert calls[0] == "start"
    assert sorted(calls[1:]) == ["constructor cleanup", "start cleanup"]
    assert root.get("database", False) is None
    assert not owner.cleanup_errors


@pytest.mark.asyncio
async def test_start_can_collect_nested_effects_and_generators() -> None:
    calls: list[str] = []

    class Collected(Database):
        def start(self) -> Iterator[object]:
            yield self.ctx.effect(lambda: lambda: calls.append("first"))
            yield lambda: calls.append("second")

    root = Context()
    fiber = await root.plugin(Collected)
    await fiber.dispose()
    assert calls == ["second", "first"]
    assert root.get("database", False) is None


@pytest.mark.parametrize("fail_in_constructor", [False, True])
@pytest.mark.asyncio
async def test_failed_start_or_constructor_rolls_back_registration_and_resources(
    fail_in_constructor: bool,
) -> None:
    root = Context()
    calls: list[str] = []

    class Broken(Database):
        def __init__(self, ctx: Context, config: object = None) -> None:
            super().__init__(ctx, config)
            ctx.effect(lambda: lambda: calls.append("released"))
            if fail_in_constructor:
                raise ValueError("constructor")

        async def start(self) -> object:
            raise ValueError("start")

    consumer = await root.inject(["database"], lambda ctx, cfg: pytest.fail("unavailable"))
    owner = root.plugin(Broken)
    with pytest.raises(ValueError):
        await owner
    assert calls == ["released"]
    assert root.get("database", False) is None
    assert_state(consumer, FiberState.PENDING)
    assert owner.get_effects() == ()
    await root.fiber.dispose()


@pytest.mark.asyncio
async def test_restart_constructs_fresh_instance_and_reloads_consumers() -> None:
    root = Context()
    owner = await root.plugin(Database)
    first = root.get("database")
    seen: list[object] = []
    consumer = await root.inject(
        ["database"], lambda ctx, cfg: seen.append(ctx.require("database"))
    )
    await owner.restart()
    await consumer
    second = root.get("database")
    assert isinstance(second, Database)
    assert first is not second
    assert seen == [first, second]
    await root.fiber.dispose()


@pytest.mark.asyncio
async def test_service_dependencies_chain_pending_loss_and_restoration() -> None:
    calls: list[Service] = []

    class Search(Service):
        name = "search"
        inject = ["database"]

        def start(self) -> object:
            assert isinstance(self.ctx.require("database"), Database)
            calls.append(self)
            return None

    root = Context()
    search = await root.plugin(Search)
    assert_state(search, FiberState.PENDING)
    assert root.get("search", False) is None  # constructor has not run
    database = await root.plugin(Database)
    await search
    assert len(calls) == 1
    await database.dispose()
    assert_state(search, FiberState.PENDING)
    assert root.get("search", False) is None
    await root.plugin(Database)
    await search
    assert len(calls) == 2
    assert calls[0] is not calls[1]
    await root.fiber.dispose()


@pytest.mark.asyncio
async def test_check_method_gates_dependents_and_can_be_refreshed() -> None:
    class Checked(Database):
        ready = False

        def check(self) -> bool:
            return self.ready

    root = Context()
    await root.plugin(Checked)
    service = root.get("database")
    assert isinstance(service, Checked)
    consumer = await root.inject(["database"], lambda ctx, cfg: None)
    assert_state(consumer, FiberState.PENDING)
    service.ready = True
    assert service.ctx.refresh_services(service.name) == (consumer,)
    await consumer
    assert_state(consumer, FiberState.ACTIVE)
    service.ready = False
    service.ctx.refresh_services(service.name)
    await consumer
    assert_state(consumer, FiberState.PENDING)
    await root.fiber.dispose()


@pytest.mark.asyncio
async def test_failing_check_keeps_consumer_pending_and_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    class Checked(Database):
        def check(self) -> bool:
            raise ValueError("not ready")

    root = Context()
    await root.plugin(Checked)
    consumer = await root.inject(["database"], lambda ctx, cfg: None)
    assert_state(consumer, FiberState.PENDING)
    assert "availability check failed" in caplog.text
    assert isinstance(root.get("database"), Checked)
    await root.fiber.dispose()


@pytest.mark.asyncio
async def test_callable_service_uses_native_call_and_keeps_instance_identity() -> None:
    class CallableDatabase(Database):
        def __call__(self, value: int) -> int:
            return value + 1

    root = Context()
    fiber = await root.plugin(CallableDatabase)
    service = root.get("database")
    assert isinstance(service, CallableDatabase)
    assert service(4) == 5
    assert root.get("database") is service
    assert root.registry.get(CallableDatabase) is fiber.runtime
    # Constructed callable instance is not collected as a cleanup callback.
    await fiber.dispose()
    assert not fiber.cleanup_errors


@pytest.mark.asyncio
async def test_manual_registration_removal_joins_dependents_without_disposing_owner() -> None:
    root = Context()
    owner = await root.plugin(Database)
    service = root.get("database")
    assert isinstance(service, Database)
    calls: list[object] = []
    consumer = await root.inject(
        ["database"], lambda ctx, cfg: lambda: calls.append(ctx.require("database"))
    )
    result = service.registration()
    assert result is not None
    await result
    assert calls == [service]
    assert_state(consumer, FiberState.PENDING)
    assert_state(owner, FiberState.ACTIVE)
    assert service.registration() is None
    assert root.get("database", False) is None
    await owner.restart()
    await consumer
    assert root.get("database") is not service
    await root.fiber.dispose()


@pytest.mark.asyncio
async def test_service_start_creates_pending_child_consumer_then_parent_activates() -> None:
    children: list[Fiber] = []
    seen: list[object] = []

    class Parent(Database):
        def start(self) -> object:
            children.append(
                self.ctx.inject([self.name], lambda ctx, cfg: seen.append(ctx.require(self.name)))
            )
            return None

    root = Context()
    owner = await root.plugin(Parent)
    await children[0]
    assert len(seen) == 1
    assert seen[0] is root.get("database")
    async with asyncio.timeout(2):
        await owner.dispose()
    assert_state(children[0], FiberState.DISPOSED)
    assert root.registry.size == 0
    assert root.get("database", False) is None


@pytest.mark.asyncio
async def test_disposal_during_async_start_waits_and_never_publishes() -> None:
    started, release = asyncio.Event(), asyncio.Event()
    calls: list[str] = []

    class Slow(Database):
        async def start(self) -> object:
            started.set()
            await release.wait()
            return lambda: calls.append("cleanup")

    root = Context()
    consumer = await root.inject(["database"], lambda ctx, cfg: pytest.fail("disposed"))
    owner = root.plugin(Slow)
    await started.wait()
    disposal = asyncio.ensure_future(owner.dispose())
    await asyncio.sleep(0)
    assert not disposal.done()
    release.set()
    await disposal
    assert calls == ["cleanup"]
    assert_state(owner, FiberState.DISPOSED)
    assert_state(consumer, FiberState.PENDING)
    assert root.get("database", False) is None
    await root.fiber.dispose()


@pytest.mark.asyncio
async def test_cancelled_start_waiter_does_not_cancel_owned_service_start() -> None:
    started, release = asyncio.Event(), asyncio.Event()

    class Slow(Database):
        async def start(self) -> object:
            started.set()
            await release.wait()
            return None

    root = Context()
    owner = root.plugin(Slow)
    waiter = asyncio.create_task(owner.wait())
    await started.wait()
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter
    release.set()
    await owner
    assert isinstance(root.get("database"), Slow)
    await root.fiber.dispose()


@pytest.mark.asyncio
async def test_service_context_is_defining_owner_and_ordinary_methods_are_untraced() -> None:
    class Counter(Database):
        def get_context(self) -> Context:
            return self.ctx

    root = Context()
    owner = await root.extend({"label": "defining"}).plugin(Counter)
    service = root.get("database")
    assert isinstance(service, Counter)
    consumer = await root.inject(["database"], lambda ctx, cfg: None)
    assert service.get_context() is owner.ctx
    assert consumer.ctx.require("database") is service
    with pytest.raises(AttributeError):
        service.ctx = consumer.ctx  # type: ignore[misc]
    with pytest.raises(AttributeError):
        service.config = object()  # type: ignore[misc]
    await root.fiber.dispose()


@pytest.mark.asyncio
async def test_start_cleanup_failure_still_removes_binding_and_dependents() -> None:
    class Broken(Database):
        def start(self) -> object:
            def cleanup() -> None:
                raise ValueError("cleanup")

            return cleanup

    root = Context()
    owner = await root.plugin(Broken)
    consumer = await root.inject(["database"], lambda ctx, cfg: None)
    await owner.dispose()
    assert root.get("database", False) is None
    assert_state(consumer, FiberState.PENDING)
    assert len(owner.cleanup_errors) == 1
    await root.fiber.dispose()


@pytest.mark.asyncio
async def test_resources_created_by_service_methods_keep_defining_fiber_ownership() -> None:
    calls: list[str] = []

    class ResourceDatabase(Database):
        def open_resource(self) -> None:
            self.ctx.effect(lambda: lambda: calls.append("released"))

    root = Context()
    owner = await root.plugin(ResourceDatabase)

    def consumer(ctx: Context, config: object) -> None:
        service = ctx.require("database")
        assert isinstance(service, ResourceDatabase)
        service.open_resource()

    user = await root.inject(["database"], consumer)
    await user.dispose()
    assert calls == []  # no caller-context tracing is implied by ordinary methods
    await owner.dispose()
    assert calls == ["released"]
    assert owner.get_effects() == ()
