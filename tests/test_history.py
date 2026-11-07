from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from repotour.cli import app
from repotour.config import CliOverrides
from repotour.git import reader
from repotour.model.tour import HotspotsSection
from repotour.pipeline import build_tour
from tests.conftest import GoldenCheck
from tests.fixtures.builder import Author, FixtureRepo
from tests.fixtures.repos import history


@pytest.fixture(scope="module")
def history_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return history(tmp_path_factory.mktemp("history")).root


def hotspots(root: Path, since: str | None = None) -> HotspotsSection:
    section = build_tour(root, CliOverrides(since=since), use_cache=False).tour.hotspots
    assert section is not None
    return section


# --- reader ------------------------------------------------------------------------


def test_reads_commits_newest_first_without_merges(history_root: Path) -> None:
    head = reader.repo_info(history_root).head_commit
    commits = reader.read_history(history_root, head)

    messages_count = len(commits)
    assert messages_count == 18  # 1 start + 11 core + 3 util + logo + removal + feature
    assert commits[0].timestamp >= commits[-1].timestamp
    assert all(len(c.sha) == 40 for c in commits)


def test_records_carry_author_and_line_counts(history_root: Path) -> None:
    head = reader.repo_info(history_root).head_commit
    first = reader.read_history(history_root, head)[-1]

    assert first.author_name == "Ada Lovelace"
    assert first.author_email == "ada@example.com"
    changes = {c.path: (c.added, c.removed) for c in first.files}
    assert changes["app/core.py"] == (1, 0)
    assert changes["logo.png"] == (None, None)


def test_mailmap_is_applied(tmp_path: Path) -> None:
    repo = FixtureRepo.create(tmp_path, "mailmap")
    repo.commit(
        "Add mailmap",
        {".mailmap": "Ada Lovelace <ada@example.com> <ada@old.example.com>\n", "a.py": "a\n"},
    )
    repo.commit("Old identity", {"a.py": "b\n"}, author=Author("ada", "ada@old.example.com"))

    head = reader.repo_info(repo.root).head_commit
    newest = reader.read_history(repo.root, head)[0]

    assert (newest.author_name, newest.author_email) == ("Ada Lovelace", "ada@example.com")


def test_head_timestamp_is_the_committer_date(history_root: Path) -> None:
    head = reader.repo_info(history_root).head_commit

    assert reader.commit_timestamp(history_root, head) == 1735380000  # 2024-12-28T10:00Z


# --- hotspots ----------------------------------------------------------------------


def test_hotspots_in_default_window(history_root: Path) -> None:
    section = hotspots(history_root)

    assert [(h.path, h.commits) for h in section.files] == [
        ("app/core.py", 6),
        ("app/util.py", 3),
        ("app/feature.py", 1),
        ("logo.png", 1),
    ]
    assert (section.since, section.start, section.end) == ("6m", "2024-07-01", "2024-12-28")


def test_since_changes_the_window(history_root: Path) -> None:
    assert [(h.path, h.commits) for h in hotspots(history_root, "1m").files] == [
        ("app/core.py", 1),
        ("app/feature.py", 1),
    ]
    assert [(h.path, h.commits) for h in hotspots(history_root, "1y").files] == [
        ("app/core.py", 12),
        ("app/util.py", 4),
        ("logo.png", 2),
        ("README.md", 1),
        ("app/feature.py", 1),
    ]


def test_generated_and_deleted_files_never_appear(history_root: Path) -> None:
    paths = {h.path for h in hotspots(history_root, "1y").files}

    assert "package-lock.json" not in paths
    assert "app/old.py" not in paths


def test_each_hotspot_cites_a_commit_range(history_root: Path) -> None:
    core = hotspots(history_root).files[0]

    evidence = core.evidence[0]
    assert evidence.kind == "commit_range"
    assert ".." in evidence.ref
    assert evidence.detail == "6 commits between 2024-07-15 and 2024-12-15"


def test_cap_comes_from_config(tmp_path: Path) -> None:
    repo = history(tmp_path)
    (repo.root / ".repotour.yml").write_text("version: 1\ncaps:\n  hotspots: 2\n", encoding="utf-8")
    repo.commit("Add config", {}, date="2024-12-29T10:00:00+00:00")

    assert len(hotspots(repo.root).files) == 2


def test_window_start_is_inclusive(tmp_path: Path) -> None:
    repo = FixtureRepo.create(tmp_path, "boundary")
    repo.commit("Too old", {"old.py": "1\n"}, date="2024-06-29T23:59:59+00:00")
    repo.commit("Exactly at start", {"edge.py": "1\n"}, date="2024-06-30T00:00:00+00:00")
    repo.commit("Head", {"head.py": "1\n"}, date="2024-07-01T00:00:00+00:00")

    assert {h.path for h in hotspots(repo.root, "1d").files} == {"edge.py", "head.py"}


def test_single_commit_evidence_names_the_commit(history_root: Path) -> None:
    feature = next(h for h in hotspots(history_root).files if h.path == "app/feature.py")

    assert ".." not in feature.evidence[0].ref
    assert feature.evidence[0].detail == "1 commit on 2024-12-20"


def test_window_is_described_for_people(history_root: Path) -> None:
    assert hotspots(history_root).window == "6 months"
    assert hotspots(history_root, "1y").window == "1 year"


def test_window_is_anchored_to_head_not_today(history_root: Path) -> None:
    # The history ends in 2024; a window measured from today would be empty.
    assert hotspots(history_root).files


def test_history_golden(history_root: Path, golden: GoldenCheck) -> None:
    result = CliRunner().invoke(app, [str(history_root), "--force", "--no-cache"])

    assert result.exit_code == 0, result.output
    golden("history", (history_root / "TOUR.md").read_bytes().decode("utf-8"))


def test_same_day_commits_say_on(tmp_path: Path) -> None:
    repo = FixtureRepo.create(tmp_path, "sameday")
    repo.commit("One", {"a.py": "1\n"}, date="2024-05-01T09:00:00+00:00")
    repo.commit("Two", {"a.py": "2\n"}, date="2024-05-01T17:00:00+00:00")

    assert hotspots(repo.root).files[0].evidence[0].detail == "2 commits on 2024-05-01"
