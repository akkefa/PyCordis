"""Harness synchronous resolveConfig/reload behavior adapted to Python validators."""

from __future__ import annotations

import asyncio
import inspect
from dataclasses import FrozenInstanceError
from typing import cast

import pytest

from deepseek_cordis import (
    ConfigValidator,
    Context,
    Fiber,
    FiberState,
    PluginMeta,
    PluginSpec,
    Service,
    ValidationError,
    ValidationIssue,
    current_context,
    plugin_meta,
)


def test_structured_issues_copy_paths_and_format_diagnostics() -> None:
    path = ["servers", 0, "port"]
    issue = ValidationIssue("must be positive", cast(tuple[str | int, ...], path))
    path.clear()
    error = ValidationError([issue, ValidationIssue("missing name")])
    assert issue.path == ("servers", 0, "port")
    assert str(error) == (
        "invalid config:\n  - must be positive (at servers.0.port)\n  - missing name"
    )
    assert error.issues == (issue, ValidationIssue("missing name"))
    with pytest.raises(FrozenInstanceError):
        issue.message = "changed"  # type: ignore[misc]
    with pytest.raises(AttributeError):
        error.issues = ()  # type: ignore[misc]


@pytest.mark.parametrize("path", ["field", [object()], [True]])
def test_invalid_issue_paths_are_rejected(path: object) -> None:
    with pytest.raises(TypeError):
        ValidationIssue("invalid", cast(tuple[str | int, ...], path))


@pytest.mark.parametrize("issues", [[], [object()]])
def test_invalid_issue_collections_are_rejected(issues: list[object]) -> None:
    with pytest.raises(TypeError):
        ValidationError(cast(list[ValidationIssue], issues))


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [None, False, 0, "", [], {}])
async def test_no_validator_preserves_raw_config_identity(value: object) -> None:
    seen: list[object] = []
    root = Context()
    fiber = await root.plugin(lambda ctx, config: seen.append(config), value)
    assert seen[0] is fiber.config is fiber.raw_config is value
    await fiber.restart()
    assert seen[1] is value
    await root.fiber.dispose()


@pytest.mark.asyncio
async def test_defaults_transform_before_class_constructor_and_start() -> None:
    raw: dict[str, object] = {"port": "123"}
    normalized: dict[str, object] = {"port": 123, "host": "localhost"}
    calls: list[str] = []

    class Schema:
        def validate(self, value: object) -> object:
            assert value is raw
            calls.append("validate")
            return normalized

    schema: ConfigValidator = Schema()

    @plugin_meta(PluginMeta(config=schema))
    class Server(Service):
        name = "server"

        def __init__(self, ctx: Context, config: object) -> None:
            assert config is normalized
            assert ctx.fiber.config is normalized
            calls.append("construct")
            super().__init__(ctx, config)

        def start(self) -> None:
            assert self.config is normalized
            calls.append("start")

    root = Context()
    fiber = await root.plugin(Server, raw)
    assert calls == ["validate", "construct", "start"]
    assert fiber.raw_config is raw
    assert raw == {"port": "123"}
    await root.fiber.dispose()


@pytest.mark.asyncio
async def test_validation_deferred_until_dependencies_available_and_runs_in_mount_scope() -> None:
    calls: list[object] = []
    root = Context()

    class Schema:
        def validate(self, value: object) -> object:
            ctx = current_context()
            assert ctx is not None
            assert ctx.require("database") is database
            assert ctx.resolve_config("database") == {"timeout": 3}
            calls.append(value)
            return {"database": database}

    database = object()
    spec = PluginSpec(
        lambda ctx, config: calls.append(config),
        PluginMeta(config=Schema(), inject={"database": {"timeout": 3}}),
    )
    raw = object()
    fiber = await root.plugin(spec, raw)
    assert fiber.state is FiberState.PENDING
    assert calls == []
    root.provide("database", database)
    await fiber
    assert cast(FiberState, fiber.state) is FiberState.ACTIVE
    assert calls == [raw, {"database": database}]
    assert current_context() is None
    await root.fiber.dispose()


