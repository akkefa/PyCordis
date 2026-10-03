# Runnable examples

From the repository root, run `uv sync --locked`, then use the commands below.
Every entry point runs independently and releases its owned resources. No external
services, credentials or network are required.

| Order | Command | What to look for |
|---:|---|---|
| 1 | `uv run python examples/first_plugin.py` | Hello, Cordis; one cleanup; later emission has no listener |
| 2 | `uv run python examples/basic_context.py` | Inherited/shadowed metadata without a new lifetime |
| 3 | `uv run python examples/first_service.py` | A named instance starts, answers a query and is removed on disposal |
| 4 | `uv run python examples/dependency_injection.py` | A declared worker reads the database snapshot |
| 5 | `uv run python examples/service_plugin.py` | Service start, dependent query, restart and fresh activation |
| 6 | `uv run python examples/reactive_services.py` | PENDING, provider arrival, old snapshot cleanup and replacement |
| 7 | `uv run python examples/effects.py` | Setup, reversed async/sync cleanup, empty owner diagnostics |
| 8 | `uv run python examples/owned_events.py` | One notice, one async job, automatic listener removal |
| 9 | `uv run python examples/waterfall.py` | Two layers add the same argument; terminal yields Result: 4 |
| 10 | `uv run python examples/events.py` | Async middleware wraps a synchronous terminal |
| 11 | `uv run python examples/basic_plugin.py` | Two mounts share identity but dispose independently |
| 12 | `uv run python examples/basic_fiber.py` | Low-level Fiber start, restart and terminal child disposal |
| 13 | `uv run python examples/scoped_services.py` | Separate database slots and explicit caller/event scope |
| 14 | `uv run python examples/plugin_metadata.py` | Identity-preserving declarations and per-mount intercept options |
| 15 | `uv run python examples/config_validation.py` | Defaults, restart, then an intentionally rejected port with a structured error |
| 16 | `uv run python examples/plugin_loader.py` | Worker listed before database; disabled row never imports; batch cleanup |

config_validation.py intentionally logs and catches a ValidationError for port -1;
that error output is part of the example. loader_plugins.py supplies importable
fixtures for plugin_loader.py and has no standalone main. Running the loader script
from this directory's file path makes its fixture module available through ordinary
Python import rules; the loader itself does not change sys.path.

Read [the mental model](../docs/mental-model.md) and [current compatibility](../docs/compatibility.md)
for ownership rules and documented limits. The examples demonstrate the Python API;
they do not establish full TypeScript or Harness compatibility.
