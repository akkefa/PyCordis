"""Verify that the installed package is importable before runtime work starts."""

from __future__ import annotations

import deepseek_cordis


def test_package_import() -> None:
    assert deepseek_cordis.__name__ == "deepseek_cordis"
