from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from repotour.analyzers.directories import first_sentence
from repotour.cli import app
from repotour.model.tour import DirectoryPurpose, Overview
from repotour.pipeline import build_tour
from tests.conftest import GoldenCheck
from tests.fixtures.builder import FixtureRepo

CONFIG = """\
version: 1
notes:
  scripts: Release and maintenance helpers; run from the repo root.
  src/core/engine.py: The heart of the system. Read this first.
  gone/: This directory was removed.
"""


@pytest.fixture(scope="module")
def repo_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    repo = FixtureRepo.create(tmp_path_factory.mktemp("dirs"), "dirs")
    repo.commit(
        "Add project",
        {
            ".repotour.yml": CONFIG,
            "README.md": "# dirs\n",
            "src/core/engine.py": "x = 1\n",
            "src/util.py": "y = 2\n",
            "plugins/README.md": (
                "# Plugins\n\n[![ci](https://x/badge.svg)](https://x)\n\n"
                "Optional **extensions** loaded at startup. See [the guide](docs.md) for more.\n"
            ),
            "plugins/auth.py": "pass\n",
            "scripts/release.sh": "echo release\n",
            "tests/test_util.py": "def test(): pass\n",
            "zebra/a.go": "package zebra\n",
            "zebra/b.go": "package zebra\n",
            "zebra/notes.md": "notes\n",
            "vendor/lib.go": "package lib\n",
        },
    )
    return repo.root


@pytest.fixture(scope="module")
def overview(repo_root: Path) -> Overview:
    result = build_tour(repo_root, use_cache=False).tour.overview
    assert result is not None
    return result


def purpose(overview: Overview, path: str) -> DirectoryPurpose:
    return next(d for d in overview.directories if d.path == path)


def test_lists_top_level_directories_sorted(overview: Overview) -> None:
    assert [d.path for d in overview.directories] == [
        "plugins",
        "scripts",
        "src",
        "tests",
        "vendor",
        "zebra",
    ]


def test_config_note_wins(overview: Overview) -> None:
    scripts = purpose(overview, "scripts")

    assert scripts.purpose == "Release and maintenance helpers; run from the repo root."
    assert scripts.evidence[0].kind == "config"
    assert scripts.evidence[0].ref == ".repotour.yml"


def test_readme_first_sentence(overview: Overview) -> None:
    plugins = purpose(overview, "plugins")

    assert plugins.purpose == "Optional extensions loaded at startup."
    assert plugins.evidence[0].ref == "plugins/README.md"


def test_well_known_name(overview: Overview) -> None:
    src = purpose(overview, "src")

    assert src.purpose == "Source code"
    assert src.evidence[0].detail == "well-known directory name"


def test_category_summary_fallback(overview: Overview) -> None:
    zebra = purpose(overview, "zebra")

    assert zebra.purpose == "3 files: 2 source (Go), 1 docs"
    assert zebra.evidence[0].ref == "zebra/"


def test_notes_on_other_paths_render_with_config_evidence(overview: Overview) -> None:
    assert [(n.path, n.text) for n in overview.notes] == [
        ("src/core/engine.py", "The heart of the system. Read this first."),
    ]
    assert overview.notes[0].evidence[0].kind == "config"


def test_stale_note_warns(repo_root: Path) -> None:
    warnings = build_tour(repo_root, use_cache=False).tour.warnings

    assert warnings == (".repotour.yml: note for 'gone/' points to a path that does not exist",)


@pytest.mark.parametrize(
    ("markdown", "expected"),
    [
        ("# Title\n\nDoes one thing. Then more.\n", "Does one thing."),
        ("Plain text without a period", "Plain text without a period"),
        ("<p align='center'><img src='x'></p>\n\nHello there.\n", "Hello there."),
        ("# Only a heading\n", None),
        ("", None),
        ("Use `pip install x` e.g. for setup. Next.\n", "Use pip install x e.g. for setup."),
        ("A " + "very " * 40 + "long line.\n", ("A " + "very " * 40)[:115].rstrip() + "…"),
    ],
)
def test_first_sentence(markdown: str, expected: str | None) -> None:
    assert first_sentence(markdown) == expected


def test_directories_golden(repo_root: Path, golden: GoldenCheck) -> None:
    result = CliRunner().invoke(app, [str(repo_root), "--force"])

    assert result.exit_code == 0, result.output
    golden("directories", (repo_root / "TOUR.md").read_bytes().decode("utf-8"))
