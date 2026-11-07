"""Writes rendered output identically on every platform."""

from __future__ import annotations

from pathlib import Path


def write_text(path: Path, text: str) -> None:
    """Write UTF-8 with LF line endings, regardless of the platform's defaults."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.replace("\r\n", "\n").encode("utf-8"))
