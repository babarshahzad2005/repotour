from __future__ import annotations

import itertools
from pathlib import Path

import pytest
from typer.testing import CliRunner

from repotour.cli import app
from repotour.model.tour import EntryPoint, EntryPointsSection, Tour
from repotour.pipeline import build_tour
from tests.conftest import GoldenCheck
from tests.fixtures.builder import FixtureRepo

_counter = itertools.count()


def tour_for(tmp_path: Path, files: dict[str, str | bytes | None]) -> Tour:
    repo = FixtureRepo.create(tmp_path, f"entry{next(_counter)}")
    repo.commit("Add", files)
    return build_tour(repo.root, use_cache=False).tour


def section_for(tmp_path: Path, files: dict[str, str | bytes | None]) -> EntryPointsSection:
    section = tour_for(tmp_path, files).entry_points
    assert section is not None
    return section


def by_path(section: EntryPointsSection) -> dict[str, EntryPoint]:
    return {e.path: e for e in section.entries}


@pytest.mark.parametrize(
    ("source", "description"),
    [
        ('def main(): ...\n\nif __name__ == "__main__":\n    main()\n', "runs as a script"),
        ("import typer\napp = typer.Typer()\n", "defines a CLI (Typer)"),
        ("import click\n\n@click.command\ndef cli(): ...\n", "defines a CLI (Click)"),
        ("import argparse\np = argparse.ArgumentParser()\n", "defines a CLI (argparse)"),
        ("import uvicorn\nuvicorn.run('app:app')\n", "starts a server"),
        ("from flask import Flask\napp = Flask(__name__)\n", "defines a web app (Flask)"),
        ("from fastapi import FastAPI\napi = FastAPI()\n", "defines a web app (FastAPI)"),
    ],
)
def test_python_execution_patterns(tmp_path: Path, source: str, description: str) -> None:
    entry = by_path(section_for(tmp_path, {"tool.py": source}))["tool.py"]

    assert entry.kind == "execution"
    assert entry.description == description
    assert entry.evidence[0].ref == "tool.py"
    assert (entry.evidence[0].detail or "").startswith("line ")


def test_django_url_routes(tmp_path: Path) -> None:
    section = section_for(tmp_path, {"site/urls.py": "urlpatterns = []\n"})

    assert by_path(section)["site/urls.py"].description == "defines URL routes (Django)"


def test_several_patterns_in_one_file_are_combined(tmp_path: Path) -> None:
    source = "import typer\napp = typer.Typer()\n\nif __name__ == '__main__':\n    app()\n"

    entry = by_path(section_for(tmp_path, {"cli.py": source}))["cli.py"]

    assert entry.description == "defines a CLI (Typer); runs as a script"
    assert len(entry.evidence) == 2


def test_console_scripts_from_pyproject(tmp_path: Path) -> None:
    section = section_for(
        tmp_path,
        {
            "pyproject.toml": '[project]\nname = "x"\n\n[project.scripts]\ntool = "pkg.cli:main"\n',
            "pkg/__init__.py": "",
            "pkg/cli.py": "def main(): ...\n",
        },
    )

    entry = by_path(section)["pkg/cli.py"]
    assert entry.kind == "execution"
    assert entry.description == "console script `tool`"
    assert (entry.evidence[0].ref, entry.evidence[0].detail) == (
        "pyproject.toml",
        "[project.scripts] tool = pkg.cli:main",
    )


def test_public_surface_is_the_top_level_package(tmp_path: Path) -> None:
    section = section_for(
        tmp_path,
        {
            "src/pkg/__init__.py": "",
            "src/pkg/sub/__init__.py": "",
            "src/pkg/core.py": "",
        },
    )

    public = [e.path for e in section.entries if e.kind == "public surface"]
    assert public == ["src/pkg/__init__.py"]
    assert by_path(section)["src/pkg/__init__.py"].description == "top-level package `pkg`"


