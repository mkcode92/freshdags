"""Thin wrapper around the `git` command line. The only module that runs git."""

import logging
import os
import re
import subprocess
from collections.abc import Mapping
from pathlib import Path

from freshdags.errors import FreshdagsError

log = logging.getLogger(__name__)


class GitError(FreshdagsError):
    """A git command failed."""


class Git:
    """Runs git commands in one repository."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def env(self) -> dict[str, str]:
        """Environment for every git call. Subclasses may override, e.g. to isolate config."""
        return dict(os.environ)

    def run(
        self,
        *args: str,
        env: Mapping[str, str] | None = None,
        strip: bool = True,
        input: str | None = None,
    ) -> str:
        """Run `git <args>` in the repository and return stdout.

        `env` adds to (or overrides) the base environment for this call only. `strip=False`
        keeps leading whitespace, which is significant in some formats like `status`. `input`
        is sent to stdin, for `--stdin` options that take more than a command line holds.
        """
        log.debug("git %s", " ".join(args))
        result = subprocess.run(
            ["git", *args],
            cwd=self.root,
            env={**self.env(), **(env or {})},
            input=input,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if result.returncode != 0:
            raise GitError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
        return result.stdout.strip() if strip else result.stdout

    def version(self) -> tuple[int, int]:
        """(major, minor) of the installed git, e.g. (2, 36) for `git version 2.36.1`."""
        found = re.search(r"(\d+)\.(\d+)", self.run("version"))
        if not found:
            raise GitError("Cannot read the git version.")
        return int(found[1]), int(found[2])
