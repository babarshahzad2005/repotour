from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest

from repotour.analyzers.base import Analyzer, AnalyzerResult
from repotour.config import Config
from repotour.model.snapshot import RepoSnapshot
from repotour.pipeline import run_analyzers
from tests.fixtures.repos import minimal

SNAPSHOT = RepoSnapshot(root=Path(), head_commit="0" * 40, files=(), config=Config())


@dataclass
class Recorder:
    calls: list[str] = field(default_factory=list)


@dataclass
class Fake:
    name: str
    depends_on: tuple[str, ...] = ()
    recorder: Recorder | None = None
    fail: bool = False
    version: int = 1

    def run(self, snapshot: RepoSnapshot, inputs: dict[str, AnalyzerResult]) -> AnalyzerResult:
        if self.recorder is not None:
            self.recorder.calls.append(self.name)
        if self.fail:
            raise RuntimeError("boom")
        assert set(inputs) == set(self.depends_on)
        return AnalyzerResult(analyzer=self.name, data={"seen": sorted(inputs)})


def test_runs_in_dependency_order() -> None:
    rec = Recorder()
    analyzers: list[Analyzer] = [
        Fake("ownership", ("history",), rec),
        Fake("history", (), rec),
        Fake("overview", (), rec),
    ]

    outcome = run_analyzers(SNAPSHOT, analyzers)

    assert rec.calls == ["history", "overview", "ownership"]
    assert outcome.results["ownership"].data == {"seen": ["history"]}
    assert outcome.warnings == ()


def test_failing_analyzer_becomes_warning_and_run_continues() -> None:
    analyzers: list[Analyzer] = [Fake("overview", fail=True), Fake("history")]

    outcome = run_analyzers(SNAPSHOT, analyzers)

    assert "overview" not in outcome.results
    assert "history" in outcome.results
    assert outcome.unavailable == ("overview",)
    assert outcome.warnings == ("overview: section unavailable (RuntimeError: boom)",)


def test_dependents_of_a_failed_analyzer_are_skipped() -> None:
    analyzers: list[Analyzer] = [Fake("history", fail=True), Fake("ownership", ("history",))]

    outcome = run_analyzers(SNAPSHOT, analyzers)

    assert outcome.unavailable == ("history", "ownership")
    assert outcome.warnings[1] == "ownership: section unavailable (needs history)"


def test_unknown_dependency_is_a_programming_error() -> None:
    with pytest.raises(ValueError, match="unknown analyzer 'missing'"):
        run_analyzers(SNAPSHOT, [Fake("a", ("missing",))])


def test_dependency_cycle_is_a_programming_error() -> None:
    with pytest.raises(ValueError, match="cycle"):
        run_analyzers(SNAPSHOT, [Fake("a", ("b",)), Fake("b", ("a",))])


def test_analyzer_warnings_are_collected(tmp_path: Path) -> None:
    @dataclass
    class Warns:
        name: str = "w"
        version: int = 1
        depends_on: tuple[str, ...] = ()

        def run(self, snapshot: RepoSnapshot, inputs: dict[str, AnalyzerResult]) -> AnalyzerResult:
            return AnalyzerResult(analyzer=self.name, data={}, warnings=["skipped x.bin"])

    outcome = run_analyzers(SNAPSHOT, [Warns()])

    assert outcome.warnings == ("skipped x.bin",)


def test_real_tour_has_overview(tmp_path: Path) -> None:
    from repotour.pipeline import build_tour

    tour = build_tour(minimal(tmp_path).root).tour

    assert tour.overview is not None
    assert tour.unavailable == ()
