"""Apply defaults and normalize configuration before plugin construction."""

import asyncio
from collections.abc import Mapping

from deepseek_cordis import (
    Context,
    PluginMeta,
    Service,
    ValidationError,
    ValidationIssue,
    plugin_meta,
)


class ServerConfig:
    def validate(self, value: object) -> object:
        if not isinstance(value, Mapping):
            raise ValidationError([ValidationIssue("expected an object")])
        port = value.get("port", 8080)
        if not isinstance(port, int) or isinstance(port, bool) or port <= 0:
            raise ValidationError([ValidationIssue("expected a positive integer", ("port",))])
        return {"host": "localhost", **value, "port": port}


@plugin_meta(PluginMeta(config=ServerConfig()))
class Server(Service):
    name = "server"

    def start(self) -> None:
        print("Started with", self.config)


async def main() -> None:
    root = Context()
    raw: dict[str, object] = {}
    fiber = await root.plugin(Server, raw)
    assert fiber.raw_config is raw
    assert fiber.config == {"host": "localhost", "port": 8080}
    await fiber.restart()
    await fiber.dispose()
    invalid = root.plugin(Server, {"port": -1})
    try:
        await invalid
    except ValidationError as error:
        print(error)
        assert invalid.error is error
    finally:
        await invalid.dispose()


if __name__ == "__main__":
    asyncio.run(main())
