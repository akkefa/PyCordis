"""Run with uv run python examples/basic_fiber.py; low-level Phase 2 API."""

from __future__ import annotations

import asyncio

from pycordis import Context, Fiber


async def setup(ctx: Context, config: object) -> object:
    print("starting", ctx.fiber.name)
    return lambda: print("cleanup", ctx.fiber.name)


async def main() -> None:
    root = Context()
    fiber = await Fiber(root, setup, name="worker")
    await fiber.restart()
    await fiber.dispose()
    await root.fiber.dispose()


if __name__ == "__main__":
    asyncio.run(main())
