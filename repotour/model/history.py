"""History as Repotour sees it: typed commit records, newest first."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FileChange:
    path: str
    added: int | None  # None for binary files
    removed: int | None


@dataclass(frozen=True)
class CommitRecord:
    sha: str
    author_name: str  # after .mailmap
    author_email: str  # after .mailmap
    timestamp: int  # committer date, Unix seconds
    files: tuple[FileChange, ...]
