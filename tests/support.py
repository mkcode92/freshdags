"""Test helpers: a git repo with controllable dates, and shared scenarios."""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from freshdags.api import FreshdagsApi
from freshdags.git import Git
from freshdags.models import GRAPH_FILE

T1 = "2026-01-01T10:00:00+00:00"
T2 = "2026-01-02T10:00:00+00:00"
T3 = "2026-01-03T10:00:00+00:00"
T4 = "2026-01-04T10:00:00+00:00"


class GitRepo(Git):
    """A throwaway repository. Unlike `Git`, it writes history, with explicit dates."""

    def env(self) -> dict[str, str]:
        """Ignore the developer's own git config, so tests behave the same everywhere."""
        return {**super().env(), "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}

    def init(self) -> None:
        self.run("init", "--quiet", "--initial-branch=main")
        self.run("config", "user.name", "Test")
        self.run("config", "user.email", "test@example.invalid")

    def write(self, path: str, content: str = "") -> Path:
        file = self.root / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(content, encoding="utf-8")
        return file

    def save(self, path: str, content: str, *, at: str) -> Path:
        """Write a file without committing it, with its modification time set to ISO `at`."""
        file = self.write(path, content)
        timestamp = datetime.fromisoformat(at).timestamp()
        os.utime(file, (timestamp, timestamp))
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
        self.run("add", "--all")
        dates = {"GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": committer_date or date}
        self.run("commit", "--quiet", "--allow-empty", "--message", message, env=dates)
        return self.run("rev-parse", "HEAD")

    def author_time(self, rev: str = "HEAD") -> datetime:
        return datetime.fromisoformat(self.run("show", "--no-patch", "--format=%aI", rev))

    # --- graph file, read and edited as plain JSON, independent of freshdags.models -------

    def graph(self) -> dict[str, Any]:
        return json.loads(self.graph_text())

    def graph_text(self) -> str:
        return (self.root / GRAPH_FILE).read_text(encoding="utf-8")

    def set_setting(self, key: str, value: str) -> None:
        """Edit a setting by hand, as a user would."""
        data = self.graph()
        data["settings"][key] = value
        (self.root / GRAPH_FILE).write_text(json.dumps(data, indent=2), encoding="utf-8")


def setup_api_doc(repo: GitRepo, fd: FreshdagsApi) -> str:
    """docs/api.md depends on src/api.py, both committed at T1. Returns that commit's sha."""
    repo.write("docs/api.md", "doc v1")
    repo.write("src/api.py", "api v1")
    fd.add("docs/api.md", "src/api.py")
    return repo.commit(date=T1)
