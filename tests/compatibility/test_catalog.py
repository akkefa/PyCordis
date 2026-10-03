"""Keep source provenance and Python evidence links from silently drifting."""

from __future__ import annotations

import ast
import json
import re
from collections import Counter
from pathlib import Path
from typing import TypedDict, cast

import pytest


class SourceFile(TypedDict):
    origin: str
    commit: str
    path: str
    sha256: str
    test_count: int


class SourceCase(TypedDict):
    id: str
    origin: str
    commit: str
    source_file: str
    source_line: int
    source_title: str
    classification: str
    coverage: str
    notes: str
    python_tests: list[str]


class Catalog(TypedDict):
    schema_version: int
    upstream_commit: str
    harness_commit: str
    scope: str
    source_files: list[SourceFile]
    cases: list[SourceCase]


@pytest.mark.compatibility
def test_source_catalog_provenance_and_python_evidence_stay_consistent() -> None:
    root = Path(__file__).resolve().parents[2]
    catalog = cast(Catalog, json.loads((root / "docs/compatibility-cases.json").read_text()))
    assert catalog["schema_version"] == 1
    commits = {"upstream": catalog["upstream_commit"], "harness": catalog["harness_commit"]}
    assert commits == {
        "upstream": "56b3d4f725681cf4556c1a8695a709cc3b6eed74",
        "harness": "639ed015397290b3745d163aafe02ffee4aa3f84",
    }
    source_files = {(entry["origin"], entry["path"]): entry for entry in catalog["source_files"]}
    assert len(source_files) == len(catalog["source_files"])
    definitions: set[str] = set()
    suite_definitions: set[str] = set()
    for path in (root / "tests").rglob("test_*.py"):
        tree = ast.parse(path.read_text())
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith(
                "test_"
            ):
                node_id = f"{path.relative_to(root).as_posix()}::{node.name}"
                definitions.add(node_id)
                if path.parent.name == "compatibility" and path.name != "test_catalog.py":
                    suite_definitions.add(node_id)
    ids: set[str] = set()
    source_titles: set[tuple[str, str, str]] = set()
    counts: Counter[tuple[str, str]] = Counter()
    evidence: set[str] = set()
    classifications = {
        "identical semantic behavior",
        "Python-specific adaptation",
        "not applicable in Python",
        "future work",
    }
    for case in catalog["cases"]:
        assert case["id"] not in ids
        ids.add(case["id"])
        title_key = (case["origin"], case["source_file"], case["source_title"])
        assert title_key not in source_titles
        source_titles.add(title_key)
        key = (case["origin"], case["source_file"])
        assert key in source_files
        assert case["commit"] == commits[case["origin"]] == source_files[key]["commit"]
        assert case["source_line"] > 0 and case["source_title"] and case["notes"]
        assert case["classification"] in classifications
        assert case["coverage"] in {"ported", "partial", "none"}
        if case["coverage"] == "none":
            assert not case["python_tests"]
        else:
            assert case["python_tests"]
        if case["classification"] == "future work":
            assert case["coverage"] != "ported"
        for node_id in case["python_tests"]:
            assert node_id in definitions, f"missing Python evidence: {node_id}"
            evidence.add(node_id)
        counts[key] += 1
    for key, source in source_files.items():
        assert re.fullmatch(r"[0-9a-f]{64}", source["sha256"])
        assert source["test_count"] == counts[key]
    assert suite_definitions <= evidence, "new behavioral ports must have pinned source evidence"
    assert sum(counts.values()) == len(catalog["cases"])
