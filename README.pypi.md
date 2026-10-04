# deepseek-cordis

A lightweight Python plugin runtime for services, reactive dependencies, owned
effects and events. Python 3.11+; no runtime dependencies.

PyPI distribution: `deepseek-cordis`. Python import: `deepseek_cordis`.

Version 0.1.0 is an alpha API. deepseek-cordis adapts the ownership model of the vendored
Cordis 4.0.4 runtime used by DeepSeek Harness at commit
`639ed015397290b3745d163aafe02ffee4aa3f84`. It is an independent implementation,
not the Harness application or an affiliated Cordis/DeepSeek product.

## First plugin

```python
import asyncio
from deepseek_cordis import Context


def greeter(ctx: Context, config: object) -> object:
    ctx.on("hello", lambda name: print("Hello,", name))
    return lambda: print("Greeter stopped")


async def main() -> None:
    root = Context()
    fiber = await root.plugin(greeter)
    root.emit("hello", "Cordis")
    await fiber.dispose()


asyncio.run(main())
```

The Fiber owns the listener and returned cleanup. Disposal removes the listener
and joins teardown. Named services can gate consumers through declared dependencies;
provider loss unloads them and restoration starts a new activation. Context views
share an owner unless a new plugin is mounted.

## Features and boundaries

- Sync/async setup, owned cleanup, generator effects and nested plugin lifetimes.
- Scoped service bindings, reactive injection, caller intercept options and Service classes.
- Owned events with emit, parallel, serial, bail and waterfall dispatch.
- Explicit plugin metadata, synchronous config validation and deterministic loader batches.
- Typed package with a py.typed marker.

Compatibility is partial. Transparent method/property proxies, method injection,
LoggerService exporters, kernel publication hooks, Fiber.update and advanced loader
configuration/HMR remain unimplemented. Passing Python tests does not establish full
Cordis or live DeepSeek Harness compatibility. There are no schema adapter extras.

## Documentation

- [Source and full walkthrough](https://github.com/akkefa/deepseek-cordis)
- [Runtime mental model](https://github.com/akkefa/deepseek-cordis/blob/main/docs/mental-model.md)
- [Runnable examples](https://github.com/akkefa/deepseek-cordis/blob/main/examples/README.md)
- [Compatibility matrix](https://github.com/akkefa/deepseek-cordis/blob/main/docs/compatibility.md)
- [Packaging and local installation](https://github.com/akkefa/deepseek-cordis/blob/main/docs/packaging.md)
- [Issues](https://github.com/akkefa/deepseek-cordis/issues)
- [Changelog](https://github.com/akkefa/deepseek-cordis/blob/main/CHANGELOG.md)

MIT licensed, copyright 2026 Ikram Ali. Cordis (Shigma) and DeepSeek Harness
(DeepSeek) are MIT-licensed behavioral references. The distribution includes the
project license and retained third-party notices; the full
[attribution](https://github.com/akkefa/deepseek-cordis/blob/main/THIRD_PARTY_NOTICES.md)
is also available in the source repository.
