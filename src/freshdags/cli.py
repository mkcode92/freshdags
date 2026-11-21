"""Command-line entry point: parses arguments, calls FreshdagsApi, renders the result.

Exit codes: 0 success / no drift, 1 drift found, 2 usage or graph error.

Output: results (the check report, `show`) go to stdout; confirmations and diagnostics are
log messages on stderr, hidden unless `-v` is given. `-q` hides results too, leaving only
errors and the exit code.
"""

import functools
import io
import logging
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Annotated

import typer

from freshdags import __version__
from freshdags.api import FreshdagsApi
from freshdags.core import Freshdags
from freshdags.errors import FreshdagsError
from freshdags.models import Mode
from freshdags.render import render_check, render_graph, render_node, render_settings

app = typer.Typer(
    name="freshdags",
    help="Track doc/code dependencies and flag documentation drift.",
    no_args_is_help=True,
)


log = logging.getLogger("freshdags")


class Output:
    """Where command results go. Quiet mode drops them; errors are never dropped."""

    quiet = False

    def result(self, text: str) -> None:
        if not self.quiet:
            typer.echo(text)


output = Output()


def api() -> FreshdagsApi:
    return Freshdags.discover(Path.cwd())


def configure_logging(verbose: int) -> None:
    """No `-v`: warnings only. `-v`: confirmations. `-vv`: diagnostics, e.g. git calls."""
    level = {0: logging.WARNING, 1: logging.INFO}.get(verbose, logging.DEBUG)
    logging.basicConfig(level=level, format="%(message)s", stream=sys.stderr, force=True)


def tolerate_unprintable_output() -> None:
    """Print `?` for characters the output encoding cannot show, instead of crashing.

    Matters on Windows, where piped or redirected output uses the ANSI code page.
    """
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(errors="replace")


def handle_errors[**P, R](command: Callable[P, R]) -> Callable[P, R]:
    """Report FreshdagsError as a message on stderr with exit code 2."""

    @functools.wraps(command)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return command(*args, **kwargs)
        except FreshdagsError as error:
            typer.echo(f"Error: {error}", err=True)
            raise typer.Exit(2) from error

    return wrapper


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
    verbose: Annotated[
        int,
        typer.Option(
            "--verbose", "-v", count=True, help="Show confirmations; -vv adds diagnostics."
        ),
    ] = 0,
    quiet: Annotated[
        bool, typer.Option("--quiet", "-q", help="Print nothing but errors; use the exit code.")
    ] = False,
) -> None:
    """Track doc/code dependencies and flag documentation drift."""
    if verbose and quiet:
        raise typer.BadParameter("--verbose and --quiet cannot be combined.")
    tolerate_unprintable_output()
    configure_logging(verbose)
    output.quiet = quiet


@app.command()
@handle_errors
def add(
    doc: Annotated[str, typer.Argument(help="The file (or ext:name) that depends on SOURCES.")],
    sources: Annotated[list[str], typer.Argument(help="Files (or ext:names) it depends on.")],
) -> None:
    """Record that DOC depends on each SOURCE."""
    api().add(doc, *sources)
    log.info("%s depends on %s", doc, ", ".join(sources))


@app.command()
@handle_errors
def rm(
    doc: Annotated[str, typer.Argument(help="The dependent file.")],
    sources: Annotated[list[str], typer.Argument(help="Sources to remove.")],
) -> None:
    """Remove the dependencies of DOC on each SOURCE."""
    api().rm(doc, *sources)
    log.info("%s no longer depends on %s", doc, ", ".join(sources))


@app.command()
@handle_errors
def configure(
    auto_flag: Annotated[
        Mode | None, typer.Option(help="What marks a source as changed automatically.")
    ] = None,
    auto_resolve: Annotated[
        Mode | None, typer.Option(help="What brings a doc up to date automatically.")
    ] = None,
) -> None:
    """Show the settings, or change them with --auto-flag / --auto-resolve."""
    output.result(render_settings(api().configure(auto_flag=auto_flag, auto_resolve=auto_resolve)))


@app.command()
@handle_errors
def show(
    node: Annotated[str | None, typer.Argument(help="Show only this node.")] = None,
) -> None:
    """Print the graph, or one node's sources and dependents."""
    fd = api()
    output.result(render_node(fd.neighbours(node)) if node else render_graph(fd.graph()))


@app.command()
@handle_errors
def check(
    rev: Annotated[
        str | None, typer.Argument(help="Check as of this commit. Default: working tree.")
    ] = None,
    as_json: Annotated[bool, typer.Option("--json", help="Machine-readable output.")] = False,
    uncommitted: Annotated[
        bool,
        typer.Option(
            "--uncommitted", help="Count uncommitted changes as a commit made now (pre-commit)."
        ),
    ] = False,
) -> None:
    """List every doc that is older than one of its sources. Exits 1 on drift."""
    report = api().check(rev, uncommitted=uncommitted)
    if as_json:
        output.result(report.model_dump_json(indent=2))
    else:
        output.result(render_check(report))
    raise typer.Exit(0 if report.ok else 1)


@app.command()
@handle_errors
def resolve(
    docs: Annotated[list[str] | None, typer.Argument(help="Docs you reviewed.")] = None,
    all_docs: Annotated[bool, typer.Option("--all", help="Resolve every drifted doc.")] = False,
) -> None:
    """Mark docs as up to date after reviewing them."""
    if all_docs == bool(docs):
        raise typer.BadParameter("Name the docs to resolve, or use --all, but not both.")
    fd = api()
    resolved = fd.resolve_all() if all_docs else fd.resolve(*(docs or []))
    log.info("Resolved: %s", ", ".join(resolved) if resolved else "nothing")


@app.command()
@handle_errors
def flag(
    node: Annotated[str, typer.Argument(help="The file (or ext:name) that changed.")],
    note: Annotated[str | None, typer.Option(help="What changed.")] = None,
) -> None:
    """Record that NODE changed in a way git cannot see, flagging its dependents."""
    api().flag(node, note)
    log.info("Flagged %s", node)
