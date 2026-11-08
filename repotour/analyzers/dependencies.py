"""Dependency graph: which modules import which, inside the repository.

Only static imports count. Test, generated, and vendored files are left out.
Imports that resolve outside the repository are counted, not drawn. A file
that fails to parse becomes a warning and is skipped.

PageRank (over importer -> imported edges) names the core modules; modules
nothing imports that are not entry points (and not empty) are leaf modules. Graphs over
`thresholds.graph_max_nodes` collapse to directories unless `full_graph`.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Callable

from repotour.analyzers.base import AnalyzerResult
from repotour.graph.collapse import ROOT_GROUP, collapse
from repotour.graph.pagerank import pagerank
from repotour.languages import ADAPTERS
from repotour.languages.base import LanguageAdapter, RawImport
from repotour.model.serde import to_data
from repotour.model.snapshot import RepoSnapshot
from repotour.model.tour import (
    CoreModule,
    DependencyGraphSection,
    Evidence,
    ExternalImports,
    GraphNode,
    ImportEdge,
    LeafModule,
)
from repotour.scan.filetypes import is_peripheral

EXTERNAL_EXAMPLES = 5
MAX_LEAVES = 10
GRAPH_CATEGORIES = ("source",)


class DependenciesAnalyzer:
    name = "dependencies"
    version = 5
    depends_on: tuple[str, ...] = ("entry_points",)

    def run(self, snapshot: RepoSnapshot, inputs: dict[str, AnalyzerResult]) -> AnalyzerResult:
        all_paths = [f.path for f in snapshot.files]
        candidates = [f.path for f in snapshot.files if f.category in GRAPH_CATEGORIES]
        warnings: list[str] = []
        languages: list[str] = []
        nodes: list[str] = []
        lines: dict[tuple[str, str], int] = {}  # (source, target) -> first import line
        external: dict[str, tuple[str, RawImport]] = {}  # name -> first (path, import)
        reached: set[str] = set()  # files reached by some import (whole Go packages)

        for adapter in ADAPTERS:
            paths = sorted(p for p in candidates if adapter.handles(p))
            if not paths:
                continue
            languages.append(adapter.name)
            parsed = _parse_all(adapter, paths, snapshot, warnings)
            index = adapter.build_index(list(parsed), all_paths, _reader(snapshot))
            nodes.extend(parsed)
            for path, imports in parsed.items():
                for raw in imports:
                    targets = adapter.resolve(raw, path, index)
                    if not targets and not raw.module.startswith((".", "/")):
                        external.setdefault(adapter.external_name(raw), (path, raw))
                    for target in targets:
                        if target != path:
                            lines.setdefault((path, target), raw.line)
                            reached.update(adapter.imported_together(target, index))

        nodes.sort()
        edges = sorted(lines)
        ranks = pagerank(nodes, edges)
        entry_paths = _entry_paths(inputs)
        config = snapshot.config
        limit = len(nodes) if config.full_graph else config.thresholds.graph_max_nodes
        drawn = collapse(nodes, edges, ranks, max(limit, 1))
        empty = {f.path for f in snapshot.files if f.lines == 0}
        leaves = _leaves([n for n in nodes if n not in empty | reached], edges, entry_paths)

        section = DependencyGraphSection(
            languages=tuple(sorted(languages)),
            modules=len(nodes),
            imports=len(edges),
            depth=drawn.depth,
            nodes=tuple(GraphNode(id=g, modules=len(drawn.members[g])) for g in drawn.nodes),
            edges=tuple(
                _edge(source, target, behind, lines)
                for (source, target), behind in sorted(drawn.edges.items())
            ),
            omitted=drawn.omitted,
            external=_external_claim(external),
            core=_core(nodes, edges, ranks, config.thresholds.core_module_share),
            leaves=tuple(leaves[:MAX_LEAVES]),
            leaves_omitted=max(0, len(leaves) - MAX_LEAVES),
        )
        data = to_data(section)
        # Module-level graph for the reading order (the drawn graph may be collapsed).
        data["module_edges"] = [[s, t, lines[(s, t)]] for s, t in edges]
        data["ranks"] = ranks
        return AnalyzerResult(analyzer=self.name, data=data, warnings=warnings)


def _reader(snapshot: RepoSnapshot) -> Callable[[str], str]:
    def read(path: str) -> str:
        return snapshot.read_bytes(path).decode("utf-8", "replace")

    return read


def _parse_all(
    adapter: LanguageAdapter, paths: list[str], snapshot: RepoSnapshot, warnings: list[str]
) -> dict[str, tuple[RawImport, ...]]:
    parsed: dict[str, tuple[RawImport, ...]] = {}
    for path in paths:
        result = snapshot.parse(adapter, path)
        if result.has_error:
            warnings.append(f"Could not parse {path}; left out of the dependency graph")
            continue
        parsed[path] = result.imports
    return parsed


def _entry_paths(inputs: dict[str, AnalyzerResult]) -> set[str]:
    result = inputs.get("entry_points")
    entries = result.data.get("entries", []) if result is not None else []
    return {e["path"] for e in entries if isinstance(e, dict)}


def _edge(
    source: str, target: str, behind: list[tuple[str, str]], lines: dict[tuple[str, str], int]
) -> ImportEdge:
    first = behind[0]
    detail = f"line {lines[first]}"
    if len(behind) > 1 or (source, target) != first:
        detail = f"{len(behind)} module import{'' if len(behind) == 1 else 's'}, e.g. {detail}"
    return ImportEdge(
        source=source,
        target=target,
        count=len(behind),
        evidence=(Evidence(kind="import", ref=f"{first[0]} -> {first[1]}", detail=detail),),
    )


def _core(
    nodes: list[str], edges: list[tuple[str, str]], ranks: dict[str, float], share: float
) -> tuple[CoreModule, ...]:
    importers: dict[str, list[str]] = {n: [] for n in nodes}
    for source, target in edges:
        importers[target].append(source)
    ordered = sorted(nodes, key=lambda n: (-ranks[n], n))
    position = {n: i + 1 for i, n in enumerate(ordered)}
    imported = [n for n in ordered if importers[n] and not is_peripheral(n)]
    count = min(len(imported), max(1, math.ceil(len(nodes) * share))) if imported else 0
    return tuple(
        CoreModule(
            path=n,
            importers=len(importers[n]),
            rank=position[n],
            evidence=(
                Evidence(
                    kind="import",
                    ref=f"{importers[n][0]} -> {n}",
                    detail=f"imported by {len(importers[n])} module"
                    f"{'' if len(importers[n]) == 1 else 's'}; "
                    f"PageRank {position[n]} of {len(nodes)}",
                ),
            ),
        )
        for n in imported[:count]
    )


def _leaves(
    nodes: list[str], edges: list[tuple[str, str]], entry_paths: set[str]
) -> list[LeafModule]:
    in_degree = Counter(target for _, target in edges)
    return [
        LeafModule(
            path=n,
            evidence=(
                Evidence(kind="file", ref=n, detail="no module imports it; not an entry point"),
            ),
        )
        for n in nodes
        if in_degree[n] == 0 and n not in entry_paths and not is_peripheral(n)
    ]


def _external_claim(external: dict[str, tuple[str, RawImport]]) -> ExternalImports | None:
    if not external:
        return None
    names = sorted(external)
    return ExternalImports(
        count=len(names),
        examples=tuple(names[:EXTERNAL_EXAMPLES]),
        evidence=tuple(
            Evidence(
                kind="import",
                ref=f"{external[name][0]} -> {name}",
                detail=f"line {external[name][1].line}",
            )
            for name in names[:3]
        ),
    )


__all__ = ["ROOT_GROUP", "DependenciesAnalyzer"]
