"""Named service instances registered through existing Fiber-owned effects."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

from .scope import current_context
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
        declared = type(self).name if name is None else name
        if name is None and not declared:
            from .metadata import inspect_plugin

            meta = (
                ctx.fiber.plugin_meta
                if ctx.fiber.runtime is not None and ctx.fiber.runtime.callback is type(self)
                else inspect_plugin(type(self))
            )
            if meta is None or len(meta.provide) != 1:
                raise TypeError(
                    "service names must be nonempty strings; "
                    "Service needs one declared provide name or an explicit name"
                )
            declared = meta.provide[0]
        self.name = _name(declared)
        self._binding_name = self.name
        self._binding_label = ctx.service_scope(self.name)
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

    def matches_scope(self, ctx: Context) -> bool:
        """Filter listeners/callers to this implementation's service label."""
        return (
            ctx.root is self.ctx.root
            and ctx.service_scope(self._binding_name) is self._binding_label
        )

    def resolve_config(
        self,
        base: Mapping[str, object] | None = None,
        head: Mapping[str, object] | None = None,
        *,
        ctx: Context | None = None,
    ) -> dict[str, object]:
        """Resolve caller intercepts explicitly or from the current ContextVar."""
        caller = ctx if ctx is not None else current_context() or self.ctx
        if not self.matches_scope(caller):
            raise ValueError("service config caller belongs to another service scope")
        return self.merge_config(*caller._config_layers(self._binding_name, base, head))

    @staticmethod
    def merge_config(*layers: Mapping[str, object]) -> dict[str, object]:
        """Override for service-specific merging; default is shallow ancestor-first."""
        result: dict[str, object] = {}
        for layer in layers:
            result.update(layer)
        return result
