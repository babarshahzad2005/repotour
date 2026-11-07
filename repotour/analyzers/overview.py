"""Overview: what the repository is and how big it is."""

from __future__ import annotations

from collections import defaultdict

from repotour.analyzers.base import AnalyzerResult
from repotour.model.serde import to_data
from repotour.model.snapshot import FileInfo, RepoSnapshot
from repotour.model.tour import Evidence, LanguageStat, Overview, Size

EVIDENCE_FILES_PER_LANGUAGE = 3


class OverviewAnalyzer:
    name = "overview"
    version = 1
    depends_on: tuple[str, ...] = ()

    def run(self, snapshot: RepoSnapshot, inputs: dict[str, AnalyzerResult]) -> AnalyzerResult:
        overview = Overview(size=_size(snapshot), languages=_languages(snapshot.files))
        return AnalyzerResult(analyzer=self.name, data=to_data(overview))


def _size(snapshot: RepoSnapshot) -> Size:
    files = snapshot.files
    return Size(
        files=len(files),
        lines_of_code=sum(f.lines for f in files if f.language is not None),
        evidence=(
            Evidence(
                kind="commit_range",
                ref=snapshot.head_commit,
                detail=f"{len(files)} tracked files at this commit",
            ),
        ),
    )


def _languages(files: tuple[FileInfo, ...]) -> tuple[LanguageStat, ...]:
    by_language: dict[str, list[FileInfo]] = defaultdict(list)
    for f in files:
        if f.language is not None:
            by_language[f.language].append(f)
    stats = []
    for language, members in by_language.items():
        largest = sorted(members, key=lambda f: (-f.lines, f.path))[:EVIDENCE_FILES_PER_LANGUAGE]
        stats.append(
            LanguageStat(
                language=language,
                files=len(members),
                lines=sum(f.lines for f in members),
                evidence=tuple(Evidence(kind="file", ref=f.path) for f in largest),
            )
        )
    return tuple(sorted(stats, key=lambda s: (-s.lines, s.language)))
