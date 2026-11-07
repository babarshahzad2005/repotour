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

DEFAULT_AUTHOR = ("Ada Lovelace", "ada@example.com")
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
        author: tuple[str, str] = DEFAULT_AUTHOR,
        date: str = DEFAULT_DATE,
    ) -> str:
        """Write, overwrite, or delete (None) files, commit them, and return the SHA."""
        for rel_path, content in files.items():
            target = self.root / rel_path
            if content is None:
                target.unlink()
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            data = content.encode("utf-8") if isinstance(content, str) else content
            target.write_bytes(data)
        self._git("add", "--all")
        name, email = author
        env = {
            "GIT_AUTHOR_NAME": name,
            "GIT_AUTHOR_EMAIL": email,
            "GIT_AUTHOR_DATE": date,
            "GIT_COMMITTER_NAME": name,
            "GIT_COMMITTER_EMAIL": email,
            "GIT_COMMITTER_DATE": date,
        }
        self._git("commit", "--quiet", "--allow-empty", "-m", message, extra_env=env)
        return self._git("rev-parse", "HEAD").strip()

    def _git(self, *args: str, extra_env: dict[str, str] | None = None) -> str:
        env = {
            **os.environ,
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
