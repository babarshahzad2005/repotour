from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner, Result

from repotour import pipeline
from repotour.analyzers.overview import OverviewAnalyzer
from repotour.cache.store import CACHE_DIR_NAME
from repotour.cli import app
from tests.fixtures.repos import minimal

runner = CliRunner()


def invoke(*args: str) -> Result:
    result = runner.invoke(app, list(args))
    assert result.exit_code == 0, result.output
    return result


def cache_dir(root: Path) -> Path:
    return root / ".git" / CACHE_DIR_NAME


class Calls:
    def __init__(self) -> None:
        self.count = 0


@pytest.fixture
def overview_calls(monkeypatch: pytest.MonkeyPatch) -> Calls:
    calls = Calls()
    original = OverviewAnalyzer.run

    def counting(self, snapshot, inputs):  # type: ignore[no-untyped-def]
        calls.count += 1
        return original(self, snapshot, inputs)

    monkeypatch.setattr(OverviewAnalyzer, "run", counting)
    return calls


def test_cache_lives_in_git_dir_and_keeps_status_clean(tmp_path: Path) -> None:
    repo = minimal(tmp_path)

    invoke(str(repo.root))

    assert (cache_dir(repo.root) / "cache.sqlite3").exists()
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=repo.root, capture_output=True, text=True, check=True
    ).stdout
    assert status.strip() == "?? TOUR.md"


def test_second_run_renders_from_cache_without_scanning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, overview_calls: Calls
) -> None:
    repo = minimal(tmp_path)
    invoke(str(repo.root))
    first = (repo.root / "TOUR.md").read_bytes()

    def no_scan(*args: object) -> None:
        raise AssertionError("scan should not run on a fully cached commit")

    monkeypatch.setattr(pipeline, "scan", no_scan)
    invoke(str(repo.root))

    assert overview_calls.count == 1
    assert (repo.root / "TOUR.md").read_bytes() == first


def test_new_commit_misses_the_cache(tmp_path: Path, overview_calls: Calls) -> None:
    repo = minimal(tmp_path)
    invoke(str(repo.root))

    repo.commit("More", {"app/extra.py": "x = 1\n"}, date="2024-03-01T12:00:00+00:00")
    invoke(str(repo.root))

    assert overview_calls.count == 2


def test_config_change_invalidates(tmp_path: Path, overview_calls: Calls) -> None:
    repo = minimal(tmp_path)
    invoke(str(repo.root))

    invoke(str(repo.root), "--since", "1y")
    invoke(str(repo.root), "--since", "1y")

    assert overview_calls.count == 2


def test_analyzer_version_bump_invalidates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, overview_calls: Calls
) -> None:
    repo = minimal(tmp_path)
    invoke(str(repo.root))

    monkeypatch.setattr(OverviewAnalyzer, "version", 999)
    invoke(str(repo.root))

    assert overview_calls.count == 2


def test_no_cache_neither_reads_nor_writes(tmp_path: Path, overview_calls: Calls) -> None:
    repo = minimal(tmp_path)

    invoke(str(repo.root), "--no-cache")
    assert not cache_dir(repo.root).exists()

    invoke(str(repo.root))
    invoke(str(repo.root), "--no-cache")
    assert overview_calls.count == 3


def test_deleting_the_cache_is_safe(tmp_path: Path, overview_calls: Calls) -> None:
    repo = minimal(tmp_path)
    invoke(str(repo.root))
    first = (repo.root / "TOUR.md").read_bytes()

    shutil.rmtree(cache_dir(repo.root))
    invoke(str(repo.root))

    assert overview_calls.count == 2
    assert (repo.root / "TOUR.md").read_bytes() == first
    assert (cache_dir(repo.root) / "cache.sqlite3").exists()


def test_corrupt_cache_is_rebuilt(tmp_path: Path) -> None:
    repo = minimal(tmp_path)
    invoke(str(repo.root))
    (cache_dir(repo.root) / "cache.sqlite3").write_bytes(b"not a database")

    result = invoke(str(repo.root))

    assert "0 warnings" in result.output


def test_worktrees_share_the_cache(tmp_path: Path, overview_calls: Calls) -> None:
    repo = minimal(tmp_path)
    invoke(str(repo.root))
    worktree = tmp_path / "wt"
    subprocess.run(
        ["git", "worktree", "add", "--quiet", "--detach", str(worktree)],
        cwd=repo.root,
        check=True,
    )

    invoke(str(worktree))

    assert overview_calls.count == 1
    assert not (worktree / CACHE_DIR_NAME).exists()


def test_failed_analyzer_results_are_not_cached(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = minimal(tmp_path)

    def boom(self, snapshot, inputs):  # type: ignore[no-untyped-def]
        raise RuntimeError("boom")

    with monkeypatch.context() as patch:
        patch.setattr(OverviewAnalyzer, "run", boom)
        assert "1 warning" in invoke(str(repo.root)).output

    assert "0 warnings" in invoke(str(repo.root)).output
