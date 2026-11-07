"""JavaScript and TypeScript: static imports, resolved like bundlers do.

Grammars: TypeScript for .ts/.mts/.cts, TSX for .tsx, JavaScript (with JSX)
for everything else. Static forms only: `import ... from`, `export ... from`,
`require('literal')`, and TypeScript `import x = require('literal')`.

Resolution: relative paths (extension inference, index files, `.js`
specifiers that point at `.ts` sources), `tsconfig.json` `paths` and
`baseUrl` (nearest config wins), and workspace packages by their
`package.json` name. Anything else is an external package.
"""

from __future__ import annotations

import json
import posixpath
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

import tree_sitter_javascript
import tree_sitter_typescript
from tree_sitter import Language, Node, Parser, Query, QueryCursor

from repotour.languages.base import DeclaredEntry, ParseResult, RawEntry, RawImport
from repotour.model.tour import Evidence

_JAVASCRIPT = Language(tree_sitter_javascript.language())
_TYPESCRIPT = Language(tree_sitter_typescript.language_typescript())
_TSX = Language(tree_sitter_typescript.language_tsx())

_COMMON = """
(import_statement source: (string) @source)
(export_statement source: (string) @source)
(call_expression function: (identifier) @require arguments: (arguments . (string) @source))
(call_expression function: (member_expression property: (property_identifier) @listen))
(binary_expression) @comparison
"""
_TS_ONLY = "(import_require_clause source: (string) @source)"
_QUERIES = {
    id(_JAVASCRIPT): Query(_JAVASCRIPT, _COMMON),
    id(_TYPESCRIPT): Query(_TYPESCRIPT, _COMMON + _TS_ONLY),
    id(_TSX): Query(_TSX, _COMMON + _TS_ONLY),
}

EXTENSIONS = (".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts")
_RESOLVE_ORDER = (".ts", ".tsx", ".d.ts", ".js", ".jsx", ".mjs", ".cjs", ".mts", ".cts")
_JS_TO_TS = {".js": (".ts", ".tsx"), ".jsx": (".tsx",), ".mjs": (".mts",), ".cjs": (".cts",)}
_EXPORT_CONDITIONS = ("import", "module", "default", "require", "node")


@dataclass(frozen=True)
class _TsConfig:
    directory: str  # where the tsconfig.json lives ("" for the root)
    base_url: str | None  # resolved directory, or None
    paths: tuple[tuple[str, tuple[str, ...]], ...]  # pattern -> targets (resolved)


@dataclass(frozen=True)
class _Package:
    directory: str
    entries: tuple[str, ...]  # candidate entry specifiers, relative to the directory


@dataclass(frozen=True)
class JavaScriptIndex:
    paths: frozenset[str]
    tsconfigs: tuple[_TsConfig, ...]  # deepest directory first
    packages: dict[str, _Package]  # package name -> package


