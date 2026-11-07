from __future__ import annotations

import itertools
from pathlib import Path

import pytest

from repotour.model.tour import OwnershipEntry, OwnershipSection
from repotour.pipeline import build_tour
from tests.fixtures.builder import Author, FixtureRepo
from tests.fixtures.repos import team

_counter = itertools.count()
SOLO = Author("Solo Dev", "solo@example.com")
OTHER = Author("Other Dev", "other@example.com")


def ownership_of(root: Path) -> OwnershipSection:
    section = build_tour(root, use_cache=False).tour.ownership
    assert section is not None
    return section


def entry(root: Path, path: str) -> OwnershipEntry:
    return next(e for e in ownership_of(root).entries if e.path == path)


def build(
    tmp_path: Path,
    *,
    files: int = 5,
    solo_commits: int = 10,
    other_lines: int = 0,
    config: str | None = None,
) -> Path:
    """`files` files in lib/, then `solo_commits` one-line commits by Solo
    (the first adds every file, one line each). Other adds `other_lines`."""
    repo = FixtureRepo.create(tmp_path, f"bus{next(_counter)}")
    initial: dict[str, str | bytes | None] = {f"lib/f{i}.py": "0\n" for i in range(files)}
    if config is not None:
        initial[".repotour.yml"] = config
    repo.commit("Start", initial, author=SOLO, date="2024-01-01T00:00:00+00:00")
    for n in range(1, solo_commits):
        repo.commit(
            f"Change {n}",
            {"lib/f0.py": f"{n}\n"},
            author=SOLO,
            date=f"2024-02-{n:02d}T00:00:00+00:00",
        )
    if other_lines:
        body = "".join(f"o{i}\n" for i in range(other_lines))
        repo.commit("Other", {"lib/other.py": body}, author=OTHER, date="2024-03-01T00:00:00+00:00")
    return repo.root


def test_warning_when_all_conditions_hold(tmp_path: Path) -> None:
    lib = entry(build(tmp_path), "lib")

    assert lib.bus_factor is not None
    assert lib.bus_factor.name == "Solo Dev"
    assert lib.bus_factor.share == 100
    assert (lib.files, lib.commits) == (5, 10)
    assert lib.bus_factor.evidence[0].kind == "commit_range"
    assert "5 files" in (lib.bus_factor.evidence[0].detail or "")


def test_too_few_commits_means_no_warning(tmp_path: Path) -> None:
    assert entry(build(tmp_path, solo_commits=9), "lib").bus_factor is None


def test_too_few_files_means_no_warning(tmp_path: Path) -> None:
    config = "version: 1\nthresholds:\n  bus_factor_min_files: 6\n"

    assert entry(build(tmp_path, config=config), "lib").bus_factor is None


def test_share_must_exceed_the_threshold(tmp_path: Path) -> None:
    # Solo: 5 (start) + 9 changes x 2 lines = 23 lines; Other 6 lines -> 23/29 = 79%
    assert entry(build(tmp_path, other_lines=6), "lib").bus_factor is None
    # Other 5 lines -> 23/28 = 82%
    assert entry(build(tmp_path, other_lines=5), "lib").bus_factor is not None


def test_configured_share_threshold(tmp_path: Path) -> None:
    config = "version: 1\nthresholds:\n  bus_factor_share: 0.5\n"

    assert entry(build(tmp_path, other_lines=6, config=config), "lib").bus_factor is not None


@pytest.fixture(scope="module")
def team_section(tmp_path_factory: pytest.TempPathFactory) -> OwnershipSection:
    return ownership_of(team(tmp_path_factory.mktemp("activity")).root)


def test_activity_states_on_team(team_section: OwnershipSection) -> None:
    activity = {e.path: (e.activity.state if e.activity else None) for e in team_section.entries}

    # Window: 6 months (180 days) before 2024-12-01 -> from 2024-06-04.
    # core/ last changed 2024-06-03 (inside 12 months): neither.
    assert activity == {
        "core": None,
        "deep": "active",
        "deep/a": "active",
        "web": "active",
        "web/api": "active",
    }


def test_small_team_directories_get_no_warning(team_section: OwnershipSection) -> None:
    assert all(e.bus_factor is None for e in team_section.entries)


def test_stable_area(tmp_path: Path) -> None:
    repo = FixtureRepo.create(tmp_path, "stable")
    repo.commit(
        "Old code",
        {f"old/f{i}.py": "x\n" for i in range(5)},
        author=SOLO,
        date="2022-01-01T00:00:00+00:00",
    )
    repo.commit("Recent docs", {"README.md": "hi\n"}, author=SOLO, date="2024-01-01T00:00:00+00:00")

    old = entry(repo.root, "old")

    assert old.activity is not None
    assert old.activity.state == "stable"
    assert old.activity.evidence[0].detail == "last change on 2022-01-01"
