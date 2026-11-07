from __future__ import annotations

import itertools
from pathlib import Path

from typer.testing import CliRunner

from repotour.cli import app
from repotour.model.tour import Command, Overview
from repotour.pipeline import build_tour
from tests.conftest import GoldenCheck
from tests.fixtures.builder import FixtureRepo

_counter = itertools.count()


def commands_for(tmp_path: Path, files: dict[str, str | bytes | None]) -> tuple[Command, ...]:
    repo = FixtureRepo.create(tmp_path, f"cmds{next(_counter)}")
    repo.commit("Add project", files)
    overview = build_tour(repo.root, use_cache=False).tour.overview
    assert isinstance(overview, Overview)
    return overview.commands


def by_purpose(commands: tuple[Command, ...]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for c in commands:
        grouped.setdefault(c.purpose, []).append(c.command)
    return grouped


MAKEFILE = """\
.PHONY: install test run
VERSION := 1.0

install:
\tpip install -e .

test: install
\tpytest -q

test-integration:
\tpytest -m integration

run:
\tpython -m app

build:
\tpython -m build
"""


def test_makefile_targets(tmp_path: Path) -> None:
    commands = commands_for(tmp_path, {"Makefile": MAKEFILE})

    assert by_purpose(commands) == {
        "install": ["make install"],
        "run": ["make run"],
        "test": ["make test", "make test-integration"],
        "other": ["make build"],
    }
    test = next(c for c in commands if c.command == "make test")
    assert test.evidence[0].ref == "Makefile"
    assert test.evidence[0].detail == "target test: pytest -q"


def test_justfile_recipes(tmp_path: Path) -> None:
    justfile = "default:\n    just --list\n\ntest *args:\n    cargo test {{args}}\n"

    assert by_purpose(commands_for(tmp_path, {"justfile": justfile})) == {
        "test": ["just test"],
        "other": ["just default"],
    }


def test_package_json_scripts_quote_the_script(tmp_path: Path) -> None:
    package = """{"name": "x", "scripts": {
        "start": "node server.js", "test": "jest", "lint": "eslint .", "dev": "vite"}}"""

    commands = commands_for(tmp_path, {"package.json": package})

    assert by_purpose(commands) == {
        "run": ["npm run dev", "npm start"],
        "test": ["npm test"],
        "other": ["npm run lint"],
    }
    start = next(c for c in commands if c.command == "npm start")
    assert start.evidence[0].detail == 'script "start": node server.js'


def test_package_manager_follows_the_lockfile(tmp_path: Path) -> None:
    package = '{"name": "x", "scripts": {"test": "vitest"}}'

    commands = commands_for(
        tmp_path, {"package.json": package, "pnpm-lock.yaml": "lockfileVersion: 9\n"}
    )

    assert by_purpose(commands) == {"test": ["pnpm test"]}


def test_pyproject_task_runners(tmp_path: Path) -> None:
    pyproject = """\
[project]
name = "x"

[tool.poe.tasks]
test = "pytest"
serve = "uvicorn app:app"

[tool.hatch.envs.default.scripts]
cov = "pytest --cov"
"""

    commands = commands_for(tmp_path, {"pyproject.toml": pyproject})

    assert by_purpose(commands) == {
        "run": ["poe serve"],
        "test": ["poe test"],
        "other": ["hatch run cov"],
    }


def test_tox_and_nox(tmp_path: Path) -> None:
    noxfile = (
        "import nox\n\n"
        "@nox.session\ndef tests(session):\n    pass\n\n"
        "@nox.session(python='3.12')\ndef lint(session):\n    pass\n"
    )

    commands = commands_for(
        tmp_path, {"tox.ini": "[tox]\nenvlist = py311\n", "noxfile.py": noxfile}
    )

    assert by_purpose(commands) == {
        "test": ["tox", "nox -s tests"],
        "other": ["nox -s lint"],
    }


WORKFLOW = """\
name: CI
on: [push]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install -e ".[test]"
      - run: |
          echo "running"
          pytest -q
"""


def test_ci_workflows_fill_install_and_test(tmp_path: Path) -> None:
    commands = commands_for(tmp_path, {".github/workflows/ci.yml": WORKFLOW})

    assert by_purpose(commands) == {
        "install": ['pip install -e ".[test]"'],
        "test": ["pytest -q"],
    }
    assert commands[0].evidence[0].ref == ".github/workflows/ci.yml"
    assert commands[0].evidence[0].detail == "job test"


def test_higher_priority_source_wins_per_purpose(tmp_path: Path) -> None:
    commands = commands_for(
        tmp_path,
        {
            "Makefile": "test:\n\tpytest\n",
            ".github/workflows/ci.yml": WORKFLOW,
        },
    )

    assert by_purpose(commands) == {
        "install": ['pip install -e ".[test]"'],
        "test": ["make test"],
    }


def test_no_commands_found(tmp_path: Path) -> None:
    assert commands_for(tmp_path, {"main.c": "int main(){}\n"}) == ()


def test_commands_golden(tmp_path: Path, golden: GoldenCheck) -> None:
    repo = FixtureRepo.create(tmp_path, "commands")
    repo.commit(
        "Add project",
        {
            "Makefile": MAKEFILE,
            "package.json": '{"name": "x", "scripts": {"start": "node server.js"}}',
            ".github/workflows/ci.yml": WORKFLOW,
        },
    )

    result = CliRunner().invoke(app, [str(repo.root)])

    assert result.exit_code == 0, result.output
    golden("commands", (repo.root / "TOUR.md").read_bytes().decode("utf-8"))
