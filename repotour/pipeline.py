"""Builds the Tour for a repository."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from repotour import __version__
from repotour.git import reader
from repotour.model.tour import Meta, Tour


@dataclass(frozen=True)
class PipelineResult:
    root: Path
    tour: Tour


def build_tour(start: Path) -> PipelineResult:
    repo = reader.repo_info(start)
    meta = Meta(
        repo_name=repo.root.name,
        head_commit=repo.head_commit,
        tool_version=__version__,
    )
    return PipelineResult(root=repo.root, tour=Tour(meta=meta))
