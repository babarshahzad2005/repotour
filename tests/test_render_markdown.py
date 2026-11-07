from __future__ import annotations

from repotour.model.tour import Meta, Tour
from repotour.render.markdown import render_markdown

TOUR = Tour(
    meta=Meta(repo_name="demo", head_commit="a" * 40, tool_version="1.2.3", config_hash="c" * 64)
)


def test_rendering_is_pure() -> None:
    assert render_markdown(TOUR) == render_markdown(TOUR)


def test_rendered_markdown_uses_lf_and_ends_with_newline() -> None:
    text = render_markdown(TOUR)

    assert "\r" not in text
    assert text.endswith("\n")
    assert not text.endswith("\n\n")


def test_meta_appears_in_markdown() -> None:
    text = render_markdown(TOUR)

    assert "demo" in text
    assert "a" * 40 in text
    assert "1.2.3" in text


def test_unavailable_overview_points_to_warnings() -> None:
    tour = Tour(
        meta=TOUR.meta,
        unavailable=("overview",),
        warnings=("overview: section unavailable (RuntimeError: boom)",),
    )

    text = render_markdown(tour)

    assert "_Unavailable: see Warnings._" in text
    assert "- overview: section unavailable (RuntimeError: boom)" in text
