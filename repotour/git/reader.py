"""The only module that runs git. It returns typed records, never raw output."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from repotour.errors import RepositoryError
from repotour.model.history import CommitRecord, FileChange

GIT_EXECUTABLE = "git"
MIN_GIT_VERSION = (2, 30, 0)

GitVersion = tuple[int, int, int]


class GitError(RepositoryError):
    """git failed unexpectedly."""


@dataclass(frozen=True)
class RepoInfo:
    root: Path
    head_commit: str
    is_shallow: bool
    has_uncommitted_changes: bool


def parse_git_version(raw: str) -> GitVersion:
    match = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", raw)
    if match is None:
        raise GitError(f"could not read the git version from {raw.strip()!r}")
    major, minor, patch = match.groups()
    return int(major), int(minor), int(patch or 0)


def git_version() -> GitVersion:
    return parse_git_version(_git(Path.cwd(), "--version"))


def ensure_supported_git() -> None:
    found = git_version()
    if found < MIN_GIT_VERSION:
        raise RepositoryError(
            f"git {_fmt(found)} is too old; Repotour needs git {_fmt(MIN_GIT_VERSION)} or newer"
        )


def repo_info(start: Path) -> RepoInfo:
    """Resolve any directory inside a repository to facts about its root and HEAD."""
    if not start.is_dir():
        raise RepositoryError(f"{start} is not a directory")
    ensure_supported_git()
    try:
        root = Path(_git(start, "rev-parse", "--show-toplevel").strip())
    except GitError:
        raise RepositoryError(f"{start} is not inside a git repository") from None
    try:
        head = _git(root, "rev-parse", "--verify", "--quiet", "HEAD^{commit}").strip()
    except GitError:
        raise RepositoryError("repository has no commits") from None
    shallow = _git(root, "rev-parse", "--is-shallow-repository").strip() == "true"
    dirty = bool(_git(root, "status", "--porcelain", "--untracked-files=no").strip())
    return RepoInfo(root=root, head_commit=head, is_shallow=shallow, has_uncommitted_changes=dirty)


def git_common_dir(root: Path) -> Path:
    """The `.git` directory shared by all worktrees of the repository at `root`."""
    raw = Path(_git(root, "rev-parse", "--git-common-dir").strip())
    return raw if raw.is_absolute() else (root / raw).resolve()


def commit_timestamp(root: Path, commit: str) -> int:
    """Committer date of `commit` as a Unix timestamp."""
    return int(_git(root, "show", "-s", "--format=%ct", commit).strip())


_RECORD = b"\x1e"
_FIELD = b"\x1f"
_LOG_FORMAT = "--format=%x1e%H%x1f%aN%x1f%aE%x1f%ct"


def read_history(root: Path, head: str) -> tuple[CommitRecord, ...]:
    """History: commits reachable from `head`, merges excluded, in git's order.

    Authors are normalized through `.mailmap`. Renames are detected repo-wide in
    the same pass (`-M`) and reported as `old_path`; `follow_renames()` links them.
    """
    return _log(root, head)


def read_history_range(root: Path, base: str, head: str) -> tuple[CommitRecord, ...]:
    """Commits reachable from `head` but not from `base`, merges excluded."""
    return _log(root, f"{base}..{head}")


def is_ancestor(root: Path, ancestor: str, descendant: str) -> bool:
    """Whether `ancestor` is reachable from `descendant`. Unknown commits are not."""
    try:
        _git(root, "merge-base", "--is-ancestor", ancestor, descendant)
    except GitError:
        return False
    return True


def _log(root: Path, revisions: str) -> tuple[CommitRecord, ...]:
    raw = _git_bytes(
        root,
        "log",
        "--no-merges",
        "--use-mailmap",
        "-M",
        "--numstat",
        "-z",
        _LOG_FORMAT,
        revisions,
    )
    return tuple(_parse_commit(c) for c in raw.split(_RECORD) if c.strip(b"\0\n"))


def _parse_commit(chunk: bytes) -> CommitRecord:
    header, _, body = chunk.partition(b"\0")
    sha, name, email, timestamp = (f.decode("utf-8", "replace") for f in header.split(_FIELD))
    # With -z, numstat writes "added\tremoved\tpath\0", or for a rename
    # "added\tremoved\t\0old\0new\0" (never the brace form).
    tokens = iter(body.lstrip(b"\n").split(b"\0"))
    files = []
    for entry in tokens:
        if not entry:
            continue
        added, removed, path = entry.split(b"\t", 2)
        old_path = None
        if not path:
            old_path, path = next(tokens), next(tokens)
        files.append(
            FileChange(
                path=_decode(path),
                added=None if added == b"-" else int(added),
                removed=None if removed == b"-" else int(removed),
                old_path=None if old_path is None else _decode(old_path),
            )
        )
    return CommitRecord(
        sha=sha,
        author_name=name,
        author_email=email,
        timestamp=int(timestamp),
        files=tuple(files),
    )


@dataclass(frozen=True)
class TreeEntry:
    """A regular file (not a symlink or submodule) in a commit's tree."""

    path: str
    oid: str


