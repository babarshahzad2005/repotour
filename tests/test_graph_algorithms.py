from __future__ import annotations

from repotour.graph.collapse import collapse
from repotour.graph.pagerank import pagerank


def test_chain_ranks_the_most_depended_on_highest() -> None:
    ranks = pagerank(["a", "b", "c"], [("a", "b"), ("b", "c")])

    assert ranks["c"] > ranks["b"] > ranks["a"]


def test_hub_ranks_highest() -> None:
    nodes = ["hub", "x", "y", "z"]
    ranks = pagerank(nodes, [("x", "hub"), ("y", "hub"), ("z", "hub")])

    assert max(ranks, key=lambda n: ranks[n]) == "hub"


def test_ranks_are_rounded_deterministic_and_sum_to_one() -> None:
    nodes = [f"n{i}" for i in range(20)]
    edges = [(f"n{i}", f"n{(i * 7) % 20}") for i in range(20)]

    first = pagerank(nodes, edges)
    second = pagerank(list(reversed(nodes)), list(reversed(edges)))

    assert first == second
    assert all(round(r, 6) == r for r in first.values())
    assert abs(sum(first.values()) - 1) < 1e-4


def test_empty_graph() -> None:
    assert pagerank([], []) == {}


def test_small_graph_is_not_collapsed() -> None:
    result = collapse(["a.py", "b.py"], [("a.py", "b.py")], {"a.py": 0.4, "b.py": 0.6}, 60)

    assert result.depth == 0
    assert result.nodes == ["a.py", "b.py"]
    assert result.edges == {("a.py", "b.py"): [("a.py", "b.py")]}


def test_collapses_one_level_at_a_time() -> None:
    nodes = [f"pkg/d{d}/m{m}.py" for d in range(3) for m in range(2)]
    edges = [(f"pkg/d{d}/m0.py", f"pkg/d{(d + 1) % 3}/m1.py") for d in range(3)]
    ranks = dict.fromkeys(nodes, 1 / 6)

    result = collapse(nodes, edges, ranks, 3)

    assert result.depth == 2
    assert result.nodes == ["pkg/d0", "pkg/d1", "pkg/d2"]
    assert result.members["pkg/d0"] == ["pkg/d0/m0.py", "pkg/d0/m1.py"]
    assert sorted(result.edges) == [
        ("pkg/d0", "pkg/d1"),
        ("pkg/d1", "pkg/d2"),
        ("pkg/d2", "pkg/d0"),
    ]


def test_falls_back_to_shallower_levels() -> None:
    nodes = [f"pkg/d{d}/m.py" for d in range(5)] + ["top.py"]
    ranks = dict.fromkeys(nodes, 1 / 6)

    result = collapse(nodes, [], ranks, 3)

    assert result.depth == 1
    assert result.nodes == ["(root)", "pkg"]


def test_keeps_the_highest_ranked_when_even_the_top_level_is_too_big() -> None:
    nodes = [f"t{i}/m.py" for i in range(5)]
    ranks = {n: (i + 1) / 15 for i, n in enumerate(nodes)}

    result = collapse(nodes, [("t0/m.py", "t4/m.py")], ranks, 3)

    assert result.depth == 1
    assert result.nodes == ["t2", "t3", "t4"]
    assert result.omitted == 2
    assert result.edges == {}
