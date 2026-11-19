"""`check` output: tell the reader what changed, where to look, and how to clear the flag.

A doc's "fresh commit" is the commit at which it was last up to date: the commit that
created it, its last commit (when commits resolve) or the commit recorded by `resolve`,
whichever is latest. The review hint diffs the source from there.
"""

import json

from conftest import Cli, Clock, GitRepo

T1 = "2026-01-01T10:00:00+00:00"
T2 = "2026-01-02T10:00:00+00:00"
T3 = "2026-01-03T10:00:00+00:00"
T4 = "2026-01-04T10:00:00+00:00"


def setup_api_doc(repo: GitRepo, cli: Cli) -> str:
    """docs/api.md depends on src/api.py, both committed at T1. Returns that commit's sha."""
    repo.write("docs/api.md", "doc v1")
    repo.write("src/api.py", "api v1")
    assert cli("add", "docs/api.md", "src/api.py").exit_code == 0
    return repo.commit(date=T1)


def test_text_output_names_diff_and_next_step(repo: GitRepo, cli: Cli) -> None:
    fresh = setup_api_doc(repo, cli)
    repo.commit({"src/api.py": "api v2"}, date=T2)

    output = cli("check").output

    assert f"git diff {repo.short(fresh)}..HEAD -- src/api.py" in output
    assert "freshdags resolve docs/api.md" in output


def test_diff_starts_at_last_resolve(repo: GitRepo, cli: Cli, clock: Clock) -> None:
    setup_api_doc(repo, cli)
    resolved_at = repo.commit({"src/api.py": "api v2"}, date=T2)
    clock(T3)
    cli("resolve", "docs/api.md")
    repo.commit({"src/api.py": "api v3"}, date=T4)

    output = cli("check").output

    assert f"git diff {repo.short(resolved_at)}..HEAD -- src/api.py" in output


def test_diff_at_revision_ends_at_that_revision(repo: GitRepo, cli: Cli) -> None:
    fresh = setup_api_doc(repo, cli)
    changed = repo.commit({"src/api.py": "api v2"}, date=T2)
    repo.commit({"unrelated.txt": "x"}, date=T3)

    output = cli("check", changed).output

    assert f"git diff {repo.short(fresh)}..{repo.short(changed)} -- src/api.py" in output


def test_external_source_shows_flag_note(repo: GitRepo, cli: Cli, clock: Clock) -> None:
    repo.write("docs/api.md", "doc v1")
    cli("add", "docs/api.md", "ext:stripe-api")
    repo.commit(date=T1)
    clock(T2)
    cli("flag", "ext:stripe-api", "--note", "API v2 released")

    output = cli("check").output

    assert "ext:stripe-api" in output
    assert "API v2 released" in output
    assert "git diff" not in output


def test_summary_when_fresh(repo: GitRepo, cli: Cli) -> None:
    setup_api_doc(repo, cli)

    output = cli("check").output

    assert "🦡" in output
    assert "1 doc is fresh" in output


def test_summary_counts_drifted_docs(repo: GitRepo, cli: Cli) -> None:
    setup_api_doc(repo, cli)
    repo.commit({"src/api.py": "api v2"}, date=T2)

    output = cli("check").output

    assert "🦡 1 doc drifted" in output


def test_json_output_has_no_badger(repo: GitRepo, cli: Cli) -> None:
    setup_api_doc(repo, cli)
    repo.commit({"src/api.py": "api v2"}, date=T2)

    assert "🦡" not in cli("check", "--json").output


def test_json_output(repo: GitRepo, cli: Cli) -> None:
    fresh = setup_api_doc(repo, cli)
    changed = repo.commit({"src/api.py": "api v2"}, date=T2)

    result = cli("check", "--json")

    assert result.exit_code == 1
    report = json.loads(result.output)
    assert report["drift"] == [
        {
            "doc": "docs/api.md",
            "source": "src/api.py",
            "doc_fresh_at": "2026-01-01T10:00:00Z",
            "doc_fresh_commit": fresh,
            "source_changed_at": "2026-01-02T10:00:00Z",
            "source_changed_commit": changed,
            "note": None,
        }
    ]


def test_json_output_without_drift(repo: GitRepo, cli: Cli) -> None:
    setup_api_doc(repo, cli)

    result = cli("check", "--json")

    assert result.exit_code == 0
    assert json.loads(result.output) == {"drift": []}
