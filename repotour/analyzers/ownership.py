"""Ownership: who has changed each area most, who to ask today, where a
single person holds an area, and which areas are in flux or settled.

Shares come from changed lines (added + removed) in history, never from
blame (ADR-0002). Renames are followed, bulk commits and bots are left out
of authorship, and authors are merged only through `.mailmap`.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime

from repotour.analyzers.base import AnalyzerResult
from repotour.analyzers.bulk import find_bulk
from repotour.config import Config, describe_duration, duration_days
from repotour.model.history import CommitRecord
from repotour.model.serde import to_data
from repotour.model.snapshot import RepoSnapshot
from repotour.model.tour import (
    Activity,
    AuthorShare,
    BusFactorWarning,
    Contact,
    Evidence,
    OwnershipEntry,
    OwnershipSection,
)

SECONDS_PER_DAY = 86_400


@dataclass
class _Author:
    name: str = ""  # most recent mailmapped name for this identity
    lines: int = 0
    commits: list[CommitRecord] = field(default_factory=list)  # newest first


@dataclass
class _Directory:
    files: int  # source and test files at HEAD
    authors: dict[str, _Author] = field(default_factory=dict)
    last_change: CommitRecord | None = None  # newest non-bulk change, bots included


@dataclass(frozen=True)
class _Cutoffs:
    contact: int
    active: int
    stable: int


class OwnershipAnalyzer:
    name = "ownership"
    version = 2
    depends_on: tuple[str, ...] = ("history",)

    def run(self, snapshot: RepoSnapshot, inputs: dict[str, AnalyzerResult]) -> AnalyzerResult:
        config = snapshot.config
        directories = _eligible_directories(snapshot)
        counted = {f.path for f in snapshot.files if not f.is_excluded}
        history = snapshot.followed_history()
        bulk = find_bulk(snapshot, history)

        for commit in history:  # newest first
            if commit.sha in bulk:
                continue
            touched: dict[str, int] = defaultdict(int)
            for change in commit.files:
                if change.path not in counted:
                    continue
                lines = (change.added or 0) + (change.removed or 0)
                for directory in _ancestors(change.path):
                    if directory in directories:
                        touched[directory] += lines
            bot = is_bot(commit.author_name, config)
            for directory, lines in touched.items():
                state = directories[directory]
                if state.last_change is None:
                    state.last_change = commit
                if bot:
                    continue
                author = state.authors.setdefault(
                    commit.author_email.lower(), _Author(name=commit.author_name)
                )
                author.lines += lines
                author.commits.append(commit)

        head = snapshot.head_timestamp
        thresholds = config.thresholds
        cutoffs = _Cutoffs(
            contact=head - duration_days(thresholds.contact_window) * SECONDS_PER_DAY,
            active=head - duration_days(config.since) * SECONDS_PER_DAY,
            stable=head - duration_days(thresholds.stable_window) * SECONDS_PER_DAY,
        )
        entries = tuple(
            entry
            for path in sorted(directories)
            if (entry := _entry(path, directories[path], config, cutoffs)) is not None
        )
        section = OwnershipSection(
            contact_window=describe_duration(thresholds.contact_window), entries=entries
        )
        return AnalyzerResult(analyzer=self.name, data=to_data(section))


def is_bot(name: str, config: Config) -> bool:
    lowered = name.lower()
    return lowered.endswith("[bot]") or lowered in {b.lower() for b in config.bots}


def _eligible_directories(snapshot: RepoSnapshot) -> dict[str, _Directory]:
    limits = snapshot.config.thresholds
    counts: dict[str, int] = defaultdict(int)
    for f in snapshot.files:
        if f.category in ("source", "test"):
            for directory in _ancestors(f.path):
                counts[directory] += 1
    return {
        d: _Directory(files=n)
        for d, n in counts.items()
        if n >= limits.ownership_min_files and d.count("/") < limits.ownership_max_depth
    }


def _ancestors(path: str) -> list[str]:
    parts = path.split("/")[:-1]
    return ["/".join(parts[: i + 1]) for i in range(len(parts))]


def _entry(
    path: str, state: _Directory, config: Config, cutoffs: _Cutoffs
) -> OwnershipEntry | None:
    total = sum(a.lines for a in state.authors.values())
    if total == 0:
        return None
    ranked = sorted(state.authors.values(), key=lambda a: (-a.lines, a.name))
    cap = config.caps.authors_per_directory
    commits = sum(len(a.commits) for a in state.authors.values())
    return OwnershipEntry(
        path=path,
        total_lines=total,
        files=state.files,
        commits=commits,
        authors=tuple(
            AuthorShare(
                name=a.name,
                lines=a.lines,
                share=_percent(a.lines, total),
                commits=len(a.commits),
                evidence=(_range_evidence(a),),
            )
            for a in ranked[:cap]
        ),
        contacts=tuple(
            Contact(
                name=a.name,
                last_commit=_date(a.commits[0].timestamp),
                evidence=(
                    Evidence(
                        kind="commit_range",
                        ref=a.commits[0].sha[:12],
                        detail=f"last commit to {path}/ on {_date(a.commits[0].timestamp)}",
                    ),
                ),
            )
            for a in ranked
            if a.commits[0].timestamp >= cutoffs.contact
        )[:cap],
        bus_factor=_bus_factor(ranked[0], total, state.files, commits, config),
        activity=_activity(state.last_change, cutoffs),
    )


def _bus_factor(
    top: _Author, total: int, files: int, commits: int, config: Config
) -> BusFactorWarning | None:
    limits = config.thresholds
    if not (
        top.lines / total > limits.bus_factor_share
        and files >= limits.bus_factor_min_files
        and commits >= limits.bus_factor_min_commits
    ):
        return None
    evidence = _range_evidence(top)
    return BusFactorWarning(
        name=top.name,
        share=_percent(top.lines, total),
        evidence=(
            Evidence(
                kind="commit_range",
                ref=evidence.ref,
                detail=f"{evidence.detail}; directory has {files} files and {commits} commits",
            ),
        ),
    )


def _activity(last: CommitRecord | None, cutoffs: _Cutoffs) -> Activity | None:
    if last is None:
        return None
    if last.timestamp >= cutoffs.active:
        state = "active"
    elif last.timestamp < cutoffs.stable:
        state = "stable"
    else:
        return None
    return Activity(
        state=state,
        evidence=(
            Evidence(
                kind="commit_range",
                ref=last.sha[:12],
                detail=f"last change on {_date(last.timestamp)}",
            ),
        ),
    )


def _percent(part: int, total: int) -> int:
    return int(100 * part / total + 0.5)


def _range_evidence(author: _Author) -> Evidence:
    newest, oldest = author.commits[0], author.commits[-1]
    count = len(author.commits)
    ref = newest.sha[:12] if count == 1 else f"{oldest.sha[:12]}..{newest.sha[:12]}"
    return Evidence(
        kind="commit_range",
        ref=ref,
        detail=f"{count} commit{'' if count == 1 else 's'}, {author.lines} lines changed",
    )


def _date(timestamp: int) -> str:
    return datetime.fromtimestamp(timestamp, tz=UTC).date().isoformat()
