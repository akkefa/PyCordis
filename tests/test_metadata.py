"""Pinned registry declarations adapted to explicit immutable Python metadata."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from typing import cast

import pytest

from deepseek_cordis import (
    Context,
    Fiber,
    FiberState,
    PluginMeta,
    PluginSpec,
    Service,
    inspect_plugin,
    plugin_meta,
)


def test_metadata_copies_normalizes_and_freezes_declarations() -> None:
    nested: list[object] = []
    config: dict[str, object] = {"timeout": 1, "nested": nested}
    dependencies: dict[str, object] = {"database": config, "logger": None}
    provided = ["search", "search"]
    intercepted = {"database": True, "logger": False}
    validator = object()
    meta = PluginMeta(
        name="search",
        inject=dependencies,
        provide=provided,
        intercept=intercepted,
        config=validator,
    )
    config["timeout"] = 99
    provided.append("extra")
    intercepted["database"] = False
    dependencies.clear()
    assert list(meta.inject) == ["database", "logger"]
    database = meta.inject["database"]
    assert database is not None
    assert database["timeout"] == 1
    assert database["nested"] is nested
    assert meta.provide == ("search",)
    assert meta.intercept == {"database": True, "logger": False}
    assert meta.config is validator
    with pytest.raises(FrozenInstanceError):
        meta.name = "changed"  # type: ignore[misc]
    with pytest.raises(TypeError):
        meta.inject["new"] = None  # type: ignore[index]
    with pytest.raises(TypeError):
        database["timeout"] = 2  # type: ignore[index]


@pytest.mark.parametrize(
    "declaration", [["database", "database", "logger"], ("database", "logger")]
)
def test_sequence_dependencies_preserve_order_and_deduplicate(declaration: object) -> None:
    meta = PluginMeta(inject=declaration)
    assert list(meta.inject) == ["database", "logger"]


def test_inspection_does_not_construct_or_start_service() -> None:
    class Search(Service):
        name = "search"
        inject = ["database"]
        intercept = {"database": True}

        def __init__(self, ctx: Context, config: object) -> None:
            pytest.fail("inspection constructed plugin")

    meta = inspect_plugin(Search)
    assert meta.name == "search"
    assert meta.inject == {"database": None}
    assert meta.provide == ("search",)
    assert meta.intercept == {"database": True}


def test_conventional_class_inheritance_and_child_override() -> None:
    class Parent:
        name = "parent"
        inject = ["database"]
        provide = ["search"]

        def __call__(self, ctx: Context, config: object) -> None:
            pass

    class Child(Parent):
        inject = ["logger"]

    assert inspect_plugin(Child()).inject == {"logger": None}
    assert inspect_plugin(Child()).provide == ("search",)
    assert inspect_plugin(Parent()).inject == {"database": None}


def test_decorator_preserves_function_and_class_identity() -> None:
    def callback(ctx: Context, config: object) -> None:
        pass

    decorated = plugin_meta(PluginMeta(inject=["database"]))(callback)
    assert decorated is callback
    assert inspect_plugin(callback).name == "callback"
    assert inspect_plugin(callback).inject == {"database": None}

    class Plugin:
        pass

    assert plugin_meta(PluginMeta(name="declared"))(Plugin) is Plugin
    assert inspect_plugin(Plugin).name == "declared"


@pytest.mark.asyncio
async def test_decorated_function_mount_waits_and_applies_intercept_config() -> None:
    @plugin_meta(PluginMeta(name="consumer", inject={"database": {"timeout": 3}}))
    def consumer(ctx: Context, config: object) -> None:
        assert ctx.resolve_config("database")["timeout"] == 3

    root = Context()
    fiber = await root.plugin(consumer)
    assert fiber.state is FiberState.PENDING
    root.provide("database", object())
    await fiber
    assert cast(FiberState, fiber.state) is FiberState.ACTIVE
    assert fiber.plugin_meta is not None
    assert fiber.plugin_meta.name == "consumer"
    assert fiber.name == "consumer"
    await root.fiber.dispose()


@pytest.mark.asyncio
async def test_spec_supports_slotted_callable_and_preserves_runtime_callback_identity() -> None:
    class Plugin:
        __slots__ = ()

        def __call__(self, ctx: Context, config: object) -> None:
            pass

    plugin = Plugin()
    root = Context()
    spec = PluginSpec(plugin, PluginMeta(name="wrapped"))
    first = await root.plugin(spec)
    second = await root.plugin(plugin)
    assert first.runtime is second.runtime
    assert root.registry.get(spec) is root.registry.get(plugin) is first.runtime
    assert first.runtime is not None
    assert first.runtime.callback is plugin
    assert first.runtime.metadata.name == "wrapped"
    assert second.plugin_meta is not None and second.plugin_meta.name is None
    assert second.name == "wrapped"  # first runtime name wins
    assert spec.plugin is plugin
    await root.fiber.dispose()


@pytest.mark.asyncio
async def test_shared_apply_identity_retains_per_mount_requirements() -> None:
    class Plugin:
        def apply(self, ctx: Context, config: object) -> None:
            pass

    plugin = Plugin()
    root = Context()
    first = await root.plugin(PluginSpec(plugin, PluginMeta(name="first", inject=["database"])))
    second = await root.plugin(PluginSpec(plugin, PluginMeta(name="second", inject=["logger"])))
    assert first.runtime is second.runtime
    assert first.plugin_meta is not None and first.plugin_meta.name == "first"
    assert second.plugin_meta is not None and second.plugin_meta.name == "second"
    assert first.inject == ("database",)
    assert second.inject == ("logger",)
    root.provide("database", object())
    await first
    assert first.state is FiberState.ACTIVE
    assert second.state is FiberState.PENDING
    await root.fiber.dispose()


@pytest.mark.asyncio
async def test_runtime_and_mount_snapshots_survive_later_declaration_changes() -> None:
    class Plugin:
        inject = ["database"]

        def __call__(self, ctx: Context, config: object) -> None:
            pass

    root = Context()
    plugin = Plugin()
    first = await root.plugin(plugin)
    assert first.runtime is not None
    initial = first.runtime.metadata
    Plugin.inject.append("logger")
    second = await root.plugin(plugin)
    assert list(initial.inject) == ["database"]
    assert first.inject == ("database",)
    assert second.inject == ("database", "logger")
    await first.dispose()
    assert first.plugin_meta is not None and list(first.plugin_meta.inject) == ["database"]
    assert first.runtime.metadata is initial
    await root.fiber.dispose()


@pytest.mark.asyncio
async def test_complete_explicit_declaration_replaces_legacy_attributes() -> None:
    class Plugin:
        inject = ["legacy"]
        provide = "legacy"

        def __call__(self, ctx: Context, config: object) -> None:
            pass

    root = Context()
    fiber = await root.plugin(PluginSpec(Plugin(), PluginMeta(name="explicit")))
    assert fiber.inject == ()
    assert fiber.plugin_meta is not None and fiber.plugin_meta.provide == ()
    assert root.get("legacy") is None
    await root.fiber.dispose()


@pytest.mark.asyncio
async def test_provide_and_intercept_declarations_are_descriptive_not_resources() -> None:
    root = Context()
    fiber = await root.plugin(
        PluginSpec(lambda ctx, cfg: None, PluginMeta(provide="ghost", intercept={"database": True}))
    )
    assert root.get("ghost") is None
    assert fiber.ctx.resolve_config("database") == {}
    assert fiber.plugin_meta is not None and fiber.plugin_meta.intercept["database"] is True
    await root.fiber.dispose()


@pytest.mark.asyncio
async def test_service_can_derive_one_binding_name_from_declaration() -> None:
    @plugin_meta(PluginMeta(name="display", provide="database"))
    class Database(Service):
        pass

    root = Context()
    owner = await root.plugin(Database)
    service = root.get("database")
    assert isinstance(service, Database)
    assert service.name == "database"
    assert owner.name == "display"
    await root.fiber.dispose()


@pytest.mark.asyncio
async def test_service_spec_provide_default_and_explicit_class_name_precedence() -> None:
    class Inferred(Service):
        pass

    class Named(Service):
        name = "named"

    root = Context()
    await root.plugin(PluginSpec(Inferred, PluginMeta(provide="database")))
    await root.plugin(PluginSpec(Named, PluginMeta(provide="descriptive")))
    assert isinstance(root.get("database"), Inferred)
    assert isinstance(root.get("named"), Named)
    assert root.get("descriptive") is None
    await root.fiber.dispose()


@pytest.mark.asyncio
async def test_service_legacy_provide_and_multiple_name_ambiguity() -> None:
    class Database(Service):
        provide = "database"

    root = Context()
    direct = Database(root)
    assert root.get("database") is direct

    class Ambiguous(Service):
        provide = ["foo", "bar"]

    fiber = root.plugin(Ambiguous)
    with pytest.raises(TypeError, match="one declared provide"):
        await fiber
    assert root.get("foo") is root.get("bar") is None
    await root.fiber.dispose()


@pytest.mark.asyncio
async def test_config_reference_is_inspectable_but_invalid_protocol_is_rejected() -> None:
    schema = object()
    spec = PluginSpec(lambda ctx, cfg: pytest.fail("must not execute"), PluginMeta(config=schema))
    assert inspect_plugin(spec).config is schema
    root = Context()
    with pytest.raises(TypeError, match="callable validate"):
        root.plugin(spec)
    assert root.registry.size == 0
    assert root.fiber.get_effects() == ()


@pytest.mark.asyncio
async def test_fiber_metadata_is_none_for_root_and_direct_mounts() -> None:
    root = Context()
    direct = await Fiber(root, lambda ctx, cfg: None)
    assert root.fiber.plugin_meta is direct.plugin_meta is None
    await root.fiber.dispose()


@pytest.mark.asyncio
async def test_spec_delete_disposes_all_mounts_of_executable_identity() -> None:
    root = Context()

    def callback(ctx: Context, config: object) -> None:
        pass

    spec = PluginSpec(callback, PluginMeta(name="spec"))
    first = await root.plugin(spec)
    second = await root.plugin(callback)
    assert root.registry.delete(spec) is first.runtime
    await first.dispose()
    await second.dispose()
    assert root.registry.size == 0


def test_inherited_explicit_metadata_replaces_only_when_child_is_decorated() -> None:
    @plugin_meta(PluginMeta(inject=["database"]))
    class Parent:
        pass

    class Child(Parent):
        pass

    assert inspect_plugin(Child).inject == {"database": None}
    plugin_meta(PluginMeta(inject=["logger"]))(Child)
    assert inspect_plugin(Child).inject == {"logger": None}
    assert inspect_plugin(Parent).inject == {"database": None}


@pytest.mark.parametrize(
    "kwargs",
    [
        {"name": 1},
        {"inject": [1]},
        {"inject": {"database": 1}},
        {"provide": ""},
        {"provide": [1]},
        {"provide": 1},
        {"intercept": {"database": 1}},
        {"intercept": {"": True}},
    ],
)
def test_invalid_declarations_rejected_without_mutation(kwargs: dict[str, object]) -> None:
    with pytest.raises(TypeError):
        PluginMeta(**kwargs)  # type: ignore[arg-type]


def test_invalid_specs_and_decorator_inputs_are_rejected() -> None:
    with pytest.raises(TypeError):
        PluginSpec(object(), cast(PluginMeta, {}))
    spec = PluginSpec(lambda ctx, cfg: None, PluginMeta())
    with pytest.raises(TypeError, match="nested"):
        PluginSpec(spec, PluginMeta())
    with pytest.raises(TypeError):
        plugin_meta(cast(PluginMeta, {}))
    with pytest.raises(TypeError):
        plugin_meta(PluginMeta())(object())
    with pytest.raises(TypeError):
        inspect_plugin(object())


@pytest.mark.asyncio
async def test_throwing_metadata_getter_is_atomic_and_preserves_existing_runtime() -> None:
    def callback(ctx: Context, config: object) -> None:
        pass

    class Plugin:
        apply = staticmethod(callback)

        @property
        def inject(self) -> object:
            raise ValueError("metadata getter")

    root = Context()
    first = await root.plugin(callback)
    with pytest.raises(ValueError, match="metadata getter"):
        root.plugin(Plugin())
    assert root.registry.get(callback) is first.runtime
    assert first.runtime is not None and first.runtime.fibers == (first,)
    await root.fiber.dispose()


@pytest.mark.asyncio
async def test_mount_resolves_apply_getter_only_once() -> None:
    calls: list[int] = []

    def first(ctx: Context, config: object) -> None:
        pass

    def second(ctx: Context, config: object) -> None:
        pytest.fail("wrong callback")

    class Plugin:
        @property
        def apply(self) -> object:
            calls.append(1)
            return first if len(calls) == 1 else second

    root = Context()
    fiber = await root.plugin(Plugin())
    assert calls == [1]
    assert fiber.runtime is not None and fiber.runtime.callback is first
    assert fiber.plugin_meta is not None and fiber.plugin_meta.name == "first"
    await root.fiber.dispose()
