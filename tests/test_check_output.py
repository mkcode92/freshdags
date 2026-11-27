"""What `check` reports about each drift, and how it is rendered for humans.

A doc's "fresh commit" is the commit at which it was last up to date: the commit that
created it, its last commit (when commits resolve) or the commit recorded by `resolve`,
whichever is latest. The review hint diffs the source from there.
"""

from datetime import datetime

from support import T1, T2, T3, T4, GitRepo, setup_api_doc
from time_machine import TimeMachineFixture

from freshdags.api import FreshdagsApi
from freshdags.models import CheckReport, Drift
from freshdags.render import render_check

# --- report contents -----------------------------------------------------------------------


def test_report_describes_drift(repo: GitRepo, fd: FreshdagsApi) -> None:
    fresh = setup_api_doc(repo, fd)
    changed = repo.commit({"src/api.py": "api v2"}, date=T2)

    report = fd.check()

    assert report.drift == [
        Drift(
            doc="docs/api.md",
            source="src/api.py",
            doc_fresh_at=datetime.fromisoformat(T1),
            doc_fresh_commit=fresh,
            source_changed_at=datetime.fromisoformat(T2),
            source_changed_commit=changed,
            note=None,
        )
    ]


def test_fresh_commit_is_last_resolve(
    repo: GitRepo, fd: FreshdagsApi, time_machine: TimeMachineFixture
) -> None:
    setup_api_doc(repo, fd)
    resolved_at = repo.commit({"src/api.py": "api v2"}, date=T2)
    time_machine.move_to(T3, tick=False)
    fd.resolve("docs/api.md")
    repo.commit({"src/api.py": "api v3"}, date=T4)

    assert fd.check().drift[0].doc_fresh_commit == resolved_at


def test_flag_note_is_reported(
    repo: GitRepo, fd: FreshdagsApi, time_machine: TimeMachineFixture
) -> None:
    repo.write("docs/api.md", "doc v1")
    fd.add("docs/api.md", "ext:stripe-api")
    repo.commit(date=T1)
    time_machine.move_to(T2, tick=False)
    fd.flag("ext:stripe-api", note="API v2 released")

    drift = fd.check().drift[0]

    assert drift.note == "API v2 released"
    assert drift.source_changed_commit is None
    assert drift.flagged


def test_uncommitted_save_is_not_a_flag(repo: GitRepo, fd: FreshdagsApi) -> None:
    setup_api_doc(repo, fd)
    repo.set_setting("auto-flag", "on-change")
    repo.save("src/api.py", "api v2", at=T2)

    drift = fd.check().drift[0]

    assert drift.source_changed_commit is None
    assert not drift.flagged


def test_report_remembers_revision(repo: GitRepo, fd: FreshdagsApi) -> None:
    sha = setup_api_doc(repo, fd)

    assert fd.check().rev is None
    assert fd.check(sha).rev == sha


# --- rendering -----------------------------------------------------------------------------

FRESH = "a" * 40
CHANGED = "b" * 40


def drift(source: str = "src/api.py", **overrides: object) -> Drift:
    values: dict[str, object] = {
        "doc": "docs/api.md",
        "source": source,
        "doc_fresh_at": datetime.fromisoformat(T1),
        "doc_fresh_commit": FRESH,
        "source_changed_at": datetime.fromisoformat(T2),
        "source_changed_commit": CHANGED,
        "note": None,
    }
    return Drift.model_validate(values | overrides)


def test_render_names_diff_and_next_step() -> None:
    report = CheckReport(rev=None, docs_checked=1, drift=[drift()])

    text = render_check(report)

    assert "git diff aaaaaaa..HEAD -- src/api.py" in text
    assert "then: update docs/api.md where the change made it wrong," in text
    assert 'only if it is still correct: freshdags resolve docs/api.md --note "why"' in text


def test_render_forbids_resolving_to_pass() -> None:
    text = render_check(CheckReport(rev=None, docs_checked=1, drift=[drift()]))

    assert text.endswith("Never resolve just to make this check, a hook or CI pass.")


def test_render_diff_ends_at_checked_revision() -> None:
    report = CheckReport(rev="v1.2", docs_checked=1, drift=[drift()])

    assert "git diff aaaaaaa..v1.2 -- src/api.py" in render_check(report)


def test_render_external_source_shows_note_instead_of_diff() -> None:
    flagged = drift(
        source="ext:stripe-api", source_changed_commit=None, note="API v2 released", flagged=True
    )
    report = CheckReport(rev=None, docs_checked=1, drift=[flagged])

    text = render_check(report)

    assert "ext:stripe-api flagged: API v2 released" in text
    assert "git diff" not in text


def test_render_uncommitted_save_diffs_working_tree() -> None:
    saved = drift(source_changed_commit=None)

    text = render_check(CheckReport(rev=None, docs_checked=1, drift=[saved]))

    assert "src/api.py changed since aaaaaaa (uncommitted)" in text
    assert "git diff aaaaaaa -- src/api.py" in text
    assert "flagged" not in text


def test_render_uncommitted_save_after_saved_doc_diffs_against_head() -> None:
    saved = drift(source_changed_commit=None, doc_fresh_commit=None)

    text = render_check(CheckReport(rev=None, docs_checked=1, drift=[saved]))

    assert "src/api.py changed (uncommitted)" in text
    assert "git diff HEAD -- src/api.py" in text
    assert "flagged" not in text


def test_render_summary_when_fresh() -> None:
    text = render_check(CheckReport(rev=None, docs_checked=1, drift=[]))

    assert "🦡" in text
    assert "1 doc is fresh" in text


def test_render_summary_counts_drifted_docs() -> None:
    report = CheckReport(rev=None, docs_checked=3, drift=[drift(), drift(source="src/b.py")])

    assert "🦡 1 doc may have drifted" in render_check(report)
