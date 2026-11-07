from __future__ import annotations

import itertools
from pathlib import Path

from typer.testing import CliRunner

from repotour.cli import app
from repotour.model.tour import HotspotsSection
from repotour.pipeline import build_tour
from tests.conftest import GoldenCheck
from tests.fixtures.builder import FixtureRepo

_counter = itertools.count()
SMALL_THRESHOLD = "version: 1\nthresholds:\n  bulk_commit_files: 3\n"


def new_repo(tmp_path: Path) -> FixtureRepo:
    return FixtureRepo.create(tmp_path, f"bulk{next(_counter)}")


def section(root: Path) -> HotspotsSection:
    result = build_tour(root, use_cache=False).tour.hotspots
    assert isinstance(result, HotspotsSection)
    return result


def counts(root: Path) -> dict[str, int]:
    return {h.path: h.commits for h in section(root).files}


def test_commit_over_the_default_threshold_is_bulk(tmp_path: Path) -> None:
    repo = new_repo(tmp_path)
    files: dict[str, str | bytes | None] = {f"pkg/m{i:03}.py": f"x = {i}\n" for i in range(201)}
    repo.commit("Import everything", files, date="2024-01-01T00:00:00+00:00")
    repo.commit("Edit one", {"pkg/m000.py": "x = -1\n"}, date="2024-01-02T00:00:00+00:00")

    result = section(repo.root)

    assert result.files[0].path == "pkg/m000.py"
    assert result.files[0].commits == 1
    assert result.bulk is not None
    assert result.bulk.count == 1


def test_configured_threshold(tmp_path: Path) -> None:
    repo = new_repo(tmp_path)
    repo.commit("Config", {".repotour.yml": SMALL_THRESHOLD}, date="2024-01-01T00:00:00+00:00")
    repo.commit(
        "Format all",
        {"a.py": "a\n", "b.py": "b\n", "c.py": "c\n", "d.py": "d\n"},
        date="2024-01-02T00:00:00+00:00",
    )
    repo.commit("Edit a", {"a.py": "a2\n"}, date="2024-01-03T00:00:00+00:00")

    assert counts(repo.root) == {"a.py": 1, ".repotour.yml": 1}


def test_ignore_revs_file(tmp_path: Path) -> None:
    repo = new_repo(tmp_path)
    repo.commit("Add", {"a.py": "a\n"}, date="2024-01-01T00:00:00+00:00")
    reformat = repo.commit("Reformat", {"a.py": "a  \n"}, date="2024-01-02T00:00:00+00:00")
    repo.commit(
        "Ignore the reformat",
        {".git-blame-ignore-revs": f"# formatting pass\n\n{reformat}\n"},
        date="2024-01-03T00:00:00+00:00",
    )

    result = section(repo.root)

    assert {h.path: h.commits for h in result.files}["a.py"] == 1
    assert result.bulk is not None
    assert result.bulk.evidence[0].ref == reformat[:12]
    assert result.bulk.evidence[0].detail == "listed in .git-blame-ignore-revs"


def test_config_ignore_revs_accepts_abbreviated_shas(tmp_path: Path) -> None:
    repo = new_repo(tmp_path)
    repo.commit("Add", {"a.py": "a\n"}, date="2024-01-01T00:00:00+00:00")
    noisy = repo.commit("Noise", {"a.py": "b\n"}, date="2024-01-02T00:00:00+00:00")
    repo.commit(
        "Config",
        {".repotour.yml": f"version: 1\nignore_revs: ['{noisy[:9]}']\n"},
        date="2024-01-03T00:00:00+00:00",
    )

    result = section(repo.root)

    assert {h.path: h.commits for h in result.files}["a.py"] == 1
    assert result.bulk is not None
    assert result.bulk.evidence[0].detail == "listed in config ignore_revs"


def test_mass_rename_is_bulk_but_renames_are_still_followed(tmp_path: Path) -> None:
    repo = new_repo(tmp_path)
    repo.commit("Config", {".repotour.yml": SMALL_THRESHOLD}, date="2024-01-01T00:00:00+00:00")
    body = "one\ntwo\nthree\nfour\nfive\n"
    old = {f"src/{n}.py": body + n + "\n" for n in "abcd"}
    first_half = {p: c for p, c in old.items() if p < "src/c.py"}
    second_half = {p: c for p, c in old.items() if p >= "src/c.py"}
    repo.commit("Add a, b", dict(first_half), date="2024-01-02T00:00:00+00:00")
    repo.commit("Add c, d", dict(second_half), date="2024-01-02T12:00:00+00:00")
    moved: dict[str, str | bytes | None] = dict.fromkeys(old)
    moved.update({p.replace("src/", "lib/"): c for p, c in old.items()})
    repo.commit("Move src to lib", moved, date="2024-01-03T00:00:00+00:00")

    assert counts(repo.root) == {
        ".repotour.yml": 1,
        "lib/a.py": 1,
        "lib/b.py": 1,
        "lib/c.py": 1,
        "lib/d.py": 1,
    }


def test_no_bulk_commits_means_no_note(tmp_path: Path) -> None:
    repo = new_repo(tmp_path)
    repo.commit("Add", {"a.py": "a\n"}, date="2024-01-01T00:00:00+00:00")

    assert section(repo.root).bulk is None


def test_bulk_golden(tmp_path: Path, golden: GoldenCheck) -> None:
    repo = FixtureRepo.create(tmp_path, "bulk")
    repo.commit("Add", {"a.py": "a\n", "b.py": "b\n"}, date="2024-01-01T00:00:00+00:00")
    reformat = repo.commit(
        "Reformat", {"a.py": "a \n", "b.py": "b \n"}, date="2024-01-02T00:00:00+00:00"
    )
    repo.commit("Edit a", {"a.py": "a2\n"}, date="2024-01-03T00:00:00+00:00")
    repo.commit(
        "Ignore the reformat",
        {".git-blame-ignore-revs": f"{reformat}\n"},
        date="2024-01-04T00:00:00+00:00",
    )

    result = CliRunner().invoke(app, [str(repo.root)])

    assert result.exit_code == 0, result.output
    golden("bulk", (repo.root / "TOUR.md").read_bytes().decode("utf-8"))
