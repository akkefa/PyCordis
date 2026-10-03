"""Run with uv run python examples/reactive_services.py."""

from __future__ import annotations

import asyncio

from pycordis import Context, FiberState


def consumer(ctx: Context, config: object) -> object:
    value = ctx.require("database")
    print("consumer setup:", value)
    return lambda: print("consumer cleanup:", ctx.require("database"))


async def main() -> None:
    root = Context()
    fiber = await root.inject(["database"], consumer)
    print("waiting:", fiber.state.name)
    first = root.provide("database", "first connection")
    await fiber
    pending = first()
    if pending is not None:
        await pending
    assert fiber.state is FiberState.PENDING
    root.provide("database", "replacement connection")
    await fiber
    await root.fiber.dispose()
    assert root.registry.size == 0


if __name__ == "__main__":
    asyncio.run(main())
