"""Python: static imports, resolved against the repository's own modules.

Resolution: relative imports walk up from the importing file's package;
absolute imports are looked up in a module index built from every source
root (the repository root, any `src/` directory, and any directory holding a
`pyproject.toml`, `setup.py`, or `setup.cfg`). For `from a import b`, a
submodule `a.b` wins over `a/__init__.py`.
"""

from __future__ import annotations

import tomllib
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath

import tree_sitter_python
from tree_sitter import Language, Node, Parser, Query, QueryCursor

from repotour.languages.base import DeclaredEntry, ParseResult, RawEntry, RawImport
from repotour.model.tour import Evidence

_LANGUAGE = Language(tree_sitter_python.language())
_STATEMENTS = Query(_LANGUAGE, "(import_statement) @s (import_from_statement) @s")
_PATTERNS = Query(
    _LANGUAGE,
    """
    (call function: (_) @call)
    (decorator (attribute) @decorator)
    (if_statement condition: (comparison_operator) @guard)
    (assignment left: (identifier) @assigned)
    """,
)
_PROJECT_FILES = ("pyproject.toml", "setup.py", "setup.cfg")

# Calls and decorators that make a file an execution entry point.
_CLI = {
    "typer.Typer": "Typer",
    "Typer": "Typer",
    "click.command": "Click",
    "click.group": "Click",
    "argparse.ArgumentParser": "argparse",
    "ArgumentParser": "argparse",
    "fire.Fire": "Fire",
}
_WEB_APPS = {
    "Flask": "Flask",
    "flask.Flask": "Flask",
    "FastAPI": "FastAPI",
    "fastapi.FastAPI": "FastAPI",
    "Starlette": "Starlette",
    "Sanic": "Sanic",
    "Quart": "Quart",
}
_SERVERS = frozenset(
    {"uvicorn.run", "hypercorn.run", "app.run", "web.run_app", "waitress.serve", "make_server"}
)


@dataclass(frozen=True)
class PythonIndex:
    modules: dict[str, str]  # dotted module name -> repo path
    paths: frozenset[str]


class PythonAdapter:
    name = "Python"
    version = 2

    def handles(self, path: str) -> bool:
        return path.endswith((".py", ".pyi"))

    def parse(self, source: bytes, path: str = "") -> ParseResult:
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
        return ParseResult(
            imports=tuple(imports),
            has_error=tree.root_node.has_error,
            entries=_entries(tree.root_node),
        )

    def declared_entries(
        self,
        paths: Sequence[str],
        all_paths: Sequence[str],
        read: Callable[[str], str],
        index: PythonIndex,
    ) -> list[DeclaredEntry]:
        declared = [
            DeclaredEntry(
                path=path,
                kind="public surface",
                description=f"top-level package `{PurePosixPath(path).parent.name}`",
                evidence=Evidence(kind="file", ref=path, detail="package root"),
            )
            for path in paths
            if _is_top_level_package(path, index)
        ]
        declared.extend(
            _main_module_entry(path, index)
            for path in paths
            if PurePosixPath(path).name == "__main__.py"
        )
        for manifest in sorted(p for p in all_paths if PurePosixPath(p).name == "pyproject.toml"):
            declared.extend(_console_scripts(manifest, read(manifest), index))
        return declared

    def build_index(
        self,
        paths: Sequence[str],
        all_paths: Sequence[str],
        read: Callable[[str], str] | None = None,
    ) -> PythonIndex:
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

    def imported_together(self, target: str, index: object) -> tuple[str, ...]:
        return (target,)

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


def _entries(root: Node) -> tuple[RawEntry, ...]:
    found: list[tuple[int, str]] = []
    for name, nodes in QueryCursor(_PATTERNS).captures(root).items():
        for node in nodes:
            line = node.start_point[0] + 1
            text = _text(node)
            description = None
            if name in ("call", "decorator"):
                if text in _CLI:
                    description = f"defines a CLI ({_CLI[text]})"
                elif text in _WEB_APPS:
                    description = f"defines a web app ({_WEB_APPS[text]})"
                elif text in _SERVERS:
                    description = "starts a server"
            elif name == "guard":
                compact = text.replace(" ", "").replace("'", '"')
                if compact in ('__name__=="__main__"', '"__main__"==__name__'):
                    description = "runs as a script"
            elif name == "assigned" and text == "urlpatterns":
                description = "defines URL routes (Django)"
            if description is not None:
                found.append((line, description))
    entries: list[RawEntry] = []
    seen: set[str] = set()
    for line, description in sorted(found):
        if description not in seen:
            seen.add(description)
            entries.append(RawEntry(description=description, line=line))
    return tuple(entries)


def _is_top_level_package(path: str, index: PythonIndex) -> bool:
    pure = PurePosixPath(path)
    if pure.stem != "__init__" or pure.parent == PurePosixPath("."):
        return False
    if not pure.parent.name.isidentifier():
        return False
    parent_init = pure.parent.parent / "__init__.py"
    return str(parent_init) not in index.paths


def _console_scripts(manifest: str, text: str, index: PythonIndex) -> list[DeclaredEntry]:
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return []
    project = data.get("project")
    tool = data.get("tool")
    sources = [
        ("[project.scripts]", project.get("scripts") if isinstance(project, dict) else None),
        (
            "[tool.poetry.scripts]",
            tool.get("poetry", {}).get("scripts") if isinstance(tool, dict) else None,
        ),
    ]
    declared = []
    for table, scripts in sources:
        if not isinstance(scripts, dict):
            continue
        for name, target in sorted(scripts.items()):
            if not isinstance(target, str):
                continue
            module = target.split(":", 1)[0].strip()
            path = index.modules.get(module)
            if path is None:
                continue
            declared.append(
                DeclaredEntry(
                    path=path,
                    kind="execution",
                    description=f"console script `{name}`",
                    evidence=Evidence(
                        kind="file", ref=manifest, detail=f"{table} {name} = {target}"
                    ),
                )
            )
    return declared


def _main_module_entry(path: str, index: PythonIndex) -> DeclaredEntry:
    package = PurePosixPath(path).parent
    names = [n for n, p in index.modules.items() if p == f"{package}/__init__.py"]
    # The shortest dotted name comes from the deepest source root (src/flask -> flask).
    dotted = min(names, key=lambda n: (len(n), n)) if names else package.name
    return DeclaredEntry(
        path=path,
        kind="execution",
        description=f"runs with `python -m {dotted}`",
        evidence=Evidence(kind="file", ref=path, detail="package __main__ module"),
    )
