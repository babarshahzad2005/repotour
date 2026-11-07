"""PageRank over the import graph, written out so results are identical on
every platform: a fixed iteration count, nodes processed in sorted order,
and scores rounded to 6 decimals before anyone ranks by them.

Edges point from importer to imported, so the most depended-on modules
rank highest.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

DAMPING = 0.85
ITERATIONS = 50
DECIMALS = 6


def pagerank(nodes: Iterable[str], edges: Iterable[tuple[str, str]]) -> dict[str, float]:
    ordered = sorted(set(nodes))
    if not ordered:
        return {}
    count = len(ordered)
    targets: dict[str, list[str]] = defaultdict(list)
    for source, target in sorted(set(edges)):
        targets[source].append(target)
    rank = dict.fromkeys(ordered, 1.0 / count)
    for _ in range(ITERATIONS):
        dangling = sum(rank[n] for n in ordered if not targets[n])
        base = (1.0 - DAMPING) / count + DAMPING * dangling / count
        incoming = dict.fromkeys(ordered, 0.0)
        for source in ordered:
            outs = targets[source]
            if outs:
                share = rank[source] / len(outs)
                for target in outs:
                    incoming[target] += share
        rank = {n: base + DAMPING * incoming[n] for n in ordered}
    return {n: round(rank[n], DECIMALS) for n in ordered}
