"""Bulk commits: commits so broad they say nothing about who works on what.

A commit is bulk if it touches more files than `thresholds.bulk_commit_files`
or is listed in `.git-blame-ignore-revs` (as committed at HEAD) or in config
`ignore_revs`. Ignore lists may use abbreviated SHAs.
"""

from __future__ import annotations

from repotour.model.history import CommitRecord
from repotour.model.snapshot import RepoSnapshot

IGNORE_REVS_FILE = ".git-blame-ignore-revs"
MIN_ABBREVIATED_SHA = 7


def find_bulk(snapshot: RepoSnapshot, commits: tuple[CommitRecord, ...]) -> dict[str, str]:
    """Map each bulk commit's SHA to the reason it is bulk."""
    listed = _listed_revs(snapshot)
    limit = snapshot.config.thresholds.bulk_commit_files
    bulk: dict[str, str] = {}
    for commit in commits:
        reason = _listed_reason(commit.sha, listed)
        if reason is None and len(commit.files) > limit:
            reason = f"touches {len(commit.files)} files"
        if reason is not None:
            bulk[commit.sha] = reason
    return bulk


def _listed_revs(snapshot: RepoSnapshot) -> list[tuple[str, str]]:
    revs: list[tuple[str, str]] = []
    if IGNORE_REVS_FILE in snapshot.contents:
        text = snapshot.read_bytes(IGNORE_REVS_FILE).decode("utf-8", "replace")
        for line in text.splitlines():
            rev = line.split("#", 1)[0].strip().lower()
            if len(rev) >= MIN_ABBREVIATED_SHA:
                revs.append((rev, f"listed in {IGNORE_REVS_FILE}"))
    for rev in snapshot.config.ignore_revs:
        cleaned = rev.strip().lower()
        if len(cleaned) >= MIN_ABBREVIATED_SHA:
            revs.append((cleaned, "listed in config ignore_revs"))
    return revs


def _listed_reason(sha: str, listed: list[tuple[str, str]]) -> str | None:
    for rev, reason in listed:
        if sha.startswith(rev):
            return reason
    return None
