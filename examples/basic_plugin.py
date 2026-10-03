"""Run with uv run python examples/basic_plugin.py."""

from __future__ import annotations

import asyncio

from pycordis import Context


async def worker(ctx: Context, config: object) -> object:
    print("starting", config, "in", ctx.metadata["label"])
    return lambda: print("cleanup", config)


async def main() -> None:
    root = Context()
    scope = root.extend({"label": "demo"})
    first = await scope.plugin(worker, "first")
    second = await scope.plugin(worker, "second")
    assert first.runtime is second.runtime
    assert root.registry.size == 1
    await first.dispose()
    await root.fiber.dispose()
    assert root.registry.size == 0


if __name__ == "__main__":
    asyncio.run(main())
