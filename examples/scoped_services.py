"""Run with uv run python examples/scoped_services.py."""

from __future__ import annotations

import asyncio

from pycordis import Context, Service


class Database(Service):
    name = "database"

    async def query(self) -> object:
        await asyncio.sleep(0)
        return self.resolve_config().get("timeout", "default")


async def main() -> None:
    root = Context()
    private = root.isolate("database")
    await root.plugin(Database)
    await private.plugin(Database)
    database = private.get("database")
    assert isinstance(database, Database)
    assert database is not root.get("database")
    request = private.intercept("database", {"timeout": 5})
    with request.scope():
        print("private query timeout:", await database.query())
    root.on("database-event", lambda: print("default listener"))
    private.on("database-event", lambda: print("private listener"))
    private.emit("database-event", filter_=database.matches_scope)
    await root.fiber.dispose()
    assert private.get("database", False) is root.get("database", False) is None


if __name__ == "__main__":
    asyncio.run(main())
