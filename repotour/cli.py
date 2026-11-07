"""Command-line entry point. Parses arguments, runs the pipeline, writes output.

This module contains no analysis logic.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from repotour.config import CliOverrides
from repotour.errors import RepotourError
from repotour.output import write_tour
from repotour.pipeline import build_tour
from repotour.render.markdown import render_markdown

EXIT_STRICT_WARNINGS = 3

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
    since: Annotated[
        str | None,
        typer.Option(
            "--since",
            help="Hotspot window as <n><d|w|m|y>, e.g. 6m. Overrides the config file.",
        ),
    ] = None,
    force: Annotated[
        bool,
        typer.Option("--force", help="Overwrite an output file that Repotour did not generate."),
    ] = False,
    strict: Annotated[
        bool,
        typer.Option("--strict", help="Exit with code 3 if any warnings were produced."),
    ] = False,
    no_cache: Annotated[
        bool,
        typer.Option("--no-cache", help="Neither read nor write the analysis cache."),
    ] = False,
) -> None:
    try:
        result = build_tour(path, CliOverrides(since=since), use_cache=not no_cache)
        target = out if out is not None else result.root / "TOUR.md"
        write_tour(target, render_markdown(result.tour), force=force)
    except RepotourError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(exc.exit_code) from None

    warnings = len(result.tour.warnings)
    typer.echo(f"Wrote {target} ({warnings} warning{'' if warnings == 1 else 's'})")
    if result.has_uncommitted_changes:
        short = result.tour.meta.head_commit[:7]
        typer.echo(f"Note: uncommitted changes are ignored; the tour describes HEAD ({short}).")
    if strict and warnings:
        typer.echo("error: warnings were produced and --strict is set", err=True)
        raise typer.Exit(EXIT_STRICT_WARNINGS)
