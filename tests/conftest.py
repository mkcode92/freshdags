"""Shared fixtures: a throwaway git repo with controllable dates, a pinned clock, a CLI runner.

Tests drive freshdags through the CLI and inspect `freshdags.json` directly, so the internal
module layout stays free to change.
"""

import json
import os
import subprocess
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner, Result

from freshdags.cli import app

GRAPH_FILE = "freshdags.json"

Clock = Callable[[str], None]
"""Type of the `clock` fixture: call it with an ISO timestamp to pin "now"."""


@dataclass
class GitRepo:
    """A git repository in a temp dir. Commit dates are explicit so tests are deterministic."""

    root: Path

    def git(
        self, *args: str, author_date: str | None = None, committer_date: str | None = None
    ) -> str:
        env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
        if author_date is not None:
            env["GIT_AUTHOR_DATE"] = author_date
        if committer_date is not None:
            env["GIT_COMMITTER_DATE"] = committer_date
        result = subprocess.run(
            ["git", *args], cwd=self.root, env=env, check=True, capture_output=True, text=True
        )
        return result.stdout.strip()

    def write(self, path: str, content: str = "") -> Path:
        file = self.root / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(content, encoding="utf-8")
        return file

    def commit(
        self,
        files: dict[str, str] | None = None,
        *,
        date: str,
        committer_date: str | None = None,
        message: str = "change",
    ) -> str:
        """Write `files` (path -> content) and commit everything at ISO `date`.

        `committer_date` defaults to `date`; set it separately to simulate a rebase.
        Returns the commit sha.
        """
        for path, content in (files or {}).items():
            self.write(path, content)
        self.git("add", "--all")
        self.git(
            "commit",
            "--quiet",
            "--allow-empty",
            "--message",
            message,
            author_date=date,
            committer_date=committer_date or date,
        )
        return self.git("rev-parse", "HEAD")

    def author_time(self, rev: str = "HEAD") -> datetime:
        return datetime.fromisoformat(self.git("show", "--no-patch", "--format=%aI", rev))

    # --- graph file helpers -------------------------------------------------------------

    def graph(self) -> dict[str, Any]:
        return json.loads((self.root / GRAPH_FILE).read_text(encoding="utf-8"))

    def graph_text(self) -> str:
        return (self.root / GRAPH_FILE).read_text(encoding="utf-8")

    def set_setting(self, key: str, value: str) -> None:
        """Edit a setting by hand, as a user would (there is no config command yet)."""
        data = self.graph()
        data["settings"][key] = value
        (self.root / GRAPH_FILE).write_text(json.dumps(data, indent=2), encoding="utf-8")


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[GitRepo]:
    """An empty git repo that is also the current working directory."""
    repo = GitRepo(tmp_path)
    repo.git("init", "--quiet", "--initial-branch=main")
    repo.git("config", "user.name", "Test")
    repo.git("config", "user.email", "test@example.invalid")
    monkeypatch.chdir(tmp_path)
    yield repo


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> Clock:
    """Pin the wall clock for `resolve` / `flag` records: `clock("2026-01-05T12:00:00+00:00")`."""

    def set_now(iso: str) -> None:
        monkeypatch.setattr("freshdags.clock.now", lambda: datetime.fromisoformat(iso))

    return set_now


class Cli:
    """Invoke the freshdags CLI in-process: `cli("check", "HEAD")`."""

    def __init__(self) -> None:
        self._runner = CliRunner()

    def __call__(self, *args: str) -> Result:
        return self._runner.invoke(app, list(args))


@pytest.fixture
def cli() -> Cli:
    return Cli()
