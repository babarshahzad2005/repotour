"""M3 acceptance: one fixture exercising the dependency graph, entry points,
and reading order across Python, JavaScript/TypeScript, and Go, compared to
its golden tour on every platform in CI."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from repotour.cli import app
from repotour.model.tour import Tour, find_unevidenced_claims
from repotour.pipeline import build_tour
from tests.conftest import GoldenCheck
from tests.fixtures.repos import graph_showcase


@pytest.fixture(scope="module")
def root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return graph_showcase(tmp_path_factory.mktemp("m3")).root


@pytest.fixture(scope="module")
def tour(root: Path) -> Tour:
    return build_tour(root, use_cache=False).tour


def test_graph_showcase_golden(root: Path, golden: GoldenCheck) -> None:
    result = CliRunner().invoke(app, [str(root), "--force", "--no-cache"])

    assert result.exit_code == 0, result.output
    golden("graph-showcase", (root / "TOUR.md").read_bytes().decode("utf-8"))


def test_every_m3_feature_is_present(tour: Tour) -> None:
    graph, entries, order = tour.dependency_graph, tour.entry_points, tour.reading_order
    assert graph is not None
    assert entries is not None
    assert order is not None

    # All three languages, collapsed because the graph exceeds 8 modules.
    assert graph.languages == ("Go", "JavaScript/TypeScript", "Python")
    assert graph.modules > 8
    assert graph.depth > 0
    assert graph.core
    assert {leaf.path for leaf in graph.leaves} == {"shop/legacy.py"}
    # Entry points of both kinds in every language.
    found = {(e.kind, e.path) for e in entries.entries}
    assert ("execution", "shop/cli.py") in found
    assert ("execution", "web/src/server.ts") in found
    assert ("execution", "service/cmd/svc/main.go") in found
    assert ("public surface", "shop/__init__.py") in found
    assert ("public surface", "web/src/server.ts") in found
    # The reading order starts at an entry point and follows imports.
    steps = [s.path for s in order.steps]
    assert len(steps) == 5
    assert steps[0] in {e.path for e in entries.entries}
    assert all(s.reason for s in order.steps)


def test_every_claim_has_evidence(tour: Tour) -> None:
    assert find_unevidenced_claims(tour) == []