class JavaScriptAdapter:
    name = "JavaScript/TypeScript"
    version = 1

    def handles(self, path: str) -> bool:
        return path.endswith(EXTENSIONS)

    def parse(self, source: bytes, path: str) -> ParseResult:
        language = _language_for(path)
        tree = Parser(language).parse(source)
        captures = QueryCursor(_QUERIES[id(language)]).captures(tree.root_node)
        requires = {
            n.parent.id
            for n in captures.get("require", [])
            if _text(n) == "require" and n.parent is not None
        }
        imports = []
        for node in sorted(captures.get("source", []), key=lambda n: n.start_byte):
            call = node.parent.parent if node.parent is not None else None
            if call is not None and call.type == "call_expression" and call.id not in requires:
                continue
            imports.append(RawImport(module=_string(node), names=(), line=node.start_point[0] + 1))
        entries: list[RawEntry] = []
        for node in captures.get("listen", []):
            if _text(node) == "listen":
                entries.append(RawEntry("starts a server", node.start_point[0] + 1))
        for node in captures.get("comparison", []):
            if _is_main_guard(node):
                entries.append(RawEntry("runs as a script", node.start_point[0] + 1))
        unique: dict[str, RawEntry] = {}
        for entry in sorted(entries, key=lambda e: e.line):
            unique.setdefault(entry.description, entry)
        return ParseResult(
            imports=tuple(imports),
            has_error=tree.root_node.has_error,
            entries=tuple(sorted(unique.values(), key=lambda e: e.line)),
        )

    def build_index(
        self, paths: Sequence[str], all_paths: Sequence[str], read: Callable[[str], str]
    ) -> JavaScriptIndex:
        tsconfigs = []
        packages: dict[str, _Package] = {}
        for path in sorted(all_paths):
            if "node_modules/" in path:
                continue
            name = PurePosixPath(path).name
            if name == "tsconfig.json":
                config = _tsconfig(path, read(path))
                if config is not None:
                    tsconfigs.append(config)
            elif name == "package.json":
                package = _package(path, read(path))
                if package is not None:
                    packages.setdefault(*package)
        tsconfigs.sort(key=lambda c: (-c.directory.count("/") - bool(c.directory), c.directory))
        return JavaScriptIndex(
            paths=frozenset(paths), tsconfigs=tuple(tsconfigs), packages=packages
        )

    def resolve(self, raw: RawImport, from_path: str, index: JavaScriptIndex) -> tuple[str, ...]:
        spec = raw.module
        if spec.startswith((".", "/")):
            base = posixpath.normpath(posixpath.join(posixpath.dirname(from_path), spec))
            found = _file(base, index)
            return (found,) if found else ()
        config = _nearest_config(from_path, index)
        if config is not None:
            for pattern, targets in config.paths:
                matched = _match(pattern, spec)
                if matched is None:
                    continue
                for target in targets:
                    if (found := _file(target.replace("*", matched), index)) is not None:
                        return (found,)
            if config.base_url is not None:
                found = _file(posixpath.normpath(posixpath.join(config.base_url, spec)), index)
                if found:
                    return (found,)
        name = self.external_name(raw)
        package = index.packages.get(name)
        if package is not None:
            sub = spec[len(name) :].lstrip("/")
            candidates = (sub,) if sub else (*package.entries, "index")
            for candidate in candidates:
                joined = posixpath.normpath(posixpath.join(package.directory, candidate))
                if (found := _file(joined, index)) is not None:
                    return (found,)
        return ()

    def imported_together(self, target: str, index: object) -> tuple[str, ...]:
        return (target,)

    def external_name(self, raw: RawImport) -> str:
        parts = raw.module.split("/")
        return "/".join(parts[:2]) if raw.module.startswith("@") else parts[0]

    def declared_entries(
        self,
        paths: Sequence[str],
        all_paths: Sequence[str],
        read: Callable[[str], str],
        index: JavaScriptIndex,
    ) -> list[DeclaredEntry]:
        declared: list[DeclaredEntry] = []
        for manifest in sorted(p for p in all_paths if PurePosixPath(p).name == "package.json"):
            if "node_modules/" in manifest:
                continue
            try:
                data = json.loads(read(manifest))
            except ValueError:
                continue
            if not isinstance(data, dict):
                continue
            directory = posixpath.dirname(manifest)
            fields: list[tuple[str, str, str, str]] = []  # (kind, description, field, target)
            for key in ("main", "module"):
                if isinstance(data.get(key), str):
                    fields.append(("public surface", f"package {key}", key, data[key]))
            for target in _export_targets(data.get("exports")):
                fields.append(("public surface", "package exports", "exports", target))
            bins = data.get("bin")
            if isinstance(bins, str):
                bins = {str(data.get("name", "bin")): bins}
            for name, target in sorted(bins.items()) if isinstance(bins, dict) else []:
                if isinstance(target, str):
                    fields.append(("execution", f"package binary `{name}`", "bin", target))
            for kind, description, key, target in fields:
                joined = posixpath.normpath(posixpath.join(directory, target))
                found = _file(joined, index)
                if found is None:
                    continue
                declared.append(
                    DeclaredEntry(
                        path=found,
                        kind=kind,
                        description=f'{description} (`{manifest}` "{key}")',
                        evidence=Evidence(kind="file", ref=manifest, detail=f'"{key}": {target}'),
                    )
                )
        return declared


def _language_for(path: str) -> Language:
    if path.endswith(".tsx"):
        return _TSX
    if path.endswith((".ts", ".mts", ".cts")):
        return _TYPESCRIPT
    return _JAVASCRIPT


