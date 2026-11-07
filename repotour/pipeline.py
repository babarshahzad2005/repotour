"""Builds the Tour: scan the repository, run analyzers in dependency order,
and assemble their results.

Failures stay local: an analyzer that raises becomes a warning and an
unavailable section, and analyzers that depend on it are skipped.

Results are cached per analyzer, version, commit, and config hash. The scan
is lazy, so a fully cached commit is rendered without reading the tree.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Any

from repotour import __version__
from repotour.analyzers.base import Analyzer, AnalyzerResult
from repotour.analyzers.history import HistoryAnalyzer
from repotour.analyzers.overview import OverviewAnalyzer
from repotour.analyzers.ownership import OwnershipAnalyzer
from repotour.cache.store import CacheStore, ResultKey, cache_path
from repotour.config import CliOverrides, Config, load_config
from repotour.git import reader
from repotour.model.serde import from_data
from repotour.model.snapshot import RepoSnapshot
from repotour.model.tour import HotspotsSection, Meta, Overview, OwnershipSection, Tour
from repotour.scan.scanner import scan

SHALLOW_WARNING = (
    "History truncated: this is a shallow clone, so history-based sections "
    "only cover the commits that were fetched."
)

# Which Tour field each analyzer's result fills, and the model type it holds.
SECTIONS: dict[str, tuple[str, type]] = {
    "overview": ("overview", Overview),
    "history": ("hotspots", HotspotsSection),
    "ownership": ("ownership", OwnershipSection),
}


def default_analyzers() -> list[Analyzer]:
    return [OverviewAnalyzer(), HistoryAnalyzer(), OwnershipAnalyzer()]


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


@dataclass(frozen=True)
class ResultCache:
    """The cache as seen by one run: a store plus this run's commit and config."""

    store: CacheStore
    head_commit: str
    config_hash: str

    def key(self, analyzer: Analyzer) -> ResultKey:
        return ResultKey(analyzer.name, analyzer.version, self.head_commit, self.config_hash)

    def get(self, analyzer: Analyzer) -> AnalyzerResult | None:
        return self.store.get(self.key(analyzer))

    def put(self, analyzer: Analyzer, result: AnalyzerResult) -> None:
        self.store.put(self.key(analyzer), result)


def build_tour(
    start: Path, overrides: CliOverrides | None = None, *, use_cache: bool = True
) -> PipelineResult:
    repo = reader.repo_info(start)
    config = load_config(repo.root, overrides)

    @cache
    def snapshot() -> RepoSnapshot:
        return scan(repo.root, repo.head_commit, config)

    store = CacheStore(cache_path(reader.git_common_dir(repo.root))) if use_cache else None
    try:
        result_cache = ResultCache(store, repo.head_commit, config.config_hash()) if store else None
        outcome = run_analyzers(snapshot, default_analyzers(), result_cache)
    finally:
        if store is not None:
            store.close()

    meta = Meta(
        repo_name=config.name or repo.root.name,
        head_commit=repo.head_commit,
        tool_version=__version__,
        config_hash=config.config_hash(),
    )
    warnings = ((SHALLOW_WARNING,) if repo.is_shallow else ()) + outcome.warnings
    sections: dict[str, Any] = {
        field_name: from_data(model, outcome.results[name].data)
        for name, (field_name, model) in SECTIONS.items()
        if name in outcome.results
    }
    tour = Tour(meta=meta, unavailable=outcome.unavailable, warnings=warnings, **sections)
    return PipelineResult(
        root=repo.root,
        config=config,
        tour=tour,
        has_uncommitted_changes=repo.has_uncommitted_changes,
    )


def run_analyzers(
    snapshot: RepoSnapshot | Callable[[], RepoSnapshot],
    analyzers: Sequence[Analyzer],
    result_cache: ResultCache | None = None,
) -> AnalysisOutcome:
    """Run analyzers in dependency order, reusing cached results.

    `snapshot` may be a callable, called only if some analyzer must run.
    """
    get_snapshot = snapshot if callable(snapshot) else (lambda: snapshot)
    results: dict[str, AnalyzerResult] = {}
    unavailable: list[str] = []
    warnings: list[str] = []
    for analyzer in _dependency_order(analyzers):
        missing = [d for d in analyzer.depends_on if d not in results]
        if missing:
            unavailable.append(analyzer.name)
            warnings.append(f"{analyzer.name}: section unavailable (needs {', '.join(missing)})")
            continue
        cached = result_cache.get(analyzer) if result_cache else None
        if cached is not None:
            results[analyzer.name] = cached
            warnings.extend(cached.warnings)
            continue
        inputs = {d: results[d] for d in analyzer.depends_on}
        try:
            result = analyzer.run(get_snapshot(), inputs)
        except Exception as exc:
            unavailable.append(analyzer.name)
            warnings.append(f"{analyzer.name}: section unavailable ({type(exc).__name__}: {exc})")
            continue
        if result_cache is not None:
            result_cache.put(analyzer, result)
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
