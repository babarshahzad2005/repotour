from __future__ import annotations

import itertools
from pathlib import Path

import pytest
from typer.testing import CliRunner

from repotour.cli import app
from repotour.model.tour import Overview
from repotour.pipeline import build_tour
from tests.conftest import GoldenCheck
from tests.fixtures.builder import FixtureRepo

_counter = itertools.count()


def overview_for(tmp_path: Path, files: dict[str, str | bytes | None]) -> Overview:
    repo = FixtureRepo.create(tmp_path, f"project{next(_counter)}")
    repo.commit("Add project", files)
    overview = build_tour(repo.root, use_cache=False).tour.overview
    assert overview is not None
    return overview


def kinds(overview: Overview) -> list[str]:
    return [t.kind for t in overview.project_types]


def evidence_refs(overview: Overview, kind: str) -> list[str]:
    claim = next(t for t in overview.project_types if t.kind == kind)
    return [e.ref for e in claim.evidence]


PYPROJECT_LIB_CLI = """\
[project]
name = "flaskish"
dependencies = ["werkzeug>=3", "jinja2"]

[project.scripts]
flaskish = "flaskish.cli:main"
"""


def test_python_library_and_cli(tmp_path: Path) -> None:
    overview = overview_for(
        tmp_path, {"pyproject.toml": PYPROJECT_LIB_CLI, "src/f/__init__.py": ""}
    )

    assert kinds(overview) == ["library", "CLI"]
    assert evidence_refs(overview, "CLI") == ["pyproject.toml"]
    cli = next(t for t in overview.project_types if t.kind == "CLI")
    assert cli.evidence[0].detail == "[project.scripts]"


def test_python_web_app_from_dependencies(tmp_path: Path) -> None:
    pyproject = '[project]\nname = "shop"\ndependencies = ["Django>=5", "psycopg"]\n'

    overview = overview_for(tmp_path, {"pyproject.toml": pyproject})

    assert kinds(overview) == ["web app"]
    assert "django" in (overview.project_types[0].evidence[0].detail or "")


def test_django_manage_py(tmp_path: Path) -> None:
    overview = overview_for(tmp_path, {"manage.py": "import django\n"})

    assert kinds(overview) == ["web app"]


def test_js_library_with_bin(tmp_path: Path) -> None:
    package = '{"name": "expressish", "main": "index.js", "bin": {"x": "bin/x.js"}}'

    overview = overview_for(tmp_path, {"package.json": package})

    assert kinds(overview) == ["library", "CLI"]


def test_js_web_app(tmp_path: Path) -> None:
    package = '{"name": "site", "private": true, "dependencies": {"react": "^19", "next": "15"}}'

    overview = overview_for(tmp_path, {"package.json": package})

    assert kinds(overview) == ["web app"]


def test_go_cli_and_library(tmp_path: Path) -> None:
    overview = overview_for(
        tmp_path,
        {
            "go.mod": "module example.com/tool\n\ngo 1.22\n",
            "main.go": "package main\n\nfunc main() {}\n",
            "src/core.go": "package core\n",
        },
    )

    assert kinds(overview) == ["library", "CLI"]
    assert evidence_refs(overview, "CLI") == ["main.go"]


def test_go_server_is_a_web_app(tmp_path: Path) -> None:
    overview = overview_for(
        tmp_path,
        {
            "go.mod": "module example.com/srv\n",
            "cmd/srv/main.go": 'package main\n\nimport "net/http"\n\n'
            'func main() { http.ListenAndServe(":8080", nil) }\n',
        },
    )

    assert kinds(overview) == ["web app"]


def test_dockerfile_expose_is_a_web_app(tmp_path: Path) -> None:
    overview = overview_for(tmp_path, {"Dockerfile": "FROM python:3.12\nEXPOSE 8000\n"})

    assert kinds(overview) == ["web app"]
    assert overview.project_types[0].evidence[0].detail == "EXPOSE 8000"


def test_rust_manifests(tmp_path: Path) -> None:
    overview = overview_for(
        tmp_path,
        {"Cargo.toml": '[package]\nname = "r"\n', "src/lib.rs": "", "src/main.rs": ""},
    )

    assert kinds(overview) == ["library", "CLI"]


