"""Human-readable output for the CLI."""

from freshdags.models import CheckReport


def render_check(report: CheckReport, *, emoji: bool = True) -> str:
    """Format a check report for a terminal.

    For each drift: what changed, a `git diff` command to review it, and how to clear the
    flag. For external or flagged sources, the flag note replaces the diff. Ends with a
    summary line led by the badger, unless `emoji` is False.
    """
    raise NotImplementedError
