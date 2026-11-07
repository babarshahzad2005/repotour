from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner, Result

from repotour.cli import app
from repotour.git import reader
from repotour.pipeline import build_tour
from tests.fixtures.builder import FixtureRepo
from tests.fixtures.repos import minimal

runner = CliRunner()


def invoke(*args: str) -> Result:
    return runner.invoke(app, list(args))


def test_not_a_git_repository_exits_1(tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()

    result = invoke(str(plain))

    assert result.exit_code == 1
    assert "not inside a git repository" in result.output
    assert not (plain / "TOUR.md").exists()


def test_missing_path_exits_1(tmp_path: Path) -> None:
    result = invoke(str(tmp_path / "does-not-exist"))

    assert result.exit_code == 1
    assert "is not a directory" in result.output


def test_repository_without_commits_exits_1(tmp_path: Path) -> None:
    repo = FixtureRepo.create(tmp_path, "empty")

    result = invoke(str(repo.root))

    assert result.exit_code == 1
    assert "repository has no commits" in result.output


def test_missing_git_exits_1(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = minimal(tmp_path)
    monkeypatch.setattr(reader, "GIT_EXECUTABLE", "git-that-does-not-exist")

    result = invoke(str(repo.root))

    assert result.exit_code == 1
    assert "git is not installed" in result.output


def test_old_git_exits_1_naming_both_versions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = minimal(tmp_path)
    monkeypatch.setattr(reader, "git_version", lambda: (2, 29, 2))

    result = invoke(str(repo.root))

    assert result.exit_code == 1
    assert "2.29.2" in result.output
    assert "2.30" in result.output


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("git version 2.54.0.windows.1", (2, 54, 0)),
        ("git version 2.39.5 (Apple Git-154)", (2, 39, 5)),
        ("git version 2.30.0", (2, 30, 0)),
        ("git version 2.45", (2, 45, 0)),
    ],
)
def test_parse_git_version(raw: str, expected: tuple[int, int, int]) -> None:
    assert reader.parse_git_version(raw) == expected


def test_subdirectory_path_tours_the_whole_repository(tmp_path: Path) -> None:
    repo = minimal(tmp_path)

    result = invoke(str(repo.root / "app"))

    assert result.exit_code == 0, result.output
    assert (repo.root / "TOUR.md").exists()
    assert not (repo.root / "app" / "TOUR.md").exists()


def test_shallow_clone_produces_tour_with_history_truncated_warning(tmp_path: Path) -> None:
    clone = minimal(tmp_path).shallow_clone("shallow")

    result = invoke(str(clone.root))

    assert result.exit_code == 0, result.output
    assert "1 warning" in result.output
    warnings = build_tour(clone.root).tour.warnings
    assert len(warnings) == 1
    assert "history truncated" in warnings[0].lower()


def test_full_clone_has_no_warnings(tmp_path: Path) -> None:
    assert build_tour(minimal(tmp_path).root).tour.warnings == ()


def test_uncommitted_changes_are_ignored_and_mentioned(tmp_path: Path) -> None:
    repo = minimal(tmp_path)
    clean = invoke(str(repo.root))
    clean_tour = (repo.root / "TOUR.md").read_bytes()
    (repo.root / "app" / "main.py").write_text("changed but not committed\n", encoding="utf-8")

    dirty = invoke(str(repo.root))

    assert dirty.exit_code == 0, dirty.output
    assert (repo.root / "TOUR.md").read_bytes() == clean_tour
    assert "uncommitted changes" in dirty.output
    assert "uncommitted changes" not in clean.output
