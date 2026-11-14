"""Project types (web app, library, CLI, monorepo) and monorepo packages,
read from manifests and build files. Every type carries the evidence that
produced it; when no rule matches, there are no types ("unknown").
"""

from __future__ import annotations

import json
import re
import tomllib
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any

import yaml

from repotour import repopath
from repotour.model.snapshot import RepoSnapshot
from repotour.model.tour import Evidence, Package, ProjectType
from repotour.scan.globs import matches_exactly

KIND_ORDER = ("monorepo", "web app", "library", "CLI")
MAX_EVIDENCE_PER_KIND = 3
PACKAGE_MANIFESTS = ("package.json", "pyproject.toml", "setup.py", "go.mod", "Cargo.toml")

PYTHON_WEB_FRAMEWORKS = frozenset(
    {
        "django", "flask", "fastapi", "starlette", "tornado", "aiohttp", "pyramid",
        "sanic", "bottle", "quart", "litestar", "falcon",
    }
)  # fmt: skip
JS_WEB_FRAMEWORKS = frozenset(
    {
        "react", "react-dom", "next", "vue", "nuxt", "svelte", "@sveltejs/kit",
        "@angular/core", "express", "koa", "fastify", "@nestjs/core", "@hapi/hapi",
        "@remix-run/react", "astro", "solid-js", "preact",
    }
)  # fmt: skip
_GO_PACKAGE = re.compile(r"^package\s+(\w+)", re.MULTILINE)
_GO_SERVER = re.compile(r"ListenAndServe(TLS)?\(|http\.Server\{")
_EXPOSE = re.compile(r"^\s*EXPOSE\s+(.+?)\s*$", re.MULTILINE | re.IGNORECASE)
_REQUIREMENT_NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")


@dataclass
class Detection:
    types: tuple[ProjectType, ...]
    packages: tuple[Package, ...]
    warnings: list[str] = field(default_factory=list)


def detect(snapshot: RepoSnapshot) -> Detection:
    return _Detector(snapshot).run()


