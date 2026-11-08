"""Tour every repository in the robustness corpus and fail on any crash.

Usage:
    uv run python benchmarks/corpus.py --dir <clone directory> [--only NAME ...]

A crash is any exit code other than 0 (Repotour reports problems as warnings
and still exits 0 without --strict) or a run that exceeds the time limit.
Results go to stdout and, in CI, to the job summary.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import yaml

CORPUS = Path(__file__).resolve().parent.parent / "tests" / "corpus.yml"
TIME_LIMIT_SECONDS = 600
_WARNINGS = re.compile(r"\((\d+) warnings?\)")


@dataclass(frozen=True)
class Repository:
    name: str
    commit: str
    shallow: bool = False


@dataclass(frozen=True)
class Outcome:
    repository: Repository
    seconds: float
    exit_code: int
    warnings: int | None
    detail: str

    @property
    def crashed(self) -> bool:
        return self.exit_code != 0


def load_corpus() -> list[Repository]:
    data = yaml.safe_load(CORPUS.read_text(encoding="utf-8"))
    return [Repository(**entry) for entry in data["repositories"]]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dir", type=Path, required=True, help="where repositories are cloned")
    parser.add_argument("--only", nargs="*", default=None, help="limit to these repositories")
    args = parser.parse_args()

    repositories = [r for r in load_corpus() if not args.only or r.name in args.only]
    outcomes = [_tour(r, args.dir) for r in repositories]
    table = _table(outcomes)
    print(table)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with Path(summary).open("a", encoding="utf-8") as handle:
            handle.write(table + "\n")
    crashes = [o for o in outcomes if o.crashed]
    for outcome in crashes:
        print(f"\n--- {outcome.repository.name} ---\n{outcome.detail}", file=sys.stderr)
    return 1 if crashes else 0


def _tour(repository: Repository, base: Path) -> Outcome:
    checkout = _checkout(repository, base)
    out = base / "tours" / f"{repository.name.replace('/', '__')}.md"
    command = [sys.executable, "-m", "repotour", str(checkout), "--out", str(out), "--force",
               "--no-cache"]  # fmt: skip
    started = time.perf_counter()
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=TIME_LIMIT_SECONDS, check=False
        )
    except subprocess.TimeoutExpired:
        return Outcome(repository, TIME_LIMIT_SECONDS, -1, None, "timed out")
    seconds = time.perf_counter() - started
    match = _WARNINGS.search(result.stdout)
    detail = (result.stderr or result.stdout)[-4000:]
    print(f"{repository.name}: exit {result.returncode} in {seconds:.1f}s", file=sys.stderr)
    return Outcome(
        repository, seconds, result.returncode, int(match.group(1)) if match else None, detail
    )


def _checkout(repository: Repository, base: Path) -> Path:
    target = base / repository.name.replace("/", "__")
    url = f"https://github.com/{repository.name}.git"
    if not target.exists():
        base.mkdir(parents=True, exist_ok=True)
        if repository.shallow:
            subprocess.run(["git", "init", "--quiet", str(target)], check=True)
            subprocess.run(["git", "-C", str(target), "fetch", "--quiet", "--depth=1", url,
                            repository.commit], check=True)  # fmt: skip
        else:
            subprocess.run(
                ["git", "clone", "--quiet", "--no-checkout", url, str(target)], check=True
            )
    ref = "FETCH_HEAD" if repository.shallow else repository.commit
    subprocess.run(["git", "-C", str(target), "checkout", "--quiet", "--detach", ref], check=True)
    return target


def _table(outcomes: list[Outcome]) -> str:
    lines = ["| Repository | Commit | Result | Time | Warnings |", "|---|---|---|---:|---:|"]
    for o in outcomes:
        result = "ok" if not o.crashed else f"CRASH (exit {o.exit_code})"
        warnings = "-" if o.warnings is None else str(o.warnings)
        shallow = " (shallow)" if o.repository.shallow else ""
        lines.append(
            f"| {o.repository.name}{shallow} | `{o.repository.commit[:12]}` | {result} "
            f"| {o.seconds:.1f}s | {warnings} |"
        )
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())
