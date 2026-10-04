"""Reject a release tag that does not exactly match the package version."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path


def validate_release_ref(ref: str, version: str) -> None:
    expected = f"refs/tags/v{version}"
    if ref != expected:
        raise ValueError(f"Release requires {expected!r}; received {ref!r}")


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    with (root / "pyproject.toml").open("rb") as stream:
        version = str(tomllib.load(stream)["project"]["version"])
    validate_release_ref(os.environ.get("GITHUB_REF", ""), version)
    print(f"Validated release tag v{version}")


if __name__ == "__main__":
    main()
