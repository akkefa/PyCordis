"""Run with a clean wheel environment: /path/to/env/bin/python -I scripts/check_installation.py."""

from __future__ import annotations

import asyncio
import importlib.metadata
import importlib.resources
import json
import sys
from pathlib import Path

import pycordis
from pycordis import Context, FiberState, PluginMeta, Service, plugin_meta
from pycordis.loader import Loader, PluginEntry


async def verify() -> None:
    calls: list[tuple[str, object]] = []

    class Validator:
        def validate(self, value: object) -> object:
            assert value is None
            return {"timeout": 5}

    @plugin_meta(PluginMeta(config=Validator()))
    class Database(Service):
        name = "database"

        def start(self) -> None:
            assert self.config == {"timeout": 5}

    @plugin_meta(PluginMeta(inject=["database"]))
    def worker(ctx: Context, config: object) -> object:
        assert isinstance(ctx.require("database"), Database)
        calls.append(("start", config))
        ctx.on("probe", lambda value: calls.append(("event", value)))
        return lambda: calls.append(("cleanup", config))

    root = Context()
    batch = await Loader(root).load(
        [
            PluginEntry(id="worker", plugin=worker, config="demo"),
            PluginEntry(id="database", plugin=Database),
        ]
    )
    assert all(f.state is FiberState.ACTIVE for f in batch.fibers.values())
    root.emit("probe", 42)
    assert ("event", 42) in calls
    await batch.dispose()
    assert root.registry.size == 0
    assert ("cleanup", "demo") in calls
    before = list(calls)
    root.emit("probe", 99)
    assert calls == before
    await root.fiber.dispose()


assert pycordis.__file__ is not None
installed = Path(pycordis.__file__).resolve()
assert installed.is_relative_to(Path(sys.prefix).resolve())
assert importlib.metadata.version("pycordis") == "0.1.0"
assert importlib.metadata.requires("pycordis") is None
assert sorted(d.metadata["Name"] for d in importlib.metadata.distributions()) == ["pycordis"]
assert importlib.resources.files("pycordis").joinpath("py.typed").is_file()
assert all(hasattr(pycordis, name) for name in pycordis.__all__)
direct_url_text = importlib.metadata.distribution("pycordis").read_text("direct_url.json")
assert direct_url_text is not None
direct_url = json.loads(direct_url_text)
assert direct_url["url"].endswith(".whl") and "dir_info" not in direct_url
asyncio.run(verify())
print(
    json.dumps(
        {
            "python": sys.version.split()[0],
            "version": "0.1.0",
            "installed": str(installed),
            "runtime_dependencies": [],
            "lifecycle_loader_events_config": "passed",
        }
    )
)
