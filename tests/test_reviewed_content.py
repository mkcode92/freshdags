"""A resolve records the content it reviewed. A change to exactly that content needs no new
review, even when it is committed after the resolve: committing moves a change's time from
its save to its commit, but not its content."""

from support import T2, T3, T4, GitRepo, setup_api_doc
from time_machine import TimeMachineFixture

from freshdags.api import FreshdagsApi
from freshdags.models import Mode


def test_resolve_before_commit_passes_the_hook_and_stays_fresh(
    repo: GitRepo, fd: FreshdagsApi, time_machine: TimeMachineFixture
) -> None:
    """Source changed, doc still correct: resolve, then commit. The pre-commit hook and
    every later check agree."""
    setup_api_doc(repo, fd)
    repo.save("src/api.py", "api v2", at=T2)
    time_machine.move_to(T3, tick=False)
    fd.resolve("docs/api.md")
    time_machine.move_to(T4, tick=False)

    assert fd.check(uncommitted=True).ok
    repo.commit(date=T4)
    assert fd.check().ok
    assert fd.check("HEAD").ok


def test_change_after_the_resolve_is_flagged_even_in_the_same_commit(
    repo: GitRepo, fd: FreshdagsApi, time_machine: TimeMachineFixture
) -> None:
    setup_api_doc(repo, fd)
    time_machine.move_to(T2, tick=False)
    fd.resolve("docs/api.md")
    repo.save("src/api.py", "api v2", at=T3)
    time_machine.move_to(T4, tick=False)

    assert not fd.check(uncommitted=True).ok
    repo.commit(date=T4)
    assert fd.check().drifted_docs == ["docs/api.md"]


def test_editing_after_the_resolve_needs_a_new_review(
    repo: GitRepo, fd: FreshdagsApi, time_machine: TimeMachineFixture
) -> None:
    setup_api_doc(repo, fd)
    repo.save("src/api.py", "api v2", at=T2)
    time_machine.move_to(T3, tick=False)
    fd.resolve("docs/api.md")
    repo.save("src/api.py", "api v3", at=T4)
    time_machine.move_to(T4, tick=False)

    assert fd.check(uncommitted=True).drifted_docs == ["docs/api.md"]


def test_on_change_mode_stays_fresh_through_the_commit(
    repo: GitRepo, fd: FreshdagsApi, time_machine: TimeMachineFixture
) -> None:
    setup_api_doc(repo, fd)
    fd.configure(auto_flag=Mode.ON_CHANGE, auto_resolve=Mode.ON_CHANGE)
    repo.save("src/api.py", "api v2", at=T2)
    assert fd.check().drifted_docs == ["docs/api.md"]
    time_machine.move_to(T3, tick=False)
    fd.resolve("docs/api.md")

    assert fd.check().ok
    repo.commit(date=T4)
    assert fd.check().ok


def test_a_flag_after_the_resolve_is_never_covered(
    repo: GitRepo, fd: FreshdagsApi, time_machine: TimeMachineFixture
) -> None:
    setup_api_doc(repo, fd)
    time_machine.move_to(T2, tick=False)
    fd.resolve("docs/api.md")
    time_machine.move_to(T3, tick=False)
    fd.flag("src/api.py", note="semantics changed")

    assert fd.check().drifted_docs == ["docs/api.md"]


def test_only_the_reviewed_sources_are_covered(
    repo: GitRepo, fd: FreshdagsApi, time_machine: TimeMachineFixture
) -> None:
    setup_api_doc(repo, fd)
    repo.write("src/models.py", "models v1")
    fd.add("docs/api.md", "src/models.py")
    repo.commit(date=T2)
    repo.save("src/api.py", "api v2", at=T3)
    time_machine.move_to(T3, tick=False)
    fd.resolve("docs/api.md")
    repo.save("src/models.py", "models v2", at=T4)
    time_machine.move_to(T4, tick=False)
    repo.commit(date=T4)

    report = fd.check()

    assert [d.source for d in report.drift] == ["src/models.py"]
