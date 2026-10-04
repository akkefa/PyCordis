"""Release authorization must match a versioned tag, never a branch or prefix."""

import runpy
from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest

validate_release_ref = cast(
    Callable[[str, str], None],
    runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts/check_release_tag.py"))[
        "validate_release_ref"
    ],
)


@pytest.mark.parametrize("version", ["0.1.0", "0.2.0", "1.0.0rc1"])
def test_exact_versioned_tag(version: str) -> None:
    validate_release_ref(f"refs/tags/v{version}", version)


@pytest.mark.parametrize(
    "ref",
    [
        "",
        "refs/heads/main",
        "refs/heads/v0.1.0",
        "refs/tags/0.1.0",
        "refs/tags/v0.2.0",
        "refs/tags/v0.1.0-extra",
    ],
)
def test_reject_nonmatching_release_ref(ref: str) -> None:
    with pytest.raises(ValueError, match="Release requires"):
        validate_release_ref(ref, "0.1.0")
