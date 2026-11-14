"""One-line purposes for top-level directories, plus maintainer notes.

A purpose comes from, in priority order: a note in `.repotour.yml`, the
first sentence of the directory's own README, a table of well-known names,
and finally a summary of the files it contains. It is never guessed.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

from repotour import repopath
from repotour.config import CONFIG_FILE
from repotour.model.snapshot import Category, FileInfo, RepoSnapshot
from repotour.model.tour import DirectoryPurpose, Evidence, Note

MAX_PURPOSE_CHARS = 120
_TRUNCATE_AT = 115

WELL_KNOWN: dict[str, str] = {
    "src": "Source code",
    "lib": "Library code",
    "app": "Application code",
    "apps": "Applications",
    "packages": "Packages of a monorepo",
    "pkg": "Go packages",
    "cmd": "Executable entry points (Go commands)",
    "internal": "Internal packages, not meant for outside use",
    "bin": "Executables and launcher scripts",
    "test": "Tests",
    "tests": "Tests",
    "spec": "Tests (specs)",
    "__tests__": "Tests",
    "e2e": "End-to-end tests",
    "fixtures": "Test fixtures",
    "testdata": "Test data",
    "docs": "Documentation",
    "doc": "Documentation",
    "examples": "Examples",
    "example": "Examples",
    "samples": "Examples",
    "benchmarks": "Benchmarks",
    "bench": "Benchmarks",
    "scripts": "Helper scripts",
    "tools": "Development tools",
    "assets": "Static assets",
    "static": "Static assets",
    "public": "Public static files",
    "templates": "Templates",
    "config": "Configuration",
    "conf": "Configuration",
    "migrations": "Database migrations",
    "deploy": "Deployment configuration",
    "deployment": "Deployment configuration",
    "infra": "Infrastructure configuration",
    "k8s": "Kubernetes manifests",
    "vendor": "Vendored third-party code",
    "third_party": "Vendored third-party code",
    "dist": "Build output",
    "build": "Build output or build scripts",
    "include": "Public headers",
    "api": "API definitions or handlers",
    "web": "Web frontend",
    "frontend": "Frontend application",
    "backend": "Backend application",
    "server": "Server code",
    "client": "Client code",
    "locales": "Translations",
    "i18n": "Translations",
    ".github": "GitHub workflows and repository settings",
    ".gitlab": "GitLab CI and repository settings",
    ".circleci": "CircleCI configuration",
    ".vscode": "Editor settings (VS Code)",
    ".devcontainer": "Development container configuration",
}

CATEGORY_ORDER: tuple[Category, ...] = (
    "source",
    "test",
    "docs",
    "config",
    "generated",
    "vendored",
    "other",
)

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")
_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_INLINE_MARKUP = re.compile(r"\*\*|__|`")


@dataclass
class DirectoryFindings:
    purposes: tuple[DirectoryPurpose, ...]
    notes: tuple[Note, ...]
    warnings: list[str] = field(default_factory=list)


def describe_directories(snapshot: RepoSnapshot) -> DirectoryFindings:
    submodules = set(snapshot.submodules)
    tracked = [f.path for f in snapshot.files] + list(submodules)
    top_level = sorted({p.split("/", 1)[0] for p in tracked if "/" in p} - submodules)
    notes, warnings = _notes(snapshot, tracked)
    dir_notes = {path: text for path, text in notes if path in top_level}
    purposes = tuple(_purpose(d, snapshot, dir_notes) for d in top_level)
    other_notes = tuple(
        Note(path=path, text=text, evidence=(_note_evidence(path),))
        for path, text in notes
        if path not in top_level
    )
    return DirectoryFindings(purposes=purposes, notes=other_notes, warnings=warnings)


def first_sentence(markdown: str) -> str | None:
    """The first sentence of the first prose paragraph, without markup."""
    paragraph: list[str] = []
    for raw in markdown.splitlines():
        line = _INLINE_MARKUP.sub("", _LINK.sub(r"\1", _IMAGE.sub("", raw))).strip()
        if not line:
            if paragraph:
                break
            continue
        if line.startswith(("#", "<", ">", "|", "---", "===", "```")):
            if paragraph:
                break
            continue
        paragraph.append(line)
    if not paragraph:
        return None
    sentence = _SENTENCE_END.split(" ".join(paragraph), maxsplit=1)[0].strip()
    if len(sentence) > MAX_PURPOSE_CHARS:
        sentence = sentence[:_TRUNCATE_AT].rstrip() + "…"
    return sentence or None


def _purpose(directory: str, snapshot: RepoSnapshot, notes: dict[str, str]) -> DirectoryPurpose:
    if directory in notes:
        return DirectoryPurpose(
            path=directory, purpose=notes[directory], evidence=(_note_evidence(directory),)
        )
    readme = _readme(directory, snapshot)
    if readme is not None:
        sentence = first_sentence(snapshot.read_bytes(readme).decode("utf-8", "replace"))
        if sentence:
            return DirectoryPurpose(
                path=directory,
                purpose=sentence,
                evidence=(Evidence(kind="file", ref=readme, detail="first sentence"),),
            )
    if directory in WELL_KNOWN:
        return DirectoryPurpose(
            path=directory,
            purpose=WELL_KNOWN[directory],
            evidence=(
                Evidence(kind="file", ref=f"{directory}/", detail="well-known directory name"),
            ),
        )
    members = [f for f in snapshot.files if f.path.startswith(f"{directory}/")]
    submodules = [s for s in snapshot.submodules if s.startswith(f"{directory}/")]
    return DirectoryPurpose(
        path=directory,
        purpose=_summary(members, len(submodules)),
        evidence=(Evidence(kind="file", ref=f"{directory}/", detail="file categories"),),
    )


def _readme(directory: str, snapshot: RepoSnapshot) -> str | None:
    candidates = sorted(
        f.path
        for f in snapshot.files
        if repopath.parent(f.path) == directory and repopath.stem(f.path).lower() == "readme"
    )
    return candidates[0] if candidates else None


def _summary(members: list[FileInfo], submodules: int = 0) -> str:
    """E.g. "3 files: 2 source (Go), 1 docs", or "1 submodule"."""
    pieces = []
    if members:
        pieces.append(_file_summary(members))
    if submodules:
        pieces.append(f"{submodules} submodule{'' if submodules == 1 else 's'}")
    return "; ".join(pieces)


def _file_summary(members: list[FileInfo]) -> str:
    counts = Counter(f.category for f in members)
    parts = []
    for category in CATEGORY_ORDER:
        if not counts[category]:
            continue
        part = f"{counts[category]} {category}"
        if category == "source":
            languages = Counter(
                f.language for f in members if f.category == "source" and f.language
            )
            if languages:
                ordered = sorted(languages, key=lambda lang: (-languages[lang], lang))
                part += f" ({', '.join(ordered)})"
        parts.append(part)
    total = len(members)
    return f"{total} file{'' if total == 1 else 's'}: {', '.join(parts)}"


def _notes(snapshot: RepoSnapshot, tracked: list[str]) -> tuple[list[tuple[str, str]], list[str]]:
    notes: list[tuple[str, str]] = []
    warnings: list[str] = []
    for raw_key, text in snapshot.config.notes:
        path = raw_key.strip().removeprefix("./").strip("/")
        exists = any(p == path or p.startswith(f"{path}/") for p in tracked)
        if path and exists:
            notes.append((path, text))
        else:
            warnings.append(
                f"{CONFIG_FILE}: note for '{raw_key}' points to a path that does not exist"
            )
    return sorted(notes), warnings


def _note_evidence(path: str) -> Evidence:
    return Evidence(kind="config", ref=CONFIG_FILE, detail=f"notes: {path}")
