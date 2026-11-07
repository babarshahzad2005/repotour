"""Reading order: the files a newcomer should read first, in order.

Candidates are non-empty source files (tests, generated, and vendored
files never qualify). Groups come first: pinned entry points (in config
order), then execution entry points, then public surfaces, then everything
else. Within a group, files rank by the mean
of their PageRank percentile and hotspot percentile, ties by path.

Selection starts with the highest-ranked entry point, then repeatedly takes
the highest-ranked file imported by a file already chosen; when none is
left, the highest-ranked remaining file that has a signal. A file needs a
signal to be chosen at all (an entry point, importers, or at least two
changes in the window), so the list is never padded. Every reason is built
from those signals.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from repotour.analyzers.base import AnalyzerResult
from repotour.config import CONFIG_FILE
from repotour.model.serde import from_data, to_data
from repotour.model.snapshot import RepoSnapshot
from repotour.model.tour import Evidence, ReadingOrderSection, ReadingStep

MIN_CHANGES_FOR_SIGNAL = 2
OTHER = 3
PINNED_PREFIX = f"pinned in {CONFIG_FILE}"


@dataclass
class _Candidate:
    path: str
    group: int  # 0 pinned, 1 execution entry point, 2 public surface, 3 other
    score: float
    entry_description: str = ""
    entry_evidence: list[Evidence] = field(default_factory=list)
    importers: list[str] = field(default_factory=list)
    commits: int = 0
    touch: dict[str, Any] | None = None

    @property
    def has_signal(self) -> bool:
        return self.group < OTHER or bool(self.importers) or self.commits >= MIN_CHANGES_FOR_SIGNAL


class ReadingOrderAnalyzer:
    name = "reading_order"
    version = 2
    depends_on: tuple[str, ...] = ("entry_points", "dependencies", "history")

    def run(self, snapshot: RepoSnapshot, inputs: dict[str, AnalyzerResult]) -> AnalyzerResult:
        graph = inputs["dependencies"].data
        history = inputs["history"].data
        entries = inputs["entry_points"].data.get("entries", [])

        lines = {(s, t): line for s, t, line in graph.get("module_edges", [])}
        importers: dict[str, list[str]] = defaultdict(list)
        for source, target in sorted(lines):
            importers[target].append(source)
        ranks: dict[str, float] = graph.get("ranks", {})
        touches: dict[str, dict[str, Any]] = history.get("touches", {})

        sources = sorted(f.path for f in snapshot.files if f.category == "source" and f.lines > 0)
        pinned_order = [p.strip().removeprefix("./") for p in snapshot.config.pinned_entry_points]
        candidates = _candidates(sources, entries, importers, ranks, touches, pinned_order)

        chosen = _select(candidates, lines, pinned_order, snapshot.config.caps.reading_order)
        window = history.get("window", "")
        steps = tuple(_step(candidates[path], via, lines, window) for path, via in chosen)
        section = ReadingOrderSection(steps=steps)
        return AnalyzerResult(analyzer=self.name, data=to_data(section))


def _candidates(
    sources: list[str],
    entries: list[dict[str, Any]],
    importers: dict[str, list[str]],
    ranks: dict[str, float],
    touches: dict[str, dict[str, Any]],
    pinned_order: list[str],
) -> dict[str, _Candidate]:
    by_path: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for entry in entries:
        by_path[entry["path"]].append(entry)
    pool = sorted(set(sources) | {p for p in pinned_order if p in by_path})
    rank_pct = _percentiles({p: ranks.get(p, 0.0) for p in pool})
    hot_pct = _percentiles({p: float(touches.get(p, {}).get("commits", 0)) for p in pool})
    candidates = {}
    for path in pool:
        found = by_path.get(path, [])
        pinned = any(e.get("pinned") for e in found)
        descriptions = [e["description"] for e in found]
        kinds = {e.get("kind") for e in found}
        if pinned:
            group = 0
        elif "execution" in kinds:
            group = 1
        elif found:
            group = 2
        else:
            group = OTHER
        candidates[path] = _Candidate(
            path=path,
            group=group,
            score=round((rank_pct[path] + hot_pct[path]) / 2, 6),
            entry_description="; ".join(descriptions),
            entry_evidence=[from_data(Evidence, ev) for e in found for ev in e["evidence"]],
            importers=importers.get(path, []),
            commits=int(touches.get(path, {}).get("commits", 0)),
            touch=touches.get(path),
        )
    return candidates


def _percentiles(values: dict[str, float]) -> dict[str, float]:
    """Share of the other candidates with a strictly lower value."""
    ordered = sorted(values.values())
    others = max(len(ordered) - 1, 1)
    lower: dict[float, int] = {}
    for i, value in enumerate(ordered):
        lower.setdefault(value, i)
    return {path: lower[value] / others for path, value in values.items()}


def _select(
    candidates: dict[str, _Candidate],
    lines: dict[tuple[str, str], int],
    pinned_order: list[str],
    cap: int,
) -> list[tuple[str, str | None]]:
    """(path, chosen-because-imported-by) pairs, in reading order."""
    pinned = [p for p in pinned_order if p in candidates and candidates[p].group == 0]
    chosen: list[tuple[str, str | None]] = [(p, None) for p in pinned[:cap]]
    taken = {p for p, _ in chosen}

    def best(pool: list[_Candidate], by_group: bool) -> _Candidate | None:
        key = (
            (lambda c: (c.group, -c.score, c.path)) if by_group else (lambda c: (-c.score, c.path))
        )
        return min(pool, key=key, default=None)

    if not chosen:
        entry_points = [c for c in candidates.values() if 0 < c.group < OTHER]
        first = best(entry_points, by_group=True)
        if first is not None:
            chosen.append((first.path, None))
            taken.add(first.path)
    while len(chosen) < cap:
        imported: dict[str, str] = {}
        for path, _ in chosen:
            for source, target in lines:
                if source == path and target not in taken and target in candidates:
                    imported.setdefault(target, source)
        pick = best([candidates[p] for p in imported], by_group=False)
        if pick is not None:
            chosen.append((pick.path, imported[pick.path]))
        else:
            rest = [c for c in candidates.values() if c.path not in taken and c.has_signal]
            fallback = best(rest, by_group=True)
            if fallback is None:
                break
            chosen.append((fallback.path, None))
            pick = fallback
        taken.add(pick.path)
    return chosen


def _step(
    candidate: _Candidate, via: str | None, lines: dict[tuple[str, str], int], window: str
) -> ReadingStep:
    reasons: list[str] = []
    evidence: list[Evidence] = []
    description = candidate.entry_description
    if candidate.group == 0:
        reasons.append(PINNED_PREFIX)
        description = description.removeprefix(PINNED_PREFIX).lstrip("; ")
    if description:
        reasons.append(f"entry point: {description}")
    evidence.extend(candidate.entry_evidence)
    if via is not None:
        reasons.append(f"imported by {via}")
        evidence.append(_import_evidence(via, candidate.path, lines))
    if candidate.importers:
        count = len(candidate.importers)
        reasons.append(f"imported by {count} module{'' if count == 1 else 's'}")
        if via is None:
            evidence.append(_import_evidence(candidate.importers[0], candidate.path, lines))
    if candidate.commits >= MIN_CHANGES_FOR_SIGNAL and candidate.touch is not None:
        reasons.append(f"changed {candidate.commits} times in the last {window}")
        evidence.append(
            Evidence(
                kind="commit_range",
                ref=str(candidate.touch["ref"]),
                detail=str(candidate.touch["detail"]),
            )
        )
    return ReadingStep(path=candidate.path, reason="; ".join(reasons), evidence=tuple(evidence))


def _import_evidence(source: str, target: str, lines: dict[tuple[str, str], int]) -> Evidence:
    return Evidence(
        kind="import", ref=f"{source} -> {target}", detail=f"line {lines[(source, target)]}"
    )
