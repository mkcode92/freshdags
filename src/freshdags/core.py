"""The implementation of FreshdagsApi."""

from pathlib import Path
from typing import Self

from freshdags.api import FreshdagsApi
from freshdags.errors import FreshdagsError
from freshdags.git import Git, GitError
from freshdags.models import CheckReport, Graph, NodeView


class Freshdags(FreshdagsApi):
    """freshdags for the git repository at `root`.

    `git` runs git commands; it is injectable so tests can isolate git config.
    """

    def __init__(self, root: Path, *, git: Git | None = None) -> None:
        self.root = root
        self.git = git or Git(root)

    @classmethod
    def discover(cls, start: Path) -> Self:
        """freshdags for the repository containing `start`."""
        try:
            root = Git(start).run("rev-parse", "--show-toplevel")
        except GitError as error:
            raise FreshdagsError(f"Not inside a git repository: {start}") from error
        return cls(Path(root))

    def add(self, doc: str, *sources: str) -> None:
        raise NotImplementedError

    def rm(self, doc: str, *sources: str) -> None:
        raise NotImplementedError

    def graph(self) -> Graph:
        raise NotImplementedError

    def neighbours(self, node: str) -> NodeView:
        raise NotImplementedError

    def check(self, rev: str | None = None) -> CheckReport:
        raise NotImplementedError

    def resolve(self, *docs: str) -> list[str]:
        raise NotImplementedError

    def resolve_all(self) -> list[str]:
        raise NotImplementedError

    def flag(self, node: str, note: str | None = None) -> None:
        raise NotImplementedError
