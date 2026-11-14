"""History records, read incrementally.

The cache keeps the history of the last toured commit. For a newer HEAD that
descends from it, only the new commits are read from git; if history was
rewritten, it is read in full. History never depends on settings such as the
hotspot window, so changing them never re-reads git.

Records are always returned in one canonical order (newest committer date
first, ties by SHA), so an incremental read and a cold read are identical.
"""

from __future__ import annotations

import json
import zlib
from pathlib import Path
from typing import Any

from repotour.cache.store import CacheStore
from repotour.git import reader
from repotour.model.history import CommitRecord, FileChange


def load_history(root: Path, head: str, store: CacheStore | None) -> tuple[CommitRecord, ...]:
    if store is None:
        return canonical(reader.read_history(root, head))
    cached = store.get_history()
    if cached is not None:
        tip, payload = cached
        if tip == head:
            return _decode(payload)
        if reader.is_ancestor(root, tip, head):
            records = canonical(_decode(payload) + reader.read_history_range(root, tip, head))
            store.put_history(head, _encode(records))
            return records
    records = canonical(reader.read_history(root, head))
    store.put_history(head, _encode(records))
    return records


def canonical(records: tuple[CommitRecord, ...]) -> tuple[CommitRecord, ...]:
    return tuple(sorted(records, key=lambda r: (-r.timestamp, r.sha)))


# History can hold hundreds of thousands of records, so it has its own compact
# codec instead of the generic one in `repotour.model.serde`: each commit is
# [sha, author_name, author_email, timestamp, [[path, added, removed, old_path], ...]].


def _encode(records: tuple[CommitRecord, ...]) -> bytes:
    rows = [
        [r.sha, r.author_name, r.author_email, r.timestamp,
         [[f.path, f.added, f.removed, f.old_path] for f in r.files]]
        for r in records
    ]  # fmt: skip
    raw = json.dumps(rows, separators=(",", ":"))
    return zlib.compress(raw.encode("utf-8"), level=6)


def _decode(payload: bytes) -> tuple[CommitRecord, ...]:
    rows: list[Any] = json.loads(zlib.decompress(payload).decode("utf-8"))
    return tuple(
        CommitRecord(sha, name, email, timestamp, tuple(FileChange(*f) for f in files))
        for sha, name, email, timestamp, files in rows
    )
