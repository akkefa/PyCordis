"""Deterministic explicit loading, separate from the kernel and file formats."""

from __future__ import annotations

import asyncio
import importlib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType

from .config import _resolve_validator
from .context import Context
from .fiber import Fiber, FiberState
from .metadata import PluginSpec, inspect_plugin


@dataclass(frozen=True)
class PluginEntry:
    """One ordered entry; config is retained by identity, not serialized/copied."""

    id: str
    plugin: object
    config: object = None
    enabled: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id.strip():
            raise TypeError("plugin entry id must be a nonempty string")
        if not isinstance(self.enabled, bool):
            raise TypeError("plugin entry enabled must be a bool")

    @classmethod
    def from_mapping(cls, row: Mapping[str, object]) -> PluginEntry:
        if not isinstance(row, Mapping):
            raise TypeError("plugin entry must be a mapping")
        if set(row) - {"id", "plugin", "config", "enabled"}:
            raise TypeError("unknown plugin entry fields")
        if "id" not in row or "plugin" not in row:
            raise TypeError("plugin entry requires id and plugin")
        entry_id = row["id"]
        enabled = row.get("enabled", True)
        if not isinstance(entry_id, str) or not isinstance(enabled, bool):
            raise TypeError("plugin entry requires string id and bool enabled")
        return cls(entry_id, row["plugin"], row.get("config"), enabled)


def resolve_plugin(reference: object) -> object:
    """Import module[:attribute.path], or preserve a supplied plugin object.

    Bare modules must export apply (and may export conventional metadata).
    This uses normal Python imports; it does not modify sys.path or reload modules.
    """
    if not isinstance(reference, str):
        return reference
    module_name, separator, attribute = reference.partition(":")
    if not module_name or any(not part.isidentifier() for part in module_name.split(".")):
        raise ValueError("plugin reference must use an absolute Python module name")
    if separator and (
        not attribute or any(not part.isidentifier() for part in attribute.split("."))
    ):
        raise ValueError("plugin reference attribute must be a dotted Python name")
    plugin: object = importlib.import_module(module_name)
    if separator:
        for part in attribute.split("."):
            plugin = getattr(plugin, part)
    return plugin


class LoadedPlugins:
    """A batch's actual owner Fiber and read-only id-to-Fiber inspection."""

    def __init__(self, owner: Fiber, fibers: Mapping[str, Fiber]) -> None:
        self._owner = owner
        self._fibers = MappingProxyType(dict(fibers))

    @property
    def owner(self) -> Fiber:
        return self._owner

    @property
    def fibers(self) -> Mapping[str, Fiber]:
        return self._fibers

    async def dispose(self) -> None:
        """Dispose only this batch and join its owned cleanup; safe to repeat."""
        await self.owner.dispose()


def _batch(ctx: Context, config: object) -> None:
    """A dedicated structural owner, with no loader service or event hooks."""


async def _wait(fiber: Fiber) -> None:
    await fiber


async def _settle(fibers: tuple[Fiber, ...]) -> None:
    # Consumers visited early can be activated by providers visited later.
    # Revisit until no lifecycle work remains, without waiting for absent services.
    while True:
        waiters = [asyncio.create_task(_wait(fiber)) for fiber in fibers]
        try:
            await asyncio.gather(*waiters)
        finally:
            for waiter in waiters:
                if not waiter.done():
                    waiter.cancel()
            await asyncio.gather(*waiters, return_exceptions=True)
        # A consumer that was PENDING on its first visit may already have failed
        # after a later provider activated it. Check stable failures before return.
        for fiber in fibers:
            error = fiber.error
            if error is not None:
                raise error
        if all(fiber.state not in (FiberState.LOADING, FiberState.UNLOADING) for fiber in fibers):
            return


class Loader:
    """Load ordered batches beneath the supplied Context view.

    Imports/declarations are preflighted before any mount. Each batch has its own
    owner; failure/cancellation drains that batch without disposing other work.
    """

    def __init__(self, ctx: Context) -> None:
        self._ctx = ctx

    @property
    def ctx(self) -> Context:
        return self._ctx

    async def load_config(self, rows: Iterable[Mapping[str, object]]) -> LoadedPlugins:
        """Parse explicit rows; no file reading, expressions or discovery."""
        return await self.load(PluginEntry.from_mapping(row) for row in rows)

    async def load(self, entries: Iterable[PluginEntry]) -> LoadedPlugins:
        """Mount in input order, then settle; unavailable consumers remain PENDING."""
        snapshot = tuple(entries)
        ids: set[str] = set()
        for entry in snapshot:
            if not isinstance(entry, PluginEntry):
                raise TypeError("loader entries must be PluginEntry objects")
            if entry.id in ids:
                raise ValueError(f"duplicate plugin entry id: {entry.id}")
            ids.add(entry.id)
        resolved: list[tuple[PluginEntry, PluginSpec]] = []
        for entry in snapshot:
            if not entry.enabled:
                continue
            plugin = resolve_plugin(entry.plugin)
            meta = inspect_plugin(plugin)
            _resolve_validator(meta.config)
            resolved.append(
                (
                    entry,
                    PluginSpec(plugin.plugin if isinstance(plugin, PluginSpec) else plugin, meta),
                )
            )
        owner = self.ctx.plugin(_batch)
        mounted: dict[str, Fiber] = {}
        try:
            # Complete synchronous mounting before any plugin begins setup.
            for entry, plugin in resolved:
                mounted[entry.id] = owner.ctx.plugin(plugin, entry.config)
            await owner
            await _settle(tuple(mounted.values()))
            if owner.uid is None:
                raise RuntimeError("loader batch owner was disposed during loading")
            return LoadedPlugins(owner, mounted)
        except BaseException:
            await owner.dispose()
            raise
