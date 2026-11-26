"""Data models: the graph file, its settings, and the results of queries."""

import json
from collections.abc import Callable
from enum import StrEnum
from typing import Any, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

GRAPH_FILE = "freshdags.json"
EXTERNAL_PREFIX = "ext:"

GRAPH_VERSION = 1
"""Format version of freshdags.json. Bump it only for breaking changes, and add an upgrade."""

UPGRADES: dict[int, Callable[[dict[str, Any]], dict[str, Any]]] = {}
"""`UPGRADES[n]` turns the raw data of a version-n file into version n + 1."""


def upgrade(data: dict[str, Any]) -> dict[str, Any]:
    """Bring raw graph data of an older (or the current) version to GRAPH_VERSION."""
    while (version := data["version"]) < GRAPH_VERSION:
        data = UPGRADES[version](data) | {"version": version + 1}
    return data


def is_external(node: str) -> bool:
    return node.startswith(EXTERNAL_PREFIX)


# --- settings ------------------------------------------------------------------------------


class Mode(StrEnum):
    """What flags a source (`auto-flag`) or resolves a doc (`auto-resolve`) automatically.

    The `flag` and `resolve` commands work in every mode.
    """

    OFF = "off"
    """Nothing automatic; only the commands."""
    ON_COMMIT = "on-commit"
    """A commit to the file."""
    ON_CHANGE = "on-change"
    """A commit, or an uncommitted save."""


class Settings(BaseModel):
    """Written as `auto-flag` / `auto-resolve` in freshdags.json."""

    model_config = ConfigDict(extra="forbid", validate_by_name=True, validate_by_alias=True)

    auto_flag: Mode = Field(Mode.ON_COMMIT, alias="auto-flag")
    """What marks a source as changed, besides `freshdags flag`."""
    auto_resolve: Mode = Field(Mode.ON_COMMIT, alias="auto-resolve")
    """What brings a doc up to date, besides `freshdags resolve`."""


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

    Whether a node is external follows from its name (see `is_external`). Flags and resolves
    are scoped to nodes: a file goes stale, and a review covers all of its sources at once.
    """

    model_config = ConfigDict(extra="forbid")

    depends_on: list[str] = []
    """Sources this node depends on, sorted and unique."""
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
    """Contents of freshdags.json.

    The file lists only nodes that carry something: sources a doc depends on, or a record.
    Every source named in a `depends_on` list gets a node when the file is read, so `nodes`
    always holds the whole graph.
    """

    model_config = ConfigDict(extra="forbid")

    version: int = GRAPH_VERSION
    settings: Settings = Settings()
    nodes: dict[str, Node] = {}

    @model_validator(mode="after")
    def _add_implicit_sources(self) -> Self:
        for node in list(self.nodes.values()):
            for source in node.depends_on:
                self.nodes.setdefault(source, Node())
        return self

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

        Settings are always written in full. Node fields are written only when they differ
        from their defaults, and nodes left empty that way are omitted.
        """
        data = {
            "version": self.version,
            "settings": self.settings.model_dump(mode="json", by_alias=True),
            "nodes": {
                name: fields
                for name, node in self.nodes.items()
                if (fields := node.model_dump(mode="json", exclude_defaults=True))
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


class Commit(BaseModel):
    sha: str
    at: AwareDatetime
    """Author date."""
    author: str
    subject: str
    """First line of the message."""


class NodeStatus(BaseModel):
    """What is known about one node, besides its edges."""

    name: str
    last_commit: Commit | None
    """Latest commit touching the file; None for external and never-committed files."""
    saved_at: AwareDatetime | None
    """Modification time of the file's uncommitted changes, if it has any."""
    resolved: Resolution | None
    """Last `freshdags resolve`."""
    flagged: Flag | None
    """Last `freshdags flag`."""


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
    flagged: bool = False
    """The change was recorded by `freshdags flag`; otherwise git saw it, as a commit or,
    when `source_changed_commit` is None, an uncommitted save."""


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
