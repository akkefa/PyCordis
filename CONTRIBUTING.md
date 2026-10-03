# Contributing

Use Python 3.11+ and uv. Run `uv sync --locked`, `uv run pytest`,
`uv run ruff check .`, `uv run ruff format --check .`, and `uv run mypy`.
Build with `uv build` when packaging changes.

Work one reviewed phase at a time. Before a runtime change, inspect the pinned
Harness source and corresponding Cordis tests, explain the behavior and Python
choices, then implement behavior tests. Keep upstream fixes distinct from the
primary compatibility target. Record deliberate deviations in docs/adr and
update docs/compatibility.md. Avoid agent-specific dependencies in the kernel.
Never commit or publish without the maintainer's explicit request.
