"""`resolve` and `flag`: recording that a doc is drift-free, or that a source changed."""

from conftest import Cli, Clock, GitRepo

T1 = "2026-01-01T10:00:00+00:00"
T2 = "2026-01-02T10:00:00+00:00"
T3 = "2026-01-03T10:00:00+00:00"


def setup_api_doc(repo: GitRepo, cli: Cli) -> None:
    repo.write("docs/api.md", "doc v1")
    repo.write("src/api.py", "api v1")
    assert cli("add", "docs/api.md", "src/api.py").exit_code == 0
    repo.commit(date=T1)


def test_resolve_clears_drift(repo: GitRepo, cli: Cli, clock: Clock) -> None:
    setup_api_doc(repo, cli)
    repo.commit({"src/api.py": "api v2"}, date=T2)
    clock(T3)

    assert cli("resolve", "docs/api.md").exit_code == 0
    assert cli("check").exit_code == 0


def test_resolve_records_who_when_and_commit(repo: GitRepo, cli: Cli, clock: Clock) -> None:
    setup_api_doc(repo, cli)
    head = repo.git("rev-parse", "HEAD")
    clock(T2)

    cli("resolve", "docs/api.md")

    record = repo.graph()["nodes"]["docs/api.md"]["resolved"]
    assert record["at"] == "2026-01-02T10:00:00Z"
    assert record["by"] == "Test"
    assert record["commit"] == head


def test_resolve_is_overtaken_by_later_source_change(repo: GitRepo, cli: Cli, clock: Clock) -> None:
    setup_api_doc(repo, cli)
    clock(T2)
    cli("resolve", "docs/api.md")
    repo.commit({"src/api.py": "api v2"}, date=T3)

    assert cli("check").exit_code == 1


def test_resolve_several_docs(repo: GitRepo, cli: Cli, clock: Clock) -> None:
    for path in ("docs/a.md", "docs/b.md", "src/api.py"):
        repo.write(path, "v1")
    cli("add", "docs/a.md", "src/api.py")
    cli("add", "docs/b.md", "src/api.py")
    repo.commit(date=T1)
    repo.commit({"src/api.py": "v2"}, date=T2)
    clock(T3)

    assert cli("resolve", "docs/a.md", "docs/b.md").exit_code == 0
    assert cli("check").exit_code == 0


def test_resolve_from_source_resolves_all_dependents(repo: GitRepo, cli: Cli, clock: Clock) -> None:
    """A minor change: resolve every doc flagged because of src/api.py at once."""
    for path in ("docs/a.md", "docs/b.md", "src/api.py", "src/other.py"):
        repo.write(path, "v1")
    cli("add", "docs/a.md", "src/api.py")
    cli("add", "docs/b.md", "src/api.py", "src/other.py")
    repo.commit(date=T1)
    repo.commit({"src/api.py": "v2"}, date=T2)
    repo.commit({"src/other.py": "v2"}, date=T2)
    clock(T3)

    assert cli("resolve", "--from", "src/api.py").exit_code == 0

    assert cli("check").exit_code == 0


def test_resolve_from_skips_docs_that_were_not_flagged(
    repo: GitRepo, cli: Cli, clock: Clock
) -> None:
    """Only docs drifted because of the source get a resolve record."""
    for path in ("docs/a.md", "docs/b.md", "src/api.py"):
        repo.write(path, "v1")
    cli("add", "docs/a.md", "src/api.py")
    cli("add", "docs/b.md", "src/api.py")
    repo.set_setting("resolve", "on-commit")
    repo.commit(date=T1)
    repo.commit({"src/api.py": "v2"}, date=T2)
    repo.commit({"docs/b.md": "v2"}, date=T3)
    clock(T3)

    cli("resolve", "--from", "src/api.py")

    nodes = repo.graph()["nodes"]
    assert "resolved" in nodes["docs/a.md"]
    assert "resolved" not in nodes["docs/b.md"]


def test_resolve_does_not_ripple_to_dependents(repo: GitRepo, cli: Cli, clock: Clock) -> None:
    """Resolving api.md means its content is still right, so guide.md stays fine."""
    setup_api_doc(repo, cli)
    repo.write("docs/guide.md", "guide v1")
    cli("add", "docs/guide.md", "docs/api.md")
    repo.commit(date=T1)
    repo.commit({"src/api.py": "api v2"}, date=T2)
    clock(T3)

    cli("resolve", "docs/api.md")

    assert cli("check").exit_code == 0


def test_resolve_unknown_node_fails(repo: GitRepo, cli: Cli) -> None:
    setup_api_doc(repo, cli)

    result = cli("resolve", "docs/nope.md")

    assert result.exit_code == 2
    assert "docs/nope.md" in result.output


def test_flag_external_source_flags_dependents(repo: GitRepo, cli: Cli, clock: Clock) -> None:
    repo.write("docs/api.md", "doc v1")
    cli("add", "docs/api.md", "ext:stripe-api")
    repo.commit(date=T1)
    clock(T2)

    assert cli("flag", "ext:stripe-api", "--note", "API v2 released").exit_code == 0

    result = cli("check")
    assert result.exit_code == 1
    assert "docs/api.md" in result.output
    record = repo.graph()["nodes"]["ext:stripe-api"]["flagged"]
    assert record == {"at": "2026-01-02T10:00:00Z", "by": "Test", "note": "API v2 released"}


def test_flag_then_resolve(repo: GitRepo, cli: Cli, clock: Clock) -> None:
    repo.write("docs/api.md", "doc v1")
    cli("add", "docs/api.md", "ext:stripe-api")
    repo.commit(date=T1)
    clock(T2)
    cli("flag", "ext:stripe-api")
    clock(T3)

    cli("resolve", "docs/api.md")

    assert cli("check").exit_code == 0


def test_flag_local_source_in_on_commit_mode(repo: GitRepo, cli: Cli, clock: Clock) -> None:
    """Behaviour changed without touching the interface file: flag it by hand."""
    setup_api_doc(repo, cli)
    clock(T2)

    cli("flag", "src/api.py")

    assert cli("check").exit_code == 1
