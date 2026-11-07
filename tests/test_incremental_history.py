from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from repotour.cache import history as history_cache
from repotour.cli import app
from repotour.git import reader
from tests.fixtures.repos import history

runner = CliRunner()


class Spy:
    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.full: list[str] = []
        self.ranges: list[tuple[str, str]] = []
        full, ranged = reader.read_history, reader.read_history_range

        def spy_full(root: Path, head: str):  # type: ignore[no-untyped-def]
            self.full.append(head)
            return full(root, head)

        def spy_range(root: Path, base: str, head: str):  # type: ignore[no-untyped-def]
            self.ranges.append((base, head))
            return ranged(root, base, head)

        monkeypatch.setattr(reader, "read_history", spy_full)
        monkeypatch.setattr(reader, "read_history_range", spy_range)


def tour(root: Path, *args: str) -> bytes:
    result = runner.invoke(app, [str(root), "--force", *args])
    assert result.exit_code == 0, result.output
    return (root / "TOUR.md").read_bytes()


def head(root: Path) -> str:
    return reader.repo_info(root).head_commit


def test_new_commits_are_read_incrementally(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = history(tmp_path)
    tour(repo.root)
    old_head = head(repo.root)
    repo.commit("More core", {"app/core.py": "v = 99\n"}, date="2025-01-05T10:00:00+00:00")

    spy = Spy(monkeypatch)
    tour(repo.root)

    assert spy.full == []
    assert spy.ranges == [(old_head, head(repo.root))]


def test_incremental_output_matches_a_cold_run(tmp_path: Path) -> None:
    repo = history(tmp_path)
    tour(repo.root)
    repo.branch("late")
    repo.commit("Backdated branch work", {"app/late.py": "x\n"}, date="2024-12-01T10:00:00+00:00")
    repo.switch("main")
    repo.commit("Main work", {"app/core.py": "v = 100\n"}, date="2025-01-02T10:00:00+00:00")
    repo.merge("late", "Merge late", date="2025-01-03T10:00:00+00:00")

    incremental = tour(repo.root)
    cold = tour(repo.root, "--no-cache")

    assert incremental == cold


def test_rewritten_history_is_read_in_full(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = history(tmp_path)
    repo.commit("Doomed", {"app/core.py": "doomed\n"}, date="2025-01-05T10:00:00+00:00")
    tour(repo.root)
    subprocess.run(["git", "reset", "--quiet", "--hard", "HEAD~1"], cwd=repo.root, check=True)
    repo.commit("Replacement", {"app/util.py": "replaced\n"}, date="2025-01-06T10:00:00+00:00")

    spy = Spy(monkeypatch)
    incremental = tour(repo.root)

    assert spy.full == [head(repo.root)]
    assert incremental == tour(repo.root, "--no-cache")


def test_changing_since_never_rereads_git(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = history(tmp_path)
    tour(repo.root)

    spy = Spy(monkeypatch)
    tour(repo.root, "--since", "1y")
    tour(repo.root, "--since", "3m")

    assert spy.full == []
    assert spy.ranges == []


def test_no_cache_reads_in_full_every_time(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = history(tmp_path)
    tour(repo.root)

    spy = Spy(monkeypatch)
    tour(repo.root, "--no-cache", "--since", "1y")

    assert spy.full == [head(repo.root)]


def test_history_is_in_canonical_order(tmp_path: Path) -> None:
    repo = history(tmp_path)

    records = history_cache.load_history(repo.root, head(repo.root), None)

    keys = [(-r.timestamp, r.sha) for r in records]
    assert keys == sorted(keys)
