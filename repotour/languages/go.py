"""Go: package imports, resolved through the module paths in go.mod files.

A Go import names a package (a directory). Each import links to one
representative file of that package (ADR-0005): the file named after the
directory, else `doc.go`, else the file with the most lines (ties by path).
Every `go.mod` in the repository counts, which covers `go.work` workspaces.
Standard library and third-party imports are external.
"""

from __future__ import annotations

import posixpath
import re
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath

import tree_sitter_go
from tree_sitter import Language, Node, Parser, Query, QueryCursor

from repotour.languages.base import DeclaredEntry, ParseResult, RawEntry, RawImport
from repotour.model.tour import Evidence

_LANGUAGE = Language(tree_sitter_go.language())
_QUERY = Query(
    _LANGUAGE,
    """
    (package_clause (package_identifier) @package)
    (import_spec path: (_) @path)
    (function_declaration name: (identifier) @function)
    (call_expression function: (selector_expression field: (field_identifier) @call))
    """,
)
_MODULE = re.compile(r"^module\s+(\S+)", re.MULTILINE)
_PACKAGE = re.compile(r"^package\s+(\w+)", re.MULTILINE)
_SERVER_CALLS = frozenset({"ListenAndServe", "ListenAndServeTLS"})


@dataclass(frozen=True)
class _Package:
    name: str
    representative: str
    files: tuple[str, ...]


@dataclass(frozen=True)
class GoIndex:
    modules: tuple[tuple[str, str], ...]  # (module path, directory), longest path first
    packages: dict[str, _Package]  # directory -> package


class GoAdapter:
    name = "Go"
    version = 1

    def handles(self, path: str) -> bool:
        return path.endswith(".go")

    def parse(self, source: bytes, path: str = "") -> ParseResult:
        tree = Parser(_LANGUAGE).parse(source)
        captures = QueryCursor(_QUERY).captures(tree.root_node)
        imports = tuple(
            RawImport(module=_text(n)[1:-1], names=(), line=n.start_point[0] + 1)
            for n in sorted(captures.get("path", []), key=lambda n: n.start_byte)
        )
        entries: list[RawEntry] = []
        package = next(iter(captures.get("package", [])), None)
        functions = {_text(n) for n in captures.get("function", [])}
        if package is not None and _text(package) == "main" and "main" in functions:
            entries.append(RawEntry("Go program (package main)", package.start_point[0] + 1))
        servers = [n for n in captures.get("call", []) if _text(n) in _SERVER_CALLS]
        if servers:
            first = min(servers, key=lambda n: n.start_byte)
            entries.append(RawEntry("starts a server", first.start_point[0] + 1))
        return ParseResult(
            imports=imports, has_error=tree.root_node.has_error, entries=tuple(entries)
        )

    def build_index(
        self, paths: Sequence[str], all_paths: Sequence[str], read: Callable[[str], str]
    ) -> GoIndex:
        modules = []
        for path in all_paths:
            if PurePosixPath(path).name == "go.mod" and "vendor/" not in path:
                match = _MODULE.search(read(path))
                if match:
                    modules.append((match.group(1), _parent(path)))
        modules.sort(key=lambda m: (-len(m[0]), m[0]))
        by_dir: dict[str, list[str]] = defaultdict(list)
        for path in sorted(paths):
            by_dir[_parent(path)].append(path)
        packages = {}
        for directory, files in by_dir.items():
            texts = {f: read(f) for f in files}
            names = [m.group(1) for f in files if (m := _PACKAGE.search(texts[f]))]
            sizes = {f: texts[f].count("\n") for f in files}
            packages[directory] = _Package(
                name=names[0] if names else "",
                representative=_representative(directory, files, sizes),
                files=tuple(files),
            )
        return GoIndex(modules=tuple(modules), packages=packages)

    def resolve(self, raw: RawImport, from_path: str, index: GoIndex) -> tuple[str, ...]:
        for module, directory in index.modules:
            if raw.module == module or raw.module.startswith(f"{module}/"):
                rest = raw.module[len(module) :].lstrip("/")
                target = posixpath.normpath(posixpath.join(directory, rest)) if rest else directory
                package = index.packages.get("" if target == "." else target)
                return (package.representative,) if package is not None else ()
        return ()

    def imported_together(self, target: str, index: GoIndex) -> tuple[str, ...]:
        package = index.packages.get(_parent(target))
        return package.files if package is not None else (target,)

    def external_name(self, raw: RawImport) -> str:
        parts = raw.module.split("/")
        return "/".join(parts[:3]) if "." in parts[0] else raw.module

    def declared_entries(
        self,
        paths: Sequence[str],
        all_paths: Sequence[str],
        read: Callable[[str], str],
        index: GoIndex,
    ) -> list[DeclaredEntry]:
        declared = []
        for module, directory in sorted(index.modules, key=lambda m: m[1]):
            package = index.packages.get(directory)
            if package is None or package.name in ("main", ""):
                continue
            manifest = f"{directory}/go.mod" if directory else "go.mod"
            declared.append(
                DeclaredEntry(
                    path=package.representative,
                    kind="public surface",
                    description=f"root package of module `{module}`",
                    evidence=Evidence(kind="file", ref=manifest, detail=f"module {module}"),
                )
            )
        return declared


def _representative(directory: str, files: list[str], sizes: dict[str, int]) -> str:
    named = f"{directory}/{PurePosixPath(directory).name}.go" if directory else None
    if named in files:
        return named
    doc = f"{directory}/doc.go" if directory else "doc.go"
    if doc in files:
        return doc
    return sorted(files, key=lambda f: (-sizes[f], f))[0]


def _parent(path: str) -> str:
    parent = str(PurePosixPath(path).parent)
    return "" if parent == "." else parent


def _text(node: Node) -> str:
    return (node.text or b"").decode("utf-8", "replace")
