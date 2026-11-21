"""The freshdags interface: every CLI command as a method.

The CLI only parses arguments, calls one of these methods and renders the result. Tests
exercise the methods directly.

Node names are file paths relative to the repository root, or external names starting with
`ext:`. Paths given by the caller are normalised: `./docs\\api.md` becomes `docs/api.md`.

Every method except `add` raises GraphNotFoundError when freshdags.json does not exist.
All errors derive from freshdags.errors.FreshdagsError.
"""

from abc import ABC, abstractmethod

from freshdags.models import CheckReport, Graph, NodeView


class FreshdagsApi(ABC):
    """Operations on the dependency graph of one git repository."""

    # --- editing the graph ------------------------------------------------------------------

    @abstractmethod
    def add(self, doc: str, *sources: str) -> None:
        """Record that `doc` depends on each of `sources`.

        Creates freshdags.json with default settings if it does not exist. Adding an edge
        that already exists changes nothing.

        Raises:
            UnknownFileError: a non-external node is not an existing file.
            SelfDependencyError: `doc` is among `sources`.
            CycleError: an edge would close a cycle. The graph is left unchanged.
        """

    @abstractmethod
    def rm(self, doc: str, *sources: str) -> None:
        """Remove the edges from `doc` to each of `sources`.

        Nodes left without any edge are removed.

        Raises:
            UnknownEdgeError: one of the edges does not exist. The graph is left unchanged.
        """

    # --- reading the graph ------------------------------------------------------------------

    @abstractmethod
    def graph(self) -> Graph:
        """The whole graph as stored in freshdags.json."""

    @abstractmethod
    def neighbours(self, node: str) -> NodeView:
        """`node` with its direct sources and dependents.

        Raises:
            UnknownNodeError: `node` is not in the graph.
        """

    # --- drift ------------------------------------------------------------------------------

    @abstractmethod
    def check(self, rev: str | None = None) -> CheckReport:
        """Find every doc that is older than one of its sources.

        Without `rev`, uses the current freshdags.json and, in `on-change` mode, the working
        tree. With `rev`, uses freshdags.json and the history as of that commit only.
        """

    # Flags and resolves are scoped to nodes: a file goes stale, and a review covers all of
    # its changed sources at once.

    @abstractmethod
    def resolve(self, *docs: str) -> list[str]:
        """Record that each doc was reviewed and is up to date. Returns the docs resolved.

        Does not flag the docs that depend on them.

        Raises:
            UnknownNodeError: a doc is not in the graph.
        """

    @abstractmethod
    def resolve_all(self) -> list[str]:
        """Resolve every drifted doc, when the change needed no doc update.

        Returns the docs resolved.
        """

    @abstractmethod
    def flag(self, node: str, note: str | None = None) -> None:
        """Record that `node` changed in a way git cannot see, flagging its dependents.

        Raises:
            UnknownNodeError: `node` is not in the graph.
        """
