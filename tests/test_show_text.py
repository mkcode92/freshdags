"""`show` as text: `(!)` marks a doc that may have drifted, `(*)` a source that changed
after the doc it is listed under was up to date."""

from datetime import datetime

from support import T1, T2

from freshdags.models import CheckReport, Drift, Graph, Node, NodeView
from freshdags.render import MARKS_LEGEND, render_graph, render_node

GRAPH = Graph(
    nodes={
        "docs/api.md": Node(depends_on=["src/api.py", "src/models.py"]),
        "docs/guide.md": Node(depends_on=["docs/api.md"]),
    }
)


def report(*edges: tuple[str, str]) -> CheckReport:
    drift = [
        Drift(
            doc=doc,
            source=source,
            doc_fresh_at=datetime.fromisoformat(T1),
            doc_fresh_commit=None,
            source_changed_at=datetime.fromisoformat(T2),
            source_changed_commit=None,
            note=None,
        )
        for doc, source in edges
    ]
    return CheckReport(rev=None, docs_checked=2, drift=drift)


def test_graph_without_drift_has_no_marks() -> None:
    text = render_graph(GRAPH, report())

    assert "(!)" not in text
    assert "(*)" not in text
    assert MARKS_LEGEND not in text


def test_graph_marks_drifted_docs_and_changed_sources() -> None:
    text = render_graph(GRAPH, report(("docs/api.md", "src/api.py")))

    assert text.splitlines() == [
        "docs/api.md (!)",
        "  src/api.py (*)",
        "  src/models.py",
        "docs/guide.md",
        "  docs/api.md (!)",
        "",
        MARKS_LEGEND,
    ]


def test_graph_marks_a_doc_that_drifted_and_changed() -> None:
    drift = report(("docs/api.md", "src/api.py"), ("docs/guide.md", "docs/api.md"))

    assert "  docs/api.md (!) (*)" in render_graph(GRAPH, drift).splitlines()


def test_node_marks_its_changed_sources_and_drifted_dependents() -> None:
    view = NodeView(name="docs/api.md", sources=["src/api.py"], dependents=["docs/guide.md"])
    drift = report(("docs/api.md", "src/api.py"), ("docs/guide.md", "docs/api.md"))

    assert render_node(view, drift).splitlines() == [
        "docs/api.md (!)",
        "  depends on: src/api.py (*)",
        "  needed by:  docs/guide.md (!)",
        "",
        MARKS_LEGEND,
    ]


def test_node_legend_only_when_its_lines_are_marked() -> None:
    view = NodeView(name="src/models.py", sources=[], dependents=["docs/api.md"])

    text = render_node(view, report(("docs/guide.md", "docs/api.md")))

    assert MARKS_LEGEND not in text
