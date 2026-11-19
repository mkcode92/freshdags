"""`on-change` mode: uncommitted saves count too, using the file's modification time.

`on-change` includes everything `on-commit` does. It only applies to `check` without a
revision; `check REV` evaluates committed history only.
"""

from conftest import Cli, Clock, GitRepo

T1 = "2026-01-01T10:00:00+00:00"
T2 = "2026-01-02T10:00:00+00:00"
T3 = "2026-01-03T10:00:00+00:00"


def setup_api_doc(repo: GitRepo, cli: Cli, *, flag: str, resolve: str) -> None:
    repo.write("docs/api.md", "doc v1")
    repo.write("src/api.py", "api v1")
    assert cli("add", "docs/api.md", "src/api.py").exit_code == 0
    repo.set_setting("flag", flag)
    repo.set_setting("resolve", resolve)
    repo.commit(date=T1)


def test_on_commit_ignores_unsaved_source_change(repo: GitRepo, cli: Cli) -> None:
    setup_api_doc(repo, cli, flag="on-commit", resolve="on-commit")
    repo.save("src/api.py", "api v2", at=T2)

    assert cli("check").exit_code == 0


def test_on_change_flags_uncommitted_source_change(repo: GitRepo, cli: Cli) -> None:
    setup_api_doc(repo, cli, flag="on-change", resolve="on-commit")
    repo.save("src/api.py", "api v2", at=T2)

    result = cli("check")

    assert result.exit_code == 1
    assert "docs/api.md" in result.output


def test_on_change_still_counts_commits(repo: GitRepo, cli: Cli) -> None:
    setup_api_doc(repo, cli, flag="on-change", resolve="on-change")
    repo.commit({"src/api.py": "api v2"}, date=T2)

    assert cli("check").exit_code == 1


def test_on_change_resolves_by_saving_doc(repo: GitRepo, cli: Cli) -> None:
    setup_api_doc(repo, cli, flag="on-change", resolve="on-change")
    repo.save("src/api.py", "api v2", at=T2)
    repo.save("docs/api.md", "doc v2", at=T3)

    assert cli("check").exit_code == 0


def test_on_change_ignores_mtime_of_unmodified_files(repo: GitRepo, cli: Cli) -> None:
    """A checkout or touch changes mtimes without changing content; that is not a change."""
    setup_api_doc(repo, cli, flag="on-change", resolve="on-change")
    repo.save("src/api.py", "api v1", at=T3)

    assert cli("check").exit_code == 0


def test_on_change_counts_new_untracked_source(repo: GitRepo, cli: Cli) -> None:
    setup_api_doc(repo, cli, flag="on-change", resolve="on-change")
    repo.save("src/extra.py", "new", at=T2)
    assert cli("add", "docs/api.md", "src/extra.py").exit_code == 0

    assert cli("check").exit_code == 1


def test_saving_child_doc_flags_parent(repo: GitRepo, cli: Cli) -> None:
    """Resolving by saving is a real change, so it ripples to dependents."""
    setup_api_doc(repo, cli, flag="on-change", resolve="on-change")
    repo.write("README.md", "overview v1")
    cli("add", "README.md", "docs/api.md")
    repo.commit(date=T1)
    repo.save("src/api.py", "api v2", at=T2)
    repo.save("docs/api.md", "doc v2", at=T3)

    result = cli("check")

    assert result.exit_code == 1
    assert "README.md" in result.output
    assert "docs/api.md" in result.output


def test_resolve_command_does_not_flag_parent(repo: GitRepo, cli: Cli, clock: Clock) -> None:
    setup_api_doc(repo, cli, flag="on-change", resolve="on-change")
    repo.write("README.md", "overview v1")
    cli("add", "README.md", "docs/api.md")
    repo.commit(date=T1)
    repo.save("src/api.py", "api v2", at=T2)
    clock(T3)

    cli("resolve", "docs/api.md")

    assert cli("check").exit_code == 0


def test_check_at_revision_ignores_working_tree(repo: GitRepo, cli: Cli) -> None:
    setup_api_doc(repo, cli, flag="on-change", resolve="on-change")
    repo.save("src/api.py", "api v2", at=T2)

    assert cli("check", "HEAD").exit_code == 0
