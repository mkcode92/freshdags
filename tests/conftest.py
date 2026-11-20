"""Fixtures. Tests call FreshdagsApi methods directly and inspect freshdags.json as plain JSON,
so neither the CLI binding nor the internal module layout is under test here."""

from pathlib import Path

import pytest
from support import Clock, GitRepo

from freshdags.api import FreshdagsApi


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> GitRepo:
    """An empty git repository that is also the current working directory."""
    repo = GitRepo(tmp_path)
    repo.init()
    monkeypatch.chdir(tmp_path)
    return repo


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def fd(repo: GitRepo, clock: Clock) -> FreshdagsApi:
    """The implementation under test, working on `repo` with a pinned clock."""
    from freshdags.core import Freshdags  # not implemented yet

    return Freshdags(repo.root, now=clock, git=repo)
