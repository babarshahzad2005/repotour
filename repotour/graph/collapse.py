"""Collapsing a large module graph into directories so it stays readable.

If the module graph has more nodes than the limit, modules are grouped by
their directory, starting at the deepest directory level and moving one
level coarser at a time until the graph fits. If even top-level directories
do not fit, the highest-ranked ones are kept and the rest are counted as
omitted.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import PurePosixPath

ROOT_GROUP = "(root)"


@dataclass
class Collapsed:
    depth: int  # 0: not collapsed (module level); otherwise directory depth
    nodes: list[str]
    members: dict[str, list[str]] = field(default_factory=dict)
    # (source group, target group) -> the module-level edges behind it
    edges: dict[tuple[str, str], list[tuple[str, str]]] = field(default_factory=dict)
    omitted: int = 0


def collapse(
    nodes: list[str],
    edges: list[tuple[str, str]],
    ranks: dict[str, float],
    max_nodes: int,
) -> Collapsed:
    if len(nodes) <= max_nodes:
        return _group(nodes, edges, lambda n: n, depth=0)
    deepest = max((len(PurePosixPath(n).parts) - 1 for n in nodes), default=0)
    for depth in range(max(deepest, 1), 0, -1):
        result = _group(nodes, edges, lambda n, d=depth: _directory(n, d), depth=depth)  # type: ignore[misc]
        if len(result.nodes) <= max_nodes:
            return result
    return _keep_top(result, ranks, max_nodes)


def _group(
    nodes: list[str], edges: list[tuple[str, str]], key: Callable[[str], str], depth: int
) -> Collapsed:
    members: dict[str, list[str]] = defaultdict(list)
    for node in sorted(nodes):
        members[key(node)].append(node)
    grouped: dict[tuple[str, str], list[tuple[str, str]]] = defaultdict(list)
    for source, target in sorted(edges):
        a, b = key(source), key(target)
        if a != b:
            grouped[(a, b)].append((source, target))
    return Collapsed(depth=depth, nodes=sorted(members), members=dict(members), edges=dict(grouped))


def _keep_top(result: Collapsed, ranks: dict[str, float], max_nodes: int) -> Collapsed:
    weight = {g: round(sum(ranks.get(m, 0.0) for m in ms), 6) for g, ms in result.members.items()}
    kept = sorted(sorted(weight, key=lambda g: (-weight[g], g))[:max_nodes])
    keep = set(kept)
    return Collapsed(
        depth=result.depth,
        nodes=kept,
        members={g: result.members[g] for g in kept},
        edges={k: v for k, v in result.edges.items() if k[0] in keep and k[1] in keep},
        omitted=len(result.nodes) - len(kept),
    )


def _directory(path: str, depth: int) -> str:
    parts = PurePosixPath(path).parts[:-1]
    return "/".join(parts[:depth]) if parts else ROOT_GROUP
