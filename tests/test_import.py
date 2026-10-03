"""Verify that the installed package is importable before runtime work starts."""

from __future__ import annotations

import pycordis


def test_package_import() -> None:
    assert pycordis.__name__ == "pycordis"
