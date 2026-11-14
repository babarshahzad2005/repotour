"""Command-line entry point. Parses arguments, runs the pipeline, writes output.

This module contains no analysis logic.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from repotour.config import CliOverrides
from repotour.errors import RepotourError
from repotour.output import Output, has_marker, write_outputs
from repotour.pipeline import build_tour
from repotour.render.json import is_generated_json, render_json
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
    full_graph: Annotated[
        bool,
        typer.Option("--full-graph", help="Draw every module instead of collapsing large graphs."),
    ] = False,
    no_cache: Annotated[
        bool,
        typer.Option("--no-cache", help="Neither read nor write the analysis cache."),
    ] = False,
    json_out: Annotated[
        Path | None,
        typer.Option(
            "--json",
            help="Also write the tour model as JSON to this path (experimental format).",
        ),
    ] = None,
) -> None:
    try:
        result = build_tour(
            path,
            CliOverrides(since=since, full_graph=full_graph or None),
            use_cache=not no_cache,
        )
        target = out if out is not None else result.root / "TOUR.md"
        outputs = [Output(target, render_markdown(result.tour), has_marker)]
        if json_out is not None:
            outputs.append(Output(json_out, render_json(result.tour), is_generated_json))
        write_outputs(outputs, force=force)
    except RepotourError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(exc.exit_code) from None

    warnings = len(result.tour.warnings)
    typer.echo(f"Wrote {target} ({warnings} warning{'' if warnings == 1 else 's'})")
    if json_out is not None:
        typer.echo(f"Wrote {json_out} (experimental JSON)")
    if result.has_uncommitted_changes:
        short = result.tour.meta.head_commit[:7]
        typer.echo(f"Note: uncommitted changes are ignored; the tour describes HEAD ({short}).")
    if strict and warnings:
        typer.echo("error: warnings were produced and --strict is set", err=True)
        raise typer.Exit(EXIT_STRICT_WARNINGS)
