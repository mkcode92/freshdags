"""`add`, `rm`, `graph` and `neighbours`: maintaining the dependency graph in freshdags.json."""

import pytest
from support import GitRepo

from freshdags import models
from freshdags.api import FreshdagsApi
from freshdags.errors import (
    CycleError,
    FreshdagsError,
    GraphNotFoundError,
    SelfDependencyError,
    UnknownEdgeError,
    UnknownFileError,
    UnsupportedVersionError,
    UntrackedFileError,
)
from freshdags.models import Edge, NodeView


def test_add_creates_graph_file_with_defaults(repo: GitRepo, fd: FreshdagsApi) -> None:
    repo.write("docs/api.md")
    repo.write("src/api.py")

    fd.add("docs/api.md", "src/api.py")

    graph = repo.graph()
    assert graph["version"] == 2
    assert graph["settings"] == {"auto-flag": "on-commit", "auto-resolve": "on-commit"}
    assert graph["nodes"]["docs/api.md"]["depends_on"] == ["src/api.py"]
    assert "src/api.py" not in graph["nodes"], "sources appear only in depends_on"


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

    assert list(repo.graph()["nodes"]) == ["docs/a.md", "docs/z.md"]
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


def test_add_rejects_untracked_file(repo: GitRepo, fd: FreshdagsApi) -> None:
    """Only files git tracks can be checked; anything else must be an ext: node."""
    repo.write("docs/api.md")
    repo.write("src/scratch.py", stage=False)

    with pytest.raises(UntrackedFileError, match="src/scratch.py"):
        fd.add("docs/api.md", "src/scratch.py")


def test_add_accepts_external_nodes_without_file(repo: GitRepo, fd: FreshdagsApi) -> None:
    repo.write("docs/api.md")
    repo.write("src/api.py")

    fd.add("docs/api.md", "ext:stripe-api")
    fd.add("ext:wiki-api-page", "src/api.py")

    assert repo.graph()["nodes"]["ext:wiki-api-page"] == {"depends_on": ["src/api.py"]}
    assert "ext:stripe-api" in fd.graph().nodes


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


def test_newer_file_version_is_refused(repo: GitRepo, fd: FreshdagsApi) -> None:
    repo.write("freshdags.json", '{"version": 99, "nodes": {}}')

    with pytest.raises(UnsupportedVersionError, match="version 99"):
        fd.graph()


def test_file_without_version_is_refused(repo: GitRepo, fd: FreshdagsApi) -> None:
    repo.write("freshdags.json", '{"nodes": {}}')

    with pytest.raises(FreshdagsError, match="version"):
        fd.graph()


def test_broken_json_is_reported(repo: GitRepo, fd: FreshdagsApi) -> None:
    repo.write("freshdags.json", "{not json")

    with pytest.raises(FreshdagsError, match="not valid JSON"):
        fd.graph()


def test_older_file_version_is_upgraded_on_read(
    repo: GitRepo, fd: FreshdagsApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pretend the format is at version 3, with an upgrade from 2 that renames a key. A
    version-1 file goes through the real 1 -> 2 upgrade first."""
    monkeypatch.setattr(models, "GRAPH_VERSION", 3)
    monkeypatch.setattr("freshdags.core.GRAPH_VERSION", 3)
    monkeypatch.setitem(
        models.UPGRADES,
        2,
        lambda data: {"version": 2, "nodes": data["dependencies"]},
    )
    repo.write("docs/api.md")
    repo.write("freshdags.json", '{"version": 1, "dependencies": {"docs/api.md": {}}}')

    graph = fd.graph()

    assert graph.version == 3
    assert list(graph.nodes) == ["docs/api.md"]


# A freshdags.json exactly as freshdags 0.1.0 writes it.
VERSION_1_FILE = """{
  "nodes": {
    "docs/api.md": {
      "depends_on": ["src/api.py"],
      "resolved": {"at": "2026-01-02T10:00:00Z", "by": "Test", "commit": null}
    }
  },
  "settings": {"auto-flag": "on-commit", "auto-resolve": "on-commit"},
  "version": 1
}
"""


def test_version_1_file_is_saved_as_version_2(repo: GitRepo, fd: FreshdagsApi) -> None:
    repo.write("docs/api.md")
    repo.write("src/api.py")
    repo.write("src/models.py")
    repo.write("freshdags.json", VERSION_1_FILE)

    fd.add("docs/api.md", "src/models.py")

    graph = repo.graph()
    assert graph["version"] == 2
    assert graph["nodes"]["docs/api.md"]["resolved"] == {
        "at": "2026-01-02T10:00:00Z",
        "by": "Test",
        "commit": None,
    }, "an upgraded resolve keeps its record and gains no sources"


def test_reading_a_version_1_file_does_not_rewrite_it(repo: GitRepo, fd: FreshdagsApi) -> None:
    repo.write("docs/api.md")
    repo.write("src/api.py")
    repo.write("freshdags.json", VERSION_1_FILE)

    fd.graph()
    fd.check()

    assert repo.graph_text() == VERSION_1_FILE


@pytest.mark.parametrize(
    "call",
    [
        lambda fd: fd.graph(),
        lambda fd: fd.neighbours("a"),
        lambda fd: fd.node_status(),
        lambda fd: fd.check(),
        lambda fd: fd.rm("a", "b"),
        lambda fd: fd.resolve("a"),
        lambda fd: fd.resolve_all(),
        lambda fd: fd.flag("a"),
    ],
    ids=["graph", "neighbours", "node_status", "check", "rm", "resolve", "resolve_all", "flag"],
)
def test_methods_fail_cleanly_without_graph_file(repo: GitRepo, fd: FreshdagsApi, call) -> None:
    with pytest.raises(GraphNotFoundError, match="freshdags.json"):
        call(fd)
