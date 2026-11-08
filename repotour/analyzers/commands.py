"""How to install, run, and test the project, quoted from its own files.

Sources come in priority tiers. For each purpose (install, run, test), only
the highest tier that defines that purpose is used, so a Makefile's `test`
target hides the CI workflow's test step. Commands are never invented.

1. Makefile targets and justfile recipes
2. package.json scripts
3. pyproject.toml task runners, tox.ini, noxfile.py
4. GitHub Actions workflow steps (install and test only)
"""

from __future__ import annotations

import json
import re
import tomllib
from dataclasses import dataclass
from typing import Any

import yaml

from repotour.model.snapshot import RepoSnapshot
from repotour.model.tour import Command, Evidence

PURPOSES = ("install", "run", "test")
MAX_PER_PURPOSE = 5
MAX_OTHER = 8
SOURCES_LOOKED_AT = (
    "Makefile, justfile, package.json scripts, pyproject.toml task runners, "
    "tox.ini, noxfile.py, and GitHub Actions workflows"
)

_INSTALL_NAMES = frozenset({"install", "setup", "bootstrap", "deps", "dependencies", "init"})
_RUN_NAMES = frozenset({"run", "start", "serve", "server", "dev", "develop"})
_TEST_NAME = re.compile(r"^(test|tests|spec|e2e|unit)([-_:].*)?$")

_MAKE_TARGET = re.compile(r"^([A-Za-z0-9][\w.-]*)\s*:(?![:=])", re.MULTILINE)
_JUST_RECIPE = re.compile(r"^@?([A-Za-z0-9][\w-]*)(?:\s+[^:=\n]*)?:(?!=)", re.MULTILINE)
_NOX_SESSION = re.compile(r"@nox\.session(?:\([^)]*\))?\s*\ndef\s+(\w+)")
_CI_INSTALL = re.compile(
    r"\b(pip3? install|uv sync|uv pip install|poetry install|pdm install|pipenv install"
    r"|npm (ci|install)|yarn install|pnpm install|bun install|bundle install"
    r"|go mod download|cargo fetch|composer install)\b"
)
_CI_TEST = re.compile(
    r"\b(pytest|tox|nox|go test|cargo test|npm (run )?test|yarn test|pnpm test|bun test"
    r"|make test|jest|vitest|mocha|rspec|phpunit|unittest|mvn test|gradle test)\b"
)


@dataclass(frozen=True)
class _Found:
    purpose: str
    command: str
    ref: str
    detail: str


def find_commands(snapshot: RepoSnapshot) -> tuple[tuple[Command, ...], list[str]]:
    finder = _Finder(snapshot)
    tiers = [
        finder.makefile() + finder.justfile(),
        finder.package_json(),
        finder.pyproject() + finder.tox() + finder.nox(),
        finder.workflows(),
    ]
    chosen: list[_Found] = []
    for purpose in PURPOSES:
        for tier in tiers:
            matching = [f for f in tier if f.purpose == purpose]
            if matching:
                chosen.extend(matching[:MAX_PER_PURPOSE])
                break
    others = [f for tier in tiers for f in tier if f.purpose == "other"]
    chosen.extend(others[:MAX_OTHER])
    commands = tuple(
        Command(
            purpose=f.purpose,
            command=f.command,
            evidence=(Evidence(kind="file", ref=f.ref, detail=f.detail),),
        )
        for f in chosen
    )
    return commands, finder.warnings


def purpose_of(name: str) -> str:
    lowered = name.lower()
    if lowered in _INSTALL_NAMES:
        return "install"
    if lowered in _RUN_NAMES:
        return "run"
    if _TEST_NAME.match(lowered):
        return "test"
    return "other"


