"""SQLite cache of analyzer results, kept in the git common directory.

Living under `.git/` means the cache is never tracked, needs no ignore
entry, is shared by worktrees, and is safe to delete (see ADR-0004).
A cache that cannot be opened or read is rebuilt, never fatal.
"""

from __future__ import annotations

import contextlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from repotour.analyzers.base import AnalyzerResult
from repotour.model.serde import from_data, to_data
from repotour.model.tour import Evidence

CACHE_DIR_NAME = "repotour-cache"
CACHE_FILE_NAME = "cache.sqlite3"
SCHEMA_VERSION = 4

_SCHEMA = """
CREATE TABLE IF NOT EXISTS analyzer_results (
    analyzer TEXT NOT NULL,
    version INTEGER NOT NULL,
    head_commit TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    payload TEXT NOT NULL,
    PRIMARY KEY (analyzer, version, head_commit, config_hash)
);
CREATE TABLE IF NOT EXISTS history (
    tip TEXT PRIMARY KEY,
    payload BLOB NOT NULL
);
CREATE TABLE IF NOT EXISTS parse_results (
    content_hash TEXT NOT NULL,
    language TEXT NOT NULL,
    version INTEGER NOT NULL,
    payload TEXT NOT NULL,
    PRIMARY KEY (content_hash, language, version)
);
CREATE TABLE IF NOT EXISTS summaries (
    content_hash TEXT NOT NULL,
    model TEXT NOT NULL,
    prompt_version INTEGER NOT NULL,
    text TEXT NOT NULL,
    PRIMARY KEY (content_hash, model, prompt_version)
);
"""


@dataclass(frozen=True)
class ResultKey:
    analyzer: str
    version: int
    head_commit: str
    config_hash: str


class CacheStore:
    """Analyzer results (keyed by analyzer, version, commit, config hash) and the
    history records of the latest toured commit."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._db = self._open()

    def get(self, key: ResultKey) -> AnalyzerResult | None:
        try:
            row = self._db.execute(
                "SELECT payload FROM analyzer_results "
                "WHERE analyzer = ? AND version = ? AND head_commit = ? AND config_hash = ?",
                (key.analyzer, key.version, key.head_commit, key.config_hash),
            ).fetchone()
        except sqlite3.DatabaseError:
            return None
        if row is None:
            return None
        payload = json.loads(row[0])
        return AnalyzerResult(
            analyzer=key.analyzer,
            data=payload["data"],
            evidence=[from_data(Evidence, e) for e in payload["evidence"]],
            warnings=list(payload["warnings"]),
        )

    def put(self, key: ResultKey, result: AnalyzerResult) -> None:
        payload = json.dumps(
            {
                "data": result.data,
                "evidence": to_data(result.evidence),
                "warnings": result.warnings,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        with contextlib.suppress(sqlite3.DatabaseError), self._db:
            self._db.execute(
                "INSERT OR REPLACE INTO analyzer_results VALUES (?, ?, ?, ?, ?)",
                (key.analyzer, key.version, key.head_commit, key.config_hash, payload),
            )

    def get_history(self) -> tuple[str, bytes] | None:
        """The cached history: its tip commit and compressed payload, if any."""
        try:
            row = self._db.execute("SELECT tip, payload FROM history LIMIT 1").fetchone()
        except sqlite3.DatabaseError:
            return None
        return None if row is None else (row[0], row[1])

    def put_history(self, tip: str, payload: bytes) -> None:
        """Replace the cached history with the one ending at `tip`."""
        with contextlib.suppress(sqlite3.DatabaseError), self._db:
            self._db.execute("DELETE FROM history")
            self._db.execute("INSERT INTO history VALUES (?, ?)", (tip, payload))

    def get_parse(self, content_hash: str, language: str, version: int) -> str | None:
        try:
            row = self._db.execute(
                "SELECT payload FROM parse_results "
                "WHERE content_hash = ? AND language = ? AND version = ?",
                (content_hash, language, version),
            ).fetchone()
        except sqlite3.DatabaseError:
            return None
        return None if row is None else str(row[0])

    def put_parse(self, content_hash: str, language: str, version: int, payload: str) -> None:
        """Queued in the current transaction; committed on close."""
        with contextlib.suppress(sqlite3.DatabaseError):
            self._db.execute(
                "INSERT OR REPLACE INTO parse_results VALUES (?, ?, ?, ?)",
                (content_hash, language, version, payload),
            )

    def get_summary(self, content_hash: str, model: str, prompt_version: int) -> str | None:
        try:
            row = self._db.execute(
                "SELECT text FROM summaries "
                "WHERE content_hash = ? AND model = ? AND prompt_version = ?",
                (content_hash, model, prompt_version),
            ).fetchone()
        except sqlite3.DatabaseError:
            return None
        return None if row is None else str(row[0])

    def put_summary(self, content_hash: str, model: str, prompt_version: int, text: str) -> None:
        """Committed immediately: each summary cost a network call."""
        with contextlib.suppress(sqlite3.DatabaseError):
            self._db.execute(
                "INSERT OR REPLACE INTO summaries VALUES (?, ?, ?, ?)",
                (content_hash, model, prompt_version, text),
            )
            self._db.commit()

    def close(self) -> None:
        with contextlib.suppress(sqlite3.DatabaseError):
            self._db.commit()
        self._db.close()

    def _open(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            return self._connect()
        except sqlite3.DatabaseError:
            self.path.unlink(missing_ok=True)
            return self._connect()

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=30)
        try:
            (version,) = db.execute("PRAGMA user_version").fetchone()
            if version != SCHEMA_VERSION:
                db.execute("DROP TABLE IF EXISTS analyzer_results")
                db.execute("DROP TABLE IF EXISTS history")
                db.execute("DROP TABLE IF EXISTS parse_results")
                db.execute("DROP TABLE IF EXISTS summaries")
                db.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            db.executescript(_SCHEMA)
            db.commit()
        except sqlite3.DatabaseError:
            db.close()
            raise
        return db


def cache_path(git_common_dir: Path) -> Path:
    return git_common_dir / CACHE_DIR_NAME / CACHE_FILE_NAME
