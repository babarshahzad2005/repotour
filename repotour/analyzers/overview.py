"""Overview: what the repository is and how big it is."""

from __future__ import annotations

from collections import defaultdict

from repotour.analyzers import project
from repotour.analyzers.base import AnalyzerResult
from repotour.analyzers.commands import find_commands
from repotour.model.serde import to_data
from repotour.model.snapshot import FileInfo, RepoSnapshot
from repotour.model.tour import (
    Evidence,
    EvidenceKind,
    ExcludedFiles,
    LanguageStat,
    Overview,
    Size,
    Submodule,
)

EVIDENCE_FILES_PER_LANGUAGE = 3
EXAMPLES_PER_EXCLUDED_CATEGORY = 3


class OverviewAnalyzer:
    name = "overview"
    version = 4
    depends_on: tuple[str, ...] = ()

    def run(self, snapshot: RepoSnapshot, inputs: dict[str, AnalyzerResult]) -> AnalyzerResult:
        counted = tuple(f for f in snapshot.files if not f.is_excluded)
        detection = project.detect(snapshot)
        commands, command_warnings = find_commands(snapshot)
        overview = Overview(
            size=_size(snapshot, counted),
            languages=_languages(counted),
            project_types=detection.types,
            packages=detection.packages,
            commands=commands,
            excluded=_excluded(snapshot.files),
            submodules=tuple(
                Submodule(
                    path=path,
                    evidence=(Evidence(kind="file", ref=path, detail="git submodule"),),
                )
                for path in snapshot.submodules
            ),
        )
        return AnalyzerResult(
            analyzer=self.name,
            data=to_data(overview),
            warnings=[*snapshot.warnings, *detection.warnings, *command_warnings],
        )


def _size(snapshot: RepoSnapshot, counted: tuple[FileInfo, ...]) -> Size:
    return Size(
        files=len(counted),
        lines_of_code=sum(f.lines for f in counted if f.language is not None),
        evidence=(
            Evidence(
                kind="commit_range",
                ref=snapshot.head_commit,
                detail=f"{len(counted)} tracked files at this commit, "
                "excluding generated and vendored files",
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


def _excluded(files: tuple[FileInfo, ...]) -> tuple[ExcludedFiles, ...]:
    claims = []
    for category in ("generated", "vendored"):
        members = [f for f in files if f.category == category]
        if not members:
            continue
        examples = members[:EXAMPLES_PER_EXCLUDED_CATEGORY]
        claims.append(
            ExcludedFiles(
                category=category,
                count=len(members),
                evidence=tuple(
                    Evidence(kind=_evidence_kind(f.reason), ref=f.path, detail=f.reason)
                    for f in examples
                ),
            )
        )
    return tuple(claims)


def _evidence_kind(reason: str | None) -> EvidenceKind:
    if reason is not None and "gitattributes" in reason:
        return "git_attribute"
    if reason is not None and reason.startswith("config"):
        return "config"
    return "file"
