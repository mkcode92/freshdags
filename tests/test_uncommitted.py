"""`check(uncommitted=True)`: what a pre-commit hook sees.

The hook runs before the commit exists, so uncommitted changes count as one commit made now.
"""

import pytest
from support import T1, T2, T3, GitRepo, setup_api_doc

from freshdags.api import FreshdagsApi
from freshdags.errors import FreshdagsError


def test_uncommitted_source_change_drifts(repo: GitRepo, fd: FreshdagsApi) -> None:
    setup_api_doc(repo, fd)
    repo.save("src/api.py", "api v2", at=T2)

    assert fd.check().ok
    assert fd.check(uncommitted=True).drifted_docs == ["docs/api.md"]


def test_doc_changed_in_the_same_commit_is_fresh(repo: GitRepo, fd: FreshdagsApi) -> None:
    """Both files go into one commit, so it does not matter which was saved first."""
    setup_api_doc(repo, fd)
    repo.save("docs/api.md", "doc v2", at=T2)
    repo.save("src/api.py", "api v2", at=T3)

    assert fd.check(uncommitted=True).ok


def test_uncommitted_doc_change_flags_its_dependents(repo: GitRepo, fd: FreshdagsApi) -> None:
    setup_api_doc(repo, fd)
    repo.write("README.md", "overview v1")
    fd.add("README.md", "docs/api.md")
    repo.commit(date=T1)
    repo.save("docs/api.md", "doc v2", at=T2)

    assert fd.check(uncommitted=True).drifted_docs == ["README.md"]


def test_auto_flag_off_stays_off(repo: GitRepo, fd: FreshdagsApi) -> None:
    setup_api_doc(repo, fd)
    repo.set_setting("auto-flag", "off")
    repo.commit(date=T1)
    repo.save("src/api.py", "api v2", at=T2)

    assert fd.check(uncommitted=True).ok


def test_uncommitted_cannot_be_combined_with_revision(repo: GitRepo, fd: FreshdagsApi) -> None:
    sha = setup_api_doc(repo, fd)

    with pytest.raises(FreshdagsError, match="uncommitted"):
        fd.check(sha, uncommitted=True)
