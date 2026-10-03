# PyCordis

An incremental, framework-independent Python plugin runtime targeting the Cordis
behavior used by DeepSeek Harness. Plugins, services, reactive dependencies,
and reversible effects belong here; agent loops and LLM integrations do not.

**Status: Phase 3 Context, low-level Fiber lifecycle and reversible effects.
Services, events and plugin registry are not implemented.**
The internal version is `0.0.0`; `0.1.0` is reserved for a coherent tested API.
The `pycordis` distribution name is provisional (PyPI JSON endpoint returned
404 on 2026-10-03; this does not reserve the name). Nothing has been published.

## Development

Requires Python 3.11+ and uv. The kernel currently has no runtime dependencies.

```sh
uv sync --locked
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv build
```

Read [architecture](docs/architecture.md), [source audit](docs/phase-0.md),
and [compatibility](docs/compatibility.md) before adding runtime code.
The next reviewed increment is Registry and plugin mounting. Read the
[Effects guide](docs/effects.md) and [Effects ADR](docs/adr/0004-reversible-effects.md). Read the
[Fiber lifecycle guide](docs/lifecycle.md) and
[Fiber ADR](docs/adr/0003-fiber-lifecycle.md). Read the
[Context guide](docs/context.md) and [Context ADR](docs/adr/0002-context-foundation.md)
before changing ownership behavior.

## Context foundation

```python
from pycordis import Context

root = Context()
worker = root.extend({"label": "worker"})
child = worker.extend({"request_id": "demo"})

assert child.parent is worker
assert child.root is root
assert child.owner is root
assert child.metadata["label"] == "worker"
```

Metadata is a read-only mapping of shallow-copied entries. Values are shared
by identity; they are not frozen. Context extensions inherit ownership without
creating lifecycle work. Run `uv run python examples/basic_context.py`.
Root construction now binds an ACTIVE root Fiber without creating a Task.

For low-level mounted lifecycle setup and cleanup, see
`uv run python examples/basic_fiber.py`. Direct Fiber construction requires a
running event loop. Root Fiber disposal restarts; child disposal is terminal.

## References and attribution

The primary target is the vendored runtime at DeepSeek Harness commit
`639ed015397290b3745d163aafe02ffee4aa3f84`, not current upstream Cordis.
This is an independent Python implementation in preparation; no affiliation
or compatibility guarantee is claimed. The project is MIT licensed.
See [third-party notices](THIRD_PARTY_NOTICES.md) for source licenses.


## Effects

Register reversible setup with `ctx.effect(setup, "label")`. Await the handle
to settle async setup, or call it to request manual cleanup. Owner unload
automatically joins setup and all owned cleanup. Run
`uv run python examples/effects.py`. Nested cleanup deliberately drains all
callbacks before reporting errors; see the compatibility notes.