def _file(base: str, index: JavaScriptIndex) -> str | None:
    base = base.removeprefix("./")
    if base.startswith("..") or not base or base == ".":
        return None
    if base in index.paths:
        return base
    stem, suffix = posixpath.splitext(base)
    for replacement in _JS_TO_TS.get(suffix, ()):
        if stem + replacement in index.paths:
            return stem + replacement
    for extension in _RESOLVE_ORDER:
        if base + extension in index.paths:
            return base + extension
    for extension in _RESOLVE_ORDER:
        if f"{base}/index{extension}" in index.paths:
            return f"{base}/index{extension}"
    return None


def _nearest_config(path: str, index: JavaScriptIndex) -> _TsConfig | None:
    for config in index.tsconfigs:
        if not config.directory or path.startswith(f"{config.directory}/"):
            return config
    return None


def _match(pattern: str, spec: str) -> str | None:
    if "*" not in pattern:
        return "" if pattern == spec else None
    prefix, suffix = pattern.split("*", 1)
    if spec.startswith(prefix) and spec.endswith(suffix) and len(spec) >= len(prefix + suffix):
        return spec[len(prefix) : len(spec) - len(suffix)]
    return None


def _tsconfig(path: str, text: str) -> _TsConfig | None:
    try:
        data = json.loads(_strip_jsonc(text))
    except ValueError:
        return None
    options = data.get("compilerOptions") if isinstance(data, dict) else None
    if not isinstance(options, dict):
        return None
    directory = posixpath.dirname(path)
    base_url = options.get("baseUrl")
    base = (
        posixpath.normpath(posixpath.join(directory, base_url))
        if isinstance(base_url, str)
        else None
    )
    if base == ".":
        base = ""
    root_for_paths = base if base is not None else directory
    patterns = []
    raw_paths = options.get("paths")
    for pattern, targets in sorted(raw_paths.items()) if isinstance(raw_paths, dict) else []:
        resolved = tuple(
            posixpath.normpath(posixpath.join(root_for_paths, t))
            for t in targets if isinstance(t, str)
        )  # fmt: skip
        patterns.append((pattern, resolved))
    return _TsConfig(directory=directory, base_url=base, paths=tuple(patterns))


def _package(path: str, text: str) -> tuple[str, _Package] | None:
    try:
        data = json.loads(text)
    except ValueError:
        return None
    if not isinstance(data, dict) or not isinstance(data.get("name"), str):
        return None
    entries = [*_export_targets(data.get("exports"))]
    entries += [data[k] for k in ("module", "main") if isinstance(data.get(k), str)]
    return data["name"], _Package(directory=posixpath.dirname(path), entries=tuple(entries))


def _export_targets(exports: Any) -> list[str]:
    """String targets of the package's "." export, in condition order."""
    if isinstance(exports, str):
        return [exports]
    if not isinstance(exports, dict):
        return []
    root = exports.get(".", exports if not any(k.startswith(".") for k in exports) else None)
    return _condition_strings(root)


def _condition_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        found: list[str] = []
        for key in _EXPORT_CONDITIONS:
            found += [s for s in _condition_strings(value.get(key)) if s not in found]
        return found
    return []


def _strip_jsonc(text: str) -> str:
    """Remove // and /* */ comments and trailing commas, outside strings."""
    out: list[str] = []
    i, in_string = 0, False
    while i < len(text):
        char = text[i]
        if in_string:
            out.append(char)
            if char == "\\" and i + 1 < len(text):
                out.append(text[i + 1])
                i += 1
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
            out.append(char)
        elif text.startswith("//", i):
            while i < len(text) and text[i] != "\n":
                i += 1
            continue
        elif text.startswith("/*", i):
            end = text.find("*/", i + 2)
            i = len(text) if end == -1 else end + 2
            continue
        else:
            out.append(char)
        i += 1
    cleaned = "".join(out)
    while True:
        shorter = _remove_trailing_comma(cleaned)
        if shorter == cleaned:
            return cleaned
        cleaned = shorter


def _remove_trailing_comma(text: str) -> str:
    return re.sub(r",(\s*[}\]])", r"\1", text)


def _is_main_guard(node: Node) -> bool:
    text = _text(node).replace(" ", "")
    return text in ("require.main===module", "module===require.main",
                    "require.main==module", "module==require.main")  # fmt: skip


def _string(node: Node) -> str:
    return _text(node)[1:-1]


def _text(node: Node) -> str:
    return (node.text or b"").decode("utf-8", "replace")
