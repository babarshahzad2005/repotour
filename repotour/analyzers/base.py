"""The analyzer contract. Each analyzer produces one section of the tour."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from repotour.model.snapshot import RepoSnapshot
from repotour.model.tour import Evidence


@dataclass
class AnalyzerResult:
    analyzer: str
    data: dict[str, Any]  # analyzer-specific, JSON-serializable
    evidence: list[Evidence] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class Analyzer(Protocol):
    name: str
    version: int  # bump to invalidate this analyzer's cache
    depends_on: tuple[str, ...]

    def run(
        self,
        snapshot: RepoSnapshot,
        inputs: dict[str, AnalyzerResult],
    ) -> AnalyzerResult: ...
