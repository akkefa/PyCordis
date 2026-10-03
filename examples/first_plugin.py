"""A first plugin: owned listeners and returned cleanup share one lifetime."""

import asyncio

from pycordis import Context


def greeter(ctx: Context, config: object) -> object:
    ctx.on("hello", lambda name: print("Hello,", name))
    return lambda: print("Greeter stopped")


async def main() -> None:
    root = Context()
    fiber = await root.plugin(greeter)
    root.emit("hello", "Cordis")
    await fiber.dispose()
    root.emit("hello", "listener already removed")
    assert root.registry.size == 0


if __name__ == "__main__":
    asyncio.run(main())
