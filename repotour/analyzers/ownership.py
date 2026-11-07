"""Ownership: who has changed each area most, and who to ask today.

Shares come from changed lines (added + removed) in history, never from
blame (ADR-0002). Renames are followed, bulk commits and bots are left out,
and authors are merged only through `.mailmap`.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import PurePosixPath

from repotour.analyzers.base import AnalyzerResult
from repotour.analyzers.bulk import find_bulk
from repotour.config import Config, describe_duration, duration_days
from repotour.model.history import CommitRecord, follow_renames
from repotour.model.serde import to_data
from repotour.model.snapshot import RepoSnapshot
from repotour.model.tour import (
    AuthorShare,
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
    commits: list[CommitRecord] = field(default_factory=list)


class OwnershipAnalyzer:
    name = "ownership"
    version = 1
    depends_on: tuple[str, ...] = ("history",)

    def run(self, snapshot: RepoSnapshot, inputs: dict[str, AnalyzerResult]) -> AnalyzerResult:
        config = snapshot.config
        directories = _eligible_directories(snapshot)
        counted = {f.path for f in snapshot.files if not f.is_excluded}
        history = follow_renames(snapshot.history())
        bulk = find_bulk(snapshot, history)

        # directory -> author identity -> totals; history is newest first.
        totals: dict[str, dict[str, _Author]] = {d: {} for d in directories}
        for commit in history:
            if commit.sha in bulk or is_bot(commit.author_name, config):
                continue
            identity = commit.author_email.lower()
            touched: dict[str, int] = defaultdict(int)
            for change in commit.files:
                if change.path not in counted:
                    continue
                lines = (change.added or 0) + (change.removed or 0)
                for directory in _ancestors(change.path):
                    if directory in totals:
                        touched[directory] += lines
            for directory, lines in touched.items():
                author = totals[directory].setdefault(identity, _Author(name=commit.author_name))
                author.lines += lines
                author.commits.append(commit)

        contact_since = snapshot.head_timestamp - (
            duration_days(config.thresholds.contact_window) * SECONDS_PER_DAY
        )
        entries = tuple(
            entry
            for directory in directories
            if (entry := _entry(directory, totals[directory], config, contact_since)) is not None
        )
        section = OwnershipSection(
            contact_window=describe_duration(config.thresholds.contact_window), entries=entries
        )
        return AnalyzerResult(analyzer=self.name, data=to_data(section))


def is_bot(name: str, config: Config) -> bool:
    lowered = name.lower()
    return lowered.endswith("[bot]") or lowered in {b.lower() for b in config.bots}


def _eligible_directories(snapshot: RepoSnapshot) -> list[str]:
    limits = snapshot.config.thresholds
    counts: dict[str, int] = defaultdict(int)
    for f in snapshot.files:
        if f.category in ("source", "test"):
            for directory in _ancestors(f.path):
                counts[directory] += 1
    return sorted(
        d
        for d, n in counts.items()
        if n >= limits.ownership_min_files and d.count("/") < limits.ownership_max_depth
    )


def _ancestors(path: str) -> list[str]:
    parts = PurePosixPath(path).parts[:-1]
    return ["/".join(parts[: i + 1]) for i in range(len(parts))]


def _entry(
    directory: str, authors: dict[str, _Author], config: Config, contact_since: int
) -> OwnershipEntry | None:
    total = sum(a.lines for a in authors.values())
    if total == 0:
        return None
    ranked = sorted(authors.values(), key=lambda a: (-a.lines, a.name))
    cap = config.caps.authors_per_directory
    shares = tuple(
        AuthorShare(
            name=a.name,
            lines=a.lines,
            share=int(100 * a.lines / total + 0.5),
            commits=len(a.commits),
            evidence=(_range_evidence(a),),
        )
        for a in ranked[:cap]
    )
    contacts = tuple(
        Contact(
            name=a.name,
            last_commit=_date(a.commits[0].timestamp),
            evidence=(
                Evidence(
                    kind="commit_range",
                    ref=a.commits[0].sha[:12],
                    detail=f"last commit to {directory}/ on {_date(a.commits[0].timestamp)}",
                ),
            ),
        )
        for a in ranked
        if a.commits[0].timestamp >= contact_since
    )[:cap]
    return OwnershipEntry(path=directory, total_lines=total, authors=shares, contacts=contacts)


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