@pytest.mark.parametrize(
    ("files", "path", "kind", "manifest"),
    [
        (
            {"package.json": '{"scripts": {"start": "node server.js"}}', "server.js": "x;\n"},
            "server.js",
            "execution",
            "package.json",
        ),
        (
            {"Dockerfile": 'FROM python:3.12\nCMD ["python", "app.py"]\n', "app.py": "x = 1\n"},
            "app.py",
            "execution",
            "Dockerfile",
        ),
        (
            {"Cargo.toml": '[package]\nname = "r"\n', "src/main.rs": "fn main() {}\n"},
            "src/main.rs",
            "execution",
            "Cargo.toml",
        ),
        (
            {"Cargo.toml": '[package]\nname = "r"\n', "src/lib.rs": "pub fn f() {}\n"},
            "src/lib.rs",
            "public surface",
            "Cargo.toml",
        ),
    ],
)
def test_entry_points_from_manifests(
    tmp_path: Path,
    files: dict[str, str | bytes | None],
    path: str,
    kind: str,
    manifest: str,
) -> None:
    entry = by_path(section_for(tmp_path, files))[path]

    assert entry.kind == kind
    assert entry.evidence[0].ref == manifest


def test_manifest_commands_that_point_nowhere_are_ignored(tmp_path: Path) -> None:
    section = section_for(tmp_path, {"package.json": '{"scripts": {"start": "node missing.js"}}'})

    assert section.entries == ()


def test_pinned_entry_points_come_first(tmp_path: Path) -> None:
    tour = tour_for(
        tmp_path,
        {
            ".repotour.yml": "version: 1\npinned_entry_points: [zz/start.py, gone.py]\n",
            "a.py": "if __name__ == '__main__':\n    pass\n",
            "zz/start.py": "x = 1\n",
        },
    )
    section = tour.entry_points
    assert section is not None

    assert [(e.path, e.pinned) for e in section.entries] == [("zz/start.py", True), ("a.py", False)]
    assert section.entries[0].evidence[0].kind == "config"
    assert ".repotour.yml: pinned entry point 'gone.py' does not exist" in tour.warnings


def test_cap_per_kind(tmp_path: Path) -> None:
    files: dict[str, str | bytes | None] = {
        f"scripts/s{i:02}.py": "if __name__ == '__main__':\n    pass\n" for i in range(12)
    }

    section = section_for(tmp_path, files)

    assert len([e for e in section.entries if e.kind == "execution"]) == 10
    assert section.omitted == 2


def test_tests_are_not_entry_points(tmp_path: Path) -> None:
    section = section_for(tmp_path, {"tests/test_x.py": "if __name__ == '__main__':\n    pass\n"})

    assert section.entries == ()


def test_entry_points_golden(tmp_path: Path, golden: GoldenCheck) -> None:
    repo = FixtureRepo.create(tmp_path, "entrypoints")
    repo.commit(
        "Add",
        {
            "pyproject.toml": (
                '[project]\nname = "shop"\n\n[project.scripts]\nshop = "shop.cli:main"\n'
            ),
            "shop/__init__.py": "",
            "shop/cli.py": "import typer\napp = typer.Typer()\n\ndef main():\n    app()\n",
            "shop/web.py": "from flask import Flask\napp = Flask(__name__)\n",
            "Dockerfile": 'FROM python:3.12\nCMD ["python", "-m", "shop.web"]\n',
        },
    )

    result = CliRunner().invoke(app, [str(repo.root)])

    assert result.exit_code == 0, result.output
    golden("entry-points", (repo.root / "TOUR.md").read_bytes().decode("utf-8"))


def test_package_main_module(tmp_path: Path) -> None:
    section = section_for(tmp_path, {"tool/__init__.py": "", "tool/__main__.py": "print(1)\n"})

    entry = by_path(section)["tool/__main__.py"]
    assert entry.kind == "execution"
    assert entry.description == "runs with `python -m tool`"
