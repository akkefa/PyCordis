"""Load consumers before providers using explicit module references and config rows."""

import asyncio

from pycordis import Context, FiberState
from pycordis.loader import Loader


async def main() -> None:
    root = Context()
    batch = await Loader(root).load_config(
        [
            {"id": "worker", "plugin": "loader_plugins:worker", "config": {"label": "demo"}},
            {"id": "database", "plugin": "loader_plugins:Database"},
            {"id": "disabled", "plugin": "not_imported", "enabled": False},
        ]
    )
    assert list(batch.fibers) == ["worker", "database"]
    assert all(fiber.state is FiberState.ACTIVE for fiber in batch.fibers.values())
    print("Loaded:", list(batch.fibers))
    await batch.dispose()
    assert root.registry.size == 0


if __name__ == "__main__":
    asyncio.run(main())