def test_unknown_when_nothing_matches(tmp_path: Path) -> None:
    overview = overview_for(tmp_path, {"notes.txt": "hello\n"})

    assert overview.project_types == ()


def test_npm_workspaces_monorepo_lists_packages(tmp_path: Path) -> None:
    overview = overview_for(
        tmp_path,
        {
            "package.json": '{"name": "root", "private": true, "workspaces": ["packages/*"]}',
            "packages/core/package.json": '{"name": "@acme/core", "main": "index.js"}',
            "packages/cli/package.json": '{"name": "@acme/cli", "bin": "cli.js"}',
            "node_modules/dep/package.json": '{"name": "dep"}',
        },
    )

    assert kinds(overview)[0] == "monorepo"
    assert {"library", "CLI"} <= set(kinds(overview))
    assert [(p.path, p.name) for p in overview.packages] == [
        ("packages/cli", "@acme/cli"),
        ("packages/core", "@acme/core"),
    ]
    assert overview.packages[0].evidence[0].ref == "packages/cli/package.json"


def test_pnpm_workspace(tmp_path: Path) -> None:
    overview = overview_for(
        tmp_path,
        {
            "pnpm-workspace.yaml": "packages:\n  - 'apps/*'\n",
            "apps/web/package.json": '{"name": "web", "private": true}',
        },
    )

    assert kinds(overview)[0] == "monorepo"
    assert [p.path for p in overview.packages] == ["apps/web"]


def test_go_work(tmp_path: Path) -> None:
    overview = overview_for(
        tmp_path,
        {
            "go.work": "go 1.22\n\nuse (\n\t./api\n\t./worker\n)\n",
            "api/go.mod": "module example.com/api\n",
            "worker/go.mod": "module example.com/worker\n",
        },
    )

    assert kinds(overview)[0] == "monorepo"
    assert [(p.path, p.name) for p in overview.packages] == [
        ("api", "example.com/api"),
        ("worker", "example.com/worker"),
    ]


def test_multiple_top_level_manifests(tmp_path: Path) -> None:
    overview = overview_for(
        tmp_path,
        {
            "frontend/package.json": '{"name": "frontend", "private": true}',
            "backend/pyproject.toml": '[project]\nname = "backend"\n',
        },
    )

    assert kinds(overview)[0] == "monorepo"
    assert [p.path for p in overview.packages] == ["backend", "frontend"]


def test_invalid_manifest_warns_and_continues(tmp_path: Path) -> None:
    repo = FixtureRepo.create(tmp_path, "broken")
    repo.commit("Add", {"package.json": "{not json", "pyproject.toml": PYPROJECT_LIB_CLI})

    tour = build_tour(repo.root, use_cache=False).tour

    assert tour.overview is not None
    assert [t.kind for t in tour.overview.project_types] == ["library", "CLI"]
    assert any("package.json" in w and "could not be parsed" in w for w in tour.warnings)


@pytest.mark.parametrize("kind", ["web app", "library", "CLI", "monorepo"])
def test_every_type_carries_evidence(tmp_path: Path, kind: str) -> None:
    overview = overview_for(
        tmp_path,
        {
            "package.json": '{"name": "r", "private": true, "workspaces": ["p/*"]}',
            "p/a/package.json": '{"name": "a", "main": "i.js", "bin": "c.js"}',
            "Dockerfile": "EXPOSE 80\n",
        },
    )

    claim = next(t for t in overview.project_types if t.kind == kind)
    assert claim.evidence


def test_monorepo_golden(tmp_path: Path, golden: GoldenCheck) -> None:
    repo = FixtureRepo.create(tmp_path, "monorepo")
    repo.commit(
        "Add workspace",
        {
            "package.json": '{"name": "root", "private": true, "workspaces": ["packages/*"]}',
            "packages/core/package.json": '{"name": "@acme/core", "main": "index.js"}',
            "packages/core/index.js": "module.exports = {};\n",
            "packages/cli/package.json": '{"name": "@acme/cli", "bin": "cli.js"}',
            "packages/cli/cli.js": "require('@acme/core');\n",
            "Dockerfile": "FROM node:22\nEXPOSE 3000\n",
        },
    )

    result = CliRunner().invoke(app, [str(repo.root)])

    assert result.exit_code == 0, result.output
    golden("monorepo", (repo.root / "TOUR.md").read_bytes().decode("utf-8"))
