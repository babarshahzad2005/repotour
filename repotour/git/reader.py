"""The only module that runs git. It returns typed records, never raw output."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


class GitError(Exception):
    """git failed or is unavailable."""


@dataclass(frozen=True)
class RepoInfo:
    root: Path
    head_commit: str


def repo_info(start: Path) -> RepoInfo:
    root = Path(_git(start, "rev-parse", "--show-toplevel").strip())
    head = _git(root, "rev-parse", "HEAD").strip()
    return RepoInfo(root=root, head_commit=head)


def _git(cwd: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
    except FileNotFoundError as exc:
        raise GitError("git is not installed or not on PATH") from exc
    except subprocess.CalledProcessError as exc:
        raise GitError(exc.stderr.strip() or f"git {' '.join(args)} failed") from exc
    return result.stdout
