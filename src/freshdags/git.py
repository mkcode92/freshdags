"""Thin wrapper around the `git` command line. The only module that runs git."""

import os
import subprocess
from collections.abc import Mapping
from pathlib import Path

from freshdags.errors import FreshdagsError


class GitError(FreshdagsError):
    """A git command failed."""


class Git:
    """Runs git commands in one repository."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def env(self) -> dict[str, str]:
        """Environment for every git call. Subclasses may override, e.g. to isolate config."""
        return dict(os.environ)

    def run(self, *args: str, env: Mapping[str, str] | None = None) -> str:
        """Run `git <args>` in the repository and return stripped stdout.

        `env` adds to (or overrides) the base environment for this call only.
        """
        result = subprocess.run(
            ["git", *args],
            cwd=self.root,
            env={**self.env(), **(env or {})},
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if result.returncode != 0:
            raise GitError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
        return result.stdout.strip()
