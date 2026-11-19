"""Wall-clock access, isolated so tests can pin the current time."""

from datetime import UTC, datetime


def now() -> datetime:
    return datetime.now(UTC)
