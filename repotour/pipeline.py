"""Builds the Tour for a repository."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from repotour import __version__
from repotour.config import CliOverrides, Config, load_config
from repotour.git import reader
from repotour.model.tour import Meta, Tour

SHALLOW_WARNING = (
    "History truncated: this is a shallow clone, so history-based sections "
    "only cover the commits that were fetched."
)


@dataclass(frozen=True)
class PipelineResult:
    root: Path
    config: Config
    tour: Tour
    has_uncommitted_changes: bool


def build_tour(start: Path, overrides: CliOverrides | None = None) -> PipelineResult:
    repo = reader.repo_info(start)
    config = load_config(repo.root, overrides)
    meta = Meta(
        repo_name=config.name or repo.root.name,
        head_commit=repo.head_commit,
        tool_version=__version__,
        config_hash=config.config_hash(),
    )
    warnings = (SHALLOW_WARNING,) if repo.is_shallow else ()
    return PipelineResult(
        root=repo.root,
        config=config,
        tour=Tour(meta=meta, warnings=warnings),
        has_uncommitted_changes=repo.has_uncommitted_changes,
    )
