"""Decides what each tracked file is: source, test, generated, vendored,
config, docs, or other, and why.

Rules, first match wins:
1. Config `exclude` globs mark files as vendored.
2. `.gitattributes`: `linguist-generated` / `linguist-vendored` set or true
   decides; explicitly unset or false switches off the matching heuristics.
3. Well-known vendored paths (`node_modules/`, `vendor/`, `third_party/`, ...).
4. Well-known generated paths and names (`dist/`, `*.min.js`, lockfiles, ...).
5. Generated-file headers (`Code generated ... DO NOT EDIT`, `@generated`).
6. Git LFS pointers and binary content are `other`.
7. Test directories, test file names, and config `test_patterns`.
8. Otherwise by extension: source, docs, config, or other.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePosixPath

from repotour.config import Config
from repotour.model.snapshot import Category
from repotour.scan.filetypes import category_of, language_of
from repotour.scan.globs import matches

MAX_ANALYZED_BYTES = 1024 * 1024
BINARY_SNIFF_BYTES = 8000
HEADER_SNIFF_BYTES = 1024
LFS_POINTER_PREFIX = b"version https://git-lfs.github.com/spec/v1"

VENDORED_DIRS = ("node_modules/", "vendor/", "third_party/", "bower_components/", ".yarn/")
GENERATED_DIRS = ("dist/",)
GENERATED_NAMES = ("*.min.js", "*.min.css", "*.map", "*_pb2.py", "*_pb2_grpc.py", "*.pb.go")
LOCKFILES = frozenset(
    {
        "package-lock.json",
        "npm-shrinkwrap.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "bun.lockb",
        "poetry.lock",
        "uv.lock",
        "Pipfile.lock",
        "pdm.lock",
        "Cargo.lock",
        "go.sum",
        "Gemfile.lock",
        "composer.lock",
        "mix.lock",
        "pubspec.lock",
        "packages.lock.json",
    }
)
TEST_DIRS = frozenset({"test", "tests", "__tests__", "spec"})
TEST_NAMES = (
    "test_*.py",
    "*_test.py",
    "*_test.go",
    *(f"*.{kind}.{ext}" for kind in ("test", "spec") for ext in ("js", "ts", "jsx", "tsx")),
)
ASSET_EXTENSIONS = frozenset(
    {
        ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".webp", ".avif", ".tiff",
        ".pdf", ".woff", ".woff2", ".ttf", ".otf", ".eot",
        ".zip", ".gz", ".tgz", ".bz2", ".xz", ".7z", ".jar",
        ".mp3", ".mp4", ".wav", ".ogg", ".webm", ".mov",
    }
)  # fmt: skip
# The marker must sit in a comment at the start of a line, as tools write it.
# Prose that merely mentions the phrase (a docstring, a README) does not count.
_COMMENT_START = rb"^[ \t]*(?://|#|/\*+|\*|--|;|<!--)[ \t]*"
_GENERATED_HEADER = re.compile(
    _COMMENT_START + rb"(?:Code generated .*DO NOT EDIT|.*@generated\b)", re.MULTILINE
)

# Values `git check-attr` reports for an attribute.
ATTR_SET = ("set", "true")
ATTR_OFF = ("unset", "false")


@dataclass(frozen=True)
class Classification:
    category: Category
    language: str | None
    reason: str | None = None
    warning: str | None = None


def classify(path: str, data: bytes, attrs: dict[str, str], config: Config) -> Classification:
    language = language_of(path)

    for pattern in config.exclude:
        if matches(pattern, path):
            return Classification("vendored", language, f"config exclude: {pattern}")

    generated_attr = attrs.get("linguist-generated", "unspecified")
    vendored_attr = attrs.get("linguist-vendored", "unspecified")
    if vendored_attr in ATTR_SET:
        return Classification("vendored", language, "linguist-vendored in .gitattributes")
    if generated_attr in ATTR_SET:
        return Classification("generated", language, "linguist-generated in .gitattributes")

    if vendored_attr not in ATTR_OFF:
        for directory in VENDORED_DIRS:
            if matches(directory, path):
                return Classification("vendored", language, f"vendored path {directory}")

    if generated_attr not in ATTR_OFF:
        found = _generated_reason(path, data)
        if found is not None:
            return Classification("generated", language, found)

    if data.startswith(LFS_POINTER_PREFIX):
        return Classification("other", None, "Git LFS pointer")
    if b"\0" in data[:BINARY_SNIFF_BYTES]:
        expected = PurePosixPath(path).suffix.lower() in ASSET_EXTENSIONS
        warning = None if expected else f"Skipped binary file: {path}"
        return Classification("other", None, "binary", warning)

    category: Category = category_of(path, language)
    reason = _test_reason(path, config)
    if reason is not None:
        category = "test"
    if len(data) > MAX_ANALYZED_BYTES:
        return Classification(
            category, None, "larger than 1 MB", f"Skipped file larger than 1 MB: {path}"
        )
    return Classification(category, language, reason)


def _generated_reason(path: str, data: bytes) -> str | None:
    name = PurePosixPath(path).name
    if name in LOCKFILES:
        return "lockfile"
    for directory in GENERATED_DIRS:
        if matches(directory, path):
            return f"build output path {directory}"
    for pattern in GENERATED_NAMES:
        if matches(pattern, path):
            return f"generated file name {pattern}"
    header = _GENERATED_HEADER.search(data[:HEADER_SNIFF_BYTES])
    if header is not None:
        marker = "DO NOT EDIT" if b"DO NOT EDIT" in header.group() else "@generated"
        return f"generated-file header ({marker})"
    return None


def _test_reason(path: str, config: Config) -> str | None:
    for pattern in config.test_patterns:
        if matches(pattern, path):
            return f"config test_patterns: {pattern}"
    parts = PurePosixPath(path).parts
    if any(part in TEST_DIRS for part in parts[:-1]):
        return "test directory"
    for pattern in TEST_NAMES:
        if matches(pattern, path):
            return f"test file name {pattern}"
    return None
