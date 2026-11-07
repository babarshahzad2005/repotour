from __future__ import annotations

import itertools
from pathlib import Path

import pytest

from repotour.languages.javascript import JavaScriptAdapter
from repotour.model.tour import DependencyGraphSection, EntryPointsSection, Tour
from repotour.pipeline import build_tour
from tests.fixtures.builder import FixtureRepo

ADAPTER = JavaScriptAdapter()
_counter = itertools.count()


def modules(source: str, path: str = "a.ts") -> list[str]:
    result = ADAPTER.parse(source.encode("utf-8"), path)
    assert not result.has_error
    return [i.module for i in result.imports]


def tour_for(tmp_path: Path, files: dict[str, str | bytes | None]) -> Tour:
    repo = FixtureRepo.create(tmp_path, f"js{next(_counter)}")
    repo.commit("Add", files)
    return build_tour(repo.root, use_cache=False).tour


def edges(tmp_path: Path, files: dict[str, str | bytes | None]) -> list[tuple[str, str]]:
    graph = tour_for(tmp_path, files).dependency_graph
    assert isinstance(graph, DependencyGraphSection)
    return [(e.source, e.target) for e in graph.edges]


# --- parsing -----------------------------------------------------------------------


def test_static_imports_exports_and_literal_requires() -> None:
    source = (
        "import a from './a';\n"
        'export { b } from "../b";\n'
        "export * from './all';\n"
        "const c = require('c');\n"
        "const d = await import('./d');\n"
        "require(name);\n"
    )

    assert modules(source, "x.js") == ["./a", "../b", "./all", "c"]


def test_typescript_import_equals_require() -> None:
    assert modules("import legacy = require('./legacy');\n", "x.ts") == ["./legacy"]


def test_typescript_casts_parse_with_the_typescript_grammar() -> None:
    assert modules("import a from './a';\nconst v = <number>a;\n", "x.ts") == ["./a"]


def test_tsx_uses_the_tsx_grammar() -> None:
    assert modules("import B from './B';\nexport const A = () => <B />;\n", "x.tsx") == ["./B"]


@pytest.mark.parametrize("path", ["a.js", "a.jsx", "a.mjs", "a.cjs", "a.ts", "a.tsx", "a.mts"])
def test_handles_js_and_ts_extensions(path: str) -> None:
    assert ADAPTER.handles(path)


# --- resolution --------------------------------------------------------------------


def test_relative_paths_extensions_and_index_files(tmp_path: Path) -> None:
    assert edges(
        tmp_path,
        {
            "src/app.ts": (
                "import { db } from './db';\nimport ui from './ui';\nimport h from '../lib/h.js';\n"
            ),
            "src/db.ts": "",
            "src/ui/index.tsx": "",
            "lib/h.ts": "",
        },
    ) == [
        ("src/app.ts", "lib/h.ts"),
        ("src/app.ts", "src/db.ts"),
        ("src/app.ts", "src/ui/index.tsx"),
    ]


def test_tsconfig_paths_and_base_url(tmp_path: Path) -> None:
    tsconfig = """{
      // comments are allowed in tsconfig
      "compilerOptions": {
        "baseUrl": ".",
        "paths": { "@/*": ["src/*"] },
      },
    }"""

    assert edges(
        tmp_path,
        {
            "tsconfig.json": tsconfig,
            "src/main.ts": "import { x } from '@/util/x';\nimport y from 'src/y';\n",
            "src/util/x.ts": "",
            "src/y.ts": "",
        },
    ) == [("src/main.ts", "src/util/x.ts"), ("src/main.ts", "src/y.ts")]


def test_workspace_packages(tmp_path: Path) -> None:
    assert edges(
        tmp_path,
        {
            "package.json": '{"private": true, "workspaces": ["packages/*"]}',
            "packages/core/package.json": '{"name": "@acme/core", "main": "lib/index.js"}',
            "packages/core/lib/index.js": "",
            "packages/core/lib/extra.js": "",
            "packages/cli/package.json": '{"name": "@acme/cli"}',
            "packages/cli/index.js": (
                "const core = require('@acme/core');\nconst e = require('@acme/core/lib/extra');\n"
            ),
        },
    ) == [
        ("packages/cli/index.js", "packages/core/lib/extra.js"),
        ("packages/cli/index.js", "packages/core/lib/index.js"),
    ]


def test_external_packages_are_counted_by_name(tmp_path: Path) -> None:
    graph = tour_for(
        tmp_path,
        {"index.js": "const e = require('express');\nimport { x } from '@scope/pkg/sub';\n"},
    ).dependency_graph
    assert graph is not None

    assert graph.external is not None
    assert graph.external.examples == ("@scope/pkg", "express")


def test_mixed_javascript_and_typescript(tmp_path: Path) -> None:
    graph = tour_for(tmp_path, {"a.ts": "import b from './b';\n", "b.js": ""}).dependency_graph
    assert graph is not None

    assert graph.languages == ("JavaScript/TypeScript",)
    assert [(e.source, e.target) for e in graph.edges] == [("a.ts", "b.js")]


# --- entry points ------------------------------------------------------------------


def entry_points(tmp_path: Path, files: dict[str, str | bytes | None]) -> dict[str, str]:
    section = tour_for(tmp_path, files).entry_points
    assert isinstance(section, EntryPointsSection)
    return {f"{e.kind}:{e.path}": e.description for e in section.entries}


def test_package_json_main_exports_and_bin(tmp_path: Path) -> None:
    found = entry_points(
        tmp_path,
        {
            "package.json": (
                '{"name": "lib", "main": "index.js", '
                '"exports": {".": {"import": "./esm/index.mjs"}}, "bin": {"lib": "cli.js"}}'
            ),
            "index.js": "module.exports = 1;\n",
            "esm/index.mjs": "export default 1;\n",
            "cli.js": "require('./index');\n",
        },
    )

    assert found["public surface:index.js"] == 'package main (`package.json` "main")'
    assert found["public surface:esm/index.mjs"] == 'package exports (`package.json` "exports")'
    assert found["execution:cli.js"] == 'package binary `lib` (`package.json` "bin")'


def test_server_startup_and_main_module_guard(tmp_path: Path) -> None:
    found = entry_points(
        tmp_path,
        {
            "server.js": "const app = express();\napp.listen(3000);\n",
            "tool.js": "if (require.main === module) {\n  run();\n}\n",
        },
    )

    assert found["execution:server.js"] == "starts a server"
    assert found["execution:tool.js"] == "runs as a script"
