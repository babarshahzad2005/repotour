from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from repotour.config import Config
from repotour.git import reader
from repotour.scan.scanner import count_lines, scan
from tests.fixtures.repos import minimal, polyglot


def snapshot_of(root: Path):  # type: ignore[no-untyped-def]
    info = reader.repo_info(root)
    return scan(info.root, info.head_commit, Config())


def test_lists_tracked_files_sorted_with_forward_slashes(tmp_path: Path) -> None:
    snapshot = snapshot_of(minimal(tmp_path).root)

    assert [f.path for f in snapshot.files] == [
        "README.md",
        "app/__init__.py",
        "app/greet.py",
        "app/main.py",
    ]


def test_hashes_are_sha256_of_committed_bytes(tmp_path: Path) -> None:
    snapshot = snapshot_of(minimal(tmp_path).root)
    readme = next(f for f in snapshot.files if f.path == "README.md")

    expected = hashlib.sha256(b"# minimal\n\nA tiny example project.\n").hexdigest()
    assert readme.content_hash == expected


def test_reads_head_not_the_working_tree(tmp_path: Path) -> None:
    repo = minimal(tmp_path)
    (repo.root / "README.md").write_text("uncommitted\n", encoding="utf-8")
    (repo.root / "untracked.py").write_text("x = 1\n", encoding="utf-8")

    snapshot = snapshot_of(repo.root)

    assert snapshot.read_bytes("README.md").startswith(b"# minimal")
    assert "untracked.py" not in [f.path for f in snapshot.files]


@pytest.mark.parametrize(
    ("data", "lines"),
    [
        (b"", 0),
        (b"a", 1),
        (b"a\n", 1),
        (b"a\nb", 2),
        (b"a\r\nb\r\n", 2),
        (b"\n\n", 2),
    ],
)
def test_count_lines(data: bytes, lines: int) -> None:
    assert count_lines(data) == lines


def test_detects_languages_by_extension(tmp_path: Path) -> None:
    snapshot = snapshot_of(polyglot(tmp_path).root)
    languages = {f.path: f.language for f in snapshot.files}

    assert languages["server/main.go"] == "Go"
    assert languages["web/app.ts"] == "TypeScript"
    assert languages["web/legacy.js"] == "JavaScript"
    assert languages["tools/build.py"] == "Python"
    assert languages["README.md"] is None
    assert languages["LICENSE"] is None


def test_basic_categories(tmp_path: Path) -> None:
    snapshot = snapshot_of(polyglot(tmp_path).root)
    categories = {f.path: f.category for f in snapshot.files}

    assert categories["server/main.go"] == "source"
    assert categories["README.md"] == "docs"
    assert categories["config.yml"] == "config"
    assert categories["LICENSE"] == "other"