class _Detector:
    def __init__(self, snapshot: RepoSnapshot) -> None:
        self.snapshot = snapshot
        self.paths = {f.path for f in snapshot.files if not f.is_excluded}
        self.evidence: dict[str, list[Evidence]] = defaultdict(list)
        self.warnings: list[str] = []

    def run(self) -> Detection:
        package_dirs = self._monorepo_packages()
        packages = tuple(self._package(d) for d in package_dirs)
        go_module_dirs = sorted({_parent(p) for p in self.paths if repopath.name(p) == "go.mod"})
        for directory in ["", *package_dirs]:
            self._detect_in(directory, go_module_dirs)
        types = tuple(
            ProjectType(
                kind=kind,
                evidence=tuple(
                    sorted(set(self.evidence[kind]), key=lambda e: (e.ref, e.detail or ""))
                )[:MAX_EVIDENCE_PER_KIND],
            )
            for kind in KIND_ORDER
            if self.evidence[kind]
        )
        return Detection(types=types, packages=packages, warnings=self.warnings)

    # --- monorepo --------------------------------------------------------------------

    def _monorepo_packages(self) -> list[str]:
        root_package = self._json("package.json")
        if isinstance(root_package, dict) and "workspaces" in root_package:
            workspaces = root_package["workspaces"]
            if isinstance(workspaces, dict):
                workspaces = workspaces.get("packages", [])
            self._add("monorepo", "package.json", '"workspaces"')
            return self._expand(_strings(workspaces), "package.json")

        pnpm = self._yaml("pnpm-workspace.yaml")
        if isinstance(pnpm, dict):
            self._add("monorepo", "pnpm-workspace.yaml", "pnpm workspace")
            return self._expand(_strings(pnpm.get("packages", [])), "package.json")

        if "go.work" in self.paths:
            self._add("monorepo", "go.work", "Go workspace")
            uses = _go_work_uses(self._text("go.work"))
            return sorted(d for d in uses if d and f"{d}/go.mod" in self.paths)

        cargo = self._toml("Cargo.toml")
        if isinstance(cargo, dict) and isinstance(cargo.get("workspace"), dict):
            self._add("monorepo", "Cargo.toml", "[workspace]")
            members = _strings(cargo["workspace"].get("members", []))
            return self._expand(members, "Cargo.toml")

        top_level = sorted(
            {
                _parent(p)
                for p in self.paths
                if repopath.name(p) in PACKAGE_MANIFESTS and p.count("/") == 1
            }
        )
        if len(top_level) >= 2:
            for directory in top_level:
                manifest = self._manifest_in(directory)
                self._add("monorepo", manifest, f"manifests in {len(top_level)} directories")
            return top_level
        return []

    def _expand(self, patterns: list[str], manifest: str) -> list[str]:
        include = [p for p in patterns if not p.startswith("!")]
        exclude = [p[1:] for p in patterns if p.startswith("!")]
        dirs = {_parent(p) for p in self.paths if repopath.name(p) == manifest and "/" in p}
        return sorted(
            d
            for d in dirs
            if any(matches_exactly(p, d) for p in include)
            and not any(matches_exactly(p, d) for p in exclude)
        )

    def _package(self, directory: str) -> Package:
        manifest = self._manifest_in(directory)
        return Package(
            path=directory,
            name=self._package_name(manifest),
            evidence=(Evidence(kind="file", ref=manifest),),
        )

    def _manifest_in(self, directory: str) -> str:
        for name in PACKAGE_MANIFESTS:
            if f"{directory}/{name}" in self.paths:
                return f"{directory}/{name}"
        return directory

    def _package_name(self, manifest: str) -> str | None:
        name = repopath.name(manifest)
        value: Any = None
        if name == "package.json":
            data = self._json(manifest)
            value = data.get("name") if isinstance(data, dict) else None
        elif name in ("pyproject.toml", "Cargo.toml"):
            data = self._toml(manifest)
            table = "project" if name == "pyproject.toml" else "package"
            section = data.get(table) if isinstance(data, dict) else None
            value = section.get("name") if isinstance(section, dict) else None
        elif name == "go.mod":
            match = re.search(r"^module\s+(\S+)", self._text(manifest), re.MULTILINE)
            value = match.group(1) if match else None
        return value if isinstance(value, str) else None

    # --- per-directory types ---------------------------------------------------------

    def _detect_in(self, directory: str, go_module_dirs: list[str]) -> None:
        prefix = f"{directory}/" if directory else ""
        self._package_json(f"{prefix}package.json")
        self._pyproject(f"{prefix}pyproject.toml")
        self._setup_files(prefix)
        self._requirements(f"{prefix}requirements.txt")
        if f"{prefix}manage.py" in self.paths:
            self._add("web app", f"{prefix}manage.py", "Django manage.py")
        self._cargo(prefix)
        if f"{prefix}go.mod" in self.paths:
            self._go(directory, go_module_dirs)
        self._dockerfile(f"{prefix}Dockerfile")

    def _package_json(self, path: str) -> None:
        data = self._json(path)
        if not isinstance(data, dict):
            return
        library_keys = [k for k in ("main", "exports", "module") if k in data]
        default_index = f"{_parent(path)}/index.js" if _parent(path) else "index.js"
        if library_keys:
            self._add("library", path, f'"{library_keys[0]}"')
        elif not data.get("private") and default_index in self.paths:
            self._add("library", path, "index.js (Node's default main)")
            library_keys = ["main"]
        if "bin" in data:
            self._add("CLI", path, '"bin"')
        deps = data.get("dependencies")
        if not library_keys and isinstance(deps, dict):
            web = sorted(JS_WEB_FRAMEWORKS & set(deps))
            if web:
                self._add("web app", path, f"depends on {web[0]}")

    def _pyproject(self, path: str) -> None:
        data = self._toml(path)
        if not isinstance(data, dict):
            return
        project = data.get("project")
        poetry = data.get("tool", {}).get("poetry") if isinstance(data.get("tool"), dict) else None
        if isinstance(project, dict):
            web = self._python_web(project.get("name"), _strings(project.get("dependencies", [])))
            if web:
                self._add("web app", path, f"depends on {web}")
            else:
                self._add("library", path, "[project]")
            if project.get("scripts"):
                self._add("CLI", path, "[project.scripts]")
        elif isinstance(poetry, dict):
            deps = poetry.get("dependencies", {})
            web = self._python_web(poetry.get("name"), list(deps) if isinstance(deps, dict) else [])
            if web:
                self._add("web app", path, f"depends on {web}")
            else:
                self._add("library", path, "[tool.poetry]")
            if poetry.get("scripts"):
                self._add("CLI", path, "[tool.poetry.scripts]")

    def _setup_files(self, prefix: str) -> None:
        setup_py = f"{prefix}setup.py"
        if setup_py in self.paths:
            text = self._text(setup_py)
            self._add("library", setup_py, "setup.py")
            if "console_scripts" in text or "scripts=" in text:
                self._add("CLI", setup_py, "console_scripts")
        setup_cfg = f"{prefix}setup.cfg"
        if setup_cfg in self.paths and "console_scripts" in self._text(setup_cfg):
            self._add("CLI", setup_cfg, "console_scripts")

    def _requirements(self, path: str) -> None:
        if path not in self.paths:
            return
        names = []
        for line in self._text(path).splitlines():
            match = _REQUIREMENT_NAME.match(line)
            if match and not line.lstrip().startswith(("#", "-")):
                names.append(match.group(1))
        web = self._python_web(None, names)
        if web:
            self._add("web app", path, f"depends on {web}")

    def _cargo(self, prefix: str) -> None:
        path = f"{prefix}Cargo.toml"
        data = self._toml(path)
        if not isinstance(data, dict) or not isinstance(data.get("package"), dict):
            return
        if "lib" in data or f"{prefix}src/lib.rs" in self.paths:
            self._add("library", path, "[lib]" if "lib" in data else "src/lib.rs")
        if "bin" in data or f"{prefix}src/main.rs" in self.paths:
            self._add("CLI", path, "[[bin]]" if "bin" in data else "src/main.rs")

    def _go(self, directory: str, go_module_dirs: list[str]) -> None:
        nested = [d for d in go_module_dirs if d != directory and _is_within(d, directory)]
        seen: set[str] = set()
        for path in sorted(self.paths):
            if not path.endswith(".go") or path.endswith("_test.go"):
                continue
            if not _is_within(_parent(path), directory):
                continue
            if any(_is_within(_parent(path), d) for d in nested):
                continue
            text = self._text(path)
            match = _GO_PACKAGE.search(text)
            if match is None:
                continue
            if match.group(1) == "main":
                if _GO_SERVER.search(text):
                    self._add("web app", path, "Go HTTP server")
                else:
                    self._add("CLI", path, "package main")
            else:
                relative = PurePosixPath(path).relative_to(directory) if directory else path
                package_dir = _parent(path)
                if not str(relative).startswith(("internal/", "cmd/")) and package_dir not in seen:
                    seen.add(package_dir)
                    self._add("library", path, "importable Go package")

    def _dockerfile(self, path: str) -> None:
        if path not in self.paths:
            return
        match = _EXPOSE.search(self._text(path))
        if match:
            self._add("web app", path, f"EXPOSE {match.group(1)}")

    # --- helpers ---------------------------------------------------------------------

    def _python_web(self, project_name: object, requirements: list[str]) -> str | None:
        own = str(project_name).lower() if isinstance(project_name, str) else ""
        for requirement in requirements:
            match = _REQUIREMENT_NAME.match(requirement)
            name = match.group(1).lower().replace("_", "-") if match else ""
            if name in PYTHON_WEB_FRAMEWORKS and name != own:
                return name
        return None

    def _add(self, kind: str, ref: str, detail: str) -> None:
        self.evidence[kind].append(Evidence(kind="file", ref=ref, detail=detail))

    def _text(self, path: str) -> str:
        return self.snapshot.read_bytes(path).decode("utf-8", "replace")

    def _json(self, path: str) -> Any:
        if path not in self.paths:
            return None
        try:
            return json.loads(self._text(path))
        except ValueError as exc:
            self.warnings.append(f"{path}: could not be parsed ({exc})")
            return None

    def _toml(self, path: str) -> Any:
        if path not in self.paths:
            return None
        try:
            return tomllib.loads(self._text(path))
        except tomllib.TOMLDecodeError as exc:
            self.warnings.append(f"{path}: could not be parsed ({exc})")
            return None

    def _yaml(self, path: str) -> Any:
        if path not in self.paths:
            return None
        try:
            return yaml.safe_load(self._text(path))
        except yaml.YAMLError as exc:
            self.warnings.append(f"{path}: could not be parsed ({exc})")
            return None


def _strings(value: object) -> list[str]:
    return [v for v in value if isinstance(v, str)] if isinstance(value, list) else []


def _parent(path: str) -> str:
    parent = repopath.parent(path)
    return "" if parent == "." else parent


def _is_within(path: str, directory: str) -> bool:
    return directory == "" or path == directory or path.startswith(f"{directory}/")


def _go_work_uses(text: str) -> list[str]:
    uses: list[str] = []
    in_block = False
    for raw in text.splitlines():
        line = raw.split("//")[0].strip()
        if in_block:
            if line == ")":
                in_block = False
            elif line:
                uses.append(line)
        elif line.startswith("use"):
            rest = line[3:].strip()
            if rest == "(":
                in_block = True
            elif rest:
                uses.append(rest)
    return [_normalize_dir(u.strip('"')) for u in uses]


def _normalize_dir(raw: str) -> str:
    """`./api/` -> `api`; `.` (the workspace root itself) -> ``."""
    cleaned = raw.rstrip("/")
    return "" if cleaned in ("", ".") else cleaned.removeprefix("./")
