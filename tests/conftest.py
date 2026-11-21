"""Fixtures. Tests call FreshdagsApi methods directly and inspect freshdags.json as plain JSON,
so neither the CLI binding nor the internal module layout is under test here."""

from pathlib import Path

import pytest
from support import GitRepo

from freshdags.api import FreshdagsApi
from freshdags.core import Freshdags


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> GitRepo:
    """An empty git repository that is also the current working directory."""
    repo = GitRepo(tmp_path)
    repo.init()
    monkeypatch.chdir(tmp_path)
    return repo


@pytest.fixture
def fd(repo: GitRepo) -> FreshdagsApi:
    """The implementation under test, working on `repo`.

    Tests that need a specific wall-clock time for `resolve` / `flag` records pin it with
    the `time_machine` fixture: `time_machine.move_to(T2, tick=False)`.
    """
    return Freshdags(repo.root, git=repo)
