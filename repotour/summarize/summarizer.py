"""Writes a short summary of each key file with the configured provider.

Key files are the reading order, then the core modules, capped at
`summaries.max_files`. Summaries are cached by content hash, model, and prompt
version, so an unchanged file never costs another call. Nothing here can stop
the tour: every failure becomes a warning.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from repotour.cache.store import CacheStore
from repotour.config import Summaries
from repotour.git import reader
from repotour.model.tour import Evidence, FileSummary, Tour
from repotour.summarize.provider import (
    ChatClient,
    Endpoint,
    MissingKeyError,
    ProviderError,
    UnreachableError,
    resolve_endpoint,
)

PROMPT_VERSION = 1
MAX_INPUT_CHARS = 12_000  # about 3,000 tokens: enough to see what a file is for
MAX_SUMMARY_CHARS = 700

SYSTEM_PROMPT = (
    "You help developers who are new to a code repository. Given one source file, "
    "write a single plain-text paragraph of two to four sentences: what the file is "
    "responsible for, its most important functions or types, and how it fits into the "
    "codebase. Do not use Markdown, lists, headings, or code blocks. Do not guess "
    "beyond what the file shows."
)


@dataclass(frozen=True)
class SummaryOptions:
    """How to reach the provider; supplied by the CLI, faked in tests."""

    client: ChatClient
    environ: Mapping[str, str]
    notify: Callable[[str], None] = lambda _message: None


@dataclass(frozen=True)
class SummaryOutcome:
    summaries: tuple[FileSummary, ...] = ()
    warnings: tuple[str, ...] = field(default_factory=tuple)


def select_files(tour: Tour, limit: int) -> list[str]:
    """Reading-order files first, then core modules, without repeats."""
    paths: list[str] = []
    if tour.reading_order is not None:
        paths.extend(step.path for step in tour.reading_order.steps)
    if tour.dependency_graph is not None:
        paths.extend(module.path for module in tour.dependency_graph.core)
    return list(dict.fromkeys(paths))[:limit]


def summarize(
    tour: Tour,
    root: Path,
    settings: Summaries,
    options: SummaryOptions,
    store: CacheStore | None,
) -> SummaryOutcome:
    try:
        endpoint = resolve_endpoint(
            settings.provider, settings.base_url, settings.model, options.environ
        )
    except MissingKeyError as exc:
        return SummaryOutcome(warnings=(f"summaries skipped: {exc}",))
    paths = select_files(tour, settings.max_files)
    if not paths:
        return SummaryOutcome(warnings=("summaries: no key files to summarize",))

    contents = reader.read_files(root, tour.meta.head_commit, paths)
    hashes = {path: hashlib.sha256(data).hexdigest() for path, data in contents.items()}
    texts: dict[str, str] = {}
    to_send: list[str] = []
    for path in paths:
        if path not in contents:
            continue
        cached = store.get_summary(hashes[path], endpoint.model, PROMPT_VERSION) if store else None
        if cached is not None:
            texts[path] = cached
        else:
            to_send.append(path)

    warnings: list[str] = []
    if to_send:
        options.notify(
            f"Sending {len(to_send)} file{'' if len(to_send) == 1 else 's'} to "
            f"{endpoint.base_url} (model {endpoint.model}) for summaries: {', '.join(to_send)}"
        )
    for index, path in enumerate(to_send):
        try:
            text = _clean(
                options.client.complete(endpoint, SYSTEM_PROMPT, _prompt(path, contents[path]))
            )
        except UnreachableError as exc:
            left = len(to_send) - index
            warnings.append(
                f"summaries: {exc}; {left} file{'' if left == 1 else 's'} left without a summary"
            )
            break
        except ProviderError as exc:
            warnings.append(f"summaries: {path} was not summarized ({exc})")
            continue
        texts[path] = text
        if store is not None:
            store.put_summary(hashes[path], endpoint.model, PROMPT_VERSION, text)

    summaries = tuple(
        _summary(path, texts[path], hashes[path], endpoint) for path in paths if path in texts
    )
    return SummaryOutcome(summaries=summaries, warnings=tuple(warnings))


def _prompt(path: str, data: bytes) -> str:
    text = data.decode("utf-8", "replace")
    note = ""
    if len(text) > MAX_INPUT_CHARS:
        text = text[:MAX_INPUT_CHARS]
        note = "\n(The file is longer; only its beginning is shown.)"
    return f"File: {path}{note}\n\n{text}"


def _clean(text: str) -> str:
    """One plain paragraph of bounded length, whatever the model sent back."""
    flat = re.sub(r"\s+", " ", text).strip()
    if len(flat) <= MAX_SUMMARY_CHARS:
        return flat
    cut = flat[:MAX_SUMMARY_CHARS].rsplit(" ", 1)[0]
    return f"{cut}..."


def _summary(path: str, text: str, content_hash: str, endpoint: Endpoint) -> FileSummary:
    evidence = Evidence(
        kind="file", ref=path, detail=f"content {content_hash[:12]}, summarized by {endpoint.model}"
    )
    return FileSummary(path=path, text=text, model=endpoint.model, evidence=(evidence,))
