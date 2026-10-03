"""Mount a named Service instance and release its resources with its Fiber."""

import asyncio

from pycordis import Context, Service


class Database(Service):
    name = "database"

    def start(self) -> object:
        print("Database ready:", self.config)
        return lambda: print("Database released")

    def query(self, statement: str) -> str:
        return f"{self.config}: {statement}"


async def main() -> None:
    root = Context()
    fiber = await root.plugin(Database, "connection")
    database = root.get("database")
    assert isinstance(database, Database)
    print(database.query("select example"))
    await fiber.dispose()
    assert root.get("database", False) is None


if __name__ == "__main__":
    asyncio.run(main())
