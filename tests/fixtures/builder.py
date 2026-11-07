"""Build small git repositories with fully scripted history.

Every input that ends up in a commit object (content bytes, author, committer,
dates, message) is fixed, so the same script produces the same commit SHAs on
every machine and operating system. Global and system git config are ignored.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Author:
    name: str
    email: str


DEFAULT_AUTHOR = Author("Ada Lovelace", "ada@example.com")
DEFAULT_DATE = "2024-01-01T12:00:00+00:00"


@dataclass(frozen=True)
class FixtureRepo:
    root: Path
    _empty_config: Path

    @classmethod
    def create(cls, parent: Path, name: str) -> FixtureRepo:
        root = parent / name
        root.mkdir(parents=True)
        empty_config = parent / f".{name}-empty-gitconfig"
        empty_config.write_bytes(b"")
        repo = cls(root=root, _empty_config=empty_config)
        repo._git("init", "--quiet", "--initial-branch=main")
        repo._git("config", "core.autocrlf", "false")
        repo._git("config", "commit.gpgsign", "false")
        return repo

    def commit(
        self,
        message: str,
        files: dict[str, str | bytes | None],
        *,
        author: Author = DEFAULT_AUTHOR,
        date: str = DEFAULT_DATE,
        gitlinks: dict[str, str] | None = None,
    ) -> str:
        """Write, overwrite, or delete (None) files, commit them, and return the SHA.

        `gitlinks` maps a path to a commit SHA, recorded as a submodule entry.
        """
        for rel_path, content in files.items():
            target = self.root / rel_path
            if content is None:
                target.unlink()
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            data = content.encode("utf-8") if isinstance(content, str) else content
            target.write_bytes(data)
        self._git("add", "--all")
        for path, sha in (gitlinks or {}).items():
            self._git("update-index", "--add", "--cacheinfo", f"160000,{sha},{path}")
        self._git(
            "commit", "--quiet", "--allow-empty", "-m", message, extra_env=_identity(author, date)
        )
        return self._git("rev-parse", "HEAD").strip()

    def branch(self, name: str) -> None:
        """Create a branch at HEAD and switch to it."""
        self._git("switch", "--quiet", "-c", name)

    def switch(self, name: str) -> None:
        self._git("switch", "--quiet", name)

    def merge(
        self, name: str, message: str, *, author: Author = DEFAULT_AUTHOR, date: str = DEFAULT_DATE
    ) -> str:
        """Merge branch `name` into the current branch with a merge commit."""
        self._git(
            "merge", "--quiet", "--no-ff", "-m", message, name, extra_env=_identity(author, date)
        )
        return self._git("rev-parse", "HEAD").strip()

    def shallow_clone(self, name: str, depth: int = 1) -> FixtureRepo:
        """Clone this repository with truncated history into a sibling directory."""
        dest = self.root.parent / name
        self._git("clone", "--quiet", f"--depth={depth}", self.root.as_uri(), str(dest))
        return FixtureRepo(root=dest, _empty_config=self._empty_config)

    def _git(self, *args: str, extra_env: dict[str, str] | None = None) -> str:
        # Drop inherited GIT_* overrides (GIT_DIR, GIT_INDEX_FILE, ...) so the
        # developer's environment can never leak into a fixture build.
        inherited = {k: v for k, v in os.environ.items() if not k.upper().startswith("GIT_")}
        env = {
            **inherited,
            "GIT_CONFIG_GLOBAL": str(self._empty_config),
            "GIT_CONFIG_NOSYSTEM": "1",
            **(extra_env or {}),
        }
        result = subprocess.run(
            ["git", *args],
            cwd=self.root,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        return result.stdout


def _identity(author: Author, date: str) -> dict[str, str]:
    return {
        "GIT_AUTHOR_NAME": author.name,
        "GIT_AUTHOR_EMAIL": author.email,
        "GIT_AUTHOR_DATE": date,
        "GIT_COMMITTER_NAME": author.name,
        "GIT_COMMITTER_EMAIL": author.email,
        "GIT_COMMITTER_DATE": date,
    }
