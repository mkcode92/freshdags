"""`add`, `rm` and `show`: maintaining the dependency graph in freshdags.json."""

from conftest import Cli, GitRepo


def test_add_creates_graph_file_with_defaults(repo: GitRepo, cli: Cli) -> None:
    repo.write("docs/api.md")
    repo.write("src/api.py")

    result = cli("add", "docs/api.md", "src/api.py")

    assert result.exit_code == 0, result.output
    graph = repo.graph()
    assert graph["version"] == 1
    assert graph["settings"] == {"flag": "on-commit", "resolve": "on-commit"}
    assert graph["nodes"]["docs/api.md"]["depends_on"] == ["src/api.py"]
    assert "src/api.py" in graph["nodes"]


def test_add_several_sources_keeps_them_sorted(repo: GitRepo, cli: Cli) -> None:
    for path in ("docs/api.md", "src/b.py", "src/a.py"):
        repo.write(path)

    assert cli("add", "docs/api.md", "src/b.py", "src/a.py").exit_code == 0

    assert repo.graph()["nodes"]["docs/api.md"]["depends_on"] == ["src/a.py", "src/b.py"]


def test_add_is_idempotent(repo: GitRepo, cli: Cli) -> None:
    repo.write("docs/api.md")
    repo.write("src/api.py")
    cli("add", "docs/api.md", "src/api.py")
    before = repo.graph_text()

    result = cli("add", "docs/api.md", "src/api.py")

    assert result.exit_code == 0
    assert repo.graph_text() == before


def test_graph_file_is_stable_and_sorted(repo: GitRepo, cli: Cli) -> None:
    for path in ("docs/z.md", "docs/a.md", "src/api.py"):
        repo.write(path)
    cli("add", "docs/z.md", "src/api.py")
    cli("add", "docs/a.md", "src/api.py")

    text = repo.graph_text()

    assert text.index('"docs/a.md"') < text.index('"docs/z.md"') < text.index('"src/api.py"')
    assert text.endswith("\n")


def test_add_normalises_paths(repo: GitRepo, cli: Cli) -> None:
    repo.write("docs/api.md")
    repo.write("src/api.py")

    assert cli("add", "./docs/api.md", "src\\api.py").exit_code == 0

    assert repo.graph()["nodes"]["docs/api.md"]["depends_on"] == ["src/api.py"]


def test_add_rejects_missing_file(repo: GitRepo, cli: Cli) -> None:
    repo.write("docs/api.md")

    result = cli("add", "docs/api.md", "src/typo.py")

    assert result.exit_code == 2
    assert "src/typo.py" in result.output


def test_add_accepts_external_nodes_without_file(repo: GitRepo, cli: Cli) -> None:
    repo.write("docs/api.md")
    repo.write("src/api.py")

    assert cli("add", "docs/api.md", "ext:stripe-api").exit_code == 0
    assert cli("add", "ext:wiki-api-page", "src/api.py").exit_code == 0

    nodes = repo.graph()["nodes"]
    assert nodes["ext:stripe-api"]["external"] is True
    assert nodes["ext:wiki-api-page"]["external"] is True
    assert "external" not in nodes["docs/api.md"]


def test_add_rejects_self_dependency(repo: GitRepo, cli: Cli) -> None:
    repo.write("docs/api.md")

    result = cli("add", "docs/api.md", "docs/api.md")

    assert result.exit_code == 2
    assert "docs/api.md" in result.output


def test_add_rejects_cycle_and_leaves_graph_unchanged(repo: GitRepo, cli: Cli) -> None:
    for path in ("a.md", "b.md", "c.md"):
        repo.write(path)
    cli("add", "a.md", "b.md")
    cli("add", "b.md", "c.md")
    before = repo.graph_text()

    result = cli("add", "c.md", "a.md")

    assert result.exit_code == 2
    assert "cycle" in result.output.lower()
    assert repo.graph_text() == before


def test_rm_removes_edge_and_prunes_orphans(repo: GitRepo, cli: Cli) -> None:
    for path in ("docs/api.md", "src/a.py", "src/b.py"):
        repo.write(path)
    cli("add", "docs/api.md", "src/a.py", "src/b.py")

    result = cli("rm", "docs/api.md", "src/a.py")

    assert result.exit_code == 0, result.output
    nodes = repo.graph()["nodes"]
    assert nodes["docs/api.md"]["depends_on"] == ["src/b.py"]
    assert "src/a.py" not in nodes


def test_rm_unknown_edge_fails(repo: GitRepo, cli: Cli) -> None:
    for path in ("docs/api.md", "src/a.py", "src/b.py"):
        repo.write(path)
    cli("add", "docs/api.md", "src/a.py")

    result = cli("rm", "docs/api.md", "src/b.py")

    assert result.exit_code == 2
    assert "src/b.py" in result.output


def test_show_lists_dependencies(repo: GitRepo, cli: Cli) -> None:
    for path in ("docs/api.md", "docs/guide.md", "src/api.py"):
        repo.write(path)
    cli("add", "docs/api.md", "src/api.py")
    cli("add", "docs/guide.md", "docs/api.md")

    result = cli("show")

    assert result.exit_code == 0
    for name in ("docs/api.md", "docs/guide.md", "src/api.py"):
        assert name in result.output


def test_show_node_lists_sources_and_dependents(repo: GitRepo, cli: Cli) -> None:
    for path in ("docs/api.md", "docs/guide.md", "src/api.py", "src/other.py"):
        repo.write(path)
    cli("add", "docs/api.md", "src/api.py")
    cli("add", "docs/guide.md", "docs/api.md")
    cli("add", "docs/guide.md", "src/other.py")

    result = cli("show", "docs/api.md")

    assert result.exit_code == 0
    assert "src/api.py" in result.output
    assert "docs/guide.md" in result.output
    assert "src/other.py" not in result.output


def test_commands_fail_cleanly_without_graph_file(repo: GitRepo, cli: Cli) -> None:
    for args in (("show",), ("check",), ("rm", "a", "b"), ("resolve", "a"), ("flag", "a")):
        result = cli(*args)
        assert result.exit_code == 2, args
        assert "freshdags.json" in result.output, args
