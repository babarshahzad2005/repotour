"""The Tour model: the single source of truth that every renderer reads.

The model has no timestamps, so the same commit and config always produce the
same tour.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import asdict, dataclass, fields, is_dataclass
from typing import Any, Literal

EvidenceKind = Literal["file", "commit_range", "import", "config", "git_attribute"]


@dataclass(frozen=True)
class Evidence:
    """A pointer that backs a claim."""

    kind: EvidenceKind
    ref: str
    detail: str | None = None


@dataclass(frozen=True, kw_only=True)
class Claim:
    """Base for every statement the tour makes about the repository.

    A claim without evidence is a bug; see `find_unevidenced_claims`.
    """

    evidence: tuple[Evidence, ...]


@dataclass(frozen=True)
class Meta:
    """Facts about the run itself, not claims about the repository."""

    repo_name: str
    head_commit: str
    tool_version: str
    config_hash: str


@dataclass(frozen=True, kw_only=True)
class LanguageStat(Claim):
    """A programming language's share of the repository."""

    language: str
    files: int
    lines: int


@dataclass(frozen=True, kw_only=True)
class Size(Claim):
    """How big the repository is at the tour's commit."""

    files: int
    lines_of_code: int


@dataclass(frozen=True, kw_only=True)
class ExcludedFiles(Claim):
    """Generated or vendored files left out of every count."""

    category: str  # "generated" or "vendored"
    count: int


@dataclass(frozen=True, kw_only=True)
class Submodule(Claim):
    """A git submodule: listed, never entered."""

    path: str


@dataclass(frozen=True, kw_only=True)
class ProjectType(Claim):
    """One kind the repository is: "web app", "library", "CLI", or "monorepo"."""

    kind: str


@dataclass(frozen=True, kw_only=True)
class Package(Claim):
    """A package inside a monorepo."""

    path: str
    name: str | None


@dataclass(frozen=True, kw_only=True)
class Command(Claim):
    """A command quoted from the project's own files."""

    purpose: str  # "install", "run", "test", or "other"
    command: str


@dataclass(frozen=True, kw_only=True)
class DirectoryPurpose(Claim):
    """What a top-level directory is for, in one line."""

    path: str
    purpose: str


@dataclass(frozen=True, kw_only=True)
class Note(Claim):
    """A maintainer's hand-written note from `.repotour.yml`."""

    path: str
    text: str


@dataclass(frozen=True, kw_only=True)
class MissingBasic(Claim):
    """Something newcomers expect that the repository lacks."""

    item: str  # "README", "tests", "contributing guide", "license", "CI configuration"


@dataclass(frozen=True)
class Overview:
    size: Size
    languages: tuple[LanguageStat, ...] = ()
    project_types: tuple[ProjectType, ...] = ()  # empty means "unknown"
    packages: tuple[Package, ...] = ()
    commands: tuple[Command, ...] = ()
    directories: tuple[DirectoryPurpose, ...] = ()
    notes: tuple[Note, ...] = ()
    missing: tuple[MissingBasic, ...] = ()
    excluded: tuple[ExcludedFiles, ...] = ()
    submodules: tuple[Submodule, ...] = ()


@dataclass(frozen=True, kw_only=True)
class Hotspot(Claim):
    """A file ranked by how many commits changed it within the hotspot window."""

    path: str
    commits: int


@dataclass(frozen=True, kw_only=True)
class BulkCommits(Claim):
    """Bulk commits left out of hotspots and ownership, across all history."""

    count: int


@dataclass(frozen=True)
class HotspotsSection:
    since: str  # the window as configured, e.g. "6m"
    window: str  # the same, for people, e.g. "6 months"
    start: str  # first day of the window, ISO date (UTC)
    end: str  # HEAD's commit date, ISO date (UTC)
    files: tuple[Hotspot, ...] = ()
    bulk: BulkCommits | None = None


@dataclass(frozen=True, kw_only=True)
class AuthorShare(Claim):
    """An author's share of the changed lines in a directory."""

    name: str  # never an email
    lines: int
    share: int  # percent, rounded half up
    commits: int


@dataclass(frozen=True, kw_only=True)
class Contact(Claim):
    """An owner who committed to the directory recently enough to ask."""

    name: str
    last_commit: str  # ISO date (UTC)


@dataclass(frozen=True, kw_only=True)
class BusFactorWarning(Claim):
    """One author holds most of a big, busy directory."""

    name: str
    share: int  # percent


@dataclass(frozen=True, kw_only=True)
class Activity(Claim):
    """Whether an area is in flux ("active") or settled ("stable")."""

    state: str  # "active" or "stable"


@dataclass(frozen=True)
class OwnershipEntry:
    path: str
    total_lines: int
    files: int = 0  # source and test files at HEAD
    commits: int = 0  # non-bulk, non-bot commits that touched the directory
    authors: tuple[AuthorShare, ...] = ()
    contacts: tuple[Contact, ...] = ()
    bus_factor: BusFactorWarning | None = None
    activity: Activity | None = None


@dataclass(frozen=True)
class OwnershipSection:
    contact_window: str  # e.g. "12 months"
    entries: tuple[OwnershipEntry, ...] = ()


@dataclass(frozen=True, kw_only=True)
class ImportEdge(Claim):
    """One module importing another, inside the repository."""

    source: str
    target: str


@dataclass(frozen=True, kw_only=True)
class ExternalImports(Claim):
    """Modules imported from outside the repository: counted, not drawn."""

    count: int
    examples: tuple[str, ...]


@dataclass(frozen=True)
class DependencyGraphSection:
    languages: tuple[str, ...] = ()  # languages that were parsed; empty: none supported
    nodes: tuple[str, ...] = ()  # repo paths, sorted
    edges: tuple[ImportEdge, ...] = ()  # sorted by (source, target)
    external: ExternalImports | None = None


@dataclass(frozen=True, kw_only=True)
class EntryPoint(Claim):
    """A file where a reader can enter the codebase (see the glossary)."""

    path: str
    kind: str  # "execution" or "public surface"
    description: str  # e.g. "defines a CLI (Typer); runs as a script"
    pinned: bool = False


@dataclass(frozen=True)
class EntryPointsSection:
    entries: tuple[EntryPoint, ...] = ()  # pinned first, then by path, within each kind
    omitted: int = 0  # entries beyond the per-kind cap


@dataclass(frozen=True)
class Tour:
    meta: Meta
    overview: Overview | None = None
    entry_points: EntryPointsSection | None = None
    reading_order: tuple[Claim, ...] = ()
    hotspots: HotspotsSection | None = None
    ownership: OwnershipSection | None = None
    dependency_graph: DependencyGraphSection | None = None
    summaries: tuple[Claim, ...] = ()
    unavailable: tuple[str, ...] = ()  # sections whose analyzer failed
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def find_unevidenced_claims(tour: Tour) -> list[Claim]:
    """Return every claim in the tour, at any depth, that carries no evidence."""
    return [claim for claim in _iter_claims(tour) if not claim.evidence]


def _iter_claims(node: object) -> Iterator[Claim]:
    if isinstance(node, Claim):
        yield node
    if is_dataclass(node) and not isinstance(node, type):
        for f in fields(node):
            yield from _iter_claims(getattr(node, f.name))
    elif isinstance(node, tuple | list):
        for item in node:
            yield from _iter_claims(item)
    elif isinstance(node, dict):
        for value in node.values():
            yield from _iter_claims(value)
