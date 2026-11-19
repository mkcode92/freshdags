"""Sanity checks for the test helpers themselves."""

from conftest import GitRepo


def test_commit_dates_are_controllable(repo: GitRepo) -> None:
    repo.commit({"src/api.py": "v1"}, date="2026-01-01T10:00:00+00:00")
    repo.commit({"docs/api.md": "doc"}, date="2026-01-02T10:00:00+00:00")
    assert repo.author_time("HEAD~1").day == 1
    assert repo.author_time("HEAD").day == 2


def test_committer_date_can_differ(repo: GitRepo) -> None:
    repo.commit(
        {"a.txt": "a"}, date="2026-01-01T10:00:00+00:00", committer_date="2026-03-01T10:00:00+00:00"
    )
    assert repo.author_time().month == 1
    assert repo.git("show", "--no-patch", "--format=%cI").startswith("2026-03-01")
