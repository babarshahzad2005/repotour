"""Basics a newcomer expects: README, tests, contributing guide, license, CI.

Each missing item is a claim whose evidence states what was looked for.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import PurePosixPath

from repotour.model.snapshot import RepoSnapshot
from repotour.model.tour import Evidence, MissingBasic

CI_FILES = frozenset(
    {
        ".gitlab-ci.yml",
        ".travis.yml",
        "azure-pipelines.yml",
        "bitbucket-pipelines.yml",
        "Jenkinsfile",
        ".circleci/config.yml",
        ".drone.yml",
        "appveyor.yml",
    }
)
CI_DIRS = (".github/workflows/", ".buildkite/", ".woodpecker/")


def find_missing(snapshot: RepoSnapshot) -> tuple[MissingBasic, ...]:
    paths = [f.path for f in snapshot.files]
    checks: list[tuple[str, Callable[[], bool], str, str]] = [
        ("README", lambda: any(_at_root(p) and _stem(p) == "readme" for p in paths),
         "README*", "a README at the repository root"),
        ("tests", lambda: any(f.category == "test" for f in snapshot.files),
         "tests", "any file classified as a test"),
        ("contributing guide", lambda: any(_is_contributing(p) for p in paths),
         "CONTRIBUTING*", "CONTRIBUTING* at the root, in docs/, or in .github/"),
        ("license", lambda: any(_at_root(p) and _is_license(p) for p in paths),
         "LICENSE*", "LICENSE*, LICENCE*, or COPYING* at the repository root"),
        ("CI configuration", lambda: any(_is_ci(p) for p in paths),
         ".github/workflows/", "GitHub Actions, GitLab CI, CircleCI, Jenkins, Azure, "
         "Travis, Bitbucket, Buildkite, Drone, or AppVeyor configuration"),
    ]  # fmt: skip
    return tuple(
        MissingBasic(
            item=item,
            evidence=(Evidence(kind="file", ref=ref, detail=f"looked for {looked_for}"),),
        )
        for item, present, ref, looked_for in checks
        if not present()
    )


def _at_root(path: str) -> bool:
    return "/" not in path


def _stem(path: str) -> str:
    return PurePosixPath(path).stem.lower()


def _is_contributing(path: str) -> bool:
    parent = str(PurePosixPath(path).parent)
    return parent in (".", "docs", ".github") and _stem(path) == "contributing"


def _is_license(path: str) -> bool:
    name = PurePosixPath(path).name.upper()
    return name.startswith(("LICENSE", "LICENCE", "COPYING"))


def _is_ci(path: str) -> bool:
    return path in CI_FILES or path.startswith(CI_DIRS)
