"""Entry points declared in manifests, for any language.

Only commands that point at a tracked file count, so every entry is a real
file a newcomer can open: `package.json` scripts, `Dockerfile` `CMD` and
`ENTRYPOINT`, and Rust crates (`src/main.rs`, `src/lib.rs`, `[[bin]]`).
"""

from __future__ import annotations

import json
import re
import shlex
import tomllib
from collections.abc import Callable
from pathlib import PurePosixPath

from repotour.languages.base import DeclaredEntry
from repotour.model.tour import Evidence

_DOCKER_COMMAND = re.compile(r"^\s*(CMD|ENTRYPOINT)\s+(.+?)\s*$", re.MULTILINE | re.IGNORECASE)


def manifest_entries(paths: set[str], read: Callable[[str], str]) -> list[DeclaredEntry]:
    entries: list[DeclaredEntry] = []
    for manifest in sorted(paths):
        name = PurePosixPath(manifest).name
        base = _parent(manifest)
        if name == "package.json":
            entries.extend(_package_scripts(manifest, base, read(manifest), paths))
        elif name == "Dockerfile" or name.startswith("Dockerfile."):
            entries.extend(_docker(manifest, base, read(manifest), paths))
        elif name == "Cargo.toml":
            entries.extend(_cargo(manifest, base, read(manifest), paths))
    return entries


def _package_scripts(manifest: str, base: str, text: str, paths: set[str]) -> list[DeclaredEntry]:
    try:
        data = json.loads(text)
    except ValueError:
        return []
    scripts = data.get("scripts") if isinstance(data, dict) else None
    if not isinstance(scripts, dict):
        return []
    entries = []
    for script, command in sorted(scripts.items()):
        if not isinstance(command, str):
            continue
        for target in _files_in(command, base, paths):
            entries.append(
                DeclaredEntry(
                    path=target,
                    kind="execution",
                    description=f'npm script "{script}"',
                    evidence=Evidence(
                        kind="file", ref=manifest, detail=f'script "{script}": {command}'
                    ),
                )
            )
    return entries


def _docker(manifest: str, base: str, text: str, paths: set[str]) -> list[DeclaredEntry]:
    entries = []
    for match in _DOCKER_COMMAND.finditer(text):
        instruction, argument = match.group(1).upper(), match.group(2)
        try:
            parsed = json.loads(argument)
            tokens = [t for t in parsed if isinstance(t, str)] if isinstance(parsed, list) else []
        except ValueError:
            tokens = _split(argument)
        for target in _files_in(" ".join(shlex.quote(t) for t in tokens), base, paths):
            entries.append(
                DeclaredEntry(
                    path=target,
                    kind="execution",
                    description=f"container {instruction.lower()}",
                    evidence=Evidence(
                        kind="file", ref=manifest, detail=f"{instruction} {argument}"
                    ),
                )
            )
    return entries


def _cargo(manifest: str, base: str, text: str, paths: set[str]) -> list[DeclaredEntry]:
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return []
    if not isinstance(data.get("package"), dict):
        return []
    prefix = f"{base}/" if base else ""
    entries = []
    found: list[tuple[str, str, str]] = []
    if f"{prefix}src/main.rs" in paths:
        found.append((f"{prefix}src/main.rs", "execution", "Rust binary"))
    if f"{prefix}src/lib.rs" in paths:
        found.append((f"{prefix}src/lib.rs", "public surface", "Rust library"))
    bins = data.get("bin")
    for item in bins if isinstance(bins, list) else []:
        path = item.get("path") if isinstance(item, dict) else None
        if isinstance(path, str) and f"{prefix}{path}" in paths:
            found.append(
                (f"{prefix}{path}", "execution", f"Rust binary `{item.get('name', path)}`")
            )
    for path, kind, description in found:
        entries.append(
            DeclaredEntry(
                path=path,
                kind=kind,
                description=description,
                evidence=Evidence(kind="file", ref=manifest, detail="Cargo package"),
            )
        )
    return entries


def _files_in(command: str, base: str, paths: set[str]) -> list[str]:
    """Tracked files a command line refers to, including `python -m module`."""
    tokens = _split(command)
    found: list[str] = []
    for i, token in enumerate(tokens):
        candidates = [token]
        if i > 0 and tokens[i - 1] == "-m":
            module = token.replace(".", "/")
            candidates = [f"{module}.py", f"{module}/__main__.py", f"src/{module}.py"]
        for candidate in candidates:
            cleaned = candidate.removeprefix("./")
            for path in (f"{base}/{cleaned}" if base else cleaned, cleaned):
                if path in paths and path not in found:
                    found.append(path)
    return found


def _split(command: str) -> list[str]:
    try:
        return shlex.split(command)
    except ValueError:
        return command.split()


def _parent(path: str) -> str:
    parent = str(PurePosixPath(path).parent)
    return "" if parent == "." else parent
