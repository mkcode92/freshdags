"""`add`, `rm`, `graph` and `neighbours`: maintaining the dependency graph in freshdags.json."""

import pytest
from support import GitRepo

from freshdags.api import FreshdagsApi
from freshdags.errors import (
    CycleError,
    GraphNotFoundError,
    SelfDependencyError,
    UnknownEdgeError,
    UnknownFileError,
)
from freshdags.models import Edge, NodeView


def test_add_creates_graph_file_with_defaults(repo: GitRepo, fd: FreshdagsApi) -> None:
    repo.write("docs/api.md")
    repo.write("src/api.py")

    fd.add("docs/api.md", "src/api.py")

    graph = repo.graph()
    assert graph["version"] == 1
    assert graph["settings"] == {"flag": "on-commit", "resolve": "on-commit"}
    assert graph["nodes"]["docs/api.md"]["depends_on"] == ["src/api.py"]
    assert "src/api.py" in graph["nodes"]


def test_add_several_sources_keeps_them_sorted(repo: GitRepo, fd: FreshdagsApi) -> None:
    for path in ("docs/api.md", "src/b.py", "src/a.py"):
        repo.write(path)

    fd.add("docs/api.md", "src/b.py", "src/a.py")

    assert repo.graph()["nodes"]["docs/api.md"]["depends_on"] == ["src/a.py", "src/b.py"]


def test_add_is_idempotent(repo: GitRepo, fd: FreshdagsApi) -> None:
    repo.write("docs/api.md")
    repo.write("src/api.py")
    fd.add("docs/api.md", "src/api.py")
    before = repo.graph_text()

    fd.add("docs/api.md", "src/api.py")

    assert repo.graph_text() == before


def test_graph_file_is_stable_and_sorted(repo: GitRepo, fd: FreshdagsApi) -> None:
    for path in ("docs/z.md", "docs/a.md", "src/api.py"):
        repo.write(path)
    fd.add("docs/z.md", "src/api.py")
    fd.add("docs/a.md", "src/api.py")

    text = repo.graph_text()

    assert list(repo.graph()["nodes"]) == ["docs/a.md", "docs/z.md", "src/api.py"]
    assert text.endswith("\n")


def test_add_normalises_paths(repo: GitRepo, fd: FreshdagsApi) -> None:
    repo.write("docs/api.md")
    repo.write("src/api.py")

    fd.add("./docs/api.md", "src\\api.py")

    assert repo.graph()["nodes"]["docs/api.md"]["depends_on"] == ["src/api.py"]


def test_add_rejects_missing_file(repo: GitRepo, fd: FreshdagsApi) -> None:
    repo.write("docs/api.md")

    with pytest.raises(UnknownFileError, match="src/typo.py"):
        fd.add("docs/api.md", "src/typo.py")


def test_add_accepts_external_nodes_without_file(repo: GitRepo, fd: FreshdagsApi) -> None:
    repo.write("docs/api.md")
    repo.write("src/api.py")

    fd.add("docs/api.md", "ext:stripe-api")
    fd.add("ext:wiki-api-page", "src/api.py")

    nodes = repo.graph()["nodes"]
    assert nodes["ext:stripe-api"]["external"] is True
    assert nodes["ext:wiki-api-page"]["external"] is True
    assert "external" not in nodes["docs/api.md"]


def test_add_rejects_self_dependency(repo: GitRepo, fd: FreshdagsApi) -> None:
    repo.write("docs/api.md")

    with pytest.raises(SelfDependencyError, match="docs/api.md"):
        fd.add("docs/api.md", "docs/api.md")


def test_add_rejects_cycle_and_leaves_graph_unchanged(repo: GitRepo, fd: FreshdagsApi) -> None:
    for path in ("a.md", "b.md", "c.md"):
        repo.write(path)
    fd.add("a.md", "b.md")
    fd.add("b.md", "c.md")
    before = repo.graph_text()

    with pytest.raises(CycleError):
        fd.add("c.md", "a.md")

    assert repo.graph_text() == before


def test_rm_removes_edge_and_prunes_orphans(repo: GitRepo, fd: FreshdagsApi) -> None:
    for path in ("docs/api.md", "src/a.py", "src/b.py"):
        repo.write(path)
    fd.add("docs/api.md", "src/a.py", "src/b.py")

    fd.rm("docs/api.md", "src/a.py")

    nodes = repo.graph()["nodes"]
    assert nodes["docs/api.md"]["depends_on"] == ["src/b.py"]
    assert "src/a.py" not in nodes


def test_rm_unknown_edge_fails(repo: GitRepo, fd: FreshdagsApi) -> None:
    for path in ("docs/api.md", "src/a.py", "src/b.py"):
        repo.write(path)
    fd.add("docs/api.md", "src/a.py")

    with pytest.raises(UnknownEdgeError, match="src/b.py"):
        fd.rm("docs/api.md", "src/b.py")


def test_graph_lists_dependencies(repo: GitRepo, fd: FreshdagsApi) -> None:
    for path in ("docs/api.md", "docs/guide.md", "src/api.py"):
        repo.write(path)
    fd.add("docs/api.md", "src/api.py")
    fd.add("docs/guide.md", "docs/api.md")

    assert fd.graph().edges() == [
        Edge(doc="docs/api.md", source="src/api.py"),
        Edge(doc="docs/guide.md", source="docs/api.md"),
    ]


def test_neighbours_lists_sources_and_dependents(repo: GitRepo, fd: FreshdagsApi) -> None:
    for path in ("docs/api.md", "docs/guide.md", "src/api.py", "src/other.py"):
        repo.write(path)
    fd.add("docs/api.md", "src/api.py")
    fd.add("docs/guide.md", "docs/api.md", "src/other.py")

    assert fd.neighbours("docs/api.md") == NodeView(
        name="docs/api.md", sources=["src/api.py"], dependents=["docs/guide.md"]
    )


@pytest.mark.parametrize(
    "call",
    [
        lambda fd: fd.graph(),
        lambda fd: fd.neighbours("a"),
        lambda fd: fd.check(),
        lambda fd: fd.rm("a", "b"),
        lambda fd: fd.resolve("a"),
        lambda fd: fd.resolve_all(),
        lambda fd: fd.flag("a"),
    ],
    ids=["graph", "neighbours", "check", "rm", "resolve", "resolve_all", "flag"],
)
def test_methods_fail_cleanly_without_graph_file(repo: GitRepo, fd: FreshdagsApi, call) -> None:
    with pytest.raises(GraphNotFoundError, match="freshdags.json"):
        call(fd)
