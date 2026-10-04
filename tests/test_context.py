"""Context foundation: adapted from pinned Cordis context.ts/extend.

Harness reference: 639ed015397290b3745d163aafe02ffee4aa3f84.
Metadata behavior is a Python-specific adaptation of property inheritance;
plugin.spec.ts/nested plugins remains future lifecycle work.
"""

from __future__ import annotations

import asyncio
from collections import UserDict
from collections.abc import Mapping

import pytest

from deepseek_cordis import Context


def test_root_has_no_parent_and_owns_itself() -> None:
    ctx = Context()
    assert ctx.parent is None
    assert ctx.root is ctx
    assert ctx.owner is ctx
    assert dict(ctx.metadata) == {}


def test_independent_roots_do_not_share_ownership_or_metadata() -> None:
    first, second = Context(), Context()
    assert first.root is not second.root
    assert first.owner is not second.owner
    assert first.metadata is not second.metadata


def test_extension_is_a_distinct_child_with_shared_ownership() -> None:
    root = Context()
    child = root.extend({"label": "worker"})
    assert child is not root
    assert child.parent is root
    assert child.root is root
    assert child.owner is root.owner
    assert child.metadata["label"] == "worker"
    assert "label" not in root.metadata


def test_nested_extension_inherits_and_shadows_metadata() -> None:
    root = Context()
    parent = root.extend({"label": "parent", "shared": 1})
    child = parent.extend({"label": "child"})
    grandchild = child.extend({"extra": 2})
    assert grandchild.parent is child
    assert grandchild.root is root
    assert grandchild.owner is root
    assert dict(grandchild.metadata) == {"label": "child", "shared": 1, "extra": 2}
    assert dict(parent.metadata) == {"label": "parent", "shared": 1}


def test_sibling_metadata_is_independent() -> None:
    parent = Context().extend({"shared": "parent"})
    first = parent.extend({"local": 1})
    second = parent.extend({"local": 2})
    assert first.metadata["local"] == 1
    assert second.metadata["local"] == 2
    assert "local" not in parent.metadata
    assert first.owner is second.owner


@pytest.mark.parametrize("meta", [None, {}])
def test_empty_extension_keeps_inherited_metadata(meta: Mapping[str, object] | None) -> None:
    parent = Context().extend({"name": "parent"})
    child = parent.extend(meta)
    assert child is not parent
    assert child.parent is parent
    assert dict(child.metadata) == dict(parent.metadata)
    assert child.owner is parent.owner


def test_input_mapping_entries_are_copied() -> None:
    values: dict[str, object] = {"name": "original"}
    child = Context().extend(values)
    values["name"] = "changed"
    values["new"] = True
    assert dict(child.metadata) == {"name": "original"}


def test_arbitrary_mapping_implementation_is_accepted() -> None:
    values: UserDict[str, object] = UserDict({"name": "worker"})
    assert Context().extend(values).metadata["name"] == "worker"


def test_values_keep_identity_and_mutations_are_shared() -> None:
    resource: list[str] = []
    parent = Context().extend({"resource": resource})
    child = parent.extend()
    assert child.metadata["resource"] is resource
    resource.append("changed")
    assert parent.metadata["resource"] == ["changed"]
    assert child.metadata["resource"] == ["changed"]


def test_none_and_false_shadow_inherited_values() -> None:
    parent = Context().extend({"value": 1, "enabled": True})
    child = parent.extend({"value": None, "enabled": False})
    assert child.metadata["value"] is None
    assert child.metadata["enabled"] is False


def test_metadata_names_do_not_replace_context_members() -> None:
    root = Context()
    child = root.extend({"root": "metadata", "extend": "metadata", "_parent": "metadata"})
    assert child.root is root
    assert child.parent is root
    assert child.extend().parent is child
    assert child.metadata["root"] == "metadata"


def test_missing_metadata_raises_key_error() -> None:
    with pytest.raises(KeyError, match="missing"):
        _ = Context().extend().metadata["missing"]


def test_metadata_mapping_is_read_only() -> None:
    metadata = Context().extend({"value": 1}).metadata
    with pytest.raises(TypeError):
        metadata["value"] = 2  # type: ignore[index]
    with pytest.raises(TypeError):
        del metadata["value"]  # type: ignore[attr-defined]
    assert metadata["value"] == 1


@pytest.mark.parametrize("name", ["parent", "root", "owner", "metadata"])
def test_context_relationships_are_read_only(name: str) -> None:
    child = Context().extend()
    with pytest.raises(AttributeError):
        setattr(child, name, None)


def test_non_string_metadata_key_is_rejected() -> None:
    with pytest.raises(TypeError, match="keys must be strings"):
        Context().extend({1: "invalid"})  # type: ignore[dict-item]


@pytest.mark.parametrize("value", [[], "invalid", 1])
def test_non_mapping_metadata_is_rejected(value: object) -> None:
    with pytest.raises(TypeError, match="must be a mapping"):
        Context().extend(value)  # type: ignore[arg-type]


def test_extension_preserves_subclass_without_reinitializing_it() -> None:
    calls: list[Context] = []

    class CustomContext(Context):
        def __init__(self) -> None:
            super().__init__()
            calls.append(self)

    root = CustomContext()
    child = root.extend({"label": "child"})
    assert isinstance(child, CustomContext)
    assert calls == [root]
    assert child.root is root


@pytest.mark.asyncio
async def test_concurrent_extensions_keep_explicit_scope_and_owner() -> None:
    root = Context()

    async def extend(label: str) -> Context:
        child = root.extend({"label": label})
        await asyncio.sleep(0)
        return child.extend()

    first, second = await asyncio.gather(extend("first"), extend("second"))
    assert first.metadata["label"] == "first"
    assert second.metadata["label"] == "second"
    assert first.root is second.root is root
    assert first.owner is second.owner is root
    assert dict(root.metadata) == {}
