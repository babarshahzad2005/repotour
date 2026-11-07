"""Python: static imports, resolved against the repository's own modules.

Resolution: relative imports walk up from the importing file's package;
absolute imports are looked up in a module index built from every source
root (the repository root, any `src/` directory, and any directory holding a
`pyproject.toml`, `setup.py`, or `setup.cfg`). For `from a import b`, a
submodule `a.b` wins over `a/__init__.py`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath

import tree_sitter_python
from tree_sitter import Language, Node, Parser, Query, QueryCursor

from repotour.languages.base import ParseResult, RawImport

_LANGUAGE = Language(tree_sitter_python.language())
_STATEMENTS = Query(_LANGUAGE, "(import_statement) @s (import_from_statement) @s")
_PROJECT_FILES = ("pyproject.toml", "setup.py", "setup.cfg")


@dataclass(frozen=True)
class PythonIndex:
    modules: dict[str, str]  # dotted module name -> repo path
    paths: frozenset[str]


class PythonAdapter:
    name = "Python"
    version = 1

    def handles(self, path: str) -> bool:
        return path.endswith((".py", ".pyi"))

    def parse(self, source: bytes) -> ParseResult:
        tree = Parser(_LANGUAGE).parse(source)
        statements = QueryCursor(_STATEMENTS).captures(tree.root_node).get("s", [])
        imports: list[RawImport] = []
        for node in sorted(statements, key=lambda n: n.start_byte):
            line = node.start_point[0] + 1
            if node.type == "import_statement":
                for name in node.children_by_field_name("name"):
                    imports.append(RawImport(module=_dotted(name), names=(), line=line))
            else:
                module = node.child_by_field_name("module_name")
                if module is None:
                    continue
                names = tuple(_dotted(n) for n in node.children_by_field_name("name"))
                imports.append(RawImport(module=_text(module), names=names, line=line))
        return ParseResult(imports=tuple(imports), has_error=tree.root_node.has_error)

    def build_index(self, paths: Sequence[str], all_paths: Sequence[str]) -> PythonIndex:
        roots = {""}
        for path in all_paths:
            pure = PurePosixPath(path)
            if pure.name in _PROJECT_FILES:
                parent = _parent(path)
                roots.update({parent, f"{parent}/src" if parent else "src"})
            if "src" in pure.parts[:-1]:
                parts = pure.parts
                roots.add("/".join(parts[: parts.index("src") + 1]))
        modules: dict[str, str] = {}
        for path in sorted(paths):
            for root in sorted(roots):
                name = _module_name(path, root)
                if name:
                    modules.setdefault(name, path)
        return PythonIndex(modules=modules, paths=frozenset(paths))

    def resolve(self, raw: RawImport, from_path: str, index: PythonIndex) -> tuple[str, ...]:
        relative = raw.module.startswith(".")
        module_path = _relative_target(raw, from_path) if relative else PurePosixPath()

        def find(name: str) -> str | None:
            if relative:
                return _as_module(module_path / name, index)
            return index.modules.get(f"{raw.module}.{name}")

        module = _as_module(module_path, index) if relative else index.modules.get(raw.module)
        submodules = [found for name in raw.names if (found := find(name)) is not None]
        # Names that are not submodules are attributes of the module itself.
        if module is not None and len(submodules) < max(len(raw.names), 1):
            submodules.append(module)
        return tuple(sorted(set(submodules)))

    def external_name(self, raw: RawImport) -> str:
        return raw.module.lstrip(".").split(".", 1)[0]


def _relative_target(raw: RawImport, from_path: str) -> PurePosixPath:
    level = len(raw.module) - len(raw.module.lstrip("."))
    rest = raw.module[level:]
    base = PurePosixPath(from_path).parent
    for _ in range(level - 1):
        base = base.parent
    return base.joinpath(*rest.split(".")) if rest else base


def _as_module(path: PurePosixPath, index: PythonIndex) -> str | None:
    base = "" if str(path) == "." else str(path)
    for candidate in (f"{base}.py", f"{base}.pyi", f"{base}/__init__.py", f"{base}/__init__.pyi"):
        candidate = candidate.lstrip("/")
        if candidate in index.paths:
            return candidate
    return None


def _module_name(path: str, root: str) -> str | None:
    prefix = f"{root}/" if root else ""
    if not path.startswith(prefix):
        return None
    parts = list(PurePosixPath(path[len(prefix) :]).with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    if not parts or not all(p.isidentifier() for p in parts):
        return None
    return ".".join(parts)


def _parent(path: str) -> str:
    parent = str(PurePosixPath(path).parent)
    return "" if parent == "." else parent


def _dotted(node: Node) -> str:
    target = node.child_by_field_name("name") if node.type == "aliased_import" else node
    return _text(target if target is not None else node)


def _text(node: Node) -> str:
    return (node.text or b"").decode("utf-8", "replace")
