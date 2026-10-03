"""Run with uv run python examples/events.py."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable

from pycordis import Context


def plugin(ctx: Context, config: object) -> None:
    ctx.once("notice", lambda message: print("notice:", message))

    async def middleware(value: int, next_: Callable[[], Awaitable[int]]) -> int:
        print("middleware before")
        result = await next_()
        print("middleware after")
        return value + result

    ctx.on("calculate", middleware)


async def main() -> None:
    root = Context()
    fiber = await root.plugin(plugin)
    root.emit("notice", "hello")
    root.emit("notice", "already consumed")
    result = root.waterfall("calculate", 1, next_=lambda: 2)
    if inspect.isawaitable(result):
        result = await result
    print("result:", result)
    await fiber.dispose()
    root.emit("notice", "owner disposed")
    assert root.fiber.get_effects() == ()


if __name__ == "__main__":
    asyncio.run(main())
