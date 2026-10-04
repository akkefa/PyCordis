"""Run with: uv run python examples/basic_context.py."""

from __future__ import annotations

from deepseek_cordis import Context


def main() -> None:
    root = Context()
    worker = root.extend({"label": "worker", "tenant": "demo"})
    request = worker.extend({"label": "request", "request_id": "123"})

    assert request.parent is worker
    assert request.root is root
    assert request.owner is root
    assert worker.metadata["label"] == "worker"
    assert request.metadata["label"] == "request"
    assert request.metadata["tenant"] == "demo"
    print(dict(request.metadata))


if __name__ == "__main__":
    main()