class _Finder:
    def __init__(self, snapshot: RepoSnapshot) -> None:
        self.snapshot = snapshot
        self.all_paths = {f.path for f in snapshot.files}
        self.warnings: list[str] = []

    def makefile(self) -> list[_Found]:
        path = next(
            (p for p in ("Makefile", "makefile", "GNUmakefile") if p in self.all_paths), None
        )
        if path is None:
            return []
        text = self._text(path)
        found = []
        for match in _MAKE_TARGET.finditer(text):
            name = match.group(1)
            if name.startswith(".") or "%" in name:
                continue
            recipe = _first_recipe_line(text, match.end())
            detail = f"target {name}: {recipe}" if recipe else f"target {name}"
            found.append(_Found(purpose_of(name), f"make {name}", path, detail))
        return _sorted_unique(found)

    def justfile(self) -> list[_Found]:
        path = next((p for p in ("justfile", "Justfile", ".justfile") if p in self.all_paths), None)
        if path is None:
            return []
        text = self._text(path)
        found = []
        for match in _JUST_RECIPE.finditer(text):
            name = match.group(1)
            recipe = _first_recipe_line(text, match.end())
            detail = f"recipe {name}: {recipe}" if recipe else f"recipe {name}"
            found.append(_Found(purpose_of(name), f"just {name}", path, detail))
        return _sorted_unique(found)

    def package_json(self) -> list[_Found]:
        data = self._parse("package.json", json.loads)
        scripts = data.get("scripts") if isinstance(data, dict) else None
        if not isinstance(scripts, dict):
            return []
        manager = self._package_manager()
        found = []
        for name, body in scripts.items():
            if not isinstance(body, str):
                continue
            found.append(
                _Found(
                    purpose_of(name),
                    _script_command(manager, name),
                    "package.json",
                    f'script "{name}": {body}',
                )
            )
        return _sorted_unique(found)

    def pyproject(self) -> list[_Found]:
        data = self._parse("pyproject.toml", tomllib.loads)
        tool = data.get("tool") if isinstance(data, dict) else None
        if not isinstance(tool, dict):
            return []
        found: list[_Found] = []
        runners = (
            ("poe", "tasks", "poe"),
            ("taskipy", "tasks", "task"),
            ("pdm", "scripts", "pdm run"),
        )
        for section, key, prefix in runners:
            tasks = _get(tool, section, key)
            if isinstance(tasks, dict):
                for name in tasks:
                    if not name.startswith("_"):
                        found.append(
                            _Found(
                                purpose_of(name),
                                f"{prefix} {name}",
                                "pyproject.toml",
                                f"[tool.{section}.{key}] {name}",
                            )
                        )
        envs = _get(tool, "hatch", "envs")
        if isinstance(envs, dict):
            for env_name, env in envs.items():
                scripts = env.get("scripts") if isinstance(env, dict) else None
                if not isinstance(scripts, dict):
                    continue
                for name in scripts:
                    target = name if env_name == "default" else f"{env_name}:{name}"
                    found.append(
                        _Found(
                            purpose_of(name),
                            f"hatch run {target}",
                            "pyproject.toml",
                            f"[tool.hatch.envs.{env_name}.scripts] {name}",
                        )
                    )
        return _sorted_unique(found)

    def tox(self) -> list[_Found]:
        if "tox.ini" not in self.all_paths:
            return []
        return [_Found("test", "tox", "tox.ini", "tox configuration")]

    def nox(self) -> list[_Found]:
        if "noxfile.py" not in self.all_paths:
            return []
        sessions = _NOX_SESSION.findall(self._text("noxfile.py"))
        return _sorted_unique(
            [_Found(purpose_of(s), f"nox -s {s}", "noxfile.py", f"session {s}") for s in sessions]
        )

    def workflows(self) -> list[_Found]:
        found: list[_Found] = []
        workflow_paths = sorted(
            p
            for p in self.all_paths
            if p.startswith(".github/workflows/") and p.endswith((".yml", ".yaml"))
        )
        for path in workflow_paths:
            data = self._parse(path, yaml.safe_load)
            jobs = data.get("jobs") if isinstance(data, dict) else None
            if not isinstance(jobs, dict):
                continue
            for job_name, job in jobs.items():
                steps = job.get("steps") if isinstance(job, dict) else None
                for step in steps if isinstance(steps, list) else []:
                    run = step.get("run") if isinstance(step, dict) else None
                    if not isinstance(run, str):
                        continue
                    for line in (ln.strip() for ln in run.splitlines()):
                        purpose = _ci_purpose(line)
                        if purpose is not None:
                            found.append(_Found(purpose, line, path, f"job {job_name}"))
        unique: dict[tuple[str, str], _Found] = {}
        for f in found:
            unique.setdefault((f.purpose, f.command), f)
        return list(unique.values())

    def _package_manager(self) -> str:
        for lockfile, manager in (
            ("pnpm-lock.yaml", "pnpm"),
            ("yarn.lock", "yarn"),
            ("bun.lockb", "bun"),
            ("bun.lock", "bun"),
        ):
            if lockfile in self.all_paths:
                return manager
        return "npm"

    def _text(self, path: str) -> str:
        return self.snapshot.read_bytes(path).decode("utf-8", "replace")

    def _parse(self, path: str, loader: Any) -> Any:
        if path not in self.all_paths:
            return None
        try:
            return loader(self._text(path))
        except (ValueError, yaml.YAMLError) as exc:
            # Manifests are reported once, by project detection; only report others.
            if path not in ("package.json", "pyproject.toml"):
                self.warnings.append(f"{path}: could not be parsed ({exc})")
            return None


def _script_command(manager: str, name: str) -> str:
    if name in ("test", "start") and manager != "bun":
        return f"{manager} {name}"
    return f"{manager} run {name}"


def _first_recipe_line(text: str, offset: int) -> str | None:
    for line in text[offset:].splitlines()[1:]:
        if not line.strip():
            continue
        if line.startswith(("\t", "    ")):
            text = line.strip().lstrip("@")
            return f"{text[:-1].rstrip()} …" if text.endswith("\\") else text
        return None
    return None


def _ci_purpose(line: str) -> str | None:
    if not line or line.startswith(("#", "echo ", "cd ")) or "${{" in line:
        return None
    if _CI_INSTALL.search(line):
        return "install"
    if _CI_TEST.search(line):
        return "test"
    return None


def _sorted_unique(found: list[_Found]) -> list[_Found]:
    unique = {f.command: f for f in found}
    return sorted(unique.values(), key=lambda f: f.command)


def _get(table: dict[str, Any], *keys: str) -> Any:
    value: Any = table
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value
