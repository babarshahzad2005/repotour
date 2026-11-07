"""What the scanner sees: every tracked file at one commit."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal

from repotour.config import Config
from repotour.model.history import CommitRecord

Category = Literal["source", "test", "generated", "vendored", "config", "docs", "other"]


@dataclass(frozen=True)
class FileInfo:
    path: str  # repo-relative, forward slashes
    language: str | None
    lines: int
    content_hash: str  # sha256 of file bytes
    category: Category
    reason: str | None = None  # why the classifier chose a non-obvious category

    @property
    def is_excluded(self) -> bool:
        """Generated and vendored files never count toward the tour."""
        return self.category in ("generated", "vendored")


@dataclass(frozen=True)
class RepoSnapshot:
    root: Path
    head_commit: str
    files: tuple[FileInfo, ...]
    config: Config
    submodules: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()  # file-level warnings from scanning
    head_timestamp: int = 0  # committer date of head_commit, Unix seconds
    contents: Mapping[str, bytes] = field(
        default_factory=lambda: MappingProxyType({}), compare=False, repr=False
    )
    history_source: Callable[[], tuple[CommitRecord, ...]] = field(
        default=lambda: (), compare=False, repr=False
    )
    # (adapter, path) -> ParseResult; shared and cached. None: parse directly.
    parse_source: Callable[[Any, str], Any] | None = field(default=None, compare=False, repr=False)

    def read_bytes(self, path: str) -> bytes:
        """Committed content of a tracked file at `head_commit`."""
        return self.contents[path]

    def parse(self, adapter: Any, path: str) -> Any:
        """The adapter's ParseResult for a tracked file, parsed at most once."""
        if self.parse_source is None:
            return adapter.parse(self.read_bytes(path), path)
        return self.parse_source(adapter, path)

    def history(self) -> tuple[CommitRecord, ...]:
        """History reachable from `head_commit`, merges excluded, newest first.

        Read from git on first use only.
        """
        return self.history_source()
