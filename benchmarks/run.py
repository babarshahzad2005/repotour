"""Benchmark Repotour on real repositories pinned to exact commits.

Method: clone each repository with full history, check out the pinned commit,
run Repotour once as a warm-up (so the OS file cache is warm), then time three
runs with an empty Repotour cache (`--no-cache`) and report the median.

Usage:
    uv run python benchmarks/run.py --dir <clone directory> [--runs 3]

Exits non-zero if any repository's median misses its target. When
GITHUB_STEP_SUMMARY is set (in CI), a Markdown table is appended to it.
"""

from __future__ import annotations

import argparse
import os
import statistics
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Benchmark:
    name: str
    url: str
    commit: str
    target_seconds: float


BENCHMARKS = (
    Benchmark(
        name="pallets/flask 3.1.3",
        url="https://github.com/pallets/flask.git",
        commit="22d924701a6ae2e4cd01e9a15bbaf3946094af65",
        target_seconds=10.0,
    ),
    Benchmark(
        name="junegunn/fzf v0.75.0",
        url="https://github.com/junegunn/fzf.git",
        commit="c7bf2b8eea25952dd257a466c0afa72faae206fb",
        target_seconds=10.0,
    ),
)


@dataclass(frozen=True)
class Result:
    benchmark: Benchmark
    timings: tuple[float, ...]

    @property
    def median(self) -> float:
        return statistics.median(self.timings)

    @property
    def passed(self) -> bool:
        return self.median < self.benchmark.target_seconds


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dir", type=Path, required=True, help="where repositories are cloned")
    parser.add_argument("--runs", type=int, default=3, help="timed runs per repository")
    args = parser.parse_args()

    results = [_run(b, args.dir, args.runs) for b in BENCHMARKS]
    table = _table(results)
    print(table)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with Path(summary).open("a", encoding="utf-8") as handle:
            handle.write(table + "\n")
    return 0 if all(r.passed for r in results) else 1


def _run(benchmark: Benchmark, base: Path, runs: int) -> Result:
    checkout = _checkout(benchmark, base)
    out = base / "tours" / f"{checkout.name}.md"
    command = [
        sys.executable, "-m", "repotour", str(checkout), "--out", str(out), "--force", "--no-cache",
    ]  # fmt: skip
    subprocess.run(command, check=True, capture_output=True)  # warm-up
    timings = []
    for _ in range(runs):
        started = time.perf_counter()
        subprocess.run(command, check=True, capture_output=True)
        timings.append(time.perf_counter() - started)
    print(f"{benchmark.name}: {', '.join(f'{t:.2f}s' for t in timings)}", file=sys.stderr)
    return Result(benchmark=benchmark, timings=tuple(timings))


def _checkout(benchmark: Benchmark, base: Path) -> Path:
    target = base / benchmark.url.rstrip("/").removesuffix(".git").rsplit("/", 1)[-1]
    if not target.exists():
        base.mkdir(parents=True, exist_ok=True)
        _git(base, "clone", "--quiet", "--no-checkout", benchmark.url, str(target))
    _git(target, "checkout", "--quiet", "--detach", benchmark.commit)
    return target


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True)


def _table(results: list[Result]) -> str:
    lines = [
        "| Repository | Commit | Median | Runs | Target | Result |",
        "|---|---|---:|---|---:|---|",
    ]
    for r in results:
        runs = ", ".join(f"{t:.2f}s" for t in r.timings)
        verdict = "pass" if r.passed else "FAIL"
        lines.append(
            f"| {r.benchmark.name} | `{r.benchmark.commit[:12]}` | {r.median:.2f}s | {runs} "
            f"| < {r.benchmark.target_seconds:.0f}s | {verdict} |"
        )
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())
