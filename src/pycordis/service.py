"""Named service instances registered through existing Fiber-owned effects."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .services import _name

if TYPE_CHECKING:
    from .context import Context
    from .effects import Effect


class Service:
    """Base for service plugins mounted with Context.plugin.

    Subclasses declare a nonempty name and optionally override start/check.
    Constructors receive (ctx, config); custom constructors must call super.
    Direct construction registers immediately but does not invoke start.
    """

    name: str = ""

    def __init__(self, ctx: Context, config: object = None, *, name: str | None = None) -> None:
        self._ctx = ctx
        self._config = config
        self.name = _name(type(self).name if name is None else name)
        self._registration = ctx.provide(self.name, self, check=self.check)

    @property
    def ctx(self) -> Context:
        """Defining context and resource owner; never rebound to the caller."""
        return self._ctx

    @property
    def config(self) -> object:
        """Original mount config, passed by identity without validation."""
        return self._config

    @property
    def registration(self) -> Effect:
        """Owned binding handle; manual removal does not dispose the whole plugin."""
        return self._registration

    def start(self) -> object:
        """Optional post-construction setup; return supported effect results."""
        return None

    def check(self) -> bool:
        """Synchronous dependency availability predicate; strict get ignores it."""
        return True
