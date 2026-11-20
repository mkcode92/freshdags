"""Sanity checks for the test helpers themselves."""

from support import T1, T2, GitRepo

from freshdags.models import Graph


def test_commit_dates_are_controllable(repo: GitRepo) -> None:
    repo.commit({"src/api.py": "v1"}, date=T1)
    repo.commit({"docs/api.md": "doc"}, date=T2)
    assert repo.author_time("HEAD~1").day == 1
    assert repo.author_time("HEAD").day == 2


def test_committer_date_can_differ(repo: GitRepo) -> None:
    repo.commit({"a.txt": "a"}, date=T1, committer_date="2026-03-01T10:00:00+00:00")
    assert repo.author_time().month == 1
    assert repo.run("show", "--no-patch", "--format=%cI").startswith("2026-03-01")


def test_git_config_is_isolated(repo: GitRepo) -> None:
    assert repo.run("config", "user.name") == "Test"


def test_set_setting_keeps_graph_valid(repo: GitRepo) -> None:
    (repo.root / "freshdags.json").write_text(Graph().to_json(), encoding="utf-8")
    repo.set_setting("resolve", "manual")
    assert Graph.from_json(repo.graph_text()).settings.resolve == "manual"
