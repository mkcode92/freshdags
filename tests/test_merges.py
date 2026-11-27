"""Merges: a merge commit changes a file itself only where its result differs from git's
automatic merge of its parents, as when someone resolves a conflict.

A clean merge changes nothing itself, even where both sides edited the same file: those
changes are in the commits it merged, and were reviewed (or not) there.
"""

import logging

import pytest
from support import T1, T2, T3, T4, GitRepo
from time_machine import TimeMachineFixture

from freshdags.api import FreshdagsApi
from freshdags.core import Freshdags


def text(first: str = "line 1", last: str = "line 9") -> str:
    """Nine lines. Edits to the first and to the last line merge cleanly; two different
    edits to the same line conflict."""
    return "\n".join([first, *(f"line {n}" for n in range(2, 9)), last]) + "\n"


def setup_doc(repo: GitRepo, fd: FreshdagsApi) -> None:
    """docs/api.md depends on src/api.py, both nine lines, committed on `main` at T1."""
    repo.write("docs/api.md", text())
    repo.write("src/api.py", text())
    fd.add("docs/api.md", "src/api.py")
    repo.commit(date=T1)


def change_api_on_both_sides_with_doc_updates(repo: GitRepo, fd: FreshdagsApi) -> None:
    """`feature` and `main` change the same line of src/api.py differently, each with a doc
    update on its own line. Both are fresh; merging them conflicts in src/api.py only."""
    setup_doc(repo, fd)
    repo.checkout("feature", new=True)
    repo.commit({"src/api.py": text(first="api a"), "docs/api.md": text(first="doc a")}, date=T2)
    repo.checkout("main")
    repo.commit({"src/api.py": text(first="api b"), "docs/api.md": text(last="doc b")}, date=T3)


def test_source_rewritten_while_resolving_a_conflict_flags(repo: GitRepo, fd: FreshdagsApi) -> None:
    change_api_on_both_sides_with_doc_updates(repo, fd)

    merge = repo.merge("feature", date=T4, resolve={"src/api.py": text(first="api a + b")})

    report = fd.check()
    assert report.drifted_docs == ["docs/api.md"]
    assert report.drift[0].source_changed_commit == merge


def test_doc_updated_while_resolving_a_conflict_is_fresh(repo: GitRepo, fd: FreshdagsApi) -> None:
    change_api_on_both_sides_with_doc_updates(repo, fd)

    repo.merge(
        "feature",
        date=T4,
        resolve={
            "src/api.py": text(first="api a + b"),
            "docs/api.md": text(first="doc a + b", last="doc b"),
        },
    )

    assert fd.check().ok


def test_clean_merge_of_reviewed_changes_stays_fresh(
    repo: GitRepo, fd: FreshdagsApi, time_machine: TimeMachineFixture
) -> None:
    """Both sides changed src/api.py, so the merged file differs from each parent. One side
    updated the doc, the other resolved it; the merge itself changed nothing."""
    setup_doc(repo, fd)
    repo.checkout("feature", new=True)
    repo.commit({"src/api.py": text(first="api a"), "docs/api.md": text(first="doc a")}, date=T2)
    repo.checkout("main")
    repo.commit({"src/api.py": text(last="api b")}, date=T2)
    time_machine.move_to(T3, tick=False)
    fd.resolve("docs/api.md", note="internal change")
    repo.commit(date=T3)

    repo.merge("feature", date=T4)

    assert fd.check().ok


def test_clean_merge_reviews_nothing(repo: GitRepo, fd: FreshdagsApi) -> None:
    """Both sides edited the doc, so the merged doc differs from each parent; that does not
    make the merge a review of the unreviewed source change it brings in."""
    setup_doc(repo, fd)
    repo.checkout("feature", new=True)
    repo.commit({"docs/api.md": text(first="doc, typo fixed")}, date=T2)
    repo.commit({"src/api.py": text(last="api changed, doc not updated")}, date=T3)
    repo.checkout("main")
    repo.commit({"docs/api.md": text(last="doc, another typo fixed")}, date=T3)

    repo.merge("feature", date=T4)

    assert fd.check().drifted_docs == ["docs/api.md"]


class GitBefore236(GitRepo):
    def version(self) -> tuple[int, int]:
        return (2, 35)


def test_git_before_2_36_warns_and_misses_conflict_resolutions(
    repo: GitRepo, fd: FreshdagsApi, caplog: pytest.LogCaptureFixture
) -> None:
    """The documented limitation: without `--remerge-diff`, merges list no changes."""
    change_api_on_both_sides_with_doc_updates(repo, fd)
    repo.merge("feature", date=T4, resolve={"src/api.py": text(first="api a + b")})
    old = Freshdags(repo.root, git=GitBefore236(repo.root))

    with caplog.at_level(logging.WARNING):
        report = old.check()

    assert report.ok
    assert "needs 2.36" in caplog.text
