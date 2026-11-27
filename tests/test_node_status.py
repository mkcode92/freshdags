"""`node_status`: what is known about each node besides its edges."""

from datetime import datetime

from support import T1, T2, T3, GitRepo, setup_api_doc
from time_machine import TimeMachineFixture

from freshdags.api import FreshdagsApi
from freshdags.models import Commit


def test_status_has_last_commit_with_author_and_subject(repo: GitRepo, fd: FreshdagsApi) -> None:
    setup_api_doc(repo, fd)
    sha = repo.commit({"src/api.py": "api v2"}, date=T2, message="Change the API\n\nDetails.")

    status = {s.name: s for s in fd.node_status()}

    assert status["src/api.py"].last_commit == Commit(
        sha=sha, at=datetime.fromisoformat(T2), author="Test", subject="Change the API"
    )
    assert status["docs/api.md"].last_commit.subject == "change"


def test_status_lists_every_node_by_name(repo: GitRepo, fd: FreshdagsApi) -> None:
    setup_api_doc(repo, fd)
    fd.add("docs/api.md", "ext:stripe-api")

    status = fd.node_status()

    assert [s.name for s in status] == ["docs/api.md", "ext:stripe-api", "src/api.py"]
    assert status[1].last_commit is None


def test_status_reports_saves_in_on_commit_mode(repo: GitRepo, fd: FreshdagsApi) -> None:
    setup_api_doc(repo, fd)
    repo.save("src/api.py", "api v2", at=T2)

    status = {s.name: s for s in fd.node_status()}

    assert status["src/api.py"].saved_at == datetime.fromisoformat(T2)
    assert status["docs/api.md"].saved_at is None


def test_status_has_resolve_and_flag_records(
    repo: GitRepo, fd: FreshdagsApi, time_machine: TimeMachineFixture
) -> None:
    repo.write("docs/api.md", "doc v1")
    fd.add("docs/api.md", "ext:stripe-api")
    repo.commit(date=T1)
    time_machine.move_to(T2, tick=False)
    fd.flag("ext:stripe-api", note="API v2 released")
    time_machine.move_to(T3, tick=False)
    fd.resolve("docs/api.md")

    status = {s.name: s for s in fd.node_status()}

    assert status["ext:stripe-api"].flagged.note == "API v2 released"
    assert status["docs/api.md"].resolved.at == datetime.fromisoformat(T3)


def test_subject_may_contain_separators(repo: GitRepo, fd: FreshdagsApi) -> None:
    setup_api_doc(repo, fd)
    repo.commit({"src/api.py": "v2"}, date=T2, message="@@ odd\x1f subject")

    status = {s.name: s for s in fd.node_status()}

    assert status["src/api.py"].last_commit.subject == "@@ odd\x1f subject"
