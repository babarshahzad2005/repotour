"""Regression tests for problems found by touring Flask, Express, and fzf."""

from __future__ import annotations

import itertools
from pathlib import Path

from repotour.model.tour import Tour
from repotour.pipeline import build_tour
from repotour.scan.filetypes import is_peripheral
from tests.fixtures.builder import FixtureRepo

_counter = itertools.count()
MAIN = "if __name__ == '__main__':\n    pass\n"


def tour_for(tmp_path: Path, files: dict[str, str | bytes | None]) -> Tour:
    repo = FixtureRepo.create(tmp_path, f"lesson{next(_counter)}")
    repo.commit("Add", files)
    return build_tour(repo.root, use_cache=False).tour


def test_peripheral_directories() -> None:
    assert is_peripheral("examples/app/main.py")
    assert is_peripheral("docs/conf.py")
    assert is_peripheral("benchmarks/run.py")
    assert not is_peripheral("src/examples.py")
    assert not is_peripheral("src/app/main.py")


def test_examples_never_lead_the_reading_order(tmp_path: Path) -> None:
    tour = tour_for(
        tmp_path,
        {
            "examples/hello/app.py": "import lib\n\n" + MAIN,
            "examples/other/app.py": MAIN,
            "lib/__init__.py": "from lib import core\n",
            "lib/core.py": "x = 1\n",
            "lib/cli.py": "from lib import core\n\n" + MAIN,
        },
    )
    assert tour.reading_order is not None

    steps = [s.path for s in tour.reading_order.steps]
    assert steps[0] == "lib/cli.py"
    assert all(not is_peripheral(p) for p in steps[:3])


def test_examples_come_last_among_entry_points(tmp_path: Path) -> None:
    tour = tour_for(tmp_path, {"examples/a.py": MAIN, "zzz.py": MAIN})
    assert tour.entry_points is not None

    assert [e.path for e in tour.entry_points.entries] == ["zzz.py", "examples/a.py"]


def test_examples_are_never_core_or_leaf_modules(tmp_path: Path) -> None:
    tour = tour_for(
        tmp_path,
        {
            "examples/db.py": "x = 1\n",
            "examples/a.py": "import db\n",
            "examples/b.py": "import db\n",
            "lib.py": "y = 1\n",
            "main.py": "import lib\n\n" + MAIN,
        },
    )
    graph = tour.dependency_graph
    assert graph is not None

    assert {c.path for c in graph.core} == {"lib.py"}
    assert all(not is_peripheral(leaf.path) for leaf in graph.leaves)


def test_package_json_without_main_defaults_to_index_js(tmp_path: Path) -> None:
    tour = tour_for(
        tmp_path,
        {
            "package.json": '{"name": "expressish", "version": "5.0.0"}',
            "index.js": "module.exports = require('./lib/app');\n",
            "lib/app.js": "module.exports = {};\n",
        },
    )
    assert tour.overview is not None
    assert tour.entry_points is not None

    assert [t.kind for t in tour.overview.project_types] == ["library"]
    public = {
        e.path: e.description for e in tour.entry_points.entries if e.kind == "public surface"
    }
    assert public == {"index.js": 'package main (`package.json` "main")'}


def test_relative_require_of_the_root_resolves_to_index_js(tmp_path: Path) -> None:
    tour = tour_for(
        tmp_path,
        {
            "index.js": "module.exports = 1;\n",
            "examples/auth/index.js": "const express = require('../..');\n",
        },
    )
    graph = tour.dependency_graph
    assert graph is not None

    assert [(e.source, e.target) for e in graph.edges] == [("examples/auth/index.js", "index.js")]
    assert graph.external is None


def test_unresolved_relative_imports_are_not_external_packages(tmp_path: Path) -> None:
    tour = tour_for(tmp_path, {"a.js": "require('./missing');\n", "b.py": "from . import gone\n"})
    graph = tour.dependency_graph
    assert graph is not None

    assert graph.external is None


def test_python_m_uses_the_source_root_name(tmp_path: Path) -> None:
    tour = tour_for(
        tmp_path, {"src/flaskish/__init__.py": "", "src/flaskish/__main__.py": "x = 1\n"}
    )
    assert tour.entry_points is not None

    entry = next(e for e in tour.entry_points.entries if e.path.endswith("__main__.py"))
    assert entry.description == "runs with `python -m flaskish`"


def test_ci_expressions_are_not_quoted_as_commands(tmp_path: Path) -> None:
    workflow = (
        "jobs:\n  tests:\n    steps:\n"
        "      - run: uv run tox run -e ${{ matrix.tox }}\n"
        "      - run: uv run tox run -e typing\n"
    )
    tour = tour_for(tmp_path, {".github/workflows/tests.yaml": workflow})
    assert tour.overview is not None

    assert [c.command for c in tour.overview.commands] == ["uv run tox run -e typing"]


def test_continued_recipe_lines_end_with_an_ellipsis(tmp_path: Path) -> None:
    makefile = 'test:\n\tgo test -v -tags "$(TAGS)" \\\n\t\t./src/...\n'
    tour = tour_for(tmp_path, {"Makefile": makefile})
    assert tour.overview is not None

    detail = tour.overview.commands[0].evidence[0].detail
    assert detail == 'target test: go test -v -tags "$(TAGS)" …'


def test_go_library_evidence_names_each_package_once(tmp_path: Path) -> None:
    tour = tour_for(
        tmp_path,
        {
            "go.mod": "module example.com/x\n",
            "main.go": "package main\n\nfunc main() {}\n",
            "src/algo/algo.go": "package algo\n",
            "src/algo/indexbyte_amd64.go": "package algo\n",
            "src/algo/indexbyte_arm64.go": "package algo\n",
        },
    )
    assert tour.overview is not None

    library = next(t for t in tour.overview.project_types if t.kind == "library")
    assert [e.ref for e in library.evidence] == ["src/algo/algo.go"]
