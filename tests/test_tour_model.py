from __future__ import annotations

import json
from pathlib import Path

from repotour.model.tour import (
    EntryPoint,
    EntryPointsSection,
    Evidence,
    FileSummary,
    Meta,
    ReadingOrderSection,
    ReadingStep,
    Tour,
    find_unevidenced_claims,
)
from repotour.pipeline import build_tour
from tests.fixtures.repos import minimal

META = Meta(repo_name="demo", head_commit="0" * 40, tool_version="0.0.0", config_hash="c" * 64)

FILE = (Evidence(kind="file", ref="a.py"),)


def summary(evidence: tuple[Evidence, ...]) -> FileSummary:
    return FileSummary(path="a.py", text="ok", model="m", evidence=evidence)


def test_every_claim_in_a_real_tour_has_evidence(tmp_path: Path) -> None:
    tour = build_tour(minimal(tmp_path).root).tour

    assert find_unevidenced_claims(tour) == []


def test_claim_without_evidence_is_flagged() -> None:
    bare = summary(evidence=())
    tour = Tour(meta=META, summaries=(bare,))

    assert find_unevidenced_claims(tour) == [bare]


def test_nested_claim_without_evidence_is_flagged() -> None:
    bare = EntryPoint(path="a.py", kind="execution", description="script", evidence=())
    good = ReadingStep(path="a.py", reason="entry point", evidence=FILE)
    tour = Tour(
        meta=META,
        entry_points=EntryPointsSection(entries=(bare,)),
        reading_order=ReadingOrderSection(steps=(good,)),
    )

    assert find_unevidenced_claims(tour) == [bare]


def test_claims_with_evidence_pass() -> None:
    tour = Tour(meta=META, summaries=(summary(FILE),))

    assert find_unevidenced_claims(tour) == []


def test_tour_model_is_json_serializable() -> None:
    fact = summary((Evidence(kind="import", ref="a.py -> b.py"),))
    tour = Tour(meta=META, summaries=(fact,), warnings=("something was skipped",))

    data = json.loads(json.dumps(tour.to_dict()))

    assert data["meta"]["repo_name"] == "demo"
    assert data["summaries"][0]["evidence"][0]["ref"] == "a.py -> b.py"
    assert set(data) == {
        "meta",
        "overview",
        "entry_points",
        "reading_order",
        "hotspots",
        "ownership",
        "dependency_graph",
        "summaries",
        "unavailable",
        "warnings",
    }
