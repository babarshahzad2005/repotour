from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from repotour.model.tour import Claim, Evidence, Meta, Tour, find_unevidenced_claims
from repotour.pipeline import build_tour
from tests.fixtures.repos import minimal

META = Meta(repo_name="demo", head_commit="0" * 40, tool_version="0.0.0", config_hash="c" * 64)


@dataclass(frozen=True, kw_only=True)
class TextClaim(Claim):
    text: str


@dataclass(frozen=True, kw_only=True)
class Group(Claim):
    members: tuple[TextClaim, ...]


def test_every_claim_in_a_real_tour_has_evidence(tmp_path: Path) -> None:
    tour = build_tour(minimal(tmp_path).root).tour

    assert find_unevidenced_claims(tour) == []


def test_claim_without_evidence_is_flagged() -> None:
    bare = TextClaim(text="this is an entry point", evidence=())
    tour = Tour(meta=META, summaries=(bare,))

    assert find_unevidenced_claims(tour) == [bare]


def test_nested_claim_without_evidence_is_flagged() -> None:
    bare = TextClaim(text="nested", evidence=())
    group = Group(members=(bare,), evidence=(Evidence(kind="file", ref="a.py"),))
    tour = Tour(meta=META, summaries=(group,))

    assert find_unevidenced_claims(tour) == [bare]


def test_claims_with_evidence_pass() -> None:
    fact = TextClaim(text="ok", evidence=(Evidence(kind="file", ref="a.py"),))
    tour = Tour(meta=META, summaries=(fact,))

    assert find_unevidenced_claims(tour) == []


def test_tour_model_is_json_serializable() -> None:
    fact = TextClaim(text="ok", evidence=(Evidence(kind="import", ref="a.py -> b.py"),))
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
