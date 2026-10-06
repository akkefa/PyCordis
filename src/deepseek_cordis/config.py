"""Minimal synchronous configuration validation, independent of schema libraries."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Protocol, cast


class ConfigValidator(Protocol):
    """Return normalized config or raise; awaitable results are unsupported. """

    def validate(self, value: object) -> object: ...


def _resolve_validator(validator: object) -> Callable[[object], object] | None:
    if validator is None:
        return None
    validate = getattr(validator, "validate", None)
    if not callable(validate):
        raise TypeError("plugin Config must expose callable validate(value)")
    return cast(Callable[[object], object], validate)


def _validate_config(validate: Callable[[object], object] | None, value: object) -> object:
    if validate is None:
        return value
    result = validate(value)
    if inspect.isawaitable(result):
        if inspect.iscoroutine(result):
            result.close()
        raise TypeError("Async config validation is not supported")
    return result
