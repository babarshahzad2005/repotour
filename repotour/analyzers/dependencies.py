"""Dependency graph: which modules import which, inside the repository.

Only static imports count. Test, generated, and vendored files are left out.
Imports that resolve outside the repository are counted, not drawn. A file
that fails to parse becomes a warning and is skipped.
"""

from __future__ import annotations

from collections import defaultdict

from repotour.analyzers.base import AnalyzerResult
from repotour.languages import ADAPTERS
from repotour.languages.base import LanguageAdapter, RawImport
from repotour.model.serde import to_data
from repotour.model.snapshot import RepoSnapshot
from repotour.model.tour import DependencyGraphSection, Evidence, ExternalImports, ImportEdge

EXTERNAL_EXAMPLES = 5
GRAPH_CATEGORIES = ("source",)


class DependenciesAnalyzer:
    name = "dependencies"
    version = 1
    depends_on: tuple[str, ...] = ()

    def run(self, snapshot: RepoSnapshot, inputs: dict[str, AnalyzerResult]) -> AnalyzerResult:
        all_paths = [f.path for f in snapshot.files]
        candidates = [f.path for f in snapshot.files if f.category in GRAPH_CATEGORIES]
        warnings: list[str] = []
        languages: list[str] = []
        nodes: list[str] = []
        edges: dict[tuple[str, str], int] = {}  # (source, target) -> first line
        external: dict[str, tuple[str, RawImport]] = {}  # name -> first (path, import)

        for adapter in ADAPTERS:
            paths = sorted(p for p in candidates if adapter.handles(p))
            if not paths:
                continue
            languages.append(adapter.name)
            parsed = _parse_all(adapter, paths, snapshot, warnings)
            index = adapter.build_index(list(parsed), all_paths)
            nodes.extend(parsed)
            for path, imports in parsed.items():
                for raw in imports:
                    targets = adapter.resolve(raw, path, index)
                    if not targets:
                        external.setdefault(adapter.external_name(raw), (path, raw))
                    for target in targets:
                        if target != path:
                            edges.setdefault((path, target), raw.line)

        section = DependencyGraphSection(
            languages=tuple(sorted(languages)),
            nodes=tuple(sorted(nodes)),
            edges=tuple(
                ImportEdge(
                    source=source,
                    target=target,
                    evidence=(
                        Evidence(kind="import", ref=f"{source} -> {target}", detail=f"line {line}"),
                    ),
                )
                for (source, target), line in sorted(edges.items())
            ),
            external=_external_claim(external),
        )
        return AnalyzerResult(analyzer=self.name, data=to_data(section), warnings=warnings)


def _parse_all(
    adapter: LanguageAdapter, paths: list[str], snapshot: RepoSnapshot, warnings: list[str]
) -> dict[str, tuple[RawImport, ...]]:
    parsed: dict[str, tuple[RawImport, ...]] = {}
    for path in paths:
        result = adapter.parse(snapshot.read_bytes(path))
        if result.has_error:
            warnings.append(f"Could not parse {path}; left out of the dependency graph")
            continue
        parsed[path] = result.imports
    return parsed


def _external_claim(external: dict[str, tuple[str, RawImport]]) -> ExternalImports | None:
    if not external:
        return None
    names = sorted(external)
    by_name: dict[str, list[str]] = defaultdict(list)
    for name in names[:3]:
        by_name[name].append(external[name][0])
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
