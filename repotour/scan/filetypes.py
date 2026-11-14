"""Maps file names to languages and coarse categories.

Languages here are programming languages, used for the overview's language
breakdown. Markup, data and config formats are categories, not languages.
"""

from __future__ import annotations

from repotour import repopath
from repotour.model.snapshot import Category

LANGUAGE_BY_EXTENSION: dict[str, str] = {
    ".py": "Python",
    ".pyi": "Python",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".mjs": "JavaScript",
    ".cjs": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".mts": "TypeScript",
    ".cts": "TypeScript",
    ".go": "Go",
    ".rs": "Rust",
    ".java": "Java",
    ".kt": "Kotlin",
    ".kts": "Kotlin",
    ".scala": "Scala",
    ".rb": "Ruby",
    ".php": "PHP",
    ".c": "C",
    ".h": "C",
    ".cc": "C++",
    ".cpp": "C++",
    ".cxx": "C++",
    ".hpp": "C++",
    ".hh": "C++",
    ".cs": "C#",
    ".swift": "Swift",
    ".m": "Objective-C",
    ".dart": "Dart",
    ".ex": "Elixir",
    ".exs": "Elixir",
    ".erl": "Erlang",
    ".hs": "Haskell",
    ".lua": "Lua",
    ".pl": "Perl",
    ".r": "R",
    ".jl": "Julia",
    ".sh": "Shell",
    ".bash": "Shell",
    ".zsh": "Shell",
    ".ps1": "PowerShell",
    ".sql": "SQL",
    ".html": "HTML",
    ".htm": "HTML",
    ".css": "CSS",
    ".scss": "SCSS",
    ".sass": "Sass",
    ".less": "Less",
    ".vue": "Vue",
    ".svelte": "Svelte",
}

DOCS_EXTENSIONS = frozenset({".md", ".markdown", ".rst", ".txt", ".adoc"})
CONFIG_EXTENSIONS = frozenset(
    {".yml", ".yaml", ".json", ".toml", ".ini", ".cfg", ".conf", ".xml", ".env"}
)


def language_of(path: str) -> str | None:
    return LANGUAGE_BY_EXTENSION.get(repopath.suffix(path).lower())


PERIPHERAL_DIRS = frozenset(
    {"examples", "example", "samples", "sample", "demo", "demos", "docs", "doc",
     "benchmarks", "benchmark", "bench"}
)  # fmt: skip


def is_peripheral(path: str) -> bool:
    """Example, documentation, and benchmark code: drawn, never recommended."""
    return any(part in PERIPHERAL_DIRS for part in repopath.directories(path))


def category_of(path: str, language: str | None) -> Category:
    suffix = repopath.suffix(path).lower()
    if language is not None:
        return "source"
    if suffix in DOCS_EXTENSIONS:
        return "docs"
    if suffix in CONFIG_EXTENSIONS:
        return "config"
    return "other"
