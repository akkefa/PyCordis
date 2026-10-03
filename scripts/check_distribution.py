"""Audit the exact local wheel/sdist pair; uses only the Python standard library."""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import io
import json
import tarfile
import tomllib
import zipfile
from email import policy
from email.parser import BytesParser
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlsplit


def check_metadata(data: bytes, project: dict[str, Any], readme: str) -> None:
    metadata = BytesParser(policy=policy.default).parsebytes(data)
    assert str(metadata["Metadata-Version"]) == "2.4"
    for field, key in [
        ("Name", "name"),
        ("Version", "version"),
        ("Summary", "description"),
        ("Requires-Python", "requires-python"),
        ("License-Expression", "license"),
    ]:
        assert str(metadata[field]) == project[key], f"incorrect {field}"
    assert str(metadata["Author"]) == project["authors"][0]["name"]
    assert str(metadata["Description-Content-Type"]) == "text/markdown"
    payload = metadata.get_payload(decode=True)
    assert isinstance(payload, bytes) and payload.decode().strip() == readme.strip(), (
        "long description differs"
    )
    assert set(metadata.get_all("License-File", [])) == set(project["license-files"])
    assert set(metadata.get_all("Classifier", [])) == set(project["classifiers"])
    assert not metadata.get_all("Requires-Dist"), "unexpected runtime dependency"
    assert not metadata.get_all("Provides-Extra"), "unexpected adapter extra"
    urls = dict(str(value).split(", ", 1) for value in metadata.get_all("Project-URL", []))
    assert urls == project["urls"], "project URLs differ"
    for url in urls.values():
        parsed = urlsplit(url)
        assert parsed.scheme == "https" and parsed.hostname
        assert parsed.username is None and parsed.password is None, "credentials in project URL"


def check_distributions(wheel: Path, sdist: Path, root: Path) -> dict[str, object]:
    with (root / "pyproject.toml").open("rb") as config_file:
        project = tomllib.load(config_file)["project"]
    assert project["dependencies"] == [] and project.get("optional-dependencies", {}) == {}
    name, version = project["name"], project["version"]
    dist_info = f"{name}-{version}.dist-info"
    readme = (root / project["readme"]).read_text()
    sources = {
        path.relative_to(root / "src").as_posix(): path.read_bytes()
        for path in (root / "src" / name).rglob("*")
        if path.is_file() and (path.suffix == ".py" or path.name == "py.typed")
    }
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        assert len(names) == len(set(names)), "duplicate wheel member"
        allowed = {
            *sources,
            f"{dist_info}/METADATA",
            f"{dist_info}/WHEEL",
            f"{dist_info}/RECORD",
            *(f"{dist_info}/licenses/{file}" for file in project["license-files"]),
        }
        assert set(names) == allowed, "wheel has missing or unexpected contents"
        for path, data in sources.items():
            assert archive.read(path) == data, f"wheel source mismatch: {path}"
        assert f"{name}/py.typed" in names
        for file in project["license-files"]:
            assert archive.read(f"{dist_info}/licenses/{file}") == (root / file).read_bytes()
        check_metadata(archive.read(f"{dist_info}/METADATA"), project, readme)
        wheel_meta = BytesParser(policy=policy.default).parsebytes(
            archive.read(f"{dist_info}/WHEEL")
        )
        assert str(wheel_meta["Root-Is-Purelib"]) == "true"
        assert wheel_meta.get_all("Tag") == ["py3-none-any"]
        rows = list(csv.reader(io.StringIO(archive.read(f"{dist_info}/RECORD").decode())))
        assert len(rows) == len(names) and {row[0] for row in rows} == set(names)
        for path, digest, size in rows:
            if path.endswith("/RECORD"):
                assert digest == size == ""
                continue
            data = archive.read(path)
            expected = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode().rstrip("=")
            assert digest == f"sha256={expected}" and int(size) == len(data), f"bad RECORD: {path}"
    prefix = f"{name}-{version}"
    with tarfile.open(sdist, "r:gz") as archive:
        members = archive.getmembers()
        names = [member.name for member in members]
        assert len(names) == len(set(names)), "duplicate sdist member"
        for member in members:
            path = PurePosixPath(member.name)
            assert not path.is_absolute() and ".." not in path.parts
            assert path.parts[0] == prefix and (member.isfile() or member.isdir())
            assert not set(path.parts) & {".git", ".venv", "__pycache__", "dist", ".env"}
        expected_files = {
            path.relative_to(root).as_posix(): path.read_bytes()
            for folder in ["src", "tests", "docs", "examples", "scripts"]
            for path in (root / folder).rglob("*")
            if path.is_file()
            and not any(
                part.startswith(".") or part == "__pycache__"
                for part in path.relative_to(root).parts
            )
            and path.suffix != ".pyc"
        }
        for file in [
            ".gitignore",
            "pyproject.toml",
            "uv.lock",
            "README.md",
            "README.pypi.md",
            "CHANGELOG.md",
            "CONTRIBUTING.md",
            "LICENSE",
            "THIRD_PARTY_NOTICES.md",
        ]:
            expected_files[file] = (root / file).read_bytes()
        actual_files = {
            member.name.removeprefix(f"{prefix}/") for member in members if member.isfile()
        }
        assert actual_files == {*expected_files, "PKG-INFO"}, "source archive contents differ"
        for path, data in expected_files.items():
            stream = archive.extractfile(f"{prefix}/{path}")
            assert stream is not None and stream.read() == data, f"source archive mismatch: {path}"
        stream = archive.extractfile(f"{prefix}/PKG-INFO")
        assert stream is not None
        check_metadata(stream.read(), project, readme)
    return {
        "name": name,
        "version": version,
        "wheel_files": len(allowed),
        "sdist_files": len(actual_files),
        "runtime_dependencies": [],
        "artifacts": {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in [wheel, sdist]
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path)
    parser.add_argument("sdist", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    print(json.dumps(check_distributions(args.wheel, args.sdist, root), indent=2))


if __name__ == "__main__":
    main()
