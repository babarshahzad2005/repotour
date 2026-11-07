"""Command-line entry point. Parses arguments, runs the pipeline, writes output.

This module contains no analysis logic.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from repotour.output import write_text
from repotour.pipeline import build_tour
from repotour.render.markdown import render_markdown

app = typer.Typer(
    add_completion=False,
    help="Generate a codebase tour for new contributors.",
)


@app.command()
def main(
    path: Annotated[
        Path,
        typer.Argument(help="Any directory inside the git repository to tour."),
    ] = Path(),
    out: Annotated[
        Path | None,
        typer.Option("--out", help="Output path. Defaults to TOUR.md at the repository root."),
    ] = None,
) -> None:
    result = build_tour(path)
    target = out if out is not None else result.root / "TOUR.md"
    write_text(target, render_markdown(result.tour))
    warnings = len(result.tour.warnings)
    typer.echo(f"Wrote {target} ({warnings} warning{'' if warnings == 1 else 's'})")
