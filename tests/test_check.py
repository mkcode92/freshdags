"""`check`: a doc drifts when one of its sources changed after the doc was last up to date.

Default settings are `auto-flag: on-commit` and `auto-resolve: on-commit`, so a commit to a
source counts as a change and a commit to a doc counts as resolving it. A doc also counts as up to
date from the commit that created it. Times are commit author dates, which survive rebases.
"""

from support import T1, T2, T3, T4, GitRepo, setup_api_doc
from time_machine import TimeMachineFixture

from freshdags.api import FreshdagsApi
from freshdags.core import Freshdags


def test_no_drift_when_committed_together(repo: GitRepo, fd: FreshdagsApi) -> None:
    setup_api_doc(repo, fd)

    assert fd.check().ok


def test_source_change_flags_doc(repo: GitRepo, fd: FreshdagsApi) -> None:
    setup_api_doc(repo, fd)
    repo.commit({"src/api.py": "api v2"}, date=T2)

    report = fd.check()

    assert [(d.doc, d.source) for d in report.drift] == [("docs/api.md", "src/api.py")]


def test_doc_updated_in_later_commit_resolves(repo: GitRepo, fd: FreshdagsApi) -> None:
    setup_api_doc(repo, fd)
    repo.commit({"src/api.py": "api v2"}, date=T2)
    repo.commit({"docs/api.md": "doc v2"}, date=T3)

    assert fd.check().ok


def test_unrelated_change_does_not_flag(repo: GitRepo, fd: FreshdagsApi) -> None:
    setup_api_doc(repo, fd)
    repo.commit({"src/internal.py": "impl detail"}, date=T2)

    assert fd.check().ok


def test_rebase_does_not_flag(repo: GitRepo, fd: FreshdagsApi) -> None:
    """A rebase rewrites committer dates; author dates keep the real order."""
    setup_api_doc(repo, fd)
    repo.commit({"src/api.py": "api v2"}, date=T2, committer_date=T4)
    repo.commit({"docs/api.md": "doc v2"}, date=T3, committer_date=T4)

    assert fd.check().ok


def test_change_within_the_same_second_still_flags(repo: GitRepo, fd: FreshdagsApi) -> None:
    """git dates have one-second resolution; scripts and agents commit faster than that."""
    setup_api_doc(repo, fd)
    repo.commit({"src/api.py": "api v2"}, date=T1)

    assert fd.check().drifted_docs == ["docs/api.md"]


def test_doc_update_within_the_same_second_resolves(repo: GitRepo, fd: FreshdagsApi) -> None:
    setup_api_doc(repo, fd)
    repo.commit({"src/api.py": "api v2"}, date=T2)
    repo.commit({"docs/api.md": "doc v2"}, date=T2)

    assert fd.check().ok


def test_check_at_revision(repo: GitRepo, fd: FreshdagsApi) -> None:
    clean = setup_api_doc(repo, fd)
    repo.commit({"src/api.py": "api v2"}, date=T2)

    assert fd.check(clean).ok
    assert not fd.check("HEAD").ok


def test_check_reports_every_drifted_edge(repo: GitRepo, fd: FreshdagsApi) -> None:
    for path in ("docs/a.md", "docs/b.md", "src/x.py", "src/y.py"):
        repo.write(path, "v1")
    fd.add("docs/a.md", "src/x.py", "src/y.py")
    fd.add("docs/b.md", "src/y.py")
    repo.commit(date=T1)
    repo.commit({"src/x.py": "v2", "src/y.py": "v2"}, date=T2)

    report = fd.check()

    assert [(d.doc, d.source) for d in report.drift] == [
        ("docs/a.md", "src/x.py"),
        ("docs/a.md", "src/y.py"),
        ("docs/b.md", "src/y.py"),
    ]
    assert report.docs_checked == 2


def test_check_gives_same_report_in_small_batches(repo: GitRepo, fd: Freshdags) -> None:
    """Large graphs query git in batches of paths; batching must not change the result."""
    for path in ("docs/a.md", "docs/b.md", "src/x.py", "src/y.py"):
        repo.write(path, "v1")
    fd.add("docs/a.md", "src/x.py", "src/y.py")
    fd.add("docs/b.md", "docs/a.md")
    repo.commit(date=T1)
    repo.commit({"src/x.py": "v2"}, date=T2)
    repo.commit({"docs/a.md": "v2", "src/y.py": "v2"}, date=T3)
    in_one_call = fd.check()

    fd.log_batch_size = 1

    assert fd.check() == in_one_call
    assert in_one_call.drifted_docs == ["docs/b.md"]


def test_change_ripples_through_doc_chain(repo: GitRepo, fd: FreshdagsApi) -> None:
    """guide.md depends on api.md; a real edit to api.md flags guide.md."""
    setup_api_doc(repo, fd)
    repo.write("docs/guide.md", "guide v1")
    fd.add("docs/guide.md", "docs/api.md")
    repo.commit(date=T1)
    repo.commit({"docs/api.md": "doc v2"}, date=T2)

    assert fd.check().drifted_docs == ["docs/guide.md"]


def test_auto_resolve_off_ignores_doc_commits(repo: GitRepo, fd: FreshdagsApi) -> None:
    setup_api_doc(repo, fd)
    repo.set_setting("auto-resolve", "off")
    repo.commit({"src/api.py": "api v2"}, date=T2)
    repo.commit({"docs/api.md": "typo fix"}, date=T3)

    assert fd.check().drifted_docs == ["docs/api.md"]


def test_auto_flag_off_ignores_source_commits(
    repo: GitRepo, fd: FreshdagsApi, time_machine: TimeMachineFixture
) -> None:
    setup_api_doc(repo, fd)
    repo.set_setting("auto-flag", "off")
    repo.commit({"src/api.py": "refactor"}, date=T2)

    assert fd.check().ok

    time_machine.move_to(T3, tick=False)
    fd.flag("src/api.py")
    assert fd.check().drifted_docs == ["docs/api.md"]


def test_doc_created_after_source_change_is_fresh(repo: GitRepo, fd: FreshdagsApi) -> None:
    """Creating a doc counts as resolving it, in every mode."""
    repo.commit({"src/api.py": "api v1"}, date=T1)
    repo.commit({"src/api.py": "api v2"}, date=T2)
    repo.write("docs/api.md", "doc v1")
    fd.add("docs/api.md", "src/api.py")
    repo.set_setting("auto-resolve", "off")
    repo.commit(date=T3)

    assert fd.check().ok


def test_external_doc_flagged_by_repo_change(
    repo: GitRepo, fd: FreshdagsApi, time_machine: TimeMachineFixture
) -> None:
    """An external page (a wiki, say) has no commits, so only `resolve` clears it."""
    repo.write("src/api.py", "api v1")
    fd.add("ext:wiki-api", "src/api.py")
    repo.commit(date=T1)
    time_machine.move_to(T2, tick=False)
    fd.resolve("ext:wiki-api")
    repo.commit({"src/api.py": "api v2"}, date=T3)

    assert fd.check().drifted_docs == ["ext:wiki-api"]


def test_external_source_without_flag_never_drifts(repo: GitRepo, fd: FreshdagsApi) -> None:
    repo.write("docs/api.md", "doc v1")
    fd.add("docs/api.md", "ext:stripe-api")
    repo.commit(date=T1)

    assert fd.check().ok
