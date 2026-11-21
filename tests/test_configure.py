"""`configure`: reading and changing the settings in freshdags.json."""

from support import GitRepo

from freshdags.api import FreshdagsApi
from freshdags.models import Mode, Settings


def test_configure_without_arguments_reads_defaults(repo: GitRepo, fd: FreshdagsApi) -> None:
    assert fd.configure() == Settings(auto_flag=Mode.ON_COMMIT, auto_resolve=Mode.ON_COMMIT)


def test_configure_creates_graph_file(repo: GitRepo, fd: FreshdagsApi) -> None:
    fd.configure()

    assert repo.graph()["settings"] == {"auto-flag": "on-commit", "auto-resolve": "on-commit"}


def test_configure_changes_only_the_given_setting(repo: GitRepo, fd: FreshdagsApi) -> None:
    settings = fd.configure(auto_resolve=Mode.OFF)

    assert settings == Settings(auto_flag=Mode.ON_COMMIT, auto_resolve=Mode.OFF)
    assert repo.graph()["settings"] == {"auto-flag": "on-commit", "auto-resolve": "off"}


def test_configure_keeps_the_graph(repo: GitRepo, fd: FreshdagsApi) -> None:
    repo.write("docs/api.md")
    repo.write("src/api.py")
    fd.add("docs/api.md", "src/api.py")

    fd.configure(auto_flag=Mode.ON_CHANGE, auto_resolve=Mode.ON_CHANGE)

    graph = repo.graph()
    assert graph["settings"] == {"auto-flag": "on-change", "auto-resolve": "on-change"}
    assert graph["nodes"]["docs/api.md"]["depends_on"] == ["src/api.py"]


def test_reading_settings_does_not_rewrite_the_file(repo: GitRepo, fd: FreshdagsApi) -> None:
    fd.configure(auto_flag=Mode.OFF)
    before = repo.graph_text()

    fd.configure()

    assert repo.graph_text() == before
