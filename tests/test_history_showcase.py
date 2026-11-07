"""M2 acceptance: one fixture exercising every history and ownership feature,
compared to its golden tour on every platform in CI."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from repotour.cli import app
from repotour.config import CliOverrides
from repotour.model.tour import Tour, find_unevidenced_claims
from repotour.pipeline import build_tour
from tests.conftest import GoldenCheck
from tests.fixtures.repos import history_showcase


@pytest.fixture(scope="module")
def root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return history_showcase(tmp_path_factory.mktemp("m2")).root


@pytest.fixture(scope="module")
def tour(root: Path) -> Tour:
    return build_tour(root, use_cache=False).tour


def test_history_showcase_golden(root: Path, golden: GoldenCheck) -> None:
    result = CliRunner().invoke(app, [str(root), "--force", "--no-cache"])

    assert result.exit_code == 0, result.output
    golden("history-showcase", (root / "TOUR.md").read_bytes().decode("utf-8"))


def test_every_history_feature_is_present(tour: Tour) -> None:
    hotspots, ownership = tour.hotspots, tour.ownership
    assert hotspots is not None
    assert ownership is not None
    entries = {e.path: e for e in ownership.entries}

    # Renames: in the 6-month window (from 2024-06-04) the engine has 10 commits.
    engine = next(h for h in hotspots.files if h.path == "core/engine.py")
    assert engine.commits == 10
    # Bulk commits: the whitespace reformat is left out and reported.
    assert hotspots.bulk is not None
    assert hotspots.bulk.count == 1
    # Mailmap: the old identity is merged; bots never appear.
    names = {a.name for e in ownership.entries for a in e.authors}
    assert names == {"Ada Lovelace", "Grace Hopper", "Linus Ops"}
    # Bus factor: Ada made every change to core/ across 11 commits.
    assert entries["core"].bus_factor is not None
    assert entries["core"].bus_factor.name == "Ada Lovelace"
    assert entries["web"].bus_factor is None
    # Activity and contacts.
    assert entries["legacy"].activity is not None
    assert entries["legacy"].activity.state == "stable"
    assert entries["web"].activity is not None
    assert entries["web"].activity.state == "active"
    assert [c.name for c in entries["web"].contacts] == ["Grace Hopper", "Linus Ops"]
    assert entries["legacy"].contacts == ()


def test_commits_before_a_rename_count_under_the_new_path(root: Path) -> None:
    year = build_tour(root, CliOverrides(since="1y"), use_cache=False).tour.hotspots
    assert year is not None

    engine = next(h for h in year.files if h.path == "core/engine.py")
    assert engine.commits == 11  # includes "Start core", made as core/old_engine.py
    assert "core/old_engine.py" not in {h.path for h in year.files}


def test_every_claim_has_evidence(tour: Tour) -> None:
    assert find_unevidenced_claims(tour) == []
