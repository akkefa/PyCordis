"""Declare plugins while preserving callback identity and per-mount dependencies."""

import asyncio

from deepseek_cordis import Context, PluginMeta, PluginSpec, Service, inspect_plugin, plugin_meta


@plugin_meta(PluginMeta(name="database provider", provide="database"))
class Database(Service):
    pass


@plugin_meta(PluginMeta(name="consumer", inject=["database"]))
def consumer(ctx: Context, config: object) -> None:
    database = ctx.require("database")
    assert isinstance(database, Database)
    print(ctx.resolve_config("database"))


async def main() -> None:
    root = Context()
    provider = await root.plugin(Database)
    first = await root.plugin(consumer)
    second = await root.plugin(
        PluginSpec(
            consumer, PluginMeta(name="configured consumer", inject={"database": {"timeout": 5}})
        )
    )
    assert first.runtime is second.runtime
    assert second.plugin_meta is not None
    assert inspect_plugin(Database).provide == ("database",)
    print(first.runtime.name if first.runtime is not None else None, second.plugin_meta.name)
    await first.dispose()
    await second.dispose()
    await provider.dispose()


if __name__ == "__main__":
    asyncio.run(main())
