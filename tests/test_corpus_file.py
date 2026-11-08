from __future__ import annotations

import re

from benchmarks.corpus import load_corpus


def test_corpus_is_twenty_pinned_repositories() -> None:
    corpus = load_corpus()

    assert len(corpus) == 20
    assert len({r.name for r in corpus}) == 20
    assert all(re.fullmatch(r"[0-9a-f]{40}", r.commit) for r in corpus)
    assert any(r.shallow for r in corpus)
