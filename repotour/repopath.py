"""Fast helpers for repository paths: relative, '/'-separated, never '.' or empty.

They behave like the matching `PurePosixPath` properties for such paths, but
work on strings directly. Large repositories have hundreds of thousands of
paths, and building path objects for each dominated some analyzers.
"""

from __future__ import annotations


def name(path: str) -> str:
    """`a/b/c.py` -> `c.py`."""
    return path.rpartition("/")[2]


def parent(path: str) -> str:
    """`a/b/c.py` -> `a/b`; a top-level file's parent is `.`."""
    head, sep, _ = path.rpartition("/")
    return head if sep else "."


def suffix(path: str) -> str:
    """`a/b.tar.gz` -> `.gz`; `.bashrc` and `Makefile` have none."""
    base = name(path)
    dot = base.rfind(".")
    return base[dot:] if 0 < dot < len(base) - 1 else ""


def stem(path: str) -> str:
    """`a/README.md` -> `README`."""
    base = name(path)
    ext = suffix(base)
    return base[: len(base) - len(ext)] if ext else base


def directories(path: str) -> list[str]:
    """The directory names a path passes through: `a/b/c.py` -> `['a', 'b']`."""
    return path.split("/")[:-1]
