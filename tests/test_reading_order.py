from __future__ import annotations

import itertools
from pathlib import Path

from typer.testing import CliRunner

from repotour.cli import app
from repotour.model.tour import ReadingOrderSection
from repotour.pipeline import build_tour
from tests.conftest import GoldenCheck
from tests.fixtures.builder import FixtureRepo

_counter = itertools.count()
MAIN = "if __name__ == '__main__':\n    pass\n"


def build(tmp_path: Path, *commits: dict[str, str | bytes | None]) -> Path:
    repo = FixtureRepo.create(tmp_path, f"reading{next(_counter)}")
    for day, files in enumerate(commits, start=1):
        repo.commit(f"Commit {day}", files, date=f"2024-01-{day:02d}T00:00:00+00:00")
    return repo.root


def order(root: Path) -> ReadingOrderSection:
    section = build_tour(root, use_cache=False).tour.reading_order
    assert section is not None
    return section


def paths(root: Path) -> list[str]:
    return [step.path for step in order(root).steps]


def test_follows_imports_from_the_entry_point(tmp_path: Path) -> None:
    root = build(
        tmp_path,
        {
            "main.py": "import a\n\n" + MAIN,
            "a.py": "import b\n",
            "b.py": "x = 1\n",
            "other.py": "y = 2\n",
        },
    )

    assert paths(root) == ["main.py", "a.py", "b.py"]


def test_prefers_the_highest_scoring_import(tmp_path: Path) -> None:
    root = build(
        tmp_path,
        {
            "main.py": "import core\nimport side\n\n" + MAIN,
            "core.py": "x = 1\n",
            "side.py": "y = 1\n",
            "user1.py": "import core\n",
            "user2.py": "import core\n",
        },
    )

    assert paths(root)[:2] == ["main.py", "core.py"]


def test_pinned_entry_points_come_first(tmp_path: Path) -> None:
    root = build(
        tmp_path,
        {
            ".repotour.yml": "version: 1\npinned_entry_points: [docs_tour.py]\n",
            "main.py": MAIN,
            "docs_tour.py": "x = 1\n",
        },
    )

    steps = order(root).steps
    assert [s.path for s in steps][:2] == ["docs_tour.py", "main.py"]
    assert steps[0].reason.startswith("pinned in .repotour.yml")


def test_never_padded(tmp_path: Path) -> None:
    root = build(tmp_path, {"main.py": MAIN, "README.md": "# hi\n"})

    assert paths(root) == ["main.py"]


def test_cap_comes_from_config(tmp_path: Path) -> None:
    files: dict[str, str | bytes | None] = {
        ".repotour.yml": "version: 1\ncaps:\n  reading_order: 2\n"
    }
    files["main.py"] = "".join(f"import m{i}\n" for i in range(4)) + "\n" + MAIN
    files.update({f"m{i}.py": "x = 1\n" for i in range(4)})

    assert len(paths(build(tmp_path, files))) == 2


def test_falls_back_when_nothing_chosen_imports_more(tmp_path: Path) -> None:
    root = build(
        tmp_path,
        {"main.py": MAIN, "hot.py": "x = 0\n"},
        {"hot.py": "x = 1\n"},
        {"hot.py": "x = 2\n"},
    )

    assert paths(root) == ["main.py", "hot.py"]


def test_reasons_come_only_from_signals(tmp_path: Path) -> None:
    root = build(
        tmp_path,
        {"main.py": "import core\n\n" + MAIN, "core.py": "x = 0\n", "u.py": "import core\n"},
        {"core.py": "x = 1\n"},
    )

    steps = {s.path: s for s in order(root).steps}
    assert steps["main.py"].reason == "entry point: runs as a script"
    assert steps["core.py"].reason == (
        "imported by main.py; imported by 2 modules; changed 2 times in the last 6 months"
    )
    assert all(s.evidence for s in steps.values())


def test_tests_are_never_in_the_reading_order(tmp_path: Path) -> None:
    root = build(tmp_path, {"main.py": MAIN, "tests/test_main.py": "import main\n"})

    assert "tests/test_main.py" not in paths(root)


def test_unsupported_language_uses_manifests_and_hotspots(tmp_path: Path) -> None:
    root = build(
        tmp_path,
        {
            "Cargo.toml": '[package]\nname = "r"\n',
            "src/main.rs": "fn main() {}\n",
            "src/engine.rs": "pub fn run() {}\n",
        },
        {"src/engine.rs": "pub fn run() { }\n"},
    )

    assert paths(root) == ["src/main.rs", "src/engine.rs"]


def test_deterministic_ties_by_path(tmp_path: Path) -> None:
    root = build(tmp_path, {"b.py": MAIN, "a.py": MAIN})

    assert paths(root) == ["a.py", "b.py"]


def test_reading_order_golden(tmp_path: Path, golden: GoldenCheck) -> None:
    root = build(
        tmp_path,
        {
            "pyproject.toml": (
                '[project]\nname = "shop"\n\n[project.scripts]\nshop = "shop.cli:main"\n'
            ),
            "shop/__init__.py": "",
            "shop/cli.py": "import typer\nfrom shop import orders\n\napp = typer.Typer()\n",
            "shop/orders.py": "from shop import db\n",
            "shop/db.py": "import sqlite3\n",
            "shop/report.py": "from shop import db\n",
        },
        {"shop/orders.py": "from shop import db\n\nX = 1\n"},
    )

    result = CliRunner().invoke(app, [str(root)])

    assert result.exit_code == 0, result.output
    golden("reading-order", (root / "TOUR.md").read_bytes().decode("utf-8"))


def test_empty_files_are_never_chosen(tmp_path: Path) -> None:
    root = build(tmp_path, {"pkg/__init__.py": "", "pkg/cli.py": MAIN})

    assert paths(root) == ["pkg/cli.py"]


def test_execution_entry_points_come_before_public_surfaces(tmp_path: Path) -> None:
    root = build(tmp_path, {"aaa/__init__.py": "VALUE = 1\n", "zzz.py": MAIN})

    assert paths(root) == ["zzz.py", "aaa/__init__.py"]
