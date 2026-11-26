"""Diagrams of the graph (`show --format mermaid|dot|html`): edges point from source to doc,
external nodes are dashed, drift is highlighted, and DOT and HTML explain it in tooltips."""

import json
from datetime import datetime

from support import T1, T2

from freshdags.models import CheckReport, Commit, Drift, Graph, Node, NodeStatus
from freshdags.render import (
    MERMAID_INTEGRITY,
    MERMAID_VERSION,
    render_dot,
    render_html,
    render_markdown,
    render_mermaid,
)


def report(*drift: Drift) -> CheckReport:
    return CheckReport(rev=None, docs_checked=2, drift=list(drift))


def stale(doc: str, source: str) -> Drift:
    return Drift(
        doc=doc,
        source=source,
        doc_fresh_at=datetime.fromisoformat(T1),
        doc_fresh_commit=None,
        source_changed_at=datetime.fromisoformat(T2),
        source_changed_commit=None,
        note=None,
    )


API = Graph(
    nodes={
        "docs/api.md": Node(depends_on=["ext:stripe-api", "src/api.py"]),
        "Readme.md": Node(depends_on=["docs/api.md"]),
    }
)


# --- mermaid -------------------------------------------------------------------------------


def test_mermaid_draws_nodes_and_edges_from_source_to_doc() -> None:
    assert render_mermaid(API).splitlines() == [
        "flowchart RL",
        '  n0["Readme.md"]',
        '  n1["docs/api.md"]',
        '  n2(["ext:stripe-api"])',
        '  n3["src/api.py"]',
        "  n1 --> n0",
        "  n2 --> n1",
        "  n3 --> n1",
        "  classDef external stroke-dasharray: 4 3",
        "  class n2 external",
    ]


def test_mermaid_colours_drifted_docs_and_changed_sources() -> None:
    lines = render_mermaid(API, report(stale("docs/api.md", "src/api.py"))).splitlines()

    assert "  class n1 drifted" in lines
    assert "  class n3 changed" in lines
    assert not any(line.startswith("  linkStyle") for line in lines)


def test_mermaid_marks_a_doc_that_drifted_and_changed() -> None:
    drift = report(stale("Readme.md", "docs/api.md"), stale("docs/api.md", "src/api.py"))

    lines = render_mermaid(API, drift).splitlines()

    assert "  class n0 drifted" in lines
    assert "  class n1 drifted_changed" in lines
    assert "  class n3 changed" in lines


def test_mermaid_escapes_labels() -> None:
    text = render_mermaid(Graph(nodes={'a "b" <c> #d.md': Node(depends_on=["src.py"])}))

    assert '  n0["a #quot;b#quot; #lt;c#gt; #35;d.md"]' in text


def test_mermaid_empty_graph() -> None:
    assert render_mermaid(Graph()) == "flowchart RL"


def test_markdown_wraps_mermaid_in_a_fence() -> None:
    assert render_markdown(API) == f"```mermaid\n{render_mermaid(API)}\n```"


# --- dot -----------------------------------------------------------------------------------


def test_dot_draws_nodes_and_edges_from_source_to_doc() -> None:
    assert render_dot(API).splitlines() == [
        "digraph freshdags {",
        "  rankdir=RL;",
        "  node [shape=box];",
        '  "Readme.md";',
        '  "docs/api.md";',
        '  "ext:stripe-api" [style="rounded,dashed"];',
        '  "src/api.py";',
        '  "docs/api.md" -> "Readme.md";',
        '  "ext:stripe-api" -> "docs/api.md";',
        '  "src/api.py" -> "docs/api.md";',
        "}",
    ]


def test_dot_colours_drifted_docs_and_changed_sources() -> None:
    lines = render_dot(API, report(stale("docs/api.md", "src/api.py"))).splitlines()

    assert any(
        line.startswith('  "docs/api.md" [style="filled" color="#cf222e" fillcolor="#ffebe9"')
        for line in lines
    )
    assert any(
        line.startswith('  "src/api.py" [style="filled" color="#bf8700" fillcolor="#fff8c5"')
        for line in lines
    )
    assert '  "src/api.py" -> "docs/api.md";' in lines


