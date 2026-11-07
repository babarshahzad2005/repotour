from __future__ import annotations

import itertools
from pathlib import Path

from typer.testing import CliRunner

from repotour.cli import app
from repotour.config import CliOverrides
from repotour.model.tour import DependencyGraphSection
from repotour.pipeline import build_tour
from tests.conftest import GoldenCheck
from tests.fixtures.builder import FixtureRepo

_counter = itertools.count()
SMALL = "version: 1\nthresholds:\n  graph_max_nodes: 3\n"


def graph_for(
    tmp_path: Path, files: dict[str, str | bytes | None], *, full: bool = False
) -> DependencyGraphSection:
    repo = FixtureRepo.create(tmp_path, f"shape{next(_counter)}")
    repo.commit("Add", files)
    overrides = CliOverrides(full_graph=True) if full else None
    graph = build_tour(repo.root, overrides, use_cache=False).tour.dependency_graph
    assert graph is not None
    return graph


STAR: dict[str, str | bytes | None] = {
    "core.py": "",
    "a.py": "import core\n",
    "b.py": "import core\n",
    "c.py": "import core\nimport util\n",
    "util.py": "",
    "main.py": "import a\n\nif __name__ == '__main__':\n    pass\n",
}


def test_core_modules_are_the_most_depended_on(tmp_path: Path) -> None:
    graph = graph_for(tmp_path, STAR)

    assert [(c.path, c.importers, c.rank) for c in graph.core] == [("core.py", 3, 1)]
    assert graph.core[0].evidence[0].detail == "imported by 3 modules; PageRank 1 of 6"


def test_leaf_modules_exclude_entry_points(tmp_path: Path) -> None:
    graph = graph_for(tmp_path, STAR)

    # b.py and c.py import things but nothing imports them; main.py is an entry point.
    assert [leaf.path for leaf in graph.leaves] == ["b.py", "c.py"]


def test_empty_files_are_not_leaf_modules(tmp_path: Path) -> None:
    graph = graph_for(
        tmp_path, {"pkg/__init__.py": "", "pkg/sub/__init__.py": "", "tool.py": "x = 1\n"}
    )

    assert [leaf.path for leaf in graph.leaves] == ["tool.py"]


def test_large_graph_collapses_to_directories(tmp_path: Path) -> None:
    files: dict[str, str | bytes | None] = {".repotour.yml": SMALL}
    for d in range(3):
        files[f"pkg/d{d}/__init__.py"] = ""
        files[f"pkg/d{d}/m.py"] = f"from pkg.d{(d + 1) % 3} import m\n"

    graph = graph_for(tmp_path, files)

    assert graph.modules == 6
    assert graph.depth == 2
    assert [(n.id, n.modules) for n in graph.nodes] == [
        ("pkg/d0", 2),
        ("pkg/d1", 2),
        ("pkg/d2", 2),
    ]
    assert [(e.source, e.target, e.count) for e in graph.edges] == [
        ("pkg/d0", "pkg/d1", 1),
        ("pkg/d1", "pkg/d2", 1),
        ("pkg/d2", "pkg/d0", 1),
    ]
    assert graph.edges[0].evidence[0].ref == "pkg/d0/m.py -> pkg/d1/m.py"


def test_full_graph_draws_every_module(tmp_path: Path) -> None:
    files: dict[str, str | bytes | None] = {".repotour.yml": SMALL}
    files.update({f"m{i}.py": "" for i in range(5)})

    assert graph_for(tmp_path, files).depth == 1
    assert graph_for(tmp_path, files, full=True).depth == 0


def test_top_level_overflow_reports_omitted(tmp_path: Path) -> None:
    files: dict[str, str | bytes | None] = {".repotour.yml": SMALL}
    files.update({f"t{i}/m.py": "" for i in range(5)})

    graph = graph_for(tmp_path, files)

    assert len(graph.nodes) == 3
    assert graph.omitted == 2


def test_full_graph_option_changes_the_config_hash(tmp_path: Path) -> None:
    repo = FixtureRepo.create(tmp_path, "hash")
    repo.commit("Add", {"a.py": ""})

    plain = build_tour(repo.root, use_cache=False).tour.meta.config_hash
    overrides = CliOverrides(full_graph=True)
    full = build_tour(repo.root, overrides, use_cache=False).tour.meta.config_hash

    assert plain != full


def test_collapsed_golden(tmp_path: Path, golden: GoldenCheck) -> None:
    repo = FixtureRepo.create(tmp_path, "collapsed")
    files: dict[str, str | bytes | None] = {".repotour.yml": SMALL, "STAR/README.md": "x\n"}
    for d in range(3):
        files[f"pkg/d{d}/__init__.py"] = ""
        files[f"pkg/d{d}/m.py"] = f"from pkg.d{(d + 1) % 3} import m\n"
    repo.commit("Add", files)

    result = CliRunner().invoke(app, [str(repo.root)])

    assert result.exit_code == 0, result.output
    golden("collapsed", (repo.root / "TOUR.md").read_bytes().decode("utf-8"))
