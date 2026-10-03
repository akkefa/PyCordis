"""Identity labels, immutable intercept entries and task-local caller contexts."""

from __future__ import annotations

from collections.abc import Mapping
from contextvars import ContextVar
from types import MappingProxyType
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .context import Context


class ScopeLabel:
    """Opaque identity token; reuse one token to join a service's scope."""

    __slots__ = ()


_current_context: ContextVar[Context | None] = ContextVar("pycordis_context", default=None)


def current_context() -> Context | None:
    """Return the active task-local caller, or None outside a scoped operation."""
    return _current_context.get()


def _config(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise TypeError("intercept config must be a mapping with string keys")
    return MappingProxyType(dict(value))
