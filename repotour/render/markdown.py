"""Markdown renderer: a pure function of the Tour model."""

from __future__ import annotations

from jinja2 import Environment, PackageLoader, StrictUndefined

from repotour.model.tour import Tour

_ENV = Environment(
    loader=PackageLoader("repotour.render", "templates"),
    autoescape=False,
    undefined=StrictUndefined,
    keep_trailing_newline=True,
    trim_blocks=True,
    lstrip_blocks=True,
    newline_sequence="\n",
)


def render_markdown(tour: Tour) -> str:
    return _ENV.get_template("tour.md.j2").render(tour=tour)
