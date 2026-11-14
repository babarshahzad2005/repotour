"""HTML renderer: the Markdown tour as one self-contained, offline page.

The page is built from the Markdown tour, so both formats always say the same
thing. Raw HTML in the Markdown (which could only come from repository text)
is escaped, never passed through. The dependency graph is drawn in the browser
by a pinned Mermaid bundle embedded inline; nothing loads from the network.
"""

from __future__ import annotations

from collections.abc import Sequence
from functools import cache
from importlib.resources import files
from typing import Any

from jinja2 import Environment, PackageLoader, StrictUndefined
from markdown_it import MarkdownIt
from markdown_it.common.utils import escapeHtml
from markdown_it.renderer import RendererHTML
from markdown_it.token import Token

from repotour.model.tour import Tour
from repotour.output import MARKER
from repotour.render.markdown import render_markdown

# @mermaid-js/tiny: the official Mermaid build without the heaviest diagram
# types; flowcharts, which the tour uses, are included.
MERMAID_VERSION = "12.3.0"
MERMAID_SHA256 = "c41f5236091b83f524c4940f97a16b2b14a76f21ff84aea4fd6b66421d8a2a9a"

_ENV = Environment(
    loader=PackageLoader("repotour.render", "templates"),
    autoescape=True,
    undefined=StrictUndefined,
    keep_trailing_newline=True,
    newline_sequence="\n",
)


def render_html(tour: Tour) -> str:
    markdown = render_markdown(tour).removeprefix(MARKER + "\n")
    body = _parser().render(markdown)
    page = _ENV.get_template("tour.html.j2").render(
        title=f"Codebase tour: {tour.meta.repo_name}",
        body=body,
        mermaid=mermaid_bundle(),
    )
    return f"{MARKER}\n{page}"


@cache
def mermaid_bundle() -> str:
    resource = files("repotour.render") / "vendor" / "mermaid.tiny.js"
    return resource.read_bytes().decode("utf-8")


@cache
def _parser() -> MarkdownIt:
    parser = MarkdownIt("commonmark", {"html": False}).enable("table")
    renderer = parser.renderer
    assert isinstance(renderer, RendererHTML)
    default_fence = renderer.rules["fence"]

    def fence(_renderer: Any, tokens: Sequence[Token], idx: int, options: Any, env: Any) -> str:
        token = tokens[idx]
        if token.info.strip() == "mermaid":
            # Mermaid reads the element's text, so escaped content is exactly right.
            return f'<pre class="mermaid">\n{escapeHtml(token.content)}</pre>\n'
        result: str = default_fence(tokens, idx, options, env)
        return result

    parser.add_render_rule("fence", fence)
    return parser
