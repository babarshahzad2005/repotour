"""History as Repotour sees it: typed commit records, newest first."""

from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class FileChange:
    path: str  # path after this commit
    added: int | None  # None for binary files
    removed: int | None
    old_path: str | None = None  # set when this commit renamed the file


@dataclass(frozen=True)
class CommitRecord:
    sha: str
    author_name: str  # after .mailmap
    author_email: str  # after .mailmap
    timestamp: int  # committer date, Unix seconds
    files: tuple[FileChange, ...]


def follow_renames(commits: tuple[CommitRecord, ...]) -> tuple[CommitRecord, ...]:
    """Rewrite every change's path to the file's path at HEAD.

    `commits` must be newest first. Walking backwards in time, each rename
    maps the old path to wherever the new path ends up at HEAD, so chains of
    renames resolve, and a path reused after a rename keeps the two histories
    apart. Paths that no longer exist at HEAD are left as they were.
    """
    head_path: dict[str, str] = {}
    followed = []
    for commit in commits:
        files = []
        for change in commit.files:
            current = head_path.get(change.path, change.path)
            if change.old_path is not None:
                head_path[change.old_path] = current
            files.append(replace(change, path=current, old_path=None))
        followed.append(replace(commit, files=tuple(files)))
    return tuple(followed)
