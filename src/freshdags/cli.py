"""Command-line entry point."""

from typing import Annotated

import typer

from freshdags import __version__

app = typer.Typer(
    name="freshdags",
    help="Track doc/code dependencies and flag documentation drift.",
    no_args_is_help=True,
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"freshdags {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool | None,
        typer.Option(
            "--version",
            callback=_version_callback,
            is_eager=True,
            help="Show the version and exit.",
        ),
    ] = None,
) -> None:
    """Track doc/code dependencies and flag documentation drift."""
