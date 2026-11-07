from __future__ import annotations

import itertools
from pathlib import Path

from typer.testing import CliRunner

from repotour.cli import app
from repotour.model.tour import DependencyGraphSection, Tour
from repotour.pipeline import build_tour
from repotour.render.mermaid import render_mermaid
from tests.conftest import GoldenCheck
from tests.fixtures.builder import FixtureRepo

_counter = itertools.count()


def tour_for(tmp_path: Path, files: dict[str, str | bytes | None]) -> Tour:
    repo = FixtureRepo.create(tmp_path, f"graph{next(_counter)}")
    repo.commit("Add", files)
    return build_tour(repo.root, use_cache=False).tour


def graph_for(tmp_path: Path, files: dict[str, str | bytes | None]) -> DependencyGraphSection:
    graph = tour_for(tmp_path, files).dependency_graph
    assert graph is not None
    return graph


def edges(graph: DependencyGraphSection) -> list[tuple[str, str]]:
    return [(e.source, e.target) for e in graph.edges]


def test_absolute_imports_of_top_level_packages(tmp_path: Path) -> None:
    graph = graph_for(
        tmp_path,
        {
            "app/__init__.py": "",
            "app/main.py": "import app.db\nfrom app import util\n",
            "app/db.py": "",
            "app/util.py": "",
        },
    )

    assert edges(graph) == [("app/main.py", "app/db.py"), ("app/main.py", "app/util.py")]


def test_relative_imports(tmp_path: Path) -> None:
    graph = graph_for(
        tmp_path,
        {
            "pkg/__init__.py": "from .core import run\n",
            "pkg/core.py": "from . import helpers\nfrom .sub.deep import thing\n",
            "pkg/helpers.py": "",
            "pkg/sub/__init__.py": "",
            "pkg/sub/deep.py": "from .. import helpers\n",
        },
    )

    assert edges(graph) == [
        ("pkg/__init__.py", "pkg/core.py"),
        ("pkg/core.py", "pkg/helpers.py"),
        ("pkg/core.py", "pkg/sub/deep.py"),
        ("pkg/sub/deep.py", "pkg/helpers.py"),
    ]


def test_src_layout(tmp_path: Path) -> None:
    graph = graph_for(
        tmp_path,
        {
            "src/flaskish/__init__.py": "from flaskish.app import App\n",
            "src/flaskish/app.py": "from flaskish import config\n",
            "src/flaskish/config.py": "",
        },
    )

    assert edges(graph) == [
        ("src/flaskish/__init__.py", "src/flaskish/app.py"),
        ("src/flaskish/app.py", "src/flaskish/config.py"),
    ]


def test_from_package_import_attribute_points_to_init(tmp_path: Path) -> None:
    graph = graph_for(
        tmp_path,
        {"pkg/__init__.py": "VALUE = 1\n", "main.py": "from pkg import VALUE\n"},
    )

    assert edges(graph) == [("main.py", "pkg/__init__.py")]


def test_one_from_import_can_point_to_several_modules(tmp_path: Path) -> None:
    graph = graph_for(
        tmp_path,
        {
            "pkg/__init__.py": "NAME = 1\n",
            "pkg/a.py": "",
            "pkg/b.py": "",
            "main.py": "from pkg import a, b, NAME\n",
        },
    )

    assert edges(graph) == [
        ("main.py", "pkg/__init__.py"),
        ("main.py", "pkg/a.py"),
        ("main.py", "pkg/b.py"),
    ]


def test_external_imports_are_counted_not_drawn(tmp_path: Path) -> None:
    graph = graph_for(
        tmp_path,
        {"main.py": "import os\nimport json\nfrom requests import get\nimport os.path\n"},
    )

    assert edges(graph) == []
    assert graph.external is not None
    assert graph.external.count == 3
    assert graph.external.examples == ("json", "os", "requests")


def test_every_edge_cites_the_import(tmp_path: Path) -> None:
    graph = graph_for(tmp_path, {"a.py": "\nimport b\n", "b.py": ""})

    evidence = graph.edges[0].evidence[0]
    assert (evidence.kind, evidence.ref, evidence.detail) == ("import", "a.py -> b.py", "line 2")


def test_tests_generated_and_vendored_files_are_left_out(tmp_path: Path) -> None:
    graph = graph_for(
        tmp_path,
        {
            "app.py": "import lib\n",
            "lib.py": "",
            "tests/test_app.py": "import app\n",
            "vendor/thing.py": "import app\n",
            "gen/api_pb2.py": "import app\n",
        },
    )

    assert [n.id for n in graph.nodes] == ["app.py", "lib.py"]
    assert edges(graph) == [("app.py", "lib.py")]


def test_unparseable_files_warn_and_are_skipped(tmp_path: Path) -> None:
    tour = tour_for(tmp_path, {"good.py": "import bad\n", "bad.py": "def broken(:\n"})

    assert tour.dependency_graph is not None
    assert "bad.py" not in {e.source for e in tour.dependency_graph.edges}
    assert "Could not parse bad.py; left out of the dependency graph" in tour.warnings


def test_no_supported_language(tmp_path: Path) -> None:
    graph = graph_for(tmp_path, {"main.c": "int main(){}\n"})

    assert graph.nodes == ()
    assert graph.languages == ()


def test_mermaid_is_deterministic_and_well_formed(tmp_path: Path) -> None:
    graph = graph_for(
        tmp_path,
        {"z.py": "import a\n", "a.py": "import m\n", "m.py": "", "lone.py": ""},
    )

    text = render_mermaid(graph)

    assert text == render_mermaid(graph)
    lines = text.splitlines()
    assert lines[0] == "flowchart LR"
    assert '    n0["a.py"]' in lines
    assert "    n0 --> n2" in lines  # a.py -> m.py
    assert all(not line.strip() or line.startswith(("flowchart", "    ")) for line in lines)


def test_graph_golden(tmp_path: Path, golden: GoldenCheck) -> None:
    repo = FixtureRepo.create(tmp_path, "graph")
    repo.commit(
        "Add",
        {
            "src/shop/__init__.py": "from shop.app import create\n",
            "src/shop/app.py": "from shop import db, views\nimport os\n",
            "src/shop/db.py": "import sqlite3\n",
            "src/shop/views.py": "from .db import query\n",
            "tests/test_app.py": "import shop\n",
        },
    )

    result = CliRunner().invoke(app, [str(repo.root)])

    assert result.exit_code == 0, result.output
    golden("graph", (repo.root / "TOUR.md").read_bytes().decode("utf-8"))
