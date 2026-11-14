from __future__ import annotations

import itertools
from pathlib import Path

import pytest

from repotour.git import reader
from repotour.model.history import CommitRecord, FileChange, follow_renames
from repotour.model.tour import HotspotsSection
from repotour.pipeline import build_tour
from tests.fixtures.builder import FixtureRepo

_counter = itertools.count()
BODY = "line one\nline two\nline three\nline four\nline five\n"


def new_repo(tmp_path: Path) -> FixtureRepo:
    return FixtureRepo.create(tmp_path, f"renames{next(_counter)}")


def hotspot_counts(root: Path) -> dict[str, int]:
    section = build_tour(root, use_cache=False).tour.hotspots
    assert isinstance(section, HotspotsSection)
    return {h.path: h.commits for h in section.files}


def test_reader_reports_old_path_for_renames(tmp_path: Path) -> None:
    repo = new_repo(tmp_path)
    repo.commit("Add", {"old.py": BODY}, date="2024-01-01T00:00:00+00:00")
    repo.commit(
        "Rename", {"old.py": None, "new.py": BODY + "six\n"}, date="2024-01-02T00:00:00+00:00"
    )

    head = reader.repo_info(repo.root).head_commit
    newest = reader.read_history(repo.root, head)[0]

    assert [(c.old_path, c.path, c.added) for c in newest.files] == [("old.py", "new.py", 1)]


def test_renamed_file_keeps_its_history(tmp_path: Path) -> None:
    repo = new_repo(tmp_path)
    repo.commit("Add", {"old.py": BODY}, date="2024-01-01T00:00:00+00:00")
    repo.commit("Edit", {"old.py": BODY + "x\n"}, date="2024-01-02T00:00:00+00:00")
    repo.commit(
        "Rename", {"old.py": None, "new.py": BODY + "x\n"}, date="2024-01-03T00:00:00+00:00"
    )
    repo.commit("Edit again", {"new.py": BODY + "y\n"}, date="2024-01-04T00:00:00+00:00")

    assert hotspot_counts(repo.root) == {"new.py": 4}


def test_directory_move(tmp_path: Path) -> None:
    repo = new_repo(tmp_path)
    repo.commit(
        "Add", {"src/a.py": BODY, "src/b.py": BODY + "b\n"}, date="2024-01-01T00:00:00+00:00"
    )
    repo.commit(
        "Move src to lib",
        {"src/a.py": None, "src/b.py": None, "lib/a.py": BODY, "lib/b.py": BODY + "b\n"},
        date="2024-01-02T00:00:00+00:00",
    )

    assert hotspot_counts(repo.root) == {"lib/a.py": 2, "lib/b.py": 2}


def test_rename_chain_resolves_to_head_path(tmp_path: Path) -> None:
    repo = new_repo(tmp_path)
    repo.commit("Add a", {"a.py": BODY}, date="2024-01-01T00:00:00+00:00")
    repo.commit("a to b", {"a.py": None, "b.py": BODY}, date="2024-01-02T00:00:00+00:00")
    repo.commit("b to c", {"b.py": None, "c.py": BODY}, date="2024-01-03T00:00:00+00:00")
    repo.commit("Edit c", {"c.py": BODY + "z\n"}, date="2024-01-04T00:00:00+00:00")

    assert hotspot_counts(repo.root) == {"c.py": 4}


def test_file_deleted_after_rename_never_appears(tmp_path: Path) -> None:
    repo = new_repo(tmp_path)
    repo.commit("Add", {"a.py": BODY, "keep.py": "k\n"}, date="2024-01-01T00:00:00+00:00")
    repo.commit("Rename", {"a.py": None, "b.py": BODY}, date="2024-01-02T00:00:00+00:00")
    repo.commit("Delete", {"b.py": None}, date="2024-01-03T00:00:00+00:00")

    assert hotspot_counts(repo.root) == {"keep.py": 1}


def test_reused_path_keeps_histories_apart(tmp_path: Path) -> None:
    repo = new_repo(tmp_path)
    repo.commit("Add a", {"a.py": BODY}, date="2024-01-01T00:00:00+00:00")
    repo.commit("a to b", {"a.py": None, "b.py": BODY}, date="2024-01-02T00:00:00+00:00")
    repo.commit("New a", {"a.py": "brand new\n"}, date="2024-01-03T00:00:00+00:00")

    assert hotspot_counts(repo.root) == {"a.py": 1, "b.py": 2}


def test_follow_renames_rewrites_paths_to_head(tmp_path: Path) -> None:
    repo = new_repo(tmp_path)
    repo.commit("Add", {"a.py": BODY}, date="2024-01-01T00:00:00+00:00")
    repo.commit("Rename", {"a.py": None, "b.py": BODY}, date="2024-01-02T00:00:00+00:00")

    head = reader.repo_info(repo.root).head_commit
    followed = follow_renames(reader.read_history(repo.root, head))

    assert [c.path for commit in followed for c in commit.files] == ["b.py", "b.py"]


def test_renames_are_followed_once_per_tour(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[int] = []
    real = follow_renames

    def counting(commits: tuple[CommitRecord, ...]) -> tuple[CommitRecord, ...]:
        calls.append(len(commits))
        return real(commits)

    monkeypatch.setattr("repotour.model.snapshot.follow_renames", counting)
    repo = new_repo(tmp_path)
    repo.commit("Add", {"a.py": BODY})
    repo.commit("Move", {"b.py": BODY, "a.py": None})

    tour = build_tour(repo.root, use_cache=False).tour

    assert tour.hotspots is not None
    assert tour.ownership is not None
    assert len(calls) == 1


def test_follow_renames_keeps_unrenamed_commits_intact() -> None:
    plain = CommitRecord("a" * 40, "Ada", "a@x", 1, (FileChange("x.py", 1, 0),))

    (followed,) = follow_renames((plain,))

    assert followed == plain
