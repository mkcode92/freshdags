"""Test helpers: a git repo with controllable dates, and shared scenarios."""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from freshdags.api import FreshdagsApi
from freshdags.git import Git, GitError
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

    def write(self, path: str, content: str = "", *, stage: bool = True) -> Path:
        """Write a file and, unless `stage=False`, stage it, so git tracks it."""
        file = self.root / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(content, encoding="utf-8")
        if stage:
            self.run("add", "--", path)
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

    def checkout(self, branch: str, *, new: bool = False) -> None:
        self.run("checkout", "--quiet", *(["-b"] if new else []), branch)

    def merge(
        self,
        branch: str,
        *,
        date: str,
        squash: bool = False,
        resolve: dict[str, str] | None = None,
    ) -> str:
        """Merge `branch` into the current branch at ISO `date`, with a merge commit, or as
        one new commit with `squash`. Returns the commit sha.

        `resolve` (path -> content) is written into the result before it is committed, as
        when someone settles a conflict. Without it, a conflict fails the merge.
        """
        dates = {"GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date}
        how = "--squash" if squash else "--no-ff"
        try:
            self.run("merge", "--quiet", "--no-commit", how, branch, env=dates)
        except GitError:
            if resolve is None:
                raise
        for path, content in (resolve or {}).items():
            self.write(path, content)
        self.run("commit", "--quiet", "--message", f"merge {branch}", env=dates)
        return self.run("rev-parse", "HEAD")

    def rebase(self, onto: str, *, date: str) -> None:
        """Rebase the current branch onto `onto`. The new commits keep their author dates."""
        self.run("rebase", "--quiet", onto, env={"GIT_COMMITTER_DATE": date})

    def forget(self, branch: str) -> None:
        """Delete `branch` and every commit only it held, as after a squash merge and a fresh
        clone."""
        self.run("branch", "--quiet", "-D", branch)
        self.run("reflog", "expire", "--expire=now", "--all")
        self.run("gc", "--quiet", "--prune=now")

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
