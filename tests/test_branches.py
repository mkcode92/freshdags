"""Branches: a doc has seen a commit when one of its own commits or resolves descends from it.

Dates cannot order commits across branches: a commit keeps its author date when it is rebased
or merged, so a source change from a branch can land after a doc edit that never saw it.
"""

import json

from support import T2, T3, T4, GitRepo, setup_api_doc
from time_machine import TimeMachineFixture

from freshdags.api import FreshdagsApi
from freshdags.models import GRAPH_FILE


def change_api_on_branch_while_main_edits_doc(repo: GitRepo, fd: FreshdagsApi) -> str:
    """`feature` changes src/api.py at T2; then `main` fixes a typo in the doc at T3, which
    did not see the change. Leaves `feature` checked out; returns the typo commit."""
    setup_api_doc(repo, fd)
    repo.checkout("feature", new=True)
    repo.commit({"src/api.py": "api v2"}, date=T2)
    repo.checkout("main")
    typo = repo.commit({"docs/api.md": "doc v1, typo fixed"}, date=T3)
    repo.checkout("feature")
    return typo


def test_source_change_rebased_onto_a_doc_edit_flags(repo: GitRepo, fd: FreshdagsApi) -> None:
    """The rebased change is older by date than the doc edit, but descends from it."""
    typo = change_api_on_branch_while_main_edits_doc(repo, fd)

    repo.rebase("main", date=T4)

    report = fd.check()
    assert report.drifted_docs == ["docs/api.md"]
    assert report.drift[0].doc_fresh_commit == typo
    assert report.drift[0].source_changed_commit == repo.run("rev-parse", "HEAD")


def test_source_change_merged_after_a_doc_edit_flags(repo: GitRepo, fd: FreshdagsApi) -> None:
    change_api_on_branch_while_main_edits_doc(repo, fd)
    repo.checkout("main")

    repo.merge("feature", date=T4)

    assert fd.check().drifted_docs == ["docs/api.md"]


def test_doc_updated_on_the_branch_stays_fresh_through_rebase_and_merge(
    repo: GitRepo, fd: FreshdagsApi
) -> None:
    setup_api_doc(repo, fd)
    repo.checkout("feature", new=True)
    repo.commit({"src/api.py": "api v2"}, date=T2)
    repo.commit({"docs/api.md": "doc v2"}, date=T2)
    repo.checkout("main")
    repo.commit({"src/other.py": "unrelated"}, date=T3)
    repo.checkout("feature")

    repo.rebase("main", date=T4)
    assert fd.check().ok

    repo.checkout("main")
    repo.merge("feature", date=T4)
    assert fd.check().ok


def test_doc_edit_on_main_does_not_see_a_change_on_another_branch(
    repo: GitRepo, fd: FreshdagsApi
) -> None:
    """Checked on `feature` before any rebase: the doc edit on `main` is not in its history."""
    change_api_on_branch_while_main_edits_doc(repo, fd)

    assert fd.check().drifted_docs == ["docs/api.md"]


def test_resolve_survives_a_squash_merge(
    repo: GitRepo, fd: FreshdagsApi, time_machine: TimeMachineFixture
) -> None:
    """The squash replaces the commit the resolve was made on, and that commit is gone; the
    content the resolve reviewed is what the squashed commit contains."""
    setup_api_doc(repo, fd)
    repo.checkout("feature", new=True)
    repo.commit({"src/api.py": "api v2"}, date=T2)
    time_machine.move_to(T3, tick=False)
    fd.resolve("docs/api.md", note="internal refactor")
    resolved_on = repo.graph()["nodes"]["docs/api.md"]["resolved"]["commit"]
    repo.commit(date=T3)
    repo.checkout("main")
    repo.merge("feature", date=T4, squash=True)

    repo.forget("feature")

    assert "missing" in repo.run("cat-file", "--batch-check", input=resolved_on + "\n")
    assert fd.check().ok


def test_resolve_on_a_lost_commit_does_not_cover_other_content(
    repo: GitRepo, fd: FreshdagsApi, time_machine: TimeMachineFixture
) -> None:
    setup_api_doc(repo, fd)
    repo.checkout("feature", new=True)
    repo.commit({"src/api.py": "api v2"}, date=T2)
    time_machine.move_to(T3, tick=False)
    fd.resolve("docs/api.md", note="internal refactor")
    repo.commit({"src/api.py": "api v3, after the resolve"}, date=T3)
    repo.checkout("main")
    repo.merge("feature", date=T4, squash=True)

    repo.forget("feature")

    assert fd.check().drifted_docs == ["docs/api.md"]


def test_version_1_resolve_covers_the_commits_it_was_made_on(
    repo: GitRepo, fd: FreshdagsApi
) -> None:
    """Resolves from version-1 files recorded no content, only the commit and time."""
    setup_api_doc(repo, fd)
    reviewed = repo.commit({"src/api.py": "api v2"}, date=T2)
    data = repo.graph()
    data["version"] = 1
    data["nodes"]["docs/api.md"]["resolved"] = {"at": T3, "by": "Test", "commit": reviewed}
    (repo.root / GRAPH_FILE).write_text(json.dumps(data), encoding="utf-8")
    assert fd.check().ok

    repo.commit({"src/api.py": "api v3"}, date=T4)

    assert fd.check().drifted_docs == ["docs/api.md"]


def test_check_at_a_branch_uses_that_branch_only(repo: GitRepo, fd: FreshdagsApi) -> None:
    """The doc update on `feature` covers the change there, not on `main`."""
    setup_api_doc(repo, fd)
    repo.commit({"src/api.py": "api v2"}, date=T2)
    repo.checkout("feature", new=True)
    repo.commit({"docs/api.md": "doc v2"}, date=T3)
    repo.checkout("main")

    assert fd.check().drifted_docs == ["docs/api.md"]
    assert fd.check("feature").ok
