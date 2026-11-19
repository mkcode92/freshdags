"""`check`: a doc drifts when one of its sources changed after the doc was last resolved.

Exit codes: 0 no drift, 1 drift found, 2 usage or graph error.

Default settings are `flag: on-commit` and `resolve: on-commit`, so a commit to a source
counts as a change and a commit to a doc counts as resolving it. A doc also counts as up to
date from the commit that created it. Times are commit author dates, which survive rebases.
"""

from conftest import Cli, Clock, GitRepo

T1 = "2026-01-01T10:00:00+00:00"
T2 = "2026-01-02T10:00:00+00:00"
T3 = "2026-01-03T10:00:00+00:00"
T4 = "2026-01-04T10:00:00+00:00"


def setup_api_doc(repo: GitRepo, cli: Cli) -> None:
    """docs/api.md depends on src/api.py, both committed at T1."""
    repo.write("docs/api.md", "doc v1")
    repo.write("src/api.py", "api v1")
    assert cli("add", "docs/api.md", "src/api.py").exit_code == 0
    repo.commit(date=T1)


def test_no_drift_when_committed_together(repo: GitRepo, cli: Cli) -> None:
    setup_api_doc(repo, cli)

    result = cli("check")

    assert result.exit_code == 0, result.output


def test_source_change_flags_doc(repo: GitRepo, cli: Cli) -> None:
    setup_api_doc(repo, cli)
    repo.commit({"src/api.py": "api v2"}, date=T2)

    result = cli("check")

    assert result.exit_code == 1
    assert "docs/api.md" in result.output
    assert "src/api.py" in result.output


def test_doc_updated_in_later_commit_resolves(repo: GitRepo, cli: Cli) -> None:
    setup_api_doc(repo, cli)
    repo.commit({"src/api.py": "api v2"}, date=T2)
    repo.commit({"docs/api.md": "doc v2"}, date=T3)

    assert cli("check").exit_code == 0


def test_unrelated_change_does_not_flag(repo: GitRepo, cli: Cli) -> None:
    setup_api_doc(repo, cli)
    repo.commit({"src/internal.py": "impl detail"}, date=T2)

    assert cli("check").exit_code == 0


def test_rebase_does_not_flag(repo: GitRepo, cli: Cli) -> None:
    """A rebase rewrites committer dates; author dates keep the real order."""
    setup_api_doc(repo, cli)
    repo.commit({"src/api.py": "api v2"}, date=T2, committer_date=T4)
    repo.commit({"docs/api.md": "doc v2"}, date=T3, committer_date=T4)

    assert cli("check").exit_code == 0


def test_check_at_revision(repo: GitRepo, cli: Cli) -> None:
    setup_api_doc(repo, cli)
    clean = repo.git("rev-parse", "HEAD")
    repo.commit({"src/api.py": "api v2"}, date=T2)

    assert cli("check", clean).exit_code == 0
    assert cli("check", "HEAD").exit_code == 1


def test_check_reports_every_drifted_edge(repo: GitRepo, cli: Cli) -> None:
    for path in ("docs/a.md", "docs/b.md", "src/x.py", "src/y.py"):
        repo.write(path, "v1")
    cli("add", "docs/a.md", "src/x.py", "src/y.py")
    cli("add", "docs/b.md", "src/y.py")
    repo.commit(date=T1)
    repo.commit({"src/x.py": "v2", "src/y.py": "v2"}, date=T2)

    output = cli("check").output

    assert output.count("docs/a.md") >= 2
    assert "docs/b.md" in output


def test_change_ripples_through_doc_chain(repo: GitRepo, cli: Cli) -> None:
    """guide.md depends on api.md; a real edit to api.md flags guide.md."""
    setup_api_doc(repo, cli)
    repo.write("docs/guide.md", "guide v1")
    cli("add", "docs/guide.md", "docs/api.md")
    repo.commit(date=T1)
    repo.commit({"docs/api.md": "doc v2"}, date=T2)

    result = cli("check")

    assert result.exit_code == 1
    assert "docs/guide.md" in result.output


def test_manual_resolve_ignores_doc_commits(repo: GitRepo, cli: Cli) -> None:
    setup_api_doc(repo, cli)
    repo.set_setting("resolve", "manual")
    repo.commit({"src/api.py": "api v2"}, date=T2)
    repo.commit({"docs/api.md": "typo fix"}, date=T3)

    assert cli("check").exit_code == 1


def test_manual_flag_ignores_source_commits(repo: GitRepo, cli: Cli, clock: Clock) -> None:
    setup_api_doc(repo, cli)
    repo.set_setting("flag", "manual")
    repo.commit({"src/api.py": "refactor"}, date=T2)

    assert cli("check").exit_code == 0

    clock(T3)
    assert cli("flag", "src/api.py").exit_code == 0
    assert cli("check").exit_code == 1


def test_external_doc_flagged_by_repo_change(repo: GitRepo, cli: Cli, clock: Clock) -> None:
    """An external page (a wiki, say) has no commits, so only `resolve` clears it."""
    repo.write("src/api.py", "api v1")
    cli("add", "ext:wiki-api", "src/api.py")
    repo.commit(date=T1)
    clock(T2)
    cli("resolve", "ext:wiki-api")
    repo.commit({"src/api.py": "api v2"}, date=T3)

    result = cli("check")

    assert result.exit_code == 1
    assert "ext:wiki-api" in result.output


def test_doc_created_after_source_change_is_fresh(repo: GitRepo, cli: Cli) -> None:
    """Creating a doc counts as resolving it, in every mode."""
    repo.commit({"src/api.py": "api v1"}, date=T1)
    repo.commit({"src/api.py": "api v2"}, date=T2)
    repo.write("docs/api.md", "doc v1")
    cli("add", "docs/api.md", "src/api.py")
    repo.commit(date=T3)

    assert cli("check").exit_code == 0


def test_external_source_without_flag_never_drifts(repo: GitRepo, cli: Cli) -> None:
    repo.write("docs/api.md", "doc v1")
    cli("add", "docs/api.md", "ext:stripe-api")
    repo.commit(date=T1)

    assert cli("check").exit_code == 0
