"""Builds the Tour: scan the repository, run analyzers in dependency order,
and assemble their results.

Failures stay local: an analyzer that raises becomes a warning and an
unavailable section, and analyzers that depend on it are skipped.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from repotour import __version__
from repotour.analyzers.base import Analyzer, AnalyzerResult
from repotour.analyzers.overview import OverviewAnalyzer
from repotour.config import CliOverrides, Config, load_config
from repotour.git import reader
from repotour.model.serde import from_data
from repotour.model.snapshot import RepoSnapshot
from repotour.model.tour import Meta, Overview, Tour
from repotour.scan.scanner import scan

SHALLOW_WARNING = (
    "History truncated: this is a shallow clone, so history-based sections "
    "only cover the commits that were fetched."
)


def default_analyzers() -> list[Analyzer]:
    return [OverviewAnalyzer()]


@dataclass(frozen=True)
class AnalysisOutcome:
    results: dict[str, AnalyzerResult] = field(default_factory=dict)
    unavailable: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class PipelineResult:
    root: Path
    config: Config
    tour: Tour
    has_uncommitted_changes: bool


def build_tour(start: Path, overrides: CliOverrides | None = None) -> PipelineResult:
    repo = reader.repo_info(start)
    config = load_config(repo.root, overrides)
    snapshot = scan(repo.root, repo.head_commit, config)
    outcome = run_analyzers(snapshot, default_analyzers())

    meta = Meta(
        repo_name=config.name or repo.root.name,
        head_commit=repo.head_commit,
        tool_version=__version__,
        config_hash=config.config_hash(),
    )
    warnings = ((SHALLOW_WARNING,) if repo.is_shallow else ()) + outcome.warnings
    overview = outcome.results.get("overview")
    tour = Tour(
        meta=meta,
        overview=from_data(Overview, overview.data) if overview else None,
        unavailable=outcome.unavailable,
        warnings=warnings,
    )
    return PipelineResult(
        root=repo.root,
        config=config,
        tour=tour,
        has_uncommitted_changes=repo.has_uncommitted_changes,
    )


def run_analyzers(snapshot: RepoSnapshot, analyzers: Sequence[Analyzer]) -> AnalysisOutcome:
    results: dict[str, AnalyzerResult] = {}
    unavailable: list[str] = []
    warnings: list[str] = []
    for analyzer in _dependency_order(analyzers):
        missing = [d for d in analyzer.depends_on if d not in results]
        if missing:
            unavailable.append(analyzer.name)
            warnings.append(f"{analyzer.name}: section unavailable (needs {', '.join(missing)})")
            continue
        inputs = {d: results[d] for d in analyzer.depends_on}
        try:
            result = analyzer.run(snapshot, inputs)
        except Exception as exc:
            unavailable.append(analyzer.name)
            warnings.append(f"{analyzer.name}: section unavailable ({type(exc).__name__}: {exc})")
            continue
        results[analyzer.name] = result
        warnings.extend(result.warnings)
    return AnalysisOutcome(
        results=results, unavailable=tuple(unavailable), warnings=tuple(warnings)
    )


def _dependency_order(analyzers: Sequence[Analyzer]) -> list[Analyzer]:
    """Topological order; among analyzers that are ready, alphabetical by name."""
    by_name = {a.name: a for a in analyzers}
    for a in analyzers:
        for dep in a.depends_on:
            if dep not in by_name:
                raise ValueError(f"{a.name} depends on unknown analyzer '{dep}'")
    ordered: list[Analyzer] = []
    done: set[str] = set()
    while len(ordered) < len(analyzers):
        ready = sorted(
            (a for a in analyzers if a.name not in done and set(a.depends_on) <= done),
            key=lambda a: a.name,
        )
        if not ready:
            raise ValueError("analyzer dependency cycle detected")
        ordered.append(ready[0])
        done.add(ready[0].name)
    return ordered
