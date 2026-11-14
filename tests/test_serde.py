from __future__ import annotations

import json
import typing
from pathlib import Path

import pytest

from repotour.model.history import CommitRecord, FileChange
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


def test_type_hints_are_resolved_once_per_class(monkeypatch: pytest.MonkeyPatch) -> None:
    from repotour.model import serde

    calls: list[type] = []
    real = typing.get_type_hints

    def counting(cls: type) -> dict[str, object]:
        calls.append(cls)
        return real(cls)

    monkeypatch.setattr("repotour.model.serde.get_type_hints", counting)
    serde.clear_caches()
    record = CommitRecord("a" * 40, "Ada", "ada@example.com", 1, (FileChange("x.py", 1, 0),))

    restored = [from_data(CommitRecord, to_data(record)) for _ in range(500)]

    assert restored[-1] == record
    assert sorted(c.__name__ for c in calls) == ["CommitRecord", "FileChange"]


def test_history_cache_round_trips_and_keeps_renames() -> None:
    from repotour.cache.history import _decode, _encode

    records = (
        CommitRecord(
            "b" * 40,
            "Grace",
            "grace@example.com",
            20,
            (FileChange("new.py", 3, 1, old_path="old.py"), FileChange("bin.dat", None, None)),
        ),
        CommitRecord("a" * 40, "Ada", "ada@example.com", 10, ()),
    )

    assert _decode(_encode(records)) == records
