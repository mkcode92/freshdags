from typer.testing import CliRunner

from freshdags import __version__
from freshdags.cli import app

runner = CliRunner()


def test_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_no_args_prints_help() -> None:
    result = runner.invoke(app, [])
    assert "Usage:" in result.output
