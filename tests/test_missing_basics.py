from __future__ import annotations

import itertools
from pathlib import Path

import pytest

from repotour.model.tour import Overview
from repotour.pipeline import build_tour
from tests.fixtures.builder import FixtureRepo

_counter = itertools.count()

COMPLETE: dict[str, str | bytes | None] = {
    "README.md": "# project\n",
    "CONTRIBUTING.md": "How to contribute.\n",
    "LICENSE": "MIT\n",
    ".github/workflows/ci.yml": "on: [push]\n",
    "src/app.py": "x = 1\n",
    "tests/test_app.py": "def test(): pass\n",
}


def missing_for(tmp_path: Path, files: dict[str, str | bytes | None]) -> list[str]:
    repo = FixtureRepo.create(tmp_path, f"basics{next(_counter)}")
    repo.commit("Add project", files)
    overview = build_tour(repo.root, use_cache=False).tour.overview
    assert isinstance(overview, Overview)
    return [m.item for m in overview.missing]


def test_complete_repository_has_no_flags(tmp_path: Path) -> None:
    assert missing_for(tmp_path, COMPLETE) == []


@pytest.mark.parametrize(
    ("remove", "item"),
    [
        ("README.md", "README"),
        ("CONTRIBUTING.md", "contributing guide"),
        ("LICENSE", "license"),
        (".github/workflows/ci.yml", "CI configuration"),
        ("tests/test_app.py", "tests"),
    ],
)
def test_each_missing_item_is_flagged(tmp_path: Path, remove: str, item: str) -> None:
    files = {k: v for k, v in COMPLETE.items() if k != remove}

    assert missing_for(tmp_path, files) == [item]


@pytest.mark.parametrize(
    "path",
    [
        "readme.rst",
        "README",
    ],
)
def test_readme_variants(tmp_path: Path, path: str) -> None:
    files = {k: v for k, v in COMPLETE.items() if k != "README.md"} | {path: "hi\n"}

    assert "README" not in missing_for(tmp_path, files)


@pytest.mark.parametrize(
    "path",
    [".github/CONTRIBUTING.md", "docs/CONTRIBUTING.rst", "CONTRIBUTING"],
)
def test_contributing_locations(tmp_path: Path, path: str) -> None:
    files = {k: v for k, v in COMPLETE.items() if k != "CONTRIBUTING.md"} | {path: "x\n"}

    assert "contributing guide" not in missing_for(tmp_path, files)


@pytest.mark.parametrize("path", ["LICENSE.txt", "LICENCE", "COPYING", "LICENSE-MIT"])
def test_license_variants(tmp_path: Path, path: str) -> None:
    files = {k: v for k, v in COMPLETE.items() if k != "LICENSE"} | {path: "x\n"}

    assert "license" not in missing_for(tmp_path, files)


@pytest.mark.parametrize(
    "path",
    [".gitlab-ci.yml", ".circleci/config.yml", "Jenkinsfile", "azure-pipelines.yml"],
)
def test_ci_variants(tmp_path: Path, path: str) -> None:
    files = {k: v for k, v in COMPLETE.items() if k != ".github/workflows/ci.yml"} | {path: "x\n"}

    assert "CI configuration" not in missing_for(tmp_path, files)


def test_flags_say_what_was_looked_for(tmp_path: Path) -> None:
    repo = FixtureRepo.create(tmp_path, "bare")
    repo.commit("Add", {"main.c": "int main(){}\n"})

    overview = build_tour(repo.root, use_cache=False).tour.overview
    assert isinstance(overview, Overview)

    assert [m.item for m in overview.missing] == [
        "README",
        "tests",
        "contributing guide",
        "license",
        "CI configuration",
    ]
    assert all(m.evidence and m.evidence[0].detail for m in overview.missing)
