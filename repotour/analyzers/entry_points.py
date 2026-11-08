"""Entry points: where execution starts, and what a library exposes.

Sources: code patterns found by each language adapter, entries the adapter
declares (public surfaces, console scripts), manifests in any language, and
config `pinned_entry_points`. One entry per file and kind, with every source
kept as evidence. Pinned entries come first, peripheral code (examples,
docs, benchmarks) last, otherwise by path; each kind is
capped by `caps.entry_points_per_kind`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from repotour.analyzers.base import AnalyzerResult
from repotour.analyzers.manifest_entries import manifest_entries
from repotour.config import CONFIG_FILE
from repotour.languages import ADAPTERS
from repotour.languages.base import DeclaredEntry
from repotour.model.serde import to_data
from repotour.model.snapshot import RepoSnapshot
from repotour.model.tour import EntryPoint, EntryPointsSection, Evidence
from repotour.scan.filetypes import is_peripheral

KINDS = ("execution", "public surface")


@dataclass
class _Draft:
    descriptions: list[str] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    pinned: bool = False

    def add(self, description: str, evidence: Evidence) -> None:
        if description not in self.descriptions:
            self.descriptions.append(description)
        self.evidence.append(evidence)


class EntryPointsAnalyzer:
    name = "entry_points"
    version = 3
    depends_on: tuple[str, ...] = ()

    def run(self, snapshot: RepoSnapshot, inputs: dict[str, AnalyzerResult]) -> AnalyzerResult:
        def read(path: str) -> str:
            return snapshot.read_bytes(path).decode("utf-8", "replace")

        all_paths = [f.path for f in snapshot.files]
        counted = {f.path for f in snapshot.files if not f.is_excluded}
        sources = [f.path for f in snapshot.files if f.category == "source"]
        drafts: dict[tuple[str, str], _Draft] = {}

        def add(path: str, kind: str, description: str, evidence: Evidence) -> None:
            drafts.setdefault((path, kind), _Draft()).add(description, evidence)

        for adapter in ADAPTERS:
            paths = sorted(p for p in sources if adapter.handles(p))
            if not paths:
                continue
            parsed = {}
            for path in paths:
                result = snapshot.parse(adapter, path)
                parsed[path] = result  # partially parsed files still yield their patterns
                for entry in result.entries:
                    add(
                        path,
                        "execution",
                        entry.description,
                        Evidence(kind="file", ref=path, detail=f"line {entry.line}"),
                    )
            index = adapter.build_index(list(parsed), all_paths, read)
            for declared in adapter.declared_entries(list(parsed), all_paths, read, index):
                add(declared.path, declared.kind, declared.description, declared.evidence)

        manifests: list[DeclaredEntry] = manifest_entries(counted, read)
        for declared in manifests:
            if declared.path in counted:
                add(declared.path, declared.kind, declared.description, declared.evidence)

        warnings = self._pin(snapshot, drafts, counted)
        entries, omitted = self._select(drafts, snapshot.config.caps.entry_points_per_kind)
        section = EntryPointsSection(entries=entries, omitted=omitted)
        return AnalyzerResult(analyzer=self.name, data=to_data(section), warnings=warnings)

    def _pin(
        self, snapshot: RepoSnapshot, drafts: dict[tuple[str, str], _Draft], counted: set[str]
    ) -> list[str]:
        warnings = []
        for raw in snapshot.config.pinned_entry_points:
            path = raw.strip().removeprefix("./")
            if path not in counted:
                warnings.append(f"{CONFIG_FILE}: pinned entry point '{raw}' does not exist")
                continue
            existing = [key for key in drafts if key[0] == path]
            key = existing[0] if existing else (path, "execution")
            draft = drafts.setdefault(key, _Draft())
            draft.pinned = True
            draft.descriptions.insert(0, f"pinned in {CONFIG_FILE}")
            draft.evidence.insert(
                0, Evidence(kind="config", ref=CONFIG_FILE, detail=f"pinned_entry_points: {path}")
            )
        return warnings

    def _select(
        self, drafts: dict[tuple[str, str], _Draft], cap: int
    ) -> tuple[tuple[EntryPoint, ...], int]:
        selected: list[EntryPoint] = []
        omitted = 0
        for kind in KINDS:
            keys = sorted(
                (key for key in drafts if key[1] == kind),
                key=lambda key: (not drafts[key].pinned, is_peripheral(key[0]), key[0]),
            )
            omitted += max(0, len(keys) - cap)
            for path, _ in keys[:cap]:
                draft = drafts[(path, kind)]
                selected.append(
                    EntryPoint(
                        path=path,
                        kind=kind,
                        description="; ".join(draft.descriptions),
                        pinned=draft.pinned,
                        evidence=tuple(draft.evidence),
                    )
                )
        return tuple(selected), omitted
