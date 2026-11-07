"""History: hotspots, the files changed most often in the hotspot window.

The window ends at HEAD's committer date, never at "now" (ADR-0001), so the
same commit always produces the same hotspots.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime

from repotour.analyzers.base import AnalyzerResult
from repotour.config import describe_duration, duration_days
from repotour.model.history import CommitRecord, follow_renames
from repotour.model.serde import to_data
from repotour.model.snapshot import RepoSnapshot
from repotour.model.tour import Evidence, Hotspot, HotspotsSection

SECONDS_PER_DAY = 86_400


class HistoryAnalyzer:
    name = "history"
    version = 2
    depends_on: tuple[str, ...] = ()

    def run(self, snapshot: RepoSnapshot, inputs: dict[str, AnalyzerResult]) -> AnalyzerResult:
        since = snapshot.config.since
        end = snapshot.head_timestamp
        start = end - duration_days(since) * SECONDS_PER_DAY
        counted = {f.path for f in snapshot.files if not f.is_excluded}

        touches: dict[str, list[CommitRecord]] = defaultdict(list)
        for commit in follow_renames(snapshot.history()):
            if commit.timestamp < start:
                continue
            for change in commit.files:
                if change.path in counted:
                    touches[change.path].append(commit)

        ranked = sorted(touches.items(), key=lambda item: (-len(item[1]), item[0]))
        section = HotspotsSection(
            since=since,
            window=describe_duration(since),
            start=_date(start),
            end=_date(end),
            files=tuple(
                _hotspot(path, commits) for path, commits in ranked[: snapshot.config.caps.hotspots]
            ),
        )
        return AnalyzerResult(analyzer=self.name, data=to_data(section))


def _hotspot(path: str, commits: list[CommitRecord]) -> Hotspot:
    oldest = min(commits, key=lambda c: (c.timestamp, c.sha))
    newest = max(commits, key=lambda c: (c.timestamp, c.sha))
    count = len(commits)
    first, last = _date(oldest.timestamp), _date(newest.timestamp)
    if count == 1:
        ref, detail = newest.sha[:12], f"1 commit on {last}"
    elif first == last:
        ref, detail = f"{oldest.sha[:12]}..{newest.sha[:12]}", f"{count} commits on {last}"
    else:
        ref = f"{oldest.sha[:12]}..{newest.sha[:12]}"
        detail = f"{count} commits between {_date(oldest.timestamp)} and {_date(newest.timestamp)}"
    return Hotspot(
        path=path,
        commits=count,
        evidence=(Evidence(kind="commit_range", ref=ref, detail=detail),),
    )


def _date(timestamp: int) -> str:
    return datetime.fromtimestamp(timestamp, tz=UTC).date().isoformat()
