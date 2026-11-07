"""Mermaid rendering of the dependency graph. Pure: no analysis here."""

from __future__ import annotations

from repotour.model.tour import DependencyGraphSection, GraphNode


def render_mermaid(graph: DependencyGraphSection) -> str:
    ids = {node.id: f"n{i}" for i, node in enumerate(graph.nodes)}
    lines = ["flowchart LR"]
    lines.extend(f'    {ids[n.id]}["{_label(n, graph.depth)}"]' for n in graph.nodes)
    lines.extend(f"    {ids[e.source]} --> {ids[e.target]}" for e in graph.edges)
    return "\n".join(lines)


def _label(node: GraphNode, depth: int) -> str:
    text = node.id
    if depth:
        name = text if text.startswith("(") else f"{text}/"
        text = f"{name} ({node.modules} module{'' if node.modules == 1 else 's'})"
    return text.replace('"', "#quot;")
