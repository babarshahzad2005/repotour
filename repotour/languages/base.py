"""The language adapter contract."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from repotour.model.tour import Evidence


@dataclass(frozen=True)
class RawImport:
    """An import as written in the source, before resolution."""

    module: str  # e.g. "os", "a.b", "..pkg.mod" (leading dots: relative levels)
    names: tuple[str, ...]  # names in `from module import a, b`; empty otherwise
    line: int  # 1-based


@dataclass(frozen=True)
class RawEntry:
    """A code pattern that makes a file an execution entry point."""

    description: str  # e.g. "defines a CLI (Typer)"
    line: int  # 1-based


@dataclass(frozen=True)
class ParseResult:
    imports: tuple[RawImport, ...]
    has_error: bool
    entries: tuple[RawEntry, ...] = ()


@dataclass(frozen=True)
class DeclaredEntry:
    """An entry point declared outside the file itself (e.g. a manifest)."""

    path: str
    kind: str  # "execution" or "public surface"
    description: str
    evidence: Evidence


class LanguageAdapter(Protocol):
    name: str  # display name, matching the overview's language names
    version: int  # bump to invalidate this language's cached parse results

    def handles(self, path: str) -> bool: ...

    def parse(self, source: bytes, path: str) -> ParseResult:
        """Parse one file. `path` picks the grammar where a language has several."""
        ...

    def build_index(
        self, paths: Sequence[str], all_paths: Sequence[str], read: Callable[[str], str]
    ) -> Any:
        """Repo-wide lookup data for resolution. `paths` are this language's
        graph files; `all_paths` are every tracked file; `read` returns a
        tracked file's committed text (for manifests and configs)."""
        ...

    def resolve(self, raw: RawImport, from_path: str, index: Any) -> tuple[str, ...]:
        """The repo files an import refers to; empty if it is external.

        `from pkg import a, b` can refer to several submodules at once.
        """
        ...

    def external_name(self, raw: RawImport) -> str:
        """A short name for an external import, for counting (e.g. "os")."""
        ...

    def declared_entries(
        self, paths: Sequence[str], all_paths: Sequence[str], read: Callable[[str], str], index: Any
    ) -> list[DeclaredEntry]:
        """Entry points this language declares outside code patterns: public
        surfaces and manifest-declared commands."""
        ...
