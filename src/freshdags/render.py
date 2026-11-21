"""Human-readable output for the CLI."""

from itertools import groupby

from freshdags.models import CheckReport, Drift, Graph, NodeView, Settings

SHORT_SHA = 7


def render_check(report: CheckReport) -> str:
    """Format a check report for a terminal.

    For each drift: what changed, a `git diff` command to review it, and how to clear the
    flag. For external or flagged sources, the flag note replaces the diff. Ends with a
    summary line led by the badger.
    """
    blocks = []
    for doc, drifts in groupby(report.drift, key=lambda d: d.doc):
        lines = [f"{doc} may have drifted"]
        for drift in drifts:
            lines.extend(_describe(drift, report.rev))
        lines.append(f"  then: update {doc}, or run: freshdags resolve {doc}")
        blocks.append("\n".join(lines))
    blocks.append(_summary(report))
    return "\n\n".join(blocks)


def _describe(drift: Drift, rev: str | None) -> list[str]:
    fresh = drift.doc_fresh_commit
    if drift.note is not None or (drift.source_changed_commit is None and fresh is None):
        note = f": {drift.note}" if drift.note else ""
        return [f"  {drift.source} flagged{note}"]
    since = f" since {fresh[:SHORT_SHA]}" if fresh else ""
    lines = [f"  {drift.source} changed{since}"]
    if fresh:
        # A committed change is diffed up to the checked revision, a saved one against the
        # working tree.
        end = f"..{rev or 'HEAD'}" if drift.source_changed_commit else ""
        lines.append(f"    review: git diff {fresh[:SHORT_SHA]}{end} -- {drift.source}")
    return lines


def _summary(report: CheckReport) -> str:
    if not report.ok:
        count = len(report.drifted_docs)
        return f"🦡 {count} {_docs(count)} may have drifted. The badger is watching."
    if report.docs_checked == 0:
        return "🦡✨ Nothing to check yet. Add a dependency with `freshdags add DOC SOURCE`."
    if report.docs_checked == 1:
        return "🦡✨ 1 doc is fresh."
    return f"🦡✨ All {report.docs_checked} docs are fresh."


def _docs(count: int) -> str:
    return "doc" if count == 1 else "docs"


def render_graph(graph: Graph) -> str:
    """Format the whole graph: each doc with the sources it depends on."""
    lines = []
    for doc, node in sorted(graph.nodes.items()):
        if node.depends_on:
            lines.append(doc)
            lines.extend(f"  {source}" for source in node.depends_on)
    return "\n".join(lines) or "No dependencies yet. Add one with `freshdags add DOC SOURCE`."


def render_settings(settings: Settings) -> str:
    """One `name: value` line per setting."""
    return "\n".join(
        f"{name}: {value}"
        for name, value in settings.model_dump(mode="json", by_alias=True).items()
    )


def render_node(view: NodeView) -> str:
    """Format one node with its sources and dependents."""
    return "\n".join(
        [
            view.name,
            f"  depends on: {', '.join(view.sources) or '-'}",
            f"  needed by:  {', '.join(view.dependents) or '-'}",
        ]
    )
