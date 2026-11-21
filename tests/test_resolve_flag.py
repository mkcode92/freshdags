"""`resolve`, `resolve_all` and `flag`: recording that a doc is up to date, or that a source
changed."""

from datetime import datetime

import pytest
from support import T1, T2, T3, GitRepo, setup_api_doc
from time_machine import TimeMachineFixture

from freshdags.api import FreshdagsApi
from freshdags.errors import UnknownNodeError


def test_resolve_clears_drift(
    repo: GitRepo, fd: FreshdagsApi, time_machine: TimeMachineFixture
) -> None:
    setup_api_doc(repo, fd)
    repo.commit({"src/api.py": "api v2"}, date=T2)
    time_machine.move_to(T3, tick=False)

    assert fd.resolve("docs/api.md") == ["docs/api.md"]
    assert fd.check().ok


def test_resolve_records_who_when_and_commit(
    repo: GitRepo, fd: FreshdagsApi, time_machine: TimeMachineFixture
) -> None:
    head = setup_api_doc(repo, fd)
    time_machine.move_to(T2, tick=False)

    fd.resolve("docs/api.md")

    assert repo.graph()["nodes"]["docs/api.md"]["resolved"] == {
        "at": "2026-01-02T10:00:00Z",
        "by": "Test",
        "commit": head,
    }


def test_resolve_is_overtaken_by_later_source_change(
    repo: GitRepo, fd: FreshdagsApi, time_machine: TimeMachineFixture
) -> None:
    setup_api_doc(repo, fd)
    time_machine.move_to(T2, tick=False)
    fd.resolve("docs/api.md")
    repo.commit({"src/api.py": "api v2"}, date=T3)

    assert not fd.check().ok


def test_source_commit_right_after_resolve_flags(
    repo: GitRepo, fd: FreshdagsApi, time_machine: TimeMachineFixture
) -> None:
    """Resolve and the next commit fall into the same second."""
    setup_api_doc(repo, fd)
    time_machine.move_to("2026-01-02T10:00:00.700+00:00", tick=False)
    fd.resolve("docs/api.md")
    repo.commit({"src/api.py": "api v2"}, date=T2)

    assert fd.check().drifted_docs == ["docs/api.md"]


def test_resolve_several_docs(
    repo: GitRepo, fd: FreshdagsApi, time_machine: TimeMachineFixture
) -> None:
    for path in ("docs/a.md", "docs/b.md", "src/api.py"):
        repo.write(path, "v1")
    fd.add("docs/a.md", "src/api.py")
    fd.add("docs/b.md", "src/api.py")
    repo.commit(date=T1)
    repo.commit({"src/api.py": "v2"}, date=T2)
    time_machine.move_to(T3, tick=False)

    fd.resolve("docs/a.md", "docs/b.md")

    assert fd.check().ok


def test_resolve_all_resolves_every_drifted_doc(
    repo: GitRepo, fd: FreshdagsApi, time_machine: TimeMachineFixture
) -> None:
    """The change needed no doc update: clear everything at once."""
    for path in ("docs/a.md", "docs/b.md", "src/x.py", "src/y.py"):
        repo.write(path, "v1")
    fd.add("docs/a.md", "src/x.py")
    fd.add("docs/b.md", "src/x.py", "src/y.py")
    repo.commit(date=T1)
    repo.commit({"src/x.py": "v2", "src/y.py": "v2"}, date=T2)
    time_machine.move_to(T3, tick=False)

    assert fd.resolve_all() == ["docs/a.md", "docs/b.md"]
    assert fd.check().ok


def test_resolve_all_skips_docs_that_were_not_drifted(
    repo: GitRepo, fd: FreshdagsApi, time_machine: TimeMachineFixture
) -> None:
    """Only drifted docs get a resolve record."""
    for path in ("docs/a.md", "docs/b.md", "src/api.py"):
        repo.write(path, "v1")
    fd.add("docs/a.md", "src/api.py")
    fd.add("docs/b.md", "src/api.py")
    repo.commit(date=T1)
    repo.commit({"src/api.py": "v2"}, date=T2)
    repo.commit({"docs/b.md": "v2"}, date=T3)
    time_machine.move_to(T3, tick=False)

    assert fd.resolve_all() == ["docs/a.md"]

    nodes = repo.graph()["nodes"]
    assert "resolved" in nodes["docs/a.md"]
    assert "resolved" not in nodes["docs/b.md"]


def test_resolve_does_not_ripple_to_dependents(
    repo: GitRepo, fd: FreshdagsApi, time_machine: TimeMachineFixture
) -> None:
    """Resolving api.md means its content is still right, so guide.md stays fine."""
    setup_api_doc(repo, fd)
    repo.write("docs/guide.md", "guide v1")
    fd.add("docs/guide.md", "docs/api.md")
    repo.commit(date=T1)
    repo.commit({"src/api.py": "api v2"}, date=T2)
    time_machine.move_to(T3, tick=False)

    fd.resolve("docs/api.md")

    assert fd.check().ok


def test_resolve_unknown_node_fails(repo: GitRepo, fd: FreshdagsApi) -> None:
    setup_api_doc(repo, fd)

    with pytest.raises(UnknownNodeError, match="docs/nope.md"):
        fd.resolve("docs/nope.md")


def test_flag_external_source_flags_dependents(
    repo: GitRepo, fd: FreshdagsApi, time_machine: TimeMachineFixture
) -> None:
    repo.write("docs/api.md", "doc v1")
    fd.add("docs/api.md", "ext:stripe-api")
    repo.commit(date=T1)
    time_machine.move_to(T2, tick=False)

    fd.flag("ext:stripe-api", note="API v2 released")

    assert fd.check().drifted_docs == ["docs/api.md"]
    assert repo.graph()["nodes"]["ext:stripe-api"]["flagged"] == {
        "at": "2026-01-02T10:00:00Z",
        "by": "Test",
        "note": "API v2 released",
    }


def test_flag_then_resolve(
    repo: GitRepo, fd: FreshdagsApi, time_machine: TimeMachineFixture
) -> None:
    repo.write("docs/api.md", "doc v1")
    fd.add("docs/api.md", "ext:stripe-api")
    repo.commit(date=T1)
    time_machine.move_to(T2, tick=False)
    fd.flag("ext:stripe-api")
    time_machine.move_to(T3, tick=False)

    fd.resolve("docs/api.md")

    assert fd.check().ok


def test_flag_local_source_in_on_commit_mode(
    repo: GitRepo, fd: FreshdagsApi, time_machine: TimeMachineFixture
) -> None:
    """Behaviour changed without touching the interface file: flag it by hand."""
    setup_api_doc(repo, fd)
    time_machine.move_to(T2, tick=False)

    fd.flag("src/api.py")

    report = fd.check()
    assert report.drifted_docs == ["docs/api.md"]
    assert report.drift[0].source_changed_at == datetime.fromisoformat(T2)