@pytest.mark.asyncio
async def test_validation_failure_retains_error_skips_setup_and_drains_owned_effects() -> None:
    error = ValidationError([ValidationIssue("required", ("port",))])
    released: list[str] = []

    class Schema:
        def validate(self, value: object) -> object:
            ctx = current_context()
            assert ctx is not None
            ctx.effect(lambda: lambda: released.append("validator resource"))
            raise error

    root = Context()
    fiber = root.plugin(
        PluginSpec(lambda ctx, config: pytest.fail("must not start"), PluginMeta(config=Schema()))
    )
    with pytest.raises(ValidationError) as caught:
        await fiber
    assert caught.value is fiber.error is error
    assert fiber.state is FiberState.FAILED
    assert released == ["validator resource"]
    assert fiber.get_effects() == ()
    assert root.registry.size == 1
    with pytest.raises(ValidationError) as repeated:
        await fiber
    assert repeated.value is error
    await fiber.dispose()
    assert root.registry.size == 0


@pytest.mark.asyncio
async def test_restart_revalidates_raw_input_and_retains_last_success_on_failure() -> None:
    raw = object()
    results = [object(), object()]
    inputs: list[object] = []
    failure = ValueError("schema bug")

    class Schema:
        def validate(self, value: object) -> object:
            inputs.append(value)
            if len(inputs) == 2:
                raise failure
            return results[0] if len(inputs) == 1 else results[1]

    root = Context()
    seen: list[object] = []
    fiber = await root.plugin(
        PluginSpec(lambda ctx, config: seen.append(config), PluginMeta(config=Schema())), raw
    )
    with pytest.raises(ValueError) as caught:
        await fiber.restart()
    assert caught.value is failure
    assert fiber.config is results[0]
    assert seen == [results[0]]
    await fiber.restart()
    assert inputs == [raw, raw, raw]
    assert seen == results
    assert fiber.error is None
    await root.fiber.dispose()


@pytest.mark.asyncio
async def test_service_loss_and_restoration_revalidate_against_new_snapshot() -> None:
    root = Context()
    seen: list[object] = []

    class Schema:
        def validate(self, value: object) -> object:
            ctx = current_context()
            assert ctx is not None
            return ctx.require("database")

    first, second = object(), object()
    provider = root.provide("database", first)
    fiber = await root.plugin(
        PluginSpec(
            lambda ctx, config: seen.append(config),
            PluginMeta(config=Schema(), inject=["database"]),
        )
    )
    removal = provider()
    if inspect.isawaitable(removal):
        await removal
    await fiber
    assert fiber.state is FiberState.PENDING
    root.provide("database", second)
    await fiber
    assert seen == [first, second]
    assert fiber.config is second
    await root.fiber.dispose()


@pytest.mark.asyncio
async def test_shared_runtime_keeps_each_mount_validator_independent() -> None:
    class Schema:
        def __init__(self, result: object) -> None:
            self.result = result

        def validate(self, value: object) -> object:
            return self.result

    def plugin(ctx: Context, config: object) -> None:
        pass

    root = Context()
    a, b = object(), object()
    first = await root.plugin(PluginSpec(plugin, PluginMeta(config=Schema(a))))
    second = await root.plugin(PluginSpec(plugin, PluginMeta(config=Schema(b))))
    assert first.runtime is second.runtime
    assert first.config is a and second.config is b
    await root.fiber.dispose()


@pytest.mark.asyncio
async def test_conventional_config_static_validator_and_false_output() -> None:
    class Schema:
        @staticmethod
        def validate(value: object) -> object:
            return False

    class Plugin:
        Config = Schema

        def __call__(self, ctx: Context, config: object) -> None:
            assert config is False

    root = Context()
    fiber = await root.plugin(Plugin())
    assert fiber.config is False
    await root.fiber.dispose()


