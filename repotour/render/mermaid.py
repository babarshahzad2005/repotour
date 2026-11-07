"""Mermaid rendering of the dependency graph. Pure: no analysis here."""

from __future__ import annotations

from repotour.model.tour import DependencyGraphSection


def render_mermaid(graph: DependencyGraphSection) -> str:
    ids = {node: f"n{i}" for i, node in enumerate(graph.nodes)}
    lines = ["flowchart LR"]
    lines.extend(f'    {ids[node]}["{_label(node)}"]' for node in graph.nodes)
    lines.extend(f"    {ids[e.source]} --> {ids[e.target]}" for e in graph.edges)
    return "\n".join(lines)


def _label(text: str) -> str:
    return text.replace('"', "#quot;")
