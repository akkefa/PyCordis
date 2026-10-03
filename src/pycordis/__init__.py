"""A Python plugin runtime developed in reviewed, incremental phases."""

from __future__ import annotations

from .context import Context
from .effects import Effect, EffectMeta
from .errors import CordisError
from .events import Events, is_bailed
from .fiber import Fiber, FiberState
from .metadata import PluginMeta, PluginSpec, inspect_plugin, plugin_meta
from .registry import PluginRuntime, Registry
from .scope import ScopeLabel, current_context
from .service import Service

__all__ = [
    "Context",
    "CordisError",
    "Effect",
    "EffectMeta",
    "Events",
    "Fiber",
    "FiberState",
    "PluginMeta",
    "PluginSpec",
    "inspect_plugin",
    "plugin_meta",
    "PluginRuntime",
    "Registry",
    "Service",
    "ScopeLabel",
    "current_context",
    "is_bailed",
]
