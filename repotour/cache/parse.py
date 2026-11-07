"""Parse results per file, cached by content hash and adapter version.

Within one run every file is parsed at most once, shared by all analyzers.
With a cache store, results also persist across runs, so only changed files
are parsed again; a moved but unchanged file is never re-parsed.
"""

from __future__ import annotations

import json
from pathlib import PurePosixPath

from repotour.cache.store import CacheStore
from repotour.languages.base import LanguageAdapter, ParseResult
from repotour.model.serde import from_data, to_data
from repotour.model.snapshot import RepoSnapshot


class ParseCache:
    def __init__(self, snapshot: RepoSnapshot, store: CacheStore | None) -> None:
        self._snapshot = snapshot
        self._store = store
        self._hashes = {f.path: f.content_hash for f in snapshot.files}
        self._memo: dict[tuple[str, int, str], ParseResult] = {}

    def parse(self, adapter: LanguageAdapter, path: str) -> ParseResult:
        content_hash = self._hashes[path]
        # The extension is part of the key: one language may use several grammars.
        language = f"{adapter.name}{PurePosixPath(path).suffix}"
        key = (language, adapter.version, content_hash)
        if key in self._memo:
            return self._memo[key]
        result = self._load(language, adapter.version, content_hash)
        if result is None:
            result = adapter.parse(self._snapshot.read_bytes(path), path)
            if self._store is not None:
                payload = json.dumps(to_data(result), separators=(",", ":"))
                self._store.put_parse(content_hash, language, adapter.version, payload)
        self._memo[key] = result
        return result

    def _load(self, language: str, version: int, content_hash: str) -> ParseResult | None:
        if self._store is None:
            return None
        payload = self._store.get_parse(content_hash, language, version)
        return None if payload is None else from_data(ParseResult, json.loads(payload))
