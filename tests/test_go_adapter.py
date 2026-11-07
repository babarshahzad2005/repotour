from __future__ import annotations

import itertools
from pathlib import Path

from repotour.languages.go import GoAdapter
from repotour.model.tour import DependencyGraphSection, EntryPointsSection, Tour
from repotour.pipeline import build_tour
from tests.fixtures.builder import FixtureRepo

ADAPTER = GoAdapter()
_counter = itertools.count()

GO_MOD = "module example.com/tool\n\ngo 1.22\n"


def tour_for(tmp_path: Path, files: dict[str, str | bytes | None]) -> Tour:
    repo = FixtureRepo.create(tmp_path, f"go{next(_counter)}")
    repo.commit("Add", files)
    return build_tour(repo.root, use_cache=False).tour


def graph_for(tmp_path: Path, files: dict[str, str | bytes | None]) -> DependencyGraphSection:
    graph = tour_for(tmp_path, files).dependency_graph
    assert graph is not None
    return graph


def test_imports_in_source_order() -> None:
    source = (
        'package main\n\nimport "fmt"\nimport (\n\t"net/http"\n'
        '\tcore "example.com/tool/internal/core"\n\t_ "embed"\n\t`example.com/raw`\n)\n'
    )

    result = ADAPTER.parse(source.encode(), "main.go")

    assert [i.module for i in result.imports] == [
        "fmt",
        "net/http",
        "example.com/tool/internal/core",
        "embed",
        "example.com/raw",
    ]


PROJECT: dict[str, str | bytes | None] = {
    "go.mod": GO_MOD,
    "main.go": (
        'package main\n\nimport "example.com/tool/internal/core"\n\nfunc main() { core.Run() }\n'
    ),
    "internal/core/core.go": (
        'package core\n\nimport "example.com/tool/internal/util"\n\nfunc Run() {}\n'
    ),
    "internal/core/extra.go": "package core\n\nfunc extra() {}\n",
    "internal/util/doc.go": "// Package util has helpers.\npackage util\n",
    "internal/util/strings.go": "package util\n\nfunc Upper() {}\n\nfunc Lower() {}\n",
    "internal/core/core_test.go": "package core\n",
}


def test_imports_link_to_the_representative_file(tmp_path: Path) -> None:
    graph = graph_for(tmp_path, PROJECT)

    assert [(e.source, e.target) for e in graph.edges] == [
        ("internal/core/core.go", "internal/util/doc.go"),
        ("main.go", "internal/core/core.go"),
    ]
    evidence = graph.edges[1].evidence[0]
    assert evidence.ref == "main.go -> internal/core/core.go"


def test_files_in_an_imported_package_are_not_leaves(tmp_path: Path) -> None:
    graph = graph_for(tmp_path, PROJECT)

    assert [leaf.path for leaf in graph.leaves] == []


def test_standard_library_and_third_party_are_external(tmp_path: Path) -> None:
    graph = graph_for(
        tmp_path,
        {
            "go.mod": GO_MOD,
            "main.go": (
                'package main\n\nimport (\n\t"fmt"\n\t"net/http"\n'
                '\t"github.com/spf13/cobra/doc"\n)\n\nfunc main() {}\n'
            ),
        },
    )

    assert graph.external is not None
    assert graph.external.examples == ("fmt", "github.com/spf13/cobra", "net/http")


def test_largest_file_is_the_fallback_representative(tmp_path: Path) -> None:
    graph = graph_for(
        tmp_path,
        {
            "go.mod": GO_MOD,
            "main.go": 'package main\n\nimport "example.com/tool/store"\n\nfunc main() {}\n',
            "store/a.go": "package store\n",
            "store/b.go": "package store\n\nfunc B() {}\n\nfunc C() {}\n",
        },
    )

    assert [(e.source, e.target) for e in graph.edges] == [("main.go", "store/b.go")]


def test_go_work_workspace_modules(tmp_path: Path) -> None:
    graph = graph_for(
        tmp_path,
        {
            "go.work": "go 1.22\n\nuse (\n\t./api\n\t./worker\n)\n",
            "api/go.mod": "module example.com/api\n",
            "api/api.go": "package api\n\nfunc Serve() {}\n",
            "worker/go.mod": "module example.com/worker\n",
            "worker/main.go": 'package main\n\nimport "example.com/api"\n\nfunc main() {}\n',
        },
    )

    assert [(e.source, e.target) for e in graph.edges] == [("worker/main.go", "api/api.go")]


def entry_points(tmp_path: Path, files: dict[str, str | bytes | None]) -> dict[str, str]:
    section = tour_for(tmp_path, files).entry_points
    assert isinstance(section, EntryPointsSection)
    return {f"{e.kind}:{e.path}": e.description for e in section.entries}


def test_go_entry_points(tmp_path: Path) -> None:
    found = entry_points(
        tmp_path,
        {
            "go.mod": GO_MOD,
            "tool.go": "// Package tool does things.\npackage tool\n\nfunc Do() {}\n",
            "cmd/tool/main.go": "package main\n\nfunc main() {}\n",
            "cmd/server/main.go": (
                'package main\n\nimport "net/http"\n\n'
                'func main() { http.ListenAndServe(":80", nil) }\n'
            ),
        },
    )

    assert found["execution:cmd/tool/main.go"] == "Go program (package main)"
    assert found["execution:cmd/server/main.go"] == "Go program (package main); starts a server"
    assert found["public surface:tool.go"] == "root package of module `example.com/tool`"
