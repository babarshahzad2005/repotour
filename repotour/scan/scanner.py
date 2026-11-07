"""Lists tracked files at a commit and describes each one."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from functools import cache
from pathlib import Path
from types import MappingProxyType

from repotour.cache.history import load_history
from repotour.config import Config
from repotour.git import reader
from repotour.model.history import CommitRecord
from repotour.model.snapshot import FileInfo, RepoSnapshot
from repotour.scan.classifier import classify


def scan(
    root: Path,
    head_commit: str,
    config: Config,
    history_source: Callable[[], tuple[CommitRecord, ...]] | None = None,
) -> RepoSnapshot:
    listing = reader.list_tree(root, head_commit)
    paths = [e.path for e in listing.files]
    blobs = reader.read_blobs(root, [e.oid for e in listing.files])
    contents = {e.path: blobs[e.oid] for e in listing.files}
    attrs = reader.check_attributes(root, paths)

    files: list[FileInfo] = []
    warnings: list[str] = []
    for path in paths:
        data = contents[path]
        result = classify(path, data, attrs.get(path, {}), config)
        files.append(
            FileInfo(
                path=path,
                language=result.language,
                lines=count_lines(data),
                content_hash=hashlib.sha256(data).hexdigest(),
                category=result.category,
                reason=result.reason,
            )
        )
        if result.warning is not None:
            warnings.append(result.warning)

    return RepoSnapshot(
        root=root,
        head_commit=head_commit,
        files=tuple(files),
        config=config,
        submodules=listing.submodules,
        warnings=tuple(warnings),
        head_timestamp=reader.commit_timestamp(root, head_commit),
        contents=MappingProxyType(contents),
        history_source=cache(history_source or (lambda: load_history(root, head_commit, None))),
    )


def count_lines(data: bytes) -> int:
    if not data:
        return 0
    return data.count(b"\n") + (0 if data.endswith(b"\n") else 1)
