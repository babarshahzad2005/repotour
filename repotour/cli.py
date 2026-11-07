"""Command-line entry point. Parses arguments, runs the pipeline, writes output.

This module contains no analysis logic.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from repotour.errors import RepotourError
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
    try:
        result = build_tour(path)
    except RepotourError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(exc.exit_code) from None

    target = out if out is not None else result.root / "TOUR.md"
    write_text(target, render_markdown(result.tour))

    warnings = len(result.tour.warnings)
    typer.echo(f"Wrote {target} ({warnings} warning{'' if warnings == 1 else 's'})")
    if result.has_uncommitted_changes:
        short = result.tour.meta.head_commit[:7]
        typer.echo(f"Note: uncommitted changes are ignored; the tour describes HEAD ({short}).")
