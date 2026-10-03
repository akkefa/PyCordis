"""Run with uv run python examples/effects.py."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from pycordis import Context


async def main() -> None:
    ctx = Context()
    events: list[str] = []

    async def cleanup() -> None:
        await asyncio.sleep(0)
        events.append("async cleanup")

    async def setup() -> AsyncIterator[object]:
        events.append("setup")
        yield lambda: events.append("sync cleanup")
        yield cleanup

    effect = ctx.effect(setup, "example")
    await effect
    await ctx.fiber.dispose()  # Structural owner joins and drains the effect.
    assert events == ["setup", "async cleanup", "sync cleanup"]
    assert ctx.fiber.get_effects() == ()
    print(events)


if __name__ == "__main__":
    asyncio.run(main())
