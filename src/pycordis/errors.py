"""Stable runtime error codes."""

from __future__ import annotations


class CordisError(RuntimeError):
    """Runtime misuse with a machine-readable code."""

    def __init__(self, code: str, message: str | None = None) -> None:
        self.code = code
        super().__init__(message or code)
