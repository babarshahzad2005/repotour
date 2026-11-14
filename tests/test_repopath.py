from __future__ import annotations

from pathlib import PurePosixPath

import pytest

from repotour import repopath

PATHS = [
    "README.md", "Makefile", ".bashrc", ".github/workflows/ci.yml", "a/b/c.py",
    "src/lib.tar.gz", "docs/file.", "x/.env.local", "pkg/v2/go.mod", "a/b/c",
    "deep/er/still/deeper/name.with.dots.ts", "ünïcode/fïle.py",
]  # fmt: skip


@pytest.mark.parametrize("path", PATHS)
def test_matches_pure_posix_path(path: str) -> None:
    pure = PurePosixPath(path)

    assert repopath.name(path) == pure.name
    assert repopath.parent(path) == str(pure.parent)
    assert repopath.suffix(path) == pure.suffix
    assert repopath.stem(path) == pure.stem
    assert repopath.directories(path) == list(pure.parts[:-1])