def test_dot_escapes_ids() -> None:
    text = render_dot(Graph(nodes={'a"b\\c.md': Node(depends_on=["src.py"])}))

    assert '  "a\\"b\\\\c.md";' in text


def test_dot_tooltips_explain_drift() -> None:
    lines = render_dot(API, report(stale("docs/api.md", "src/api.py"))).splitlines()

    assert (
        '  "docs/api.md" [style="filled" color="#cf222e" fillcolor="#ffebe9" penwidth=1.5 '
        'tooltip="docs/api.md\\nmay have drifted:\\n  src/api.py changed (uncommitted)'
        '\\n    review: git diff HEAD -- src/api.py"];'
    ) in lines
    assert any(
        line.endswith('tooltip="src/api.py\\nchanged after: docs/api.md"];') for line in lines
    )
    assert '  "Readme.md" [tooltip="Readme.md\\nfresh"];' in lines


def test_dot_without_report_has_no_tooltips() -> None:
    assert "tooltip" not in render_dot(API)


# --- html ----------------------------------------------------------------------------------


def test_html_embeds_escaped_diagram() -> None:
    page = render_html(API, report(stale("docs/api.md", "src/api.py")))

    assert '<pre class="mermaid">flowchart RL\n' in page
    assert "  n3 --&gt; n1" in page
    assert "1 doc may have drifted" in page


def test_html_leaves_state_colours_to_its_stylesheet() -> None:
    page = render_html(API, report(stale("docs/api.md", "src/api.py")))

    assert "  classDef drifted stroke-width:1.5px\n  class n1 drifted\n" in page
    assert "fill:#" not in page.split('<pre class="mermaid">')[1].split("</pre>")[0]


def test_html_tooltips_are_json_by_node_id() -> None:
    page = render_html(API, report(stale("docs/api.md", "src/api.py")))

    data = page.split('<script type="application/json" id="tooltips">')[1].split("</script>")[0]
    tips = json.loads(data)
    assert tips["n1"].startswith("docs/api.md\nmay have drifted:\n  src/api.py changed")
    assert tips["n3"] == "src/api.py\nchanged after: docs/api.md"
    assert "click" not in page


def test_html_tooltips_cannot_close_their_script() -> None:
    graph = Graph(nodes={"docs/</script>.md": Node(depends_on=["src.py"])})

    page = render_html(graph, report(stale("docs/</script>.md", "src.py")))

    assert page.count("</script>") == 3  # the JSON block, Mermaid and the module


def test_html_placeholders_in_paths_stay_literal() -> None:
    graph = Graph(nodes={"docs/{{tooltips}}.md": Node(depends_on=["src.py"])})

    page = render_html(graph, report(stale("docs/{{tooltips}}.md", "src.py")))

    assert "[&quot;docs/{{tooltips}}.md&quot;]" in page
    assert page.count("</script>") == 3


def test_html_pins_mermaid_and_sends_nothing() -> None:
    page = render_html(API, report())

    assert f'integrity="{MERMAID_INTEGRITY}"' in page
    assert f'mermaid@{MERMAID_VERSION}/dist/mermaid.min.js"' in page
    assert "default-src 'none'" in page
    assert "connect-src 'none'" in page
    assert '<meta name="referrer" content="no-referrer">' in page


def test_html_is_ascii() -> None:
    page = render_html(Graph(nodes={"docs/über.md": Node(depends_on=["src.py"])}), report())

    assert page.isascii()
    assert "docs/&#252;ber.md" in page
    assert "&#129441;" in page  # the badger in the summary


def test_tooltips_show_node_history() -> None:
    commit = Commit(sha="c" * 40, at=datetime.fromisoformat(T1), author="Jane", subject="Fix")
    status = [
        NodeStatus(
            name="src/api.py",
            last_commit=commit,
            saved_at=datetime.fromisoformat(T2),
            resolved=None,
            flagged=None,
        )
    ]

    page = render_html(API, report(), status)

    when = datetime.fromisoformat(T1).astimezone().strftime("%Y-%m-%d %H:%M")
    assert f"last commit: ccccccc, {when} by Jane" in page
    assert "uncommitted changes, saved" in page
