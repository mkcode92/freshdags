"""`on-change` mode: uncommitted saves count too, using the file's modification time.

`on-change` includes everything `on-commit` does. It only applies to `check` without a
revision; `check(rev)` evaluates committed history only.
"""

from support import T1, T2, T3, Clock, GitRepo, setup_api_doc

from freshdags.api import FreshdagsApi


def setup_modes(repo: GitRepo, fd: FreshdagsApi, *, flag: str, resolve: str) -> None:
    setup_api_doc(repo, fd)
    repo.set_setting("flag", flag)
    repo.set_setting("resolve", resolve)
    repo.commit(date=T1)


def add_readme_over_api_doc(repo: GitRepo, fd: FreshdagsApi) -> None:
    repo.write("README.md", "overview v1")
    fd.add("README.md", "docs/api.md")
    repo.commit(date=T1)


def test_on_commit_ignores_unsaved_source_change(repo: GitRepo, fd: FreshdagsApi) -> None:
    setup_modes(repo, fd, flag="on-commit", resolve="on-commit")
    repo.save("src/api.py", "api v2", at=T2)

    assert fd.check().ok


def test_on_change_flags_uncommitted_source_change(repo: GitRepo, fd: FreshdagsApi) -> None:
    setup_modes(repo, fd, flag="on-change", resolve="on-commit")
    repo.save("src/api.py", "api v2", at=T2)

    report = fd.check()

    assert report.drifted_docs == ["docs/api.md"]
    assert report.drift[0].source_changed_commit is None


def test_on_change_still_counts_commits(repo: GitRepo, fd: FreshdagsApi) -> None:
    setup_modes(repo, fd, flag="on-change", resolve="on-change")
    repo.commit({"src/api.py": "api v2"}, date=T2)

    assert not fd.check().ok


def test_on_change_resolves_by_saving_doc(repo: GitRepo, fd: FreshdagsApi) -> None:
    setup_modes(repo, fd, flag="on-change", resolve="on-change")
    repo.save("src/api.py", "api v2", at=T2)
    repo.save("docs/api.md", "doc v2", at=T3)

    assert fd.check().ok


def test_on_change_ignores_mtime_of_unmodified_files(repo: GitRepo, fd: FreshdagsApi) -> None:
    """A checkout or touch changes mtimes without changing content; that is not a change."""
    setup_modes(repo, fd, flag="on-change", resolve="on-change")
    repo.save("src/api.py", "api v1", at=T3)

    assert fd.check().ok


def test_on_change_counts_new_untracked_source(repo: GitRepo, fd: FreshdagsApi) -> None:
    setup_modes(repo, fd, flag="on-change", resolve="on-change")
    repo.save("src/extra.py", "new", at=T2)
    fd.add("docs/api.md", "src/extra.py")

    assert fd.check().drifted_docs == ["docs/api.md"]


def test_saving_child_doc_flags_parent(repo: GitRepo, fd: FreshdagsApi) -> None:
    """Resolving by saving is a real change, so it ripples to dependents."""
    setup_modes(repo, fd, flag="on-change", resolve="on-change")
    add_readme_over_api_doc(repo, fd)
    repo.save("src/api.py", "api v2", at=T2)
    repo.save("docs/api.md", "doc v2", at=T3)

    assert fd.check().drifted_docs == ["README.md"]


def test_resolve_command_does_not_flag_parent(
    repo: GitRepo, fd: FreshdagsApi, clock: Clock
) -> None:
    setup_modes(repo, fd, flag="on-change", resolve="on-change")
    add_readme_over_api_doc(repo, fd)
    repo.save("src/api.py", "api v2", at=T2)
    clock.set(T3)

    fd.resolve("docs/api.md")

    assert fd.check().ok


def test_check_at_revision_ignores_working_tree(repo: GitRepo, fd: FreshdagsApi) -> None:
    setup_modes(repo, fd, flag="on-change", resolve="on-change")
    repo.save("src/api.py", "api v2", at=T2)

    assert fd.check("HEAD").ok
