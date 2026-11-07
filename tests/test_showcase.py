"""M1 acceptance: one fixture exercising every overview feature, compared to
its golden tour on every platform in CI."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from repotour.cli import app
from repotour.model.tour import find_unevidenced_claims
from repotour.pipeline import build_tour
from tests.conftest import GoldenCheck
from tests.fixtures.repos import showcase


def test_showcase_golden(tmp_path: Path, golden: GoldenCheck) -> None:
    repo = showcase(tmp_path)

    result = CliRunner().invoke(app, [str(repo.root)])

    assert result.exit_code == 0, result.output
    golden("showcase", (repo.root / "TOUR.md").read_bytes().decode("utf-8"))


def test_showcase_uses_every_overview_feature(tmp_path: Path) -> None:
    tour = build_tour(showcase(tmp_path).root, use_cache=False).tour
    overview = tour.overview
    assert overview is not None

    assert overview.project_types
    assert overview.languages
    assert overview.commands
    assert overview.directories
    assert overview.notes
    assert overview.missing
    assert overview.excluded
    assert overview.submodules
    assert find_unevidenced_claims(tour) == []


def test_directory_holding_only_a_submodule(tmp_path: Path) -> None:
    overview = build_tour(showcase(tmp_path).root, use_cache=False).tour.overview
    assert overview is not None

    external = next(d for d in overview.directories if d.path == "external")
    assert external.purpose == "1 submodule"
