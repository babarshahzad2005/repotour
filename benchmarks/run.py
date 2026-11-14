"""Benchmark Repotour on real repositories pinned to exact commits.

Method: clone each repository with full history, check out the pinned commit,
run Repotour once as a warm-up (so the OS file cache is warm), then time three
runs with an empty Repotour cache (`--no-cache`) and report the median.

Incremental method: tour the previous release with an empty cache (untimed),
check out the pinned release, and time the re-run that reuses the cache, three
times, reporting the median. The incremental tour must be byte-identical to the
cold tour of the same commit.

Usage:
    uv run python benchmarks/run.py --dir <clone directory> [--runs 3]

Exits non-zero if any repository's median misses its target. When
GITHUB_STEP_SUMMARY is set (in CI), a Markdown table is appended to it.
"""

from __future__ import annotations

import argparse
import os
import shutil
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
    gate: bool = True  # False: a stretch target, reported but never failing
    previous: str | None = None  # an earlier release, for the incremental benchmark
    previous_name: str = ""


INCREMENTAL_TARGET_SECONDS = 5.0


BENCHMARKS = (
    Benchmark(
        name="pallets/flask 3.1.3",
        url="https://github.com/pallets/flask.git",
        commit="22d924701a6ae2e4cd01e9a15bbaf3946094af65",
        target_seconds=10.0,
        previous="2c1b30d0503cfb064f1cb252e6614a06915a362a",
        previous_name="3.1.2",
    ),
    Benchmark(
        name="junegunn/fzf v0.75.0",
        url="https://github.com/junegunn/fzf.git",
        commit="c7bf2b8eea25952dd257a466c0afa72faae206fb",
        target_seconds=10.0,
        previous="6765f464a60e39afc20775f54f7ba40896bf1b81",
        previous_name="v0.74.0",
    ),
    Benchmark(
        name="golang/go go1.27.3",
        url="https://github.com/golang/go.git",
        commit="2aae1000ea1d4b28923b96db28acf4e3b99d6aff",
        target_seconds=120.0,
        previous="8af21751f066eced273ca3ce49506b366847c623",
        previous_name="go1.27.0",
    ),
    Benchmark(
        name="kubernetes/kubernetes v1.37.2",
        url="https://github.com/kubernetes/kubernetes.git",
        commit="c50e5395f1ae2d4a2c05f28fdcc38c0916cc1a32",
        target_seconds=120.0,
        gate=False,
    ),
)


@dataclass(frozen=True)
class Result:
    benchmark: Benchmark
    timings: tuple[float, ...]
    incremental: tuple[float, ...] = ()
    incremental_identical: bool = True

    @property
    def median(self) -> float:
        return statistics.median(self.timings)

    @property
    def incremental_median(self) -> float | None:
        return statistics.median(self.incremental) if self.incremental else None

    @property
    def passed(self) -> bool:
        cold = not self.benchmark.gate or self.median < self.benchmark.target_seconds
        incremental = self.incremental_median
        return (
            cold
            and self.incremental_identical
            and (incremental is None or incremental < INCREMENTAL_TARGET_SECONDS)
        )


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
    if benchmark.previous is None:
        return Result(benchmark=benchmark, timings=tuple(timings))
    incremental, identical = _run_incremental(benchmark, checkout, out, runs)
    return Result(benchmark, tuple(timings), incremental, identical)


def _run_incremental(
    benchmark: Benchmark, checkout: Path, cold_tour: Path, runs: int
) -> tuple[tuple[float, ...], bool]:
    assert benchmark.previous is not None
    out = cold_tour.with_name(f"{cold_tour.stem}.incremental.md")
    command = [sys.executable, "-m", "repotour", str(checkout), "--out", str(out), "--force"]
    cache = checkout / ".git" / "repotour-cache"
    timings = []
    for _ in range(runs):
        shutil.rmtree(cache, ignore_errors=True)
        _git(checkout, "checkout", "--quiet", "--detach", benchmark.previous)
        subprocess.run(command, check=True, capture_output=True)  # fills the cache
        _git(checkout, "checkout", "--quiet", "--detach", benchmark.commit)
        started = time.perf_counter()
        subprocess.run(command, check=True, capture_output=True)
        timings.append(time.perf_counter() - started)
    identical = out.read_bytes() == cold_tour.read_bytes()
    print(
        f"{benchmark.name} incremental from {benchmark.previous_name}: "
        f"{', '.join(f'{t:.2f}s' for t in timings)}; identical to cold tour: {identical}",
        file=sys.stderr,
    )
    return tuple(timings), identical


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
        met = r.median < r.benchmark.target_seconds
        verdict = (
            ("pass" if met else "FAIL")
            if r.benchmark.gate
            else ("stretch: met" if met else "stretch: not met")
        )
        lines.append(
            f"| {r.benchmark.name} | `{r.benchmark.commit[:12]}` | {r.median:.2f}s | {runs} "
            f"| < {r.benchmark.target_seconds:.0f}s | {verdict} |"
        )
        incremental = r.incremental_median
        if incremental is not None:
            runs = ", ".join(f"{t:.2f}s" for t in r.incremental)
            met = incremental < INCREMENTAL_TARGET_SECONDS
            verdict = (
                ("pass" if met else "FAIL") if r.incremental_identical else "FAIL (tour differs)"
            )
            lines.append(
                f"| {r.benchmark.name}, incremental from {r.benchmark.previous_name} "
                f"| `{r.benchmark.previous[:12] if r.benchmark.previous else ''}` "
                f"| {incremental:.2f}s | {runs} | < {INCREMENTAL_TARGET_SECONDS:.0f}s | {verdict} |"
            )
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())
