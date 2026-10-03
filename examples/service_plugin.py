"""Run with uv run python examples/service_plugin.py."""

from __future__ import annotations

import asyncio

from pycordis import Context, Service


class Database(Service):
    name = "database"

    def start(self) -> object:
        print("starting database:", self.config)
        return lambda: print("releasing database:", self.config)

    def query(self, statement: str) -> str:
        return f"{self.config}: {statement}"


def consumer(ctx: Context, config: object) -> object:
    database = ctx.require("database")
    assert isinstance(database, Database)
    print(database.query("example query"))
    return lambda: print("releasing consumer for:", database.config)


async def main() -> None:
    root = Context()
    database = await root.plugin(Database, "connection")
    worker = await root.inject(["database"], consumer)
    await database.restart()
    await worker
    await root.fiber.dispose()
    assert root.registry.size == 0
    assert root.get("database", False) is None


if __name__ == "__main__":
    asyncio.run(main())
