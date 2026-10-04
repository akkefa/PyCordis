"""Run with a clean wheel environment: /path/to/env/bin/python -I scripts/check_installation.py."""

from __future__ import annotations

import asyncio
import importlib.metadata
import importlib.resources
import json
import sys
import tomllib
from pathlib import Path

import deepseek_cordis
from deepseek_cordis import Context, FiberState, PluginMeta, Service, plugin_meta
from deepseek_cordis.loader import Loader, PluginEntry


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


assert deepseek_cordis.__file__ is not None
installed = Path(deepseek_cordis.__file__).resolve()
assert installed.is_relative_to(Path(sys.prefix).resolve())
with (Path(__file__).resolve().parents[1] / "pyproject.toml").open("rb") as stream:
    project = tomllib.load(stream)["project"]
    expected_name = str(project["name"])
    expected_version = str(project["version"])
assert importlib.metadata.version(expected_name) == expected_version
assert importlib.metadata.requires(expected_name) is None
assert sorted(d.metadata["Name"] for d in importlib.metadata.distributions()) == [expected_name]
assert importlib.resources.files("deepseek_cordis").joinpath("py.typed").is_file()
assert all(hasattr(deepseek_cordis, name) for name in deepseek_cordis.__all__)
direct_url_text = importlib.metadata.distribution(expected_name).read_text("direct_url.json")
assert direct_url_text is not None
direct_url = json.loads(direct_url_text)
assert direct_url["url"].endswith(".whl") and "dir_info" not in direct_url
asyncio.run(verify())
print(
    json.dumps(
        {
            "python": sys.version.split()[0],
            "name": expected_name,
            "version": expected_version,
            "installed": str(installed),
            "runtime_dependencies": [],
            "lifecycle_loader_events_config": "passed",
        }
    )
)