@dataclass(frozen=True)
class TreeListing:
    files: tuple[TreeEntry, ...]
    submodules: tuple[str, ...]


_REGULAR_FILE_MODES = (b"100644", b"100755")
LINGUIST_ATTRIBUTES = ("linguist-generated", "linguist-vendored")


def list_tree(root: Path, commit: str) -> TreeListing:
    """Regular files and submodule paths in `commit`, each sorted by path.

    Symlinks are skipped; submodules are listed but never entered.
    """
    raw = _git_bytes(root, "ls-tree", "-r", "-z", "--full-tree", commit)
    files: list[TreeEntry] = []
    submodules: list[str] = []
    for record in raw.split(b"\0"):
        if not record:
            continue
        meta, _, raw_path = record.partition(b"\t")
        mode, kind, oid = meta.split(b" ")
        path = raw_path.decode("utf-8", "replace")
        if kind == b"blob" and mode in _REGULAR_FILE_MODES:
            files.append(TreeEntry(path=path, oid=oid.decode()))
        elif kind == b"commit":
            submodules.append(path)
    return TreeListing(
        files=tuple(sorted(files, key=lambda e: e.path)), submodules=tuple(sorted(submodules))
    )


def check_attributes(root: Path, paths: list[str]) -> dict[str, dict[str, str]]:
    """Linguist attributes per path, as `git check-attr` reports them.

    Values are `set`, `unset`, `unspecified`, or the assigned value. Attributes
    come from the committed `.gitattributes` files (via the index), not the
    working tree.
    """
    if not paths:
        return {}
    raw = _git_bytes(
        root,
        "check-attr",
        "--cached",
        "-z",
        "--stdin",
        *LINGUIST_ATTRIBUTES,
        stdin=b"\0".join(p.encode("utf-8") for p in paths) + b"\0",
    )
    fields = raw.split(b"\0")
    attrs: dict[str, dict[str, str]] = {p: {} for p in paths}
    for i in range(0, len(fields) - 2, 3):
        path, attr, value = (f.decode("utf-8", "replace") for f in fields[i : i + 3])
        attrs.setdefault(path, {})[attr] = value
    return attrs


def read_blobs(root: Path, oids: list[str]) -> dict[str, bytes]:
    """Contents of the given blobs, read in one `git cat-file --batch` call."""
    unique = sorted(set(oids))
    if not unique:
        return {}
    raw = _git_bytes(root, "cat-file", "--batch", stdin="".join(f"{o}\n" for o in unique).encode())
    blobs: dict[str, bytes] = {}
    pos = 0
    while pos < len(raw):
        header_end = raw.index(b"\n", pos)
        oid, kind, size = raw[pos:header_end].split(b" ")
        if kind != b"blob":
            raise GitError(f"expected a blob for {oid.decode()}, got {kind.decode()}")
        start = header_end + 1
        end = start + int(size)
        blobs[oid.decode()] = raw[start:end]
        pos = end + 1
    return blobs


def read_files(root: Path, commit: str, paths: list[str]) -> dict[str, bytes]:
    """Contents of files at `commit`, read in one `git cat-file --batch` call.

    Paths that are missing at that commit, or are not blobs, are left out.
    """
    if not paths:
        return {}
    stdin = "".join(f"{commit}:{path}\n" for path in paths).encode("utf-8")
    raw = _git_bytes(root, "cat-file", "--batch", stdin=stdin)
    files: dict[str, bytes] = {}
    pos = 0
    for path in paths:
        header_end = raw.index(b"\n", pos)
        header = raw[pos:header_end].split(b" ")
        pos = header_end + 1
        if header[-1] == b"missing" or len(header) != 3:
            continue
        size = int(header[2])
        if header[1] == b"blob":
            files[path] = raw[pos : pos + size]
        pos += size + 1
    return files


def _decode(raw: bytes) -> str:
    return raw.decode("utf-8", "replace")


def _fmt(version: GitVersion) -> str:
    return ".".join(str(part) for part in version)


def _git(cwd: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            [GIT_EXECUTABLE, *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
    except FileNotFoundError:
        raise RepositoryError("git is not installed or not on PATH") from None
    except subprocess.CalledProcessError as exc:
        raise GitError(exc.stderr.strip() or f"git {' '.join(args)} failed") from exc
    return result.stdout


def _git_bytes(cwd: Path, *args: str, stdin: bytes | None = None) -> bytes:
    try:
        result = subprocess.run(
            [GIT_EXECUTABLE, *args], cwd=cwd, input=stdin, capture_output=True, check=True
        )
    except FileNotFoundError:
        raise RepositoryError("git is not installed or not on PATH") from None
    except subprocess.CalledProcessError as exc:
        message = exc.stderr.decode("utf-8", "replace").strip()
        raise GitError(message or f"git {' '.join(args)} failed") from exc
    return result.stdout
