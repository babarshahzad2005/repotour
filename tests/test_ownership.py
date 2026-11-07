"""Ownership on the `team` fixture. Expected shares, by hand:

core/    Ada 60 (start) + 20 (rewrite as ada@old, merged by .mailmap) = 80
         Grace 5 (extend c2); dependabot[bot] and release-robot excluded
         -> 85 lines: Ada 94%, Grace 6%
web/     Grace 20 (start); Linus 20 (grow w1) + 10 (api) = 30
         -> 50 lines: Linus 60%, Grace 40%
web/api/ Linus 10 -> 100%
deep/, deep/a/  Grace 5 -> 100%   (deep/a/b/ is too deep; tiny/ is too small)

Contacts: a commit to the directory within 12 months (360 days) before HEAD
(2024-12-01), i.e. on or after 2023-12-07.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from repotour.cli import app
from repotour.model.tour import OwnershipEntry, OwnershipSection
from repotour.pipeline import build_tour
from tests.conftest import GoldenCheck
from tests.fixtures.builder import FixtureRepo
from tests.fixtures.repos import team


@pytest.fixture(scope="module")
def team_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return team(tmp_path_factory.mktemp("ownership")).root


@pytest.fixture(scope="module")
def ownership(team_root: Path) -> OwnershipSection:
    section = build_tour(team_root, use_cache=False).tour.ownership
    assert section is not None
    return section


def entry(section: OwnershipSection, path: str) -> OwnershipEntry:
    return next(e for e in section.entries if e.path == path)


def shares(e: OwnershipEntry) -> list[tuple[str, int]]:
    return [(a.name, a.share) for a in e.authors]


def test_directories_respect_depth_and_size_limits(ownership: OwnershipSection) -> None:
    assert [e.path for e in ownership.entries] == ["core", "deep", "deep/a", "web", "web/api"]


def test_mailmap_merges_identities(ownership: OwnershipSection) -> None:
    assert shares(entry(ownership, "core")) == [("Ada Lovelace", 94), ("Grace Hopper", 6)]


def test_bots_are_excluded(ownership: OwnershipSection) -> None:
    names = {a.name for e in ownership.entries for a in e.authors}

    assert "dependabot[bot]" not in names
    assert "release-robot" not in names


def test_shares_and_line_counts(ownership: OwnershipSection) -> None:
    web = entry(ownership, "web")

    assert shares(web) == [("Linus Ops", 60), ("Grace Hopper", 40)]
    assert [(a.lines, a.commits) for a in web.authors] == [(30, 2), (20, 1)]
    assert web.total_lines == 50
    assert shares(entry(ownership, "web/api")) == [("Linus Ops", 100)]


def test_contacts_need_a_recent_commit(ownership: OwnershipSection) -> None:
    assert [c.name for c in entry(ownership, "core").contacts] == ["Grace Hopper"]
    assert [c.name for c in entry(ownership, "web").contacts] == ["Linus Ops", "Grace Hopper"]
    assert entry(ownership, "web").contacts[0].last_commit == "2024-11-02"


def test_every_author_and_contact_cites_commits(ownership: OwnershipSection) -> None:
    for e in ownership.entries:
        for claim in (*e.authors, *e.contacts):
            assert claim.evidence
            assert claim.evidence[0].kind == "commit_range"


def test_author_cap_comes_from_config(tmp_path: Path) -> None:
    repo = team(tmp_path)
    (repo.root / ".repotour.yml").write_text(
        "version: 1\nbots: [release-robot]\ncaps:\n  authors_per_directory: 1\n", encoding="utf-8"
    )
    repo.commit("Cap", {}, date="2024-12-02T10:00:00+00:00")

    section = build_tour(repo.root, use_cache=False).tour.ownership
    assert section is not None
    assert all(len(e.authors) <= 1 for e in section.entries)


def test_no_emails_in_the_tour(team_root: Path) -> None:
    result = CliRunner().invoke(app, [str(team_root), "--force", "--no-cache"])
    assert result.exit_code == 0, result.output

    text = (team_root / "TOUR.md").read_text(encoding="utf-8")
    ownership_part = text.split("## Ownership", 1)[1].split("## Warnings", 1)[0]
    assert "@" not in ownership_part


def test_renamed_files_count_toward_their_current_directory(tmp_path: Path) -> None:
    repo = FixtureRepo.create(tmp_path, "moved")
    body = "".join(f"line{i}\n" for i in range(10))
    repo.commit(
        "Add",
        {f"old/m{i}.py": body + str(i) + "\n" for i in range(5)},
        date="2024-01-01T00:00:00+00:00",
    )
    moved: dict[str, str | bytes | None] = {f"old/m{i}.py": None for i in range(5)}
    moved.update({f"new/m{i}.py": body + str(i) + "\n" for i in range(5)})
    repo.commit("Move", moved, date="2024-01-02T00:00:00+00:00")

    section = build_tour(repo.root, use_cache=False).tour.ownership
    assert section is not None
    assert [(e.path, e.total_lines) for e in section.entries] == [("new", 55)]


def test_ownership_golden(team_root: Path, golden: GoldenCheck) -> None:
    result = CliRunner().invoke(app, [str(team_root), "--force", "--no-cache"])

    assert result.exit_code == 0, result.output
    golden("team", (team_root / "TOUR.md").read_bytes().decode("utf-8"))
