"""Middleware wraps a terminal while every listener receives the same arguments."""

import asyncio
from collections.abc import Callable

from pycordis import Context


def add(value: int, next_: Callable[[], object]) -> int:
    result = next_()
    assert isinstance(result, int)
    return value + result


async def main() -> None:
    root = Context()
    root.on("calculate", add)
    root.on("calculate", add)
    result = root.waterfall("calculate", 1, next_=lambda: 2)
    assert result == 4
    print("Result:", result)
    await root.fiber.dispose()
    assert root.fiber.get_effects() == ()


if __name__ == "__main__":
    asyncio.run(main())
