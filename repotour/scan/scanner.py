"""Lists tracked files at a commit and describes each one."""

from __future__ import annotations

import hashlib
from pathlib import Path
from types import MappingProxyType

from repotour.config import Config
from repotour.git import reader
from repotour.model.snapshot import FileInfo, RepoSnapshot
from repotour.scan.filetypes import category_of, language_of


def scan(root: Path, head_commit: str, config: Config) -> RepoSnapshot:
    entries = reader.list_tree(root, head_commit)
    blobs = reader.read_blobs(root, [e.oid for e in entries])
    contents = {e.path: blobs[e.oid] for e in entries}
    files = tuple(_describe(e.path, contents[e.path]) for e in entries)
    return RepoSnapshot(
        root=root,
        head_commit=head_commit,
        files=files,
        config=config,
        contents=MappingProxyType(contents),
    )


def count_lines(data: bytes) -> int:
    if not data:
        return 0
    return data.count(b"\n") + (0 if data.endswith(b"\n") else 1)


def _describe(path: str, data: bytes) -> FileInfo:
    language = language_of(path)
    return FileInfo(
        path=path,
        language=language,
        lines=count_lines(data),
        content_hash=hashlib.sha256(data).hexdigest(),
        category=category_of(path, language),
    )
