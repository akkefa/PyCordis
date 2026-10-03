"""Explicit immutable plugin declarations, separate from executable identity."""

from __future__ import annotations

import inspect
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import TypeVar, cast

from .services import _name, normalize_inject

T = TypeVar("T")
_MARKER = "__pycordis_meta__"


@dataclass(frozen=True, init=False)
class PluginMeta:
    """Copied declaration snapshot; config/provide/intercept do not execute hooks.

    inject drives reactive mounting. provide/intercept are descriptive declarations.
    config is a synchronous validator reference, applied before each activation.
    """

    name: str | None
    inject: Mapping[str, Mapping[str, object] | None]
    provide: tuple[str, ...]
    intercept: Mapping[str, bool]
    config: object

    def __init__(
        self,
        *,
        name: str | None = None,
        inject: object = None,
        provide: str | list[str] | tuple[str, ...] | None = None,
        intercept: Mapping[str, bool] | None = None,
        config: object = None,
    ) -> None:
        if name is not None and not isinstance(name, str):
            raise TypeError("plugin name must be a string")
        if provide is None:
            provided: tuple[str, ...] = ()
        elif isinstance(provide, str):
            provided = (_name(provide),)
        elif isinstance(provide, (list, tuple)):
            provided = tuple(dict.fromkeys(_name(item) for item in provide))
        else:
            raise TypeError("provide must be a service name or list/tuple of names")
        if intercept is not None and (
            not isinstance(intercept, Mapping)
            or any(not isinstance(value, bool) for value in intercept.values())
        ):
            raise TypeError("intercept declarations must be a name-to-bool mapping")
        intercepts = (
            {} if intercept is None else {_name(key): value for key, value in intercept.items()}
        )
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "inject", MappingProxyType(normalize_inject(inject)))
        object.__setattr__(self, "provide", provided)
        object.__setattr__(self, "intercept", MappingProxyType(intercepts))
        object.__setattr__(self, "config", config)


@dataclass(frozen=True)
class PluginSpec:
    """An explicit plugin/metadata pair, including for slotted callable objects."""

    plugin: object
    meta: PluginMeta

    def __post_init__(self) -> None:
        if not isinstance(self.meta, PluginMeta):
            raise TypeError("PluginSpec meta must be PluginMeta")
        if isinstance(self.plugin, PluginSpec):
            raise TypeError("nested PluginSpec wrappers are not supported")


def _resolve_callback(plugin: object) -> Callable[..., object] | None:
    if isinstance(plugin, PluginSpec):
        plugin = plugin.plugin
    try:
        if callable(plugin):
            return cast(Callable[..., object], plugin)
        callback = getattr(plugin, "apply", None)
        if callable(callback):
            return cast(Callable[..., object], callback)
    except Exception:
        pass
    return None


def inspect_plugin(plugin: object) -> PluginMeta:
    """Snapshot explicit metadata or conventional attrs without mounting/setup.

    A spec or decorator is an authoritative complete declaration. Otherwise
    normal Python attribute inheritance applies; method metadata is not scanned.
    """
    callback = _resolve_callback(plugin)
    if callback is None:
        raise TypeError("invalid plugin: expected a callable or an object with callable apply")
    return _inspect_meta(plugin, callback)


def _inspect_meta(plugin: object, callback: Callable[..., object]) -> PluginMeta:
    explicit = plugin.meta if isinstance(plugin, PluginSpec) else getattr(plugin, _MARKER, None)
    if explicit is not None and not isinstance(explicit, PluginMeta):
        raise TypeError("explicit plugin declaration must be PluginMeta")
    if isinstance(explicit, PluginMeta):
        name = explicit.name
        if name is None:
            name = getattr(callback, "__name__", None)
        return PluginMeta(
            name=None if name in ("apply", "<lambda>") else name,
            inject=explicit.inject,
            provide=explicit.provide,
            intercept=explicit.intercept,
            config=explicit.config,
        )
    name = getattr(plugin, "name", None)
    if name is None:
        name = getattr(callback, "__name__", None)
    provided = getattr(plugin, "provide", None)
    if provided is None and inspect.isclass(plugin):
        from .service import Service

        binding_name = getattr(plugin, "name", None)
        if issubclass(plugin, Service) and isinstance(binding_name, str) and binding_name:
            provided = binding_name
    return PluginMeta(
        name=None if name in ("apply", "<lambda>") else name,
        inject=getattr(plugin, "inject", None),
        provide=provided,
        intercept=getattr(plugin, "intercept", None),
        config=getattr(plugin, "Config", None),
    )


def plugin_meta(meta: PluginMeta) -> Callable[[T], T]:
    """Attach a full declaration without wrapping/replacing the plugin object.

    This declares plugins; it does not schedule annotated instance methods.
    Use PluginSpec when the plugin does not allow attribute assignment.
    """
    if not isinstance(meta, PluginMeta):
        raise TypeError("plugin_meta requires PluginMeta")

    def decorate(plugin: T) -> T:
        if _resolve_callback(plugin) is None or isinstance(plugin, PluginSpec):
            raise TypeError("plugin_meta requires an executable plugin, not a PluginSpec")
        setattr(plugin, _MARKER, meta)
        return plugin

    return decorate