@pytest.mark.asyncio
async def test_async_validator_result_is_closed_and_reported_as_lifecycle_failure() -> None:
    entered: list[bool] = []

    class Schema:
        async def validate(self, value: object) -> object:
            entered.append(True)
            return value

    root = Context()
    fiber = root.plugin(
        PluginSpec(lambda ctx, config: pytest.fail("must not start"), PluginMeta(config=Schema()))
    )
    with pytest.raises(TypeError, match="Async config validation"):
        await fiber
    assert fiber.state is FiberState.FAILED
    assert entered == []
    await root.fiber.dispose()


@pytest.mark.asyncio
async def test_future_validator_result_is_rejected_without_cancelling_external_work() -> None:
    future: asyncio.Future[object] = asyncio.get_running_loop().create_future()

    class Schema:
        def validate(self, value: object) -> object:
            return future

    root = Context()
    fiber = root.plugin(PluginSpec(lambda ctx, config: None, PluginMeta(config=Schema())))
    with pytest.raises(TypeError, match="Async config validation"):
        await fiber
    assert not future.cancelled()
    future.set_result(None)
    await root.fiber.dispose()


@pytest.mark.asyncio
async def test_disposal_before_loading_checkpoint_skips_validator() -> None:
    class Schema:
        def validate(self, value: object) -> object:
            pytest.fail("disposed mount must not validate")

    root = Context()
    fiber = root.plugin(PluginSpec(lambda ctx, config: None, PluginMeta(config=Schema())))
    await fiber.dispose()
    assert fiber.state is FiberState.DISPOSED


@pytest.mark.asyncio
async def test_validator_disposal_prevents_setup_and_config_publication() -> None:
    raw = object()

    class Schema:
        def validate(self, value: object) -> object:
            ctx = current_context()
            assert ctx is not None
            ctx.fiber.dispose()
            return object()

    root = Context()
    fiber = root.plugin(
        PluginSpec(
            lambda ctx, config: pytest.fail("disposed mount ran"), PluginMeta(config=Schema())
        ),
        raw,
    )
    await fiber
    assert fiber.state is FiberState.DISPOSED
    assert fiber.config is raw
    assert root.registry.size == 0


@pytest.mark.asyncio
async def test_direct_fiber_preserves_raw_config_without_validation() -> None:
    root = Context()
    value = object()
    fiber = await Fiber(root, lambda ctx, config: None, value)
    assert fiber.raw_config is fiber.config is value
    await root.fiber.dispose()


@pytest.mark.asyncio
async def test_invalid_validator_rejection_preserves_live_shared_runtime() -> None:
    def plugin(ctx: Context, config: object) -> None:
        pass

    root = Context()
    existing = await root.plugin(plugin)
    effects = root.fiber.get_effects()
    runtime = existing.runtime
    with pytest.raises(TypeError, match="callable validate"):
        root.plugin(PluginSpec(plugin, PluginMeta(config=object())))
    assert root.registry.size == 1
    assert root.registry.get(plugin) is runtime
    assert runtime is not None and runtime.fibers == (existing,)
    assert root.fiber.get_effects() == effects
    await root.fiber.dispose()


@pytest.mark.asyncio
async def test_validator_can_normalize_to_none_without_falling_back_to_raw() -> None:
    class Schema:
        def validate(self, value: object) -> object:
            return None

    root = Context()
    raw = object()
    seen: list[object] = []
    fiber = await root.plugin(
        PluginSpec(lambda ctx, config: seen.append(config), PluginMeta(config=Schema())), raw
    )
    assert seen == [None]
    assert fiber.config is None and fiber.raw_config is raw
    await root.fiber.dispose()


@pytest.mark.asyncio
async def test_pending_disposed_validator_is_never_called() -> None:
    class Schema:
        def validate(self, value: object) -> object:
            pytest.fail("missing service must defer validation")

    root = Context()
    fiber = await root.plugin(
        PluginSpec(lambda ctx, config: None, PluginMeta(config=Schema(), inject=["database"]))
    )
    assert fiber.state is FiberState.PENDING
    await fiber.dispose()
    root.provide("database", object())
    await root.fiber.dispose()
