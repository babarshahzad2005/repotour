"""Generate the published sample tours from real repositories at pinned commits.

Usage:
    uv run python benchmarks/samples.py --dir <clone directory> --out <tour directory>

Each repository is cloned with full history (history-based sections need it),
checked out at its pinned release commit, and toured with an empty cache.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Sample:
    slug: str  # output file name
    name: str
    url: str
    commit: str


SAMPLES = (
    Sample(
        slug="flask",
        name="pallets/flask 3.1.3",
        url="https://github.com/pallets/flask.git",
        commit="22d924701a6ae2e4cd01e9a15bbaf3946094af65",
    ),
    Sample(
        slug="express",
        name="expressjs/express v5.3.0",
        url="https://github.com/expressjs/express.git",
        commit="cf6722bf89a86905281d9160b6482e08166b5ef0",
    ),
    Sample(
        slug="fzf",
        name="junegunn/fzf v0.75.0",
        url="https://github.com/junegunn/fzf.git",
        commit="c7bf2b8eea25952dd257a466c0afa72faae206fb",
    ),
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dir", type=Path, required=True, help="where repositories are cloned")
    parser.add_argument("--out", type=Path, required=True, help="where tours are written")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    for sample in SAMPLES:
        checkout = _checkout(sample, args.dir)
        target = args.out / f"{sample.slug}.md"
        subprocess.run(
            [sys.executable, "-m", "repotour", str(checkout), "--out", str(target), "--force",
             "--no-cache"],
            check=True,
        )  # fmt: skip
        print(f"{sample.name}: {target}", file=sys.stderr)
    return 0


def _checkout(sample: Sample, base: Path) -> Path:
    target = base / sample.slug
    if not target.exists():
        base.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "clone", "--quiet", "--no-checkout", sample.url, str(target)], check=True
        )
    subprocess.run(
        ["git", "checkout", "--quiet", "--detach", sample.commit], cwd=target, check=True
    )
    return target


if __name__ == "__main__":
    sys.exit(main())
