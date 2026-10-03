"""Declare a dependency and read its activation snapshot explicitly."""

import asyncio

from pycordis import Context, FiberState


def worker(ctx: Context, config: object) -> None:
    print("Worker uses:", ctx.require("database"))


async def main() -> None:
    root = Context()
    root.provide("database", "connection")
    fiber = await root.inject(["database"], worker)
    assert fiber.state is FiberState.ACTIVE
    await root.fiber.dispose()
    assert root.get("database", False) is None
    assert root.registry.size == 0


if __name__ == "__main__":
    asyncio.run(main())
