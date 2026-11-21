"""Human-readable output for the CLI."""

from freshdags.models import CheckReport, Graph, NodeView


def render_check(report: CheckReport) -> str:
    """Format a check report for a terminal.

    For each drift: what changed, a `git diff` command to review it, and how to clear the
    flag. For external or flagged sources, the flag note replaces the diff. Ends with a
    summary line led by the badger.
    """
    raise NotImplementedError


def render_graph(graph: Graph) -> str:
    """Format the whole graph: each doc with the sources it depends on."""
    raise NotImplementedError


def render_node(view: NodeView) -> str:
    """Format one node with its sources and dependents."""
    raise NotImplementedError
