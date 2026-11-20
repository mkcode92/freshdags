"""Data models: the graph file, its settings, and the results of queries."""

import json
from enum import StrEnum
from typing import Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, field_validator

GRAPH_FILE = "freshdags.json"
EXTERNAL_PREFIX = "ext:"


def is_external(node: str) -> bool:
    return node.startswith(EXTERNAL_PREFIX)


# --- settings ------------------------------------------------------------------------------


class Mode(StrEnum):
    """What counts as a change (`flag`) or as bringing a doc up to date (`resolve`)."""

    MANUAL = "manual"
    """Only the `flag` / `resolve` command."""
    ON_COMMIT = "on-commit"
    """A commit to the file, or the command."""
    ON_CHANGE = "on-change"
    """An uncommitted save, a commit, or the command."""


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    flag: Mode = Mode.ON_COMMIT
    resolve: Mode = Mode.ON_COMMIT


# --- graph ---------------------------------------------------------------------------------


class Record(BaseModel):
    """Who did something, and when (wall-clock time)."""

    model_config = ConfigDict(extra="forbid")

    at: AwareDatetime
    by: str


class Resolution(Record):
    """`freshdags resolve`: the doc was reviewed and is up to date with all its sources."""

    commit: str | None
    """HEAD at the time of resolving; None in a repository without commits."""


class Flag(Record):
    """`freshdags flag`: the node changed in a way git cannot see."""

    note: str | None = None


class Node(BaseModel):
    """A file path relative to the repository root, or an external `ext:<name>`.

    Flags and resolves are scoped to nodes: a file goes stale, and a review covers all of
    its sources at once.
    """

    model_config = ConfigDict(extra="forbid")

    depends_on: list[str] = []
    """Sources this node depends on, sorted and unique."""
    external: bool = False
    resolved: Resolution | None = None
    """Last `freshdags resolve` of this node as a doc."""
    flagged: Flag | None = None
    """Last `freshdags flag` of this node as a source. Applies to all its dependents."""

    @field_validator("depends_on")
    @classmethod
    def _sorted_unique(cls, value: list[str]) -> list[str]:
        return sorted(set(value))


class Edge(BaseModel):
    """`doc` depends on `source`."""

    model_config = ConfigDict(frozen=True)

    doc: str
    source: str


class Graph(BaseModel):
    """Contents of freshdags.json."""

    model_config = ConfigDict(extra="forbid")

    version: Literal[1] = 1
    settings: Settings = Settings()
    nodes: dict[str, Node] = {}

    def edges(self) -> list[Edge]:
        """All edges, sorted by doc, then source."""
        return [
            Edge(doc=doc, source=source)
            for doc, node in sorted(self.nodes.items())
            for source in node.depends_on
        ]

    @classmethod
    def from_json(cls, text: str) -> Self:
        return cls.model_validate_json(text)

    def to_json(self) -> str:
        """Stable, diff-friendly JSON: sorted keys, two-space indent, trailing newline.

        Settings are always written in full; node fields are written only when they differ
        from their defaults.
        """
        data = {
            "version": self.version,
            "settings": self.settings.model_dump(mode="json"),
            "nodes": {
                name: node.model_dump(mode="json", exclude_defaults=True)
                for name, node in self.nodes.items()
            },
        }
        return json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


# --- query results -------------------------------------------------------------------------


class NodeView(BaseModel):
    """One node with its direct neighbours."""

    name: str
    sources: list[str]
    """What this node depends on."""
    dependents: list[str]
    """What depends on this node."""


class Drift(BaseModel):
    """`doc` is stale: `source` changed after the doc was last up to date. A doc with
    several changed sources has one Drift per source, so the report shows them all."""

    doc: str
    source: str
    doc_fresh_at: AwareDatetime | None
    """When the doc was last up to date; None if never (e.g. an unresolved external doc)."""
    doc_fresh_commit: str | None
    """Commit at which the doc was last up to date; start of the review diff."""
    source_changed_at: AwareDatetime
    source_changed_commit: str | None
    """Commit that changed the source; None for a `flag` or an uncommitted save."""
    note: str | None
    """Note from `freshdags flag`, if the change was flagged by hand."""


class CheckReport(BaseModel):
    rev: str | None
    """The revision checked as given by the caller; None means the working tree."""
    docs_checked: int
    """Number of nodes that depend on something."""
    drift: list[Drift]
    """Every drifted edge, sorted by doc, then source."""

    @property
    def ok(self) -> bool:
        return not self.drift

    @property
    def drifted_docs(self) -> list[str]:
        return sorted({d.doc for d in self.drift})
