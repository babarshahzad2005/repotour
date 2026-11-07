from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from repotour.cli import app
from repotour.model.tour import Overview
from repotour.pipeline import build_tour
from tests.conftest import GoldenCheck
from tests.fixtures.repos import polyglot


def overview_of(root: Path) -> Overview:
    overview = build_tour(root).tour.overview
    assert overview is not None
    return overview


def test_languages_sorted_by_lines_then_name(tmp_path: Path) -> None:
    overview = overview_of(polyglot(tmp_path).root)

    assert [(s.language, s.files, s.lines) for s in overview.languages] == [
        ("Go", 2, 5),
        ("JavaScript", 1, 3),
        ("TypeScript", 1, 2),
        ("Python", 2, 1),
    ]


def test_each_language_cites_its_largest_files(tmp_path: Path) -> None:
    overview = overview_of(polyglot(tmp_path).root)
    go = overview.languages[0]

    assert [e.ref for e in go.evidence] == ["server/main.go", "server/util.go"]
    assert all(e.kind == "file" for e in go.evidence)


def test_size_counts_files_and_lines_of_code(tmp_path: Path) -> None:
    repo = polyglot(tmp_path)
    overview = overview_of(repo.root)

    assert overview.size.files == 9
    assert overview.size.lines_of_code == 11
    assert overview.size.evidence[0].kind == "commit_range"


def test_overview_golden(tmp_path: Path, golden: GoldenCheck) -> None:
    repo = polyglot(tmp_path)

    result = CliRunner().invoke(app, [str(repo.root)])

    assert result.exit_code == 0, result.output
    golden("polyglot", (repo.root / "TOUR.md").read_bytes().decode("utf-8"))
