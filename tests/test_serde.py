from __future__ import annotations

import json
from pathlib import Path

from repotour.model.serde import from_data, to_data
from repotour.model.tour import Overview, Tour
from repotour.pipeline import build_tour
from tests.fixtures.repos import polyglot


def test_tour_round_trips_through_json(tmp_path: Path) -> None:
    tour = build_tour(polyglot(tmp_path).root).tour

    restored = from_data(Tour, json.loads(json.dumps(to_data(tour))))

    assert restored == tour


def test_overview_round_trips(tmp_path: Path) -> None:
    overview = build_tour(polyglot(tmp_path).root).tour.overview
    assert overview is not None

    assert from_data(Overview, to_data(overview)) == overview
