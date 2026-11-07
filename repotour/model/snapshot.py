"""What the scanner sees: every tracked file at one commit."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Literal

from repotour.config import Config

Category = Literal["source", "test", "generated", "vendored", "config", "docs", "other"]


@dataclass(frozen=True)
class FileInfo:
    path: str  # repo-relative, forward slashes
    language: str | None
    lines: int
    content_hash: str  # sha256 of file bytes
    category: Category


@dataclass(frozen=True)
class RepoSnapshot:
    root: Path
    head_commit: str
    files: tuple[FileInfo, ...]
    config: Config
    contents: Mapping[str, bytes] = field(
        default_factory=lambda: MappingProxyType({}), compare=False, repr=False
    )

    def read_bytes(self, path: str) -> bytes:
        """Committed content of a tracked file at `head_commit`."""
        return self.contents[path]
