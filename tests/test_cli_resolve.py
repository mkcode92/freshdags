"""`freshdags resolve` on the command line requires a note: a resolve claims the doc is still
correct, and the note makes that claim reviewable. The API leaves it optional."""

from support import GitRepo, setup_api_doc
from typer.testing import CliRunner

from freshdags.api import FreshdagsApi
from freshdags.cli import app


def test_resolve_without_note_is_refused(repo: GitRepo, fd: FreshdagsApi) -> None:
    setup_api_doc(repo, fd)

    result = CliRunner().invoke(app, ["resolve", "docs/api.md"])

    assert result.exit_code == 2
    assert "--note" in result.output
    assert "resolved" not in repo.graph()["nodes"]["docs/api.md"]


def test_blank_note_is_refused(repo: GitRepo, fd: FreshdagsApi) -> None:
    setup_api_doc(repo, fd)

    result = CliRunner().invoke(app, ["resolve", "docs/api.md", "--note", "  "])

    assert result.exit_code == 2


def test_resolve_with_note_is_recorded(repo: GitRepo, fd: FreshdagsApi) -> None:
    setup_api_doc(repo, fd)

    result = CliRunner().invoke(app, ["resolve", "docs/api.md", "--note", " only a rename "])

    assert result.exit_code == 0
    assert repo.graph()["nodes"]["docs/api.md"]["resolved"]["note"] == "only a rename"
