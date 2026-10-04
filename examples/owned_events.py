"""Synchronous notices and asynchronous jobs use different dispatch methods."""

import asyncio

from deepseek_cordis import Context


def listeners(ctx: Context, config: object) -> None:
    ctx.once("notice", lambda message: print("Notice:", message))

    async def job(message: str) -> None:
        await asyncio.sleep(0)
        print("Job:", message)

    ctx.on("job", job)


async def main() -> None:
    root = Context()
    fiber = await root.plugin(listeners)
    root.emit("notice", "hello")
    root.emit("notice", "already consumed")
    await root.parallel("job", "work")
    await fiber.dispose()
    await root.parallel("job", "listener already removed")
    assert root.registry.size == 0


if __name__ == "__main__":
    asyncio.run(main())
