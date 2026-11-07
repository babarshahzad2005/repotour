"""The only module that runs git. It returns typed records, never raw output."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from repotour.errors import RepositoryError

GIT_EXECUTABLE = "git"
MIN_GIT_VERSION = (2, 30, 0)

GitVersion = tuple[int, int, int]


class GitError(RepositoryError):
    """git failed unexpectedly."""


@dataclass(frozen=True)
class RepoInfo:
    root: Path
    head_commit: str
    is_shallow: bool
    has_uncommitted_changes: bool


def parse_git_version(raw: str) -> GitVersion:
    match = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", raw)
    if match is None:
        raise GitError(f"could not read the git version from {raw.strip()!r}")
    major, minor, patch = match.groups()
    return int(major), int(minor), int(patch or 0)


def git_version() -> GitVersion:
    return parse_git_version(_git(Path.cwd(), "--version"))


def ensure_supported_git() -> None:
    found = git_version()
    if found < MIN_GIT_VERSION:
        raise RepositoryError(
            f"git {_fmt(found)} is too old; Repotour needs git {_fmt(MIN_GIT_VERSION)} or newer"
        )


def repo_info(start: Path) -> RepoInfo:
    """Resolve any directory inside a repository to facts about its root and HEAD."""
    if not start.is_dir():
        raise RepositoryError(f"{start} is not a directory")
    ensure_supported_git()
    try:
        root = Path(_git(start, "rev-parse", "--show-toplevel").strip())
    except GitError:
        raise RepositoryError(f"{start} is not inside a git repository") from None
    try:
        head = _git(root, "rev-parse", "--verify", "--quiet", "HEAD^{commit}").strip()
    except GitError:
        raise RepositoryError("repository has no commits") from None
    shallow = _git(root, "rev-parse", "--is-shallow-repository").strip() == "true"
    dirty = bool(_git(root, "status", "--porcelain", "--untracked-files=no").strip())
    return RepoInfo(root=root, head_commit=head, is_shallow=shallow, has_uncommitted_changes=dirty)


def _fmt(version: GitVersion) -> str:
    return ".".join(str(part) for part in version)


def _git(cwd: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            [GIT_EXECUTABLE, *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
    except FileNotFoundError:
        raise RepositoryError("git is not installed or not on PATH") from None
    except subprocess.CalledProcessError as exc:
        raise GitError(exc.stderr.strip() or f"git {' '.join(args)} failed") from exc
    return result.stdout
